from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

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

    app = QApplication(sys.argv)
    app.setApplicationName("Webbyfin")
    app.setOrganizationName("Webbyfin")

    window = JellyfinWindow(args.server)
    window.show()

    return app.exec()
