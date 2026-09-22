import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox
from musicmate.app import Window


def test_later_does_not_download(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.update_timer.stop()
    started = []
    monkeypatch.setattr(window, 'start', lambda *args: started.append(args))
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda self: None)
    window.offer_update({'manifest': {'version': '9.0.0'}})
    assert started == []
    window.deleteLater()


def test_busy_music_job_prevents_update_prompt(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.update_timer.stop()
    window.worker = object()
    prompts = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: prompts.append(True))
    window.offer_update({'manifest': {'version': '9.0.0'}})
    assert not prompts
    window.worker = None
    window.deleteLater()
