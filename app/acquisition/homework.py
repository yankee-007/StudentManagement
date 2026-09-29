"""作业平台班级目录和达标表采集。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import requests

from .fixed_settings import HOMEWORK
from .homework_auth import load_sessionid, login, fetch_csrf_token
from .merge_data import read_homework

BASE = HOMEWORK['base_url'].rstrip('/')


class HomeworkClient:
    def __init__(self, username: str, password: str, session_path: str | Path):
        if not username or not password:
            raise ValueError('请先在设置中保存作业平台账号和密码。')
        self.username, self.password = username, password
        self.session_path = Path(session_path)
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessionid = load_sessionid(username, password, session_file=self.session_path)
        self.csrf = fetch_csrf_token()

    def _request(self, method, path, **kwargs):
        for attempt in range(2):
            response = requests.request(method, BASE + path, headers={**HOMEWORK['headers'], 'Origin': BASE, 'Referer': BASE + '/admin/records',
                **({'X-CSRFToken': self.csrf} if self.csrf else {})},
                cookies={'sessionid': self.sessionid, **({'csrftoken': self.csrf} if self.csrf else {})}, timeout=HOMEWORK['timeout'], **kwargs)
            if response.status_code in (401, 403) and attempt == 0:
                self.csrf = fetch_csrf_token()
                self.sessionid = login(self.username, self.password, session_file=self.session_path)
                continue
            response.raise_for_status()
            return response
        raise ValueError('作业平台登录失败。')

    def classes(self):
        payload = self._request('GET', '/api/admin/classes').json()
        if not isinstance(payload, dict) or str(payload.get('code', 0)) not in ('0', '200') or not isinstance(payload.get('data'), list):
            raise ValueError('作业班期接口数据格式不正确。')
        result = []
        for row in payload['data']:
            if not isinstance(row, dict) or row.get('id') is None:
                continue
            result.append({'id': int(row['id']), 'name': str(row.get('name') or ''),
                           'course_ids': [int(v) for v in row.get('primary_course_ids', []) if str(v).isdigit()]})
        return result

    def records(self, class_id: int, course_id: int):
        response = self._request('POST', '/api/admin/achievement-record-exports', json={'course_id': course_id, 'class_id': class_id})
        if not response.content.startswith(b'PK\x03\x04'):
            raise ValueError('作业平台未返回有效 XLSX，旧数据未覆盖。')
        return read_homework(BytesIO(response.content))
