# ADR-005: 班期对应关系与作业课程自动绑定

## Status

Accepted。2026-09-29 根据用户需求与本 Session 实现整理。

## Context

用户反馈两点：①重启程序后「班期对应关系」里第二个作业平台的班期/班级不显示，需要重新「获取作业班级」才能确认；②设置页要求确认「课程 ID」在本项目实际应用到的部分，没有用到就删除。

调查结果：作业平台 `/api/admin/classes` 返回的 `primary_course_ids` 在实际账号下每个班级只有一个课程；该课程 ID 会随绑定写入本地库，并在采集时传给 `/api/admin/achievement-record-exports` 导出达标表。因此课程 ID 有实际用途，但界面上让用户“选择”课程没有选择余地。

## Options Considered

1. 保留课程下拉框，仅修复班级列表重启后不显示。
2. 彻底删除课程 ID（不保存也不传给接口）。
3. 去掉课程下拉框，由平台主课程自动写入绑定；平台返回多个课程时才显示选择框。

方案 2 会改变发送给作业平台接口的参数，缺少可验证依据，未采用。

## Decision

采用方案 3。`SettingsModule.saveBinding(term_id, class_id, course_id=0)`：`course_id` 为 0 时取该班级 `course_ids` 的第一个（平台主课程），显式传入时仍校验必须属于该班级；平台未返回课程时拒绝确认并提示重新获取。

作业平台班级目录按作业账号缓存在主库 `settings.homework_classes`（`{"admin": ..., "classes": [...]}`），启动时载入；换账号后不沿用上一个账号的目录。打开设置页或切换追光鲸鱼班期时，用 `homework_bindings` 带出已确认的作业班级。

## Rationale

保留接口需要的课程 ID，同时消除没有选择余地的交互；持久化班级目录让重启后仍能直接显示并核对对应关系，不必先联网获取。

## Consequences

- 平台课程变化后必须重新「获取作业班级」才能刷新缓存与课程；未刷新时确认会提示平台未返回课程或课程不属于该班级。
- 采集前的 `AcquisitionTask('learning')` 仍会校验绑定的课程仍在平台返回的 `course_ids` 中，保持原有防错。
- 更换作业平台账号后班级目录为空，需要重新获取；旧的 `homework_bindings` 记录保留，重新获取后仍可带出。

## Rejected / Failed Approaches

未删除 `homework_bindings.course_id` 列，避免改变已有数据库结构与采集参数。

## Related Areas

qml/SettingsModule.qml、qml/AccountSettingsCard.qml、qml/PageWheelScroll.qml；app/settings_module.py；tests/test_settings.py、tests/smoke_settings_ui.py。
