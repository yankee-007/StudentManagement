# ADR-006: 最新批次学习数据跟随获取刷新

## Status

Accepted。2026-09-29 由用户明确要求（“让最新批次学习列跟随每次获取刷新；但是不可影响旧批次”）取代 [ADR-004](ADR-004-acquisition-snapshot-boundary.md) 中“已建学习快照不随获取重写”对**最新批次**的部分。历史批次仍按 ADR-004 冻结。

## Context

工作台的刷新按钮（qml/Main.qml 的 fetchLearningButton，现位于「新建催办」左侧、名为「刷新数据」）只在未建批次或选中最新批次时可见。按 ADR-004 的原始口径，任何已建批次的学习快照都不随获取重写，于是用户在最新批次点「获取数据」后会出现“半刷新”：toast 报“获取完成”，姓名/学籍状态/微信/免催等身份列会跟随当前资料变化，但未完课次、未完作业、欠交合计、合计完成课程/作业仍是建批时的值，看板也仍写着“创建时的数据快照”。界面上没有任何提示解释这种差异，容易被当成获取失败或数据未刷新；要看到新数据只能「新建催办」再建一批。

## Options Considered

1. 保持全批次冻结，只补 UI 提示，不改数据语义。
2. 最新批次跟随每次获取刷新，历史批次继续冻结（本决定）。
3. 全部批次跟随刷新：被否决——历史反馈、看板和导出依赖创建当时的证据，改写等于推翻 ADR-004 的核心。

## Decision

- 获取成功、名单同步、进入工作台都经过 Workflow.refresh_live()；它先调用 CampaignStore.refresh_latest_learning()，按当前学习数据重算**最新批次**的学习列与看板快照。
- 只更新 campaign_students.snapshot 中的 courses、homework、missing_total、completed_total、completed_courses、completed_homework、source_sync。批次成员、反馈、草稿、免催、eligible、reason、message、send_state、sent_at 一律不动。
- 学习列与建批共用同一套推导 campaigns.learning_snapshot(flags)；U 仍显示“未获取”/“—”，不得把 U 当作完成或未开课。
- 本次获取未返回的学员（不在 learning_source() 中）**保留已取得的数据**，不因一次缺失获取被清空。
- 旧批次（batch_id != max(id)）完全不参与刷新；导出、看板、反馈继续读它们自己的快照。
- campaign_dashboards 行缺失时不重建，保留“无法准确还原”提示；数据实际变化才写回，并在真正刷新时记录 refreshed_at，看板文案变为“学习数据已跟随 <时间> 的获取刷新”。
- 刷新成功时把最新批次的 campaigns.created_at 更新为该次获取时间（取该批学员的 last_sync_at 最大值）：批次下拉标签、详情标题、反馈列日期、画像历史反馈都读到同一时间；看板 refreshed_at 与之相同。
- 没有批次、或 learning_source() 为空时不写数据库；重复刷新同一数据不产生写入（批次时间也不漂移）。

## Rationale

最新批次的用途是“现在要催谁”，必须反映最近一次获取；历史批次是反馈与发送的证据，必须冻结。分开之后，工作台表格、看板与刚获取的数据一致，「获取数据」按钮不再有歧义，同时保留 ADR-004 对历史证据的保护。

## Consequences

- 获取后最新批次的欠交人数、「本次催办」范围、看板分母与比率都会变化。发送前的预览必须重新生成：sending_store.plan 会把 courses/homework/missing_total/completed_* 放进计划比较，学习数据变化后旧预览自动失效。
- 成员不随获取增删：新学员、退课学员仍由「新建催办」纳入新批次（ADR-004 不变）。
- 单侧或缺失获取会把最新批次相应的学习列改成“未获取”，属于规则内的可见变化；需要固定证据时应先建新批次或导出。
- 批次时间会被最后一次刷新改写，创建时间不再单独保留；批次编号与按 id 的排序不变，历史批次的时间不受影响。
- 不得把刷新扩展到历史批次；refresh_latest_learning 必须继续只针对 max(id)。

## Rejected / Failed Approaches

- 只补 UI 提示、保持全冻结（选项 1）：未满足用户要求，未采用。
- 历史批次跟随刷新：会改写已登记的反馈与发送依据，未采用。
- 刷新时同步重算 campaign_students.message 文案：会绕过 ADR-003 的“参数/消息变化必须废弃预览”，未采用。
- 清空本次未获取学员的学习列以“完全等于新建催办结果”：会让一次缺失获取丢掉已取得的数据，未采用。

## Related Areas

app/campaigns.py、app/workflow.py、app/backend.py、app/dashboard.py、app/sending_store.py；tests/test_latest_batch_refresh.py、tests/test_roster_preview.py、tests/test_separated_modules.py、tests/smoke_editor_identity.py；ADR-003、ADR-004。
