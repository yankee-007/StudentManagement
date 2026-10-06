# TASK-20261006-c9e4a13bf572：原生标题栏与顶部工具栏统一

## Identity
- 工作状态：cancelled
- 更新时间：2026-10-06 22:36（Asia/Shanghai）
- 关联：TASK-20261006-76ec258f174b

## Requirement
实施用户选择的方案 1：保留原生标题栏和窗口操作，与应用白色顶部工具栏统一配色，移除工具栏重复的应用名称。验证宽窄窗口、原生窗口状态和既有关闭保护；主观视觉验收独立。

最新澄清：用户希望应用名称更醒目，明确要求在顶部工具栏、班期下拉框左侧放较大的「学员管理」。现使用 22px 加粗标题；原生标题栏字号保持系统管理。本次局部调整基于干净的 f3c0e85 工作区。

## Baseline / Workspace
- main；起点 6d5df9593cb5b0be9703bfa061619a3c088751ea；工作区及暂存区干净。
- 单 Agent；使用虚构学员与临时数据库，不启动默认业务应用，不访问真实平台或企微。
- 无新增上传授权。

## Findings / Design
- 本机 Windows 10 build 19045 / Python 3.11 / PySide6 6.8.3。独立 QWindow 的 DWM 探针：属性 20（浅色模式）成功，35（标题栏背景色）返回 0x80070057。系统 ColorPrevalence 为 0。
- 微软文档明确属性 34/35/36 从 Windows 11 build 22000 支持。Windows 11 精确使用 QML 主题色；Windows 10 尝试浅色，显式配色不支持时保留原生渲染，不改全局系统设置。
- app/window_theme.py 使用指针宽度正确的 HWND 与 COLORREF；初始化、显示、激活、系统主题或窗口句柄变化后重新应用。不替换边框或处理鼠标／关闭消息。
- Main.qml 暴露主题颜色供 Python 使用；工具栏仅保留底部分隔线。初版移除工具栏标题，后按用户澄清恢复为班期下拉框左侧 22px 加粗的 appToolbarTitle。现有班期 100px 居中选择和操作入口保留。

## 撤销前的 Snapshot / Verification
实现及针对性验证完成；文件为 app/window_theme.py、main.py、qml/Main.qml、tests/smoke_native_title_bar.py 及受影响的入口／架构／任务文档。

- Windows 10 原生窗口：实际 DWM 读取确认浅色模式；三个尺寸（1280×800、1000×700、720×480）中文截图可读，标题栏和工具栏白色衔接，22px 工具栏标题位于班期左侧且不重叠，班期及重启控件在窗口内。截图在忽略目录 output/native-title-bar；PrintWindow 仅读取测试 HWND。
- 原生系统命令实际检查最大化、最小化与还原；原生 caption/system menu/resize/minimize/maximize 样式位保持；联系人忙碌时拒绝关闭，结束后可关闭。模拟 DLL 不可用及单个颜色接口失败不阻断；模拟 ABI 检查 Windows 11 的 COLORREF 与 HWND 参数。非 Windows／offscreen 跳过原生设置。
- 已通过 smoke_ui_refresh（七模块／三个尺寸／21 张截图）、smoke_ui_refinements（班期与联系人操作）、smoke_restart_ui（忙碌保护／正常关闭）、test_restart（3 项）。这些检查使用临时数据库和虚构数据，没有真实登录或发送。
- 本次标题恢复后重新通过 smoke_native_title_bar 与 smoke_ui_refresh；查看原生小窗口截图确认标题完整、与班期下拉框间隔正常。其余上述检查为初版标题栏实现证据，本次未重复运行。
- 首次原生还原断言错误地预期「最大化后最小化，再还原」直接回普通窗口；实际 Windows 保留最大化状态。更正为两次还原，之后通过，未修改产品窗口行为。
- 首次桌面区域截图被其它前台窗口遮挡，已删除并改为对测试 HWND 调用 PrintWindow；最终证据仅含虚构数据。

## Handoff / Closure
用户明确要求回退至方案 1 实现前；方案 1 及随后 22px 标题均已撤销，产品代码恢复至 6d5df95。此任务取消，不再等待视觉验收；上述验证仅为撤销前的实现记录。后续回退验证与本次 GitHub 交付见 TASK-20261006-e751c908ab34。
