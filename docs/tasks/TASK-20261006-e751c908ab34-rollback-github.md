# TASK-20261006-e751c908ab34：回退标题栏方案并交付 GitHub

## Identity
- 工作状态：verifying
- 更新时间：2026-10-06 22:40（Asia/Shanghai）
- 关联：TASK-20261006-c9e4a13bf572（cancelled）

## Requirement
用户明确要求回退至方案 1 实现之前，并将项目提交至 GitHub。本次单次交付范围为现有 origin 的 yankee-007/StudentManagement、main 分支及回退后的项目版本；包括远端尚未收到的项目提交。不扩大为后续持续上传授权。

## Baseline / Workspace
- main；起点 41c5f4a；工作区与暂存区干净。
- 已核对真实 push URL 为 git@github.com:yankee-007/StudentManagement.git，无额外 pushurl 或 URL 重写。fetch 成功，origin/main 比本地少 7 个提交，无远端领先或分叉。
- 本地与远端树均未发现 .github 工作流；未发现仓库内推送触发部署配置。外部集成配置无法由本地代码证明。

## Plan / Snapshot
按新到旧撤销 41c5f4a 和 f3c0e85，不改写既有历史。产品代码应与 6d5df95 一致；保留并取消原标题栏任务记录。完成 UI／业务回归和全部待上传提交的敏感内容检查后，提交并普通推送 main，再核对远端 SHA。

已应用两次 revert（未提交）；main.py、qml/、app/、tests/、assets/、requirements.txt 与 6d5df95 无差异。旧标题栏任务记录已保留并标记 cancelled，移出活动表。本地验证通过；下一步：提交并推送，再核对远端 SHA 与完成记录。

## Verification / Closure
- 已通过 smoke_ui_refresh（七模块／三个尺寸／21 张截图）、smoke_ui_refinements、smoke_restart_ui；查看 720px 工作台截图确认回退后标题和班期布局正常。证据位于忽略目录 output/rollback-ui，仅虚构学员。
- 完整 unittest 回归通过：200 项，199 通过、1 跳过，用时 151.841 秒。所有验证使用临时数据库、虚构学员、模拟平台与企微，不启动正式业务应用。
- 已检查 origin/main..HEAD 的 7 个待上传提交：84 个新增文本 blob，未发现高置信凭据模式、私钥、数据库、会话／发送／企微证据文件。2 个二进制 blob 为 assets/ 图标 PNG／ICO，签名核验与 PNG 视觉检查正常。规则扫描不能证明不存在所有秘密；不扫描无关磁盘内容。
- 回退及文档尚未提交、尚未推送；交付状态不能视为完成。
