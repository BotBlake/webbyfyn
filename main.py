from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow


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


class JellyfinWindow(QMainWindow):
    def __init__(self, server: str) -> None:
        super().__init__()

        self.server = server

        self.setWindowTitle("Webbyfin")
        self.resize(1280, 800)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)

        self.web.load(QUrl(self.server))

def main() -> int:
    args = parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Webbyfin")
    app.setOrganizationName("Webbyfin")

    window = JellyfinWindow(args.server)
    window.show()

    return app.exec()


if __name__ == "__main__":
    main()
    sys.exit()
