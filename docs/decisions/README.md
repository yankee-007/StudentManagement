# ADR 索引

先查此表，只读当前任务相关条目。ADR 保存重要原因与约束，不替代当前代码；没有历史证据的方案不能补写成曾经讨论或失败。

| ADR | 主题 | 状态 | 相关区域 |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-independent-lists-feedback.md) | 筛选名单与反馈独立于发送，兼容旧来源名单 | Accepted | 工作台、群发、反馈 |
| [ADR-002](ADR-002-editor-identity-lifecycle.md) | 编辑身份与稳定 QML 委托 | Accepted | 自动保存、浮窗、模型/界面测试 |
| [ADR-003](ADR-003-autosave-preview-boundary.md) | 群发参数自动保存与显式发送边界 | Accepted | 设置、消息编辑、预览、发送保护 |
| [ADR-004](ADR-004-acquisition-snapshot-boundary.md) | 学习数据完整性与批次快照边界 | Accepted | 采集、班级隔离、历史反馈/看板 |
| [ADR-005](ADR-005-term-binding-and-course.md) | 作业班级目录缓存与课程 ID 自动绑定 | Accepted | 设置页、班期绑定、采集参数 |
| [ADR-006](ADR-006-latest-batch-learning-refresh.md) | 最新批次学习数据跟随获取刷新，历史批次冻结 | Accepted | 催办批次、获取数据、看板、发送预览 |
| [ADR-007](ADR-007-filter-freeze-and-scope.md) | 筛选结果为冻结集合，业务范围只算真正匹配的行 | Accepted | 画像/工作台筛选、名单生成、导出、批量反馈 |
| [ADR-008](ADR-008-remark-revision-window-title.md) | 备注批改以浮窗标题为真实备注，复用 student_contacts | Accepted | 备注批改、企微联系人定位、群发前缀 |
| [ADR-009](ADR-009-live-absence-per-lesson.md) | 未进直播间按节次判定，null 与 0 秒分开，每节课只提醒一次 | Accepted | 未进直播间、直播数据采集、群发名单来源 |
| [ADR-010](ADR-010-dashboard-cumulative-and-completion-buckets.md) | 看板累计人数与累计率同源，完课次数按完成节数分桶 | Accepted | 学习看板、批次快照版本、可跟进人数 |
| [ADR-011](ADR-011-inline-wecom-remark-tool.md) | 备注批改的 OCR 工具内联进 app/，不再依赖 wecomrename/ 目录 | Accepted | 备注批改、依赖声明、仓库入库范围 |
| [ADR-012](ADR-012-manual-followup-status.md) | 批次人工可跟进状态独立于反馈状态 | Accepted | 工作台、字段、批次统计、学习概览 |
| [ADR-013](ADR-013-independent-learning-overview.md) | 独立学习概览、冻结范围与历史降级 | Accepted | 四页签、只读聚合、图表、目标追踪 |

新增条目需满足：不知道这一决定很可能重踩坑或破坏业务。改变已接受决策时，更新原条目状态并链接替代条目，避免互相矛盾的规则。

## 记录规范与导航

创建门槛包括跨模块架构、数据模型、长期接口、实质方案取舍、真实失败或显著兼容/回归风险；普通实现写法和小布局改动不机械生成 ADR。

沿用 ADR-001 等项目编号并检查冲突。新记录包含标题、Status、Context、Options Considered、Decision、Rationale、Consequences、Related Areas；真实有失败证据时才加 Failed Approaches。既有记录不为格式统一而重写。状态使用 Proposed、Accepted、Deprecated、Superseded；Agent 提议不能写成用户已接受，被替代时保留原原因并链接后继。

当前结构见 [架构](../architecture.md)，任务执行与交接见 [活动任务](../tasks/README.md)。只更新受影响的记忆，不复制任务日志。
