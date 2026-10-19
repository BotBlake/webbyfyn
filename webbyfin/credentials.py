from __future__ import annotations

import json
import logging
from typing import Any

import keyring
import keyring.errors
from PySide6.QtCore import QObject, Slot

from .constants import CLIENT_NAME

_LOGGER = logging.getLogger(__name__)

_SERVICE = CLIENT_NAME
_REQUIRED_FIELDS = ("Id", "UserId", "AccessToken")


def _valid_record(record: Any) -> bool:
    return isinstance(record, dict) and all(
        isinstance(record.get(field), str) and record[field] for field in _REQUIRED_FIELDS
    )


class SessionStore:
    """Remembered Jellyfin session kept in the OS keyring, one entry per server origin.

    Fails closed: if no secure backend is available nothing is stored.
    """

    def __init__(self, origin: str) -> None:
        self._origin = origin

    def load(self) -> dict[str, Any] | None:
        try:
            raw = keyring.get_password(_SERVICE, self._origin)
        except keyring.errors.KeyringError:
            _LOGGER.warning("Secure credential storage is unavailable; not restoring a session")
            return None
        if raw is None:
            return None
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            record = None
        if not _valid_record(record):
            self.clear()
            return None
        return record

    def save(self, record: dict[str, Any]) -> bool:
        if not _valid_record(record):
            return False
        try:
            keyring.set_password(_SERVICE, self._origin, json.dumps(record, separators=(",", ":")))
        except keyring.errors.KeyringError:
            _LOGGER.warning("Secure credential storage is unavailable; session not remembered")
            return False
        return True

    def clear(self) -> bool:
        try:
            keyring.delete_password(_SERVICE, self._origin)
        except keyring.errors.PasswordDeleteError:
            pass  # nothing stored
        except keyring.errors.KeyringError:
            _LOGGER.warning("Could not clear the remembered session from secure storage")
            return False
        return True


class SessionBridge(QObject):
    """QWebChannel object letting the Jellyfin page save or forget the remembered session."""

    def __init__(self, store: SessionStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store

    @Slot(str, result=bool)
    def save(self, payload: str) -> bool:
        try:
            record = json.loads(payload)
        except json.JSONDecodeError:
            return False
        return self._store.save(record)

    @Slot(result=bool)
    def clear(self) -> bool:
        return self._store.clear()
