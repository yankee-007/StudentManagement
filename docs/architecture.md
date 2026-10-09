# 当前架构

核对日期：2026-09-29。模块导航见 [项目概览](../PROJECT_CONTEXT.md)，设计原因见 [ADR 索引](decisions/README.md)。

## 入口与边界

main.py 创建 QApplication（原生文件对话框需要 QWidget 支持），设置 Fusion/字体/应用名称，将 Backend 和 studentModel 注入 QQmlApplicationEngine，加载 qml/Main.qml。Main 切换今日工作台、催办、学习概览、画像、班期学员、设置、群发中心、备注批改、未进直播间，并管理独立浮窗。今日工作台接入于2026-10-08，学习概览接入于2026-10-07。

```text
Main.qml / 模块 QML / 浮窗
       ↕ Property、Signal、Slot；表格角色
Backend（组合入口，持有当前 db/repo）
 ├─ Workflow ─ CampaignStore ─ 每班 SQLite
 ├─ LearningOverview ─ SQLite mode=ro ─ 每班批次快照/人工标记
 ├─ ProfileModule ─ StudentRepository / profile_storage / ProfileWechatVerifier
 ├─ TermModule ─ TermRosterStore ─ 原主库缓存
 ├─ SettingsModule ─ 原主库设置 / keyring
 ├─ AiCampaignModule ─ GenerationWorker / ai_campaign ─ 配置的 AI 服务
 │                     └─ 独立群发名单（content + learning_data，沿用 GroupStore）
 ├─ ProfileCompanion、CampaignCompanion、ContactOpener
 ├─ LiveAbsence ─ live_storage ─ 每班 SQLite（live_reminders）
 └─ GroupCenter ─ GroupStore ─ group_messaging.db
                     ↓ plan / claim / finish
              SendWorker + F11Hotkey → WeComSender

Backend / TermModule / SettingsModule / LiveAbsence → AcquisitionTask（QThread）
   → completion / homework 客户端 → 合并/校验 → 导入/缓存
```

这些 QObject 同时承担界面状态和业务协调，没有统一独立的 Service 层。Backend 保留旧表格接口；当前工作台主要使用 backend.workflow.tableModel。

AI 催交于2026-10-09接入 Backend.aiCampaign。设置卡片保存非密参数至主registry、API Key至keyring；催办生成窗口冻结当前真正匹配的学员／欠账，按本批dashboard.opened课程节次选只读模板（可手选）。GenerationWorker运行JSON请求、分批并发及失败退避重试，创建时复核身份和数据版本。结果直接写独立名单content，learning_data保留失败项重试所需的诊断／模板索引／错误；不会保存反馈记忆或改动发送协议。重试回写仅填仍为空且未受发送保护的失败项，个人编辑优先。见ADR-015；本地32次催交话术库当前为未跟踪运行依赖。

## Python ↔ QML 与状态

