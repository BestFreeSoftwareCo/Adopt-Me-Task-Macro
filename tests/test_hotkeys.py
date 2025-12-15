import unittest

from adoptme_macro import hotkeys


class HotkeyNormalizeTests(unittest.TestCase):
    def test_f_key_normalization(self) -> None:
        self.assertEqual(hotkeys._normalize_hotkey("f6"), "<f6>")

    def test_combo_normalization(self) -> None:
        self.assertEqual(hotkeys._normalize_hotkey("ctrl+shift+s"), "<ctrl>+<shift>+s")

    def test_passthrough_already_normalized(self) -> None:
        self.assertEqual(hotkeys._normalize_hotkey("<ctrl>+<shift>+s"), "<ctrl>+<shift>+s")

    def test_reject_empty(self) -> None:
        with self.assertRaises(ValueError):
            hotkeys._normalize_hotkey(" ")


if __name__ == "__main__":
    unittest.main()
