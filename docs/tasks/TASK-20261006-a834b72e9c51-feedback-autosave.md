# 催办反馈卡片自动保存与输入性能

- Identity: TASK-20261006-a834b72e9c51；awaiting_acceptance；2026-10-06 Asia/Shanghai。
- Requirement: 移除记录反馈按钮，参考画像填写卡片，自动保存且支持修改，解决输入卡顿。用户确认：停顿约半秒或失焦保存；非空计已回复，清空恢复待反馈，不推进选择。
- Baseline: main / adc1bcbce71c721f9dbbeebfb51d04153be3d128；工作区干净；单 Agent 写入。
- Scope: CampaignDetail、工作台及共用反馈浮窗的保存链；不改正式数据库，不连接平台或企微。
- Findings: 主卡片每次文字变化同步写草稿并广播 changed/selectionChanged；浮窗每次草稿保存 reload_rows。反馈显示与草稿分离，既有 submit 追加记录并推进选择。
- Implementation: CampaignDetail 移除提交按钮及重复只读反馈框，使用可修改的单框、保存状态及自适应高度。Workflow 集中合并连续输入，只保存捕获身份的反馈；失败保留待保存值，阻止关键上下文切换及主窗口关闭。CampaignStore 原表事务内替换本批次反馈，旧反馈与草稿在编辑前完整显示，不做全库迁移。保留旧 draft/submit 接口兼容。
- Findings / repairs: 定时器直接连接返回 bool 的 Qt Slot 在本机 PySide6 触发 access violation；改为 void lambda 回调后定时器测试通过。Review 发现保存后排序可能改变点击行索引，改为先捕获学号再完成选择。离屏输入法事件覆盖预编辑不保存、确认后保存。
- Verification: 26 项相关测试通过（test_feedback_autosave、test_workbench_revision、test_campaign_companion、test_filter_freeze、test_workbench_ui，后者包含真实 QML smoke）。另行通过 smoke_editor_identity 和 500 人 smoke_workbench_revision，覆盖输入法预编辑/确认、定时保存、焦点/光标、修改、主窗/浮窗关闭、归属与冻结筛选。500 名虚构学员，100 次连续文字更新合并为一次写库；中位 0.09ms，p95 0.40ms（文字属性更新和事件处理，非物理键入延迟保证）。中文可读的 1000×700 界面已检查。未跑全库回归，未访问正式数据或真实平台/企微。
- Snapshot: 实现和相关文档已完成，按任务文件及本地 Git 提交恢复；下一步由用户在当前版本试用主卡片及浮窗的中文输入、粘贴、修改、清空和切换，确认主观流畅度。
- Delivery: 本地实现和验证，等待主观体验验收；无远端上传授权，不推送。
