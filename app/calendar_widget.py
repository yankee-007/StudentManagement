from PySide6.QtCore import Qt, QRectF, QDate, QLocale
from PySide6.QtGui import QColor, QPen, QTextCharFormat, QPainter
from PySide6.QtWidgets import QCalendarWidget


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
        for day in (Qt.Saturday, Qt.Sunday):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor('#667085'))
            self.setWeekdayTextFormat(day, fmt)
        self.selectionChanged.connect(self.updateCells)

    def paintCell(self, painter, rect, value):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(rect, QColor('white'))
        box = QRectF(rect).adjusted(3, 2, -3, -2)
        today = value == QDate.currentDate()
        selected = value == self.selectedDate()
        faded = value.month() != self.monthShown() or value.year() != self.yearShown() or value < self.minimumDate()
        if today:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#335cff'))
            painter.drawRoundedRect(box, 5, 5)
        if selected:
            painter.setPen(QPen(QColor('#173bbd'), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor('white' if today else '#c3c8d2' if faded else '#344054'))
        painter.drawText(rect, Qt.AlignCenter, str(value.day()))
        painter.restore()
