import os, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import core
from app import privileged_toggles

class Batch(unittest.TestCase):
    def test_uninstall_cancel_stops_and_keeps_remaining_apps_untouched(self):
        calls=[]
        class Fixture:
            def uninstall(self,app,paths,purge):
                calls.append((app.id,paths,purge))
                if app.id=='b': raise RuntimeError('用户取消')
                return '卸载成功'
        apps=[core.Entry(i,'应用'+i,'DEB') for i in ['a','b','c']]
        result=core.batch_uninstall(Fixture(),apps,{'a':['a-data'],'b':['b-data'],'c':['c-data']},True)
        self.assertEqual(calls,[('a',['a-data'],True),('b',['b-data'],True)]); self.assertIn('其余 1 个应用未操作',result)
    def test_startup_batch_excludes_readonly_and_unchanged_modules(self):
        items=[core.Entry('selected','selected','test',enabled=True),core.Entry('already','already','test',enabled=False),core.Entry('readonly','readonly','test',enabled=True,removable=False)]
        with patch.object(core.Backend,'toggle') as toggle:
            text=privileged_toggles(items,False)
        self.assertEqual([call.args[0].id for call in toggle.call_args_list],['selected']); self.assertIn('1 个启动模块',text)
    @unittest.skipUnless(core.WINDOWS,'Windows user Run batch fixture')
    def test_native_batch_startup_disable_restore(self):
        import winreg as w
        names=['PCSteward-Batch-Fixture-1','PCSteward-Batch-Fixture-2']; base='Software\\Microsoft\\Windows\\CurrentVersion\\'
        try:
            with w.CreateKey(w.HKEY_CURRENT_USER,base+'Run') as key:
                for name in names: w.SetValueEx(key,name,0,w.REG_SZ,'notepad.exe')
            items=[e for e in core.windows_startup() if e.name in names]
            privileged_toggles(items,False); disabled=[e for e in core.windows_startup() if e.name in names]; self.assertEqual(len(disabled),2); self.assertFalse(any(e.enabled for e in disabled))
            privileged_toggles(disabled,True); enabled=[e for e in core.windows_startup() if e.name in names]; self.assertEqual(len(enabled),2); self.assertTrue(all(e.enabled for e in enabled))
        finally:
            for suffix in ['Run','PCStewardDisabledRun','Explorer\\StartupApproved\\Run']:
                try:
                    with w.OpenKey(w.HKEY_CURRENT_USER,base+suffix,0,w.KEY_SET_VALUE) as key:
                        for name in names:
                            try: w.DeleteValue(key,name)
                            except FileNotFoundError: pass
                except FileNotFoundError: pass

if __name__=='__main__': unittest.main(verbosity=2)
