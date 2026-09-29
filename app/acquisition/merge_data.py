"""读取完课 JSON 和作业达标表，以学号合并为 T/F/N 数据。"""
import csv
import re
from pathlib import Path

from openpyxl import load_workbook

CLASS_COUNT = 32
FIELDS = ['学号', '姓名'] + [f'C{i}' for i in range(1, 33)] + [f'Z{i}' for i in range(1, 33)]


def identifier(value):
    if value is None or not str(value).strip():
        raise ValueError('学号为空，无法关联学员。')
    return str(value).strip()


def homework_flag(value):
    if value is None or not str(value).strip():
        return 'N'
    text = str(value).strip()
    if re.fullmatch(r'完成/\d+', text):
        return 'T'
    if text == '无/0' or re.fullmatch(r'(未完成|未达标)/\d+', text):
        return 'F'
    raise ValueError(f'无法识别的作业状态：{value!r}')


def read_homework(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if '达标记录' not in workbook.sheetnames:
            raise ValueError('作业文件缺少“达标记录”工作表。')
        rows = workbook['达标记录'].iter_rows(values_only=True)
        headers = next(rows, ())
        positions = {}
        courses = {}
        for index, value in enumerate(headers):
            label = str(value).strip() if value is not None else ''
            if label in positions:
                raise ValueError(f'作业表头重复：{label}')
            positions[label] = index
            if label.isdigit():
                number = int(label)
                if not 1 <= number <= CLASS_COUNT or number in courses:
                    raise ValueError(f'作业课次无效或重复：{label}')
                courses[number] = index
        for label in ('学号', '姓名', '学员状态'):
            if label not in positions:
                raise ValueError(f'作业表缺少字段：{label}')
        if not courses:
            raise ValueError('作业表缺少课次列。')
        students = {}
        for row in rows:
            if all(value is None for value in row):
                continue
            number = identifier(row[positions['学号']])
            if number in students:
                raise ValueError(f'作业表学号重复：{number}')
            status = str(row[positions['学员状态']]).strip()
            if status not in ('在读', '退课'):
                raise ValueError(f'未知作业学籍状态：{status}')
            students[number] = {
                'name': str(row[positions['姓名']] or '').strip(),
                'status': status,
                'flags': {i: homework_flag(row[column]) for i, column in courses.items()},
            }
        return students
    finally:
        workbook.close()


def completion_students(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
        raise ValueError('完课 JSON 缺少 rows 列表。')
    students = {}
    for student in payload['rows']:
        number = identifier(student.get('studentNo'))
        if number in students:
            raise ValueError(f'完课数据学号重复：{number}')
        if str(student.get('status')) not in ('-1', '0', '1', '2', '3', '4', '6', '7', '8'):
            raise ValueError(f'未知完课学籍状态：{student.get("status")}')
        students[number] = student
    return students


def merge_students(payload, homework):
    completion = completion_students(payload)
    rows = []
    for number in sorted(completion.keys() | homework.keys()):
        student = completion.get(number)
        assignment = homework.get(number)
        if student is not None and str(student['status']) != '0':
            continue
        if student is None and (assignment is None or assignment['status'] != '在读'):
            continue
        completion_name = str((student or {}).get('realname') or '').strip()
        homework_name = str((assignment or {}).get('name') or '').strip()
        if completion_name and homework_name and completion_name != homework_name:
            raise ValueError(f'学号 {number} 两平台姓名不一致（{completion_name} / {homework_name}），未更新；请核对平台资料。')
        name = completion_name or homework_name
        if not name:
            raise ValueError(f'学员缺少姓名：{number}')
        row = {'学号': number, '姓名': name}
        for i in range(1, CLASS_COUNT + 1):
            key = f'classNum_{i}'
            if student is not None and key not in student:
                raise ValueError(f'学员 {number} 缺少课程字段：{key}')
            row[f'C{i}'] = ('U' if student is None else 'N' if student[key] is None else
                            'T' if student[key] in ('直播', '录播') else 'F')
            row[f'Z{i}'] = (assignment['flags'].get(i, 'N') if assignment is not None and assignment['status']=='在读' else 'U')
        rows.append(row)
    stats = {
        '完课学员': len(completion), '作业学员': len(homework),
        '仅完课系统存在': len(completion.keys() - homework.keys()),
        '仅作业系统存在': len(homework.keys() - completion.keys()),
        '匹配但非双方在读': sum(
            str(completion[n]['status']) != '0' or homework[n]['status'] != '在读'
            for n in completion.keys() & homework.keys()),
        '双方在读并导出': sum(all(r[f'{p}1'] != 'U' for p in ('C','Z')) for r in rows),
    }
    return rows, stats


def write_csv(rows, output):
    output = Path(output)
    temporary = output.with_suffix(output.suffix + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
