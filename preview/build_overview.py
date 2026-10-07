"""Build the independent learning overview prototype from read-only snapshots."""
import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def load_batches(connection, feedback_batch=None):
    batches = []
    has_followup = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_followup_status'").fetchone() is not None
    for row in connection.execute(
        "SELECT c.id,c.created_at,d.data FROM campaigns c "
        "JOIN campaign_dashboards d ON d.batch_id=c.id ORDER BY c.id"
    ):
        data = json.loads(row[2])
        homework = {item['lesson']: item for item in data.get('homework', [])}
        lessons = []
        for course in sorted(data.get('courses', []), key=lambda item: item['lesson']):
            hw = homework.get(course['lesson'])
            if hw is None:
                continue
            try:
                cr = float(course['completedRate'].rstrip('%'))
                hr = float(hw['completedRate'].rstrip('%'))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            lessons.append(dict(lesson=course['lesson'], course=cr, homework=hr,
                                gap=round(cr-hr, 2), courseDone=course.get('completed'),
                                homeworkDone=hw.get('completed')))
        completion = [dict(bucket) for bucket in data.get('completion', {}).get('courses', [])] if data.get('version', 0) >= 3 else []
        completion_notice = ''
        completion_total = 0
        for bucket in completion:
            bucket.pop('followable', None)
        if completion:
            opened = data.get('opened', max(bucket['count'] for bucket in completion))
            # Match the historical workbench's targets view, independently of its column filters.
            target_counts = dict(connection.execute(
                "SELECT MIN(CAST(json_extract(s.snapshot,'$.completed_courses') AS INTEGER),?),COUNT(*) "
                "FROM campaign_students s WHERE s.batch_id=? "
                "AND s.eligible=1 AND TRIM(s.name)!='' "
                "AND json_extract(s.snapshot,'$.wechat')='是' "
                "AND json_extract(s.snapshot,'$.roster_status') IN ('','在读') "
                "AND COALESCE(json_extract(s.snapshot,'$.is_placeholder'),0)=0 "
                "AND json_extract(s.snapshot,'$.completed_courses') NOT IN ('','未获取') GROUP BY 1", (opened, row[0])))
            completion_total = sum(target_counts.values())
            followup_counts = {}
            if has_followup:
                followup_counts = dict(connection.execute(
                    "SELECT MIN(CAST(json_extract(s.snapshot,'$.completed_courses') AS INTEGER),?),COUNT(*) "
                    "FROM campaign_students s JOIN campaign_followup_status f "
                    "ON f.batch_id=s.batch_id AND f.student_id=s.student_id "
                    "WHERE s.batch_id=? AND s.eligible=1 AND TRIM(s.name)!='' AND f.status='是' "
                    "AND json_extract(s.snapshot,'$.wechat')='是' "
                    "AND json_extract(s.snapshot,'$.roster_status') IN ('','在读') "
                    "AND COALESCE(json_extract(s.snapshot,'$.is_placeholder'),0)=0 "
                    "AND json_extract(s.snapshot,'$.completed_courses') NOT IN ('','未获取') GROUP BY 1", (opened, row[0])))
            for bucket in completion:
                count = bucket['count']
                people = target_counts.get(count, 0)
                cumulative = sum(n for k, n in target_counts.items() if k >= count)
                bucket.update(people=people, cumulative=cumulative,
                              ratio=f'{100*people/completion_total:.2f}%' if completion_total else '—',
                              cumulativeRate=f'{100*cumulative/completion_total:.2f}%' if completion_total else '—')
                if has_followup:bucket['followable'] = followup_counts.get(count, 0)
        batches.append(dict(id=row[0], time=row[1], total=data.get('total', 0),
                            lessons=lessons, completion=completion,
                            completionTotal=completion_total,
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
        raise SystemExit('Specified preview batch has no dashboard snapshot.')
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
