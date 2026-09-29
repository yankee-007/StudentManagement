REMOVED_FIELDS = {'学历', '专业', '是否有基础'}
CHOICES = {
    '学员状态': ['', '退课', '异动', '未加'],
    '助教微信\n是否添加学员': ['', '是', '否'],
    '助教QQ\n是否添加学员': ['', '是', '否'],
    '是否\n有电脑': ['', '是', '否'],
    '工具\n是否已经安装': ['', '是', '手机安装', '待检查'],
    '微信': ['', '是', '否'], 'QQ': ['', '是', '否'],
    '电脑': ['', '是', '否'], '工具安装': ['', '是', '手机安装', '待检查'],
}
DISPLAY_LABELS = {
    '助教微信\n是否添加学员': '微信', '助教QQ\n是否添加学员': 'QQ',
    '是否\n有电脑': '电脑', '工具\n是否已经安装': '工具安装',
}

BASE_PROFILE_LABELS = ('微信','QQ','电脑','工具安装','所在地区','学习目的')
PROFILE_INPUT_LABELS = BASE_PROFILE_LABELS + ('开学时间','军训时间','画像情况')


def canonical_fields(fields):
    result = {key: '' for key in PROFILE_INPUT_LABELS}
    for key, value in fields.items():
        label = '画像情况' if key.startswith('画像情况') else DISPLAY_LABELS.get(key,key)
        if label in result and (key == label or not result[label]):
            result[label] = '' if value is None else value
    return result


def clean_profiles(db):
    """Migrate basic fields, extensions and exemptions without a backup."""
    from .profile_storage import migrate
    migrate(db)
