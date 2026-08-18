from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow


class JellyfinWindow(QMainWindow):
    def __init__(self, server: str) -> None:
        super().__init__()

        self.server = server
        self.setWindowTitle("Webbyfin")
        self.resize(1280, 800)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)
        self.web.load(QUrl(self.server))