- QML 展示层共用 UiTheme、UiButton、UiTextField、UiComboBox、UiPanel；本地 qmldir 注册主题单例。左侧导航调用原 switchModule，群发中心位于最后。班期学员／画像／催办等共用顶部 classSelector，班期页通过 Workflow.selectClass → TermModule.alignTerm/activate 跟随当前班级；activate 和班期目录刷新均按当前班级 term_id 选择缓存，未关联平台的旧导入班级显示空名单及选择提示，避免显示另一班期的缓存。调试重启保留原保护条件。工作台／画像窄窗口切换列表与详情的可见性，不销毁编辑组件、不改保存和业务接口。群发按群发名单／模板／发送配置三栏排列（消息模板居中），姓名仅展示前缀＋姓名，模板默认纵向气泡，标题右侧切换逐人消息表格（保留标题与说明，两种模式固定相同 padding／表头高度）；TableView 使用 GroupCenter 的 pendingMessageModel／sentMessageModel，和姓名模型共用同源人员顺序及 recordKey，以 40px 行高、相同视口和 bottomMargin 按 contentY−originY 双向联动。字段列最小 220px，正文省略且不附加标号，消息1／消息2…表头同步 contentX；长文悬停打开可滚动只读 Popup，字段表头在弹窗复用原 MessageChatEditor，切换先检查草稿；双击姓名或消息行打开个人消息弹窗（已移除「查看个人消息」按钮）。左侧「群发名单」标题后直接配置前缀，待处理／已发送采用下划线页签；ListView 行高 40px、统一底色，选中行浅色背景与左侧细标记，行间 1px 横线缩进 12px 并降低透明度、行距 0，页脚为 TextArea 添加单元格与「＋」按钮（单个姓名回车或点击按钮提交、多行粘贴自动按行加入；0ms Timer 等待粘贴结束，组合输入不提交，切换名单取消待处理输入；成功后清空保留焦点并滚动到底部，全为重复或失败时保留输入），选择用 recordKey 集合维护，支持 Ctrl 增删、Shift 连选、Ctrl+C 复制、Ctrl+V 粘贴加入与 Delete 删除，剪贴板经隐藏 TextEdit 桥接系统剪贴板。MessageChatEditor 复用于公共模板和个人消息，支持 Enter 加入、Shift＋Enter 换行、组合输入保护、双击气泡内联编辑并以回车或点击外部提交、文件及顺序；文字气泡按最宽一行实测宽度自适应并留 2 像素余量，能放进列宽的消息以 NoWrap 渲染，设备像素取整不再把末字挤到下一行，只有整条消息超过列宽上限才换行，换行时不拆开 `{变量}` 占位符；聊天模式的消息线程与姓名列表独立滚动，表格模式的纵向滚动同步、字段可横向查看，长消息内联编辑单独滚动，当前编辑委托在移出视口时保留。发送参数在右侧自动保存；粘贴等待默认 0.5 秒，关闭回车发送时单条发送禁用并置灰。
- SettingsModule.appearanceMode 读取主 registry 的 settings.appearance_mode（light/dark，旧库或无效值默认 light），保存成功后只发 appearanceChanged，不广播账号/绑定 changed。UiTheme 绑定该属性，统一语义颜色与 Fusion Palette；主窗口和两个独立 Window 共享此 Palette。OverviewChart 将既有业务颜色映射为主题颜色并延迟重绘，保留当前选择/缩放。Backend 日期弹窗和 LeaveCalendar 使用对应 QWidget Palette，包含自绘日期格与星期标题；文件选择器仍由 Windows 原生界面承载。

