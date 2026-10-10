# Qt 布局、剪贴板与字体警告及 main 开发基线

- Identity: TASK-20261010-4e120e797236；done；2026-10-10 16:57 +08:00。
- Requirement: 定位并修复用户报告的递归布局、剪贴板重试、字体回退警告；顶部「重新获取课程和学员」在全部可切换班期的模块显示；验证后将当前分支合并到 main，此后以 main 为开发基准。用户本轮明确授权本地集成和切换，不包含远端上传。
- Baseline: codex/daily-workspace / 77d77bf；工作区和暂存区干净；main 为 dafb522，是当前 HEAD 的祖先，现有分支多 5 条提交。
- Workspace: 单 Agent 串行写入；当前工作区已切换 main，codex/daily-workspace 保留在 57cca8f。其他 detached worktree 不属于本任务，未修改。
- Snapshot: 画像搜索框改为依据外层面板宽度计算，消除布局自身宽度反馈。顶部获取按钮显示与启用状态跟随班期切换框。移除群发名单隐藏 TextEdit 剪贴板中转；Windows 名单文本和附件读取仅访问所需原生格式，锁占用时提示重试，保留消息和草稿；其他平台/离屏沿用 Qt。字体补充 Nirmala UI/表情等已安装可缩放回退并优先 outline，仅过滤 font.db 的 info 候选探测，保留 warning/error。
- Findings: 全局 Qt 诊断与布局 debug 定位到 ProfileModule 搜索行初始化时宽度按一半递增（76→114→133），原 QQmlEngine warnings 没有捕获该诊断。独立 Windows 绘图复现 script 19（Malayalam）候选字体 info；ContextFontMerging 会在表情回退时遍历到 Fixedsys/System/Terminal 并触发 DirectWrite 错误，最终没有启用此策略。Qt 源码说明剪贴板重试由外部锁导致 OLE 读取失败，不能保证原生 Qt 输入控件在外部占用时永不输出系统重试；本次没有隐藏此类警告。用户不能提供具体触发步骤。
- Verification: Python 3.11 / PySide6 6.8.3。剪贴板/群发中心/群发交互 31 项单元通过；群发输入（含文件、锁占用保留草稿）和完整群发交互真实 QML 冒烟通过。新全局诊断冒烟覆盖启动及 54 组主题/窗口/模块组合，七个班期模块实际点击、忙碌保护、名单读取失败保留数据均通过；亮暗宽窄中文截图已检查。独立 Windows 字体冒烟验证中文/英文/表情/Malayalam 无缺失 glyph 或 DirectWrite 错误，且字体 warning 仍可输出。班期切换冒烟通过。最终按钮互斥条件验证通过；main / 57cca8f 上再次执行全局 QML 冒烟、原生字体冒烟及 7 项剪贴板单元，均通过。
- Handoff: 修复提交 57cca8f，已将本地 main 从 dafb522 正常快进到 57cca8f（包含原 5 条提交和本轮修复），没有合并节点或历史改写；切换后 main 与源分支代码树一致。默认 main 已写入 AGENTS 和策略，原待人工验收任务保留验收状态。未推送；后续从 main 恢复，可点击调试重启加载。正式平台/企微未访问，原用户环境的触发过程不明确，保留上述 Qt 输入框与外部剪贴板占用边界。
