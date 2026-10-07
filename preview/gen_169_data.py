"""Export class 169's real dashboard data (read-only) for the HTML preview.

Only lessons that actually exist in the stored snapshot are exported; lessons that
have not opened yet are not written as zeroes or estimates.
"""
import json
import os
import sqlite3
from pathlib import Path

# 正式库默认在 Qt AppLocalDataLocation 下；用环境变量可覆盖，不把机器专属路径写死入库。
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "LocalTools" / "学员催办维护名单"
DB = Path(os.environ.get("FOLLOWUP_DB", DEFAULT_DIR / "followup.db"))
SOURCE_BATCHES = [9, 10, 11, 12, 13]   # 走势对比用的最近若干次催办；缺失会在下面报错
TARGET_LESSONS = 32          # 课程总节数：考核线按满课时设定，图表只画已开课节次

if not DB.exists():
    raise SystemExit(f"找不到正式库：{DB}\n用 FOLLOWUP_DB=<路径> 指定，或先在本机启动一次应用生成 followup.db。")

# 只读打开：mode=ro 从根上排除写入，也避免触发任何迁移。
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

batches = []
for bid in SOURCE_BATCHES:
    campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (bid,)).fetchone()
    if campaign is None:
        raise SystemExit(f"批次 {bid} 不存在；该班被清理过或批次号变了，请调整 SOURCE_BATCHES。")
    data = json.loads(conn.execute("SELECT data FROM campaign_dashboards WHERE batch_id=?", (bid,)).fetchone()["data"])
    snapshots = {r["student_id"]: json.loads(r["snapshot"])
                 for r in conn.execute("SELECT student_id,snapshot FROM campaign_students WHERE batch_id=?", (bid,))}
    members = {sid: s for sid, s in snapshots.items()
               if s.get("roster_status") == "在读" and not s.get("is_placeholder")}
    batches.append(dict(id=bid, created=campaign["created_at"], dashboard=data, members=members))

current, previous = batches[-1], batches[-2]
data = current["dashboard"]
TOTAL = data["total"]

# --- only the lessons that are actually open in the stored snapshot ---------------
homework = {r["lesson"]: r for r in data["homework"]}
lessons = []
for row in sorted(data["courses"], key=lambda r: r["lesson"]):
    hw = homework.get(row["lesson"])
    if hw is None:
        continue
    lessons.append(dict(
        lesson=row["lesson"],
        course=float(row["completedRate"].rstrip("%")), homework=float(hw["completedRate"].rstrip("%")),
        gap=round(float(row["completedRate"].rstrip("%")) - float(hw["completedRate"].rstrip("%")), 2),
        courseDone=row["completed"], homeworkDone=hw["completed"],
        pending=row["pending"], pendingHomework=hw["pending"],
        unopened_course=row.get("unopened", 0), unopened_homework=hw.get("unopened", 0),
        unknown_course=row.get("unknown", 0), unknown_homework=hw.get("unknown", 0)))

OPEN = len(lessons)
funnel = []
for i, item in enumerate(lessons):
    done = item["courseDone"]
    partial = lessons[0]["courseDone"] - done if i else 0
    funnel.append(dict(lesson=item["lesson"], done=done, partial=partial,
                       zero=TOTAL - done - partial, pending=item["pending"],
                       pending_homework=item["pendingHomework"], gap=item["gap"]))

trend = []
for batch in batches:
    dash = batch["dashboard"]
    course = float(dash["courses"][-1]["completedRate"].rstrip("%"))
    home = float(dash["homework"][-1]["completedRate"].rstrip("%"))
    trend.append(dict(name=f"第{batch['id']}次", label=batch["created"][5:16], total=dash["total"],
                      courseRate=course, homeworkRate=home, gap=round(course - home, 2)))


def counters(members):
    return {sid: (int(s.get("completed_courses") or 0), int(s.get("completed_homework") or 0))
            for sid, s in members.items()}


before, after = counters(previous["members"]), counters(current["members"])
shared = sorted(set(before) & set(after))
movement = dict(shared=len(shared),
                improved=sum(1 for sid in shared if sum(after[sid]) > sum(before[sid])),
                flat=sum(1 for sid in shared if sum(after[sid]) == sum(before[sid])),
                regressed=sum(1 for sid in shared if sum(after[sid]) < sum(before[sid])),
                new=len(set(after) - set(before)), dropped=len(set(before) - set(after)))

GRADES = [dict(key="excellent", label="优秀", max=5, color="#12b76a"),
          dict(key="good", label="良好", max=10, color="#2f6fed"),
          dict(key="pass", label="及格", max=15, color="#f79009"),
          dict(key="fail", label="不合格", max=None, color="#d92d20")]


def grade_of(value):
    for item in GRADES:
        if item["max"] is not None and value <= item["max"]:
            return item
    return GRADES[-1]


grades_by_lesson = [grade_of(item["gap"]) for item in lessons]
counts = {g["key"]: sum(1 for x in grades_by_lesson if x["key"] == g["key"]) for g in GRADES}
worst_index = max(range(OPEN), key=lambda i: lessons[i]["gap"])

payload = dict(
    className="py169", total=TOTAL, targetLessons=TARGET_LESSONS, openLessons=OPEN,
    grades=GRADES, lessonGrades=[g["key"] for g in grades_by_lesson], gradeCounts=counts,
    gradeSummary=" · ".join(f"{g['label']} {counts[g['key']]} 节" for g in GRADES if counts[g["key"]]),
    lessonsList=[item["lesson"] for item in lessons],
    course=[item["course"] for item in lessons], homework=[item["homework"] for item in lessons],
    gap=[item["gap"] for item in lessons],
    completed=[item["courseDone"] for item in lessons], completed_homework=[item["homeworkDone"] for item in lessons],
    pending=[item["pending"] for item in lessons], pendingHomework=[item["pendingHomework"] for item in lessons],
    unopened=sum(item["unopened_course"] + item["unopened_homework"] for item in lessons),
    unknown=sum(item["unknown_course"] + item["unknown_homework"] for item in lessons),
    detail=lessons, funnel=funnel, trend=trend, movement=movement,
    worst=dict(lesson=lessons[worst_index]["lesson"], gap=lessons[worst_index]["gap"],
               grade=grades_by_lesson[worst_index]["label"]),
    last=dict(lesson=lessons[-1]["lesson"], course=lessons[-1]["course"], homework=lessons[-1]["homework"],
              gap=lessons[-1]["gap"], grade=grades_by_lesson[-1]["label"], gradeKey=grades_by_lesson[-1]["key"],
              pending=lessons[-1]["pending"], pendingHomework=lessons[-1]["pendingHomework"],
              courseDone=lessons[-1]["courseDone"], homeworkDone=lessons[-1]["homeworkDone"],
              dCourse=round(lessons[-1]["course"] - trend[-2]["courseRate"], 2),
              dHomework=round(lessons[-1]["homework"] - trend[-2]["homeworkRate"], 2),
              dGap=round(lessons[-1]["gap"] - trend[-2]["gap"], 2)),
)
conn.close()
Path("preview/dashboard-data-169.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print("openLessons:", OPEN, "| lessons:", payload["lessonsList"], "| total:", TOTAL)
print("grades:", json.dumps(counts, ensure_ascii=False), "|", payload["gradeSummary"])
print("last:", json.dumps(payload["last"], ensure_ascii=False))
print("worst:", json.dumps(payload["worst"], ensure_ascii=False))
print("unopened/unknown totals:", payload["unopened"], payload["unknown"])
print("movement:", movement)
print("gaps:", payload["gap"])
