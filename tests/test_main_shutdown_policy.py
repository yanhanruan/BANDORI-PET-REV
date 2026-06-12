from pathlib import Path


def test_tray_exit_defers_quit_until_context_menu_unwinds():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "exit_action.triggered.connect(lambda: QTimer.singleShot(0, quit_all))" in source


def test_main_shutdown_uses_cooperative_nonblocking_process_close():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "notify_child_processes_shutdown()" in source
    assert "QTimer.singleShot(50, app.quit)" in source
    assert "app.aboutToQuit.connect(notify_child_processes_shutdown)" in source
    assert "app.aboutToQuit.connect(lambda: close_settings_process(force=False, wait=False))" in source
    assert "app.aboutToQuit.connect(lambda: close_pet_processes(force=False, wait=False))" in source


def test_settings_process_handles_shutdown_ipc():
    source = Path("settings_process.py").read_text(encoding="utf-8")
    assert 'elif line == "SHUTDOWN":' in source
    assert "QTimer.singleShot(0, window.close)" in source


def test_chat_process_uses_immediate_shutdown_path():
    process_source = Path("chat_process.py").read_text(encoding="utf-8")
    window_source = Path("chat_window/chat_window.py").read_text(encoding="utf-8")
    assert "window.request_immediate_shutdown()" in process_source
    assert "def request_immediate_shutdown(self):" in window_source
    assert "if self._immediate_shutdown:" in window_source
