import os, tempfile, time, unittest, sys, subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

class Behavior(unittest.TestCase):
    def test_cache_preserves_recent_and_symlink_target(self):
        with tempfile.TemporaryDirectory() as value:
            root=Path(value); cache=root/'cache'; cache.mkdir(); docs=root/'documents'; docs.mkdir(); protected=docs/'important.txt'; protected.write_text('keep')
            old=cache/'old'; old.write_bytes(b'12345'); os.utime(old,(time.time()-172800,)*2)
            fresh=cache/'fresh'; fresh.write_text('keep')
            try: (cache/'link').symlink_to(docs,target_is_directory=True)
            except OSError: pass
            failures=[]; count,skipped=core.clean_tree(cache,time.time()-86400,failures)
            self.assertEqual(count,5); self.assertFalse(old.exists()); self.assertTrue(fresh.exists()); self.assertEqual(protected.read_text(),'keep'); self.assertFalse(failures)
    def test_rejects_dangerous_data_paths(self):
        for p in [Path.home(),core.data_roots()[0],Path.home()/'Documents',core.data_roots()[0]/'Microsoft',core.STATE]:
            with self.subTest(path=p):
                with self.assertRaises(ValueError): core.check_data_path(p)
    def test_accepts_specific_app_directory(self):
        p=core.data_roots()[0]/'PCStewardTestApp'; self.assertEqual(core.check_data_path(p),p.absolute())
    @unittest.skipIf(core.WINDOWS,'Linux XDG test')
    def test_xdg_toggle_preserves_exec_and_system_original(self):
        with tempfile.TemporaryDirectory() as value:
            root=Path(value); original=root/'vendor.desktop'; original.write_text('[Desktop Entry]\nType=Application\nName=Sample\nExec=/usr/bin/true --sample\n')
            target=root/'user/sample.desktop'; item=core.Entry('test','test','test',meta={'type':'xdg','path':str(original),'target':str(target)})
            core.linux_toggle(item,False); self.assertEqual(core.desktop_config(target)['Desktop Entry']['Hidden'],'true'); self.assertEqual(core.desktop_config(target)['Desktop Entry']['Exec'],'/usr/bin/true --sample')
            item.meta['path']=str(target); core.linux_toggle(item,True); self.assertEqual(core.desktop_config(target)['Desktop Entry']['Hidden'],'false'); self.assertNotIn('Hidden=',original.read_text())
    @unittest.skipUnless(core.WINDOWS,'Windows registry fixture')
    def test_windows_startup_disable_enable(self):
        import winreg as w
        name='PCSteward-Acceptance-Fixture'; path='Software\\Microsoft\\Windows\\CurrentVersion\\Run'
        try:
            with w.CreateKey(w.HKEY_CURRENT_USER,path) as k: w.SetValueEx(k,name,0,w.REG_SZ,'notepad.exe')
            item=next(e for e in core.windows_startup() if e.name==name and not e.meta.get('disabled'))
            core.windows_toggle(item,False); items=[e for e in core.windows_startup() if e.name==name]; self.assertTrue(items); self.assertFalse(any(e.enabled for e in items))
            core.windows_toggle(next(e for e in items if e.meta['disabled']),True)
            items=[e for e in core.windows_startup() if e.name==name]; self.assertTrue(any(e.enabled for e in items)); self.assertEqual(items[0].detail,'notepad.exe')
        finally:
            for key in [path,'Software\\Microsoft\\Windows\\CurrentVersion\\PCStewardDisabledRun','Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run','Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run32']:
                try:
                    with w.OpenKey(w.HKEY_CURRENT_USER,key,0,w.KEY_SET_VALUE) as k: w.DeleteValue(k,name)
                except OSError: pass
    def test_uninstall_does_not_clean_on_failure(self):
        from unittest.mock import patch
        root=core.data_roots()[0]; root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='PCStewardFixture-',dir=root) as value:
            p=Path(value)/'keep'; p.write_text('keep'); app=core.Entry('fixture','fixture','test')
            function='windows_uninstall' if core.WINDOWS else 'linux_uninstall'
            with patch.object(core,function,side_effect=RuntimeError('cancelled')):
                with self.assertRaises(RuntimeError): core.Backend().uninstall(app,[value])
            self.assertEqual(p.read_text(),'keep')
    def test_uninstall_cleans_only_after_confirmed_absence(self):
        from unittest.mock import patch
        root=core.data_roots()[0]; root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='PCStewardFixture-',dir=root) as value:
            data=Path(value)/'profile'; data.mkdir(); (data/'file').write_text('delete'); keep=Path(value)/'other'; keep.write_text('keep'); app=core.Entry('fixture','fixture','test')
            function='windows_uninstall' if core.WINDOWS else 'linux_uninstall'
            with patch.object(core,function),patch.object(core.Backend,'apps',return_value=[]): core.Backend().uninstall(app,[str(data)])
            self.assertFalse(data.exists()); self.assertEqual(keep.read_text(),'keep')
    @unittest.skipUnless(core.WINDOWS,'Windows native uninstaller fixture')
    def test_registered_uninstaller_and_opt_in_data_cleanup(self):
        import winreg as w, base64
        sub='PCStewardAcceptanceFixture'
        key='Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'+sub
        script="Remove-Item 'HKCU:\\"+key+"' -Recurse -Force -ErrorAction Stop"
        command='powershell.exe -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(script.encode('utf-16le')).decode()
        with tempfile.TemporaryDirectory(prefix='PCStewardFixture-',dir=core.data_roots()[0]) as value:
            data=Path(value)/'profile'; data.mkdir(); (data/'file').write_text('delete'); keep=Path(value)/'other'; keep.write_text('keep')
            try:
                with w.CreateKey(w.HKEY_CURRENT_USER,key) as k:
                    w.SetValueEx(k,'DisplayName',0,w.REG_SZ,'PCSteward Acceptance Test Application')
                    w.SetValueEx(k,'UninstallString',0,w.REG_SZ,command)
                app=next(e for e in core.windows_apps() if e.meta.get('package')==sub)
                core.Backend().uninstall(app,[str(data)])
                self.assertFalse(data.exists()); self.assertEqual(keep.read_text(),'keep'); self.assertFalse(any(e.id==app.id for e in core.windows_apps()))
            finally:
                try: w.DeleteKey(w.HKEY_CURRENT_USER,key)
                except FileNotFoundError: pass
    def test_process_group_matches_real_executable_sources(self):
        groups=core.processes(); pid=os.getpid(); item=next(e for e in groups if any(p['pid']==pid for p in e.meta['processes']))
        self.assertTrue(item.meta['path']); self.assertTrue(next(p for p in item.meta['processes'] if p['pid']==pid)['protected'])
    def test_terminates_only_selected_test_process(self):
        process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
        other=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
        try:
            import psutil
            p=psutil.Process(process.pid); result=core.terminate_processes([{'pid':p.pid,'created':p.create_time(),'exe':sys.executable}])
            process.wait(timeout=5); self.assertIsNone(other.poll()); self.assertIn('1',result)
        finally:
            for p in [process,other]:
                if p.poll() is None: p.terminate(); p.wait()

if __name__=='__main__': unittest.main(verbosity=2)
