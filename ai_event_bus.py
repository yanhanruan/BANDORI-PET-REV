import json

from ipc_bus import send_ipc_message


def publish_ai_event(data: dict):
    if not isinstance(data, dict):
        return
    try:
        payload = json.dumps(data, ensure_ascii=False)
        send_ipc_message(f"AI_EVENT\t{payload}\n", 200)
    except Exception:
        pass
