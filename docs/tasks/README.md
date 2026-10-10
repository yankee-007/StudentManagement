# 活动任务

按 [有效策略](../agent/policy.md) 的 adaptive 条件登记真实任务。默认单 Agent、单写入者；索引不是锁或跨分支实时调度表。

任务与消息、Session 不一一对应，澄清、修正和接力沿用原 ID。索引只表示当前检出版本可见的记录；接手时核对实际文件、Git 分支及相关 worktree。若以后启用 task-worktree，main 的空表不能证明其他工作区无活动任务，Task 通常先存在任务分支；集成仍需串行协调，本表不授予写入权。关闭跟踪时保留旧记录，不创建或更新任务/活动表，按有效策略说明恢复限制。

原有 13 项待验收任务已由用户于 2026-10-09 确认「已全部验收」，任务文件保留在原路径。完整清单可用 `docs/tasks/TASK-*.md` 检索，历史文件名见提交记录。

| Task ID | 标题 | 工作状态 | 分支或范围 | 文件 |
| --- | --- | --- | --- | --- |
| TASK-20261010-ec62960cf424 | 群发中心剪贴板模式 | awaiting_acceptance | main | [任务](TASK-20261010-ec62960cf424-clipboard-mode.md) |
| TASK-20261010-e6f409a58d72 | 群发消息附件预览 | awaiting_acceptance | main | [任务](TASK-20261010-e6f409a58d72-message-attachments.md) |
| TASK-20261010-9471b8c036da | 催办工作台性能与群发名单弹窗 | awaiting_acceptance | main（已按授权集成） | [任务](TASK-20261010-9471b8c036da-workbench-performance-list-dialog.md) |

规则见 [任务协议](../agent/workflow.md)。启用跟踪时先更新任务，再同步索引；done/cancelled 从活动表删除并保留原文件路径，核对 ID 不再留在活动表。历史任务可重开；新需求另建并关联，不登记模板示例。
