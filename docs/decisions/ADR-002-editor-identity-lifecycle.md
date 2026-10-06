# ADR-002: 编辑身份与稳定 QML 委托

## Status

Accepted。2026-09-29 整理。

## Context

画像、催办主表和浮窗都能自动保存；切班、切批次、排序筛选、日历返回和输入法回调可能发生在不同时间。仅凭当前行号或当前选择写入，会把旧编辑内容归到新学员。新增字段排序又使反馈编辑器进入动态委托。

## Options Considered

本轮曾使用由当前行值构造的详情字段数组；Review 指出每次保存通知都可能重建 Repeater 编辑器。最终改为稳定布局定义与单独值绑定。没有可靠记录可还原更早其他备选实现。

## Decision

- 编辑携带路径/学员身份；工作台还包含 batch_id。Slot 保存前校验 key、可编辑性和真实学员，日历返回后再次校验。
- 画像浮窗连续文本输入和下拉选择短暂合并后保存；切换联系人或班级、关闭浮窗、字段布局或外部值刷新前先提交待保存内容。日期和回车仍立即保存，待保存内容始终绑定原画像身份。
- 催办浮窗独立于主表选择，仅最新批次；上下文改变清空旧学员。2026-10-06 用户确认主卡片与浮窗改为单框自动保存、可修改、清空恢复待反馈，均不推进选择。连续输入按捕获身份合并 500ms 后保存，切换和关闭前提交待保存内容；旧 submit 兼容接口仍可推进，当前卡片不再调用。
- CampaignDetail 只在可见字段 key/label/顺序签名变化时重建字段模型，值独立绑定；加载草稿设 guard，兼顾输入法组合状态，不用通知循环覆盖输入。
- UI 回归检查实际视觉树、保存归属、同 key 更新与跨上下文拒绝。

## Rationale

身份与显示位置分离；持久化通知不能破坏编辑生命周期。字段管理应影响顺序/显隐，而不是让每个按键都重新创建输入框。

## Consequences

新增编辑入口必须沿用身份契约，不能绕过 slot 调用直接写库。注意 selectionChanged/changed 的消费者；只测数据库方法不足以验证焦点与输入法。字段真正改变后允许委托重建，测试应重新查找界面对象。

## Rejected / Failed Approaches

本轮真实 UI 测试使用 QObject.findChild 查找动态反馈框失败；Repeater 的视觉子节点不一定是 QObject 后代，改用 QQuickItem.childItems 遍历并保留原保存断言。该失败是测试定位方式问题，不能通过删除身份断言掩盖。

值驱动的整组委托重建风险在 Review 中被发现并规避；不将其夸大为已确认发生的真实用户数据丢失事件。

## Related Areas

qml/CampaignDetail.qml、AutoProfileField.qml；app/workflow.py、profile_module.py、campaign_companion.py、profile_companion.py、qt_models.py；tests/smoke_editor_identity.py、smoke_workbench_revision.py、test_campaign_companion.py。
