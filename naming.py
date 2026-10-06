"""Human-readable labels. Identity, paths and operation targets remain unchanged."""
from __future__ import annotations
import ctypes, functools, os, re, shlex, sys, xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath

CHINESE = re.compile(r'[\u3400-\u9fff]')
UUID = re.compile(r'^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$',re.I)
GENERIC = {'application','app','client','cef','runtime','scripts','bin','office6','resources','helper','microsoft windows operating system','microsoft® windows® operating system','chromium','electron','chromium embedded framework','windows operating system'}
APP_NAMES = {
 'google chrome':'谷歌 Chrome 浏览器','brave':'Brave 浏览器','microsoft edge':'Microsoft Edge 浏览器',
 'microsoft edge webview2 runtime':'Microsoft Edge 网页运行库','nvidia container':'NVIDIA 显卡后台服务',
 'nvidia overlay':'NVIDIA 游戏覆盖层','nvidia shadowplay':'NVIDIA 游戏录制组件',
 'wps office':'WPS 办公软件','wps':'WPS 办公软件','wps office personal':'WPS 办公软件',
 'wechat':'微信','wechatappex':'微信小程序组件','weixin':'微信','qq':'腾讯 QQ',
 'visual studio code':'Visual Studio Code 编辑器','microsoft visual studio code':'Visual Studio Code 编辑器',
 'microsoft store':'微软应用商店','game bar':'Xbox 游戏栏','cortana':'Cortana 语音助手',
 'anticheatexpert':'游戏反作弊组件（AntiCheatExpert）','python':'Python 解释器',
}
PACKAGE_NAMES = {
 'microsoft.windows.filepicker':'Windows 文件选择器','microsoft.windows.fileexplorer':'Windows 文件资源管理器组件',
 'microsoft.windows.appresolverux':'Windows 应用选择器','microsoft.windows.addsuggestedfolderstolibrarydialog':'Windows 文件库文件夹选择器',
 'microsoft.aad.brokerplugin':'Microsoft 账号登录组件','microsoft.accountscontrol':'Windows 账号管理组件',
 'microsoft.asynctextservice':'Windows 文本输入服务','microsoft.bioenrollment':'Windows 生物识别设置',
 'microsoft.creddialoghost':'Windows 凭据对话框','microsoft.desktopappinstaller':'Windows 应用安装程序',
 'microsoft.ecapp':'Windows 眼控组件','microsoft.heifimageextension':'HEIF 图像扩展',
 'microsoft.languageexperiencepackzh-cn':'Windows 简体中文语言包','microsoft.lockapp':'Windows 锁屏',
 'microsoft.microsoftedge.stable':'Microsoft Edge 浏览器','microsoft.microsoftedgedevtoolsclient':'Microsoft Edge 开发者工具',
 'microsoft.people':'Windows 人脉','microsoft.storepurchaseapp':'微软商店购买组件',
 'microsoft.vp9videoextensions':'VP9 视频扩展','microsoft.wallet':'Microsoft 钱包',
 'microsoft.webmediaextensions':'网络媒体扩展','microsoft.webpimageextension':'WebP 图像扩展',
 'microsoft.win32webviewhost':'Windows 桌面网页视图组件','microsoft.windows.apprep.chxapp':'Windows 应用安全检查',
 'microsoft.windows.assignedaccesslockapp':'Windows 专用访问锁屏','microsoft.windows.callingshellapp':'Windows 通话组件',
 'microsoft.windows.capturepicker':'Windows 屏幕捕获选择器','microsoft.windows.cloudexperiencehost':'Windows 初始设置',
 'microsoft.windows.contentdeliverymanager':'Windows 内容推荐组件','microsoft.windows.devhome':'Windows 开发者主页',
 'microsoft.windows.narratorquickstart':'Windows 讲述人入门','microsoft.windows.oobenetworkcaptiveportal':'Windows 网络登录组件',
 'microsoft.windows.oobenetworkconnectionflow':'Windows 网络连接设置','microsoft.windows.parentalcontrols':'Windows 家长控制',
 'microsoft.windows.peopleexperiencehost':'Windows 人脉组件','microsoft.windows.pinningconfirmationdialog':'Windows 固定应用确认',
 'microsoft.windows.search':'Windows 搜索','microsoft.windows.secureassessmentbrowser':'Windows 安全考试浏览器',
 'microsoft.windows.shellexperiencehost':'Windows 桌面界面组件','microsoft.windows.startmenuexperiencehost':'Windows 开始菜单',
 'microsoft.windows.xgpuejectdialog':'Windows 外接显卡移除提示','microsoftwindows.client.cbs':'Windows 系统界面组件',
 'microsoft.windowsprint':'Windows 打印组件','microsoft.windows.ncsiuwpapp':'Windows 网络状态组件',
 'winappruntime.main.2':'Windows 应用运行库主组件','winappruntime.singleton':'Windows 应用运行库共享组件',
 'microsoft.windowsstore':'微软应用商店','microsoft.windowscalculator':'计算器','microsoft.windowscamera':'相机',
 'microsoft.windows.photos':'照片','microsoft.yourphone':'手机连接','microsoft.screensketch':'截图和草图',
 'windows.immersivecontrolpanel':'Windows 设置','microsoft.microsoftpcmanager':'微软电脑管家',
 'microsoft.mspaint':'画图 3D','microsoft.microsoftstickyNotes'.lower():'便笺',
 'microsoft.windowsalarms':'时钟','microsoft.windowssoundrecorder':'录音机','microsoft.zunemusic':'媒体播放器',
 'microsoft.zunevideo':'电影和电视','microsoft.windowsmaps':'地图','microsoft.bingweather':'天气',
 'microsoft.windowsfeedbackhub':'反馈中心','microsoft.gethelp':'获取帮助','microsoft.getstarted':'Windows 使用技巧',
 'microsoft.windowscommunicationsapps':'邮件和日历','microsoft.xboxgamingoverlay':'Xbox 游戏栏',
}
PROCESS_NAMES = {
 'system':'Windows 系统内核','system idle process':'系统空闲进程','registry':'Windows 注册表',
 'memcompression':'Windows 内存压缩','explorer.exe':'Windows 文件资源管理器','svchost.exe':'Windows 服务主机',
 'csrss.exe':'Windows 客户端运行服务','wininit.exe':'Windows 启动初始化','winlogon.exe':'Windows 登录管理',
 'lsass.exe':'Windows 本地安全服务','services.exe':'Windows 服务管理','smss.exe':'Windows 会话管理',
 'fontdrvhost.exe':'Windows 字体驱动服务','dwm.exe':'桌面窗口管理器','conhost.exe':'控制台窗口主机',
 'sihost.exe':'Windows 桌面基础服务','taskhostw.exe':'Windows 任务主机','runtimebroker.exe':'Windows 应用权限管理',
 'searchapp.exe':'Windows 搜索','searchindexer.exe':'Windows 搜索索引','startmenuexperiencehost.exe':'Windows 开始菜单',
 'shellexperiencehost.exe':'Windows 桌面界面','lockapp.exe':'Windows 锁屏','textinputhost.exe':'Windows 文本输入',
 'ctfmon.exe':'Windows 输入法服务','chsime.exe':'微软拼音输入法','systemsettings.exe':'Windows 设置',
 'useroobebroker.exe':'Windows 初始设置服务','powershell.exe':'Windows PowerShell 终端','cmd.exe':'Windows 命令提示符',
 'nvdisplay.container.exe':'NVIDIA 显卡显示服务','nvcontainer.exe':'NVIDIA 显卡后台服务',
 'nvidia overlay.exe':'NVIDIA 游戏覆盖层','nvsphelper64.exe':'NVIDIA 游戏录制辅助服务',
 'atiesrxx.exe':'AMD 显卡事件服务','atieclxx.exe':'AMD 显卡事件客户端','amdfendrsr.exe':'AMD 显卡崩溃防护服务',
 'wechatappex.exe':'微信小程序组件','sogouimebroker.exe':'搜狗输入法服务','msedgewebview2.exe':'Microsoft Edge 网页运行库',
 'brave.exe':'Brave 浏览器','chrome.exe':'谷歌 Chrome 浏览器','msedge.exe':'Microsoft Edge 浏览器',
 'wps.exe':'WPS 文字','et.exe':'WPS 表格','wpp.exe':'WPS 演示','wpscloudsvr.exe':'WPS 云服务',
 'wpscenter.exe':'WPS 应用中心','wpsupdate.exe':'WPS 更新服务','wtoolex.exe':'WPS 工具组件',
 'python.exe':'Python 解释器','pythonw.exe':'Python 图形程序解释器','pcsteward.exe':'电脑管家',
}

