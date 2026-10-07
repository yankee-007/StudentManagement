"""Build the independent learning overview prototype from read-only snapshots."""
import argparse
import json
import os
import sqlite3
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


def completion_snapshot(connection, batch, data, has_followup):
    records = connection.execute('SELECT student_id,name,snapshot,eligible FROM campaign_students WHERE batch_id=?', (batch,)).fetchall()
    flags = dict(connection.execute('SELECT student_id,status FROM campaign_followup_status WHERE batch_id=?', (batch,))) if has_followup else {}
    targets, reading = [], 0
    for sid, name, raw, eligible in records:
        snap = json.loads(raw)
        if snap.get('roster_status') == '在读' and not snap.get('is_placeholder'):reading += 1
        if eligible and (name or '').strip() and snap.get('wechat') == '是' and snap.get('roster_status') in ('', '在读') and not snap.get('is_placeholder'):
            targets.append((sid, snap))
    counts, followup = Counter(), Counter()
    unknown = 0
    for sid, snap in targets:
        if 'completed_courses' in snap:
            value = snap['completed_courses']
        else:
            legacy = re.fullmatch(r'(\d+)/\d+', str(snap.get('completed_total', '')))
            value = legacy.group(1) if legacy else None
        if not re.fullmatch(r'\d+', str(value)) or int(value) > 32:
            unknown += 1
            continue
        count = int(value)
        counts[count] += 1
        if flags.get(sid) == '是':followup[count] += 1
    total = len(targets)
    marked = sum(sid in flags for sid, snap in targets)
    summary = dict(total=total, marked=marked, yes=sum(flags.get(sid) == '是' for sid, snap in targets),
                   no=sum(flags.get(sid) == '否' for sid, snap in targets), unmarked=total-marked)
    opened = max([int(data.get('opened') or 0)] + [int(r['lesson']) for r in data.get('courses', [])])
    buckets = []
    if counts:
        for count in range(max([opened] + list(counts)), -1, -1):
            people = counts[count]
            cumulative = sum(n for k, n in counts.items() if k >= count)
            bucket = dict(count=count, people=people, cumulative=cumulative,
                          ratio=f'{100*people/total:.2f}%', cumulativeRate=f'{100*cumulative/total:.2f}%')
            if marked:bucket['followable'] = followup[count]
            buckets.append(bucket)
    notes = ['完课次数来自该批次学员保存的完成计数，不反推累计学习率。']
    if unknown:notes.append(f'{unknown}名催办学员未保存可用完成计数，不归入0次；比例仍以本次催办人数为分母。')
    if not marked:notes.append('本批次尚未填写可跟进标记，可跟进人数显示 —。')
    elif marked < total:notes.append(f'尚有{total-marked}人未填写，可跟进人数仅统计已确认是的学员。')
    return buckets, total, ' '.join(notes), summary, len(records), reading


def load_batches(connection, feedback_batch=None):
    batches = []
    has_followup = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_followup_status'").fetchone() is not None
    for row in connection.execute(
        "SELECT c.id,c.created_at,d.data FROM campaigns c "
        "LEFT JOIN campaign_dashboards d ON d.batch_id=c.id ORDER BY c.id"
    ):
        data = json.loads(row[2]) if row[2] else {}
        homework = {item['lesson']: item for item in data.get('homework', [])}
        lessons = []
        for course in sorted(data.get('courses', []) if data.get('version', 1) >= 2 else [], key=lambda item: item['lesson']):
            hw = homework.get(course['lesson'])
            if hw is None:continue
            try:
                cr = float(course['completedRate'].rstrip('%'))
                hr = float(hw['completedRate'].rstrip('%'))
            except (KeyError, ValueError, TypeError, AttributeError):continue
            lessons.append(dict(lesson=course['lesson'], course=cr, homework=hr,
                                gap=round(cr-hr, 2), courseDone=course.get('completed'),
                                homeworkDone=hw.get('completed')))
        completion, total, completion_notice, summary, members, reading = completion_snapshot(connection, row[0], data, has_followup)
        learning_notice = '' if lessons else ('本批次仅保存单节学习快照，无法还原第1～N节累计率。' if row[2] else '本批次未保存累计学习快照；学员成员与完成计数仍可查看。')
        batches.append(dict(id=row[0], time=row[1], total=data.get('total', reading),
                            lessons=lessons, completion=completion, members=members,
                            completionTotal=total, followupSummary=summary,
                            learningNotice=learning_notice,
                            completionNotice=completion_notice, notice=data.get('notice', '')))
    return batches


def main():
    default_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'LocalTools' / '学员催办维护名单'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path(os.environ.get('FOLLOWUP_DB', default_dir / 'followup.db')))
    parser.add_argument('--class-name', default='py169')
    parser.add_argument('--preview-batch', type=int, help='Use a specified historical batch for the dashboard review')
    args = parser.parse_args()
    if not args.db.is_file():
        raise SystemExit('Database missing; specify --db. No application or migration was started.')
    with sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        batches = load_batches(connection, args.preview_batch)
    if args.preview_batch is not None and not any(b['id'] == args.preview_batch for b in batches):
        raise SystemExit('Specified preview batch was not found.')
    payload = dict(className=args.class_name, batches=batches, previewBatch=args.preview_batch,
                   exportedAt=datetime.now().astimezone().isoformat(timespec='seconds'))
    folder = Path(__file__).resolve().parent
    template = (folder / 'overview_template.html').read_text(encoding='utf-8')
    echarts = (folder.parent / 'vendor/echarts.min.js').read_text(encoding='utf-8')
    encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    output = folder / 'learning-overview-local.html'
    output.write_text(template.replace('/*__ECHARTS__*/', echarts).replace('/*__DATA__*/', encoded), encoding='utf-8')
    print(f'Built {output.name}: {len(batches)} batches; aggregate snapshots only.')


if __name__ == '__main__':
    main()
