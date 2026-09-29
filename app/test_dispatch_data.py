"""Build isolated test campaigns through the production roster/import/plan path."""
__test__ = False
import re
import uuid
from .database import Database
from .repository import StudentRepository
from .roster_sync import sync_roster
from .importer import import_rows
from .campaigns import CampaignStore
from . import sending_store as receipts


def lesson_numbers(value):
    text=str(value or '').strip()
    if not text:return []
    parts=re.split(r'[,，、\s]+',text)
    if any(not v.isdigit() or not 1<=int(v)<=32 for v in parts):
        raise ValueError('课次只能为 1–32，用逗号分隔，例如 1,2,3')
    values=[int(v) for v in parts]
    if len(values)!=len(set(values)):raise ValueError('课次不能重复')
    return sorted(values)


def build_test_campaign(path,people,prefix,template):
    if not 1<=len(people)<=20:raise ValueError('测试名单请填写 1–20 人')
    namespace='TEST'+uuid.uuid4().hex[:12]
    roster=[];source=[]
    names=set()
    for i,person in enumerate(people,1):
        name=str(person.get('name','')).strip()
        if not name or any(c in name for c in '\r\n\0'):raise ValueError(f'第 {i} 行请填写有效测试人员姓名')
        if name in names:raise ValueError('测试人员姓名重复，无法唯一定位联系人')
        names.add(name)
        sid=f'{namespace}{i:03d}'
        row={'学号':sid,'姓名':name}
        pending=0
        for p,key,total in [('c','courses','completed_courses'),('z','homework','completed_homework')]:
            missing=lesson_numbers(person.get(key,''))
            count=str(person.get(total,'0')).strip()
            if not count.isdigit() or not 0<=int(count)<=32-len(missing):
                raise ValueError(f'第 {i} 行完成数量无效；完成数＋未完成数不能超过 32')
            completed=[n for n in range(1,33) if n not in missing][:int(count)]
            row.update({f'{p}{n}':'F' if n in missing else 'T' if n in completed else 'N' for n in range(1,33)})
            pending+=len(missing)
        if not pending:raise ValueError(f'第 {i} 行没有欠交项目，不符合本次催办规则')
        roster.append(dict(student_id=sid,name=name,source='测试输入',status='在读'))
        source.append(row)
    # All input validation precedes writing. This database is never registered as a class.
    db=Database(path)
    repo=StudentRepository(db)
    store=CampaignStore(db,repo)
    receipts.recover(db)
    sync_roster(db,dict(termId='SEND_TEST',termNo=namespace),roster)
    for row in roster:repo.update_profile_field(row['student_id'],'微信','是')
    import_rows(db,source)
    batch=store.create('测试群发（非真实学员数据）',template)
    receipts.save_config(store,batch,prefix,template)
    return store,batch
