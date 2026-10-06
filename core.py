from __future__ import annotations
import configparser, ctypes, dataclasses, datetime, json, logging, logging.handlers, os, platform, re, shlex, shutil, stat, subprocess, sys, time
from pathlib import Path
from naming import SourceIndex, apply_label, alias, executable, file_names, manifest_names, package_alias, searchable, choose_name

WINDOWS = sys.platform == 'win32'
HOME = Path.home()
STATE = Path(os.environ.get('LOCALAPPDATA', str(HOME / '.local/share'))) / 'PCSteward'
STATE.mkdir(parents=True, exist_ok=True)
LOG = STATE / 'operations.log'
logger = logging.getLogger('PCSteward')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.handlers.RotatingFileHandler(LOG, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)

@dataclasses.dataclass
class Entry:
    id: str
    name: str
    source: str
    detail: str = ''
    version: str = ''
    publisher: str = ''
    size: int = 0
    enabled: bool = True
    removable: bool = True
    meta: dict = dataclasses.field(default_factory=dict)

def run(args, timeout=180, check=True):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                       creationflags=0x08000000 if WINDOWS else 0)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f'退出码 {p.returncode}')[-5000:])
    return p.stdout.strip()

def ps(script, timeout=180):
    import base64
    return run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',
                base64.b64encode(("[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"+script).encode('utf-16le')).decode()], timeout)

def ps_json(script):
    text = ps(script + ' | ConvertTo-Json -Depth 8 -Compress')
    value = json.loads(text or '[]')
    return value if isinstance(value,list) else [value]

