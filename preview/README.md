# 看板预览（HTML 原型，本地生成，不入库）

> `/preview/dashboard-169.html` 与 `/preview/dashboard-data-*.json` 已被 .gitignore 排除（见 .gitignore 第 42–44 行），
> 因为真实班级数据的预览页可能含班级信息。这些文件只在本机用于人工评审。

打开 `dashboard-169.html` 即可查看（图表库已内嵌，离线可用）。

| 文件 | 说明 | 是否入库 |
| --- | --- | --- |
| `dashboard-169.html` | 班级 py169 真实数据看板（已开课 4 节，滑块可平移／缩放） | 否（.gitignore） |
| `dashboard-data-169.json` | 169 班数据集，由 `gen_169_data.py` 只读导出 | 否（.gitignore） |
| `dashboard_template.html` | 页面模板，占位符 `/*__ECHARTS__*/` 与 `/*__DATA__*/` | 是 |
| `build_preview.py` | 注入模板生成 `dashboard-169.html` | 是 |
| `gen_169_data.py` | 只读打开 followup.db，导出真实节次数据 | 是 |
| `check_preview.js` | 无头自检：图表数、数据点数、考核线、堆叠合计 | 是 |
| `shoot_preview.py` | Chrome 无头截图（输出到被忽略的 docs/preview-dashboard-history） | 是 |
| `dashboard-32*.html` | 早期纯虚拟数据原型（32 节、无考核线），仅作对照 | 否（.gitignore） |

## 数据口径

- 只统计**在读**真实学员，不含退课／冻结／补位。
- 累计完课率／作业率 = 第 1～N 节全部完成的人数 ÷ 在读人数。
- 差值 = 累计完课率 − 累计作业率；考核线：**优秀 ≤5pp / 良好 ≤10pp / 及格 ≤15pp / 不合格 >15pp**。
- **只写已开课的节次**：本班当前为第 1、2、3、4 节；未开课节次不写入、不参与统计
  （课程总节数 32 节，仅用于说明考核线适用范围）。
- 全部取自最近一次催办的真实冻结快照；历史批次只读，不受后续获取影响。

## 重新生成

```powershell
python preview/gen_169_data.py      # 只读导出真实数据
python preview/build_preview.py     # 生成 dashboard-169.html
node   preview/check_preview.js     # 无头自检
python preview/shoot_preview.py     # 截图
```

## 待用户确认（尚未进入正式实现）

1. 考核档位按**节次**判定，还是给班级一个**总评**（建议用最新已开课节次的差值）。
2. 接入正式 QML 看板的形态：考核带 + 滑块交互（QtCharts 或 RangeSlider）。
3. 是否需要把逐节考核结果写入批次快照（会影响存储格式，需按 ADR-004/006 评审）。