- Backend 以常量 QObject Property 暴露模块；QML 使用 QVariantMap/List 读取行、字段、参数，调用 Slot，以 notify signal 更新绑定。
- DictTableModel 是 QAbstractTableModel，角色包括 display、studentId、recordKey、expiredCell、staleRow。set_rows 重置模型，reconcile_rows 用增删移动/数据通知减少委托重建。
- Workflow 的 _rows 是完整批次行，_model.rows 是当前显示集合（冻结结果集，可能含已不符合筛选的过期行），_selected 是主表选择。selectionChanged、queryChanged、changed 不可任意互换。
- 筛选按 ADR-007 冻结：应用筛选时把命中 key 存入 _frozen，值变化只更新数据并写 _filter_stale，只有显式重新筛选（搜索、视图、列筛选、切班/切批、刷新数据、重新应用）才重算；业务取数必须走 _scope_rows()（显示集合去掉过期行），不能直接用 _model.rows。
- 列筛选按字段 key 保存；ProfileFilterDialog 共用于画像和工作台。ProfileFieldOrder 共用卡片拖动、插入间隙索引转换、边缘滚动及按钮排序，ProfileFieldCard 展示字段名、类型／固定备注与显隐；48px卡片／6px间距，ListModel按ID增量移动，间隙及滚动边界计入originY与8px头部。拖动保留源占位，半透明缩窄副本按原抓取点比例定位，动画和移动期间保持指针位置、不限制副本横向位置，画像拖动层高于新增表单。释放前清理手势；画像调用moveFieldAsync，工作台仍调用moveField，字段通知／关闭取消手势。画像管理字段宽窗双栏、窄窗切换新增表单。工作台隐藏列宽为 0，模型仍保留数据列。
- ProfileModule排序只更新字段配置及表格列，复用学员行、冻结筛选、排序键和光标；managedFields在refresh失效，当前班编辑字段复用owner.db与字段缓存。fieldLayoutChanged／editorFieldsChanged定向通知布局和编辑器，原changed／selectionChanged继续转发相应通知；表头用columnKeys判断筛选标记，点击时才计算选项。moveField保留同步契约；UI的moveFieldAsync即时更新布局，单工作线程捕获当时数据库并串行写profile_field_order，40ms定时器收取结果，fieldOrderSaving显示待保存状态。flushFieldOrder在面板关闭、refresh（含切班）、其他字段修改及aboutToQuit时等待写完；最新失败提示并回退已保存布局。resetFieldLayout在同一事务清除本班顺序／显隐设置并显示所有现有额外字段，保留定义、值和删除标记；不改变schema。
- 画像记录身份组合数据库路径/学号；工作台 editorKey 是 JSON [db_path,batch_id,student_id]。名单对话框捕获 recipientKeys，后端检查仍与当前筛选完全一致。
- CampaignDetail 由主界面和催办浮窗共用，反馈为单行 TextField + 点击展开的 Menu，无独立下拉按钮。TapHandler 保留原输入事件；Menu 不抢输入焦点，键入时收起，快捷内容追加到末尾，非空时以「；」分隔。Menu 按上下空间定位，限制高度支持滚动，避免覆盖输入框；捕获 editorKey 防止旧菜单写入新学员。列表底部提供添加选项，默认「答应补课」「未接听电话」，新增选项存于当前班级 settings.campaign_feedback_shortcuts，经专用通知同步，避免广播重建编辑器。字段模型仅在布局签名改变时更新，值单独绑定；反馈保存不能重建编辑器。后端拒绝旧身份 key，工作台集中保存带身份的待保存反馈，连续输入只重启 500ms 定时器，不逐键写库或广播刷新。
- 切班/切班期是同步 Slot：selectClass 会重建班级上下文并刷新名单、批次和画像，实测整班首次切换约 430ms、缓存命中 30–75ms，必须由 WaitingOverlay 覆盖。
- 切换时序：ComboBox 的 onActivated 先 close() 弹出层，再 begin(name, action, largeRoster) 打开 ClassSwitchOverlay；Overlay 只在 hostWindow.frameSwapped（一次真实绘制，含 app/window.update()）后经 Qt.callLater 执行 action，因此耗时刷新不会阻塞 Loading 的首次绘制。最快显示 140ms 防闪烁；窗口不可见时 cancel() 丢弃待执行动作，渲染停摆时 frameTimer 兜底执行，避免动作丢失或 Loading 常驻。
- 长耗时提示必须提前决定：同步刷新会冻结事件循环，定时器只能在刷新结束后才触发，事后补提示必然晚于工作完成。因此由 Workflow.classRosterSize / TermModule.termRosterSize 在切换前读取缓存人数（只读连接，不构造 Database、不触发迁移，结果按班期缓存），≥300 人或未知时首帧即显示“数据较多，加载时间稍长”。
- 切班时同一次统计只取一遍名单：selectClass 把 owner.refresh() 返回的 students 分别传给 reload_batches/reload_rows/live_roster 和 _refresh_statistics。list_students 在 900 人班约 30–45ms，重复调用是切班的主要可消除开销。

- 群发模板捕获list_id与contentRevision；defaultFields由选中名单原始缓存计算。MessageChatEditor 用 sourceIndex 关联原始槽位，新条目为 -1，排序不重编号。每次气泡操作经 saveDefaultRow / GroupStore.save_default_row 同一事务校验并写入可编辑人员内容及模板；成功后在原模型更新修订和槽位，保持滚动与待加入输入，失败保留草稿。内联失败恢复字段旧值及原 dirty 状态，仅保留 editText 供修正；Esc 取消该编辑，已有其他失败操作稿保留，干净稿遇修订变化时重载。未编辑的混合槽位与个人覆盖保持原值，删除槽位同时删除对应个人改动；显式覆盖个人需确认，受保护记录保留。预览/切换/关闭前提交有效内联编辑并检查待加入输入，不能隐式把输入框正文加入模板；直接提交空白或失败稿阻止操作，空白内联稿失焦／外部点击等同 Esc 取消，名单选择器恢复真实选择。气泡操作行保留尺寸，只在悬停／键盘聚焦／菜单展开时显示；输入框通过 GroupCenter.clipboardMessageFiles／messageFiles 读取本地文件 URL，并按 prepare_content 原子验证整批附件，普通文字／网页链接粘贴回退 TextArea，DropArea 只接受 CopyAction，新增附件沿用现有提交及失败稿保护。个人消息使用捕获的名单/人员身份整稿保存，弹窗关闭清理内联状态，待核实动作在个人弹窗中。发送仍由预览窗口显式开始。

