import ctypes
import sys
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import mpv
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QWidget

from .constants import MPV_LOG_PREFIX


class MpvPlayer(QWidget):
    """Native Qt video surface backed by one lazy libmpv instance."""

    activeChanged = Signal(bool)
    playbackStarted = Signal()
    playbackEnded = Signal()
    playbackFailed = Signal(str)
    positionChanged = Signal(float)
    pauseChanged = Signal(bool)

    _fileLoaded = Signal(int)
    _fileEnded = Signal(int, int, int, int)
    _positionObserved = Signal(int, float)
    _pauseObserved = Signal(int, bool)
    _coreStopped = Signal(int)

    def __init__(self, server_url: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background: black;")

        server = urlsplit(server_url)
        self._server_url = server_url
        self._server_origin = server.scheme.lower(), server.netloc.lower()
        self._mpv: mpv.MPV | None = None
        self._entry_id: int | None = None
        self._loaded = False
        self._pending_subtitle: str | None = None
        self._closed = False

        queued = Qt.ConnectionType.QueuedConnection
        self._fileLoaded.connect(self._on_file_loaded, queued)
        self._fileEnded.connect(self._on_file_ended, queued)
        self._positionObserved.connect(self._on_position_changed, queued)
        self._pauseObserved.connect(self._on_pause_changed, queued)
        self._coreStopped.connect(self._on_core_stopped, queued)

    def dispatch(self, command: str, args: list[Any]) -> bool:
        """Execute one command produced by native.js."""

        try:
            if self._closed:
                raise RuntimeError("player is closed")

            match command:
                case "loadfile":
                    self._loadfile(args)
                case "stop":
                    self._stop()
                case "seek":
                    self._seek(args)
                case "set":
                    self._set_property(args)
                case "sub-add":
                    self._add_subtitle(args)
                case _:
                    raise ValueError("command is not allowed")
        except Exception as error:  # noqa: BLE001
            print(f"{MPV_LOG_PREFIX} rejected {command}: {error}", flush=True)
            return False

        return True

    def shutdown(self) -> None:
        """Stop libmpv before Qt destroys its native render surface."""

        if self._closed:
            return

        self._closed = True
        self._entry_id = None
        self._loaded = False
        self._pending_subtitle = None
        player, self._mpv = self._mpv, None

        if player is not None:
            try:
                player.terminate()
            except Exception as error:  # noqa: BLE001
                print(f"{MPV_LOG_PREFIX} shutdown failed: {error}", flush=True)

    def _loadfile(self, args: list[Any]) -> None:
        url, _, _, options = args
        player = self._ensure_player()

        self._loaded = False
        self._pending_subtitle = None
        player.pause = False
        result = player.command(
            "loadfile",
            self._media_url(url),
            "replace",
            -1,
            f"start={float(options['start']):.15g}",
        )
        self._entry_id = int(result["playlist_entry_id"])
        self.activeChanged.emit(True)

    def _stop(self) -> None:
        self._entry_id = None
        self._loaded = False
        self._pending_subtitle = None
        if self._mpv is not None and not self._mpv.core_shutdown:
            self._mpv.stop()
        self.activeChanged.emit(False)

    def _seek(self, args: list[Any]) -> None:
        seconds, _ = args
        self._ensure_player().seek(float(seconds), "absolute", "exact")

    def _set_property(self, args: list[Any]) -> None:
        name, value = args
        if name not in {"pause", "volume", "mute", "sid"}:
            raise ValueError("property is not allowed")
        setattr(self._ensure_player(), name, value)

    def _add_subtitle(self, args: list[Any]) -> None:
        url, _ = args
        url = self._media_url(url)
        if self._loaded:
            self._ensure_player().sub_add(url, "select")
        else:
            self._pending_subtitle = url

    def _ensure_player(self) -> mpv.MPV:
        if self._mpv is not None and not self._mpv.core_shutdown:
            return self._mpv

        # Creating this native child before playback can cover Qt WebEngine.
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        window_id = int(self.winId())
        if sys.platform == "win32":
            window_id = ctypes.c_uint32(window_id).value

        self._mpv = mpv.MPV(
            wid=str(window_id),
            idle=True,
            osc=True,
            input_default_bindings=True,
            input_vo_keyboard=True,
        )
        self._register_callbacks(self._mpv)
        return self._mpv

    def _register_callbacks(self, player: mpv.MPV) -> None:
        current_entry_id: int | None = None
        last_position_emit = 0.0

        @player.event_callback("start-file")
        def on_file_started(event: Any) -> None:
            nonlocal current_entry_id, last_position_emit
            current_entry_id = int(event.data.playlist_entry_id)
            last_position_emit = 0.0

        @player.event_callback("file-loaded")
        def on_file_loaded(_event: Any) -> None:
            if current_entry_id is not None:
                self._fileLoaded.emit(current_entry_id)

        @player.event_callback("end-file")
        def on_file_ended(event: Any) -> None:
            nonlocal current_entry_id
            data = event.data
            entry_id = int(data.playlist_entry_id)
            reason = int(data.reason)
            self._fileEnded.emit(
                entry_id,
                reason,
                int(data.error),
                int(data.playlist_insert_id),
            )
            if reason == mpv.MpvEventEndFile.QUIT:
                self._coreStopped.emit(entry_id)
            if current_entry_id == entry_id:
                current_entry_id = None

        @player.property_observer("time-pos")
        def on_position_changed(_name: str, value: Any) -> None:
            nonlocal last_position_emit
            if value is None or current_entry_id is None:
                return

            now = time.monotonic()
            if now - last_position_emit >= 0.5:
                last_position_emit = now
                self._positionObserved.emit(current_entry_id, float(value) * 1000)

        @player.property_observer("pause")
        def on_pause_changed(_name: str, value: Any) -> None:
            if current_entry_id is not None and type(value) is bool:
                self._pauseObserved.emit(current_entry_id, value)

    @Slot(int)
    def _on_file_loaded(self, entry_id: int) -> None:
        if entry_id != self._entry_id:
            return

        self._loaded = True
        subtitle, self._pending_subtitle = self._pending_subtitle, None
        if subtitle is not None and self._mpv is not None:
            try:
                self._mpv.sub_add(subtitle, "select")
            except Exception as error:  # noqa: BLE001
                print(f"{MPV_LOG_PREFIX} subtitle failed: {error}", flush=True)

        self.playbackStarted.emit()

    @Slot(int, int, int, int)
    def _on_file_ended(
        self,
        entry_id: int,
        reason: int,
        error_code: int,
        inserted_entry_id: int,
    ) -> None:
        if entry_id != self._entry_id:
            return
        if reason == mpv.MpvEventEndFile.REDIRECT:
            self._entry_id = inserted_entry_id
            return
        if reason not in {mpv.MpvEventEndFile.EOF, mpv.MpvEventEndFile.ERROR}:
            return

        self._entry_id = None
        self._loaded = False
        self._pending_subtitle = None
        self.activeChanged.emit(False)

        if reason == mpv.MpvEventEndFile.ERROR:
            self.playbackFailed.emit(f"MPV playback failed ({error_code})")
        else:
            self.playbackEnded.emit()

    @Slot(int, float)
    def _on_position_changed(self, entry_id: int, position: float) -> None:
        if entry_id == self._entry_id:
            self.positionChanged.emit(max(0.0, position))

    @Slot(int, bool)
    def _on_pause_changed(self, entry_id: int, paused: bool) -> None:
        if entry_id == self._entry_id:
            self.pauseChanged.emit(paused)

    @Slot(int)
    def _on_core_stopped(self, entry_id: int) -> None:
        if self._closed or entry_id != self._entry_id:
            return

        self._mpv = None
        self._entry_id = None
        self._loaded = False
        self._pending_subtitle = None
        self.activeChanged.emit(False)
        self.playbackEnded.emit()

    def _media_url(self, value: str) -> str:
        url = urljoin(self._server_url, value)
        parsed = urlsplit(url)
        if (parsed.scheme.lower(), parsed.netloc.lower()) != self._server_origin:
            raise ValueError("media URL must use the configured Jellyfin server")
        return url


class MpvBridge(QObject):
    """The deliberately small part of the player exposed to JavaScript."""

    playbackStarted = Signal()
    playbackEnded = Signal()
    playbackFailed = Signal(str)
    positionChanged = Signal(float)
    pauseChanged = Signal(bool)

    def __init__(self, player: MpvPlayer) -> None:
        super().__init__(player)
        self._player = player
        player.playbackStarted.connect(self.playbackStarted)
        player.playbackEnded.connect(self.playbackEnded)
        player.playbackFailed.connect(self.playbackFailed)
        player.positionChanged.connect(self.positionChanged)
        player.pauseChanged.connect(self.pauseChanged)

    @Slot(str, "QVariantList", result=bool)
    def dispatch(self, command: str, args: list[Any]) -> bool:
        return self._player.dispatch(command, args)
