"""Disposable group-switch timing; no network or sender is invoked."""
import cProfile
import io
import pstats
import tempfile
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QMetaObject, QUrl, Q_ARG
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        backend = Backend(Path(directory) / 'test.db')
        center = backend.groupCenter
        for batch in range(2):
            people = [dict(name=f'学员{i}', content=[dict(type='text', text=f'学员{i}，请填写资料。' * 25),
                      dict(type='text', text='请回复学习情况。' * 30)],
                      learning_data={'profile_fields': {f'字段{j}': '学习情况' * 20 for j in range(15)}})
                      for i in range(200)]
            center.store.create(f'批次{batch}', people)
        center.refresh()
        engine = QQmlApplicationEngine()
        errors = []
        engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
        engine.rootContext().setContextProperty('backend', backend)
        engine.rootContext().setContextProperty('studentModel', backend.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        window = engine.rootObjects()[0]
        window.resize(1250, 800)
        window.show()
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 4))
        QTest.qWait(100)
        profile = cProfile.Profile()
        timings = []
        profile.enable()
        for index in [0, 1, 0, 1, 0, 1]:
            begin = perf_counter()
            center.selectList(index)
            app.processEvents()
            timings.append(round((perf_counter() - begin) * 1000, 1))
            assert center.pendingCount == 200
        profile.disable()
        print('Switch + UI events (ms):', timings)
        stats = pstats.Stats(profile)
        roster_exports = sum(value[1] for key, value in stats.stats.items()
                             if key[0].endswith('group_center.py') and key[2] == 'rows')
        assert roster_exports == 0, f'UI exported the complete roster {roster_exports} times'
        assert not errors, errors
        output = io.StringIO()
        pstats.Stats(profile, stream=output).sort_stats('cumulative').print_stats(15)
        print(output.getvalue())
        print('QML warnings:', errors)
        window.close()
        engine.deleteLater()
        app.processEvents()
        backend.groupCenter.shutdown()


if __name__ == '__main__':
    run()
