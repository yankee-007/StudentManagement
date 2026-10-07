from PySide6.QtCore import Qt, QRectF, QDate, QLocale
from PySide6.QtGui import QColor, QPen, QTextCharFormat, QPainter, QPalette
from PySide6.QtWidgets import QCalendarWidget


def date_dialog_theme(dark):
    """Palette and styled widget colors for the app-owned date dialog."""
    colors = ({'surface': '#1e2938', 'ink': '#e6edf7', 'nav': '#2a4163',
               'accent': '#3568b9', 'focus': '#91b9ff', 'hover': '#30435e',
               'line': '#3a4a60', 'input': '#192332', 'muted': '#93a4bb', 'faded': '#8c9bb0'}
              if dark else
              {'surface': '#ffffff', 'ink': '#344054', 'nav': '#eef2ff',
               'accent': '#335cff', 'focus': '#173bbd', 'hover': '#dce6ff',
               'line': '#d0d5dd', 'input': '#f9fafb', 'muted': '#667085', 'faded': '#c3c8d2'})
    palette = QPalette()
    for role, key in ((QPalette.Window, 'surface'), (QPalette.Base, 'surface'),
                      (QPalette.WindowText, 'ink'), (QPalette.Text, 'ink'),
                      (QPalette.Button, 'input'), (QPalette.ButtonText, 'ink'),
                      (QPalette.Highlight, 'accent'), (QPalette.Link, 'focus'),
                      (QPalette.PlaceholderText, 'muted')):
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(QPalette.HighlightedText, QColor('white'))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors['faded']))
    stylesheet = '''
        QDialog { background: %(surface)s; }
        QCalendarWidget { font-size: 14px; }
        QCalendarWidget QWidget#qt_calendar_navigationbar { background: %(nav)s; border-radius: 8px; }
        QCalendarWidget QToolButton { color: %(focus)s; padding: 10px; border: none; border-radius: 6px; }
        QCalendarWidget QToolButton:hover { background: %(hover)s; }
        QCalendarWidget QAbstractItemView { background: %(surface)s; color: %(ink)s; selection-background-color: %(accent)s; selection-color: white; border: none; outline: none; }
        QPushButton { padding: 9px 22px; border: 1px solid %(line)s; border-radius: 6px; background: %(input)s; color: %(ink)s; }
        QPushButton:default { background: %(accent)s; color: white; border: none; }
    ''' % colors
    return palette, stylesheet


class LeaveCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        self.setFirstDayOfWeek(Qt.Monday)
        self.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setGridVisible(False)
        self.setDateEditEnabled(False)
        self.setMinimumDate(QDate.currentDate())
        self.set_theme_palette(self.palette())
        self.selectionChanged.connect(self.updateCells)

    def set_theme_palette(self, palette):
        self.setPalette(palette)
        header = self.headerTextFormat()
        header.setBackground(palette.color(QPalette.Base))
        header.setForeground(palette.color(QPalette.Text))
        self.setHeaderTextFormat(header)
        for day in (Qt.Saturday, Qt.Sunday):
            fmt = QTextCharFormat()
            fmt.setForeground(palette.color(QPalette.PlaceholderText))
            self.setWeekdayTextFormat(day, fmt)

    def paintCell(self, painter, rect, value):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(rect, palette.color(QPalette.Base))
        box = QRectF(rect).adjusted(3, 2, -3, -2)
        today = value == QDate.currentDate()
        selected = value == self.selectedDate()
        faded = value.month() != self.monthShown() or value.year() != self.yearShown() or value < self.minimumDate()
        if today:
            painter.setPen(Qt.NoPen)
            painter.setBrush(palette.color(QPalette.Highlight))
            painter.drawRoundedRect(box, 5, 5)
        if selected:
            painter.setPen(QPen(palette.color(QPalette.Link), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(box, 5, 5)
        painter.setPen(palette.color(QPalette.HighlightedText) if today else
                       palette.color(QPalette.Disabled, QPalette.Text) if faded else palette.color(QPalette.Text))
        painter.drawText(rect, Qt.AlignCenter, str(value.day()))
        painter.restore()
