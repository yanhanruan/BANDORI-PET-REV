from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPalette, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QScrollArea, QSizePolicy,
    QApplication,
)

from qfluentwidgets import (
    PushButton, PrimaryPushButton, BodyLabel, StrongBodyLabel,
    FluentIcon, ScrollArea, isDarkTheme,
)
from qfluentwidgets.common.config import qconfig

from llm_manager import (
    build_system_prompt, LLMStreamWorker, NonStreamWorker,
    parse_action_tags, strip_action_tags,
)


_BG_LIGHT = "#ffffff"
_BG_DARK = "#1e1e1e"

_USER_BUBBLE_LIGHT = "#d1e8ff"
_USER_BUBBLE_DARK = "#1e3a5f"
_ASSIST_BUBBLE_LIGHT = "#f0f0f0"
_ASSIST_BUBBLE_DARK = "#2a2a2a"


def _theme_color(key: str) -> QColor:
    colors = {
        "bg": QColor(_BG_DARK if isDarkTheme() else _BG_LIGHT),
        "bubble_user": QColor(_USER_BUBBLE_DARK if isDarkTheme() else _USER_BUBBLE_LIGHT),
        "bubble_assist": QColor(_ASSIST_BUBBLE_DARK if isDarkTheme() else _ASSIST_BUBBLE_LIGHT),
    }
    return colors.get(key, QColor(_BG_LIGHT))