def clean_name(value):
    return re.sub(r'\s+',' ',str(value or '').replace('\x00','')).strip()

def readable(value):
    v=clean_name(value)
    return bool(v and not UUID.fullmatch(v) and not v.lower().startswith(('ms-resource:','@{','@%')) and '\ufffd' not in v and v.casefold() not in GENERIC)

def alias(value):
    value=clean_name(value)
    if CHINESE.search(value): return value
    direct=APP_NAMES.get(value.casefold())
    if direct: return direct
    for prefix in ['NVIDIA ShadowPlay','WPS Office']:
        if re.fullmatch(re.escape(prefix)+r'\s+(?:版本\s*)?\d[\w.+ -]*',value,re.I):
            return APP_NAMES[prefix.casefold()]+' '+value[len(prefix):].strip()
    return value

def choose_name(candidates, fallback='', kind='应用'):
    usable=[(alias(name),source) for name,source in candidates if readable(name)]
    chinese=next(((n,s) for n,s in usable if CHINESE.search(n)),None)
    if chinese: return chinese
    if usable: return usable[0]
    if readable(fallback): return alias(fallback),'原始名称'
    suffix=clean_name(fallback)[:8]
    return f'未命名{kind}'+(f'（{suffix}）' if suffix and UUID.fullmatch(clean_name(fallback)) else ''),'未提供显示名'

