from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"无法识别 CSV 编码：{last_error}")


def pending_from_row(row: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    courses: list[str] = []
    homework: list[str] = []
    ordered: list[str] = []
    normalized = {str(k).strip().lower(): str(v or "").strip().upper() for k, v in row.items() if k}
    for lesson in range(1, 33):
        if normalized.get(f"c{lesson}") == "F":
            item = f"第{lesson}节完课"
            courses.append(item)
            ordered.append(item)
        if normalized.get(f"z{lesson}") == "F":
            item = f"第{lesson}节作业"
            homework.append(item)
            ordered.append(item)
    return courses, homework, ordered


def import_csv(db: Database, path: str | Path) -> dict[str, int]:
    return import_rows(db, read_csv_rows(path))


def import_rows(db: Database, rows: list[dict[str, str]]) -> dict[str, int]:
    if not rows:
        return {"rows": 0, "inserted": 0, "updated": 0}
    required = {"学号", "姓名"}
    if not required.issubset(rows[0]):
        raise ValueError("CSV 缺少必需列：学号、姓名")
    now = datetime.now().isoformat(timespec="seconds")
    inserted = updated = 0
    seen: set[str] = set()
    with db.connect() as conn:
        profiles = {r['student_id']: dict(r) for r in conn.execute('SELECT p.student_id,r.name FROM profiles p JOIN class_roster r ON r.student_id=p.student_id')}
        matched_rows = []
        mismatched = unknown = 0
        if profiles:
            conn.execute('INSERT OR IGNORE INTO reminder_data(student_id) SELECT student_id FROM profiles')
        conn.execute("UPDATE reminder_data SET matched=0,sync_state='本次未获取，保留原值'")
        for line_no, row in enumerate(rows, start=2):
            student_id = str(row.get("学号") or "").strip()
            name = str(row.get("姓名") or "").strip()
            if not student_id or not name:
                raise ValueError(f"第 {line_no} 行缺少学号或姓名")
            if student_id in seen:
                raise ValueError(f"CSV 中学号重复：{student_id}")
            seen.add(student_id)
            if profiles:
                profile = profiles.get(student_id)
                if not profile:
                    unknown += 1
                    continue
                if profile['name'] != name:
                    mismatched += 1
                    conn.execute("UPDATE reminder_data SET sync_state='姓名不一致，未更新' WHERE student_id=?", (student_id,))
                    continue
                flags = {str(k).strip().lower(): str(v or '').strip().upper() for k,v in row.items() if k}
                if any(flags.get(f'{p}{i}', '') not in ('T','F','N','U','') for p in ('c','z') for i in range(1,33)):
                    raise ValueError(f'第 {line_no} 行学习状态无效，未更新')
                if any(f'{p}{i}' not in flags for p in ('c','z') for i in range(1,33)):
                    raise ValueError('获取结果缺少课程/作业列，未更新')
            flags = {str(k).strip().lower(): str(v or 'N').strip().upper() or 'N'
                     for k,v in row.items() if k and str(k).strip().lower() in {f'{p}{i}' for p in ('c','z') for i in range(1,33)}}
            fields = {}
            for prefix, total, missing in [('c','合计完课','差的课程'),('z','合计作业','差的作业')]:
                fields[total] = None if any(flags.get(f'{prefix}{i}') == 'U' for i in range(1,33)) else sum(flags.get(f'{prefix}{i}') == 'T' for i in range(1,33))
                fields[missing] = ','.join(str(i) for i in range(1,33) if flags.get(f'{prefix}{i}') == 'F')
            matched_rows.append(row)
            courses, homework, items = pending_from_row(row)
            exists = conn.execute('SELECT 1 FROM students WHERE student_id=?',(student_id,)).fetchone()
            old_row = conn.execute('SELECT data FROM reminder_data WHERE student_id=?',(student_id,)).fetchone()
            old = json.loads(old_row[0]) if old_row else {}
            old_list = json.loads(old.get('pending_items') or '[]')
            old_items = set(old_list)
            current = set(items)
            values: dict[str, Any] = {
                "pending_courses": json.dumps(courses, ensure_ascii=False),
                "pending_homework": json.dumps(homework, ensure_ascii=False),
                "pending_items": json.dumps(items, ensure_ascii=False),
                "pending_count": len(items),
                "new_f": json.dumps([x for x in items if x not in old_items], ensure_ascii=False),
                "persistent_f": json.dumps([x for x in items if x in old_items], ensure_ascii=False),
                "resolved_f": json.dumps([x for x in old_list if x not in current], ensure_ascii=False),
                "last_sync_at": now, "system_fields": fields,
            }
            conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?) ON CONFLICT(student_id) DO UPDATE SET name=excluded.name',
                         (student_id,name,now))
            conn.execute("INSERT OR IGNORE INTO class_roster(student_id,term_id,ordinal,name,status) VALUES(?,'',0,?,'')",(student_id,name))
            conn.execute('INSERT INTO reminder_data VALUES(?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET data=excluded.data,flags=excluded.flags,matched=1,sync_state=excluded.sync_state',
                         (student_id,json.dumps(values,ensure_ascii=False),json.dumps(flags),1,('部分获取，完课或作业数据缺失 ' if 'U' in flags.values() else '已匹配 ')+now))
            if exists:
                updated += 1
            else:
                inserted += 1
        snapshot = [{"student_id": str(r['学号']).strip(), "flags": {
            str(k).lower(): str(v or 'N').strip().upper() or 'N'
            for k, v in r.items() if k and str(k).lower() in {f'{p}{i}' for p in ('c','z') for i in range(1,33)}
        }} for r in matched_rows]
        conn.execute("INSERT INTO settings(key,value) VALUES('snapshot',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(snapshot),))
    return {"rows": len(rows), "inserted": inserted, "updated": updated,
            "matched": len(matched_rows), "mismatched": mismatched, "unknown": unknown,
            "missing": len(set(profiles) - seen)}
