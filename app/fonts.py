from PySide6.QtCore import QLoggingCategory
from PySide6.QtGui import QFont, QFontDatabase


def configure_font(app):
    """Use an installed scalable UI font instead of Windows bitmap defaults."""
    available = set(QFontDatabase.families())
    family = next((name for name in ('Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI')
                   if name in available), 'Sans Serif')
    font = app.font()
    fallbacks = [name for name in ('Nirmala UI', 'Segoe UI Emoji', 'Segoe UI')
                 if name in available and name != family and QFontDatabase.isSmoothlyScalable(name)]
    font.setFamilies([family, *fallbacks])
    font.setStyleName('')
    font.setFixedPitch(False)
    font.setStyleHint(QFont.SansSerif)
    font.setStyleStrategy(QFont.PreferOutline)
    app.setFont(font)
    # Qt logs each rejected shaping candidate at info level, even when the
    # next fallback renders correctly. Keep actual font warnings/errors enabled.
    QLoggingCategory.setFilterRules('qt.text.font.db.info=false')
    return family