## 关键调用链

### 班期、学习数据与快照

1. TermModule 通过 AcquisitionTask 获取班期、课程、名单；TermRosterStore 在原主库缓存，Workflow.sync_terms/roster_sync 同步到各班库。
2. 名单采集固定识别首节课程，与当前查看课程独立；缺失缓存才补取，显式刷新更新已有缓存。取消后拒收结果，等待网络结束/超时，不强杀线程。
3. 新建催办调用 Backend.createCampaign，按作业绑定获取两平台数据；_fetch_succeeded 校验数据库身份、姓名、完整性后导入，再调用 Workflow.createBatch。
4. CampaignStore 保存全班快照和 campaign_dashboards；dashboard.learning_dashboard 在建批时计算（version 3 起同时写入累计完课／作业人数与按完成节数分桶的 completion 分布）。后续获取只刷新最新批次的学习列、看板与批次时间 created_at（refresh_latest_learning，与建批共用 learning_snapshot 推导），最新批次身份可同步；历史批次不重写快照，建下一批前冻结上一批。Workflow.refresh_dashboard 读快照后按所选批次独立人工是标记补算每个桶的「可跟进人数」（历史也可补充标记），不使用反馈状态、不写回学习快照。
5. Workflow 组合反馈/草稿/免催，执行视图、搜索、列条件、排序，再通知模型和选择。

### 反馈、免催与浮窗

- 可跟进状态：CampaignDetail显式未填写/是/否 → Workflow.setFollowupStatus（捕获班级/批次/学员身份） → CampaignStore.set_followup_status → campaign_followup_status。独立于反馈状态，缺少标记为空；未填写操作删除标记记录，保持旧是/否存储约束。历史允许补充此人工标记但不修改原反馈/学习；更新后保留冻结筛选并重算看板。新批次不继承，刷新学习不覆写；表格、字段管理、筛选和导出支持。见ADR-012。

- CampaignDetail → queueFeedbackForSelection → Workflow.queueFeedback/flushFeedback → CampaignStore.save_feedback：校验班级、批次、真实学员，按捕获身份替换本批次反馈并清空旧草稿；非空计已回复，清空恢复待反馈，不推进选择。保存时读取该学员并 reconcile_rows，保留编辑委托和冻结筛选；失焦、切班/批/学员、切模块、关闭时提交待保存内容，失败保留内存内容并阻止班级/批次切换及主窗口关闭。旧 draft/submit 接口保留兼容调用，旧记录与草稿仅在实际编辑后合并持久化。
- markUnreplied → mark_unreplied(batch, visible_ids)：事务中跳过补位、空姓名、已有任何反馈或非空草稿，不检查发送成功。
- setLeave/clearLeave → profile_storage.set_exemption：画像/催办共享免催表；日历返回后复查身份，刷新当前资料但不修改历史快照。
- 两个浮窗是无主窗口从属关系的独立窗口，主窗口最小化时仍可见；主窗口关闭时显式关闭浮窗。浮窗定时读取经进程验证的前台企微独立聊天标题。画像浮窗默认跨已登记班级识别，已保存备注或本班前缀＋姓名优先，唯一姓名兜底；重名时要求下拉指定班级。手动班级按数据库路径固定，只影响浮窗，不调用主界面 selectClass；主界面全部班级视图也不禁用画像浮窗。匹配成功每 2 秒重读，失败每 500ms 重查；按路径缓存仓库，兼容尚无 student_contacts 的班级库。切换/重读前提交待保存编辑，失败保留编辑并阻止切换。催办浮窗仍按当前班级唯一姓名匹配。CampaignCompanion 限最新批次，独立于主表选择；切班/批次清身份。ProfileCompanion 的画像身份格式不同，不能混用 key。
- ContactOpener 使用 ContactOpenTask 打开/验证联系人，不发送消息；与群发互斥，退出等待任务结束。画像和催办填写卡片的姓名右侧提供打开按钮，ContactOptions 弹层共用前缀输入、使用前缀／验证联系人／保留浮窗多选项。设置页通过 defaultPrefix / setDefaultPrefix 在固定主库保存 settings.contact_default_prefix；原班期 profile_contact_prefix / campaign_contact_prefix 优先（包括显式空值），缺失才回退默认值。使用默认值可在弹层显式选择；不改变已有打开接口的身份校验与按班期记忆。
- ProfileModule.wechatVerifier（app/profile_wechat.py）按当前画像匹配名单批量核验微信：有搜索/列筛选时从_scope_rows取真正匹配者并保留表格排序，空结果不回退全班；无查询时从active的class_roster关联profiles默认排除已退课，两种范围均排除补位。筛选范围可包含已退课学员，任务记录该初始状态，运行中原未退课者变为已退课仍跳过。查询/冻结集合改变时重建预览，同一查询的值变化保留上轮结果。QThread只搜索并发送核验结果，主线程写入前复核数据库路径、姓名及学籍，复用autoSaveField/reflect_saved同步微信与最新身份并保留筛选。RemarkDriver只读标题、关闭浮窗；明确姓名/旧姓名斜杠备注/本班已知前缀或已保存备注才接受，重名及其他标题留待确认。ContactNotFoundError继承RuntimeError区分未找到与窗口操作失败，保留旧调用兼容。逐人结果仅保留在会话，无新表；共享企微互斥、F11及关闭等待，并在退出前投递已完成联系人的待写结果。

