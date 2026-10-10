# TASK-20261010-042af07e7e69：项目记忆升级至 Bootstrap 0.4.0

## Identity

- 工作状态：done
- 更新时间：2026-10-10T16:26:54+08:00

## Requirement

用户要求按指定 GitHub BOOTSTRAP 更新项目记忆至最新版本，并删除根目录 HANDOFF.md，不保留兼容入口。范围为治理与受影响的当前文档；保留既有单 Agent、策略值、业务约束、历史 Task/ADR 和未完成业务的验收边界。

完成标准：固定并完整读取来源，补齐新版最低语义，删除兼容入口及现行规则中的依赖，核对链接、策略、原文保护与实际差异。不要求修改业务、人工接受文档、集成到 main 或远端上传。

## Baseline 与 Workspace

- 起点：5c6dc1188eea581b3ff6177d62462b11acbedf81；当前分支 codex/daily-workspace，沿用指定项目工作区串行升级。
- 开始时 staged、unstaged、untracked 均为空，无用户未提交内容、冲突或进行中的 Git 操作。
- 已确认集成目标为 main；本任务不集成、不切换分支、不新建或清理 worktree。已有 detached 基线核对工作区保持原样。
- 无实施依赖；旧记忆升级 TASK-20261006-b04f86edd3a4 仅供沿革追溯，不重开。工作区可通过项目 Git 与本 Task ID 定位，不以本机路径为唯一恢复入口。

## 上次核验快照

已完成来源固定、清单完整性检查、项目/Git 基线与最低语义缺项分析。来源版本 0.4.0，完整 SHA 为 80ab20527d75158eaf0b414b38d4784708302e4a，协议与相关模板均通过同 SHA Raw URL 读取。

已补充入口、策略、工作/Git 协议和任务索引，更新上下文事实边界，删除根兼容入口，纠正 README/架构的素材入库描述；原业务代码、数据和历史 Task/ADR 未修改。观察状态为起点上的本轮文档工作区，修改 8 个既有文件、删除 1 个文件、新增本 Task；提交结果以 Git 查询为准。

文档生成、最低语义核对与差异审查已完成，本任务完成标准满足；本地提交按策略保存，实际提交与跨电脑可取得状态以 Git 查询为准。没有业务实现、集成或清理动作。

## 关键发现

- 既有有效值 single-writer、follow-existing、authorized-milestones 优先保留，新版 task-worktree/squash/on-request 默认值不覆盖它们。
- 根交接文件只有导航，原业务正文已在独立 Task；删除导航不删除历史记录，也不改变 awaiting_acceptance 状态。
- README 与架构原称 32次催交话术库未跟踪，但 Git 已跟踪其规则和 32 份素材；已修正两处过期说明，与当前上下文一致。

## 验证与人工验收

2026-10-10，Windows/PowerShell 与 Python 标准库，针对起点及本轮文档工作区完成 14 项检查：收尾后 51 个本地 Markdown 链接目标可解析；9 项有效策略值与历史远端授权正文未变；原 Python/QML、数据安全和 Review 工程约束完整保留；39 份已有 Task/ADR/历史文件内容未变；根兼容入口不存在且现行文档无其文件依赖；来源/版本、适配点、工具包独立性、ID 唯一性、已有活动任务行、变更范围和 git diff --check 均通过。另核对本任务 done、活动行已移除、文件原路径保留及旧任务仍待验收。人工逐项审查最低语义及实际差异，映射见下表。

修改范围为 8 个既有文档、删除 1 个兼容文件、新增本 Task；ADR 索引和历史资料复用，.gitignore 已覆盖相关数据/凭据，未改忽略规则。仅文档验证，不启动正式应用、不连接真实平台、不运行或重新宣称业务测试通过。旧业务验收和基线失败仍按原记录处理。

## 当前阻碍与下一步

无文档阻碍，本任务已完成；按生命周期从活动表移除并保留本文件，原待验收任务行保持原样。下一步仅核对最终 staged 并按 verified-owned-units 保存本地逻辑单元；远端同步没有本轮授权。

## 交接或结束

