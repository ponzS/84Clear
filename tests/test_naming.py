import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, naming

class Naming(unittest.TestCase):
    def test_chinese_display_wins_and_raw_identity_stays(self):
        app=core.Entry('stable-id','Internal.Module','Store',meta={'package':'stable-package'})
        naming.apply_label(app,[('Product','产品信息'),('中文产品','开始菜单')])
        self.assertEqual(app.name,'中文产品'); self.assertEqual(app.id,'stable-id'); self.assertEqual(app.meta['package'],'stable-package'); self.assertEqual(app.meta['original_name'],'Internal.Module')
        self.assertIn('internal.module',naming.searchable(app))
    def test_uuid_filepicker_uses_actual_systemapps_location(self):
        value=naming.package_alias('1527c705-839a-4832-9118-54d4Bd6a0c89',r'C:\Windows\SystemApps\Microsoft.Windows.FilePicker_cw5n1h2txyewy')
        self.assertEqual(value,'Windows 文件选择器')
    def test_unresolved_uuid_and_resource_are_not_main_labels(self):
        for raw in ['1527c705-839a-4832-9118-54d4Bd6a0c89','ms-resource:DisplayName']:
            label,_=naming.choose_name([],raw,'商店组件'); self.assertIn('未命名商店组件',label)
    def test_unknown_brand_remains_readable(self):
        self.assertEqual(naming.choose_name([('Example Brand','系统登记')],'')[0],'Example Brand')
    def test_shared_framework_gets_human_description(self):
        self.assertEqual(naming.package_alias('Microsoft.NET.Native.Runtime.2.2'),'Microsoft .NET Native 运行库 2.2')
    def test_manifest_reads_literal_display_name(self):
        with tempfile.TemporaryDirectory() as value:
            Path(value,'AppxManifest.xml').write_text('<Package xmlns="test"><Properties><DisplayName>中文商店应用</DisplayName></Properties></Package>',encoding='utf-8')
            self.assertEqual(naming.manifest_names(value,'pkg','pkg_full'),['中文商店应用'])
    def test_resource_constructs_fully_qualified_reference(self):
        with patch.object(naming,'indirect_name',side_effect=lambda v:'商店名称' if v=='@{PackageFull?ms-resource://Package.Name/resources/DisplayName}' else ''):
            self.assertEqual(naming.resource_name('ms-resource:DisplayName','Package.Name','PackageFull',''), '商店名称')
    def test_windows_owner_uses_deepest_root_and_path_boundaries(self):
        wide=core.Entry('wide','公司','test',meta={'install':r'D:\Apps'})
        app=core.Entry('app','办公软件','test',meta={'install':r'D:\Apps\WPS'})
        index=naming.SourceIndex([wide,app],windows=True)
        self.assertIs(index.owner(r'd:\apps\wps\bin\update.exe'),app)
        self.assertIs(index.owner(r'D:\Apps\WPSOther\update.exe'),wide)
        self.assertIsNone(index.owner(r'D:\AppsOther\update.exe'))
    def test_menu_does_not_use_uninstaller_name(self):
        index=naming.SourceIndex([], [{'Name':'卸载示例','Target':r'D:\Example\uninstall.exe'},{'Name':'示例软件','Target':r'D:\Example\main.exe'}],windows=True)
        self.assertEqual(index.menu_names(r'D:\Example',root=True),[('示例软件','开始菜单')])
    def test_wps_nested_modules_share_product_root(self):
        index=naming.SourceIndex([],windows=True)
        a=index.product_root(r'D:\Kingsoft\WPSOffice\12\office6\wps.exe')
        b=index.product_root(r'D:\Kingsoft\WPSOffice\12\office6\sub\update.exe')
        self.assertEqual(a,b); self.assertEqual(a[1],'WPS 办公软件')
    def test_startup_group_retains_modules_and_individual_states(self):
        prefix='C:\\Apps\\Office' if core.WINDOWS else '/opt/office'
        app=core.Entry('office','办公软件','test',meta={'install':prefix})
        modules=[core.Entry(str(i),'Internal'+str(i),'注册表',prefix+os.sep+'module'+str(i)+('.exe' if core.WINDOWS else ''),enabled=i%2==0,removable=i!=2,meta={'command':prefix+os.sep+'module'+str(i)+('.exe' if core.WINDOWS else '')}) for i in range(3)]
        with patch.object(core,'windows_menu',return_value=[]): groups=core.group_startup(modules,[app])
        self.assertEqual(len(groups),1); self.assertEqual(groups[0].name,'办公软件'); self.assertEqual(groups[0].meta['count'],3); self.assertEqual(groups[0].meta['enabled_count'],2); self.assertEqual([m.id for m in groups[0].meta['modules']],['0','1','2'])
    @unittest.skipUnless(core.WINDOWS,'Native version resources')
    def test_native_file_description_and_system_process_label(self):
        path=str(Path(os.environ['SystemRoot'])/'System32/notepad.exe')
        self.assertTrue(naming.file_names(path)); self.assertEqual(naming.SourceIndex([]).label(str(Path(os.environ['SystemRoot'])/'explorer.exe'),'explorer.exe')[0],'Windows 文件资源管理器')

if __name__=='__main__': unittest.main(verbosity=2)
