# 看板预览（HTML 原型）

在浏览器中直接打开 `dashboard-169.html` 即可（图表库已内嵌，无需联网）。

| 文件 | 说明 |
| --- | --- |
| `dashboard-169.html` | **班级 py169 真实数据**看板（已开课 4 节，滑块可平移／缩放） |
| `dashboard-data-169.json` | 169 班数据集，由 `gen_169_data.py` 从正式库只读导出 |
| `dashboard_template.html` | 页面模板，占位符 `/*__ECHARTS__*/` 与 `/*__DATA__*/` |
| `gen_169_data.py` | 只读打开 followup.db，导出真实节次数据 |
| `build_preview.py` | 注入模板生成 dashboard-169.html |
| `check_preview.js` | 无头自检：图表数、数据点数、考核线、堆叠合计 |
| `shoot_preview.py` | Chrome 无头截图到 docs/preview-dashboard-history |
| `dashboard-32*.html` | 早期纯虚拟数据原型（32 节、无考核线），仅作对照，已不反映当前设计 |

## 数据口径

- 只统计**在读**真实学员，不含退课／冻结／补位。
- 累计完课率／作业率 = 第 1～N 节全部完成的人数 ÷ 在读人数。
- 差值 = 累计完课率 − 累计作业率；考核线：**优秀 ≤5pp / 良好 ≤10pp / 及格 ≤15pp / 不合格 >15pp**。
- **只写已开课的节次**：本班当前为第 1、2、3、4 节，未开课节次不写入、不参与统计（课程总节数 32 节，
  仅用于说明考核线适用范围）。
- 全部取自最近一次催办的真实冻结快照；历史批次只读，不受后续获取影响。

## 重新生成

```powershell
python preview/gen_169_data.py      # 只读导出真实数据
python preview/build_preview.py     # 生成 dashboard-169.html
node   preview/check_preview.js     # 无头自检
python preview/shoot_preview.py     # 截图
```
