# ADR-003: 群发参数自动保存与显式发送边界

## Status

Accepted。2026-09-29 根据本 Session 的交互调整整理。

## Context

用户反馈消息编辑、批量修改和预览发送不顺手，明确要求参数移到左侧，删除保存设置/撤销修改按钮，自动保存，只保留设置标题旁一个“预览并发送”入口。

## Options Considered

本 Session 先存在显式保存/撤销和额外预览入口，随后用户要求改为自动保存及单入口。没有关于其他自动发送方案的可靠讨论记录。

## Decision

参数在左侧常驻显示，600ms 防抖保存；切换名单、预览和相关关闭流程处理未完成保存。后端以 list_id 拒绝陈旧设置写入。内容/参数变化清空预览确认，预览窗口显式开始才启动队列。

消息支持逐人、逐格及整列编辑；批量修改默认保留个人修改，受保护发送状态不可覆盖。预览按人员显示有序文字/文件，可返回编辑。

## Rationale

降低重复操作，同时保留“保存配置”和“执行发送”的明确边界。自动保存不意味着旧预览仍代表当前内容。

## Consequences

新增参数、编辑或名单切换路径都必须检查保存归属与预览失效。保留发送前/每人开始的验证，以及文件变更检查、F11、尝试持久化与不确定结果保护。不可为简化交互而把参数保存连到 start。

## Rejected / Failed Approaches

显式保存/撤销按钮和重复预览入口是被用户替换的交互，不是无效业务数据。没有证据表明本次发生过真实误发；自动测试只使用模拟驱动。

## Related Areas

qml/GroupCenter.qml、RecipientMessages.qml、Main.qml；app/group_center.py、group_dispatch.py、message_content.py；tests/test_group_interaction.py、smoke_group_interaction.py、smoke_profile_group.py。
