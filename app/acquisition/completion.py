"""追光鲸鱼登录、班期名单与完课采集。"""
from __future__ import annotations

import time
import hashlib
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path
from urllib.parse import unquote_plus, urlencode, urlsplit

import requests
from bs4 import BeautifulSoup

from .fixed_settings import COMPLETION

BASE = COMPLETION['base_url'].rstrip('/')
LESSON_PATH = '/jihua/term/termXeClass/termStudentLiveData'
AUTH_WORDS = ('未登录', '未登陆', '没有登录', '没有登入', '请登录', '请先登录', '登录失效', '登录过期', '登陆过期', '无权限', '没有权限', '权限不足', '认证失败', 'unauthorized', 'forbidden', 'not logged in')
STATUS_LABELS = {'-1': '预备', '0': '在读', '1': '冻结', '2': '已退课', '3': '重修转班', '4': '冻结转班', '6': '强退', '7': '超时解冻', '8': '降班'}
TYPE_LABELS = {'0': '新生', '1': '重修', '2': '冻转'}


def _auth_failed(response, payload):
    if response.status_code in (401, 403) or any(x in urlsplit(response.url).path.lower() for x in ('/login', '/auth/', '/unauth')):
        return True
    if isinstance(payload, dict):
        msg = str(payload.get('msg') or '') + str(payload.get('message') or '')
        return str(payload.get('code')) in ('401', '403') or any(x in msg.lower() for x in AUTH_WORDS)
    return any(x in response.text.lower() for x in (*AUTH_WORDS, '扫码登录', 'type="password"', 'login.dingtalk.com'))


