"""Compute statistics once when creating a campaign snapshot."""


def learning_dashboard(students, source):
    students=[s for s in students if s.get('roster_status')=='在读' and not s.get('is_placeholder')]
    total=len(students)
    flags=[source.get(s['student_id'],{}) for s in students]
    result={'version':2,'total':total,'matched':sum(s['student_id'] in source and 'U' not in source[s['student_id']].values() for s in students)}
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
    return result
