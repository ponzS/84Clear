from __future__ import annotations
import ctypes, dataclasses, json, os, platform, subprocess, sys, time, uuid
from pathlib import Path
from core import *

def privileged_toggles(items, enabled):
    completed=0; errors=[]; elevated=[]
    for item in items:
        if not item.removable or item.enabled==enabled: continue
        if WINDOWS and item.meta.get('machine') and not ctypes.windll.shell32.IsUserAnAdmin(): elevated.append(item); continue
        try: Backend().toggle(item,enabled); completed+=1
        except PermissionError:
            if WINDOWS: elevated.append(item)
            else: errors.append(item.name+'：权限不足')
        except Exception as ex: errors.append(item.name+'：'+str(ex))
    if elevated:
        jobdir=STATE/'jobs'; jobdir.mkdir(exist_ok=True); job=jobdir/(uuid.uuid4().hex+'.json')
        job.write_text(json.dumps({'ids':[e.id for e in elevated],'enabled':enabled}),encoding='utf-8')
        args=['--action-file',str(job)]
        if not getattr(sys,'frozen',False): args.insert(0,str(Path(__file__).resolve()))
        result=ctypes.windll.shell32.ShellExecuteW(None,'runas',sys.executable,subprocess.list2cmdline(args),None,0)
        if result<=32: errors.append('未授予管理员权限，'+str(len(elevated))+' 项未修改。'); job.unlink(missing_ok=True)
        else:
            out=job.with_suffix('.result')
            for _ in range(180):
                if out.exists():
                    data=json.loads(out.read_text(encoding='utf-8')); completed+=data.get('completed',0); errors+=data.get('errors',[])
                    job.unlink(missing_ok=True); out.unlink(missing_ok=True); break
                time.sleep(1)
            else: errors.append('等待管理员操作超时，请刷新核对状态。')
    return f'已更新 {completed} 个启动模块，下次登录时生效。'+('\n\n'+'\n'.join(errors) if errors else '')

def privileged_toggle(item, enabled): return privileged_toggles([item],enabled)

def action_main(path):
    job=Path(path).resolve()
    if job.parent != (STATE/'jobs').resolve() or job.suffix!='.json': return 2
    result={'completed':0,'errors':[]}
    try:
        data=json.loads(job.read_text(encoding='utf-8')); current={e.id:e for e in windows_startup()}
        for item_id in data.get('ids',[data.get('id')]):
            try:
                item=current[item_id]
                if not item.removable: raise ValueError('受保护的系统项目')
                Backend().toggle(item,bool(data['enabled'])); result['completed']+=1
            except Exception as ex: result['errors'].append(str(item_id)+'：'+str(ex))
    except Exception as ex: result['errors'].append(str(ex))
    temp=job.with_suffix('.tmp'); temp.write_text(json.dumps(result),encoding='utf-8'); temp.replace(job.with_suffix('.result'))
    return 0

if '--action-file' in sys.argv:
    sys.exit(action_main(sys.argv[sys.argv.index('--action-file')+1]))

from PySide6.QtCore import Qt, QObject, Signal, QThread, QTimer, QUrl, Slot
from PySide6.QtGui import QFont, QDesktopServices, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QStackedWidget,
    QFrame,QMessageBox,QDialog,QDialogButtonBox,QCheckBox,QFileDialog,QTextEdit,QProgressBar)

