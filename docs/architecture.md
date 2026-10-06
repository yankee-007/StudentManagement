# 当前架构

核对日期：2026-09-29。模块导航见 [项目概览](../PROJECT_CONTEXT.md)，设计原因见 [ADR 索引](decisions/README.md)。

## 入口与边界

main.py 创建 QApplication（原生文件对话框需要 QWidget 支持），设置 Fusion/字体/应用名称，将 Backend 和 studentModel 注入 QQmlApplicationEngine，加载 qml/Main.qml。Main 切换工作台、画像、班期学员、设置、群发中心、备注批改、未进直播间，并管理独立浮窗。

```text
Main.qml / 模块 QML / 浮窗
       ↕ Property、Signal、Slot；表格角色
Backend（组合入口，持有当前 db/repo）
 ├─ Workflow ─ CampaignStore ─ 每班 SQLite
 ├─ ProfileModule ─ StudentRepository / profile_storage
 ├─ TermModule ─ TermRosterStore ─ 原主库缓存
 ├─ SettingsModule ─ 原主库设置 / keyring
 ├─ ProfileCompanion、CampaignCompanion、ContactOpener
 ├─ LiveAbsence ─ live_storage ─ 每班 SQLite（live_reminders）
 └─ GroupCenter ─ GroupStore ─ group_messaging.db
                     ↓ plan / claim / finish
              SendWorker + F11Hotkey → WeComSender

Backend / TermModule / SettingsModule / LiveAbsence → AcquisitionTask（QThread）
   → completion / homework 客户端 → 合并/校验 → 导入/缓存
```

这些 QObject 同时承担界面状态和业务协调，没有统一独立的 Service 层。Backend 保留旧表格接口；当前工作台主要使用 backend.workflow.tableModel。

## Python ↔ QML 与状态

- QML 展示层共用 UiTheme、UiButton、UiTextField、UiComboBox、UiPanel；本地 qmldir 注册主题单例。左侧导航调用原 switchModule，群发中心位于最后。班期学员／画像／催办等共用顶部 classSelector，班期页通过 Workflow.selectClass → TermModule.alignTerm/activate 跟随当前班级；activate 和班期目录刷新均按当前班级 term_id 选择缓存，未关联平台的旧导入班级显示空名单及选择提示，避免显示另一班期的缓存。调试重启保留原保护条件。工作台／画像窄窗口切换列表与详情的可见性，不销毁编辑组件、不改保存和业务接口。群发参数常驻左侧，消息视口保留横向滚动。

- Backend 以常量 QObject Property 暴露模块；QML 使用 QVariantMap/List 读取行、字段、参数，调用 Slot，以 notify signal 更新绑定。
- DictTableModel 是 QAbstractTableModel，角色包括 display、studentId、recordKey、expiredCell、staleRow。set_rows 重置模型，reconcile_rows 用增删移动/数据通知减少委托重建。
- Workflow 的 _rows 是完整批次行，_model.rows 是当前显示集合（冻结结果集，可能含已不符合筛选的过期行），_selected 是主表选择。selectionChanged、queryChanged、changed 不可任意互换。
- 筛选按 ADR-007 冻结：应用筛选时把命中 key 存入 _frozen，值变化只更新数据并写 _filter_stale，只有显式重新筛选（搜索、视图、列筛选、切班/切批、刷新数据、重新应用）才重算；业务取数必须走 _scope_rows()（显示集合去掉过期行），不能直接用 _model.rows。
- 列筛选按字段 key 保存；ProfileFilterDialog 共用于画像和工作台，ProfileFieldOrder 负责字段拖拽。工作台隐藏列宽为 0，模型仍保留数据列。
- 画像记录身份组合数据库路径/学号；工作台 editorKey 是 JSON [db_path,batch_id,student_id]。名单对话框捕获 recipientKeys，后端检查仍与当前筛选完全一致。
- CampaignDetail 由主界面和催办浮窗共用，反馈为单行 TextField + 点击展开的 Menu，无独立下拉按钮。TapHandler 保留原输入事件；Menu 不抢输入焦点，键入时收起，快捷内容追加到末尾，非空时以「；」分隔。Menu 按上下空间定位，限制高度支持滚动，避免覆盖输入框；捕获 editorKey 防止旧菜单写入新学员。列表底部提供添加选项，默认「答应补课」「未接听电话」，新增选项存于当前班级 settings.campaign_feedback_shortcuts，经专用通知同步，避免广播重建编辑器。字段模型仅在布局签名改变时更新，值单独绑定；反馈保存不能重建编辑器。后端拒绝旧身份 key，工作台集中保存带身份的待保存反馈，连续输入只重启 500ms 定时器，不逐键写库或广播刷新。
- 切班/切班期是同步 Slot：selectClass 会重建班级上下文并刷新名单、批次和画像，实测整班首次切换约 430ms、缓存命中 30–75ms，必须由 WaitingOverlay 覆盖。
- 切换时序：ComboBox 的 onActivated 先 close() 弹出层，再 begin(name, action, largeRoster) 打开 ClassSwitchOverlay；Overlay 只在 hostWindow.frameSwapped（一次真实绘制，含 app/window.update()）后经 Qt.callLater 执行 action，因此耗时刷新不会阻塞 Loading 的首次绘制。最快显示 140ms 防闪烁；窗口不可见时 cancel() 丢弃待执行动作，渲染停摆时 frameTimer 兜底执行，避免动作丢失或 Loading 常驻。
- 长耗时提示必须提前决定：同步刷新会冻结事件循环，定时器只能在刷新结束后才触发，事后补提示必然晚于工作完成。因此由 Workflow.classRosterSize / TermModule.termRosterSize 在切换前读取缓存人数（只读连接，不构造 Database、不触发迁移，结果按班期缓存），≥300 人或未知时首帧即显示“数据较多，加载时间稍长”。
- 切班时同一次统计只取一遍名单：selectClass 把 owner.refresh() 返回的 students 分别传给 reload_batches/reload_rows/live_roster 和 _refresh_statistics。list_students 在 900 人班约 30–45ms，重复调用是切班的主要可消除开销。

