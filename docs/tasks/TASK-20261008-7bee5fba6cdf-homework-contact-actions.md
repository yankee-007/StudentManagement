# 补作业名单联系人操作

## Identity
- ID：TASK-20261008-7bee5fba6cdf
- 状态：done
- 更新时间：2026-10-08（Asia/Shanghai）
- 基线：main / a4a8b25，起始工作区干净；单 Agent。
- 关联：TASK-20261007-19c5a0db0505。

## Requirement
- 用户要求去掉补作业名单序号列，为每个学员增加打开对应联系人按钮，复用催办工作台功能。
- 保留姓名、学号、欠交作业节次；共享工作台前缀及联系人验证/浮窗选项、打开线程和群发互斥。
- 通过名单所在班级/批次/学员身份校验点击，不切换工作台游标，不更改学习快照或反馈。切班、切批、离开目标页、人员不再符合当前名单后拒绝旧按钮身份。
- 目标页允许查看历史批次，历史候选可打开联系人；原工作台最新批次限制保留。

## Snapshot
- 工作台入口校验当前工作台/浮窗选择，不能直接把其他名单学员身份传给它。
- 已移除序号，增加联系人列。抽出CampaignContactButton供工作台和名单共用，弹窗复用ContactOptions及已保存工作台前缀；工作台重新显示时重读共享前缀。
- ContactOpener.openOverviewContact先校验当前概览名单身份，再与openCampaignContact共用同一任务启动函数，保持前缀保存、验证/浮窗选项、非法字符和群发互斥校验。
- 概览表格通过可选操作列承载按钮，其余统计表不改变。

## Verification / Closure
- 使用D:/miniconda3/envs/groupmessaging/python.exe：`python -B -m unittest tests.test_learning_overview tests.test_contact_opener tests.test_campaign_companion -q`，31项通过；随后新增历史候选场景，修改的单项测试复跑通过。覆盖对应联系人、共享前缀/选项、群发及重复打开互斥、非法前缀、失效身份和工作台/学习快照不变。
- offscreen/Fusion/微软雅黑，`python -B -m tests.smoke_learning_overview`通过，三个尺寸1280×820、1000×700、720×480。实际QML鼠标点击名单B、暗色窄窗口键盘打开C、返回工作台点击A，均调用模拟ContactOpenTask并核对姓名及选项；工作台游标不变、共用前缀更新、其他按钮忙时禁用、既有表格/图表/切班检查通过。
- 目视检查1000宽弹窗和720宽亮暗滚动后截图，姓名/学号/欠交节次/打开按钮可读，窄窗口可滚动到最后一行。
- Review及git diff --check通过。README、当前上下文、架构和ADR-013更新了受影响的功能与身份边界；未增加依赖或持久化格式。
- 全部测试只使用临时数据库、虚构学员和模拟联系人任务；未操作生产数据或真实企微，未运行全库回归。按项目策略保存本地提交；未上传远端，真实企微效果沿用既有适配器，本轮未实机验收。