class Worker(QObject):
    done=Signal(object); failed=Signal(str)
    def __init__(self, fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as ex:
            logger.exception('操作失败'); self.failed.emit(str(ex))

class CheckTable(QTableWidget):
    """Check state is independent of highlighted rows and excludes protected items."""
    changed=Signal()
    def __init__(self,headers,parent=None):
        super().__init__(0,len(headers),parent); self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers); self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.itemChanged.connect(lambda _:self.changed.emit())
    def select_all(self,checked=True):
        self.blockSignals(True)
        for row in self.checkable_rows(): self.item(row,0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.blockSignals(False); self.changed.emit()
    def checkable_rows(self):
        return [i for i in range(self.rowCount()) if self.item(i,0) and self.item(i,0).data(Qt.CheckStateRole) is not None and self.item(i,0).flags() & Qt.ItemIsUserCheckable]
    def checked_rows(self): return [i for i in self.checkable_rows() if self.item(i,0).checkState()==Qt.Checked]

def add_selection_controls(layout,table):
    line=QHBoxLayout(); all_box=QCheckBox('全选可操作项'); all_box.setTristate(True); clear=QPushButton('取消全选'); line.addWidget(all_box); line.addWidget(clear); line.addStretch(); layout.addLayout(line)
    def toggle(state): table.select_all(state!=Qt.Unchecked.value)
    def sync():
        rows=table.checkable_rows(); count=len(table.checked_rows()); all_box.blockSignals(True)
        all_box.setCheckState(Qt.Checked if rows and count==len(rows) else Qt.PartiallyChecked if count else Qt.Unchecked); all_box.blockSignals(False)
    all_box.stateChanged.connect(toggle); clear.clicked.connect(lambda:table.select_all(False)); table.changed.connect(sync); sync()
    return all_box,clear

class BatchUninstallDialog(QDialog):
    def __init__(self,plans,parent):
        super().__init__(parent); self.plans=plans; self.setWindowTitle('批量卸载确认'); self.resize(850,650); box=QVBoxLayout(self)
        box.addWidget(QLabel(f'已选择 {len(plans)} 个应用，将依次打开各自的卸载器。'))
        text=QTextEdit(); text.setReadOnly(True); text.setPlainText('\n\n'.join(e.name+'\n'+plan for e,plan,paths in plans)); text.setMaximumHeight(160); box.addWidget(text)
        self.clear=QCheckBox('卸载成功后额外清理勾选的数据目录'); box.addWidget(self.clear)
        info=QLabel('数据目录默认不选。原卸载器可能自行清理数据，商店卸载通常移除沙盒数据。'); info.setWordWrap(True); box.addWidget(info)
        self.table=CheckTable(['应用 / 数据目录','大小']); self.path_all,self.path_clear=add_selection_controls(box,self.table); box.addWidget(self.table)
        self.path_owners=[]
        for e,plan,paths in plans:
            for path in paths: self.add_path(e,path)
        row=QHBoxLayout(); self.appchoice=QComboBox(); self.appchoice.addItems([e.name for e,_,_ in plans]); row.addWidget(self.appchoice,1); add=QPushButton('添加数据目录…'); add.clicked.connect(self.pick); row.addWidget(add); box.addLayout(row)
        self.purge=QCheckBox('清除 DEB 软件包配置 / Snap 快照'); self.purge.setVisible(any(e.source in ('DEB','Snap') for e,_,_ in plans)); box.addWidget(self.purge)
        self.table.setEnabled(False); add.setEnabled(False); self.purge.setEnabled(False); self.path_all.setEnabled(False); self.path_clear.setEnabled(False)
        self.clear.toggled.connect(self.table.setEnabled); self.clear.toggled.connect(add.setEnabled); self.clear.toggled.connect(self.purge.setEnabled); self.clear.toggled.connect(self.path_all.setEnabled); self.clear.toggled.connect(self.path_clear.setEnabled)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setText('确认卸载所选应用'); buttons.button(QDialogButtonBox.Cancel).setText('取消'); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); box.addWidget(buttons)
    def add_path(self,app,path):
        if (app.id,path) in self.path_owners: return
        self.path_owners.append((app.id,path)); r=self.table.rowCount(); self.table.insertRow(r); item=QTableWidgetItem(app.name+' / '+path); item.setToolTip(path); item.setCheckState(Qt.Unchecked); self.table.setItem(r,0,item); self.table.setItem(r,1,QTableWidgetItem(fmt_size(size_of(path))))
    def pick(self):
        path=QFileDialog.getExistingDirectory(self,'选择该应用的数据目录')
        if path:
            try: check_data_path(path); self.add_path(self.plans[self.appchoice.currentIndex()][0],path)
            except ValueError as ex: QMessageBox.warning(self,'不能清理此目录',str(ex))
    def selected_paths(self,app):
        return [path for i,(owner,path) in enumerate(self.path_owners) if owner==app.id and self.clear.isChecked() and i in self.table.checked_rows()]