def package_alias(identity, install=''):
    # UUID-based system packages can be identified by their actual SystemApps folder.
    candidates=[identity.split('_')[0],PureWindowsPath(install).name.split('_')[0]]
    for candidate in candidates:
        low=candidate.casefold()
        if low in PACKAGE_NAMES: return PACKAGE_NAMES[low]
        for pattern,label in [(r'microsoft\.net\.native\.framework\.(.+)','Microsoft .NET Native 框架'),(r'microsoft\.net\.native\.runtime\.(.+)','Microsoft .NET Native 运行库'),(r'microsoft\.ui\.xaml\.(.+)','Windows 界面运行库（XAML）'),(r'microsoft\.vclibs\.(.+)','Microsoft Visual C++ 运行库'),(r'microsoft\.windowsappruntime\.(.+)','Windows 应用运行库')]:
            match=re.fullmatch(pattern,low)
            if match: return label+' '+match.group(1).replace('uwpdesktop','桌面版')
    return ''

@functools.lru_cache(maxsize=1024)
def indirect_name(value):
    if sys.platform!='win32' or not value.startswith('@'): return ''
    from ctypes import wintypes as w
    dll=ctypes.WinDLL('shlwapi'); fn=dll.SHLoadIndirectString
    fn.argtypes=[w.LPCWSTR,w.LPWSTR,w.UINT,ctypes.c_void_p]; fn.restype=ctypes.c_long
    buffer=ctypes.create_unicode_buffer(2048)
    return clean_name(buffer.value) if fn(value,buffer,len(buffer),None)==0 else ''

def resource_name(value,identity,full_name,install):
    if not value: return ''
    if value.startswith('@'): return indirect_name(value)
    if not value.lower().startswith('ms-resource:'): return clean_name(value)
    tail=value[len('ms-resource:'):]
    if tail.startswith('//'): uris=[value]
    else:
        tail=tail.lstrip('/')
        uris=[f'ms-resource://{identity}/{tail}']
        if not tail.lower().startswith('resources/'): uris.insert(0,f'ms-resource://{identity}/resources/{tail}')
    for uri in uris:
        for source in [full_name,str(Path(install)/'resources.pri')]:
            result=indirect_name('@{'+source+'?'+uri+'}')
            if readable(result): return result
    return ''

@functools.lru_cache(maxsize=1024)
def manifest_names(install,identity,full_name):
    if not install: return []
    try:
        root=ET.parse(Path(install)/'AppxManifest.xml').getroot()
        values=[]
        for node in root.iter():
            if node.tag.rsplit('}',1)[-1]=='DisplayName' and node.text: values.append(node.text)
            if 'DisplayName' in node.attrib: values.append(node.attrib['DisplayName'])
        return [name for v in values if (name:=resource_name(v,identity,full_name,install))]
    except (OSError,ET.ParseError): return []

