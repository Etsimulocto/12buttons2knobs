import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from app import (fresh_profile, load_profile, save_profile, perform_action,
                 fresh_settings, load_settings, save_settings, MacroPadApp,
                 compile_input_combo, INPUT_OUTPUT_CATALOG)

class ProfileTests(unittest.TestCase):
    def test_profile_round_trip(self):
        profile = fresh_profile()
        profile["actions"]["button_01"] = {"type": "open_url", "url": "https://example.com"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            save_profile(profile, path)
            self.assertEqual(load_profile(path), profile)

    def test_copy_file_to_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); source = base / "skycam.png"; destination = base / "copies"
            source.write_bytes(b"image sample")
            perform_action({"type": "copy_file", "source": str(source), "destination": str(destination)})
            self.assertEqual((destination / source.name).read_bytes(), b"image sample")

    def test_rejects_unsafe_url_scheme(self):
        with self.assertRaises(ValueError):
            perform_action({"type": "open_url", "url": "file:///etc/passwd"})

    def test_settings_round_trip(self):
        settings = fresh_settings()
        settings.update(theme="Light", accent="Teal", window_size="Large", geometry="1280x820+10+20", autostart=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)

    def test_pad_letter_codes_preview_button_order(self):
        self.assertEqual(MacroPadApp._known_button("key:30"), "button_01")
        self.assertEqual(MacroPadApp._known_button("key:38"), "button_12")
        self.assertIsNone(MacroPadApp._known_button("key:2"))

    def test_compile_keyboard_combo(self):
        codes = SimpleNamespace(EV_KEY=1, EV_REL=2, EV_ABS=3,
                                KEY_LEFTCTRL=29, KEY_J=36)
        self.assertEqual(compile_input_combo(["CTRL", "J"], codes),
                         {(1, 29): 1, (1, 36): 1})

    def test_compile_gamepad_combo_and_reject_conflicting_axis(self):
        codes = SimpleNamespace(EV_KEY=1, EV_REL=2, EV_ABS=3,
                                BTN_SOUTH=304, ABS_HAT0Y=17, ABS_X=0)
        self.assertEqual(compile_input_combo(["Pad A/South", "DPAD UP"], codes),
                         {(1, 304): 1, (3, 17): -1})
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            compile_input_combo(["Left Axis ←", "Left Axis →"], codes)

    def test_input_combo_action_uses_selected_slots(self):
        with patch("app.send_input_combo") as send:
            perform_action({"type": "input_combo", "slots": ["CTRL", "J"]})
        send.assert_called_once_with(["CTRL", "J"])

    def test_combo_limit_is_four(self):
        codes = SimpleNamespace(EV_KEY=1, EV_REL=2, EV_ABS=3, KEY_A=30)
        with self.assertRaisesRegex(ValueError, "up to four"):
            compile_input_combo(["A"] * 5, codes)

    def test_output_catalog_has_requested_control_families(self):
        self.assertIn("CTRL", INPUT_OUTPUT_CATALOG)
        self.assertIn("J", INPUT_OUTPUT_CATALOG)
        self.assertIn("Mouse Left", INPUT_OUTPUT_CATALOG)
        self.assertIn("DPAD UP", INPUT_OUTPUT_CATALOG)
        self.assertIn("Left Axis ←", INPUT_OUTPUT_CATALOG)


if __name__ == "__main__":
    unittest.main()
