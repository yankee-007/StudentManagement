# Project Context

核对日期：2026-09-29。当前事实以磁盘代码为准。运行方式见 [README](README.md)，按任务查阅 [架构](docs/architecture.md) 与 [ADR 索引](docs/decisions/README.md)。

## 1. 项目目标

Windows 本地桌面工具，供班级管理者获取学员和学习数据、维护画像、建立催办快照、登记反馈，并将人员/消息送入独立群发中心。不是 Web 服务，不自动读取聊天反馈。

## 2. 技术栈

Python、PySide6/Qt Quick QML（Fusion）、SQLite；requests/BeautifulSoup/lxml 采集解析，openpyxl 处理 XLSX，pycryptodome 支持平台协议，keyring 保存密码。企微自动化依赖 Windows、PyAutoGUI 和 pywin32，不使用 OCR。依赖范围以 requirements.txt 为准。

## 3. 当前核心功能

- 班期学员：平台班期/课程/名单缓存、缺号补位、同步班级身份。
- 学员画像：基础及额外字段、自动保存、按班字段管理、跨班只读总览、联系人打开和聊天跟随浮窗。
- 催办工作台：学习采集、全班批次快照、画像式列筛选、反馈/草稿/免催、当前批次浮窗、四列学习看板及全班 XLSX 导出。
- 名单生成：按当前筛选和排序配置文字/文件；工作台也可仅生成人员名单。
- 群发中心：独立名单、多条文字/文件、逐人/整列编辑、左侧参数自动保存、预览与显式启动、暂停/继续/结果核实。
- 设置：两平台账号、登录验证、班期与作业班级/课程绑定。

## 4. 核心模块

