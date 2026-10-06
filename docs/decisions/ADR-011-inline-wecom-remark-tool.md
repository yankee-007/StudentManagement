# ADR-011: 把备注批改的 OCR 工具内联进 app/，不再依赖 wecomrename/ 目录

## Status

Accepted。2026-10-01 由用户要求：仓库首次提交前确认「工具核心功能是否已嵌入项目，不再依赖后再不提交该工具」。核查结论是**当时并未嵌入**（运行时按路径加载），因此按用户选择执行内联。

## Context

「备注批改」模块原本分成两半：

- `app/wecom_renamer.py`：搜索联系人、`Ctrl+O` 浮窗读标题、`remark_scan` 判定链、状态持久化、F11/暂停。
- `wecomrename/wecom_remark.py`：真正的 OCR 改名（`RapidOCREngine`、`WeComRemarkChanger`、`change_wecom_remark`，约 580 行），另有自己的 `README.md`、`requirements.txt`、`t.py` 试验脚本，以及含真实学员姓名的 `evidence/` 截图目录。

连接方式是**运行期按文件路径动态加载**：

```python
path = ROOT / 'wecomrename' / 'wecom_remark.py'
if not path.is_file():
    raise RemarkRenameError(f'缺少备注修改脚本：{path}')
spec = importlib.util.spec_from_file_location('wecom_remark', path)
```

这带来三个实际问题：

1. **删除即失效但不报错于测试**：`tests/test_remark_renamer.py` 用 mock 替换 `load_change_remark`，所以把 `wecomrename/` 拿掉后测试仍然全绿，功能却会在真机上直接报「缺少备注修改脚本」——「测试通过」不能证明该目录可以被排除。
2. **依赖声明分散**：OCR 依赖写在 `wecomrename/requirements.txt`，主 `requirements.txt` 只重复了一部分注释，装机时容易漏。
3. **把含真实学员姓名的目录带进版本库的风险**：该目录里的 `README.md`、`t.py`、截图取证目录都出现过真实姓名与备注格式，属于不该公开的内容。

## Options Considered

1. **原样提交整个 `wecomrename/`**：功能零风险，但真实姓名与取证截图需要逐个清洗，且「两个 requirements、一个目录只为装一个模块」的结构继续存在。用户否决。
2. **不提交 `wecomrename/`**（加进 .gitignore）：会让仓库里「备注批改」成为不可运行的残缺功能，且真机报错点被推到运行期。核查后确认不可接受。
3. **内联进 `app/wecom_remark.py`（本决定）**：把模块搬进应用包，`load_change_remark` 改为延迟 `from .wecom_remark import change_wecom_remark`；依赖并入根 `requirements.txt`；删除 `wecomrename/`。
4. **保留动态加载但改路径**：只是把问题挪个位置，动态加载的探测性失败与「测试绿而功能坏」的隐患不变。

## Decision

- `wecomrename/wecom_remark.py` 原样迁入 `app/wecom_remark.py`（逻辑不改，保留其 `__main__` CLI 入口，`python -m app.wecom_remark "旧备注" "新备注" --dry-run` 仍可用）。
- `app/wecom_renamer.py::load_change_remark()` 改成**函数内延迟 import**：

  ```python
  try:
      from .wecom_remark import change_wecom_remark
  except Exception as exc:
      raise RemarkRenameError(f'备注修改脚本加载失败：{exc}') from exc
  return change_wecom_remark
  ```

  延迟 import 保留了原有的「启动期不加载 OCR/PyAutoGUI」特性；把 ImportError 归一成 `RemarkRenameError`，与既有的「缺少备注修改脚本」错误类型一致，调用方与 QML 提示不用改。
- 依赖并入根 `requirements.txt`（`rapidocr`、`onnxruntime`、`pyperclip`、`pygetwindow`、`Pillow`，均带 `sys_platform == 'win32'` 标记）；删除 `wecomrename/requirements.txt`。
- 删除整个 `wecomrename/`；新增 `.gitignore` 规则 `wecom_remark_evidence/`（过程截图仍含真实姓名，不入版本库）。
- 真实姓名示例统一替换为虚构名（`py175示例学员`、`示例学员/新生`）：涉及 `app/wecom_remark.py` 文档串、`app/remark_scan.py` 注释、`tests/test_remark_renamer.py` 夹具、`README.md`、ADR-008。

## Rationale

判断依据是**运行期真实依赖**而不是「测试是否通过」：`load_change_remark` 读的是磁盘路径，`tests/test_remark_renamer.py` 又把该函数 mock 掉，所以只有读源码才能发现依赖仍然存在。这正是本 ADR 要留下的教训：判断「某目录能不能不提交」，必须追到运行期加载点，不能看测试脸色。

选择内联而不是保留独立目录，是因为该模块只服务这一个功能，且已经通过 `change_wecom_remark` 这一稳定入口被调用；搬进包内后，导入失败会在真正改名时以项目自己的错误类型暴露，而不是「文件不存在」的路径错误。延迟 import 让「不跑备注批改就不加载 OCR」这一既有性能与兼容性行为保持不变。

## Consequences

- `wecomrename/` 不再存在；`app/wecom_remark.py` 是 OCR 改名的唯一实现位置。
- **真实企微端到端验收仍需人工在场先跑 1 人**：本次改动动了真实改名路径的加载方式，`tests/test_remark_renamer.py`（28 项，mock 驱动）与 `tests/smoke_remark_renamer.py`（只加载界面）都不覆盖真实 OCR 与按键序列。
- 失败提示文案从「缺少备注修改脚本：<路径>」变为「备注修改脚本加载失败：<原因>」；`RemarkRenameError` 类型不变。
- `wecom_remark_evidence/` 继续作为运行期举证目录，并已在 `.gitignore` 中排除。

## Rejected / Failed Approaches

- 靠「测试是否通过」判断该目录可否删除：mock 会让删除后的测试依旧全绿，必须读 `load_change_remark` 才能发现依赖。
- 顶层 `from .wecom_remark import change_wecom_remark`：会让所有入口（含离屏测试、无 OCR 依赖的环境）在启动期就加载 PyAutoGUI/RapidOCR，破坏既有的延迟加载行为。

## Related Areas

app/wecom_remark.py（新）、app/wecom_renamer.py（`load_change_remark`）、requirements.txt、.gitignore；tests/test_remark_renamer.py、tests/smoke_remark_renamer.py；ADR-008。
