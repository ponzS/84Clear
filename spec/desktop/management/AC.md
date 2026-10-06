# 验收场景
Status: draft

- SC-STARTUP: Given 已登记的用户启动项，When 用户禁用后重新扫描，Then 显示已禁用；再次启用恢复启动命令。
- SC-UNINSTALL: Given 可卸载的应用，When 用户取消卸载，Then 应用数据保留；When 卸载完成且应用不再登记，Then 仅清理用户明确勾选的目录。
- SC-CACHE: Given 含旧文件、新文件及指向文档的链接的缓存目录，When 用户按默认设置清理所选项，Then 旧文件删除，新文件与链接目标保留。
- SC-PROTECT: Given 用户试图清理数据根目录、系统共享目录、链接目标或个人文档，When 提交操作，Then 拒绝操作并显示原因。
- SC-DESKTOP: Given Windows 或 Linux 桌面，When 启动应用，Then 展示原生窗口，三个功能页可加载真实系统清单且不阻塞界面。

这些场景由直接需求整理。新增边界尚未单独取得人工 AC 文案确认，因此维持 draft；实际功能测试结果另见 artifacts。
- SC-DISK: Given Windows 各盘上的已登记安装或缓存路径，When 用户按盘筛选，Then 只显示匹配盘的项目，未知路径显示未知而不推测盘符。
- SC-RUNTIME: Given 多个来自同一应用安装目录的真实进程，When 打开运行管理，Then 展示同一来源分组及资源汇总，展开可核对每个 PID 的实际文件路径。
- SC-TERMINATE: Given 两个独立普通测试进程，When 选择其中一个并确认结束，Then 仅所选进程结束，另一个保持运行；本工具及系统进程不可结束。
- SC-NAMES: Given 应用提供中文菜单/资源显示名或系统组件只有 UUID，When 加载应用与进程列表，Then 中文产品名/组件说明优先，原始名称可在详情核对及搜索，操作仍使用原始稳定标识。
- SC-STARTUP-GROUP: Given 同一 WPS 安装目录内的多个自动启动任务/模块，When 打开自启动页，Then 显示一个 WPS 分组及准确模块数，展开可分别勾选启用/禁用，系统只读模块不参与批量变更。
- SC-SELECT-ALL: Given 筛选后的可操作列表含受保护项目，When 全选，Then 仅勾选当前筛选范围内的可操作项目，切换筛选保留已有勾选，取消全选清空该页勾选；模块/进程/应用数据明细同样提供全选。
- SC-BATCH-UNINSTALL: Given 用户确认多个应用的卸载与每个应用的数据选择，When 某应用卸载失败或取消，Then 停止处理后续应用，不清理失败应用的数据；成功应用仅清理其自身被勾选的目录。
