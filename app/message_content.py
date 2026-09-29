"""Ordered text/file content shared by GUI, queue validation and desktop sender."""
from pathlib import Path
import re


def prepare_content(content):
    if isinstance(content,str):content=[{'type':'text','text':content}]
    if not isinstance(content,list) or not content:raise ValueError('请至少添加一个文字或文件字段')
    items=[]
    for item in content:
        if not isinstance(item,dict):raise ValueError('消息字段格式无效')
        if item.get('type')=='text':
            value=item.get('text')
            if not isinstance(value,str) or not value.strip() or '\0' in value:raise ValueError('文字字段不能为空或包含空字符')
            normalized=dict(type='text',text=value)
            for key in ('template','personal_override'):
                if key in item:normalized[key]=item[key]
            items.append(normalized)
        elif item.get('type')=='file':
            value=item.get('path')
            if not isinstance(value,(str,Path)) or not str(value):raise ValueError('请选择文件')
            path=Path(value)
            if not path.is_absolute():path=Path(__file__).resolve().parent.parent/path
            try:path=path.resolve(strict=True)
            except OSError:raise ValueError(f'文件不存在：{value}')
            if not path.is_file():raise ValueError(f'不是文件：{path}')
            normalized=dict(type='file',path=str(path))
            for key in ('template','personal_override'):
                if key in item:normalized[key]=item[key]
            items.append(normalized)
        else:raise ValueError('消息字段仅支持文字或文件')
    return items


def render_content(fields,name,message='',variables=None):
    values=dict(variables or {})
    values['姓名']=name
    values.setdefault('话术',message)
    pattern=re.compile(r'\{([^{}]+)\}')
    items=[]
    for f in fields:
        item=dict(f)
        if item.get('type')=='text':
            template=str(item.get('template',item.get('text','')))
            item['template']=template
            item['text']=pattern.sub(lambda match:str(values[match.group(1)]) if match.group(1) in values else match.group(0),template)
        items.append(item)
    return prepare_content(items)


def describe(content):
    return '\n'.join(f['text'] if f['type']=='text' else '[文件] '+f['path'] for f in content)


def file_versions(content):
    result=[]
    for f in content:
        if f['type']=='file':
            info=Path(f['path']).stat()
            result.append(dict(path=f['path'],size=info.st_size,mtime_ns=info.st_mtime_ns))
    return result
