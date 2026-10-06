import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from app import QApplication,Window,CheckTable,BatchUninstallDialog,QTableWidgetItem,Qt
from core import Entry

class SelectionUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.qt=QApplication.instance() or QApplication([])
    def setUp(self):
        with patch('app.QTimer.singleShot'): self.window=Window()
        self.window.runtime_timer.stop(); self.window.loaded=set(self.window.data)
    def tearDown(self): self.window.close()
    def test_apps_select_all_skips_protected_and_survives_filter(self):
        self.window.data['apps']=[Entry('a','中文应用','桌面'),Entry('b','第二个应用','桌面'),Entry('c','系统组件','桌面',removable=False)]
        self.window.switch('apps'); self.window.select_visible(Qt.Checked.value)
        self.assertEqual(self.window.checked['apps'],{'a','b'}); self.assertEqual(len(self.window.checked_entries()),2)
        self.window.search.setText('第二个'); self.assertEqual(self.window.table.rowCount(),1); self.window.select_visible(Qt.Unchecked.value); self.window.search.clear(); self.assertEqual(self.window.checked['apps'],{'a'})
        self.window.clear_checked(); self.assertFalse(self.window.checked['apps'])
    def test_select_all_checkbox_works_through_click_signal(self):
        from PySide6.QtTest import QTest
        self.window.data['apps']=[Entry('a','中文应用','桌面'),Entry('b','第二个应用','桌面')]
        self.window.switch('apps'); self.window.show()
        QTest.mouseClick(self.window.selectall,Qt.LeftButton)
        self.assertEqual(self.window.checked['apps'],{'a','b'})
        QTest.mouseClick(self.window.selectall,Qt.LeftButton)
        self.assertEqual(self.window.checked['apps'],set())
    def test_startup_selection_keeps_readonly_group_out(self):
        editable=Entry('edit','办公软件','注册表',meta={'count':3,'enabled_count':2,'modules':[]})
        readonly=Entry('system','系统','计划任务',removable=False,meta={'count':1,'enabled_count':1,'modules':[]})
        self.window.data['startup']=[editable,readonly]; self.window.render(); self.window.select_visible(Qt.Checked.value)
        self.assertEqual(self.window.checked['startup'],{'edit'})
    def test_runtime_select_all_requires_unprotected_process(self):
        self.window.data['runtime']=[Entry('app','应用','来源',meta={'count':1,'cpu':0,'processes':[{'protected':False,'name':'应用进程'}]}),Entry('sys','系统','来源',meta={'count':1,'cpu':0,'processes':[{'protected':True,'name':'系统进程'}]})]
        self.window.switch('runtime'); self.window.select_visible(Qt.Checked.value); self.assertEqual(self.window.checked['runtime'],{'app'})
    def test_dialog_select_all_checks_only_checkbox_rows(self):
        table=CheckTable(['项目']); table.setRowCount(3)
        for i in range(3):
            item=QTableWidgetItem(str(i))
            if i!=1: item.setCheckState(Qt.Unchecked)
            table.setItem(i,0,item)
        table.select_all(); self.assertEqual(table.checked_rows(),[0,2]); table.select_all(False); self.assertEqual(table.checked_rows(),[])
    def test_data_cleanup_select_all_is_optional_and_app_specific(self):
        with tempfile.TemporaryDirectory() as value:
            a=Entry('a','应用甲','test'); b=Entry('b','应用乙','test')
            x=Path(value)/'a'; y=Path(value)/'b'; x.mkdir(); y.mkdir()
            dialog=BatchUninstallDialog([(a,'plan',[str(x)]),(b,'plan',[str(y)])],self.window)
            self.assertFalse(dialog.clear.isChecked()); self.assertEqual(dialog.selected_paths(a),[])
            dialog.clear.setChecked(True); dialog.table.select_all(); self.assertEqual(dialog.selected_paths(a),[str(x)]); self.assertEqual(dialog.selected_paths(b),[str(y)]); dialog.reject()

if __name__=='__main__': unittest.main(verbosity=2)
