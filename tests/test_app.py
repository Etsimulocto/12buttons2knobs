import tempfile
import unittest
from pathlib import Path
from app import (fresh_profile, load_profile, save_profile, perform_action,
                 fresh_settings, load_settings, save_settings, MacroPadApp)

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

if __name__ == "__main__":
    unittest.main()