| 位置 | 职责 |
| --- | --- |
| main.py、qml/Main.qml | QApplication、上下文注入、窗口与五个模块入口 |
| app/backend.py | QObject 组合入口、采集协调与日期刷新 |
| app/workflow.py、campaigns.py、dashboard.py | 工作台状态、批次/反馈存储、看板计算 |
| app/profile_module.py、profile_storage.py、repository.py | 画像展示/编辑、字段/免催、关联查询 |
| app/term_module.py、term_roster.py、roster_sync.py | 班期缓存、补位与每班同步 |
| app/acquisition/、importer.py、learning_store.py | 网络任务、两平台数据合并/校验、学习结果 |
| app/group_center.py、group_dispatch.py、message_content.py | 群发界面状态、独立名单/队列、有序消息与变量 |
| app/send_controller.py、sending_store.py、wecom_sender.py | 发送线程/F11、旧来源保护/回写、桌面驱动 |
| app/*companion.py、contact_opener.py | 独立浮窗学员状态及打开企微联系人 |
| app/qt_models.py、qml/、tests/ | 表格模型、界面组件、单元及真实 QML 冒烟验证 |

## 5. 核心业务规则

- 班级数据库隔离；身份由班期名单关联。补位进入画像/快照，但不是反馈或名单生成对象。画像全部班级视图只读。
- 新建催办先验证本班全部在读真实学员的两平台数据和姓名；缺失阻断建批。单独获取允许保留单侧数据，未知 U 不等于完成。
- 最新批次学习数据（欠交、合计、看板）与批次时间跟随每次刷新，成员不随之增删；历史批次学习数据与时间固定且只读。最新批次身份/微信/免催可关联当前资料。以往反馈只取更早批次。见 ADR-006。
- 反馈不依赖发送成功；批量未回复仅用于“本次催办/待反馈”当前可见人员，已有任何反馈或非空草稿必须跳过。
- 有效免催包含截止当天。“本次催办”要求有欠交、微信为“是”、符合学籍/免催资格；全班快照不据此删人。
- 新生成名单是当前筛选人员的独立名单，不额外套用催办资格、不联动旧发送状态。重建属于新名单，不能认为跨名单自动去重。旧来源名单保留原保护链，见 ADR-001。
- 画像与工作台的筛选是冻结结果集：应用筛选后修改字段、登记反馈、草稿、免催、发送回写、切换模块都不会把行移出表格，只标记为“已不符合当前筛选”；搜索/视图切换/列筛选/切班切批/刷新数据/重新应用才重算，排序只重排不重判。选择必须连续：重算后若原选中行被筛掉，高光落到原顺序中的下一条（table_query.next_cursor），不得回落到第一行；工具条显示“正在处理 第 i / n 条 · 姓名”。名单生成、导出画像、批量未回复只取真正匹配的人，见 ADR-007。
- 工作台字段设置按班保存：姓名不可隐藏、学号默认隐藏；显隐/顺序影响表格、详情、浮窗。导出字段设置独立并记忆，导出所选批次全班，按学号升序。
- 看板分母为批次内在读非补位学员，含仍在读的免催学员；累计率要求第 1～N 节全部完成，差值为累计完课率减累计作业率。UI 仅展示节次、两项累计率及差值。

## 6. 核心数据流

```text
班期接口 → 缓存 → 每班名单/身份 → 画像
两平台学习接口 → 合并校验 → 当前学习结果 → 最新批次快照刷新（历史批次冻结）/看板
QML 反馈/草稿/免催 → 身份校验 → 每班 SQLite → 通知与界面刷新
当前筛选人员 + 可选消息 → 独立群发库 → 预览 → 显式开始 → 企微 → 尝试/结果
```

Python ↔ QML 通过 Backend 暴露的 QObject、Property/Signal/Slot 和 DictTableModel 通信，没有 HTTP 桥接。

## 7. 数据与持久化

默认 Qt 本地应用目录中有 followup.db；原主库承担班级登记/平台设置/班期缓存，新班一般用同目录 class_term_<termId>.db，已有班沿用旧路径。group_messaging.db 独立保存群发。密码由 keyring 保存，登录缓存位于 platform_sessions/。作业平台班级目录按作业账号缓存在主库 settings.homework_classes，班期与作业班级的对应关系存 homework_bindings（课程 ID 由平台主课程自动写入）。

每班主要表：class_roster、profiles、额外字段定义/值、exemptions、reminder_data、campaigns/campaign_students、campaign_feedback/campaign_drafts/campaign_dashboards。students 等兼容表仍保留。构造 Database 会迁移，不是只读探针；变更格式须检查旧库兼容。

## 8. 重要系统约束

不自动解析聊天或推断请假；采集不能覆盖人工资料/历史反馈。名单内重名不能唯一定位企微，创建/启动会校验。参数或消息变化必须废弃预览；不确定发送结果禁止自动重试。附件保存路径而非副本，移动文件可能导致校验失败。

## 9. 易回归区域

- 编辑身份、输入法组合输入、同学员外部更新及 Repeater/Model 重建，见 ADR-002。
- 班级/批次切换、浮窗待保存内容、异步采集返回时的上下文检查。
- 筛选范围与生成/批量反馈范围；全班导出不能误跟随筛选。冻结结果集下 _model.rows 可能含过期行，业务范围必须走 _scope_rows()。
- 新独立名单与旧来源名单的不同资格、回写和重试路径。
- 预览失效、个人消息覆盖、受保护发送状态、F11 与关闭生命周期。
- 累计与单节统计、缺失与未开课状态、历史快照与当前身份的边界。
- 最新批次跟随获取刷新与历史批次冻结的边界；本次未返回的学员保留原数据；刷新不得改动反馈、草稿、免催和发送状态。

## 10. 当前已知问题 / 技术债

- LegacyMain.qml、Backend 旧接口及 Workflow.sender 等兼容实现仍在；不是当前工作台入口，未经调用/数据兼容调查不要删除。
- 名单长期缓存与设置页的作业班级目录都可能落后于平台变化，需手动刷新；是否增加刷新提醒待产品确认，不能自行改成每次联网。
- Windows 企微兼容性、真实平台端到端对账与长时间稳定性尚未由本轮自动测试证明。
- test_profiles 的本机样例文件缺失会跳过一项测试，不代表画像导入全覆盖。
- 旧业务审计 A01–A07 已修复，不是现存缺陷清单。请假分母的早期口径分歧未发现新的最终确认，当前代码/测试包含在读免催者；修改口径前再确认。
- tests/smoke_term_ui.py 与 tests/smoke_profile_ui.py 仍断言已不存在的 showStudentId / showStudentIdToggle（HEAD 与当前 qml/ 均无该属性），会在这两步失败；属旧 UI 遗留的过期断言，与催办/刷新无关，本次未修。smoke_profile_ui 还依赖本机 C:/Users/AAA/Desktop/学员画像表.xlsx。
- QML 初始化/销毁瞬间会打印 Cannot read property … of null（backend 尚未注入或已销毁时绑定求值），与既有行为一致，不影响加载，未顺手清理。
- 设置页 ComboBox 的滚轮守卫（PageWheelScroll）只接在设置页三个下拉框上；其它页面需要滚动时复用同一组件，未做全局改造。
- 筛选面板（ProfileFilterDialog）的选项只渲染“当前还有匹配行”的值：某个已勾选值在数据变化后 0 匹配时，该条目不再出现在面板里，但规则仍在生效（表头带标记、表格可能为 0 行），只能靠面板「重置」或「清除筛选」自救。ADR-007 未处理这一条。
- 工作台隐藏列（「管理字段」取消勾选，列宽为 0）仍继续参与筛选，界面没有提示；画像表格相反，列被隐藏/删除时会清掉该列筛选。两个表格的列生命周期仍不一致。

## 11. 当前项目状态

上述流程已实现。最近功能轮完整回归运行 109 项、1 项样例缺失跳过，其余通过，随后新增工作台 UI wrapper 与浮窗检查单独通过。这是历史验证记录，不是新 Session 的保证；当前命令见 README。

2026-09-29 依用户决定实施 ADR-006：最新批次的学习列、看板与批次时间跟随每次刷新，历史批次继续冻结；「获取数据」改名「刷新数据」并移到「新建催办」左侧；新增 tests/test_latest_batch_refresh.py。最终完整回归 124 项通过、1 项样例缺失跳过；QML 冒烟 workbench_revision / editor_identity / floating_windows 通过，term_ui 因上述过期断言失败。离屏加载真实 Main.qml 的顺序验证（建批 → 刷新 → 建第二批 → 再刷新）确认最新批次的表格/看板/时间随新数据更新、旧批次数据与时间不变、刷新按钮在历史批次隐藏，且无 QML 错误。同为历史记录，不代表后续 Session。

2026-09-30 依用户确认实施 ADR-007（筛选结果集冻结）：画像与工作台的列筛选/搜索/视图结果在应用时冻结，字段自动保存、记录反馈、草稿、免催、备注、发送状态回写只更新数据并把该行标记为“已不符合当前筛选”（staleRow 角色 + 淡橙行），搜索/视图切换/列筛选/切班切批/刷新数据/「重新应用筛选」才重算，表头排序只重排不重判；名单生成、导出画像、批量未回复只取真正匹配的行（_scope_rows）。新增 tests/test_filter_freeze.py、tests/smoke_filter_freeze.py，改写 tests/test_profile_group_flow.py 中原来的“编辑后立即重算”断言。随后按用户反馈补齐核心诉求（处理顺序不能被切换页面打断）：Main.qml 的 switchModule 改走 ProfileModule.activate()/Workflow.activate()，只重读数据不重新筛选；新增 table_query.next_cursor 保证重新筛选后被筛掉的当前行由“下一条”接替而不是回到队首；工具条显示“正在处理 第 i / n 条 · 姓名”。完整回归 134 项通过、1 项样例缺失跳过；QML 冒烟 profile_group / workbench_revision / editor_identity / floating_windows / filter_freeze 全部通过，1280×820 与 1000×700 截图确认过期行、游标提示可读且无 QML 警告。历史记录，不代表后续 Session。

Git 初始提交为 ce327fd（2026-09-29），不能据此还原更早开发过程。后续按 AGENTS 的单 Agent 与按需阅读规则工作。
