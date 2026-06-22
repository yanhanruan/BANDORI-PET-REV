def _scoped(scope: str, selector: str) -> str:
    scope = scope.strip()
    return f"{scope} {selector}" if scope else selector


def fluent_scrollbar_style(scope: str, background: str, *, dark: bool, width: int = 8) -> str:
    radius = max(3, width // 2)
    side_margin = 2 if width >= 8 else 1
    handle = "#5c6577" if dark else "#c2ccdc"
    handle_hover = "#727d91" if dark else "#aab7ca"
    handle_pressed = "#8792a5" if dark else "#909db0"
    return f"""
            {_scoped(scope, "QScrollBar:vertical")} {{
                background: transparent;
                border: none;
                width: {width}px;
                margin: 4px {side_margin}px 4px {side_margin}px;
            }}
            {_scoped(scope, "QScrollBar::handle:vertical")} {{
                background: {handle};
                border-radius: {radius}px;
                min-height: 32px;
            }}
            {_scoped(scope, "QScrollBar::handle:vertical:hover")} {{
                background: {handle_hover};
            }}
            {_scoped(scope, "QScrollBar::handle:vertical:pressed")} {{
                background: {handle_pressed};
            }}
            {_scoped(scope, "QScrollBar::add-line:vertical")},
            {_scoped(scope, "QScrollBar::sub-line:vertical")} {{
                background: {background};
                height: 0px;
            }}
            {_scoped(scope, "QScrollBar::add-page:vertical")},
            {_scoped(scope, "QScrollBar::sub-page:vertical")} {{
                background: transparent;
            }}
        """
