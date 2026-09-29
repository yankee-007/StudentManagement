from __future__ import annotations

import re
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Slot


class DictTableModel(QAbstractTableModel):
    StudentIdRole = Qt.UserRole + 1
    RecordKeyRole = Qt.UserRole + 2
    ExpiredCellRole = Qt.UserRole + 3
    def __init__(self, columns: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        if role == self.StudentIdRole:
            return self.rows[index.row()].get('student_id', '')
        if role == self.RecordKeyRole:
            return self.rows[index.row()].get('_record_key',self.rows[index.row()].get('student_id',''))
        if role == self.ExpiredCellRole:
            return bool(self.columns[index.column()][0]=='exemption_text' and self.rows[index.row()].get('exemption_expired'))
        if not 0 <= index.column() < len(self.columns):
            return None
        key = self.columns[index.column()][0]
        value = self.rows[index.row()].get(key, "")
        if role in (Qt.DisplayRole, Qt.EditRole):
            if key in ("pending_courses_text", "pending_homework_text"):
                return ",".join(re.findall(r"第(\d+)节", str(value)))
            if key == "pending_count":
                student = self.rows[index.row()]
                return f"{len(student.get('pending_courses', []))}/{len(student.get('pending_homework', []))}"
            if isinstance(value, bool):
                return "是" if value else "否"
            return "" if value is None else str(value)
        if role == Qt.UserRole:
            return value
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.columns):
            return self.columns[section][1]
        return super().headerData(section, orientation, role)

    def roleNames(self):
        # Stable scalar roles: never marshal the complete profile for a cell.
        return {Qt.DisplayRole: b"display", self.StudentIdRole: b"studentId", self.RecordKeyRole:b"recordKey", self.ExpiredCellRole:b"expiredCell"}

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def reconcile_rows(self, rows):
        """Keep delegates alive when one feedback changes filtering or ordering."""
        wanted = {r['student_id'] for r in rows}
        for i in range(len(self.rows)-1, -1, -1):
            if self.rows[i]['student_id'] not in wanted:
                self.beginRemoveRows(QModelIndex(), i, i)
                self.rows.pop(i)
                self.endRemoveRows()
        for i, row in enumerate(rows):
            j = next((j for j in range(i, len(self.rows)) if self.rows[j]['student_id'] == row['student_id']), -1)
            if j < 0:
                self.beginInsertRows(QModelIndex(), i, i)
                self.rows.insert(i, row)
                self.endInsertRows()
            else:
                if j != i:
                    self.beginMoveRows(QModelIndex(), j, j, QModelIndex(), i)
                    self.rows.insert(i, self.rows.pop(j))
                    self.endMoveRows()
                if self.rows[i] != row:
                    self.rows[i] = row
                    self.dataChanged.emit(self.index(i,0), self.index(i,len(self.columns)-1))

    @Slot(int, result="QVariantMap")
    def get(self, row: int):
        return self.rows[row] if 0 <= row < len(self.rows) else {}
