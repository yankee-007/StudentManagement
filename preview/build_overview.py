"""Build the independent learning overview prototype from read-only snapshots."""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.feedback_status import is_reply


def load_batches(connection, feedback_batch=None):
    batches = []
    connection.create_function('feedback_is_reply', 2, is_reply)
    latest = connection.execute("SELECT MAX(id) FROM campaigns").fetchone()[0]
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
        for bucket in completion:
            bucket.pop('followable', None)
        if completion and row[0] in (latest, feedback_batch):
            opened = data.get('opened', max(bucket['count'] for bucket in completion))
            # Count each student once; export no identifiers or feedback text.
            reply_counts = dict(connection.execute(
                "SELECT MIN(COALESCE(CAST(json_extract(s.snapshot,'$.completed_courses') AS INTEGER),0),?),COUNT(*) "
                "FROM campaign_students s WHERE s.batch_id=? "
                "AND json_extract(s.snapshot,'$.roster_status')='在读' "
                "AND COALESCE(json_extract(s.snapshot,'$.is_placeholder'),0)=0 "
                "AND EXISTS(SELECT 1 FROM campaign_feedback f WHERE f.batch_id=s.batch_id "
                "AND f.student_id=s.student_id AND feedback_is_reply(f.content,f.kind)) GROUP BY 1", (opened, row[0])))
            for bucket in completion:
                value = sum(number for count, number in reply_counts.items() if count <= bucket['count'])
                capacity = sum(item['people'] for item in completion if item['count'] <= bucket['count'])
                if 0 <= value <= capacity:
                    bucket['followable'] = value
                else:
                    completion_notice = '回复人数与分布快照不一致，受影响的可跟进人数暂不展示。'
        batches.append(dict(id=row[0], time=row[1], total=data.get('total', 0),
                            lessons=lessons, completion=completion,
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
