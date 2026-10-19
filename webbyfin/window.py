from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFile, QIODevice, QSettings, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEngineFullScreenRequest,
    QWebEnginePage,
    QWebEngineScript,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QStackedLayout, QWidget

from .constants import (
    CLIENT_NAME,
    CLIENT_VERSION,
    DEVICE_NAME,
    DEVICE_PROFILE,
    MPV_LOG_PREFIX,
)
from .credentials import SessionBridge, SessionStore
from .player import MpvBridge, MpvPlayer
from .urls import normalize_server_url, url_origin

_LOGGER = logging.getLogger(__name__)


class JellyfinPage(QWebEnginePage):
    def __init__(self, server_url: QUrl, parent: QWidget) -> None:
        super().__init__(parent)
        self._server_origin = url_origin(server_url.toString())

    def acceptNavigationRequest(
        self,
        url: QUrl,
        navigation_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if is_main_frame and url_origin(url.toString()) != self._server_origin:
            _LOGGER.warning("Blocked top-level navigation outside the configured Jellyfin origin")
            return False

        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

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

        server_url = self._server_url(server)

        content = QWidget(self)
        stack = QStackedLayout(content)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.web = QWebEngineView(content)
        self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        page = JellyfinPage(QUrl(server_url), self.web)
        page.setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,
            True,
        )
        page.fullScreenRequested.connect(self._handle_fullscreen_request)
        self.web.setPage(page)

        self.player = MpvPlayer(server_url, content)

        stack.addWidget(self.player)
        stack.addWidget(self.web)
        stack.setCurrentWidget(self.web)
        self.setCentralWidget(content)

        self._player_bridge = MpvBridge(self.player)
        self._channel = QWebChannel(self.web.page())
        scheme, host, port = url_origin(server_url)
        self._session_store = SessionStore(f"{scheme}://{host}:{port}")
        self._session_bridge = SessionBridge(self._session_store, self)
        self._channel.registerObject("player", self._player_bridge)
        self._channel.registerObject("session", self._session_bridge)
        self.web.page().setWebChannel(self._channel)

        self._install_native_shell(self._session_store.load())

        self.web.load(QUrl(server_url))

    def _handle_fullscreen_request(self, request: QWebEngineFullScreenRequest) -> None:
        toggle_on = request.toggleOn()
        request.accept()
        if toggle_on:
            self.showFullScreen()
        else:
            self.showNormal()

    @staticmethod
    def _device_id() -> str:
        # Jellyfin keeps one token per DeviceId, so it must survive restarts.
        settings = QSettings()
        device_id = settings.value("deviceId", type=str)
        if not device_id:
            device_id = str(uuid.uuid4())
            settings.setValue("deviceId", device_id)
        return device_id

    def _install_native_shell(self, saved_server: dict[str, Any] | None) -> None:
        factory = Path(__file__).with_name("native.js").read_text(encoding="utf-8")
        web_channel_file = QFile(":/qtwebchannel/qwebchannel.js")
        if not web_channel_file.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Could not load Qt's WebChannel JavaScript")
        web_channel_source = bytes(web_channel_file.readAll()).decode("utf-8")

        config = json.dumps(
            {
                "appName": CLIENT_NAME,
                "appVersion": CLIENT_VERSION,
                "deviceName": DEVICE_NAME,
                "deviceId": self._device_id(),
                "savedServer": saved_server,
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
        script.setSourceCode(f"{web_channel_source}\n({factory})({config});")
        self.web.page().scripts().insert(script)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.player.shutdown()
        super().closeEvent(event)

    @staticmethod
    def _server_url(server: str) -> str:
        return normalize_server_url(server)
