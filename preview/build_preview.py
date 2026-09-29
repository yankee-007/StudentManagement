"""Inject the class-169 dataset + ECharts into the template."""
from pathlib import Path

data = Path("preview/dashboard-data-169.json").read_text(encoding="utf-8")
template = Path("preview/dashboard_template.html").read_text(encoding="utf-8")
echarts = Path("vendor/echarts.min.js").read_text(encoding="utf-8")
html = template.replace("/*__ECHARTS__*/", echarts).replace("/*__DATA__*/", data)
out = Path("preview/dashboard-169.html")
out.write_text(html, encoding="utf-8")
print("written", out, len(html), "bytes")