class CompletionClient:
    def __init__(self, username: str, password: str, cookie_path: str | Path):
        if not username or not password:
            raise ValueError('请先在设置中保存追光鲸鱼账号和密码。')
        self.username, self.password = username, password
        base_path = Path(cookie_path)
        suffix = hashlib.sha256(username.encode('utf-8')).hexdigest()[:16]
        self.cookie_path = base_path.with_name(base_path.stem + '_' + suffix + base_path.suffix)
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.refreshed = False
        jar = MozillaCookieJar(str(self.cookie_path))
        try:
            jar.load(ignore_discard=True)
        except (OSError, LoadError):
            self.login()
        else:
            self.session.cookies.update(jar)
            if not any(c.name == 'JSESSIONID' and not c.is_expired() for c in jar):
                self.login()

    def close(self):
        self.session.close()

    def login(self):
        auth = COMPLETION['auth']
        headers = {'User-Agent': auth['user_agent']}
        session = requests.Session()
        response = session.get(BASE + auth['login_path'], headers=headers, timeout=COMPLETION['timeout'])
        response.raise_for_status()
        scripts = BeautifulSoup(response.text, 'lxml').find_all('script')
        try:
            qr_url = scripts[2].text.split('\n')[1].split(' = ')[1][1:-2]
            state = unquote_plus(qr_url.split('=')[-1]).split('=')[-1]
        except (IndexError, AttributeError):
            raise ValueError('追光鲸鱼登录页面已变化，请检查登录方式。') from None
        ding = auth['dingtalk_base_url'].rstrip('/')
        oauth = auth['oauth_url'] + '?' + urlencode({'response_type': 'code', 'appid': auth['app_id'], 'scope': 'snsapi_login', 'redirect_uri': BASE + '/jihua/auth/callback/dingtalk', 'state': state})
        referer = ding + '/login/index.htm?' + urlencode({'goto': oauth})
        response = session.post(ding + '/login/login_with_pwd', headers={'Origin': ding, 'Referer': referer, 'User-Agent': auth['user_agent']}, data={
            'mobile': f"{auth['country_code']}-{self.username}", 'pwd': self.password, 'goto': oauth,
            'pdmToken': '', 'araAppkey': auth['ara_appkey'], 'araToken': auth['ara_token'],
            'araScene': 'login', 'captchaImgCode': '', 'captchaSessionId': '', 'type': 'h5',
        }, timeout=COMPLETION['timeout'])
        response.raise_for_status()
        link = response.json().get('data')
        if not isinstance(link, str) or not link.startswith('https://'):
            raise ValueError('追光鲸鱼登录未返回跳转链接，可能需要验证码。')
        response = session.get(link, timeout=COMPLETION['timeout'])
        response.raise_for_status()
        domain = urlsplit(BASE).hostname
        cookies = [c for c in session.cookies if c.domain.lstrip('.') == domain]
        if not cookies:
            raise ValueError('追光鲸鱼登录未收到 Cookie。')
        check = session.post(BASE + '/jihua/term/term/list', data={'pageSize': 1, 'pageNum': 1, 'xeResourceType': 50}, timeout=COMPLETION['timeout'])
        check.raise_for_status()
        try:
            verified = str(check.json().get('code', 0)) in ('0', '200')
        except (ValueError, AttributeError):
            verified = False
        if not verified:
            raise ValueError('追光鲸鱼登录验证失败。')
        jar = MozillaCookieJar(str(self.cookie_path))
        for cookie in cookies:
            jar.set_cookie(cookie)
        jar.save(ignore_discard=True, ignore_expires=True)
        self.session.cookies.clear()
        self.session.cookies.update(jar)
        session.close()
        self.refreshed = True

    def request(self, method, path, *, form=None, params=None, html=False, referer=None):
        retries = 0
        while True:
            response = self.session.request(method, BASE + path, data=form, params=params,
                headers={**COMPLETION['headers'], 'origin': BASE, 'referer': referer or BASE + LESSON_PATH}, timeout=COMPLETION['timeout'])
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if _auth_failed(response, payload):
                if self.refreshed:
                    raise ValueError('追光鲸鱼登录后仍无权限，请检查账号。')
                self.login()
                continue
            server_failed = response.status_code in (500, 502, 503, 504) or isinstance(payload, dict) and str(payload.get('code')) == '500'
            if server_failed and retries < COMPLETION['server_retries']:
                retries += 1
                time.sleep(retries * COMPLETION['retry_delay'])
                continue
            response.raise_for_status()
            if html:
                return response.text
            if not isinstance(payload, dict) or str(payload.get('code', 0)) not in ('0', '200'):
                raise ValueError('追光鲸鱼接口返回业务错误；旧数据未覆盖。')
            rows = payload.get('rows')
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                raise ValueError('追光鲸鱼接口未返回有效 rows。')
            return payload

    def _single_page(self, method, path, **kwargs):
        payload = self.request(method, path, **kwargs)
        rows = payload['rows']
        if int(payload.get('total', len(rows))) != len(rows):
            raise ValueError('接口记录数超过单页，未保存不完整名单。')
        return rows

    def terms(self):
        form = dict(pageSize=10, pageNum=1, isAsc='asc', xeResourceType=50, termNo='', termName='', classTypeKey='', classKey='', openEndStatus='')
        form.update({'params[termPage]': '0', 'params[sysUserRoleKey]': 'after_quality'})
        form.update({f'params[{k}]': '' for k in ('beginDate','endDate','termEndTimeS','termEndTimeE','area','group','teacherUserId')})
        result = []
        for row in self._single_page('POST', '/jihua/term/term/list', form=form):
            if not row.get('termId') or not row.get('termNo'):
                raise ValueError('班期接口缺少 termId 或 termNo。')
            result.append({k: row.get(k) or '' for k in ('termId','termNo','termName','termAlias','termTime','termEndTime')})
        return result

    def lessons(self, term_id):
        html = self.request('GET', LESSON_PATH, params={'termId': term_id}, html=True)
        select = BeautifulSoup(html, 'html.parser').select_one('select#resourceId')
        if select is None:
            raise ValueError('课程页面未找到课程选择框。')
        seen, result = set(), []
        for option in select.select('option'):
            value = (option.get('value') or '').strip()
            if value and value not in seen:
                seen.add(value)
                result.append({'resource_id': value, 'label': option.get_text(' ', strip=True)})
        if not result:
            raise ValueError('本班期暂无可选课程。')
        return result

    def students(self, term_id, resource_id):
        if not resource_id:
            raise ValueError('未找到第 1 节课，无法获取学员。')
        form = dict(pageSize=500, pageNum=1, isAsc='asc', termId=term_id, resourceId=resource_id,
                    status='', studentType='', checkingInStatus='', studentNo='', nickname='', xeuid='', isStudyLeave='')
        form.update({'params[classNumGt0]': '', 'params[liveorrelive30min]': ''})
        for prefix in ('hisLearnTime', 'hisLearningTime', 'hisLearnedTime'):
            for suffix in ('GeOrLe', 'Minute', 'Second'):
                form[f'params[{prefix}{suffix}]'] = '0' if suffix == 'GeOrLe' else ''
        result = []
        for row in self._single_page('POST', LESSON_PATH + '/list', form=form):
            number = str(row.get('studentNo') or '').strip()
            if not number:
                raise ValueError('学员缺少学号，原名单未覆盖。')
            if not any(k in row for k in ('realname', 'studentName', 'name')):
                raise ValueError('学员接口姓名字段尚未适配。')
            name = next((str(row[k]).strip() for k in ('realname','studentName','name') if row.get(k) and str(row[k]).strip()), '')
            value = lambda key, labels={}: labels.get(str(row.get(key) if row.get(key) is not None else '').strip(), str(row.get(key) if row.get(key) is not None else '').strip())
            result.append({'student_id': number, 'name': name, 'status': value('status', STATUS_LABELS), 'student_type': value('studentType', TYPE_LABELS), 'nickname': value('nickname')})
        return result

    def learning(self, term_id):
        path = '/jihua/report/term/ReportTermStudentStudyData/list'
        form = {**COMPLETION['filters'], 'pageNum': 1, 'pageSize': COMPLETION['page_size'], 'params[selectType]': COMPLETION['select_type']}
        rows, previous = [], None
        while True:
            page_url = BASE + '/jihua/report/term/ReportTermStudentStudyData?' + urlencode({'termId': term_id, 'selectType': COMPLETION['select_type']})
            payload = self.request('POST', path, form=form, params={'termId': str(term_id)}, referer=page_url)
            page = payload['rows']
            total = int(payload.get('total', len(page)))
            if rows and (not page or page == previous):
                raise ValueError('完课分页提前结束或重复，旧数据未覆盖。')
            rows.extend(page)
            if len(rows) >= total:
                if len(rows) != total:
                    raise ValueError('完课接口记录数不一致。')
                return {'rows': rows, 'total': total}
            previous = page
            form['pageNum'] += 1