@functools.lru_cache(maxsize=2048)
def _file_names(path,stamp):
    if sys.platform!='win32': return []
    from ctypes import wintypes as w
    dll=ctypes.WinDLL('version')
    sizefn=dll.GetFileVersionInfoSizeW; sizefn.argtypes=[w.LPCWSTR,ctypes.POINTER(w.DWORD)]; sizefn.restype=w.DWORD
    get=dll.GetFileVersionInfoW; get.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p]; get.restype=w.BOOL
    query=dll.VerQueryValueW; query.argtypes=[ctypes.c_void_p,w.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(w.UINT)]; query.restype=w.BOOL
    ignored=w.DWORD(); size=sizefn(path,ctypes.byref(ignored))
    if not size or size>16_000_000: return []
    data=ctypes.create_string_buffer(size)
    if not get(path,0,size,data): return []
    ptr=ctypes.c_void_p(); length=w.UINT(); translations=[]
    if query(data,'\\VarFileInfo\\Translation',ctypes.byref(ptr),ctypes.byref(length)):
        words=ctypes.cast(ptr,ctypes.POINTER(w.WORD))
        translations=[(words[i],words[i+1]) for i in range(0,length.value//2-1,2)]
    translations=sorted(set(translations+[(0x0804,1200),(0x0409,1200)]),key=lambda t: (t[0]&0x3ff)!=4)
    results=[]
    for lang,code in translations:
        for field in ['ProductName','FileDescription']:
            key=f'\\StringFileInfo\\{lang:04x}{code:04x}\\{field}'
            if query(data,key,ctypes.byref(ptr),ctypes.byref(length)) and length.value:
                value=clean_name(ctypes.wstring_at(ptr.value,length.value).rstrip('\x00'))
                if readable(value): results.append((value,'程序产品信息' if field=='ProductName' else '程序文件说明'))
    return results

def file_names(path):
    try:
        p=Path(path)
        if not p.is_file(): return []
        return _file_names(str(p),p.stat().st_mtime_ns)
    except (OSError,ValueError): return []

def executable(command,windows=None):
    windows=sys.platform=='win32' if windows is None else windows
    command=os.path.expandvars(clean_name(command))
    if windows:
        match=re.match(r'^"([^"]+)"',command) or re.match(r'^(.+?\.(?:exe|com|bat|cmd))(?=\s|,|$)',command,re.I)
        return match.group(1) if match else ''
    try:
        parts=shlex.split(command)
        if parts and parts[0]=='env': parts=[p for p in parts[1:] if '=' not in p and not p.startswith('-')]
        return parts[0] if parts else ''
    except ValueError: return ''

class SourceIndex:
    def __init__(self,apps,menu=None,windows=None):
        self.windows=sys.platform=='win32' if windows is None else windows
        self.apps=[]; self.exact={}; self.menu=menu or []
        self.pathclass=PureWindowsPath if self.windows else Path
        for app in apps:
            for exe in app.meta.get('executables',[]): self.exact[self.pathclass(exe)]=app
            root=app.meta.get('install') or ''
            if root and self.pathclass(root).is_absolute(): self.apps.append((self.pathclass(root),app))
        self.apps.sort(key=lambda item:len(str(item[0])),reverse=True)
    def owner(self,exe):
        if not exe: return None
        p=self.pathclass(exe)
        if p in self.exact: return self.exact[p]
        for root,app in self.apps:
            if p.is_relative_to(root): return app
        return None
    def menu_names(self,exe,root=False):
        if not exe: return []
        path=self.pathclass(exe); candidates=[]
        for row in self.menu:
            target=row.get('Target','')
            if not target: continue
            p=self.pathclass(target)
            matched=p==path or root and p.is_relative_to(path)
            if matched and not re.search(r'卸载|安装|帮助|uninstall|setup|readme|help',row.get('Name',''),re.I): candidates.append((row['Name'],'开始菜单'))
        return candidates
    def product_root(self,exe):
        known={'wpsoffice':'WPS 办公软件','wps office':'WPS 办公软件','nvidia app':'NVIDIA 显卡管理程序','qqpcmgr':'腾讯电脑管家'}
        p=self.pathclass(exe) if exe else None
        if not p or not p.is_absolute(): return None
        for parent in p.parents:
            if parent.name.casefold() in known: return str(parent),known[parent.name.casefold()]
        return None
    def label(self,exe,raw='',owner=None):
        candidates=[]
        if owner: candidates.append((owner.name,owner.meta.get('name_source','所属应用')))
        candidates+=self.menu_names(exe)
        raw_file=self.pathclass(exe).name if exe else raw
        known=PROCESS_NAMES.get(raw_file.casefold())
        if known: candidates.append((known,'已知进程说明'))
        candidates+=file_names(exe)
        return choose_name(candidates,raw or raw_file,'进程')

def apply_label(entry,candidates,kind='应用'):
    raw=entry.meta.setdefault('original_name',entry.name)
    entry.name,entry.meta['name_source']=choose_name(candidates,raw,kind)
    return entry

def searchable(entry):
    pieces=[entry.name,entry.source,entry.detail,entry.publisher,entry.meta.get('install',''),entry.meta.get('original_name',''),entry.meta.get('package','')]
    for item in entry.meta.get('modules',[]): pieces.extend([item.name,item.detail,item.meta.get('original_name','')])
    for item in entry.meta.get('processes',[]): pieces.extend([item['name'],item.get('original_name',''),item.get('exe','')])
    return ' '.join(pieces).casefold()