### 群发

- createFromCampaignSelection/createFromProfiles 按可见人员生成独立名单，文字变量创建时展开，保留模板和资料元数据。names_only 保存空消息，补齐后才可发送。
- GroupCenter 缓存名单、选择、待处理/已发送模型；GroupStore 负责持久化、编辑和队列保护。空方案（create allow_empty）允许 0 成员，`save_default_row` 对空名单只写模板；`add_recipients` 手填/粘贴加入成员并按当前模板渲染消息，模板无法解析时留空并回报 no_message，`remove_recipients` 只删没有尝试记录的待处理行。
- GroupCenter.qml 顶部一行是「选择群发方案」下拉框＋「重命名」（左）与「复制为新名单」「新建群发」（右对齐）；重命名经 GroupCenter.renameList → GroupStore.rename_list 只更新 lists.title（拒绝空白/换行标题与过期 list_id，发送运行中只提示不改名），不触碰 recipients/attempts，也不清空当前预览确认。「新建群发」只收方案名称，调用 createEmptyList 建空方案，成员与消息随后手动补。
- GroupCenter.qml 参数 600ms 防抖保存，切名单/预览/关闭另有保存处理；按 list_id 校验，修改后清除预览确认。
- prepare → GroupStore.plan → confirmation；start 重验计划、参数/文件及 F11 注册，再启动 SendWorker。每人先 claim 后 finish；暂停/结束在当前联系人完成后生效。
- WeComSender 执行进程/焦点检查、搜索、可选浮窗核验、剪贴板粘贴和回车。“已发送”不证明送达，不确定结果需人工核实。
- 旧 generateCampaign/sending_store 路径仍处理来源名单：复核源批次/资格、防重复、结果回写和待回写恢复。当前独立名单不具有源批次约束，不可混同。

### 备注批改

- RemarkRenamer 取画像「微信=是」的学员，按班期推导前缀（settings.profile_remark_prefix 可覆盖），把每人状态放在 wecom_remark_scan。
- RemarkWorker 逐人调用 RemarkDriver：WeComSender.search_contact_v2(姓名, substring_mode, close_on_success=False, capture_title=True) 打开浮窗并取标题，driver 关闭浮窗并校验主窗口回到前台，再按 remark_scan.classify 决定跳过 / 改名 / 待确认 / 未找到。
- 改名交给 app/wecom_remark.py 的 change_wecom_remark（由 wecom_renamer.load_change_remark 在真正改名时延迟 import，避免启动期加载 OCR/PyAutoGUI）；成功与「已符合」都把真实备注写入学生 contacts 表，群发搜索按前缀+姓名即可命中。
- 与群发互斥（owner.workflow.send_busy），复用 F11Hotkey；暂停在当前联系人处理完成后生效，单人失败继续下一位。

