# TASK-20261006-9dd5d6536487：看板既有任务的人工验收与待定口径

## Identity
- ID：TASK-20261006-9dd5d6536487（升级时为原无 ID 记录补充，后续沿用）
- 工作状态：done
- 更新时间：2026-10-09 22:50 +08:00
- 验收：用户于 2026-10-09 确认「已全部验收」；实现版本为 commit b24c0a4 的 main。既有看板口径按现状接受，新增两列仍需先有数据源与口径，属后续需求，不在本任务关闭范围内。
- 归属：旧任务，仅迁移记忆；本轮未继续业务实施。

## Requirement、Baseline 与 Workspace
需求与已确认范围保留在下方原文。实现与历史自动验证已记录完成；待定两列按用户要求留空，不能推定必须本轮接入。人工观感及真实平台/企微验收缺口尚未核验。完成标准：核对相关代码/历史证据、得到所需人工验收；新增两列需先有数据源/口径及实施授权，属于后续需求。

原实施起点与当时 staged/unstaged/untracked 边界无法从旧记录确认，标为未知，不追填历史。迁移观察版本：209224fc9e49df5c307c59022eb716e7dcaafea0，main；升级开始工作区干净。原目标分支/依赖任务未知；关联 ADR-008/009/010，本轮不要求集成或合并。

## 核验偏差、阻碍与下一步
2026-10-06 静态核对 app/dashboard.py::_distribution 与 qml/LearningDashboard.qml：当前「完课率」是累计人数 ÷ 全部在读人数；下方原文第 3 项关于“桶人数”及非单调的描述已过期，不作为修改依据。历史测试和截图只属原记录，本轮未复跑、未重新检查截图。其它实施/结果信息尚未逐项重新验证。

阻碍单列：两列未来接入的数据源和业务口径待确认；真实环境与人工接受缺失。本轮文档升级不依赖这些条件。下一步最小动作：当用户继续此任务时，先核对当前看板与 ADR-010，确认要验收现状还是接入新数据源；不得仅因活动索引存在就启动真实外部操作。

## 恢复与交付限制
从项目 Git 检出上述观察版本，按 README 恢复 Python/PySide6 环境，安全验证只用临时数据库与模拟网络。历史自动测试结果见下方；真实数据观感与企微端到端结果不保证。本文件已从根目录 HANDOFF.md 迁入独立 Task，后续在此更新；本轮提交/远端可取得状态以 Git 查询为准，文档保存不等于上传。新任务不复用此 HANDOFF。

---

以下为原 HANDOFF 快照（原文保留，遇到偏差以上方当前核验为准）：

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


## 旧 Session 记录同步（2026-10-06T20:15:50+08:00）

用户要求同步仍沿用旧 HANDOFF 的 Session。迁移起点为 a30ef7f6046606e0c872a24d3725675649b8e010，main，staged/unstaged/untracked 均为空。迁移前 HANDOFF 与已提交版本一致，没有新增业务进度；反馈编辑的后续任务已有独立记录 TASK-20261006-a834b72e9c51，未合并或覆盖。原任务 ID、awaiting_acceptance 状态、历史正文及未决事项保留。根 HANDOFF 改为导航，不再保存任务正文。

仅重新静态核对完课率的累计人数 / 在读人数口径；历史测试与人工验收仍未复核。此轮仅验证迁移内容保留、本地链接、路径映射与差异；无业务修改或外部操作。下一步仍为上文所列人工验收/口径确认；恢复按 README 环境和当前 Git 查询进行，不依赖旧 Session。

迁移检查结果：本地 Markdown 引用可解析，旧 HANDOFF 历史正文完整保留，反馈编辑 Task 未改变，git diff --check 通过。仅本地文档同步，未运行业务测试或新增人工验收；提交与远端状态以 Git 查询为准。
