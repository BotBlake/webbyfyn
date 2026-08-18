from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from .constants import (
    CLIENT_NAME,
    CLIENT_VERSION,
    DEVICE_NAME,
    DEVICE_PROFILE,
    MPV_LOG_PREFIX,
)


class JellyfinPage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        if message.startswith(MPV_LOG_PREFIX):
            print(message, flush=True)
            return

        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class JellyfinWindow(QMainWindow):
    def __init__(self, server: str) -> None:
        super().__init__()

        self.setWindowTitle(CLIENT_NAME)
        self.resize(1280, 800)

        self.web = QWebEngineView(self)
        self.web.setPage(JellyfinPage(self.web))
        self.setCentralWidget(self.web)

        self._install_native_shell()

        self.web.load(QUrl(self._server_url(server)))

    def _install_native_shell(self) -> None:
        factory = Path(__file__).with_name("native.js").read_text(encoding="utf-8")
        config = json.dumps(
            {
                "appName": CLIENT_NAME,
                "appVersion": CLIENT_VERSION,
                "deviceName": DEVICE_NAME,
                "deviceProfile": DEVICE_PROFILE,
                "logPrefix": MPV_LOG_PREFIX,
            },
            separators=(",", ":"),
        )

        script = QWebEngineScript()
        script.setName("webbyfin-native-shell")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(f"({factory})({config});")
        self.web.page().scripts().insert(script)

    @staticmethod
    def _server_url(server: str) -> str:
        server = server.strip().rstrip("/")

        parsed = urlparse(server)

        if parsed.scheme not in {"http", "https"}:
            server = f"http://{server}"

        if not server.endswith("/web"):
            server += "/web"

        return server + "/"
