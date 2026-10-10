# 项目协作策略

协议来源版本：Agent Project Bootstrap 0.4.0。版本仅用于识别和明确升级，不自动重跑初始化。

来源模式：GitHub；固定提交 `80ab20527d75158eaf0b414b38d4784708302e4a`，协议与模板通过该提交的 Raw URL 读取。入口：[固定版本 BOOTSTRAP](https://github.com/yankee-007/AgentBootstrapPrompt/blob/80ab20527d75158eaf0b414b38d4784708302e4a/agent-project-bootstrap/BOOTSTRAP.md)。升级日期：2026-10-10。

来源记录仅供追溯，不是日常 Session 的外部读取依赖。无法核验来源提交时明确记录未知，不写入本机工具包或缓存绝对路径。

## 有效策略

下表记录本项目的有效策略，具体依据与操作范围见后文。不得通过修改本文件自行获得权限。

| 配置 | 生效值 | 含义 |
| --- | --- | --- |
| GIT_POLICY | detect-and-init | 已有 Git 复用；无 Git 且范围明确、无其他 VCS 约束时本地初始化 |
| REMOTE_POLICY | ask-once | 首次远端操作确认目标和范围，已有授权不重复询问；可选 existing-only、private-auto、disabled |
| TASK_TRACKING_POLICY | adaptive | 复杂、跨阶段、易中断、并行或需接力的任务建立记录；简单修改可不建 |
| PARALLEL_DEVELOPMENT_POLICY | single-writer | 默认串行；显式并行时独立工作区和分支，另核对共享资源 |
| AUTO_COMMIT_POLICY | verified-owned-units | 日常自动提交归属清楚且符合该逻辑单元验证要求的内容；明确推送请求按项目快照规则保存当前状态 |
| RECOVERY_COMMIT_POLICY | on-handoff | 需交接时可保存明确标注的未完成工作；分支和副作用须符合项目约定 |
| AUTO_PUSH_POLICY | authorized-milestones | 已授权范围内，完成并验证的里程碑可自动推送；恢复性上传需授权涵盖未完成内容 |
| HUMAN_VERIFICATION_POLICY | criteria-based | 根据验收标准、主观要求和 Agent 验证能力决定是否需要人工确认 |
| INTEGRATION_POLICY | follow-existing | 沿用既有集成方式；未知时不自动合入共享目标分支 |

可将提交、恢复提交、推送策略改为 `ask` 或 `disabled`；任务跟踪可改为 `always` 或 `disabled`。关闭跟踪后必须说明跨 Session 恢复能力下降，不能仍承诺完整交接。`existing-only` 禁止新建远端但不自动授予上传权限；`private-auto` 仅在服务、账号/组织、名称与范围已确认时自动创建私有仓库。未识别的取值或相互冲突的配置需澄清，不静默采用更宽松策略。

本项目保留既有 `single-writer`、`follow-existing` 和 `authorized-milestones`，不因升级改为新版默认的 task-worktree、squash-on-completion 或 on-request。单 Agent 串行、按需隔离，不自动迁移当前任务或把既有分支变成只接收成果的工作区。

若用户明确启用 `task-worktree`，独立修改任务在写入前建立唯一分支与 worktree；澄清、修正或接力沿用原任务，不按消息或 Session 新建。纯讨论/查询/审查通常不建分支，轻量或关闭跟踪也不免除已启用的隔离要求。集成分支仅接收成果；该策略不自动委派 Agent。

若明确启用 `squash-on-completion`，满足当前任务集成条件后向已确认目标串行 squash；用户要求仅开发、评审或等待接受时保留任务成果。它不允许绕过提交/验收禁令、合并未知任务、上传或部署；当前 `follow-existing` 不自动授予 squash 或合入 main 的权限。

`authorized-milestones` 保留已授权且验证的里程碑自动推送条件。用户明确要求推送/同步项目时，按下文项目快照规则保存当前内容；该备份请求与自动里程碑、任务完成及集成分别判断。没有推送请求或适用持续授权时不自行上传；不因升级新增远端授权。

`REMOTE_POLICY=disabled` 时不因自动推送策略而执行远端操作；恢复提交也不得绕过项目明确禁止提交的约定。明确的用户新指示可调整相关范围，但无回复或任务文本不能代替授权。

具体冲突按以下规则处理，不要求用户重答整张表：

| 条件 | 实际行为 |
| --- | --- |
| TASK_TRACKING_POLICY=disabled | 不创建/更新任务记录和活动表；初始化可保留注明停用的导航章节，既有记录原样保留；仍核对文件并报告恢复入口及能力下降 |
| TASK_TRACKING_POLICY=always / adaptive | 分别为所有实际任务 / 满足复杂度条件的任务保留完整最低记录；不登记模板示例 |
| GIT_POLICY=disabled 或项目禁止 Git 写入 | 不初始化、暂存、提交或推送；许可的只读核对和文件保存可继续 |
| task-worktree 已启用但无可用 Git/基线，或禁止创建分支/worktree | 不伪造隔离或改为共享并行；说明限制，仅在确认单写入者且允许时继续现有目录的文件工作 |
| TASK_TRACKING_POLICY=disabled / adaptive 的轻量任务 | 不因隔离强制创建 Task 或活动表；已启用隔离时仍核对唯一分支、基线、目标与依赖，按提交及交付摘要追溯 |
| AUTO_COMMIT_POLICY=disabled | 不自动创建普通或恢复提交；RECOVERY_COMMIT_POLICY=on-handoff 不能覆盖禁令 |
| AUTO_COMMIT_POLICY=disabled / ask，或任务尚未满足集成条件 | 不由 squash 策略绕过约定；保留分支和成果，已有适用提交/集成授权直接使用 |
| AUTO_COMMIT_POLICY=ask 或 RECOVERY_COMMIT_POLICY=ask | 相应提交须有适用明确授权；恢复提交同时满足两者，已有授权不重复询问 |
| RECOVERY_COMMIT_POLICY=disabled | 不自动创建恢复提交，普通提交仍按其策略判断 |
| REMOTE_POLICY=disabled 或 AUTO_PUSH_POLICY=disabled | 不自动推送；前者同时禁用其他远端操作，后者不替代远端读取策略 |
| 用户明确要求项目快照且 Git/提交/远端允许 | 保存全部已跟踪文件当前内容及删除、未忽略的新文件和原有修改；无需测试或人工验收先通过，用户限定内容时遵循其范围 |

多 worktree 备份须逐个核对实际覆盖，协调各写入者在任务分支保存稳定快照；未完成任务不为备份提前合入集成分支。按已授权的同仓库 refs 上传，不默认推送所有分支；仅允许 main 时，其他任务先保存本地并报告未远端覆盖。main 已推送不等于全部任务已备份，缺少的分支授权只影响相应上传。

GIT_POLICY 可显式设为 `disabled`；启用 Git 时仍遵循既有项目检测/初始化约定。关闭提交不阻止安全文件保存，关闭推送不意味着另一台电脑已取得代码。无法解释的其他配置只阻塞相关动作，不采用较宽松取值。

## 策略依据与操作范围

沿用项目原有单 Agent 开发、最小修改、数据安全与针对性验证约定；其正文在 workflow 的「项目工程约束」。任务跟踪保留 adaptive：新复杂任务使用独立 Task，历史任务原路径与 ID 保留。用户于 2026-10-10 明确要求删除根交接兼容入口；后续从 AGENTS.md 和任务索引恢复，不维护第二份任务导航。未规定项按有效策略解释，不扩大业务或外部权限。

远端同步授权：2026-10-06 用户明确要求「回退至实现方案1之前；项目提交至GitHub」。本次单次交付允许将回退后的项目及既有待上传提交推送至已核对的 origin：git@github.com:yankee-007/StudentManagement.git、main 分支，任务 TASK-20261006-e751c908ab34。无额外 pushurl 或 URL 重写；本地与远端树均未发现 .github 工作流，未发现仓库内自动部署配置，外部集成不可由本地代码证明。授权不包含强推、发布、部署或后续持续上传；未来任务须按其实际授权核对范围。

远端同步授权：2026-10-09 用户明确要求「将项目提交至GitHub」，并在确认中选定「提交本轮修改并推送 codex/daily-workspace」，同时确认把 32次催交话术库 一并纳入仓库。本次单次交付允许：把本轮工作区修改按逻辑单元提交后，连同既有待上传提交推送至已核对的 origin（git@github.com:yankee-007/StudentManagement.git）的 codex/daily-workspace 与 main 分支。实际结果：codex/daily-workspace 9827639、main 07e7a53，均为快进推送。授权不包含强推、远端删除、标签推送、发布、部署，也不包含把 codex/daily-workspace 合入 main（该限制仅约束该轮，见下条新授权）；2026-10-06 的单次交付授权已结束，不延伸至本轮。仓库未发现 .github 工作流，本地代码无法证明是否存在外部自动部署。

远端同步授权：2026-10-09 用户询问后续拉取代码应以哪条分支为开发主线，明确选定「把 main 快进到当前开发分支，以后拉 main」。据此把 main 快进（`07e7a53..829fa9c`，无合并提交、不改写历史、无强推）并推送至同一 origin 的 main 分支；本地 main 同步推进到 829fa9c，与 codex/daily-workspace 同一提交。此后项目开发与拉取基线为 main，main 上的新提交按 AUTO_PUSH_POLICY 在授权里程碑内推送。原先对 codex/daily-workspace 的单次上传授权不延伸至后续新内容。

远端同步授权（限定强推）：2026-10-09 验收记录提交 `12c60ee` 的提交信息首行被写入 BOM 字符，用户明确选定「用 --force-with-lease 覆盖这条提交」。据此把该提交改写为内容相同、信息干净的 `8a844b4`，并以 `--force-with-lease` 分别覆盖 origin 的 codex/daily-workspace 与 main；改写只涉及这一条尚未被他人使用的提交，基线 `b24c0a4` 及其下历史不变，工作区 15 个文件的变更内容未改。该授权仅限本次修正，不构成后续强推、远端删除或历史重写的通用许可。

远端同步授权：2026-10-10 用户在本轮群发中心修改完成后明确要求「提交至github」。本次单次交付允许将群发交互提交 `9f97610`、此前尚未上传的学习概览鼠标拖动修复 `ca6a10a`，以及本次授权与交付说明，通过正常快进推送至已核对的 origin（当前地址 `https://github.com/yankee-007/StudentManagement.git`）的 main 分支。已 fetch 核对远端基线为 `2c60f5a`，本地领先两条实现提交、无分叉；两条提交均为文本代码、测试与文档，未发现新增凭据字面量或敏感文件。仓库未发现 .github 工作流或部署配置，外部集成无法由本地文件证明。授权不包括强推、其他分支、标签、发布、部署或后续持续上传；推送结果以实际远端查询和本轮交付答复核对。

授权记录只记录用户或有效项目约定明确允许的范围，至少能定位实际远端、允许分支、允许内容、适用任务/阶段、已知推送副作用及授权依据。单次交付结束后不自动延伸至下一轮；持续授权明确记录其边界。未授权时明确写“待确认”；有登录能力不等于有操作授权。已有适用授权直接使用，不重复询问。

按请求备份时，“推送/同步项目”默认覆盖整个项目当前可纳入 Git 的状态，包含原有 staged/unstaged 修改、未完成或未验收内容，不再逐文件或逐任务确认内容。沿用已确认且仍适用的目标与分支范围；用户限定文件或任务则按限定执行。新建仓库、变更目标、扩展 refs、强推、部署等另按实际授权处理。本次文档升级没有远端上传请求，不沿用已结束的单次交付授权。

## 项目入口与验证方式

运行和验证入口见 README 的「启动」「测试」，依赖见 requirements.txt。常规回归为 `python -m unittest discover -s tests -v`；QML 采用 README 中 offscreen 冒烟并核对真实界面。测试只用临时数据库、虚构学员、模拟网络/企微，不启动正式应用调查。本次纯文档升级只做文档与差异检查，不重新宣称历史测试通过；既有失败与真实平台/企微验收缺口见 PROJECT_CONTEXT。

沿用已有 Git 根和分支，已确认的集成与拉取目标为 main；当前检出分支、HEAD 和相对 main 的差异每轮以 Git 查询核对，不能根据历史同步记录认定仍相同。需要新分支时采用 `codex/<task-id>-<slug>`；codex/daily-workspace 的名称不代表其全部实际范围。本次在指定工作区串行升级，不切换分支、不集成。

默认单 Agent、单工作区单写入者；显式并行需求须有用户授权和独立工作区。集成由一个执行者串行处理，无需常驻服务；没有执行层互斥时使用明确的串行交接。Markdown 状态、Task Owner、超时和 git worktree lock 不能授予写入权。当前没有后续新内容的通用远端分支授权，须按每次请求核对同一仓库与 refs；历史单次授权见上文。

## 文档路径映射

默认根入口为 `AGENTS.md`、上下文为 `PROJECT_CONTEXT.md`、架构为 `docs/architecture.md`；协议在 `docs/agent/`，任务在 `docs/tasks/`，决策在 `docs/decisions/`。

| 职责 | 实际路径 / 章节 |
| --- | --- |
| 短入口 | AGENTS.md |
| 当前状态 | PROJECT_CONTEXT.md（历史记录另见 docs/history/project-validation.md） |
| 使用与验证 | README.md |
| 当前架构 | docs/architecture.md |
| 策略、条件与授权 | docs/agent/policy.md |
| 任务、验证、恢复、生命周期及既有工程约束 | docs/agent/workflow.md |
| Git 归属、安全、提交和上传 | docs/agent/git.md |
| 活动任务 | docs/tasks/README.md |
| 新任务 | docs/tasks/TASK-日期-12位随机十六进制-主题.md |
| 长期决策 | docs/decisions/README.md 及索引中的既有 ADR |

后续按实际路径读取。凭据、机器专属临时路径与活跃进程信息不写入共享策略。