从项目仓库取得本任务与对应提交，先读 AGENTS.md、PROJECT_CONTEXT.md、策略和本任务；按 README 恢复 Python/PySide6 环境。文档保存、本地提交、远端可取得分别核对；本任务的本地逻辑单元按 verified-owned-units 策略保存，远端上传无本轮授权，不保证另一台电脑已取得。

本次没有集成或清理动作，保留既有分支和 worktree；历史未完成任务的人工验收条件不由文档升级关闭。

## 最低语义完成核对

| 最低语义 | 实际路径 / 章节 | 结果 |
| --- | --- | --- |
| 入口、职责与按需加载 | AGENTS.md；policy 的文档路径映射；README 开发交接 | 已覆盖，无根兼容入口依赖 |
| 策略条件及关闭能力限制 | policy 的有效策略/冲突表；workflow 的 Session 与任务开始；git 开头 | 已覆盖，9 项既有生效值保留，disabled 不被无条件义务覆盖 |
| 任务 ID、六种状态、时区与单列阻碍 | workflow 的标识、状态与最小记录；本 Task Identity/阻碍 | 已覆盖，12 位随机标识已核对唯一性 |
| 任务最低记录与恢复环境 | workflow 的最小记录；本 Task Requirement/Baseline/Workspace/快照/验证/结束 | 已覆盖，需求、范围、完成标准、修改边界、依赖、验证和下一步可定位 |
| 工作区与用户内容保护 | AGENTS.md；workflow 的接力/工程约束；git 的基线与修改归属 | 已覆盖，普通归属筛选与明确项目快照分开，单写入者保持 |
| 任务隔离、串行集成与历史保留 | policy 的策略适配/入口与验证；workflow 的 Session/接力；git 的任务分支/串行集成/清理 | 已覆盖，目标 main、codex 命名、依赖、条件式 squash 与清理边界明确；既有 single-writer/follow-existing 优先 |
| 多工作区备份 | policy 的多 worktree 备份；git 的按请求保存项目快照 | 已覆盖，协调写入者，按授权 refs 上传，不提前集成，不以 main 同步代替全部备份 |
| Git、敏感内容与按请求快照 | git 的 Commit/快照/Secret/Push；policy 的操作范围 | 已覆盖，完整当前状态、忽略规则、身份/hook、历史检查与分叉边界明确；本轮未上传 |
| 接手恢复、阶段落盘与能力边界 | workflow 的 Session/关键阶段与 checkpoint；本 Task 的基线与快照 | 已覆盖，跟踪关闭不写 Task，文档/本地提交/跨电脑取得分别判断，不保证崩溃前收尾 |
| 验证、事实、推断与未知 | workflow 的验证与人工接受；PROJECT_CONTEXT 第 11 节；本 Task 验证 | 已覆盖，证据绑定范围/版本/环境，不把旧通过和无回复当作新验收 |
| 交付与授权范围 | policy 的策略依据与操作范围；git 的 Push；workflow 的接力；本 Task 结束 | 已覆盖，目标/分支/内容/阶段/副作用限定授权，历史单次授权不自行延伸 |
| 生命周期与长期维护 | workflow 的文档维护与完成；任务索引；ADR 索引 | 已覆盖，先任务后索引，done/cancelled 移除活动行并保留原文件，仅更新受影响文档 |

后续常规启动读取 AGENTS.md、PROJECT_CONTEXT.md、docs/agent/policy.md 与 docs/decisions/README.md；无 Task ID 时再读 docs/tasks/README.md，有 ID 时直接读对应任务。workflow/git 按动作加载，架构与 ADR 只读相关条目。无法确认自动加载入口的 Agent 须显式读 AGENTS.md；来源工具包无需重新获取。

常规启动文档规模（字符 / UTF-8 字节，按 LF 归一化；不等于 token，不宣称节省比例）：

| 文件 | 字符 | UTF-8 字节 |
| --- | --- | --- |
| AGENTS.md | 1131 | 2695 |
| PROJECT_CONTEXT.md | 10850 | 25089 |
| docs/agent/policy.md | 6794 | 13918 |
| docs/decisions/README.md | 2234 | 3918 |
| docs/tasks/README.md | 736 | 1426 |
