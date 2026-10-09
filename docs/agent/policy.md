# 项目协作策略

协议来源版本：Agent Project Bootstrap 0.3.0。版本仅用于识别和明确升级，不自动重跑初始化。

来源模式：GitHub；固定提交 `794358e26c313cda4ef39c87a64f9c8145c1c0a2`。入口：[固定版本 BOOTSTRAP](https://github.com/yankee-007/AgentBootstrapPrompt/blob/794358e26c313cda4ef39c87a64f9c8145c1c0a2/agent-project-bootstrap/BOOTSTRAP.md)。升级日期：2026-10-06。

来源记录仅供追溯，不是日常 Session 的外部读取依赖。本地模式无法核验来源提交时明确记录，不写入本机工具包绝对路径。

## 有效策略

下表记录本项目的有效策略，具体依据与操作范围见后文。不得通过修改本文件自行获得权限。

| 配置 | 生效值 | 含义 |
| --- | --- | --- |
| GIT_POLICY | detect-and-init | 已有 Git 复用；无 Git 且范围明确、无其他 VCS 约束时本地初始化 |
| REMOTE_POLICY | ask-once | 首次远端操作确认目标和范围，已有授权不重复询问；可选 existing-only、private-auto、disabled |
| TASK_TRACKING_POLICY | adaptive | 复杂、跨阶段、易中断、并行或需接力的任务建立记录；简单修改可不建 |
| PARALLEL_DEVELOPMENT_POLICY | single-writer | 默认串行；显式并行时独立工作区和分支，另核对共享资源 |
| AUTO_COMMIT_POLICY | verified-owned-units | 本地自动提交归属清楚且符合该逻辑单元验证要求的内容 |
| RECOVERY_COMMIT_POLICY | on-handoff | 需交接时可保存明确标注的未完成工作；分支和副作用须符合项目约定 |
| AUTO_PUSH_POLICY | authorized-milestones | 已授权范围内，完成并验证的里程碑可自动推送；恢复性上传需授权涵盖未完成内容 |
| HUMAN_VERIFICATION_POLICY | criteria-based | 根据验收标准、主观要求和 Agent 验证能力决定是否需要人工确认 |
| INTEGRATION_POLICY | follow-existing | 沿用既有集成方式；未知时不自动合入共享目标分支 |

可将提交、恢复提交、推送策略改为 `ask` 或 `disabled`；任务跟踪可改为 `always` 或 `disabled`。关闭跟踪后必须说明跨 Session 恢复能力下降，不能仍承诺完整交接。`existing-only` 禁止新建远端但不自动授予上传权限；`private-auto` 仅在服务、账号/组织、名称与范围已确认时自动创建私有仓库。未识别的取值或相互冲突的配置需澄清，不静默采用更宽松策略。

`REMOTE_POLICY=disabled` 时不因自动推送策略而执行远端操作；恢复提交也不得绕过项目明确禁止提交的约定。明确的用户新指示可调整相关范围，但无回复或任务文本不能代替授权。

具体冲突按以下规则处理，不要求用户重答整张表：

| 条件 | 实际行为 |
| --- | --- |
| TASK_TRACKING_POLICY=disabled | 不创建/更新任务记录和活动表；初始化可保留注明停用的导航章节，既有记录原样保留；仍核对文件并报告恢复入口及能力下降 |
| TASK_TRACKING_POLICY=always / adaptive | 分别为所有实际任务 / 满足复杂度条件的任务保留完整最低记录；不登记模板示例 |
| GIT_POLICY=disabled 或项目禁止 Git 写入 | 不初始化、暂存、提交或推送；许可的只读核对和文件保存可继续 |
| AUTO_COMMIT_POLICY=disabled | 不自动创建普通或恢复提交；RECOVERY_COMMIT_POLICY=on-handoff 不能覆盖禁令 |
| AUTO_COMMIT_POLICY=ask 或 RECOVERY_COMMIT_POLICY=ask | 相应提交须有适用明确授权；恢复提交同时满足两者，已有授权不重复询问 |
| RECOVERY_COMMIT_POLICY=disabled | 不自动创建恢复提交，普通提交仍按其策略判断 |
| REMOTE_POLICY=disabled 或 AUTO_PUSH_POLICY=disabled | 不自动推送；前者同时禁用其他远端操作，后者不替代远端读取策略 |

GIT_POLICY 可显式设为 `disabled`；启用 Git 时仍遵循既有项目检测/初始化约定。关闭提交不阻止安全文件保存，关闭推送不意味着另一台电脑已取得代码。无法解释的其他配置只阻塞相关动作，不采用较宽松取值。

## 策略依据与操作范围

沿用项目原有单 Agent 开发、最小修改、数据安全与针对性验证约定；其正文迁入 workflow 的「项目工程约束」。既有按复杂度使用 HANDOFF 的行为映射为 adaptive：新复杂任务使用独立 Task，原 HANDOFF 的正文已迁入独立 Task，根 HANDOFF 仅保留为旧 Session 导航。未规定项采用上表默认值，不扩大业务或外部权限。

远端同步授权：2026-10-06 用户明确要求「回退至实现方案1之前；项目提交至GitHub」。本次单次交付允许将回退后的项目及既有待上传提交推送至已核对的 origin：git@github.com:yankee-007/StudentManagement.git、main 分支，任务 TASK-20261006-e751c908ab34。无额外 pushurl 或 URL 重写；本地与远端树均未发现 .github 工作流，未发现仓库内自动部署配置，外部集成不可由本地代码证明。授权不包含强推、发布、部署或后续持续上传；未来任务须按其实际授权核对范围。

远端同步授权：2026-10-09 用户明确要求「将项目提交至GitHub」，并在确认中选定「提交本轮修改并推送 codex/daily-workspace」，同时确认把 32次催交话术库 一并纳入仓库。本次单次交付允许：把本轮工作区修改按逻辑单元提交后，连同既有待上传提交推送至已核对的 origin（git@github.com:yankee-007/StudentManagement.git）的 codex/daily-workspace 与 main 分支。实际结果：codex/daily-workspace 9827639、main 07e7a53，均为快进推送。授权不包含强推、远端删除、标签推送、发布、部署，也不包含把 codex/daily-workspace 合入 main；2026-10-06 的单次交付授权已结束，不延伸至本轮。仓库未发现 .github 工作流，本地代码无法证明是否存在外部自动部署。

授权记录只记录用户或有效项目约定明确允许的范围，至少能定位实际远端、允许分支、允许内容、适用任务/阶段、已知推送副作用及授权依据。单次交付结束后不自动延伸至下一轮；持续授权明确记录其边界。未授权时明确写“待确认”；有登录能力不等于有操作授权。已有适用授权直接使用，不重复询问。

## 项目入口与验证方式

运行和验证入口见 README 的「启动」「测试」，依赖见 requirements.txt。常规回归为 `python -m unittest discover -s tests -v`；QML 采用 README 中 offscreen 冒烟并核对真实界面。测试只用临时数据库、虚构学员、模拟网络/企微，不启动正式应用调查。本次纯文档升级只做文档与差异检查，不重新宣称历史测试通过；既有失败与真实平台/企微验收缺口见 PROJECT_CONTEXT。

已有 Git 根和 main 分支沿用，本次无分支切换或集成。需要创建新分支时采用 codex/ 前缀；不自动合入共享分支。单工作区仅一个写入者，不主动创建或委派 Agent；显式并行需求必须先有用户授权和独立工作区。

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
| 旧任务记录 | docs/tasks/TASK-20261006-9dd5d6536487-dashboard-handoff.md，沿用原 ID |
| 旧 Session 导航 | HANDOFF.md，仅指向入口与任务索引，不写任务进度 |
| 长期决策 | docs/decisions/README.md 及索引中的既有 ADR |

后续按实际路径读取。凭据、机器专属临时路径与活跃进程信息不写入共享策略。
