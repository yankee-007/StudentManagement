# 学员画像管理字段交互与布局

- ID：TASK-20261009-c17bfef2a601
- 状态：done
- 更新时间：2026-10-09 22:5 +08:00
- 验收：用户于 2026-10-09 确认「已全部验收」；实现版本为 commit b24c0a4 的 main。未记录逐项复验方式与真机截图，验收为验收人确认，不代表本轮新增自动验证。

## 需求与完成标准

管理字段拖动时卡片悬起跟随鼠标，在相邻字段间高亮实际插入位置，松开后按该位置保存。优化字段排序、显隐与新增表单的层级，适配窄窗口和亮暗主题。保留按班隔离、固定显示字段和删除确认；现有moveField同步契约保留，UI新增异步保存入口以消除放置阻塞。

本轮已实现：放置时只同步字段布局，不重读整班名单；QML ListModel按ID移动原卡片，字段配置缓存与定向通知减少重复读取，表头筛选标记只查字段key。进一步测量发现单次SQLite写入仍偶发耗时100～300ms，因此UI采用即时布局＋单线程后台串行保存，捕获原班数据库；关闭面板、切班／刷新、重置／其他字段修改和退出等待完成，最新失败提示并回退已保存顺序。增加「重置默认」，仅恢复当前班期顺序及显示，保留自定义字段、填写内容和已删除字段状态；不重建字段或清空资料。卡片64px／12px间距改为48px／6px，头部和内容边距收紧。原鼠标锚点和取消链保留。

最新反馈已实现：拾起卡片变淡、收窄；指针在按住时的卡片位置持续保持，不能拾起时跳到鼠标上方。原实现额外上移40px并限制横向位置，现移除这两处偏移，取消旋转／放大；按原卡片抓取点的归一化坐标定位缩窄副本，宽度90%、不透明度72%，动画期间也同步调整位置。画像排序面板拖动时提升层级，副本经过右侧新增表单时仍显示在上面。真实鼠标锚点、动画与既有排序行为验证通过。

## 基线与工作区

分支 codex/daily-workspace，HEAD b9c003df9ab784c390e52bc570fa6354ec169a66。当前 Agent 单独分析、写入与验证。

起点存在16个已修改文件、AI催交实现及话术素材等未跟踪内容，属于既有任务。相关 ProfileFieldOrder.qml 仅有固定字段备注使用 modelData.note 的已有修改，须保留；ProfileModule.qml 起点无差异。PROJECT_CONTEXT.md、README.md、任务索引已有改动，只追加本需求对应内容。既有修改不归本任务提交。

## 方案与依据

沿用 UiTheme：白色 surface #ffffff、浅灰 canvas #eef2f6、深色 ink #203047、次级 muted #596b80、蓝色 accent #285db4、选中 selection #e5eefc，并使用对应暗色映射。沿用微软雅黑 UI 字体，标题20px、紧凑字段名13px、类型11px、说明12px。字段按真实顺序编号，左对齐排列；宽窗左侧排序列表、右侧新增表单，窄窗按需展开表单。结构为「班期标题／拖动说明 → 字段列表＋重置默认 | 新增字段 → 保存状态／完成」。

视觉重点集中于卡片拾取与间隙插入线，普通卡片不堆叠阴影。达到拖动阈值后才启动；原位置留占位，悬浮副本显示阴影、变淡收窄并保持原抓取位置，边缘持续滚动，Esc或离开放置区域取消。上移／下移按钮提供无需拖动的替代操作。插入间隙索引转换为移除源字段后的最终索引。模型变化或弹窗关闭时取消拖动。

## 快照与验证

已定位交互链 ProfileModule.qml → ProfileFieldOrder.qml → ProfileModule.moveField/setFieldVisible/addField/deleteField。现有拖动仅高亮整行；列表被外层滚动区嵌套，新增表单占用列表空间。PROJECT_CONTEXT 记载既有 smoke_profile_editor_layout 拖动失败，本任务以真实指针交互重新验证。

已实现：ProfileFieldOrder 分离视觉卡片／占位／插入线，ProfileFieldCard 共用字段卡片内容，ProfileModule 改为双栏弹窗；窄窗口的新增表单独立切换，避免挤压列表与越过底栏。卡片拾起后变淡、收窄且保持指针抓取点，插入线始终可见。沿用已有固定字段 note 语义。共享排序组件也用于催办字段设置，覆盖其兼容性。

实现与验证完成，主观体验待用户验收。当前真实代码以工作区为准；核对期间HEAD推进至341b00ed2b6a503184b43b395ce57800dd2176d0（既有AI功能提交），本Agent未执行Git写操作。剩余工作区仍含既有工作台改动，未认领或覆盖。

验证环境为项目Python 3.11.5／PySide6 6.8.3，QML设QT_QPA_PLATFORM=offscreen，加载微软雅黑，全部使用虚构学员与临时库：

