import threading

from PySide6.QtNetwork import QLocalSocket

from process_utils import ipc_server_name

_ipc_lock = threading.Lock()


def send_ipc_message(message: str, timeout_ms: int = 200) -> bool:
    if not message:
        return False
    with _ipc_lock:
        return _send_ipc_message_locked(message, timeout_ms)


def _send_ipc_message_locked(message: str, timeout_ms: int) -> bool:
    socket = QLocalSocket()
    try:
        socket.connectToServer(ipc_server_name())
        if socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
            if not socket.waitForConnected(timeout_ms):
                socket.abort()
                return False
        socket.write(message.encode("utf-8"))
        socket.flush()
        if not socket.waitForBytesWritten(timeout_ms):
            socket.abort()
            return False
        socket.disconnectFromServer()
        return True
    except Exception:
        socket.abort()
        return False
