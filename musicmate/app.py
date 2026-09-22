from __future__ import annotations

import sys
import json
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from filelock import Timeout

from musicmate import __version__
from musicmate import updater
from musicmate.core import Cancelled, inspect_track, save_track, validate_url


class Worker(QThread):
    result = Signal(object)
    failure = Signal(str)
    progress = Signal(int, str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.action(self.cancel, self.progress.emit))
        except Exception as error:
            self.failure.emit("작업을 취소했습니다." if self.cancel.is_set() or isinstance(error, Cancelled)
                              else str(error))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"YoutubeMusicMate {__version__}")
        self.resize(620, 370)
        self.setMinimumSize(540, 350)
        self.settings = QSettings("DalBear", "YoutubeMusicMate")
        self.track = None
        self.worker = None
        self.saved_path = None
        self.update_worker = None
        self.available_update = None
        self.install_pending = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        url_row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("YouTube 또는 YouTube Music 영상 주소 붙여넣기")
        self.url.setAccessibleName("YouTube 영상 주소")
        self.inspect_button = QPushButton("정보 조회")
        self.inspect_button.setObjectName("primary")
        self.inspect_button.clicked.connect(self.inspect)
        self.url.returnPressed.connect(self.inspect)
        self.url.textChanged.connect(self.invalidate)
        url_row.addWidget(self.url, 1)
        url_row.addWidget(self.inspect_button)
        layout.addLayout(url_row)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(12)
        self.cover = QLabel("♫\n표지 미리보기")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFixedSize(104, 104)
        self.cover.setObjectName("cover")
        card_layout.addWidget(self.cover)
        form = QFormLayout()
        form.setSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title = QLineEdit()
        self.artist = QLineEdit()
        self.album = QLineEdit()
        for label, field in (("곡명", self.title), ("가수", self.artist), ("앨범", self.album)):
            field.setAccessibleName(label)
            form.addRow(label, field)
        self.duration = QLabel("주소를 입력하면 곡 정보를 불러옵니다.")
        self.duration.setObjectName("muted")
        form.addRow(self.duration)
        card_layout.addLayout(form, 1)
        layout.addWidget(card)
        hint = QLabel("표지·일반 가사 자동 저장 · 곡명과 가수를 확인하세요.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        destination = QHBoxLayout()
        destination.addWidget(QLabel("저장 폴더"))
        self.folder = QLineEdit(str(self.settings.value("folder", str(Path.home() / "Music" / "YoutubeMusicMate"))))
        self.folder.setReadOnly(True)
        self.folder_button = QPushButton("변경")
        self.folder_button.clicked.connect(self.choose_folder)
        destination.addWidget(self.folder, 1)
        destination.addWidget(self.folder_button)
        layout.addLayout(destination)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        layout.addWidget(self.progress)
        self.status = QLabel("주소를 입력해 시작하세요.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.open_button = QPushButton("폴더 열기")
        self.open_button.clicked.connect(self.open_folder)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.save_button = QPushButton("MP3로 저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        self.save_button.setEnabled(False)
        actions.addWidget(self.open_button)
        self.update_button = QPushButton("업데이트 확인")
        self.update_button.clicked.connect(lambda: self.check_updates(True))
        actions.addWidget(self.update_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.setStyleSheet('''
            QMainWindow { background: #f4f6fa; }
            QWidget { color: #202b40; font-size: 12px; }
            QLabel#muted { color: #69758a; }
            QFrame#card { background: white; border: 1px solid #e1e6ef; border-radius: 9px; }
            QLabel#cover { background: #eeebfb; color: #8074bb; border-radius: 6px; font-size: 14px; }
            QLineEdit { background: white; border: 1px solid #d8deea; border-radius: 5px; padding: 5px 7px; }
            QLineEdit:focus { border-color: #7b6ce1; }
            QPushButton { background: #e7ebf3; border: none; border-radius: 5px; padding: 6px 10px; font-weight: 600; }
            QPushButton:hover { background: #dce1ee; }
            QPushButton#primary { background: #6958d5; color: white; }
            QPushButton#primary:hover { background: #5846c1; }
            QPushButton:disabled, QPushButton#primary:disabled { background: #e3e6ed; color: #97a0b1; }
            QProgressBar { background: #e4e7ef; border: none; border-radius: 3px; }
            QProgressBar::chunk { background: #8070e2; border-radius: 3px; }
        ''')

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(lambda: self.check_updates(False))
        self.update_timer.start(6 * 60 * 60 * 1000)
        QTimer.singleShot(1500, self.startup_update)

    def startup_update(self):
        result_path = updater.state_dir() / 'update-result.json'
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding='utf-8'))
                self.status.setText(result['message'])
                if not result['ok']:
                    QMessageBox.warning(self, '업데이트 결과', result['message'])
            finally:
                result_path.unlink(missing_ok=True)
        self.check_updates(False)

    def check_updates(self, manual=False):
        if self.worker is not None or self.update_worker is not None:
            if manual:
                self.status.setText('현재 작업을 마친 후 업데이트를 확인하세요.')
            return
        if self.available_update:
            self.offer_update(self.available_update)
            return
        self.update_button.setEnabled(False)
        self.update_worker = Worker(lambda cancel, progress: updater.check_update(), self)
        self.update_worker.result.connect(lambda result: self.update_checked(result, manual))
        self.update_worker.failure.connect(lambda message: self.status.setText('업데이트 확인 실패: ' + message) if manual else None)
        self.update_worker.finished.connect(self.update_check_finished)
        self.update_worker.start()

    def update_check_finished(self):
        worker = self.update_worker
        self.update_worker = None
        worker.deleteLater()
        self.update_button.setEnabled(self.worker is None)

    def update_checked(self, update, manual):
        if update is None:
            if manual:
                self.status.setText(f'최신 버전입니다. ({__version__})')
            return
        self.available_update = update
        self.update_button.setText('새 버전 설치')
        if self.worker is None:
            self.offer_update(update)

    def offer_update(self, update):
        if self.worker is not None:
            return
        version = update['manifest']['version']
        dialog = QMessageBox(self)
        dialog.setWindowTitle('새 버전 안내')
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f'새 버전 {version}이 있습니다. 현재 버전: {__version__}')
        dialog.setInformativeText('동의하면 업데이트를 다운로드합니다. 검증 후 앱을 완전히 종료하고 설치·재시작합니다. 입력 중인 곡 정보는 유지되지 않습니다.')
        install = dialog.addButton('업데이트 설치', QMessageBox.ButtonRole.AcceptRole)
        later = dialog.addButton('나중에', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(later)
        dialog.exec()
        if dialog.clickedButton() != install or self.worker is not None:
            return
        def download(cancel, progress):
            stage = updater.prepare_update(update, cancel, progress)
            updater.launch_helper(stage)
            return stage
        self.start(download, self.update_prepared)

    def update_prepared(self, stage):
        self.install_pending = True
        self.status.setText('앱을 종료합니다. 종료 확인 후 업데이트가 설치됩니다.')

    def invalidate(self):
        self.track = None
        self.save_button.setEnabled(False)
        self.title.clear()
        self.artist.clear()
        self.album.clear()
        self.cover.clear()
        self.cover.setText("♫\n표지 미리보기")
        self.duration.setText("주소를 입력하면 곡 정보를 불러옵니다.")

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "MP3 저장 폴더", self.folder.text())
        if folder:
            self.folder.setText(folder)
            self.settings.setValue("folder", folder)

    def open_folder(self):
        folder = Path(self.folder.text())
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self.status.setText("음악을 저장하면 폴더가 생성됩니다.")

    def busy(self, value):
        for widget in (self.url, self.inspect_button, self.title, self.artist, self.album, self.folder_button):
            widget.setEnabled(not value)
        self.update_button.setEnabled(not value and self.update_worker is None)
        self.save_button.setEnabled(not value and self.track is not None)
        self.cancel_button.setEnabled(value)

    def start(self, action, callback):
        if self.worker is not None:
            return
        self.busy(True)
        self.worker = Worker(action, self)
        self.worker.result.connect(callback)
        self.worker.failure.connect(self.failed)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.busy(False)
        self.progress.setRange(0, 100)
        if self.install_pending:
            QApplication.instance().quit()

    def failed(self, message):
        self.status.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

    def update_progress(self, value, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(value)
        self.status.setText(message)

    def inspect(self):
        if self.worker is not None:
            return
        try:
            url = validate_url(self.url.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.invalidate()
        self.progress.setRange(0, 0)
        self.status.setText("곡 정보와 표지를 가져오고 있습니다…")
        self.start(lambda cancel, progress: inspect_track(url, cancel), self.inspected)

    def inspected(self, track):
        self.track = track
        self.title.setText(track.title)
        self.artist.setText(track.artist)
        self.album.setText(track.album)
        seconds = int(track.duration)
        self.duration.setText(f"{seconds // 60}:{seconds % 60:02d}  ·  MP3 고음질 VBR")
        if track.cover:
            pixmap = QPixmap()
            pixmap.loadFromData(track.cover)
            self.cover.setPixmap(pixmap.scaled(104, 104, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(track.notice.strip() or "곡 정보를 확인한 후 MP3로 저장하세요.")

    def save(self):
        if self.track is None or self.worker is not None:
            return
        if not self.title.text().strip():
            self.status.setText("곡명을 입력하세요.")
            return
        track = replace(self.track, title=self.title.text().strip(), artist=self.artist.text().strip(),
                        album=self.album.text().strip())
        folder = Path(self.folder.text())
        self.start(lambda cancel, progress: save_track(track, folder, cancel, progress), self.saved)

    def saved(self, result):
        path, notice = result
        self.saved_path = path
        self.status.setText(f"저장 완료: {path.name}\n{notice}")

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("취소 중… 현재 네트워크 요청이 끝나면 중단합니다.")

    def closeEvent(self, event):
        if self.worker is not None or self.update_worker is not None:
            self.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YoutubeMusicMate")
    app.setOrganizationName("DalBear")
    lock = updater.instance_lock()
    try:
        lock.acquire(timeout=0)
    except Timeout:
        QMessageBox.information(None, 'YoutubeMusicMate', '앱이 이미 실행 중이거나 업데이트 설치 중입니다.')
        return
    try:
        window = Window()
        window.show()
        result = app.exec()
    finally:
        lock.release()
    sys.exit(result)
