# 电脑管家 · PC Steward

Windows / Linux 原生 Qt Widgets 桌面应用，中文界面，无需浏览器。当前版本 1.1.0。

## 功能

- 自启动：Windows Run 注册表（32/64 位）、启动文件夹、登录/启动/定时/事件自动计划任务；Linux XDG 自启动和 systemd 用户服务。按所属应用归组，展示启用数和模块总数，双击分组可查看注册表项、启动文件及计划任务原始命令。支持全选应用批量启用/禁用，也可在明细中全选或单选模块。可添加启动程序。Windows 系统计划任务集中为只读组，系统目录启动项只读；一次批量操作中的管理员变更合并为一次 UAC 请求。Windows 系统服务不在当前管理范围。
- 应用：Windows 已登记的桌面应用及 Microsoft Store；Linux DEB、RPM、Pacman、Flatpak、Snap。显示版本、来源、安装目录、盘符及登记大小。注册表未登记安装目录时，明确标记由卸载器目录推断；无法判断时显示未提供路径。
- 卸载与数据：调用系统或应用原有卸载器，用户可勾选已识别的数据目录，也可手动添加当前用户应用数据根目录内的专用目录；只有确认应用从系统清单中消失后才删除所选目录。未勾选时不额外删除数据。原卸载器可能自行处理数据，Store 卸载通常会删除其沙盒数据。
- 缓存：逐项展示用户临时文件、用户缓存及已知浏览器/图形缓存的大小与路径。默认保留最近 24 小时的文件；跳过链接、目录联接和不可删除的文件。切换来源或盘符筛选会保留已有勾选。
- 运行管理：按可执行文件所在目录匹配已安装应用的安装根目录，将相同来源集中展示。无法匹配时直接显示来源目录，无法读取路径时保持独立 PID 分组。Linux 公共 bin 目录按实际可执行文件区分，避免混合不同应用。展示进程数、CPU、内存、盘符，支持搜索、每 5 秒刷新、展开 PID/用户/路径/命令，并确认结束明确勾选的进程。系统进程、SSH、本工具进程只读；PID 创建时间用于防止误操作复用的 PID。
- 全选与批量操作：应用、自启动、缓存、运行管理均可全选当前筛选结果中的可操作项、取消全选。切换筛选保留勾选，受保护项目排除。应用支持批量卸载；卸载遇到失败或取消即停止剩余应用。应用数据目录、启动模块和进程明细均可全选，数据清理仍默认关闭。
- 名称显示：优先中文开始菜单、商店清单资源、程序版本信息与已知组件中文说明，UUID 和模块名保留在悬浮详情与搜索中。进程明细同时展示产品名称、原始文件名、路径、PID，稳定操作标识保持一致。Linux 利用桌面条目的 `Name[zh_CN]` / `Name[zh]`。无法取得中文品牌名时保留原名，无法识别的组件用通用中文说明。
- 操作记录：本地轮转日志。Windows `%LOCALAPPDATA%\PCSteward\operations.log`；Linux `~/.local/share/PCSteward/operations.log`。

自动归属来自已登记的路径和保守匹配。同一目录可能包含多个产品，进程详情始终显示实际文件路径。便携软件、无法确认归属的数据、其他账号数据、远端同步数据不声称全部自动识别。缓存页面中的扫描大小是候选文件总量，最终释放量以删除结果为准。Windows 用户看到的物理 RAM 使用量不等同于进程 RSS 简单相加，本应用内存分组显示 RSS 合计。

## Windows 安装与构建

安装包中的 `release/PCSteward` 是独立可运行程序，包含 Python 和 Qt 运行库，无需另装 Python。双击 `PCSteward.exe` 可直接运行；执行同级安装脚本建立桌面和开始菜单入口，并登记到系统应用列表：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-windows.ps1
```

默认路径：`%LOCALAPPDATA%\Programs\PCSteward\PCSteward.exe`。卸载可通过 Windows“应用和功能”进行，保留操作日志。

从源码构建（Python 3.10+，Windows x64）：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python -m PyInstaller --noconfirm --onedir --windowed --name PCSteward --icon app.ico --distpath release app.py
```

## Linux 安装

需要 Python 3.10+、venv、桌面环境以及 Qt 所需系统库；发行版软件包卸载授权依赖 PolicyKit 的 `pkexec` 与桌面授权代理。Qt 6.11 Linux 二进制要求 glibc 2.34+；Ubuntu 22.04+、Debian 12+、当前 Fedora/Arch 可使用本安装方式。Ubuntu/Debian 如缺少 xcb 插件依赖，可安装 `libxcb-cursor0`、`libxkbcommon-x11-0` 等实际报错所指依赖。

```bash
bash install-linux.sh
~/.local/bin/pc-steward
```

安装到当前用户的数据目录，在桌面应用菜单创建“电脑管家”。依赖安装阶段需要网络。Linux 发行版的包管理器操作会展示计划，受保护核心组件拒绝卸载，不自动移除无人使用的依赖。

## 验证

```bash
python -m unittest discover -s tests -v
python app.py --smoke artifacts/desktop
```

测试覆盖缓存近期文件/链接保护、数据路径校验、选中数据的条件清理、真实测试进程结束、Linux XDG 覆盖启停，以及 Windows 注册表启动项和登记卸载器的独立测试应用。测试应用均有独立前缀，结束后清除。

`--smoke` 在真实清单上切换四个页面，检查搜索、Windows 盘符筛选、选择与进程详情取消，输出截图和 inventory.json。Linux 无显示设备时可设置 `QT_QPA_PLATFORM=offscreen`；Windows 应在交互桌面运行，以验证字体与系统可读进程。

规格草案位于 `spec/desktop/management`，已执行验证摘要见 [docs/VALIDATION.md](docs/VALIDATION.md)。运行时生成的截图与清单保存在本地 `artifacts`，不提交到仓库。

## 实现依据

- [Microsoft：Run 注册表启动项](https://learn.microsoft.com/windows/win32/setupapi/run-and-runonce-registry-keys)
- [Microsoft：登记卸载信息](https://learn.microsoft.com/en-us/windows/win32/msi/uninstall-registry-key)
- [Qt：Python 桌面部署](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- [Freedesktop：桌面自启动规范](https://specifications.freedesktop.org/autostart/latest/)

Windows 名称解析使用 [SHLoadIndirectString](https://learn.microsoft.com/en-us/windows/win32/api/shlwapi/nf-shlwapi-shloadindirectstring) 解析商店资源，并读取 [VerQueryValue](https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-verqueryvaluew) 的产品名/文件说明。