## 关键调用链

### 班期、学习数据与快照

1. TermModule 通过 AcquisitionTask 获取班期、课程、名单；TermRosterStore 在原主库缓存，Workflow.sync_terms/roster_sync 同步到各班库。
2. 名单采集固定识别首节课程，与当前查看课程独立；缺失缓存才补取，显式刷新更新已有缓存。取消后拒收结果，等待网络结束/超时，不强杀线程。
3. 新建催办调用 Backend.createCampaign，按作业绑定获取两平台数据；_fetch_succeeded 校验数据库身份、姓名、完整性后导入，再调用 Workflow.createBatch。
4. CampaignStore 保存全班快照和 campaign_dashboards；dashboard.learning_dashboard 在建批时计算（version 3 起同时写入累计完课／作业人数与按完成节数分桶的 completion 分布）。后续获取只刷新最新批次的学习列、看板与批次时间 created_at（refresh_latest_learning，与建批共用 learning_snapshot 推导），最新批次身份可同步；历史批次不重写快照，建下一批前冻结上一批。Workflow.refresh_dashboard 读快照后只在最新批次按当前反馈补算每个桶的「可跟进人数」，不写回快照。
5. Workflow 组合反馈/草稿/免催，执行视图、搜索、列条件、排序，再通知模型和选择。

### 反馈、免催与浮窗

- CampaignDetail → queueFeedbackForSelection → Workflow.queueFeedback/flushFeedback → CampaignStore.save_feedback：校验班级、批次、真实学员，按捕获身份替换本批次反馈并清空旧草稿；非空计已回复，清空恢复待反馈，不推进选择。保存时读取该学员并 reconcile_rows，保留编辑委托和冻结筛选；失焦、切班/批/学员、切模块、关闭时提交待保存内容，失败保留内存内容并阻止班级/批次切换及主窗口关闭。旧 draft/submit 接口保留兼容调用，旧记录与草稿仅在实际编辑后合并持久化。
- markUnreplied → mark_unreplied(batch, visible_ids)：事务中跳过补位、空姓名、已有任何反馈或非空草稿，不检查发送成功。
- setLeave/clearLeave → profile_storage.set_exemption：画像/催办共享免催表；日历返回后复查身份，刷新当前资料但不修改历史快照。
- 两个浮窗是无主窗口从属关系的独立窗口，主窗口最小化时仍可见；主窗口关闭时显式关闭浮窗。浮窗定时读取经进程验证的前台企微标题，只接受唯一姓名匹配。CampaignCompanion 限最新批次，独立于主表选择；切班/批次清身份。ProfileCompanion 的画像身份格式不同，不能混用 key。
- ContactOpener 使用 ContactOpenTask 打开/验证联系人，不发送消息；与群发互斥，退出等待任务结束。画像和催办填写卡片的姓名右侧提供打开按钮，ContactOptions 弹层共用前缀输入、使用前缀／验证联系人／保留浮窗多选项。设置页通过 defaultPrefix / setDefaultPrefix 在固定主库保存 settings.contact_default_prefix；原班期 profile_contact_prefix / campaign_contact_prefix 优先（包括显式空值），缺失才回退默认值。使用默认值可在弹层显式选择；不改变已有打开接口的身份校验与按班期记忆。

### 群发

- createFromCampaignSelection/createFromProfiles 按可见人员生成独立名单，文字变量创建时展开，保留模板和资料元数据。names_only 保存空消息，补齐后才可发送。
- GroupCenter 缓存名单、选择、待处理/已发送模型；GroupStore 负责持久化、编辑和队列保护。
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
| 群发/恢复 | test_group_center、test_group_interaction、test_real_sending、test_message_content；smoke_group_interaction、smoke_profile_group |
| 备注批改 | test_remark_renamer；smoke_remark_renamer（默认测试不真实登录企微、不改名） |
| 未进直播间 | test_live_absence；smoke_live_absence（注入假直播间结果，不登录平台、不发送） |

命令见 README。LegacyMain.qml、sent_messages/、data/ 不是默认调查入口，后两者可能含真实数据。
