# 设置页 UI 规范

状态：**已实施**（2026-09-29；班期绑定流程于2026-10-08更新）。实现文件：qml/SettingsModule.qml、qml/SettingsBindingRow.qml、qml/SettingsCard.qml、qml/AccountSettingsCard.qml、qml/SettingsWheelGuard.qml。
参考条目来源为公开设计系统与开源实现的检索结果；本机 web_fetch 被网络策略阻止（域名解析到非公网 IP），未逐页阅读原文，按公开条目与仓库名借鉴做法。

## 1. 参考依据

| 参考 | 借用的做法 | 落地位置 |
| --- | --- | --- |
| VS Code Settings 编辑器架构 | 设置按「分组 + 条目行（标题/说明/控件）」组织 | 卡片 = 标题/说明/内容/底部操作 |
| Material Design · Settings 模式 | 按语义分组；说明文字紧跟控件 | 卡片说明、课程说明就近显示 |
| Ant Design Pro · 布局 | 主内容单一阅读列，页面只有一个滚动条 | Flickable + 右侧常驻滚动条 |
| Supabase Design System · Forms patterns | 标签与控件同基线、标签列固定宽、帮助文字贴所属控件 | 表单行标签列 96px |
| n8n 实例设置组件 | 卡片统一为 标题 / 说明 / 内容 / 底部操作（右对齐） | qml/SettingsCard.qml |
| Untitled UI · Settings pages | 宽屏账号类设置两列卡片；保存状态用行内状态文字 | 账号卡片并排 + 状态胶囊 |
| bitcoin-core/gui-qml PR #872 | QML 设置页抽成可复用表单/卡片组件 | 抽出卡片、账号卡片、滚轮守卫三个组件 |

## 2. 已实施的结构（方案3：单列 + 卡片骨架）

1. 页面头：`设置` 标题 + 一句说明 + 右侧「刷新状态」。
2. 全局提示行：只保留一条（保存结果、作业班级获取结果、绑定结果共用）。
3. 平台账号：`卡期 ≥840px 时两张账号卡片并排且等高`，否则上下堆叠；卡片内为「账号 / 原始密码」两行表单，底部操作行放「验证登录 / 保存」，状态胶囊在右上角。
4. 班期对应关系：以完课平台缓存班期为固定行，卡片顶部「刷新完课班期／获取作业班级」。每行显示固定班期、保存状态与作业班级下拉框，包含「未绑定（留空）」；选择立即保存，无确认按钮。宽屏左右对应，窄屏纵向排列。单课程自动对应，多课程显示下拉并恢复已保存课程；目录暂缺时仍显示原绑定名称，保存失败恢复原选择并在行内提示。
5. 凭据说明：密码保存位置、换账号要求、作业班级目录缓存说明。

未采用：左侧分区导航（方案1）。设置项变多时再评估。

## 3. 设计令牌（沿用现有配色，未新增色板）

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| 页面底色 | #f5f7fb | 窗口背景 |
| 卡片 | #ffffff + 1px #e1e6ef，圆角 10，内边距 16 | 分区卡片 |
| 主 / 次 / 说明文字 | #17213a / #475467 / #667085 与 #98a2b3 | 标题 / 标签 / 说明 |
| 主按钮 | 底 #e9efff，框 #b9c8f5，字 #1d3ecf | 保存账号 |
| 输入 / 下拉 | 高 28，框 #c9d0dc，圆角 6 | 沿用既有控件尺寸 |
| 成功 / 警告 | #027a48 / #b54708 | 已绑定、已保存 / 尚未保存 |
| 标签列宽 | 96px，行间距 10px | 表单对齐基准 |
| 字号 | 标题 19，卡片标题 15，正文 12，说明 11 | 沿用既有比例 |

## 4. 组件与约束

| 组件 | 职责 | 注意 |
| --- | --- | --- |
| qml/SettingsCard.qml | 卡片骨架；`content` / `footer` / `headerRight` 三个内容槽 | 内容用 ColumnLayout 管理，卡片高度由 `layout.implicitHeight` 决定；不要改回 `childrenRect` 计算（对布局子项不可靠） |
| qml/AccountSettingsCard.qml | 单个平台账号卡片 | 依赖 SettingsCard 的 `tag/tagColor/tagBackground` |
| qml/SettingsBindingRow.qml | 一个固定完课班期对应可选作业班级 | 仅用户激活选项时保存；列表与绑定使用独立通知，避免账号状态变化重建行；保存失败保留旧绑定 |
| qml/SettingsWheelGuard.qml | ComboBox 滚轮守卫：Qt 6 的 ComboBox 会无条件 accept 滚轮，导致页面滚不动 | 用显式宽高而非 anchors（可能被放进 Layout）；页面里每个 ComboBox 都要挂一个 |

## 5. 相关文档

- 实现注意与踩坑记录：[qml-settings-pitfalls.md](qml-settings-pitfalls.md)
- 页面基线截图：docs/ui/settings-page.jpg

## 6. 验证

当前逐行绑定流程的定向回归与真实 QML 证据见 [TASK-20261008-06191dab05cf](tasks/TASK-20261008-06191dab05cf-term-homework-bindings.md)。以下为2026-09-29页面基线记录，不代表本次全库回归结果。

- `python -m unittest discover -s tests`：134 项通过，1 项因本机样例文件缺失跳过。
- `QT_QPA_PLATFORM=offscreen python -B -m tests.smoke_settings_ui`：通过（并排/堆叠、卡片等高、滚轮滚动、滚轮不误改下拉选项、重启后带出对应关系、单课程不显示选择框）。
- 原生渲染截图：1280×800 内容高 686px（可用 752px，一屏看全）；760×700 卡片上下堆叠。
- 基线效果图：docs/ui/settings-page.jpg
