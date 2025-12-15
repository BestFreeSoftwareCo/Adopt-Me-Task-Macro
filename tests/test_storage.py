import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adoptme_macro.models import AppState, Dot, Settings
from adoptme_macro import storage


class StorageTests(unittest.TestCase):
    def test_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = AppState(
                settings=Settings(
                    start_stop_hotkey="f6",
                    pause_resume_hotkey="f7",
                    show_coordinates=True,
                    lock_dots=True,
                ),
                dots=[Dot(id="d1", name="Dot 1", x=123, y=456, click_type="key", key="{E}", delay_override_ms=111)],
            )

            with patch.object(storage, "project_dir", return_value=root):
                storage.save_config(state)
                loaded = storage.load_config()

            self.assertEqual(loaded.to_dict(), state.to_dict())

    def test_profile_roundtrip_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = AppState(
                settings=Settings(theme="light"),
                dots=[Dot(id="d2", name="A", x=1, y=2, click_type="click")],
            )

            with patch.object(storage, "project_dir", return_value=root):
                storage.save_profile("MyProfile", state)
                loaded = storage.load_profile("MyProfile")
                names = [n for (n, _mt) in storage.list_profiles()]

            self.assertEqual(loaded.to_dict(), state.to_dict())
            self.assertIn("MyProfile", names)


if __name__ == "__main__":
    unittest.main()
