"""Render synthetic multilingual text with the native font backend; no window or data."""
from PySide6.QtCore import QLoggingCategory, qCWarning, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontDatabase, QTextLayout
from PySide6.QtWidgets import QApplication

from app.fonts import configure_font


def run():
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, text: messages.append((context.category, text)))
    try:
        app = QApplication([])
        inherited = QFont('Fixedsys', 10)
        inherited.setFixedPitch(True)
        app.setFont(inherited)
        family = configure_font(app)
        assert family != 'Fixedsys' and not app.font().fixedPitch()
        assert app.font().styleStrategy() & QFont.PreferOutline
        samples = ['中文 学员管理 ABC 123', '😀 附件']
        if 'Nirmala UI' in QFontDatabase.families():
            samples.append('中文 Malayalam മലയാളം')
        families = set()
        for text in samples:
            layout = QTextLayout(text, app.font())
            layout.beginLayout()
            line = layout.createLine(); line.setLineWidth(600)
            layout.endLayout()
            for run in layout.glyphRuns():
                assert run.rawFont().isValid()
                assert all(run.glyphIndexes()), (text, run.rawFont().familyName())
                families.add(run.rawFont().familyName())
        assert 'Fixedsys' not in families, families
        if len(samples) == 3:
            assert 'Nirmala UI' in families, families
        assert not [text for category, text in messages if category in ('qt.qpa.fonts', 'qt.text.font.db')], messages
        qCWarning(QLoggingCategory('qt.text.font.db'), 'font warning visibility probe')
        assert ('qt.text.font.db', 'font warning visibility probe') in messages
        print('Native font smoke OK: Chinese, Latin, emoji and installed Malayalam font; scalable fallback and font warnings retained')
    finally:
        qInstallMessageHandler(previous)


if __name__ == '__main__':
    run()
