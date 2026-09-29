# ADR-004: 学习数据完整性与批次快照边界

## Status

Accepted（部分取代：[ADR-006](ADR-006-latest-batch-learning-refresh.md) 规定**最新批次**的学习数据跟随每次获取刷新；“已建批次学习数据固定”只对非最新批次成立）。2026-09-29 按现行代码、测试及 2026-09-26 业务审计修复记录整理；不推测最初决策日期。

## Context

历史审计曾复现同学号姓名冲突被合并、缺少作业丢掉已知完课数据、只匹配少量人员仍建全班快照，以及历史反馈混入之后批次等问题。记录来源为 BUSINESS_LOGIC_AUDIT.md，A01–A07 已修复。

## Options Considered

审计记录曾建议严重缺失时阻止建批或人工确认后建立不完整批次。当前实现选择完整性阻断；不凭空补写未讨论的百分比阈值或最终确认过程。

## Decision

单独获取可保存单侧已知数据，缺失标记 U；新建催办要求本班全部在读真实学员两侧齐全且姓名一致，有问题保留原学习数据并记录异常。获取/取消返回必须检查当前上下文。

每班库隔离，历史批次的学习快照不随获取重写（最新批次按 [ADR-006](ADR-006-latest-batch-learning-refresh.md) 跟随获取刷新）。最新批次可同步当前身份/微信/免催；历史批次只读，以往反馈仅来自更早批次。反馈及草稿有独立表，采集不覆盖人工记录。

## Rationale

既保留已取得的信息，又不让部分匹配伪装成完整催办。当前资格变化与历史证据分别处理，避免回看历史时被当前资料改写。

## Consequences

不要把 U 当作完成或未开课 N；不要恢复“两平台交集才保存”的旧行为。采集成功和允许建批是不同条件。看板保存批次快照，当前代码将仍在读的免催学员计入分母；早期口径冲突需用户确认后才能改，不能从旧统计函数推断新看板口径。

## Rejected / Failed Approaches

历史审计的 A02/A03/A04/A06/A07 有复现和回归证据：静默合并姓名、丢弃单侧结果、缺失建批、当前免催不刷新、历史反馈时间方向错误均不可重新引入。旧报告的“尚未修复”段落只描述当时现场，不是当前待办。

## Related Areas

app/acquisition/merge_data.py、backend.py、importer.py、roster_sync.py、campaigns.py、dashboard.py；tests/test_business_logic.py、test_fetch_workflow.py、test_dashboard.py、test_class_isolation_regressions.py；BUSINESS_LOGIC_AUDIT.md。
