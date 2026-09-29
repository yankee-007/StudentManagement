from datetime import date

STATUSES = ("正常", "请假")


def validate_status(data):
    if data.get('status', '正常') not in STATUSES:
        return ['状态只能为正常或请假']
    if data.get('status') == '请假':
        try:
            date.fromisoformat(data.get('exemption_end') or '')
        except ValueError:
            return ['请选择免催结束日期']
    return []
