# 学员画像浮窗跨班识别

- Identity: TASK-20261007-b9167e34ac52；done；2026-10-09 22:50 +08:00。用户于 2026-10-09 确认「已全部验收」；实现版本为 commit b24c0a4 的 main，真实企微兼容性按验收人确认。
- Requirement: 自动识别已登记班级的聊天学员；优先备注/前缀，姓名唯一时兜底；下拉含自动识别及固定班级；只切浮窗；显示前缀 姓名；移除姓名拖动与重试按钮。
- Baseline: main / 23f123d994836a7d57131c091145cc1704af7275；起点工作区干净。
- Workspace: 当前单 Agent，未授权本轮远端上传。
- Initial implementation snapshot: 已修改 app/profile_companion.py、qml/FloatingProfile.qml，回归断言适配浮窗独立班级。待跨班、重名、保存归属及真实 QML 验证。
- Findings: 仍读取企微前台独立聊天 HWND 标题；不会读取主窗口会话内容。按数据库路径缓存仓库，每次匹配读取名单及备注；失败保留待保存编辑。
- Verification: 默认 Python 缺少 Crypto，测试未加载；改用 README 指定环境。未接触正式数据库、真实企微或网络。
- Handoff: 完成测试、文档影响检查与本地提交；真实企微人工验收待用户操作。

- Final snapshot: 实现与文档已完成。浮窗下拉支持自动/固定班级，系统标题栏移动；按钮移除，retryContact 后端保留兼容。主界面班级及全部班级视图不改变浮窗身份。读取备注表前检查存在性，未打开的新班库不被强制创建备注表。使用本班备注批改前缀与联系人前缀（联系人前缀缺省时沿用全局配置）；匹配的前缀用于显示，无配置则只显示姓名。
- Verification (final): README 指定 groupmessaging 环境，12 项测试通过（test_profile_companion_classes、test_profile_editor_layout、test_class_isolation_regressions）。smoke_profile_companion_classes 通过真实 QML 键盘切班、跨班输入保存、自动模式重名阻断、240×490/220×280 布局检查；截图视觉检查中文可读、控件未溢出，临时输出在 output/profile-companion（不入库）。旧 smoke_editor_identity 在第 56 行微信选项断言失败，使用 git archive HEAD 临时副本复跑在同处失败，属已证实基线失败，本轮未修。测试不连接真实企微或平台。
- Human acceptance: 重启应用后，以不同班级企微独立聊天窗口验证自动识别、重名下拉固定、标题栏拖动和实际编辑体感；尚未人工验收。
- Handoff / delivery: 本地提交按项目策略保存；本轮未获远端上传授权，不推送。需求范围内完成，无待实现项。