class Window(QMainWindow):
    def __init__(self):
        super().__init__(); self.backend=Backend(); self.data={'startup':[],'apps':[],'cache':[],'runtime':[]}; self.loaded=set(); self.checked={k:set() for k in self.data}; self.checked_cache=self.checked['cache']; self.busy=False; self.threads=[]; self.page='startup'
        self.setWindowTitle('电脑管家 · PC Steward'); self.resize(1180,780); self.setMinimumSize(920,620)
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(204); nav=QVBoxLayout(sidebar); nav.setContentsMargins(18,32,18,24); nav.setSpacing(12)
        brand=QLabel('▣  电脑管家'); brand.setObjectName('brand'); nav.addWidget(brand)
        sub=QLabel('PC STEWARD  /  1.1'); sub.setObjectName('navSubtitle'); nav.addWidget(sub); nav.addSpacing(34)
        self.navbuttons={}
        for key,name in [('startup','自启动管理'),('apps','应用管理'),('cache','缓存清理'),('runtime','运行管理'),('history','操作记录')]:
            b=QPushButton(name); b.setCheckable(True); b.setObjectName('nav'); b.clicked.connect(lambda _,k=key:self.switch(k)); nav.addWidget(b); self.navbuttons[key]=b
        nav.addStretch(); sysname=QLabel(('Windows' if WINDOWS else 'Linux')+'\n当前用户：'+HOME.name); sysname.setObjectName('navSubtitle'); nav.addWidget(sysname); outer.addWidget(sidebar)
        content=QWidget(); layout=QVBoxLayout(content); layout.setContentsMargins(32,30,32,22); layout.setSpacing(18); outer.addWidget(content,1)
        head=QHBoxLayout(); self.title=QLabel(); self.title.setObjectName('title'); head.addWidget(self.title); head.addStretch(); self.refresh=QPushButton('↻  刷新列表'); self.refresh.clicked.connect(self.reload); head.addWidget(self.refresh); layout.addLayout(head)
        self.subtitle=QLabel(); self.subtitle.setWordWrap(True); self.subtitle.setObjectName('muted'); layout.addWidget(self.subtitle)
        cards=QHBoxLayout(); self.stats=[]
        for label in ['已发现项目','当前已启用','运行环境']:
            frame=QFrame(); frame.setObjectName('card'); box=QVBoxLayout(frame); box.setContentsMargins(20,15,20,15); t=QLabel(label); t.setObjectName('muted'); v=QLabel('—'); v.setObjectName('stat'); box.addWidget(t); box.addWidget(v); cards.addWidget(frame); self.stats.append((t,v))
        layout.addLayout(cards)
        controls=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText('搜索名称、来源或路径…'); self.search.textChanged.connect(self.render); controls.addWidget(self.search,1)
        self.auto=QCheckBox('每 5 秒刷新'); self.auto.setChecked(True); self.auto.hide(); controls.addWidget(self.auto)
        self.filter=QComboBox(); self.filter.setMinimumWidth(160); self.filter.currentTextChanged.connect(self.render); controls.addWidget(self.filter); self.diskfilter=QComboBox(); self.diskfilter.addItem('所有盘'); self.diskfilter.setMinimumWidth(115); self.diskfilter.currentTextChanged.connect(self.render); self.diskfilter.setVisible(WINDOWS); controls.addWidget(self.diskfilter); layout.addLayout(controls)
        selection=QHBoxLayout(); self.selectall=QCheckBox('全选当前列表'); self.selectall.setTristate(True); self.selectall.stateChanged.connect(self.select_visible); selection.addWidget(self.selectall); self.clearselected=QPushButton('取消全选'); self.clearselected.clicked.connect(self.clear_checked); selection.addWidget(self.clearselected); self.selection_info=QLabel(); self.selection_info.setObjectName('muted'); selection.addWidget(self.selection_info); selection.addStretch(); layout.addLayout(selection)
        self.stack=QStackedWidget(); self.table=QTableWidget(); self.table.setAlternatingRowColors(True); self.table.setShowGrid(False); self.table.verticalHeader().hide(); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.SingleSelection); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.itemSelectionChanged.connect(self.update_actions); self.table.itemChanged.connect(self.update_actions); self.table.itemDoubleClicked.connect(lambda _: self.startup_dialog() if self.page=='startup' else self.runtime_dialog() if self.page=='runtime' else None); self.table.setSortingEnabled(False); self.stack.addWidget(self.table)
        self.history=QTextEdit(); self.history.setReadOnly(True); self.stack.addWidget(self.history); layout.addWidget(self.stack,1)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.setMaximumHeight(5); self.progress.hide(); layout.addWidget(self.progress)
        footer=QHBoxLayout(); self.status=QLabel('准备就绪'); self.status.setObjectName('muted'); self.status.setWordWrap(True); footer.addWidget(self.status,1)
        self.batch=QPushButton(); self.batch.clicked.connect(self.batch_action); footer.addWidget(self.batch)
        self.extra=QPushButton(); self.extra.clicked.connect(self.extra_action); footer.addWidget(self.extra)
        self.action=QPushButton(); self.action.setObjectName('primary'); self.action.clicked.connect(self.main_action); footer.addWidget(self.action); layout.addLayout(footer)
        self.navbuttons['startup'].setChecked(True); self.switch('startup'); QTimer.singleShot(50,self.reload)
        self.runtime_timer=QTimer(self); self.runtime_timer.timeout.connect(self.auto_refresh); self.runtime_timer.start(5000)
    def switch(self,key):
        if self.busy: return
        self.page=key; self.auto.setVisible(key=='runtime')
        for k,b in self.navbuttons.items(): b.setChecked(k==key)
        titles={'startup':('自启动管理','按所属应用归组登录自启动模块。勾选应用可批量启用/禁用，双击查看模块明细。'), 'apps':('应用管理','查看已登记的桌面应用与软件包，按需卸载并选择是否清理应用数据。'), 'cache':('缓存清理','先扫描再选择。仅清理用户缓存与临时文件，不涉及下载、文档或浏览器密码。'), 'runtime':('运行管理','按可执行文件的来源路径归组，匹配已安装应用。展开分组查看实际进程；系统进程只读。'), 'history':('操作记录','每次变更均写入本地日志，方便核对结果与排查问题。')}
        self.title.setText(titles[key][0]); self.subtitle.setText(titles[key][1]); self.search.clear()
        self.filter.blockSignals(True); self.filter.clear(); self.filter.addItem('全部来源'); self.filter.blockSignals(False)
        is_history=key=='history'; self.stack.setCurrentIndex(1 if is_history else 0); self.search.setVisible(not is_history); self.filter.setVisible(not is_history); self.diskfilter.setVisible(WINDOWS and not is_history); self.action.setVisible(not is_history); self.selectall.setVisible(not is_history); self.clearselected.setVisible(not is_history); self.selection_info.setVisible(not is_history); self.batch.setVisible(key in ('startup','runtime')); self.extra.setText({'startup':'添加启动项…','apps':'打开数据目录','cache':'全选当前列表','runtime':'打开来源目录','history':'打开日志文件'}[key])
        self.stats[2][1].setText('Windows' if WINDOWS else 'Linux')
        if is_history: self.reload()
        elif key in self.loaded: self.populate_filter(); self.render()
        else: self.render(); QTimer.singleShot(0,self.reload)
    def auto_refresh(self):
        if self.page=='runtime' and self.auto.isChecked() and not self.busy and QApplication.activeModalWidget() is None: self.reload()
    def populate_filter(self):
        current=self.filter.currentText(); self.filter.blockSignals(True); self.filter.clear(); self.filter.addItems(['全部来源']+sorted({e.source for e in self.data[self.page]})); self.filter.setCurrentText(current); self.filter.blockSignals(False)
        drive=self.diskfilter.currentText(); self.diskfilter.blockSignals(True); self.diskfilter.clear(); self.diskfilter.addItems(['所有盘']+sorted({entry_disk(e) for e in self.data[self.page]})); self.diskfilter.setCurrentText(drive); self.diskfilter.blockSignals(False)
    def work(self,fn,done,message):
        if self.busy: return
        self.busy=True; self.status.setText(message); self.progress.show(); self.refresh.setEnabled(False); self.action.setEnabled(False); self.extra.setEnabled(False); self.batch.setEnabled(False); self.selectall.setEnabled(False); self.clearselected.setEnabled(False)
        for b in self.navbuttons.values(): b.setEnabled(False)
        thread=QThread(self); worker=Worker(fn); worker.moveToThread(thread); thread.started.connect(worker.run)
        self.work_callback=done
        worker.done.connect(self.worker_done, Qt.QueuedConnection); worker.failed.connect(self.worker_failed, Qt.QueuedConnection)
        worker.done.connect(thread.quit); worker.failed.connect(thread.quit); worker.done.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        pair=(thread,worker); self.threads.append(pair); thread.finished.connect(lambda:self.threads.remove(pair)); thread.start()
    def finish_work(self):
        self.busy=False; self.progress.hide(); self.refresh.setEnabled(True); self.extra.setEnabled(True); self.selectall.setEnabled(True); self.clearselected.setEnabled(True)
        for b in self.navbuttons.values(): b.setEnabled(True)
        self.update_actions()
    @Slot(object)
    def worker_done(self,value):
        callback=self.work_callback; self.finish_work(); callback(value)
    @Slot(str)
    def worker_failed(self,msg):
        self.finish_work(); self.status.setText('操作未完成'); QMessageBox.warning(self,'操作未完成',msg)
    def reload(self):
        if self.busy: return
        key=self.page
        if key=='history':
            self.history.setPlainText(LOG.read_text(encoding='utf-8')[-100000:] if LOG.exists() else '还没有操作记录。'); self.stats[0][1].setText(str(len(self.history.toPlainText().splitlines()))); self.stats[1][1].setText('本地保存'); self.status.setText(str(LOG)); return
        def done(values):
            self.data[key]=values; self.checked[key].intersection_update(e.id for e in values); self.loaded.add(key); self.populate_filter(); self.render(); self.status.setText(f'已刷新 · {len(values)} 个项目 · '+datetime.datetime.now().strftime('%H:%M:%S'))
        fn=(lambda:processes(self.data['apps'] or self.backend.apps())) if key=='runtime' else getattr(self.backend,{'startup':'startup','apps':'apps','cache':'caches'}[key])
        self.work(fn,done,'正在扫描，请稍候…')
    def render(self):
        if self.page=='history': return
        self.table.blockSignals(True); old=self.selected(); old_id=old.id if old else None; self.table.setRowCount(0)
        key=self.page; query=self.search.text().casefold(); source=self.filter.currentText()
        headers={'startup':['所属应用 / 选择','启用 / 总模块','启动来源','所在盘','应用来源路径'],'apps':['应用名称','版本','来源','所在盘','安装路径','大小 / 发布者'],'cache':['选择 / 名称','大小','类型','所在盘','实际路径'],'runtime':['应用 / 来源分组','进程数','CPU','内存','所在盘','可执行文件来源']}[key]
        self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers)
        drive=self.diskfilter.currentText()
        self.visible=[e for e in self.data[key] if (source in ('','全部来源') or e.source==source) and (drive in ('','所有盘') or entry_disk(e)==drive) and query in searchable(e)]
        for e in self.visible:
            row=self.table.rowCount(); self.table.insertRow(row)
            if key=='startup': values=[e.name,f"{e.meta['enabled_count']} / {e.meta['count']}",e.source,entry_disk(e),e.detail]
            elif key=='apps': values=[e.name,e.version or '—',e.source,entry_disk(e),(e.meta.get('install')+'（卸载器目录推断）' if e.meta.get('install_inferred') and e.meta.get('install') else e.meta.get('install')) or e.detail or '未登记安装路径',(fmt_size(e.size)+' / ' if e.size else '')+(e.publisher or '未提供大小')]
            elif key=='runtime': values=[e.name,str(e.meta['count']),f"{e.meta['cpu']:.1f}%",fmt_size(e.size),entry_disk(e),e.detail]
            else: values=[e.name,fmt_size(e.size),e.source,entry_disk(e),e.detail]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); item.setData(Qt.UserRole,e.id)
                if col==0:
                    if self.can_check(e): item.setCheckState(Qt.Checked if e.id in self.checked[key] else Qt.Unchecked)
                    else: item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                    item.setToolTip(str(value)+'\n原始名称：'+e.meta.get('original_name',e.name)+'\n名称来源：'+e.meta.get('name_source','系统清单'))
                if col==1 and key=='startup': item.setForeground(QColor('#128263' if e.enabled else '#7c889b'))
                if not e.removable: item.setToolTip(item.toolTip()+'\n受保护的组件 / 系统任务或无卸载器')
                self.table.setItem(row,col,item)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        widths={'startup':{1:110,2:158,3:94},'apps':{1:95,2:145,3:94,5:150},'cache':{1:94,2:130,3:94},'runtime':{1:65,2:65,3:85,4:94}}[key]
        for i in range(len(headers)):
            if i in widths:
                self.table.horizontalHeader().setSectionResizeMode(i,QHeaderView.Fixed); self.table.setColumnWidth(i,widths[i])
            else: self.table.horizontalHeader().setSectionResizeMode(i,QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(48)
        all_data=self.data[key]; self.stats[0][0].setText('来源分组' if key=='runtime' else '应用分组' if key=='startup' else '已发现项目'); self.stats[0][1].setText(str(len(all_data)))
        self.stats[1][0].setText({'startup':'当前已启用','apps':'可卸载应用','cache':'扫描到的空间','runtime':'进程 / 内存合计'}[key])
        self.stats[1][1].setText(str(sum(e.meta['enabled_count'] for e in all_data)) if key=='startup' else str(sum(e.removable for e in all_data)) if key=='apps' else f"{sum(e.meta['count'] for e in all_data)} / {fmt_size(sum(e.size for e in all_data))}" if key=='runtime' else fmt_size(sum(e.size for e in all_data)))
        self.table.blockSignals(False)
        if old_id:
            for i,e in enumerate(self.visible):
                if e.id==old_id: self.table.selectRow(i); break
        self.update_actions()
    def selected(self):
        row=self.table.currentRow()
        return self.visible[row] if 0<=row<len(getattr(self,'visible',[])) else None
    def can_check(self,e):
        if self.page=='runtime': return any(not p['protected'] for p in e.meta['processes'])
        return e.removable
    def checked_entries(self): return [e for e in self.data[self.page] if e.id in self.checked[self.page]]
    def select_visible(self,state):
        checked=state!=Qt.Unchecked.value
        self.table.blockSignals(True)
        for i,e in enumerate(self.visible):
            if self.can_check(e):
                self.table.item(i,0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
                if checked: self.checked[self.page].add(e.id)
                else: self.checked[self.page].discard(e.id)
        self.table.blockSignals(False); self.update_actions()
    def clear_checked(self):
        self.checked[self.page].clear(); self.render()
    def update_actions(self,*args):
        if self.page=='history': return
        if args and isinstance(args[0],QTableWidgetItem) and args[0].column()==0:
            item=args[0]; key=item.data(Qt.UserRole)
            if item.checkState()==Qt.Checked: self.checked[self.page].add(key)
            else: self.checked[self.page].discard(key)
        candidates=[e for e in getattr(self,'visible',[]) if self.can_check(e)]; count=sum(e.id in self.checked[self.page] for e in candidates)
        self.selectall.blockSignals(True); self.selectall.setCheckState(Qt.Checked if candidates and count==len(candidates) else Qt.PartiallyChecked if count else Qt.Unchecked); self.selectall.blockSignals(False)
        selected=self.checked_entries(); self.selection_info.setText(f'已选 {len(selected)} 项 · 全选只覆盖当前筛选的可操作项')
        if self.busy: return
        e=self.selected(); key=self.page
        self.action.setText({'startup':'禁用所选应用自启动','apps':'卸载所选应用…','cache':'清理所选缓存…','runtime':'查看分组进程…'}[key])
        self.action.setEnabled(bool(e) if key=='runtime' else bool(selected))
        self.batch.setText('启用所选应用自启动' if key=='startup' else '结束所选组进程…'); self.batch.setEnabled(bool(selected))
        self.extra.setEnabled(key not in ('apps','runtime') or e is not None)
    def batch_action(self):
        if self.page=='startup': self.toggle_selected(True)
        elif self.page=='runtime':
            selected=[p for e in self.checked_entries() for p in e.meta['processes'] if not p['protected']]
            if self.confirm_processes(selected): self.work(lambda:terminate_processes(selected),self.operation_done,'正在结束所选进程…')
    def confirm_processes(self,items,parent=None):
        if not items: return False
        message=f'确认结束 {len(items)} 个进程？未保存的工作可能丢失。\n\n'+'\n'.join(f"{p['name']} · PID {p['pid']} · {p['exe']}" for p in items)
        return QMessageBox.warning(parent or self,'确认结束进程',message,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
    def toggle_selected(self,enabled):
        groups=self.checked_entries(); modules=[m for e in groups for m in e.meta['modules'] if m.removable and m.enabled!=enabled]
        if not modules: QMessageBox.information(self,'无需变更','所选应用的可操作模块已经处于目标状态。'); return
        message=f"{'启用' if enabled else '禁用'} {len(groups)} 个应用中的 {len(modules)} 个启动模块？\n\n"+'\n'.join(e.name+f"（{e.meta['count']} 个模块）" for e in groups)
        if QMessageBox.question(self,'确认批量自启动变更',message,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.work(lambda:privileged_toggles(modules,enabled),self.operation_done,'正在更新所选启动模块…')
    def extra_action(self):
        if self.page=='startup':
            p,_=QFileDialog.getOpenFileName(self,'选择要在登录时启动的程序',str(HOME),'程序 (*.exe *.bat *.cmd);;所有文件 (*)' if WINDOWS else '所有文件 (*)')
            if p: self.work(lambda:add_startup(p),lambda _:self.reload(),'正在添加启动项…')
        elif self.page=='cache': self.select_visible(Qt.Checked.value)
        elif self.page=='runtime':
            e=self.selected()
            if e and e.meta.get('path'): QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(e.meta['path']).parent if Path(e.meta['path']).is_file() else Path(e.meta['path']))))
        elif self.page=='apps':
            e=self.selected(); paths=related_data(e)
            if paths: QDesktopServices.openUrl(QUrl.fromLocalFile(paths[0]))
            else: QMessageBox.information(self,'应用数据','未识别到可确认属于此应用的用户数据目录。卸载时可手动添加目录。')
        else: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG)))
    def main_action(self):
        e=self.selected()
        if self.page=='startup': self.toggle_selected(False)
        elif self.page=='apps':
            selected=self.checked_entries()
            def show(plans):
                dialog=BatchUninstallDialog(plans,self)
                if dialog.exec()!=QDialog.Accepted: return
                paths={app.id:dialog.selected_paths(app) for app in selected}; purge=dialog.clear.isChecked() and dialog.purge.isChecked()
                all_paths=[app.name+' / '+path for app in selected for path in paths[app.id]]
                if all_paths and QMessageBox.warning(self,'确认永久清理','各应用卸载成功后将永久删除所选目录：\n\n'+'\n'.join(all_paths),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
                self.work(lambda:batch_uninstall(self.backend,selected,paths,purge),self.operation_done,'依次运行所选应用卸载器，请完成各卸载窗口中的步骤…')
            self.work(lambda:[(app,removal_plan(app),related_data(app)) for app in selected],show,'正在核对所选应用的卸载计划…')
        elif self.page=='runtime': self.runtime_dialog()
        elif self.page=='cache':
            selected=[e for e in self.data['cache'] if e.id in self.checked_cache]
            dialog=QDialog(self); dialog.setWindowTitle('确认缓存清理'); dialog.resize(630,460); box=QVBoxLayout(dialog)
            box.addWidget(QLabel(f'所选 {len(selected)} 项，扫描大小 {fmt_size(sum(e.size for e in selected))}'))
            text=QTextEdit(); text.setReadOnly(True); text.setPlainText('\n'.join(e.detail for e in selected)); box.addWidget(text)
            box.addWidget(QLabel('默认保留最近 24 小时的文件，正在使用的文件会跳过。'))
            recent=QCheckBox('同时清理最近 24 小时的缓存文件'); box.addWidget(recent)
            buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setText('确认清理'); buttons.button(QDialogButtonBox.Cancel).setText('取消'); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); box.addWidget(buttons)
            if dialog.exec()==QDialog.Accepted:
                def done(result):
                    self.checked_cache.clear()
                    msg=f"已释放 {fmt_size(result['bytes'])}，跳过 {result['skipped']} 个近期文件 / 链接。"
                    if result['errors']: msg+=f"\n{len(result['errors'])} 项因权限或占用未删除：\n"+'\n'.join(result['errors'][:8])
                    self.operation_done(msg)
                self.work(lambda:self.backend.clean(selected,recent.isChecked()),done,'正在清理所选缓存…')
    def runtime_dialog(self):
        entry=self.selected()
        if not entry or self.busy: return
        dialog=QDialog(self); dialog.setWindowTitle(entry.name+' · 进程详情'); dialog.resize(1000,560); layout=QVBoxLayout(dialog)
        title=QLabel(entry.name); title.setObjectName('dialogTitle'); layout.addWidget(title)
        path=QLabel('归组依据：'+entry.detail); path.setWordWrap(True); path.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(path)
        table=CheckTable(['选择','PID','中文 / 产品名称','CPU','内存','用户','原始名称 / 文件路径 / 命令']); table.setRowCount(len(entry.meta['processes'])); add_selection_controls(layout,table); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for i,p in enumerate(entry.meta['processes']):
            values=['系统 / 只读' if p['protected'] else '',str(p['pid']),p['name'],f"{p['cpu']:.1f}%",fmt_size(p['memory']),p['user'],p.get('original_name',p['name'])+'\n'+p['exe']+'\n'+p['command']]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value); item.setToolTip(value)
                if j==0 and not p['protected']: item.setCheckState(Qt.Unchecked)
                table.setItem(i,j,item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch); layout.addWidget(table)
        note=QLabel('结束进程可能丢失未保存的工作。同一来源目录中的进程不一定属于同一个产品，请核对实际文件路径。'); note.setWordWrap(True); layout.addWidget(note)
        bottom=QHBoxLayout(); end=QPushButton('结束勾选的进程…'); end.setObjectName('primary'); bottom.addWidget(end); bottom.addStretch(); close=QPushButton('关闭'); close.clicked.connect(dialog.reject); bottom.addWidget(close); layout.addLayout(bottom)
        def terminate():
            selected=[p for i,p in enumerate(entry.meta['processes']) if not p['protected'] and table.item(i,0).checkState()==Qt.Checked]
            if not selected: QMessageBox.information(dialog,'选择进程','请先勾选要结束的进程。'); return
            if self.confirm_processes(selected,dialog):
                dialog.accept(); self.work(lambda:terminate_processes(selected),self.operation_done,'正在结束所选进程…')
        end.clicked.connect(terminate); dialog.exec()
    def startup_dialog(self):
        entry=self.selected()
        if not entry or self.busy: return
        dialog=QDialog(self); dialog.setWindowTitle(entry.name+' · 自启动模块'); dialog.resize(1000,560); layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(entry.name+f" · {entry.meta['count']} 个模块"))
        table=CheckTable(['模块名称','状态','启动方式','原始模块名 / 启动命令']); add_selection_controls(layout,table); layout.addWidget(table)
        modules=entry.meta['modules']; table.setRowCount(len(modules))
        for i,m in enumerate(modules):
            values=[m.meta.get('display_name',m.name),'已启用' if m.enabled else '已禁用',m.source,m.name+'\n'+m.detail]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value); item.setToolTip(value)
                if j==0 and m.removable: item.setCheckState(Qt.Unchecked)
                table.setItem(i,j,item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        line=QHBoxLayout(); enable=QPushButton('启用所选模块'); disable=QPushButton('禁用所选模块'); close=QPushButton('关闭'); close.clicked.connect(dialog.reject); line.addWidget(enable); line.addWidget(disable); line.addStretch(); line.addWidget(close); layout.addLayout(line)
        def toggle(enabled):
            chosen=[modules[i] for i in table.checked_rows() if modules[i].enabled!=enabled]
            if not chosen: QMessageBox.information(dialog,'选择模块','请勾选需要变更状态的模块。'); return
            message=f"{'启用' if enabled else '禁用'}所选 {len(chosen)} 个模块？\n\n"+'\n'.join(m.name+' · '+m.detail for m in chosen)
            if QMessageBox.question(dialog,'确认模块变更',message,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
                dialog.accept(); self.work(lambda:privileged_toggles(chosen,enabled),self.operation_done,'正在更新所选模块…')
        enable.clicked.connect(lambda:toggle(True)); disable.clicked.connect(lambda:toggle(False)); dialog.exec()
    def operation_done(self,message):
        QMessageBox.information(self,'操作完成',message); self.reload()
    def closeEvent(self,event):
        if self.busy: QMessageBox.information(self,'操作进行中','请等待当前操作完成后再关闭。'); event.ignore()
        else: event.accept()

STYLE='''
QWidget {font-family: "Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"; font-size: 13px; color:#26344b;}
QMainWindow, QDialog {background:#f4f6fa;}
#sidebar {background:#142238;} #brand {color:white;font-size:23px;font-weight:700;} #navSubtitle {color:#a3b2c8;font-size:11px;line-height:1.5;}
#nav {background:transparent;color:#bcc8da;text-align:left;border:0;padding:14px 16px;border-radius:8px;font-size:14px;}
#nav:checked {background:#2a4568;color:white;} #nav:hover {background:#203551;}
#title {font-size:28px;font-weight:700;} #dialogTitle {font-size:20px;font-weight:700;} #muted {color:#76849a;font-size:12px;}
#card {background:white;border:1px solid #e5eaf2;border-radius:10px;} #stat {font-size:26px;font-weight:600;color:#203d66;}
QPushButton {background:white;border:1px solid #dce3ec;border-radius:7px;padding:10px 18px;}
QPushButton:hover {border-color:#8da9d3;background:#f0f5fd;} QPushButton:disabled {color:#a5afbc;background:#edf0f5;border-color:#e1e6ed;}
#primary {background:#2563c4;color:white;border:0;} #primary:hover {background:#1e54ab;} #primary:disabled {background:#adbed7;}
QLineEdit,QComboBox {background:white;border:1px solid #dce3ec;border-radius:7px;padding:10px;}
QTableWidget {background:white;alternate-background-color:#f8faff;border:1px solid #e5eaf2;border-radius:8px;selection-background-color:#e6efff;selection-color:#244b84;}
QHeaderView::section {background:#eef2f7;color:#718098;border:0;border-bottom:1px solid #e1e7ef;padding:11px;text-align:left;}
QTableWidget::item {padding:8px;} QTextEdit {background:white;border:1px solid #dce3ec;border-radius:6px;padding:10px;}
QProgressBar {border:0;background:#e1e9f5;} QProgressBar::chunk {background:#2563c4;} QCheckBox {spacing:8px;padding:4px;}
'''

def app_icon():
    pix=QPixmap(64,64); pix.fill(Qt.transparent); p=QPainter(pix); p.setRenderHint(QPainter.Antialiasing); p.setBrush(QColor('#2563c4')); p.setPen(Qt.NoPen); p.drawRoundedRect(0,0,64,64,14,14); p.setPen(QColor('white')); p.setFont(QFont('Segoe UI',34,QFont.Bold)); p.drawText(pix.rect(),Qt.AlignCenter,'P'); p.end(); return QIcon(pix)

def main():
    app=QApplication(sys.argv); app.setApplicationName('PCSteward'); app.setOrganizationName('PCSteward'); app.setStyle('Fusion'); app.setStyleSheet(STYLE); app.setWindowIcon(app_icon()); window=Window(); window.show()
    if '--smoke' in sys.argv:
        dest=Path(sys.argv[sys.argv.index('--smoke')+1]); dest.mkdir(parents=True,exist_ok=True); phase=[0]; started=time.time(); report={}
        def check():
            if time.time()-started>240: (dest/'error.txt').write_text('smoke timed out'); app.exit(2); return
            if window.busy: return
            key=['startup','apps','cache','runtime'][phase[0]]
            if key not in window.loaded: return
            report[key]={'count':len(window.data[key]),'rows':window.table.rowCount()}
            window.select_visible(Qt.Checked.value); assert all(e.id in window.checked[key] for e in window.visible if window.can_check(e)); assert all(e.id not in window.checked[key] for e in window.visible if not window.can_check(e)); window.clear_checked()
            window.search.setText('PCSteward-Never-Matches-UI-Fixture'); assert window.table.rowCount()==0; window.search.clear()
            if WINDOWS and window.diskfilter.count()>1:
                window.diskfilter.setCurrentIndex(1); drive=window.diskfilter.currentText(); assert all(entry_disk(e)==drive for e in window.visible); window.diskfilter.setCurrentIndex(0)
            if window.table.rowCount():
                window.table.selectRow(0)
                if key in ('runtime','startup'):
                    QTimer.singleShot(100,lambda:app.activeModalWidget().reject() if app.activeModalWidget() else None); window.runtime_dialog() if key=='runtime' else window.startup_dialog()
            report[key]['ui_checks']='search / disk filter / select-all protection / cancel details passed'
            window.grab().save(str(dest/(key+'.png')))
            if phase[0]<3: phase[0]+=1; window.switch(['startup','apps','cache','runtime'][phase[0]])
            else:
                (dest/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); app.quit()
        timer=QTimer(); timer.timeout.connect(check); timer.start(500)
    return app.exec()

if __name__=='__main__': sys.exit(main())
