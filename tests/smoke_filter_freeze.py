"""Disposable GUI integration for ADR-007: no network access or real message sending."""
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from app.backend import Backend
from app.fonts import configure_font
from tests.profile_fixtures import insert_profile


def find(window, name):
    item = window.findChild(QObject, name)
    assert item is not None, f'未找到 {name}'
    return item


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    # The offscreen platform may not enumerate Windows' installed CJK fonts.
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'test.db')
        with b.db.connect() as conn:
            for i, name in enumerate(('张三', '李四', '王五'), 1):
                sid = str(i)
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-09-28'))
                insert_profile(conn, sid, name, i, {'微信': '是' if i < 3 else '否'})
        b.refresh()
        b.workflow.createBatch()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 820); window.show()

        # ---- 画像：修改字段后行保留为过期 ----
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 1))
        QTest.qWait(120)
        profiles = b.profilesModule
        profiles.setColumnFilter('profile:微信', 'values', ['是'], '')
        QTest.qWait(60)
        assert profiles.visibleCount == 2, profiles.visibleCount
        key = profiles.selected['_record_key']
        assert profiles.saveEditorField(key, '微信', '否')
        QTest.qWait(120)
        assert (profiles.visibleCount, profiles.staleCount) == (2, 1), (profiles.visibleCount, profiles.staleCount)
        stale = next(r for r in profiles.tableModel.rows if r['_record_key'] == key)
        assert stale['_filter_stale'] and stale['profile:微信'] == '否'
        # 切到工作台再切回画像：行、高光与“正在处理”位置都不能变。
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 0))
        QTest.qWait(120)
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 1))
        QTest.qWait(120)
        assert (profiles.visibleCount, profiles.staleCount) == (2, 1), (profiles.visibleCount, profiles.staleCount)
        assert profiles.selected['_record_key'] == key, profiles.selected.get('name')
        assert profiles.cursorText == '正在处理 第 1 / 2 条 · 张三', profiles.cursorText
        reapply = find(window, 'profileReapplyFilter')
        assert reapply.property('visible'), '重新应用筛选按钮未显示'
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-filter-freeze-profile.png'))
        QMetaObject.invokeMethod(reapply, 'clicked')
        QTest.qWait(120)
        assert (profiles.visibleCount, profiles.staleCount) == (1, 0), (profiles.visibleCount, profiles.staleCount)
        assert not reapply.property('visible')
        # 被筛掉的张三不在列表里，高光落到“下一条”李四，而不是回到第一行。
        assert profiles.selected['name'] == '李四', profiles.selected.get('name')

        # ---- 工作台：记录反馈后行保留为过期 ----
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 0))
        QTest.qWait(120)
        w = b.workflow
        w.filterRows('pending', '')
        QTest.qWait(60)
        assert w.visibleCount == 3, w.visibleCount
        assert w.submit('已回复')
        QTest.qWait(120)
        assert (w.visibleCount, w.matchedCount, w.staleCount) == (3, 2, 1), (w.visibleCount, w.matchedCount, w.staleCount)
        campaign_reapply = find(window, 'campaignReapplyFilter')
        assert campaign_reapply.property('visible'), '工作台重新应用筛选按钮未显示'
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-filter-freeze-workbench.png'))
        bad = [x for x in warnings if 'staleRow' in x or 'Unable to assign' in x]
        assert not bad, bad
        print('filter freeze smoke ok; QML warnings:', len(warnings))


if __name__ == '__main__':
    run()
