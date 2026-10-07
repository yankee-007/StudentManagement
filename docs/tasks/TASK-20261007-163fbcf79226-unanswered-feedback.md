# TASK-20261007-163fbcf79226：未接听反馈的回复状态修正

- Identity：TASK-20261007-163fbcf79226；awaiting_acceptance；2026-10-07T17:00:58+08:00。
- Requirement：用户指出填写「未接听电话」自动判为已回复，使可跟进人数不准确。修复新保存与已有记录的显示/统计；保留反馈原文、自动保存、编辑与历史保护。
- Baseline：main / 74f83c8，工作区干净；当前Agent单独写入。关联TASK-20261007-19754d1a822f及反馈自动保存任务TASK-20261006-a834b72e9c51。
- Findings：submit/save_feedback固定写kind=reply；rows仅判断kind；Workflow可跟进谓词还把待反馈计入。默认快捷项包含未接听电话，现有「非空计已回复」规则与本次用户澄清冲突。
- Plan：集中判定明确的「未接听电话」「未回复」记录；新保存写正确kind，读取已有误记kind时纠正展示而不迁移正式数据库；未接听内容仍保留在编辑框，和明确回复并存时按有回复计算。看板排除待反馈，预览复用相同判定。
- Verification计划（已执行见下）：用临时数据库覆盖新/旧记录、合并快捷反馈、清空、历史只读与可跟进统计，并做真实QML离屏检查。
- 初始Snapshot：正式实现尚未开始；不连接平台/企微、不写正式库、不推送。
- Completion：针对性回归、界面证据及文档更新后等待用户真实使用验收。

- Implementation：feedback_status共享判定；CampaignStore新保存使用正确kind、旧记录读时判定，反馈原文仍完整可编辑（包括未回复标记）。Workflow可跟进只计已回复，自动保存成功立即重算看板。QML说明更新；第16次预览注册同一SQLite只读判定函数，排除旧误记的未接听记录。不批量迁移正式数据。
- Findings：新增测试暴露自动保存后看板未实时重算，已修复。测试初始画像学籍为空造成分母0，修正新用例的在读夹具后验证；未通过修改业务期望隐藏失败。
- Verification：正确项目Python环境通过27个相关单元测试（反馈自动保存、campaigns、工作台与浮窗），含新/旧未接听、负项组合、清空、回复追加、编辑原文、历史保护与实时统计。QML offscreen workbench与dashboard_completion通过，工作台真实输入确认未接听→未回复、原文保留、回复追加→已回复；100次输入只落库一次，编辑焦点保持。截图output/feedback-fix/unanswered.png已查看，虚构数据、中文可读。预览内存库导出测试及完整Playwright交互检查通过，第16次已重新导出。
- Limitations：PATH的Python缺Crypto，切换项目已有环境后通过；未安装依赖。smoke_editor_identity在画像初始化微信断言失败，使用HEAD独立临时归档运行同样失败，确认是既有失败；其后续检查未完成。不修无关画像问题，不运行正式应用或平台/企微端到端，不声称全仓回归通过。
- Delivery：状态awaiting_acceptance，待用户重启正式工具验收；本地成果按策略提交，不推送。正式独立学习概览仍未落地，本次正式修改只修复反馈判定与联动。
