from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    # Default base dir (you can later make this configurable in settings)
    base_projects_dir = Path("./projects").resolve()

    w = MainWindow(base_projects_dir=base_projects_dir)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
