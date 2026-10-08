# TASK-20261008-06191dab05cf · 完课班期对应可选作业班级

- 状态：done
- 更新时间：2026-10-08 18:39 +08:00（Asia/Shanghai）
- 需求：设置按完课平台班期数量逐行列出固定班期，仅选择对应作业班级；允许留空，重启保留。
- 完成标准：平台缓存班期与行数一致；选择/清空立即写入主库；旧绑定兼容；重启及目录缺失时显示保存结果；真实 QML 交互、临时数据库回归通过。
- 基线：`56d4b72f625d1bd92f5fa5fdc9557cdfd056310b`，`codex/daily-workspace`；开始时工作区、暂存区干净。沿用当前分支，无远端上传授权。
- 范围：app/settings_module.py、qml/SettingsModule.qml、绑定行组件、设置测试及受影响文档。单 Agent、单写入者。

## 分析与恢复快照

已核对真实磁盘及 Git。原设置从 workflow 登记班级生成下拉框，可能包含平台列表之外的历史班级；作业班级需要另点确认，留空无法保存。已有 homework_bindings 和按账号保存的班级目录可复用，无需数据迁移。

已实现：以 remote_terms 缓存为准（没有平台缓存时兼容已登记班期），逐行展示；选择/清空自动保存；保存失败显示错误并恢复已有绑定；目录缺失保留保存名称，空目录持久化；多课程恢复原选择。设置通知分离，账号变化不重建绑定行。复选同一班级保留课程。

## 验证与交付

使用临时数据库、虚构班期和模拟凭据；未启动正式应用、未联网登录、未访问正式数据库。Python 3.11.5 / PySide6 6.8.3：

- `unittest tests.test_settings tests.test_acquisition tests.test_appearance tests.test_term_roster`：21项通过。
- `unittest tests.test_class_isolation_regressions`：6项通过。
- offscreen `tests.smoke_settings_ui`：通过，覆盖实际下拉操作、留空/清空、各行隔离、目录缺失清空、错误恢复、同班级课程保留、平台列表增删、滚轮、窄屏、亮暗主题与后端/引擎重建后的恢复，无 QML 警告。
- offscreen `tests.smoke_appearance`、`tests.smoke_class_switch`：通过。
- 已查看 `output/settings-input/bindings-wide.png`、`bindings-narrow.png`、`bindings-dark.png`，中文可读、绑定行无重叠；截图在忽略目录，可运行冒烟重建。
- `git diff --check` 通过；完成修改归属、旧格式兼容、主库写入、调用方及文档影响审查。修复验证中发现的 QML 滚动引用遮蔽和重复选择班级重置课程问题。

## 交付与恢复

需求已实现，客观验收项已覆盖。按项目策略保存本地逻辑单元，以本 Task ID 和 Git 查询定位提交；无远端上传授权，未推送。活动索引移除本任务，任务文件保留。没有结构迁移；原绑定继续可读，留空仅删除该班期对应记录。

本次验证未覆盖真实平台登录/联网对账，也未运行全库回归；这些边界不作为本任务的通过声明。使用现有启动方式重新启动后查看设置新流程。
