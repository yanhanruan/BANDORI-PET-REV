from ipc_bus import send_ipc_message


def publish_action(character: str, action: str):
    if not character or not action:
        return
    send_ipc_message(f"ACTION\t{character}\t{action}\n", 200)


def publish_lip_sync(character: str, level: float, form: float | None = None):
    if not character:
        return
    try:
        level = max(0.0, min(float(level), 1.0))
        suffix = ""
        if form is not None:
            form = max(-1.0, min(float(form), 1.0))
            suffix = f"\t{form:.3f}"
        send_ipc_message(f"LIP\t{character}\t{level:.3f}{suffix}\n", 50)
    except Exception:
        pass