def fmt_size(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024: return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'

def is_link(p):
    try:
        s = p.lstat()
        return stat.S_ISLNK(s.st_mode) or bool(getattr(s,'st_file_attributes',0) & 0x400)
    except OSError: return False

def size_of(path):
    p = Path(path)
    total = 0
    if is_link(p): return 0
    try:
        if p.is_file(): return p.stat().st_size
        for root, dirs, files in os.walk(p, followlinks=False):
            dirs[:] = [d for d in dirs if not is_link(Path(root)/d)]
            for name in files:
                f = Path(root)/name
                try:
                    if not is_link(f): total += f.stat().st_size
                except OSError: pass
    except OSError: pass
    return total

def data_roots():
    if WINDOWS:
        return [Path(os.environ.get(k,str(HOME/k))) for k in ['APPDATA','LOCALAPPDATA']]
    return [Path(os.environ.get('XDG_CONFIG_HOME',str(HOME/'.config'))),
            Path(os.environ.get('XDG_DATA_HOME',str(HOME/'.local/share'))),
            Path(os.environ.get('XDG_CACHE_HOME',str(HOME/'.cache'))), HOME/'.var/app', HOME/'snap']

def check_data_path(path):
    p = Path(os.path.abspath(path))
    roots = data_roots()
    if not any(p != root and p.is_relative_to(root) for root in roots):
        raise ValueError('只允许清理当前用户的应用数据目录，不能删除数据根目录或个人文档。')
    protected = {'microsoft','windows','packages','programs','pcsteward','autostart','systemd','applications','flatpak','trash','keyrings','dconf','gnupg'}
    dedicated=[('Microsoft','Edge','User Data'),('Microsoft','Windows','INetCache')]
    for root in roots:
        if not p.is_relative_to(root): continue
        parts=p.relative_to(root).parts
        allowed_dedicated=WINDOWS and any(tuple(s.casefold() for s in parts[:len(d)])==tuple(s.casefold() for s in d) for d in dedicated)
        if not allowed_dedicated and any(s.casefold() in protected for s in parts):
            raise ValueError('该路径属于系统、共享或本工具目录，禁止清理。')
    cursor = p
    while cursor != cursor.parent:
        if is_link(cursor): raise ValueError('不清理符号链接、挂载链接或 Windows 目录联接。')
        cursor = cursor.parent
    return p

def norm(value): return re.sub(r'[^\w]','',value.casefold(),flags=re.UNICODE)

def related_data(app):
    names = {norm(app.name),norm(app.meta.get('original_name','')),norm(app.meta.get('package','')),norm(app.meta.get('desktop_id',''))}
    location = app.meta.get('install','')
    if location: names.add(norm(Path(location).name))
    names -= {'','app','apps','application','applications','program','programs','bin','lib','data','desktop','client','software','update','updater','microsoft','windows','python','pcsteward'}
    result = []
    for root in data_roots():
        if not root.is_dir(): continue
        try:
            for p in root.iterdir():
                if norm(p.name) in names and p.is_dir():
                    try: check_data_path(p)
                    except ValueError: continue
                    result.append(str(p))
        except OSError: pass
    if app.source == 'Flatpak':
        p = HOME/'.var/app'/app.meta['package']
        if p.exists(): result.append(str(check_data_path(p)))
    if WINDOWS:
        local=Path(os.environ['LOCALAPPDATA']); roaming=Path(os.environ['APPDATA'])
        recipes={
            'googlechrome':[local/'Google/Chrome/User Data'],
            'microsoftedge':[local/'Microsoft/Edge/User Data'],
            'mozillafirefox':[roaming/'Mozilla/Firefox',local/'Mozilla/Firefox'],
            'firefox':[roaming/'Mozilla/Firefox',local/'Mozilla/Firefox'],
            'microsoftvisualstudiocode':[roaming/'Code',local/'Code'],
            'visualstudiocode':[roaming/'Code',local/'Code'],
            'discord':[roaming/'discord'], 'telegramdesktop':[roaming/'Telegram Desktop'],
            'obsstudio':[roaming/'obs-studio'], 'vlcmediaplayer':[roaming/'vlc'],
            'notepad':[roaming/'Notepad++'], 'spotify':[roaming/'Spotify',local/'Spotify'],
        }
        appname=re.sub(r'\s*\([^)]*\)\s*$','',app.meta.get('original_name',app.name))
        for p in recipes.get(norm(appname),[]):
            try:
                if p.is_dir(): result.append(str(check_data_path(p)))
            except ValueError: pass
    return sorted(set(result))

class Backend:
    def startup(self):
        modules=windows_startup() if WINDOWS else linux_startup()
        return group_startup(modules,self.apps())
    def apps(self): return windows_apps() if WINDOWS else linux_apps()
    def caches(self):
        entries = []
        roots = [Path(os.environ.get('TEMP',str(HOME/'AppData/Local/Temp')))] if WINDOWS else [data_roots()[2]]
        if WINDOWS:
            local = Path(os.environ.get('LOCALAPPDATA',str(HOME/'AppData/Local')))
            roots += [local/'pip/Cache', local/'Microsoft/Windows/INetCache',local/'D3DSCache',local/'NVIDIA/DXCache',local/'NVIDIA/GLCache']
            for base in [local/'Google/Chrome/User Data',local/'Microsoft/Edge/User Data',Path(os.environ.get('APPDATA',''))/'Mozilla/Firefox/Profiles']:
                if base.is_dir():
                    for profile in base.iterdir():
                        if profile.is_dir() and not is_link(profile):
                            roots += [profile/'Cache',profile/'Code Cache',profile/'GPUCache',profile/'cache2']
        for root in roots:
            if not root.is_dir() or is_link(root): continue
            if root == (data_roots()[2] if not WINDOWS else roots[0]):
                for p in root.iterdir():
                    if p.name.casefold() == 'pcsteward' or is_link(p): continue
                    entries.append(Entry(str(p),p.name,'用户临时文件' if WINDOWS else '用户缓存',str(p),size=size_of(p),meta={'path':str(p),'root':str(root)}))
            else:
                entries.append(Entry(str(root),root.parent.name+' / '+root.name,'应用缓存',str(root),size=size_of(root),meta={'path':str(root),'root':str(root)}))
        return sorted(entries,key=lambda x:x.size,reverse=True)
    def toggle(self, item, enabled):
        if WINDOWS: windows_toggle(item,enabled)
        else: linux_toggle(item,enabled)
        logger.info('自启动 %s %s',item.name,'启用' if enabled else '禁用')
    def uninstall(self, app, paths, purge=False):
        paths = [str(check_data_path(p)) for p in paths]
        logger.info('卸载开始 %s [%s] 清理目录=%s',app.name,app.source,paths)
        if WINDOWS: windows_uninstall(app)
        else: linux_uninstall(app,purge)
        # Native uninstallers can spawn another process; absence is the success criterion.
        for i in range(15):
            if not any(a.id == app.id for a in self.apps()): break
            if i == 14: raise RuntimeError('尚未确认应用已卸载。卸载器可能被取消或仍在运行，未清理任何应用数据。请完成卸载后刷新列表。')
            time.sleep(2)
        report = []
        for value in paths:
            p = check_data_path(value)
            if not p.exists(): continue
            failures=[]
            delete_tree(p,failures)
            if failures: report.extend(failures)
        logger.info('卸载完成 %s 清理失败=%s',app.name,report)
        return '应用已卸载。'+(' 部分数据未能删除：\n'+'\n'.join(report[:20]) if report else ' 已完成所选数据清理。' if paths else ' 未执行额外的数据清理。')
    def clean(self, entries, recent=False):
        # Re-discover allowlisted candidates to reject arbitrary action-file paths.
        allowed = {e.id: e for e in self.caches()}
        removed = 0; failures=[]; skipped=0
        for e in entries:
            if e.id not in allowed: raise ValueError('缓存路径已变化，请重新扫描。')
            p = Path(allowed[e.id].meta['path'])
            if is_link(p): continue
            cutoff = 0 if recent else time.time()-86400
            count,skip = clean_tree(p,cutoff,failures)
            removed += count; skipped += skip
        logger.info('缓存清理 释放=%s 跳过=%s 失败=%s',removed,skipped,failures)
        return {'bytes':removed,'skipped':skipped,'errors':failures}

def delete_tree(p, failures):
    if is_link(p): failures.append(str(p)+'：跳过链接'); return
    try:
        if p.is_dir():
            for child in p.iterdir(): delete_tree(child,failures)
            p.rmdir()
        else: p.unlink()
    except OSError as ex: failures.append(str(p)+'：'+str(ex))

def clean_tree(p, cutoff, failures):
    if is_link(p): return 0,1
    removed=0; skipped=0
    try:
        if p.is_dir():
            for child in p.iterdir():
                n,s=clean_tree(child,cutoff,failures); removed+=n; skipped+=s
            try: p.rmdir()
            except OSError: pass
        elif p.exists():
            info=p.stat()
            if info.st_mtime >= cutoff: return 0,1
            p.unlink(); removed+=info.st_size
    except OSError as ex: failures.append(str(p)+'：'+str(ex))
    return removed,skipped

# Windows adapters: Run keys (both registry views), startup folders and scheduled login/boot tasks.
def reg_value(key,name,default=''):
    import winreg
    try: return winreg.QueryValueEx(key,name)[0]
    except OSError: return default

def windows_startup():
    import winreg as w
    result=[]
    for hive,label in [(w.HKEY_CURRENT_USER,'当前用户'),(w.HKEY_LOCAL_MACHINE,'所有用户')]:
        for view in ([w.KEY_WOW64_64KEY] if hive==w.HKEY_CURRENT_USER else [w.KEY_WOW64_64KEY,w.KEY_WOW64_32KEY]):
            for suffix,disabled in [('Run',False),('PCStewardDisabledRun',True)]:
                keypath='Software\\Microsoft\\Windows\\CurrentVersion\\'+suffix
                try:
                    with w.OpenKey(hive,keypath,0,w.KEY_READ|view) as key:
                        for i in range(w.QueryInfoKey(key)[1]):
                            name,cmd,kind=w.EnumValue(key,i)
                            approved='Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\'+('Run32' if view==w.KEY_WOW64_32KEY else 'Run')
                            enabled=not disabled
                            try:
                                with w.OpenKey(hive,approved) as ak:
                                    state=reg_value(ak,name,b'')
                                    if state: enabled=not disabled and state[0] in (2,6)
                            except OSError: pass
                            result.append(Entry(f'reg:{label}:{view}:{name}',name,'注册表 · '+label,str(cmd),enabled=enabled,
                                                meta={'type':'reg','machine':hive==w.HKEY_LOCAL_MACHINE,'view':view,'name':name,'command':cmd,'kind':kind,'disabled':disabled,'approved':approved}))
                except FileNotFoundError: pass
    for machine,base in [(False,Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'),(True,Path(os.environ['PROGRAMDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup')]:
        for folder,enabled in [(base,True),(base.parent/'PCStewardDisabledStartup',False)]:
            if not folder.is_dir(): continue
            for p in folder.iterdir():
                if p.name.casefold()=='desktop.ini': continue
                result.append(Entry('file:'+str(p),p.stem,'启动文件夹 · '+('所有用户' if machine else '当前用户'),str(p),enabled=enabled,meta={'type':'file','path':str(p),'base':str(base),'machine':machine}))
    try:
        tasks=ps_json("Get-ScheduledTask | Where-Object { $_.Triggers.Count -gt 0 } | Select-Object TaskName,TaskPath,@{n='State';e={[string]$_.State}},@{n='Command';e={($_.Actions.Execute -join '; ')}},@{n='Trigger';e={($_.Triggers.CimClass.CimClassName -join ',')}}")
        for task in tasks:
            protected=task['TaskPath'].startswith('\\Microsoft\\')
            result.append(Entry('task:'+task['TaskPath']+task['TaskName'],task['TaskName'],('计划任务（登录/开机）' if re.search('LogonTrigger|BootTrigger',task.get('Trigger','')) else '计划任务（定时/事件）')+(' · 系统' if protected else ''),task.get('Command',''),enabled=task['State']!='Disabled',removable=not protected,meta={'type':'task','name':task['TaskName'],'path':task['TaskPath'],'machine':True}))
    except Exception as ex: logger.warning('计划任务读取失败 %s',ex)
    for e in result:
        path=executable(e.meta.get('command') or e.detail)
        if path and Path(path).is_absolute() and Path(path).is_relative_to(Path(os.environ.get('SystemRoot','C:\\Windows'))): e.removable=False
    return sorted({e.id:e for e in result}.values(),key=lambda x:x.name.casefold())

def windows_toggle(item,enabled):
    import winreg as w
    m=item.meta
    if m['type']=='reg':
        hive=w.HKEY_LOCAL_MACHINE if m['machine'] else w.HKEY_CURRENT_USER
        base='Software\\Microsoft\\Windows\\CurrentVersion\\'
        source=base+('PCStewardDisabledRun' if m['disabled'] else 'Run')
        dest=base+('Run' if enabled else 'PCStewardDisabledRun')
        with w.OpenKey(hive,source,0,w.KEY_READ|m['view']) as key:
            command,kind=w.QueryValueEx(key,m['name'])
        if source!=dest:
            with w.CreateKeyEx(hive,dest,0,w.KEY_WRITE|m['view']) as key: w.SetValueEx(key,m['name'],0,kind,command)
            with w.OpenKey(hive,source,0,w.KEY_SET_VALUE|m['view']) as key: w.DeleteValue(key,m['name'])
        with w.CreateKeyEx(hive,m['approved'],0,w.KEY_WRITE) as key:
            w.SetValueEx(key,m['name'],0,w.REG_BINARY,bytes([2 if enabled else 3])+bytes(11))
    elif m['type']=='file':
        p=Path(m['path'])
        target=(Path(m['base']) if enabled else Path(m['base']).parent/'PCStewardDisabledStartup')/p.name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target!=p:
            if target.exists(): raise RuntimeError('目标文件已存在，未覆盖。')
            p.rename(target)
    elif m['type']=='task':
        if not item.removable: raise ValueError('系统任务只读。')
        ps(f"{'Enable' if enabled else 'Disable'}-ScheduledTask -TaskName {ps_quote(m['name'])} -TaskPath {ps_quote(m['path'])} -ErrorAction Stop | Out-Null")

def ps_quote(v): return "'"+v.replace("'","''")+"'"

CORE_WINDOWS={'pc steward','电脑管家','microsoft windows','microsoft edge webview2 runtime'}
def windows_apps():
    import winreg as w
    result=[]
    for hive,label in [(w.HKEY_CURRENT_USER,'当前用户'),(w.HKEY_LOCAL_MACHINE,'所有用户')]:
        for view in ([w.KEY_WOW64_64KEY] if hive==w.HKEY_CURRENT_USER else [w.KEY_WOW64_64KEY,w.KEY_WOW64_32KEY]):
            keypath='Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall'
            try:
                with w.OpenKey(hive,keypath,0,w.KEY_READ|view) as root:
                    for i in range(w.QueryInfoKey(root)[0]):
                        sub=w.EnumKey(root,i)
                        try:
                            with w.OpenKey(root,sub) as k:
                                name=reg_value(k,'DisplayName')
                                if not name: continue
                                uninstall=reg_value(k,'UninstallString')
                                protected=bool(reg_value(k,'SystemComponent',0) or reg_value(k,'NoRemove',0)) or name.casefold() in CORE_WINDOWS
                                result.append(Entry(f'regapp:{label}:{view}:{sub}',name,'桌面应用 · '+label,reg_value(k,'InstallLocation'),version=str(reg_value(k,'DisplayVersion')),publisher=str(reg_value(k,'Publisher')),size=int(reg_value(k,'EstimatedSize',0))*1024,removable=bool(uninstall) and not protected,
                                    meta={'display_icon':reg_value(k,'DisplayIcon'),'uninstall':uninstall,'msi':bool(reg_value(k,'WindowsInstaller',0)),'package':sub,'install':reg_value(k,'InstallLocation') or inferred_install(uninstall),'protected':protected,'install_inferred':not bool(reg_value(k,'InstallLocation'))}))
                        except OSError: pass
            except OSError: pass
    menu=windows_menu()
    try:
        for a in ps_json("Get-AppxPackage | Select-Object Name,PackageFullName,PackageFamilyName,Version,Publisher,InstallLocation,NonRemovable,IsFramework"):
            item=Entry('appx:'+a['PackageFullName'],a['Name'],'Microsoft Store',a.get('InstallLocation',''),version=str(a['Version']),publisher=a.get('Publisher',''),removable=not a.get('NonRemovable',False) and not a.get('IsFramework',False),meta={'package':a['PackageFullName'],'appx':True,'install':a.get('InstallLocation','')})
            family=a.get('PackageFamilyName','')
            candidates=[(r['Name'],'开始菜单') for r in menu if family and r.get('AppID','').startswith(family+'!')]
            candidates += [(v,'商店清单资源') for v in manifest_names(a.get('InstallLocation',''),a['Name'],a['PackageFullName'])]
            known=package_alias(a['Name'],a.get('InstallLocation',''))
            if known: candidates.append((known,'Windows 组件说明'))
            apply_label(item,candidates,'商店组件'); result.append(item)
    except Exception as ex: logger.warning('Store 应用读取失败 %s',ex)
    index=SourceIndex(result,menu)
    for item in result:
        if item.meta.get('appx'): continue
        root=item.meta.get('install','')
        candidates=[(item.name,'系统应用登记')]+index.menu_names(root,root=True)
        icon=item.meta.get('display_icon','').strip('"').split(',')[0]
        if icon: candidates+=file_names(icon)
        apply_label(item,candidates)
    return sorted(result,key=lambda a:a.name.casefold())

_MENU_CACHE=(0,[])
def windows_menu():
    global _MENU_CACHE
    if time.monotonic()-_MENU_CACHE[0]<180: return _MENU_CACHE[1]
    try:
        rows=ps_json(r"""$rows=@(); Get-StartApps | ForEach-Object { $rows+=@{Name=$_.Name;AppID=$_.AppID;Target=''} }; $shell=New-Object -ComObject WScript.Shell; foreach($base in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('CommonPrograms'))){ Get-ChildItem -LiteralPath $base -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object { try{$shortcut=$shell.CreateShortcut($_.FullName);$rows+=@{Name=$_.BaseName;AppID='';Target=$shortcut.TargetPath}}catch{} } }; @($rows)""")
        _MENU_CACHE=(time.monotonic(),rows)
        return rows
    except Exception as ex: logger.warning('开始菜单读取失败 %s',ex); return []

def windows_uninstall(app):
    if not app.removable: raise ValueError('该应用属于受保护组件或没有登记卸载器。')
    if app.meta.get('appx'):
        ps('Remove-AppxPackage -Package '+ps_quote(app.meta['package'])+' -ErrorAction Stop',timeout=600); return
    command=app.meta['uninstall']
    if app.meta.get('msi'):
        guid=re.search(r'\{[0-9A-Fa-f-]{36}\}',command)
        if not guid: raise RuntimeError('无法识别 MSI 产品编号。')
        command='msiexec.exe /x '+guid.group(0)+' /norestart'
    try: p=subprocess.run(command,timeout=1800)
    except OSError as ex:
        if getattr(ex,'winerror',0)!=740: raise
        match=re.match(r'^"([^"]+)"\s*(.*)$',command) or re.match(r'^(.+?\.exe)\s*(.*)$',command,re.I)
        if not match: raise RuntimeError('无法解析需要管理员权限的卸载命令。')
        code=ps('$p=Start-Process -FilePath '+ps_quote(match.group(1))+' -ArgumentList '+ps_quote(match.group(2) or ' ')+' -Verb RunAs -Wait -PassThru -ErrorAction Stop; $p.ExitCode',timeout=1800)
        p=subprocess.CompletedProcess(command,int(code.strip()))
    if p.returncode not in (0,3010): raise RuntimeError(f'卸载器退出码 {p.returncode}，未清理数据。')

# Linux adapters.
def desktop_config(path):
    c=configparser.ConfigParser(interpolation=None,strict=False); c.optionxform=str
    c.read(path,encoding='utf-8'); return c

def linux_startup():
    user=Path(os.environ.get('XDG_CONFIG_HOME',str(HOME/'.config')))/'autostart'
    merged={}
    for base in [*(Path(p)/'autostart' for p in os.environ.get('XDG_CONFIG_DIRS','/etc/xdg').split(':')),user]:
        if base.is_dir():
            for p in base.glob('*.desktop'): merged[p.name]=p
    result=[]
    for name,p in merged.items():
        try:
            c=desktop_config(p); d=c['Desktop Entry']
            result.append(Entry('xdg:'+name,d.get('Name[zh_CN]',d.get('Name',p.stem)),'桌面自启动',d.get('Exec',''),enabled=d.get('Hidden','false').lower()!='true' and d.get('X-GNOME-Autostart-enabled','true').lower()!='false',meta={'type':'xdg','path':str(p),'target':str(user/name)}))
        except Exception as ex: logger.warning('%s %s',p,ex)
    if shutil.which('systemctl'):
        out=run(['systemctl','--user','list-unit-files','--type=service','--no-legend','--no-pager'],check=False)
        for line in out.splitlines():
            cols=line.split()
            if len(cols)>1 and cols[1] in ('enabled','disabled','masked','enabled-runtime'):
                result.append(Entry('unit:'+cols[0],cols[0],'用户服务',cols[1],enabled=cols[1].startswith('enabled'),meta={'type':'unit','unit':cols[0]}))
    return sorted(result,key=lambda e:e.name.casefold())

def linux_toggle(item,enabled):
    m=item.meta
    if m['type']=='unit':
        if enabled and item.detail=='masked': run(['systemctl','--user','unmask',m['unit']])
        run(['systemctl','--user','enable' if enabled else 'disable',m['unit']]); return
    p=Path(m['path']); target=Path(m['target'])
    c=desktop_config(p)
    c['Desktop Entry']['Hidden']='false' if enabled else 'true'
    c['Desktop Entry']['X-GNOME-Autostart-enabled']='true' if enabled else 'false'
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as f: c.write(f,space_around_delimiters=False)
    temp.replace(target)

PROTECTED_LINUX={'base','base-files','filesystem','linux','linux-lts','linux-image','kernel','kernel-core','systemd','systemd-sysv','glibc','libc6','bash','coreutils','apt','dpkg','pacman','rpm','dnf','sudo','polkit','openssh','openssh-server','networkmanager','python','python3','pc-steward'}
def protected_linux(name):
    n=name.split(':')[0]
    return n in PROTECTED_LINUX or n.startswith(('linux-image-','linux-headers-','kernel-','libc6','systemd-'))

def linux_apps():
    result=[]
    if shutil.which('dpkg-query'):
        out=run(['dpkg-query','-W','-f=${db:Status-Status}\t${binary:Package}\t${Version}\t${Installed-Size}\t${Maintainer}\n'],check=False)
        for line in out.splitlines():
            c=line.split('\t')
            if len(c)>=5 and c[0]=='installed': result.append(Entry('deb:'+c[1],c[1],'DEB',version=c[2],size=int(c[3] or 0)*1024,publisher=c[4],removable=not protected_linux(c[1]),meta={'package':c[1]}))
    elif shutil.which('pacman'):
        for line in run(['pacman','-Q']).splitlines():
            name,ver=line.split(' ',1)
            result.append(Entry('arch:'+name,name,'Pacman',version=ver,removable=not protected_linux(name),meta={'package':name}))
    elif shutil.which('rpm'):
        for line in run(['rpm','-qa','--qf','%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{VENDOR}\n']).splitlines():
            c=line.split('\t')
            if len(c)>=4: result.append(Entry('rpm:'+c[0],c[0],'RPM',version=c[1],size=int(c[2]),publisher=c[3],removable=not protected_linux(c[0]),meta={'package':c[0]}))
    if shutil.which('flatpak'):
        for scope in ['--user','--system']:
            for line in run(['flatpak','list',scope,'--app','--columns=application,name,version'],check=False).splitlines():
                c=line.split('\t')
                if len(c)>=2: result.append(Entry('flatpak:'+scope+':'+c[0],c[1],'Flatpak',version=c[2] if len(c)>2 else '',meta={'package':c[0],'scope':scope}))
    if shutil.which('snap'):
        for line in run(['snap','list'],check=False).splitlines()[1:]:
            c=line.split()
            if len(c)>=6: result.append(Entry('snap:'+c[0],c[0],'Snap',version=c[1],publisher=c[4],removable=c[0] not in ('snapd','core','core18','core20','core22','core24','bare'),meta={'package':c[0]}))
    linux_labels(result)
    return sorted(result,key=lambda a:a.name.casefold())

def linux_uninstall_command(app,purge=False):
    if not app.removable: raise ValueError('受保护的系统组件不能卸载。')
    name=app.meta['package']
    if app.source=='DEB': return ['apt-get','--no-auto-remove','purge' if purge else 'remove',name]
    if app.source=='Pacman': return ['pacman','-R','--noconfirm',name]
    if app.source=='RPM':
        if shutil.which('dnf'): return ['dnf','remove','--noautoremove','-y',name]
        if shutil.which('zypper'): return ['zypper','--non-interactive','remove',name]
        return ['rpm','-e',name]
    if app.source=='Flatpak': return ['flatpak','uninstall',app.meta['scope'],'--noninteractive',name]
    if app.source=='Snap': return ['snap','remove',name]+(['--purge'] if purge else [])
    raise ValueError('不支持的软件来源')

def removal_plan(app,purge=False):
    if WINDOWS: return app.meta.get('uninstall',app.meta.get('package',''))
    args=linux_uninstall_command(app,purge)
    if app.source=='DEB':
        text=run([args[0],'-s',*args[1:]])
        names=re.findall(r'^(?:Remv|Purg) (\S+)',text,re.M)
        if any(protected_linux(n) for n in names): raise RuntimeError('卸载会影响受保护系统组件，已阻止。')
        return text
    if app.source=='RPM' and args[0]=='dnf':
        # rpm -e --test refuses dependency-breaking removals; no cascading removes.
        run(['rpm','-e','--test',app.meta['package']])
        return shlex.join(args)
    return shlex.join(args)

def linux_uninstall(app,purge=False):
    args=linux_uninstall_command(app,purge)
    removal_plan(app,purge)
    if app.source=='DEB': args.insert(1,'-y')
    if not (app.source=='Flatpak' and app.meta['scope']=='--user') and os.geteuid()!=0:
        if not shutil.which('pkexec'): raise RuntimeError('需要管理员权限；请安装 PolicyKit (pkexec) 后重试。')
        args=['pkexec',*args]
    run(args,timeout=1800)

def add_startup(executable):
    p=Path(executable)
    if not p.is_file(): raise ValueError('请选择存在的可执行文件。')
    if WINDOWS:
        target=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'/(p.stem+'.lnk')
        if target.exists(): raise RuntimeError('该自启动项已存在。')
        ps(f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({ps_quote(str(target))});$s.TargetPath={ps_quote(str(p))};$s.WorkingDirectory={ps_quote(str(p.parent))};$s.Save()")
    else:
        target=Path(os.environ.get('XDG_CONFIG_HOME',str(HOME/'.config')))/'autostart'/('pcsteward-'+p.stem+'.desktop')
        if target.exists(): raise RuntimeError('该自启动项已存在。')
        target.parent.mkdir(parents=True,exist_ok=True)
        escaped=str(p).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
        target.write_text('[Desktop Entry]\nType=Application\nName='+p.stem+'\nExec="'+escaped+'"\nHidden=false\n',encoding='utf-8')
    logger.info('添加自启动 %s',p)

# Runtime grouping uses executable locations, never guesses membership from process names.
def entry_disk(entry):
    if not WINDOWS: return '/'
    value=entry.meta.get('install') or entry.meta.get('path') or entry.detail
    found=re.search(r'([A-Za-z]:)[\\/]',str(value))
    if found: return found.group(1).upper()
    if str(value).startswith('\\\\'): return '网络位置'
    return '未提供路径'

def inferred_install(command):
    command=os.path.expandvars(command.strip())
    match=re.match(r'^"([^"]+)"',command) or re.match(r'^(.+?\.(?:exe|msi))(?=\s|$)',command,re.I)
    if match:
        p=Path(match.group(1))
        if p.is_absolute() and p.parent.name.casefold() not in ('system32','syswow64','windows','installer'): return str(p.parent)
    return ''

def processes(apps=None):
    import psutil
    apps=apps or []
    index=SourceIndex(apps,windows_menu() if WINDOWS else [])
    samples=[]
    for p in psutil.process_iter(['pid','name','exe','username','create_time','memory_info','cmdline']):
        try:
            info=p.info; p.cpu_percent(None); samples.append((p,info))
        except (psutil.NoSuchProcess,psutil.AccessDenied): continue
    time.sleep(.4)
    groups={}; cores=psutil.cpu_count() or 1
    for p,info in samples:
        try: cpu=p.cpu_percent(None)/cores
        except (psutil.NoSuchProcess,psutil.AccessDenied): continue
        exe=info.get('exe') or ''
        if exe and not Path(exe).is_absolute(): exe=''
        directory=str(Path(exe).parent) if exe else ''
        owner=index.owner(exe); product=index.product_root(exe); base=(owner.meta.get('install') or directory) if owner else product[0] if product else directory
        if not WINDOWS and directory in ('/usr/bin','/usr/local/bin','/bin','/sbin','/usr/sbin'):
            base=exe
        key=base.casefold() if base else 'unknown:'+str(info['pid'])
        if key not in groups:
            name,name_source=index.label(exe,info.get('name') or '',owner)
            if product and not owner: name=product[1]; name_source='产品来源目录'
            system=WINDOWS and directory.casefold().startswith(os.environ.get('SystemRoot','C:\\Windows').casefold()+os.sep)
            if system and directory.casefold() in {str(Path(os.environ.get('SystemRoot','C:\\Windows'))/'System32').casefold(),str(Path(os.environ.get('SystemRoot','C:\\Windows'))/'SysWOW64').casefold()}: name='Windows 系统服务'
            elif system and not owner: name='Windows 系统 · '+name
            groups[key]=Entry('process:'+key,name,'已匹配应用' if owner else '系统目录' if system else '可执行文件目录' if directory else '来源不可读',base or '无法读取可执行文件路径',meta={'path':base,'processes':[],'cpu':0,'count':0,'original_name':Path(base).name if base else info.get('name',''),'name_source':name_source})
        e=groups[key]; mem=info.get('memory_info'); rss=mem.rss if mem else 0
        friendly,origin=index.label(exe,info.get('name') or '',None)
        if owner and friendly in ('chrome.exe','crashpad_handler.exe','promecefpluginhost.exe'): friendly=owner.name+' · 辅助进程'
        detail={'pid':info['pid'],'name':friendly,'original_name':info.get('name') or '', 'name_source':origin, 'exe':exe,'created':info.get('create_time',0),'cpu':round(cpu,2),'memory':rss,'user':info.get('username') or '', 'command':subprocess.list2cmdline(info.get('cmdline') or []) if WINDOWS else shlex.join(info.get('cmdline') or []),'protected':protected_process(info)}
        e.meta['processes'].append(detail); e.meta['cpu']+=cpu; e.meta['count']+=1; e.size+=rss
    return sorted(groups.values(),key=lambda e:e.size,reverse=True)

def protected_process(info):
    name=(info.get('name') or '').casefold(); exe=info.get('exe') or ''
    if info['pid'] in (0,1,4,os.getpid()) or not exe or not Path(exe).is_absolute(): return True
    if name in {'sshd','sshd.exe','ssh','ssh.exe','system','registry','csrss.exe','wininit.exe','winlogon.exe','lsass.exe','services.exe','smss.exe','svchost.exe','systemd','init','dbus-daemon','polkitd','pcsteward.exe'}: return True
    if WINDOWS:
        root=os.environ.get('SystemRoot','C:\\Windows').casefold().rstrip('\\')
        return exe.casefold().startswith(root+'\\')
    return False

def terminate_processes(items):
    import psutil
    successes=[]; failures=[]
    for item in items:
        try:
            p=psutil.Process(item['pid'])
            info=p.as_dict(attrs=['pid','name','exe','create_time'])
            if abs(info['create_time']-item['created'])>.01: raise RuntimeError('PID 已被其他进程复用，未结束。')
            if protected_process(info): raise RuntimeError('系统、来源不可读或本工具进程受到保护。')
            p.terminate()
            try: p.wait(timeout=5)
            except psutil.TimeoutExpired: raise RuntimeError('进程未退出；请保存工作后通过系统工具处理。')
            successes.append(item['pid']); logger.info('结束进程 pid=%s source=%s',item['pid'],item['exe'])
        except psutil.NoSuchProcess: successes.append(item['pid'])
        except Exception as ex: failures.append(f"PID {item['pid']}：{ex}")
    return f'已结束 {len(successes)} 个进程。'+('\n'+'\n'.join(failures) if failures else '')


def linux_labels(apps):
    roots=[Path(os.environ.get('XDG_DATA_HOME',str(HOME/'.local/share')))/'applications',Path('/usr/share/applications'),Path('/usr/local/share/applications'),HOME/'.local/share/flatpak/exports/share/applications',Path('/var/lib/flatpak/exports/share/applications')]
    entries=[]; owners={}
    for root in roots:
        if not root.is_dir(): continue
        for p in root.glob('*.desktop'):
            try:
                d=desktop_config(p)['Desktop Entry']
                if d.get('Type','Application')!='Application': continue
                label=d.get('Name[zh_CN]') or d.get('Name[zh]') or d.get('Name','')
                exe=executable(d.get('Exec',''),False)
                if exe and not Path(exe).is_absolute(): exe=shutil.which(exe) or exe
                entries.append((p,label,exe))
            except (OSError,KeyError,configparser.Error): pass
    if shutil.which('dpkg-query'):
        out=run(['dpkg-query','-S','/usr/share/applications/*.desktop'],check=False)
        for line in out.splitlines():
            if ': /' in line:
                owner,path=line.rsplit(': ',1); owners[path]=owner.split(':')[0]
    elif shutil.which('pacman') and entries:
        out=run(['pacman','-Qo',*[str(p) for p,_,_ in entries]],check=False)
        for line in out.splitlines():
            match=re.match(r'(.+) is owned by (\S+) ',line)
            if match: owners[match[1]]=match[2]
    for app in apps:
        package=app.meta.get('package','').split(':')[0]
        relevant=[(p,label,exe) for p,label,exe in entries if p.stem==package or owners.get(str(p))==package]
        candidates=[(label,'桌面应用中文名') for p,label,exe in relevant]
        apply_label(app,candidates)
        app.meta['executables']=[exe for p,label,exe in relevant if exe]
        if relevant: app.meta['desktop_id']=relevant[0][0].stem

def startup_command(item):
    if item.meta.get('type')=='file' and WINDOWS:
        try: return ps('$s=(New-Object -ComObject WScript.Shell).CreateShortcut('+ps_quote(item.meta['path'])+');$s.TargetPath')
        except Exception: return ''
    if item.meta.get('type')=='unit':
        # Read ExecStart without changing the service.
        text=run(['systemctl','--user','show',item.meta['unit'],'--property=ExecStart','--value'],check=False)
        found=re.search(r'path=([^ ;]+)',text)
        return found[1] if found else ''
    return item.meta.get('command') or item.detail

def group_startup(modules,apps):
    index=SourceIndex(apps,windows_menu() if WINDOWS else [])
    groups={}
    for item in modules:
        command=startup_command(item); exe=executable(command)
        if not WINDOWS and exe and not Path(exe).is_absolute(): exe=shutil.which(exe) or exe
        owner=index.owner(exe); product=index.product_root(exe)
        name,origin=index.label(exe,item.name,owner)
        # Module roles remain visible in the detail dialog, even when the product is shared.
        item.meta['original_name']=item.name; item.meta['display_name']=name; item.meta['name_source']=origin; item.meta['executable']=exe
        if WINDOWS and item.meta.get('type')=='task' and not item.removable and item.meta.get('path','').startswith('\\Microsoft\\'):
            key='windows:system-tasks'; group_name='Windows 系统计划任务'; location=os.environ.get('SystemRoot','C:\\Windows')
        elif owner:
            key='app:'+owner.id; group_name=owner.name; location=owner.meta.get('install') or str(Path(exe).parent)
        elif product:
            location,group_name=product; key='product:'+location.casefold()
        elif exe and Path(exe).is_absolute():
            parent=str(Path(exe).parent)
            generic=parent.casefold() in {str(Path(os.environ.get('SystemRoot','C:\\Windows'))/'System32').casefold(),'/usr/bin','/bin','/usr/local/bin'}
            key='exe:'+exe.casefold() if generic else 'path:'+parent.casefold()
            group_name=name; location=exe if generic else parent
        else:
            key='unknown:'+item.id; group_name=name; location=item.detail
        if key not in groups:
            groups[key]=Entry('startupgroup:'+key,group_name,'',location,enabled=False,removable=False,meta={'modules':[],'path':location,'original_name':owner.meta.get('original_name',owner.name) if owner else item.name,'name_source':origin})
        group=groups[key]; group.meta['modules'].append(item); group.enabled|=item.enabled; group.removable|=item.removable
    for group in groups.values():
        group.source=' / '.join(sorted({m.source.split(' · ')[0] for m in group.meta['modules']}))
        group.meta['count']=len(group.meta['modules']); group.meta['enabled_count']=sum(m.enabled for m in group.meta['modules'])
    return sorted(groups.values(),key=lambda e:e.name.casefold())


def batch_uninstall(backend,apps,paths,purge=False):
    report=[]
    for i,app in enumerate(apps):
        try: report.append(app.name+'：'+backend.uninstall(app,paths.get(app.id,[]),purge and app.source in ('DEB','Snap')))
        except Exception as ex:
            report.append(app.name+'：'+str(ex)); report.append(f'批量卸载已停止，其余 {len(apps)-i-1} 个应用未操作。'); break
    return '\n\n'.join(report)
