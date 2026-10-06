# ADR-008: 备注批改以浮窗标题为真实备注，复用 student_contacts 作为备注对应表

## Status

Accepted。2026-09-30 由用户逐项确认后实施：搜索只用姓名；用 `Ctrl+O` 浮窗标题判定；前缀按班期推导且可手改；成功与「判定已符合」都回写；重名只标记不阻断；独立第六个入口；全局 F11 中途暂停。

## Context

已有 `app/wecom_remark.py`（`change_wecom_remark(original_remark, new_remark, ...)`，实施时原为独立的 `wecomrename/wecom_remark.py`，后按用户要求内联进 `app/`，见 ADR-011）能用纯 OCR 修改**当前聊天**联系人的备注，但它不搜索、也不验证联系人是谁：内部要求左侧蓝色选中行与聊天顶部名称都等于 `original_remark`，否则抛错。批量使用必须由调用方完成“定位并确认是哪一位”。

用户现场备注格式为旧 `姓名/新生` 与新 `前缀＋姓名`（`py175示例学员`）并存，且**已经有相当一部分学员改好了**，没有任何记录标明谁改过。若只按本地数据判断，会把已改好的人再改一次，或在搜不到时误改他人。

同时，群发中心的搜索关键字是 `群发名单.prefix + 学员姓名`（app/group_dispatch.py 的 `plan`），画像「备注」与催办快照的 `remark` 都读同一个 `student_contacts(student_id PRIMARY KEY, remark)`。也就是说：备注一旦改成新格式，若不同步这张表，群发反而更搜不到人。

## Options Considered

1. **在本地维护一份“旧备注→新备注”对照表**，按对照表搜索与改名：被否决——旧备注无来源、易过期，搜不到时无法区分“已改好”和“备注不同”。
2. **读企业微信联系人资料卡判定当前备注**：被否决——资料卡入口与字段布局在 OCR 下不稳定，且 `change_wecom_remark` 本身已经要打开资料卡，重复读取会放大误判面。
3. **用 `Ctrl+O` 浮窗标题作为真实备注**（本决定）：标题就是企微里的备注名，不需要本地先验数据，天然能区分“已改好”“旧格式”“其它”。

## Decision

- **名单来源**：当前班期画像中「微信=是」的学员，学号/姓名取 `class_roster`（与画像、催办同源）。重名姓名按完整名单（含其他班期）统计，只写「存在重名」标记，不阻断、不跳过。
- **前缀**：由班期号推导（`P2026175` → 取尾部 `175` → `py175`；`编程175期` → `py175`；纯年份 `P2026` 不推导），可手动修改，按班期保存在 `settings.profile_remark_prefix`，切班自动换默认值。
- **单人处理链**：以**姓名**搜索（包含匹配）→ `Ctrl+O` 打开浮窗 → `GetWindowText` 读标题 → 关闭浮窗并**校验主窗口回到前台**（`change_wecom_remark` 依赖主窗口状态）→ 按标题判定。
- **判定链**（app/remark_scan.py 的 `classify`）：标题含「前缀＋姓名」= `已符合`（跳过改名）；标题以姓名开头且含 `/` = 旧格式，交给 `change_wecom_remark(标题, 前缀＋姓名)`；其它 = `待确认`（不自动改，只能人工选中后强改）；标题不含该姓名 = `未找到`（本轮继续下一位）。
- **持久化**：复用 `student_contacts` 作为备注对应表（学号 → 企微真实备注名）；新增 `wecom_remark_scan(student_id, observed, desired, state, detail, scanned_at)` 记录判定结果。`已符合` 与 `已修改` 都写 `student_contacts.remark`，因此已改好的学员重启后依旧跳过，群发中心把前缀填成同一前缀即可搜到。两表的 DDL 只在 app/remark_scan.py 定义一处，app/campaigns.py 的 SCHEMA 与 app/remark_storage.py 的 `bootstrap()` 共用它，旧班库从任一入口首次运行即幂等升级，不需要单独迁移步骤。
- **失败与暂停**：单人异常记为 `失败` 并继续下一位；`未找到`/`失败` 可重试；`已跳过` 由人工标记。全局 F11 与「暂停」都在**当前联系人处理完成后**生效，不打断 OCR 与按键序列；`处理中` 不落库，避免中断后留下假状态。

## Rationale

浮窗标题是唯一由企微自己给出的、逐人可核验的“当前备注”。把它同时用作判定依据与 `change_wecom_remark` 的 `original_remark`，可以让“要不要改”和“改什么”共用同一份事实，避免本地数据陈旧导致的重复修改或误改。

复用 `student_contacts` 而不是新建备注表，是因为它已经是备注的唯一消费点（群发搜索、画像备注、催办快照）。新表只承担“这次批改做到哪一步”，职责不重叠；离线可查、可续跑、可审计。

不改动 `change_wecom_remark` 内部逻辑，只在 `WeComSender.search_contact_v2` 增加两个**默认关闭**的参数（`capture_title`、`activate_on_close`），保证群发与工作台发送路径的行为字节不变。

## Consequences

- 备注批改与群发共用 `student_contacts`：改完备注后必须把群发前缀设成同一前缀，否则搜索关键字仍是旧值；这是有意的耦合，README 已说明。
- `wecom_remark_scan` 不进入画像导出（用户明确不需要导出），但它是跳过判定的唯一依据；清空该表会导致所有人被重新扫描。
- 判定依赖 OCR 可读的浮窗标题与姓名唯一性：姓名不完全匹配时记 `未找到` 而不改名，宁可漏改不可误改。跨班重名只提示。
- 每个联系人需要约 3–8 秒真实桌面操作，处理期间占用键鼠；真机验收必须人工在场，默认测试不得真实登录或改名。

## Rejected / Failed Approaches

- 让 `change_wecom_remark` 自己搜索：它只操作“当前聊天”，加搜索会让 OCR 定位与焦点假设混在一起，未采用。
- 把「微信备注名」放进 `BASE_PROFILE_LABELS`：会改变 4 处现存断言并使 `profiles.fields` 语义扩散，用户选择不导出，故只存 `wecom_remark_scan`。
- 用固定坐标或 UIA 读取备注：与现有 OCR 路线不一致，未采用。

## Related Areas

app/wecom_renamer.py、app/wecom_remark.py、app/remark_scan.py、app/remark_storage.py、app/wecom_sender.py、app/campaigns.py（SCHEMA）、app/group_dispatch.py（搜索关键字）、qml/RemarkRenamer.qml、qml/Main.qml；tests/test_remark_renamer.py、tests/smoke_remark_renamer.py；ADR-001、ADR-003、ADR-011。
