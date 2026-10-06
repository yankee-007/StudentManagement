"""Compute statistics once when creating a campaign snapshot.

Version 3 adds the cumulative headcounts (全部已开课节次都完成的人数) and the
完课次数分布 (每个完成节数各有多少人) that the workbench 看板 shows. Both derive
from the same base flags as the cumulative rates, so the rate and the headcount
can never disagree.
"""


def _distribution(ids, completions, total, opened):
    """完成次数分布：每人完成 k 节的人数、累计人数、累计完课率。

    显示行 k=0..opened，因此完成节数超过本批已开课节次的人必须留在总数里，否则
    分母对不上；这些人计入 k=opened 一行。
    """
    counts = [0] * (opened + 1)
    if not total:
        return []
    for sid in ids:
        value = completions.get(sid, 0)
        counts[opened if value > opened else value] += 1
    rows = []
    cumulative = 0
    for count in range(opened, -1, -1):
        people = counts[count]
        cumulative += people
        rows.append(dict(count=count, people=people, cumulative=cumulative,
                         ratio=f'{people / total:.2%}' if total else '—',
                         cumulativeRate=f'{cumulative / total:.2%}' if total else '—'))
    return rows


def learning_dashboard(students, source):
    students=[s for s in students if s.get('roster_status')=='在读' and not s.get('is_placeholder')]
    total=len(students)
    ids=[s['student_id'] for s in students]
    flags=[source.get(sid,{}) for sid in ids]
    # 每人已完成的节数（按完成数分桶用），与累计率的 T 标记同源。
    totals={prefix:{sid:sum(source.get(sid,{}).get(f'{prefix}{i}')=='T' for i in range(1,33)) for sid in ids}
            for prefix in ('c','z')}
    result={'version':3,'total':total,'matched':sum(s['student_id'] in source and 'U' not in source[s['student_id']].values() for s in students)}
    for prefix,key in (('c','courses'),('z','homework')):
        rows=[]
        for lesson in range(1,33):
            values=[f.get(f'{prefix}{lesson}') for f in flags]
            completed=values.count('T')
            pending=values.count('F')
            if not completed and not pending:continue
            cumulative=sum(all(f.get(f'{prefix}{i}')=='T' for i in range(1,lesson+1)) for f in flags)
            rows.append(dict(lesson=lesson,pending=pending,completed=cumulative,
                singleCompleted=completed,singleRate=f'{completed/total:.2%}',
                pendingRate=f'{pending/total:.2%}',completedRate=f'{cumulative/total:.2%}',
                unopened=values.count('N'),unknown=sum(v not in ('T','F','N') for v in values)))
        result[key]=rows
    courses={r['lesson']:r for r in result['courses']}
    homework={r['lesson']:r for r in result['homework']}
    for row in result['courses']+result['homework']:
        lesson=row['lesson']
        row['difference']=(f"{(courses[lesson]['completed']-homework[lesson]['completed'])/total:.2%}"
                           if lesson in courses and lesson in homework else '—')
    # 累计口径：第 1～N 节全部完成，N＝已开课节次（该列有 T 或 F 记录的最大节次）。
    opened=result['courses'][-1]['lesson'] if result['courses'] else 0
    result['opened']=opened
    result['cumulativeCourse']=courses[opened]['completed'] if opened else 0
    result['cumulativeHomework']=homework[opened]['completed'] if opened and opened in homework else 0
    result['cumulative']=dict(opened=opened, courses=result['cumulativeCourse'], homework=result['cumulativeHomework'])
    result['completion']={'courses':_distribution(ids,totals['c'],total,opened),
                          'homework':_distribution(ids,totals['z'],total,opened)}
    return result
