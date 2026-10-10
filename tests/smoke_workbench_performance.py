"""Measure workbench entry with 1000 synthetic students and 24 history batches.

Set WORKBENCH_PERF_LABEL=before to run this unchanged script in an isolated
baseline checkout; assertions target behavior, not machine-dependent latency.
"""
import json
import os
import statistics
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.backend import Backend
from app.fonts import configure_font
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output = Path(os.environ.get('WORKBENCH_PERF_OUTPUT', 'output/workbench-optimization'))
    output.mkdir(parents=True, exist_ok=True)
    label = os.environ.get('WORKBENCH_PERF_LABEL', 'after')
    with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
        b = Backend(Path(folder) / 'bench.db')
        with b.db.connect() as conn:
            for i in range(1000):
                sid, name = f'{i+1:04d}', f'虚构学员{i+1:04d}'
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid,name,'2026-10-10'))
                insert_profile(conn,sid,name,i,{'微信':'是'})
            conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('snapshot',json.dumps([
                dict(student_id=f'{i+1:04d}',flags={'c1':'T','z1':'F'}) for i in range(1000)])))
        w = b.workflow; w.createBatch(); first=w._batch
        template=w.template
        with b.db.connect() as conn:
            for batch in range(1,26):
                if batch != first:
                    conn.execute('INSERT INTO campaigns(id,class_name,created_at,template) VALUES(?,?,?,?)',
                                 (batch,'性能测试班',f'2026-09-{batch:02d}T10:00:00',template))
                    conn.execute('INSERT INTO campaign_students SELECT ?,student_id,name,remark,snapshot,eligible,reason,message,send_state,sent_at FROM campaign_students WHERE batch_id=?', (batch,first))
                if batch < 25:
                    conn.executemany('INSERT INTO campaign_feedback(batch_id,student_id,content,kind) VALUES(?,?,?,?)',
                                     [(batch,f'{i+1:04d}',f'第{batch}次虚构反馈：已沟通学习安排；下周复查。','reply') for i in range(1000)])
        w.reload_batches(); w.setShowPreviousFeedback(True)
        engine=QQmlApplicationEngine(); warnings=[]
        engine.warnings.connect(lambda entries: warnings.extend(i.toString() for i in entries))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]; window.resize(1280,800); window.show(); QTest.qWait(100)
        durations=[]
        with patch.object(w.store,'rows',wraps=w.store.rows) as reads, \
             patch.object(w.store,'refresh_latest_learning',wraps=w.store.refresh_latest_learning) as refresh:
            for _ in range(6):
                window.switchModule(1); QTest.qWait(20)
                start=perf_counter(); window.switchModule(0); app.processEvents(); window.grabWindow()
                durations.append((perf_counter()-start)*1000)
            result=dict(students=1000,history_batches=24,entry_median_ms=round(statistics.median(durations),2),
                        first_entry_ms=round(durations[0],2),entry_max_ms=round(max(durations),2),
                        batch_reads=reads.call_count,learning_refreshes=refresh.call_count)
            if label != 'before':
                assert refresh.call_count==1,result
                assert reads.call_count==1,result
        table=window.findChild(QObject,'studentTable')
        w.setColumnFilter('feedback','empty',[], '')
        sid=w.selected['student_id']; editor=w.editorKey
        resets=[]; w.tableModel.modelReset.connect(lambda:resets.append(True))
        start=perf_counter(); w.queueFeedback(editor,'虚构反馈修改'); assert w.flushFeedback()
        app.processEvents(); window.grabWindow()
        result['feedback_ms']=round((perf_counter()-start)*1000,2)
        assert w.selected['student_id']==sid and not resets
        assert w.selected['_filter_stale'] and len(w.recipientKeys)==999
        assert table.property('contentY')>=0
        if label!='before':
            assert b.dailyWorkspace._dirty, 'Collapsed commitment editors must not load the hidden workspace'
            visible=[f for f in w.managedFields if f['field_id'].startswith('previous_feedback_') and f['show_column']]
            assert len(visible)==24
            for field in visible[:-1]: assert w.setFieldVisible(field['field_id'],False)
            assert len([key for key in w._rows[0] if key.startswith('previous_feedback_')])==1
            assert window.grabWindow().save(str(output/'one-history-field.png'))
        assert not warnings,warnings
        (output/f'entry-{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
        window.hide(); engine.deleteLater(); app.processEvents()


if __name__=='__main__': run()
