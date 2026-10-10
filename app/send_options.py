"""Validated options used by the group center and desktop adapter."""
import math

DEFAULTS = dict(wait=0.5,timeout=3.0,focus_delay=0.5,paste_delay=0.5,
                interval=0.0,substring_mode=False,verify_contact=True,confirm_send=True,single_send=True,clipboard_mode=False)


def normalize(values=None):
    values=dict(values or {})
    if 'close_on_success' in values:
        values.pop('close_on_success')
        values.setdefault('verify_contact',True)
        if values.get('paste_delay')==.3:values['paste_delay']=DEFAULTS['paste_delay']
        if values.get('interval')==1:values['interval']=0
    if set(values)-set(DEFAULTS):raise ValueError('存在不支持的发送参数')
    result={**DEFAULTS,**values}
    for key,low,high in [('wait',.1,10),('timeout',.5,30),('focus_delay',.1,10),('paste_delay',.1,10),('interval',0,60)]:
        try:value=float(result[key])
        except (TypeError,ValueError):raise ValueError(f'{key} 必须为数字')
        if not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{key} 范围为 {low}–{high} 秒')
        result[key]=value
    for key in ('substring_mode','verify_contact','confirm_send','single_send','clipboard_mode'):
        if not isinstance(result[key],bool):raise ValueError(f'{key} 必须为布尔值')
    return result
