from PySide6.QtNetwork import QLocalSocket

from process_utils import ipc_server_name

_ipc_socket = None


def send_ipc_message(message: str, timeout_ms: int = 200) -> bool:
    if not message:
        return False
    global _ipc_socket
    try:
        if _ipc_socket is None:
            _ipc_socket = QLocalSocket()
        if _ipc_socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            _ipc_socket.connectToServer(ipc_server_name())
        if _ipc_socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
            if not _ipc_socket.waitForConnected(timeout_ms):
                return False
        _ipc_socket.write(message.encode("utf-8"))
        _ipc_socket.flush()
        if not _ipc_socket.waitForBytesWritten(timeout_ms):
            _reset_socket()
            return False
        return True
    except Exception:
        _reset_socket()
        return False


def _reset_socket():
    global _ipc_socket
    try:
        if _ipc_socket is not None:
            _ipc_socket.disconnectFromServer()
    except Exception:
        pass
    _ipc_socket = None