class MessageBubble(QWidget):
    def __init__(self, text: str, role: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._role = role
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        self._label = QLabel(self._text, self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = QFont()
        font.setPointSize(10)
        self._label.setFont(font)

        inner = QHBoxLayout()
        inner.setContentsMargins(10, 8, 10, 8)

        if self._role == "user":
            inner.addStretch()
            self._container = self._make_container(user=True)
            self._container.setLayout(QVBoxLayout())
            self._container.layout().setContentsMargins(0, 0, 0, 0)
            self._container.layout().addWidget(self._label)
            inner.addWidget(self._container)
            inner.setContentsMargins(40, 0, 0, 0)
        else:
            self._container = self._make_container(user=False)
            self._container.setLayout(QVBoxLayout())
            self._container.layout().setContentsMargins(0, 0, 0, 0)
            self._container.layout().addWidget(self._label)
            inner.addWidget(self._container)
            inner.addStretch()
            inner.setContentsMargins(0, 0, 40, 0)

        layout.addLayout(inner)

    def _make_container(self, user: bool) -> QWidget:
        w = QWidget()
        dark = isDarkTheme()
        bg = _USER_BUBBLE_DARK if user and dark else _USER_BUBBLE_LIGHT if user else _ASSIST_BUBBLE_DARK if dark else _ASSIST_BUBBLE_LIGHT
        radius = "12px 4px 12px 12px" if user else "4px 12px 12px 12px"
        w.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                border-radius: {radius};
                padding: 1px;
            }}
        """)
        return w

    def set_text(self, text: str):
        self._label.setText(text)


class ChatWindow(QWidget):
    action_triggered = Signal(str)
    closed = Signal()

    def __init__(self, character: str, model_manager, live2d_module,
                 config_manager, parent_pet=None):
        super().__init__()
        self._character = character
        self._model_manager = model_manager
        self._live2d = live2d_module
        self._cfg = config_manager
        self._parent_pet = parent_pet
        self._conv_id: int | None = None
        self._worker = None
        self._current_bubble: MessageBubble | None = None
        self._pending_actions: list[str] = []

        self._display_name = model_manager.get_display_name(character)

        from database_manager import DatabaseManager
        self._db = DatabaseManager()

        self.setWindowTitle(f"Chat - {self._display_name}")
        self.setMinimumSize(320, 480)
        self.resize(360, 560)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._init_ui()
        self._apply_theme()
        qconfig.themeChanged.connect(self._apply_theme)

        self._load_or_create_conversation()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._titlebar = self._build_titlebar()
        main_layout.addWidget(self._titlebar)

        self._msg_area = QWidget()
        self._msg_layout = QVBoxLayout(self._msg_area)
        self._msg_layout.setContentsMargins(0, 8, 0, 8)
        self._msg_layout.setSpacing(2)
        self._msg_layout.addStretch()

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._msg_area)
        main_layout.addWidget(self._scroll, 1)

        main_layout.addWidget(self._build_input_area())

    def _build_titlebar(self):
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setCursor(Qt.CursorShape.ArrowCursor)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(4)

        title = StrongBodyLabel(f"Chat - {self._display_name}", bar)
        layout.addWidget(title)
        layout.addStretch()

        new_btn = PushButton(FluentIcon.ADD, "", bar)
        new_btn.setFixedSize(28, 28)
        new_btn.setToolTip(self.tr("New Chat"))
        new_btn.clicked.connect(self._new_conversation)
        layout.addWidget(new_btn)

        close_btn = PushButton(FluentIcon.CLOSE, "", bar)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._drag_start = None

        def mouse_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.globalPosition().toPoint()

        def mouse_move(event):
            if self._drag_start is not None:
                delta = event.globalPosition().toPoint() - self._drag_start
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self._drag_start = event.globalPosition().toPoint()

        def mouse_release(event):
            self._drag_start = None

        bar.mousePressEvent = mouse_press
        bar.mouseMoveEvent = mouse_move
        bar.mouseReleaseEvent = mouse_release

        return bar

    def _build_input_area(self):
        area = QWidget()
        area.setFixedHeight(56)
        layout = QHBoxLayout(area)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText(self.tr("Type a message..."))
        self._input.setAcceptRichText(False)
        self._input.setFixedHeight(40)
        self._input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        font = QFont()
        font.setPointSize(10)
        self._input.setFont(font)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        send_btn = PrimaryPushButton(FluentIcon.SEND, "", area)
        send_btn.setFixedSize(36, 36)
        send_btn.clicked.connect(self._send_message)
        layout.addWidget(send_btn)

        self._input_area = area
        return area

    def eventFilter(self, obj, event):
        if obj == self._input and event.type() == QKeyEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and not event.modifiers():
                self._send_message()
                return True
            if event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                return False
        return super().eventFilter(obj, event)

    def _apply_theme(self):
        dark = isDarkTheme()
        bg = _BG_DARK if dark else _BG_LIGHT
        border = "#3a3a3a" if dark else "#e0e0e0"
        input_bg = "#2d2d2d" if dark else "#f5f5f5"
        input_border = "#555555" if dark else "#d0d0d0"
        text_color = "#ffffff" if dark else "#000000"
        title_bg = "#252525" if dark else "#fafafa"
        title_border = "#3a3a3a" if dark else "#e8e8e8"

        self.setStyleSheet(f"""
            ChatWindow {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        self._titlebar.setStyleSheet(f"""
            QWidget {{
                background: {title_bg};
                border-bottom: 1px solid {title_border};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
        """)

        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {input_bg};
                color: {text_color};
                border: 1px solid {input_border};
                border-radius: 20px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border-color: #60cdff;
            }}
        """)

        self._input_area.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)

        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {bg};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {bg};
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {'#555555' if dark else '#c0c0c0'};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(bg))
        self.setPalette(pal)

    def _load_or_create_conversation(self):
        last = self._db.get_last_conversation(self._character)
        if last:
            self._conv_id = last["id"]
        else:
            self._conv_id = self._db.create_conversation(self._character)
        self._load_messages()

    def _new_conversation(self):
        self._msg_layout.removeItem(self._msg_layout.itemAt(self._msg_layout.count() - 1))
        for i in range(self._msg_layout.count() - 1, -1, -1):
            item = self._msg_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._msg_layout.addStretch()
        self._conv_id = self._db.create_conversation(self._character)

    def _load_messages(self):
        if self._conv_id is None:
            return
        messages = self._db.get_messages(self._conv_id)
        stretch = self._msg_layout.takeAt(self._msg_layout.count() - 1)
        for m in messages:
            bubble = MessageBubble(m["content"], m["role"])
            self._msg_layout.addWidget(bubble)
        self._msg_layout.addStretch()
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _send_message(self):
        text = self._input.toPlainText().strip()
        if not text:
            return

        api_url = self._cfg.get("llm_api_url", "")
        api_key = self._cfg.get("llm_api_key", "")
        model_id = self._cfg.get("llm_model_id", "")

        if not api_url or not api_key or not model_id:
            bubble = MessageBubble(self.tr("Please configure LLM API settings first."), "assistant")
            self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
            self._scroll_to_bottom()
            return

        self._input.clear()
        self._input.setEnabled(False)

        user_bubble = MessageBubble(text, "user")
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, user_bubble)

        assist_bubble = MessageBubble("...", "assistant")
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, assist_bubble)
        self._current_bubble = assist_bubble
        self._scroll_to_bottom()

        if self._conv_id:
            self._db.add_message(self._conv_id, "user", text)

        system_prompt = build_system_prompt(self._character)
        messages = [{"role": "system", "content": system_prompt}]

        if self._conv_id:
            history = self._db.get_messages(self._conv_id)
            max_history = 20
            for m in history[-(max_history * 2):]:
                messages.append({"role": m["role"], "content": m["content"]})

        use_stream = True
        if use_stream:
            self._worker = LLMStreamWorker(api_url, api_key, model_id, messages)
            self._worker.chunk_received.connect(self._on_chunk_received)
            self._worker.finished.connect(self._on_response_finished)
            self._worker.error.connect(self._on_response_error)
        else:
            self._worker = NonStreamWorker(api_url, api_key, model_id, messages)
            self._worker.finished.connect(self._on_response_finished_nonstream)
            self._worker.error.connect(self._on_response_error)

        self._worker.start()

    def _on_chunk_received(self, text: str):
        self._pending_actions.extend(parse_action_tags(text))
        clean = strip_action_tags(text)
        if self._current_bubble:
            current = self._current_bubble._label.text()
            if current == "...":
                current = ""
            self._current_bubble.set_text(current + clean)
            self._scroll_to_bottom()
        self._flush_actions()

    def _on_response_finished(self, full_text: str, actions: list):
        self._pending_actions.extend(parse_action_tags(full_text))
        self._flush_actions()

        clean = strip_action_tags(full_text)
        if self._current_bubble:
            self._current_bubble.set_text(clean)

        if self._conv_id:
            self._db.add_message(self._conv_id, "assistant", clean)

        self._input.setEnabled(True)
        self._input.setFocus()
        self._worker = None
        self._current_bubble = None
        self._scroll_to_bottom()

    def _on_response_finished_nonstream(self, full_text: str, actions: list):
        acts = parse_action_tags(full_text)
        self._pending_actions.extend(acts)
        self._flush_actions()

        clean = strip_action_tags(full_text)
        if self._current_bubble:
            self._current_bubble.set_text(clean)

        if self._conv_id:
            self._db.add_message(self._conv_id, "assistant", clean)

        self._input.setEnabled(True)
        self._input.setFocus()
        self._worker = None
        self._current_bubble = None
        self._scroll_to_bottom()

    def _on_response_error(self, error_msg: str):
        if self._current_bubble:
            self._current_bubble.set_text(f"Error: {error_msg}")
        self._input.setEnabled(True)
        self._input.setFocus()
        self._worker = None
        self._current_bubble = None

    def _flush_actions(self):
        if not self._pending_actions:
            return
        for action in self._pending_actions:
            self.action_triggered.emit(action)
        self._pending_actions.clear()

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def position_next_to_pet(self, pet_window: QWidget):
        pet_geo = pet_window.geometry()
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
        else:
            screen_geo = pet_geo

        chat_w = self.width()
        left_space = pet_geo.left() - screen_geo.left()
        right_space = screen_geo.right() - pet_geo.right()

        if left_space >= chat_w + 20:
            x = pet_geo.left() - chat_w - 16
        elif right_space >= chat_w + 20:
            x = pet_geo.right() + 16
        else:
            x = max(screen_geo.left(), pet_geo.left() - chat_w - 16)

        y = pet_geo.top() + (pet_geo.height() - self.height()) // 2
        y = max(screen_geo.top(), min(y, screen_geo.bottom() - self.height()))
        self.move(x, y)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._db.close()
        self.closed.emit()
        super().closeEvent(event)
