# 催办反馈卡片自动保存与输入性能

- Identity: TASK-20261006-a834b72e9c51；awaiting_acceptance；2026-10-06 Asia/Shanghai。
- Requirement: 移除记录反馈按钮，参考画像填写卡片，自动保存且支持修改，解决输入卡顿。用户确认：停顿约半秒或失焦保存；非空计已回复，清空恢复待反馈，不推进选择。后续调整为单行可编辑下拉框，预置「答应补课」「未接听电话」，可新增快捷选项；移除待反馈视图，仅保留全班快照、本次催办，以反馈为空的列筛选替代。
- Baseline: main / adc1bcbce71c721f9dbbeebfb51d04153be3d128；工作区干净；单 Agent 写入。
- Scope: CampaignDetail、工作台及共用反馈浮窗的保存链；不改正式数据库，不连接平台或企微。
- Findings: 主卡片每次文字变化同步写草稿并广播 changed/selectionChanged；浮窗每次草稿保存 reload_rows。反馈显示与草稿分离，既有 submit 追加记录并推进选择。
- Implementation: CampaignDetail 移除提交按钮及重复只读反馈框，使用画像式单行可编辑下拉框；选择快捷选项填入反馈，也能自由修改。旁边「+」新增选项，按班级 settings 持久化，主卡片和浮窗共用。界面视图仅保留 all/targets，旧 pending 后端接口保留兼容，当前界面不再调用。Workflow 集中合并连续输入，只保存捕获身份的反馈；失败保留待保存值，阻止关键上下文切换及主窗口关闭。CampaignStore 原表事务内替换本批次反馈，旧反馈与草稿在编辑前完整显示，不做全库迁移。保留旧 draft/submit 接口兼容。
- Findings / repairs: 定时器直接连接返回 bool 的 Qt Slot 在本机 PySide6 触发 access violation；改为 void lambda 回调后定时器测试通过。Review 发现保存后排序可能改变点击行索引，改为先捕获学号再完成选择。离屏输入法事件覆盖预编辑不保存、确认后保存。扩充 QML 等待测试后暴露浮窗识别 mock 只覆盖打开瞬间的问题，已将识别全程模拟，修复随机活动窗口干扰，UI 重跑通过。
- Verification: 本轮 27 项相关测试通过（test_feedback_autosave、test_workbench_revision、test_campaign_companion、test_filter_freeze 的 26 项，以及单独复跑通过的 test_workbench_ui，后者包含真实 QML smoke）。另行通过 smoke_editor_identity 和 500 人 smoke_workbench_revision，覆盖单行高度、两个初始快捷项、选择/自由输入、新增及浮窗同步、输入法预编辑/确认、定时保存、焦点/光标、修改、主窗/浮窗关闭、归属与冻结筛选、反馈为空组合筛选。快捷选项持久化/去重/班级隔离已覆盖。500 名虚构学员，100 次连续文字更新合并为一次写库；中位 0.06ms，p95 0.37ms（文字属性更新和事件处理，非物理键入延迟保证）。中文可读的 1000×700 单行界面已检查。未跑全库回归，测试仅临时数据及模拟交互。
- Snapshot: 原自动保存版本已提交 ca494b3；本轮单行下拉及两视图修改和文档已完成，保存为该 Task 的后续本地提交；下一步由用户试用主卡片和浮窗的快捷选择、自由输入、新增选项及反馈为空筛选，确认使用体验。
- Delivery: 本地实现和验证，等待主观体验验收；无远端上传授权，不推送。
