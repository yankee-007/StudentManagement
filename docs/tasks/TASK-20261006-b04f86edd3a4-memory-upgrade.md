# TASK-20261006-b04f86edd3a4：项目记忆升级至 Bootstrap 0.3.0

## Identity
- 工作状态：done
- 更新时间：2026-10-06T15:19:47+08:00

## Requirement
用户要求读取指定 BOOTSTRAP.md，将本项目初始记忆升级至最新协议。范围仅治理文档；保留单 Agent、业务约束、既有内容及旧 HANDOFF 未完成事项。完成标准：固定来源、适配最低语义、核对链接和策略、审查实际差异；不要求业务改动、远端上传或人工接受文档。

## Baseline 与 Workspace
- 起点：209224fc9e49df5c307c59022eb716e7dcaafea0；分支与目标分支 main，沿用当前分支，无合并任务。
- 开始时 staged、unstaged、untracked 均为空，无用户未提交修改；无依赖任务。
- 旧 HANDOFF 另保留为 TASK-20261006-9dd5d6536487，不接管其业务实施。

## 上次核验快照
已完成固定来源、缺项识别、短入口和长期协议适配、旧任务兼容迁移、上下文历史分离、ADR 索引规范。观察状态为起点 commit 上的本轮文档改动：5 个已有文件修改、6 个新文件，均归属本次升级，无业务文件修改；提交结果以 Git 查询为准。

## 关键发现
- 来源版本 0.3.0，SHA 794358e26c313cda4ef39c87a64f9c8145c1c0a2；Raw 获取两文件出现 EOF，改用同 SHA GitHub Contents API 完整解码成功。
- 旧 HANDOFF 的完课率描述与当前代码不符：源码采用累计人数 / 全部在读人数；保留旧快照并注明偏差，不修改业务。

## 验证与人工验收
2026-10-06，Windows/PowerShell、基于上述起点及本轮文档工作区：本地 Markdown 引用、适配点、原工程约束原文保留、原 HANDOFF 原文完整保留、历史证据迁移（姓名脱敏除外）均通过自动核对；git diff --check 通过。人工审查最低语义、策略条件与实际 diff；未运行业务测试、启动应用、访问真实平台或验收旧业务。

## 当前阻碍与下一步
本任务完成标准已满足，无文档阻碍；旧业务缺口仍在 HANDOFF，不由本任务关闭。活动索引已移除本任务并保留记录。下一步：按有效策略核对完整 staged、提交本轮治理内容并核验结果；远端同步未授权。

## 交接或结束
代码通过项目仓库及上述起点恢复；Python 环境与安全测试方式见 README。文档已保存；本轮逻辑单元可按策略本地提交，实际 commit 与工作区状态以 Git 查询为准。未获远端上传授权，不保证另一台电脑已能取得本轮改动。后续从 AGENTS.md 开始，不能自动加载的 Agent 应显式读取入口。

## 最低语义完成核对

| 最低语义 | 实际路径 / 章节 | 结果 |
| --- | --- | --- |
| 入口与职责、按需加载 | AGENTS.md；policy 的文档路径映射 | 已覆盖 |
| 策略条件及能力关闭限制 | policy 的有效策略/冲突表；workflow 的 Session 与任务开始；git 开头 | 已覆盖，adaptive/single-writer 与项目单 Agent 一致 |
| 任务身份、六种状态、时区、单列阻碍 | workflow 的标识/状态/最小记录；本 Task 与 HANDOFF 的 Identity | 已覆盖；原无 ID 记录补唯一 ID，历史未知显式标注 |
| 任务最低记录及恢复环境 | workflow 的最小记录；本 Task 与 HANDOFF | 已覆盖，无虚构历史或依赖 |
| 工作区保护与单写入者 | workflow 的项目工程约束/接力；git 的基线与修改归属 | 已覆盖 |
| Git、秘密与上传安全 | git 的全部章节；policy 的操作范围 | 已覆盖，上传待授权，无凭据值 |
| 恢复、接手摘要与阶段保存 | workflow 的 Session/关键阶段/checkpoint | 已覆盖，不承诺崩溃前收尾 |
| 验证与事实边界 | workflow 的验证与人工接受；PROJECT_CONTEXT 第 11 节 | 已覆盖；本轮未复跑业务测试 |
| 交付、目标范围及授权 | policy 的策略依据与操作范围；git Push；workflow 接力 | 已覆盖，文档/本地提交/跨电脑可取得分别判断 |
| 完成、索引移除与长期维护 | workflow 的文档维护与完成；docs/tasks/README；ADR 索引 | 已覆盖，完成 Task 原路径保留，活动行已移除 |

复用 docs/architecture.md 和全部既有 ADR；README 仅改开发导航。未改 .gitignore，现有规则已覆盖本轮范围；未增加伪造 ADR、后台服务或工具包外部必读依赖。

常规启动文档规模（字符 / UTF-8 字节；不等于 token）：AGENTS 1014 / 2350，PROJECT_CONTEXT 6502 / 14235，policy 3686 / 7076，ADR 索引 1797 / 3179；任务索引按收尾后活动行读取，明确 Task ID 时直接读任务。workflow/git 按动作需要加载。
