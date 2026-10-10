"""In-memory clipboard snapshot; never retain handles owned by the copy source."""
import struct

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from .clipboard import _native_clipboard, _opened
from .message_content import prepare_content, file_versions


class ClipboardPayload:
    def __init__(self,formats,*,text='',files=(),image=False,rich=False):
        self.formats=tuple(formats)
        self.files=prepare_content([dict(type='file',path=path) for path in files]) if files else []
        self.versions=file_versions(self.files)
        labels=[]
        if self.files:labels.append(f'文件（{len(self.files)} 个）')
        if image:labels.append('图片')
        if rich:labels.append('富文本 / 应用内容')
        if text.strip():labels.append('文字')
        if not self.formats or not labels:raise ValueError('剪贴板没有可发送的内容，请先复制文字、图片或文件，再重新预览')
        self.preview=dict(kindLabel='、'.join(labels),text=text,files=[item['path'] for item in self.files])

    def validate(self):
        try:
            if file_versions(self.files)!=self.versions:raise ValueError('剪贴板中的文件已变化，请重新复制并预览')
        except OSError as exc:raise ValueError('剪贴板中的文件已失效，请重新复制并预览') from exc

    def restore(self,native):
        self.validate()
        with _opened(native):
            native.EmptyClipboard()
            for fmt,data in self.formats:native.SetClipboardData(fmt,data)


def _file_drop(paths):
    return struct.pack('<IiiII',20,0,0,0,1)+('\0'.join(paths)+'\0\0').encode('utf-16le')


def capture():
    native=_native_clipboard()
    if native is None:return _capture_qt()
    formats=[];text='';files=();image=False;rich=False
    with _opened(native):
        ids=[];fmt=0
        while True:
            fmt=native.EnumClipboardFormats(fmt)
            if not fmt:break
            ids.append(fmt)
        for fmt in ids:
            # Bitmap/metafile/palette and private formats contain borrowed handles.
            # Windows enumerates synthesized DIB formats for bitmap-only copies.
            if fmt in (2,3,9,14,0x80,0x81,0x82,0x83) or 0x200<=fmt<0x400:continue
            name=native.GetClipboardFormatName(fmt) if fmt>=0xC000 else ''
            if name in ('Ole Private Data','DataObject'):continue
            try:data=native.GetClipboardData(fmt)
            except Exception as exc:
                raise ValueError('无法保存完整剪贴板内容，请重新复制后预览') from exc
            if fmt==15:
                files=tuple(data);data=_file_drop(files)
            elif not isinstance(data,(str,bytes)):
                continue
            if fmt==13:text=data
            if fmt in (8,17):image=True
            if fmt>=0xC000:
                if name.lower() in ('png','image/png','jfif'):image=True
                elif name in ('HTML Format','Rich Text Format'):rich=True
            formats.append((fmt,data))
    return ClipboardPayload(formats,text=text,files=files,image=image,rich=rich)


def _capture_qt():
    # Offscreen verification uses Qt's clipboard. Production Windows uses the
    # native path above, including registered rich formats in their original order.
    app=QGuiApplication.instance()
    if not isinstance(app,QGuiApplication):raise ValueError('剪贴板不可用，请在界面中重新预览')
    mime=app.clipboard().mimeData()
    formats=[];text=mime.text() if mime else '';files=[];image=False
    if text:formats.append((13,text))
    if mime and mime.hasUrls():
        files=[url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
        if files:formats.append((15,_file_drop(files)))
    if mime and mime.hasImage():
        value=app.clipboard().image();buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
        if not value.isNull() and value.save(buffer,'BMP'):
            formats.append((8,bytes(buffer.data())[14:]));image=True
    return ClipboardPayload(formats,text=text,files=files,image=image)
