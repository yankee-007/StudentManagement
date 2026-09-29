from PySide6.QtGui import QFont, QFontDatabase


def configure_font(app):
    """Use an installed scalable UI font instead of Windows bitmap defaults."""
    available = set(QFontDatabase.families())
    family = next((name for name in ('Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI')
                   if name in available), 'Sans Serif')
    font = app.font()
    font.setFamily(family)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
    return family
