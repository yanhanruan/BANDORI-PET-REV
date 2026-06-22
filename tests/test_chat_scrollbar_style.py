import unittest

from chat_window.scrollbar_style import fluent_scrollbar_style


class ChatScrollbarStyleTest(unittest.TestCase):
    def test_scoped_style_uses_fluent_scrollbar_states(self):
        style = fluent_scrollbar_style("QScrollArea#GroupListScroll", "#151923", dark=True)

        self.assertIn("QScrollArea#GroupListScroll QScrollBar:vertical", style)
        self.assertIn("width: 8px", style)
        self.assertIn("background: transparent", style)
        self.assertIn("QScrollArea#GroupListScroll QScrollBar::handle:vertical:hover", style)
        self.assertIn("QScrollArea#GroupListScroll QScrollBar::handle:vertical:pressed", style)
        self.assertIn("QScrollArea#GroupListScroll QScrollBar::add-page:vertical", style)
        self.assertIn("QScrollArea#GroupListScroll QScrollBar::sub-page:vertical", style)
        self.assertIn("border-radius: 4px", style)

    def test_unscoped_style_can_be_reused_inside_local_stylesheets(self):
        style = fluent_scrollbar_style("", "#ffffff", dark=False, width=6)

        self.assertIn("QScrollBar:vertical", style)
        self.assertIn("width: 6px", style)
        self.assertIn("QScrollBar::handle:vertical:hover", style)
        self.assertIn("QScrollBar::handle:vertical:pressed", style)
        self.assertNotIn("#GroupListScroll", style)


if __name__ == "__main__":
    unittest.main()
