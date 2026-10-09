"""Passwords are stored in the current Windows user's Credential Manager."""
import keyring

SERVICES = {
    'ai_campaign': 'LocalTools/学员催办维护名单/AI催交话术',
    'completion': 'LocalTools/学员催办维护名单/追光鲸鱼',
    'homework': 'LocalTools/学员催办维护名单/作业平台',
}


def _service(platform):
    if platform not in SERVICES:
        raise ValueError('未知平台')
    return SERVICES[platform]


def get_password(platform, username):
    return keyring.get_password(_service(platform), username) if username else None


def set_password(platform, username, password):
    if not username.strip() or not password:
        raise ValueError('账号和密码不能为空')
    keyring.set_password(_service(platform), username.strip(), password)
