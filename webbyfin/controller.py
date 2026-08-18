from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QApplication

from .constants import CLIENT_NAME, CLIENT_VERSION
from .window import JellyfinWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="webbyfin",
        description="Minimal QtWebEngine Jellyfin client",
    )
    parser.add_argument(
        "--server",
        required=True,
        help="Jellyfin server URL, e.g. http://192.168.1.10:8096",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    app = QApplication(sys.argv)
    app.setApplicationName(CLIENT_NAME)
    app.setApplicationVersion(CLIENT_VERSION)
    app.setOrganizationName(CLIENT_NAME)

    window = JellyfinWindow(args.server)
    window.show()

    return app.exec()