### 未进直播间

- LiveAbsence 跟随全局当前班级（`workflow._classes[class_index]`）：term_id/term_no 取自班级登记，节次读原主库 term_lessons 缓存（缺失才联网获取，刷新时保留原有 resource_id，不改「班期学员」页的第 1 节默认值）。
- 获取走 AcquisitionTask('live') → CompletionClient.live_students(term_id, resource_id)：同一接口按 resourceId 返回该节每人的 hisLearningTime（秒）；成功回填后按 term_id + resource_id 双重校验，切班或换节次即丢弃结果。
- `_rebuild()` 把接口行与本地范围合并：status=在读 → 画像微信=是（remark_storage.load_students(require_wechat=False)）→ 非有效免催（live_storage.active_exemptions）→ 有姓名；`hisLearningTime is None` 为未进入，`0` 秒按 includeZero 选项判定。补位、无微信、免催、接口无姓名只计数，进入 issues 提示。
- 每节提醒标记存本班库 live_reminders；`GroupCenter.createFromLiveAbsence(title, fields, record_keys)` 校验 record_keys 与当前 recipientKeys 一致后建独立名单，成功后回写标记并跳到群发中心，只创建不发送。
- 切班由 Workflow.selectClass 末尾的 liveAbsence.reload() 触发，和备注批改同一模式；该页与群发/其它采集互斥（busy）。

## 持久化边界

### 今日工作台

Backend.dailyWorkspace → DailyWorkspace（独立选择与冻结列表、目标聚合、方案排序、核验）→ FollowupStore（每班daily_goals/daily_tasks/daily_events）。读路径不建表；首次写入前对已有学员的班库做SQLite备份，再新增三个表及单目标/单未结束承诺索引。正式目标与LearningOverview临时试算分开；累计仍复用load_batches有效性校验，采用最新批次成员，周期开始人员只用于变化提示。当前逐节flags仅在source_sync一致时补充范围内事实，N之后的未知不影响已确认范围。

Backend.fetchData记录请求启动时间，成功导入及刷新/建批后把实际返回且姓名匹配的人员交给after_fetch。核验要求请求启动晚于承诺项目/时间调整，保存启动/完成/原同步时间与各项目证据；未返回者保留原结果。核验、承诺和联系事件不改反馈或人工可跟进状态。每分钟提示、跨班重载和关闭/重启沿用Qt生命周期。

FollowupEditor共用于今日详情与催办详情/浮窗的折叠区。草稿同时捕获数据库、学号、任务、修订、目标及编辑器token；模块切换只隐藏编辑器并保留草稿，切换学员/班级/批次及关闭前flushEditor，失败阻止该操作；同学员另一编辑器保留冲突输入。列表修订使用reconcile_rows和next_cursor，不以冻结过期行生成名单。GroupCenter.createFromDailySelection创建独立名单，learning_data关联学号、班库、正式目标、任务及版本；发送结果只供详情读取，不写承诺完成。

今日卡片固定联系人头部与底部操作，中间ScrollView滚动；嵌入CampaignDetail时随外层滚动并沿用compact尺寸，聚焦输入保持可见。联系人使用ContactOptions；联系记录复用workflow.feedbackShortcuts并捕获编辑key。项目模型只在内容变化时替换，同一学员保存保留前缀与展开状态。期限支持快捷日期，独立复查、指标贡献、历史和取消按需展开；review_required由保存入口校验，留空时不能在身份切换提交中退回默认期限。输入停顿不自动新建承诺，保存/回车及既有离开提交继续生效；已有承诺仅完整输入500ms合并提交，输入法组合期间不提交，菜单或日期弹窗打开时暂停计时；版本冲突及过期保存通知保留草稿。保存错误在表单显示并聚焦无效字段。

### 学习概览（只读）

LearningOverview接收Workflow.overviewSourceChanged，在激活时或可见期间读取当前owner.db.path；独立SQLite只读连接开启读取事务，不构造Database/CampaignStore，不迁移、不联网、不写历史。不可读取Workflow._model.rows或store.rows的当前身份联动结果替代冻结成员。失活时仅置脏；切班即标记重置，重新激活清除旧选择。四页签各存批次/节次状态，最新固定max(id)，目标及范围均不落库。Main切模块仍先flushFeedback，概览选择不调用工作台selectBatch/selectRow。

