# 群发消息附件预览

- Identity: TASK-20261010-e6f409a58d72；awaiting_acceptance；2026-10-10 18:55 +08:00。
- Requirement: 群发中心的图片直接展示内容，控制缩放；其他文件参考用户截图展示文件名、大小及类型图标。覆盖消息模板、个人消息、发送预览及表格查看；保留现有编辑、排序、保存和显式发送边界。
- Baseline: main，5a1ff06；开始时 staged/unstaged/untracked 均为空。
- Workspace: 当前仓库 main，单 Agent 单写入者，沿用普通串行开发；不创建隔离分支，不操作正式数据库或企微。
- Snapshot: 实现和自审完成。新增 qml/MessageAttachment.qml 及 GroupCenter.messageFileInfo，只读文件元信息，模板/个人/发送/表格预览统一展示；图片异步加载，保持比例、限制尺寸并不放大小图，缩短聊天区域时进一步缩小。文件卡片展示最多两行文件名、大小及类型图标；失效/无法解码时降级提示。保留编辑/排序/删除与显式发送边界，无持久化格式修改。同路径文件重载更新元信息，并以修改时间/大小刷新图片缓存。README、PROJECT_CONTEXT 与架构已同步。
- Findings: 原聊天附件是名称文字，发送预览是完整路径；表格固定 40px 行高并与姓名同步，需用紧凑缩略图/文件图标保留同步。图片等比缩小、不放大小图，常规预览上限 240×180。
- Verification: Python 3.11.5 / PySide6 6.8.3、offscreen；47项相关单元通过（test_group_interaction、test_message_content、test_profile_group_flow、test_group_center、test_real_sending）。smoke_group_attachments、smoke_group_message_input、smoke_group_list_view、smoke_group_interaction 通过；覆盖真实文件替换、保存/草稿/IME/只读保护、个人与发送/表格预览、40px同步行高、含中文/空格/%/#的路径、图片缓存重载、EXIF方向、横竖/小图、损坏/失效文件、1280×960/720×480及亮暗。截图在忽略目录 output/group-attachments，中文及布局已目视检查。故意截断的PNG会产生预期libpng诊断，界面回退卡片已验证。全部使用临时库、虚构人员及生成的测试附件，无真实登录或发送。
- Handoff / Closure: 实现、文档和测试在main按本Task ID的本地提交恢复；无远端上传。用户重启后查看文件卡片风格、图片大小与表格缩略图，主观接受待确认，无回复不代表已验收。其余历史待验收任务保留。