- `python -B -m unittest tests.test_profile_editor_layout tests.test_profile_extensions tests.test_profile_module tests.test_profile_choices tests.test_workbench_revision -v`：14项通过，覆盖按班字段隔离、固定字段、显隐／删除、顺序持久化与主卡片／浮窗同步。
- `python -B -m tests.smoke_profile_field_manager`：最终通过，无QML警告；真实鼠标双向拖动、间隙几何、首尾插入、相邻无变化、Esc整个手势取消、区域外取消、模型刷新取消、关闭取消、静止边缘持续滚动、按钮排序、固定显示、显隐、新增下拉、删除确认取消和数据库重开。1280×860／720×480，亮暗两种模式；窄窗真实滚轮后点击新增均成功，表单与底栏无溢出。
- `python -B -m tests.smoke_profile_editor_layout`：通过，保留共享编辑器回车导航、联系人动作模拟、拖动排序、浮窗编辑与字段显隐断言。定位改为从画像弹窗查找列表，避免误选工作台隐藏实例。
- `python -B -m tests.smoke_workbench_revision`：最终通过，覆盖共享组件的催办字段／历史反馈兼容；模拟100次输入仍合并为1次写入。
- `git diff --check`：通过；复核本任务QML与冒烟差异、共享组件调用、通知取消、索引转换、删除确认和本班存储契约。README、PROJECT_CONTEXT、architecture及任务索引只更新相关当前状态，不新增ADR。

截图保存在忽略目录output/profile-field-manager：wide-light/dark、drag-between-light/dark、drag-last-light、narrow-light/dark、narrow-add-light/dark、narrow-add-scrolled-light/dark，已逐项查看代表图，中文可读。

2026-10-09 20:28补充验证：最终`smoke_profile_field_manager`通过，无QML警告；新增真实鼠标按手柄上部／中部／下部抓取、横向移动和区域外移动检查，使用源卡片实际坐标与悬浮副本的mapFromScene坐标比较，动画每30ms采样，归一化位置偏差小于0.002；宽度缩窄、不透明度降低和静止边缘滚动期间锚点也通过。两种主题代表截图重新查看，副本不再上移、不再被新增表单遮挡。`smoke_profile_editor_layout`通过，`git diff --check`通过。本次没有后端变化，未重复上轮14项单元测试或全库；真实体感待用户查看。另观察到RecipientMessages.qml、群发任务及其新冒烟文件的其他任务修改，未触碰。

首次截图发现窄窗列表＋表单堆叠时溢出底栏，已改为两者切换；旧冒烟失败实际是定位错隐藏列表。模型值未变时onModelChanged不会触发，补监听原changed信号保证刷新取消。窄窗滚轮测试还发现自动Flickable的越界回弹期间点击不稳定，新增表单改用显式StopAtBounds滚动区，并沿用SettingsWheelGuard避免滚轮改类型；验证等待滚动结束后使用真实按下／释放。未启动正式应用、未访问正式学员数据或真实企微；未跑全库或真实中文输入法，主观拖动体感待用户查看。

## 交付与恢复

2026-10-09本轮验证（最终工作区，虚构数据／临时库）：

- 1000人、8次实际QML鼠标拖放：修改前松手中位287.51ms／最大319.00ms，至抓取下一帧中位295.52ms／最大327.60ms，整班读取8次；最终松手中位32.34ms／最大35.88ms，下一帧中位39.74ms／最大46.01ms，整班读取0次。测量包含QTest分发及offscreen渲染，不是生产数据或长时间性能保证。最终可复跑`tests.smoke_profile_field_manager_performance`；结果在忽略目录perf-before/after.json。
- 相关单元19项通过（field_layout、editor_layout、extensions、module、choices、workbench_revision）；新增5项覆盖后台写入被阻塞时即时落位、连续排序保存顺序、切班时原数据库、重置等待队列、失败回退、资料／自定义／删除状态、冻结行／光标／排序键及只读保护。补充模拟重置失败通过。
- 最终smoke_profile_field_manager通过，无QML警告：紧凑布局、真实重置按钮／值保留、原委托移动、抓取锚点／动画、间隙／首尾／双向、取消链／静止边缘滚动、亮暗1280×860与720×480、新增表单滚轮／点击与重开持久化。增量移动曾令ListView.originY变化，重置后插入索引错误；现按originY＋头部计算，回归通过。不能以contentY≤0判断回到开头，改检验第一张卡片的实际可见位置。
- 最终smoke_profile_editor_layout、smoke_workbench_revision通过（后者100次反馈输入仍合并1次写入），同步字段契约／浮窗及共享工作台组件正常。代表截图已复核：wide-light、narrow-dark、drag-between-light，中文可读、间隙与紧凑卡片正确；未操作正式应用或真实企微。
- 本轮新增后端profile_module改动与tests/test_profile_field_layout.py、tests/smoke_profile_field_manager_performance.py；共享排序仍保留workflow既有note及同步moveField。README／PROJECT_CONTEXT／architecture／任务索引只更新本需求；未改schema或新增ADR。最终差异、调用链与git diff --check通过；最后补充的重置失败提示测试和最终界面冒烟也通过，主观体感待用户查看。

成果已提交并推送。2026-10-09 用户明确要求「将项目提交至GitHub」，据此把本轮修改（含新增ProfileFieldCard.qml、smoke_profile_field_manager.py、smoke_profile_field_manager_performance.py、test_profile_field_layout.py和本任务文件）提交为 commit 52a7d14 并推送 codex/daily-workspace。同一提交内的qml/CampaignFieldDialog.qml、qml/Main.qml、qml/ProfileFieldOrder.qml共享改动和app/workflow.py「以往反馈情况」列属工作区其他在改内容，未单独拆分，随本提交一并上传。截图与性能结果仍位于忽略目录output/，不随仓库分发。

用户可点击「调试重启」，进入「学员画像 → 管理字段」查看卡片拾取、1／2字段间插入、滚动和窄窗新增表单；运行时证据通过，审美与真实鼠标体感仍需用户自行评估。无需接触正式学员值、删除字段或真实企微即可查看视觉行为。