目标追踪的差值目标提供只读补作业名单弹窗。名单用campaign_students保存的姓名/学号、欠交课程与作业节次、完成计数筛选在读非补位、第1～N节课程全部完成且仍有欠交作业的学员（该范围欠交合计0/X），不限制本批人工可跟进标记。弹窗标题及条件随选择显示实际节次，明确「排除范围内未完课程人员，再保留范围内欠交作业人员」两个条件；第N节之后的欠课/欠作业不影响入选。缺失/未匹配/非法学习数据不推断，候选人数与试算所需人数分别展示，人数不足提示缺口；切班、离开目标页或累计数据失效时关闭弹窗。

campaign_students.snapshot推导全班范围和精确完成次数，campaign_followup_status仅补人工统计；campaign_dashboards累计版本/人数/比率校验失败时保留批次及成员，累计指标留空。LearningOverview.qml用OverviewChart的QtQuick Canvas与RangeSlider绘制实线/虚线、考核线、悬浮/键盘明细，用OverviewTable显示同源明细和固定节次走势；目标输入委托固定，统计更新不销毁输入焦点。没有新依赖或存储格式。见ADR-013。

| 范围 | 内容 |
| --- | --- |
| 原主库 / workflow.registry | 班级路径、平台设置、作业绑定、term_rosters/term_lessons；切班不替换 registry |
| 每班库 / owner.db | class_roster；profiles；profile_field_definitions/values；exemptions；reminder_data |
| 每班批次表 | campaigns、campaign_students、campaign_feedback、campaign_drafts、campaign_dashboards，以及旧发送兼容表 |
| 备注批改 | 每班库的 student_contacts（学号 → 真实备注名，群发/画像共用）与 wecom_remark_scan（判定状态）；settings.profile_remark_prefix；两表 DDL 只在 app/remark_scan.py 定义，campaigns.SCHEMA 与 remark_storage.bootstrap 共用，旧班库由任一入口幂等升级 |
| 未进直播间 | 每班库的 live_reminders(term_id, resource_id, student_id, reminded_at, list_id)；DDL 只在 app/live_storage.py，bootstrap 幂等升级；直播明细不落库，节次复用原主库 term_lessons |
| group_messaging.db | lists、recipients、attempts；参数、消息 JSON、模板、来源元数据、发送状态 |
| 数据库外 | keyring 密码、platform_sessions 登录缓存；附件绝对路径；手动导出 XLSX |

Database 顶部 SCHEMA 不是最终 schema 全貌：构造还执行 learning_store/profile_fields 等迁移，画像初始化涉及 profile_storage。最终 profiles 按学号关联 roster，不可只按旧建表语句设计查询。连接使用事务/外键，GroupStore 有独立连接管理。

工作台布局使用 workflow_field_order、workflow_field_visibility；导出用独立 workflow_export_preferences。显示顺序、模型索引、导出顺序、消息列顺序不能混成一个设置。

## 按任务验证

| 区域 | tests/ 中的主要验证 |
| --- | --- |
| 班期/学习/快照 | test_term_roster、test_fetch_workflow、test_business_logic、test_dashboard、test_linked_identity；smoke_class_switch |
| 画像/隔离 | test_profile_module、test_profile_extensions、test_class_isolation_regressions；smoke_profile_ui |
| 工作台/浮窗 | test_workbench_revision、test_campaign_generation、test_campaign_companion、test_workbench_ui、test_editor_identity |
| 群发/恢复 | test_group_center、test_group_interaction、test_real_sending、test_message_content；smoke_group_interaction、smoke_group_list_view、smoke_group_message_input、smoke_profile_group |
| 备注批改 | test_remark_renamer；smoke_remark_renamer（默认测试不真实登录企微、不改名） |
| 未进直播间 | test_live_absence；smoke_live_absence（注入假直播间结果，不登录平台、不发送） |

命令见 README。LegacyMain.qml、sent_messages/、data/ 不是默认调查入口，后两者可能含真实数据。
