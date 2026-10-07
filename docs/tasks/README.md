# 活动任务

按 [有效策略](../agent/policy.md) 的 adaptive 条件登记真实任务。默认单 Agent、单写入者；索引不是锁或跨分支实时调度表。

| Task ID | 标题 | 工作状态 | 分支或范围 | 文件 |
| --- | --- | --- | --- | --- |
| TASK-20261006-76ec258f174b | 班期切换与学员操作界面细化 | awaiting_acceptance | main／QML、联系人默认配置 | [任务](TASK-20261006-76ec258f174b-ui-refinements.md) |
| TASK-20261006-3d2ba861e904 | 学员管理桌面 UI 优化 | awaiting_acceptance | main／QML 界面 | [任务](TASK-20261006-3d2ba861e904-ui-refresh.md) |
| TASK-20261006-a834b72e9c51 | 催办反馈卡片自动保存与输入性能 | awaiting_acceptance | main／反馈编辑链 | [任务](TASK-20261006-a834b72e9c51-feedback-autosave.md) |
| TASK-20261006-9dd5d6536487 | 看板既有任务的人工验收与待定口径 | awaiting_acceptance | main／旧快照待重新核验 | [任务](TASK-20261006-9dd5d6536487-dashboard-handoff.md) |
| TASK-20261007-19754d1a822f | 催办看板历史对比与差值考核线设计 | awaiting_acceptance | main／看板设计，预览阶段，代码零改动 | [任务](TASK-20261007-19754d1a822f-dashboard-history-comparison.md) |

规则见 [任务协议](../agent/workflow.md)。先更新任务，再同步索引；done/cancelled 从活动表删除并保留原文件路径，核对 ID 不再留在活动表。历史任务可重开；新需求另建并关联，不登记模板示例。
