# HANDOFF

## 当前任务目标

催办工作台看板：顶部增加**累计完课人数／累计作业人数**，并新增「完课次数」分栏
（`完课次数 / 人数 / 所占比例 / 可跟进人数 / 完成人数 / 本周是否有退课 / 完课率 / 完课人数`）。

## 状态：**代码、单测、离屏 QML 冒烟与完整回归已完成并通过。仅剩两列待接入数据源。**

## 用户原始需求摘要

- 看板顶部显示累计完课人数、累计作业人数。
- 新增一个「完课次数」分栏，列如上（按用户逐项确认的 8 列）。
- 用户逐项确认的口径（2026-10-01）：
  - 分桶按**恰好完成 k 节课程**计数，`完课次数 0` ＝ 一次课都没看的人；行范围 `k = 0 … 已开课节次`。
  - `完课人数`＝完成节数不少于该行的**累计人数**（＝参考表里非单调的「完课率 × 人数」那一列的分母口径）。
  - `可跟进人数` ＝ 该桶中**有反馈记录、不是「未回复」标记**的学员。
  - `完成人数`、`本周是否有退课`：**先留空**，后续接入（用户明确要求）。
  - 范围与看板分母一致：批次内在读非补位学员。
  - 版面：做成看板内第二个标签页，与现有表格共用展开按钮。

## 已完成（磁盘现状）

| 文件 | 改动 |
| --- | --- |
| `app/dashboard.py` | `learning_dashboard` 升到 `version: 3`：新增 `opened`、`cumulative{courses,homework}`、`cumulativeCourse/cumulativeHomework`、`completion{courses,homework}`（每桶 `count/people/cumulative/ratio/cumulativeRate`）；新增 `_distribution()` |
| `app/campaigns.py` | `CampaignStore.dashboard` 增加 `version < 3` 降级：空分布 + 累计人数 `—` + notice「旧版快照未保存完课次数分布」 |
| `app/workflow.py` | `refresh_dashboard` 读取快照后调用新的 `_attach_followable()`：只在最新批次按当前反馈补算每桶 `followable`，不写回快照 |
| `qml/LearningDashboard.qml` | 顶部一行追加累计完课／作业人数；`tab` 属性 + 两个标签按钮；「完课次数」分栏（8 列）与自适应高度列表；计算说明补充新口径 |
| `tests/test_dashboard.py` | 更新精确断言 + 新增 `CumulativeHeadcountTests`、`CompletionDistributionTests`（13 项） |
| `tests/test_campaigns.py` | 新增 2 项：看板累计人数与分桶自洽（含 followable 只在最新批次）、旧版本快照降级 |
| `tests/smoke_dashboard_completion.py`（新） | 离屏真实 `Main.qml`：展开、真实鼠标点击切标签、逐行文本校验、截图中文可读、切换后分栏保持 |
| `tests/smoke_editor_identity.py` | 原「重开的 store 与界面看板全等」改为比较去掉 `followable` 的快照 |
| `README.md`、`PROJECT_CONTEXT.md`、`docs/architecture.md`、`docs/decisions/ADR-010-*.md`、`docs/decisions/README.md` | 功能说明、模块表、调用链、口径与验证记录 |

## 未完成 / 待人工确认

1. **`完成人数`** 列仍为空单元格：数据来源未定，需要用户说明它到底代表什么（当前实现按用户要求不猜）。
2. **`本周是否有退课`** 列仍为空单元格：系统里只有班期名单的「学员状态」，**没有退课日期**；要做“本周”判断必须先确定退课时间的来源（平台接口字段？本地记录？）。
3. 参考表里的「完课率」非单调（第 4 行 55.29% 高于第 5 行 32.35%）已按用户参考表实现：**完课率＝累计完课人数 ÷ 桶人数**。若后续要单调的完成率，属于口径变更（改用累计分母或换列含义），需先确认。
4. 真实班级数据下的观感未验证：建议在一个真实批次上展开分栏，确认各桶人数合计等于「在读人数」、完课率为 100% 的行就是 `完课次数 0` 行。

## 已执行测试及结果

- `python -m unittest tests.test_dashboard`：13 项通过。
- `python -m unittest tests.test_campaigns`：6 项通过。
- `python -B -m tests.smoke_dashboard_completion`（`QT_QPA_PLATFORM=offscreen`）：通过，退出码 0；
  截图 `%TEMP%/student-dashboard-{lessons,completion}.png` 已确认中文可读、标签页与 8 列正常。
- 完整回归 `python -m unittest discover -s tests`：**Ran 190 tests, OK (skipped=1)**（跳过项为既有的本机样例缺失）。
- 相关 QML 冒烟：`smoke_workbench_revision`、`smoke_filter_freeze`、`smoke_floating_windows`、`smoke_editor_identity`、`smoke_dashboard_completion` 全部通过。
- **`smoke_profile_editor_layout` 在第 83 行（画像字段拖拽排序）失败，已确认是既有失败**：
  用 HEAD 版本的 `LearningDashboard.qml` 复跑同样失败，与本次看板改动无关，本次未修。
- 环境：`D:\miniconda3\envs\groupmessaging\python.exe`（Python 3.11.5 / PySide6）。

## 关键代码位置

- 分桶与累计人数：`app/dashboard.py::_distribution` / `learning_dashboard`
- 旧快照降级：`app/campaigns.py::CampaignStore.dashboard`
- 可跟进人数：`app/workflow.py::Workflow._attach_followable`
- 界面：`qml/LearningDashboard.qml`（`completionRows`、`tab`、`learningDashboardCompletionList`）

## 已做出的任务级临时决策

- 「完成人数」「本周是否有退课」输出**空单元格**而不是 `—`：用户明确说“先空着，后续更改/优化”。
- `followable` 由 `Workflow` 实时补算、不入快照：反馈是实时的，快照按 ADR-006 冻结。
- 旧快照（version < 3）不尝试反推分布，直接显示空分栏并提示，避免给出错误数字。
- 分桶口径只数 `T`：`F`/`N`/`U`/无记录一律计入 `0 节`桶，保证各桶合计＝在读人数。

## 遗留（上一任务）

未进直播间（ADR-009）、备注批改（ADR-008）代码已完成，仅剩真实平台取数与企微端到端验收（人工在场先跑 1 人）。

## 阻塞

无。仅差上述两列的数据源口径确认。
