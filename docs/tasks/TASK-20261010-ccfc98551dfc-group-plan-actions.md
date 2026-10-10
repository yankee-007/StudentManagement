# 群发中心个人编辑与方案右键操作

- Task ID: TASK-20261010-ccfc98551dfc
- 状态: done
- 更新时间: 2026-10-10 12:38 +08:00

## Requirement

个人消息弹窗按 Esc 取消未保存修改；已单独编辑的人员及消息可见提示；方案下拉框右键支持重命名与删除，移除独立重命名按钮。

## Baseline / Workspace

- 起点: main，ca6a10ab8ed5aaa764054fbee88a916cd63c105f。
- 起始 staged / unstaged / untracked 均为空；当前 Agent 单独写入，沿用当前分支。

## Findings / Snapshot

- 个人消息已经持久化 personal_override；复用此标记，无需改存储格式。
- 下拉框收起时右键管理当前方案，展开时右键管理对应项；菜单与弹窗捕获方案 ID，避免操作错方案。
- 删除经确认清除独立群发库内该方案的成员、消息、尝试记录；禁止删除发送中、未核实或来源回写未完成的方案，不操作来源库。
- 三项功能已实现，涉及 app/group_center.py、group_dispatch.py、qml/GroupCenter.qml、RecipientMessages.qml。个人弹窗 Escape 快捷键覆盖内联编辑按键，关闭清空未保存整稿；标记复用既有数据。
- 现有解释器未安装 PySide6；临时隔离环境已安装 Python 3.13 / PySide6 6.8.3 及相关依赖，不修改全局环境。
- 界面首轮失败发现 rowsChanged 的 QML 回调可先于 Python 表格刷新，导致保存后标记仍读取旧模型；已改为 modelInfoChanged 后刷新。测试直接读取 QQuickPopup* 遇到 PySide 转换限制，改用可见下拉项；保护记录测试使用捕获的真实方案 ID，保持其保护状态至原有断言完成，再在临时数据中核实后验证删除。
- 小窗姓名标记缩为「已改」，保留姓名空间，完整提示仍可悬停查看；删除弹窗只显示本次删除失败提示。

## Verification

- 47 项相关后端测试通过：tests.test_group_center / test_group_interaction / test_message_content / test_profile_group_flow / test_real_sending。覆盖删除当前/未选中/最后方案、陈旧 ID、保护状态、失败事务回滚、来源回执保留、个人覆盖和模板保护。
- 四个真实 QML 离屏冒烟通过：smoke_group_interaction、smoke_group_list_view、smoke_group_message_input、smoke_profile_group。使用虚构学员、临时数据库、模拟发送；未启动正式应用或真实发送。
- QML 证据覆盖 Esc 取消整稿及内联编辑、保存标记即时出现/模板覆盖后清除、下拉左右键目标、取消删除/删除失败/当前与最后方案删除、附件输入、模块/预览/关闭的草稿保护。
- 已检查亮暗主题、1250×800 与 720×480 截图，中文可读。截图输出在忽略目录 output/group-plan-actions、output/group-message-list。以上证据对应本轮本地实现，不代替正式环境主观体验验收。
- 受影响的 README、PROJECT_CONTEXT、架构和 ADR-003 已同步；最终差异检查无空白错误。

## Handoff / Closure

实现、自动验证和审查已完成，无待处理验收条件；用户尚未对正式环境主观体验作确认。群发交互交付版本为 `9f97610`。2026-10-10 用户明确要求「提交至github」，授权将本轮实现、此前尚未上传的 `ca6a10a` 学习概览拖动修复及本次授权/交付说明正常快进推送至 origin 的 main；实际远端已核对为 `https://github.com/yankee-007/StudentManagement.git`，授权边界见项目策略。上传结果以 Git 远端查询及本轮交付答复核对。若继续调整，从当前磁盘代码与 Git 核对恢复，不沿用旧测试结果作为后续变更的保证。
