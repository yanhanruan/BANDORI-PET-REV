from PySide6.QtNetwork import QLocalSocket

from process_utils import ipc_server_name


def send_ipc_message(message: str, timeout_ms: int = 200) -> bool:
    if not message:
        return False
    try:
        socket = QLocalSocket()
        socket.connectToServer(ipc_server_name())
        if not socket.waitForConnected(timeout_ms):
            socket.disconnectFromServer()
            return False
        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True
    except Exception:
        return False
