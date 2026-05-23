import argparse
import json
import os
import sys

from process_utils import app_base_dir, ensure_xwayland, set_windows_app_user_model_id

BASE_DIR = str(app_base_dir())

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from radial_menu import RadialMenu


def _parse_args():
    parser = argparse.ArgumentParser(description="Show radial menu in a separate process.")
    parser.add_argument("--payload", required=True)
    return parser.parse_args()


def _emit(line: str):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    ensure_xwayland()
    os.chdir(BASE_DIR)
    args = _parse_args()
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        return 2

    set_windows_app_user_model_id("BandoriPet.RadialMenu")
    app = QApplication(sys.argv)
    app.setApplicationName("BandoriPet-RadialMenu")
    app.setOrganizationName("BandoriPet")
    app.setQuitOnLastWindowClosed(False)

    if sys.platform == "darwin":
        import macos_patch

        macos_patch.hide_dock_icon()

    menu = RadialMenu()
    menu.set_animation_fps(int(payload.get("fps", 120)))
    menu.set_locked(bool(payload.get("locked", False)))
    menu.lock_toggled.connect(lambda locked: _emit(f"LOCK\t{1 if locked else 0}"))
    menu.closed.connect(app.quit)

    for item in payload.get("items", []):
        action = str(item.get("action", "") or "").strip()
        label = str(item.get("label", "") or "")
        glyph = str(item.get("glyph", "") or "")
        color_values = item.get("color") or [80, 80, 80]
        enabled = bool(item.get("enabled", True))
        if not action or len(color_values) != 3:
            continue
        color = QColor(int(color_values[0]), int(color_values[1]), int(color_values[2]))
        menu.add_item(
            "",
            label,
            color,
            on_click=lambda act=action: _emit(f"ACT\t{act}"),
            glyph=glyph,
            enabled=enabled,
        )

    menu.prepare_for_show()
    QTimer.singleShot(0, lambda: menu.show_at(QPoint(int(payload.get("x", 0)), int(payload.get("y", 0)))))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
