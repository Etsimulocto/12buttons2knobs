#!/usr/bin/env python3
"""12buttons2knobs: Raspberry Pi macro-pad dashboard and assignment app."""
from __future__ import annotations
import argparse, fcntl, json, os, queue, shlex, shutil, socket, subprocess, threading, time, webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "12buttons2knobs"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_PATH = CONFIG_DIR / "profile.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
AUTOSTART_PATH = Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"
INSTANCE_LOCK_PATH = CONFIG_DIR / "instance.lock"
INSTANCE_SOCKET_PATH = CONFIG_DIR / "instance.sock"
PAD_USB_ID = (0x1189, 0x8840)
# Codes reported by evtest for this pad's A–L button sequence.
PAD_BUTTON_CODES = (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38)
PAD_BUTTON_NAMES = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L")
WINDOW_SIZES = {"Compact": "1040x680", "Standard": "1240x800", "Large": "1420x900", "Maximized": "1240x800"}
THEMES = {
    "Midnight": {"bg": "#101018", "panel": "#1a1a27", "fg": "#ececf4", "muted": "#a8a6bd", "key": "#d4d1db", "keyfg": "#17151f"},
    "Light": {"bg": "#eef0f5", "panel": "#ffffff", "fg": "#202130", "muted": "#626579", "key": "#d9dce8", "keyfg": "#202130"},
    "Graphite": {"bg": "#17191c", "panel": "#24282d", "fg": "#f0f2f4", "muted": "#a8b0b8", "key": "#d2d7dc", "keyfg": "#17191c"},
}
ACCENTS = {"Violet": "#7650ad", "Teal": "#087f8c", "Blue": "#3267b2", "Amber": "#ad6b18", "Rose": "#a84468"}
CONTROLS = [f"button_{i:02d}" for i in range(1, 13)] + [
    f"knob_{n}_{direction}" for n in (1, 2) for direction in ("ccw", "press", "cw")
]
CONTROL_LABELS = {
    **{f"button_{i:02d}": f"Button {i:02d}" for i in range(1, 13)},
    **{f"knob_{n}_{d}": f"Knob {n} {d.upper()}" for n in (1, 2) for d in ("ccw", "press", "cw")},
}
ACTION_TYPES = ("Unassigned", "Run command", "Send key/button combo", "Copy file", "Open URL")
# Display label -> (event type, Linux input code name, value). Slots are stored
# by their stable display label in profiles so they remain readable/editable.
INPUT_OUTPUT_CATALOG = {"— None —": None}
INPUT_OUTPUT_CATALOG.update({f"{name}": ("EV_KEY", f"KEY_{name}", 1) for name in
    ("LEFTCTRL", "LEFTSHIFT", "LEFTALT", "LEFTMETA", "RIGHTCTRL", "RIGHTSHIFT", "RIGHTALT", "RIGHTMETA")})
# Short display names keep all four drop-down columns readable in the editor.
INPUT_OUTPUT_CATALOG.update({"CTRL": INPUT_OUTPUT_CATALOG.pop("LEFTCTRL"),
                             "SHIFT": INPUT_OUTPUT_CATALOG.pop("LEFTSHIFT"),
                             "ALT": INPUT_OUTPUT_CATALOG.pop("LEFTALT"),
                             "META": INPUT_OUTPUT_CATALOG.pop("LEFTMETA"),
                             "R CTRL": INPUT_OUTPUT_CATALOG.pop("RIGHTCTRL"),
                             "R SHIFT": INPUT_OUTPUT_CATALOG.pop("RIGHTSHIFT"),
                             "R ALT": INPUT_OUTPUT_CATALOG.pop("RIGHTALT"),
                             "R META": INPUT_OUTPUT_CATALOG.pop("RIGHTMETA")})
INPUT_OUTPUT_CATALOG.update({f"{chr(letter)}": ("EV_KEY", f"KEY_{chr(letter)}", 1) for letter in range(ord("A"), ord("Z") + 1)})
INPUT_OUTPUT_CATALOG.update({str(number): ("EV_KEY", f"KEY_{number}", 1) for number in range(10)})
INPUT_OUTPUT_CATALOG.update({f"F{number}": ("EV_KEY", f"KEY_F{number}", 1) for number in range(1, 13)})
INPUT_OUTPUT_CATALOG.update({label: ("EV_KEY", code, 1) for label, code in {
    "Esc": "KEY_ESC", "Enter": "KEY_ENTER", "Space": "KEY_SPACE", "Tab": "KEY_TAB",
    "Backspace": "KEY_BACKSPACE", "Delete": "KEY_DELETE", "Insert": "KEY_INSERT",
    "Home": "KEY_HOME", "End": "KEY_END", "Page Up": "KEY_PAGEUP", "Page Down": "KEY_PAGEDOWN",
    "Up": "KEY_UP", "Down": "KEY_DOWN", "Left": "KEY_LEFT", "Right": "KEY_RIGHT",
    "Caps Lock": "KEY_CAPSLOCK", "Num Lock": "KEY_NUMLOCK", "Print Screen": "KEY_SYSRQ",
    "Pause": "KEY_PAUSE", "-": "KEY_MINUS", "=": "KEY_EQUAL", "[": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE", "\\": "KEY_BACKSLASH", ";": "KEY_SEMICOLON", "'": "KEY_APOSTROPHE",
    "`": "KEY_GRAVE", ",": "KEY_COMMA", ".": "KEY_DOT", "/": "KEY_SLASH",
    "Numpad 0": "KEY_KP0", "Numpad 1": "KEY_KP1", "Numpad 2": "KEY_KP2", "Numpad 3": "KEY_KP3",
    "Numpad 4": "KEY_KP4", "Numpad 5": "KEY_KP5", "Numpad 6": "KEY_KP6", "Numpad 7": "KEY_KP7",
    "Numpad 8": "KEY_KP8", "Numpad 9": "KEY_KP9", "Numpad Enter": "KEY_KPENTER",
    "Numpad +": "KEY_KPPLUS", "Numpad -": "KEY_KPMINUS", "Numpad *": "KEY_KPASTERISK",
    "Numpad /": "KEY_KPSLASH", "Numpad .": "KEY_KPDOT",
}.items()})
INPUT_OUTPUT_CATALOG.update({f"F{number}": ("EV_KEY", f"KEY_F{number}", 1) for number in range(13, 25)})
INPUT_OUTPUT_CATALOG.update({label: ("EV_KEY", code, 1) for label, code in {
    "Menu": "KEY_MENU", "Compose": "KEY_COMPOSE", "Power": "KEY_POWER",
    "Mute": "KEY_MUTE", "Volume +": "KEY_VOLUMEUP", "Volume -": "KEY_VOLUMEDOWN",
    "Play/Pause": "KEY_PLAYPAUSE", "Next Track": "KEY_NEXTSONG", "Prev Track": "KEY_PREVIOUSSONG",
    "Stop Media": "KEY_STOPCD", "Browser": "KEY_WWW", "Browser Back": "KEY_BACK",
    "Web Forward": "KEY_FORWARD",
}.items()})
INPUT_OUTPUT_CATALOG.update({label: ("EV_KEY", code, 1) for label, code in {
    "Mouse Left": "BTN_LEFT", "Mouse Right": "BTN_RIGHT", "Mouse Mid": "BTN_MIDDLE",
    "Mouse Side": "BTN_SIDE", "Mouse Extra": "BTN_EXTRA",
    "Pad A/South": "BTN_SOUTH", "Pad B/East": "BTN_EAST",
    "Pad X/West": "BTN_WEST", "Pad Y/North": "BTN_NORTH",
    "Pad LB": "BTN_TL", "Pad RB": "BTN_TR", "Pad LT": "BTN_TL2",
    "Pad RT": "BTN_TR2", "Pad Select": "BTN_SELECT", "Pad Start": "BTN_START",
    "Pad Guide": "BTN_MODE", "Pad L3": "BTN_THUMBL", "Pad R3": "BTN_THUMBR",
}.items()})
INPUT_OUTPUT_CATALOG.update({label: ("EV_ABS", code, value) for label, code, value in (
    ("DPAD LEFT", "ABS_HAT0X", -1), ("DPAD RIGHT", "ABS_HAT0X", 1),
    ("DPAD UP", "ABS_HAT0Y", -1), ("DPAD DOWN", "ABS_HAT0Y", 1),
    ("Left Axis ←", "ABS_X", -32767), ("Left Axis →", "ABS_X", 32767),
    ("Left Axis ↑", "ABS_Y", -32767), ("Left Axis ↓", "ABS_Y", 32767),
    ("Right Axis ←", "ABS_RX", -32767), ("Right Axis →", "ABS_RX", 32767),
    ("Right Axis ↑", "ABS_RY", -32767), ("Right Axis ↓", "ABS_RY", 32767),
    ("LT axis", "ABS_Z", 255), ("RT axis", "ABS_RZ", 255),
)})
INPUT_OUTPUT_CATALOG.update({"Wheel Up": ("EV_REL", "REL_WHEEL", 1),
                             "Wheel Down": ("EV_REL", "REL_WHEEL", -1),
                             "Wheel Left": ("EV_REL", "REL_HWHEEL", -1),
                             "Wheel Right": ("EV_REL", "REL_HWHEEL", 1)})
INPUT_OUTPUT_OPTIONS = tuple(INPUT_OUTPUT_CATALOG)
_VIRTUAL_INPUT = None

def compile_input_combo(slots, ecodes):
    """Resolve four UI choices to Linux event triples, rejecting axis conflicts."""
    if len(slots) > 4:
        raise ValueError("A combo can contain up to four outputs.")
    events = {}
    for label in slots:
        if not label or label == "— None —":
            continue
        spec = INPUT_OUTPUT_CATALOG.get(label)
        if spec is None:
            raise ValueError(f"Unknown key/button selection: {label}")
        type_name, code_name, value = spec
        key = (getattr(ecodes, type_name), getattr(ecodes, code_name))
        if key in events and events[key] != value:
            raise ValueError(f"Conflicting selections for {label.split()[0]} axis/direction.")
        events[key] = value
    if not events:
        raise ValueError("Choose at least one key, mouse button, or gamepad control.")
    return events

def _get_virtual_input(ecodes):
    global _VIRTUAL_INPUT
    if _VIRTUAL_INPUT is not None:
        return _VIRTUAL_INPUT
    from evdev import AbsInfo, UInput
    capabilities = {ecodes.EV_KEY: set(), ecodes.EV_REL: set(), ecodes.EV_ABS: []}
    abs_ranges = {
        "ABS_HAT0X": (-1, 1), "ABS_HAT0Y": (-1, 1),
        "ABS_X": (-32767, 32767), "ABS_Y": (-32767, 32767),
        "ABS_RX": (-32767, 32767), "ABS_RY": (-32767, 32767),
        "ABS_Z": (0, 255), "ABS_RZ": (0, 255),
    }
    for spec in INPUT_OUTPUT_CATALOG.values():
        if not spec:
            continue
        type_name, code_name, _value = spec
        event_type = getattr(ecodes, type_name)
        code = getattr(ecodes, code_name)
        if event_type == ecodes.EV_KEY:
            capabilities[ecodes.EV_KEY].add(code)
        elif event_type == ecodes.EV_REL:
            capabilities[ecodes.EV_REL].add(code)
    for code_name, (minimum, maximum) in abs_ranges.items():
        code = getattr(ecodes, code_name)
        capabilities[ecodes.EV_ABS].append((code, AbsInfo(0, minimum, maximum, 0, 0, 0)))
    capabilities = {event_type: list(codes) for event_type, codes in capabilities.items() if codes}
    _VIRTUAL_INPUT = UInput(capabilities, name="12buttons2knobs Output")
    return _VIRTUAL_INPUT

def close_virtual_input():
    global _VIRTUAL_INPUT
    if _VIRTUAL_INPUT is not None:
        _VIRTUAL_INPUT.close()
        _VIRTUAL_INPUT = None

def send_input_combo(slots):
    """Tap a selected keyboard/mouse/gamepad chord through Linux uinput."""
    try:
        import evdev
    except ImportError as exc:
        raise RuntimeError("Install python3-evdev to send keyboard, mouse, or gamepad input.") from exc
    events = compile_input_combo(slots, evdev.ecodes)
    device = _get_virtual_input(evdev.ecodes)
    for (event_type, code), value in events.items():
        device.write(event_type, code, value)
    device.syn()
    time.sleep(0.04)
    for (event_type, code), value in events.items():
        if event_type == evdev.ecodes.EV_KEY:
            device.write(event_type, code, 0)
        elif event_type == evdev.ecodes.EV_ABS:
            device.write(event_type, code, 0)
    device.syn()

def fresh_profile():
    return {"name": "Default", "labels": {}, "actions": {}, "input_device": "", "bindings": {}}

def fresh_settings():
    return {"theme": "Midnight", "accent": "Violet", "window_size": "Standard", "geometry": "", "autostart": True}

def load_settings(path=SETTINGS_PATH):
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    settings = fresh_settings()
    if isinstance(loaded, dict):
        settings.update({key: value for key, value in loaded.items() if key in settings and isinstance(value, type(settings[key]))})
    if settings["theme"] not in THEMES: settings["theme"] = "Midnight"
    if settings["accent"] not in ACCENTS: settings["accent"] = "Violet"
    if settings["window_size"] not in WINDOW_SIZES: settings["window_size"] = "Standard"
    return settings

def save_settings(settings, path=SETTINGS_PATH):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

def set_autostart(enabled, app_path=None):
    """Install/remove a per-user desktop login entry for plug monitoring."""
    if not enabled:
        AUTOSTART_PATH.unlink(missing_ok=True)
        return
    executable = Path(app_path or __file__).resolve()
    AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART_PATH.write_text(
        "[Desktop Entry]\nType=Application\nName=12buttons2knobs controller monitor\n"
        f'Exec=/usr/bin/python3 "{executable}" --background\nTerminal=false\nX-GNOME-Autostart-enabled=true\n',
        encoding="utf-8",
    )

def notify_running_instance():
    """Ask the existing app window to come forward instead of opening a duplicate."""
    address = str(INSTANCE_SOCKET_PATH)
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        for _ in range(12):
            try:
                client.sendto(b"show", address)
                return True
            except OSError:
                time.sleep(0.1)
    return False

def acquire_instance_lock():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(INSTANCE_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        notify_running_instance()
        os.close(fd)
        return None

class InstanceNotifier:
    """Local per-user socket used by repeat launches to raise the current window."""
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        INSTANCE_SOCKET_PATH.unlink(missing_ok=True)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(INSTANCE_SOCKET_PATH))
        os.chmod(INSTANCE_SOCKET_PATH, 0o600)
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def _listen(self):
        while not self.stop_event.is_set():
            try:
                message = self.sock.recv(32)
                if message == b"show":
                    self.app.events.put(("show", ""))
            except OSError:
                break

    def close(self):
        self.stop_event.set()
        try: self.sock.close()
        except OSError: pass
        INSTANCE_SOCKET_PATH.unlink(missing_ok=True)

def load_profile(path=CONFIG_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        profile = fresh_profile()
        if isinstance(data, dict):
            for key, value in data.items():
                if key in profile and isinstance(value, type(profile[key])):
                    profile[key] = value
        return profile
    except (OSError, json.JSONDecodeError):
        return fresh_profile()

def save_profile(profile, path=CONFIG_PATH):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

def perform_action(action):
    """Run one explicitly configured local action."""
    kind = action.get("type", "")
    if kind == "command":
        args = shlex.split(action.get("command", ""))
        if not args:
            raise ValueError("Enter a command first.")
        subprocess.Popen(args, start_new_session=True)
    elif kind == "copy_file":
        source = Path(os.path.expandvars(os.path.expanduser(action.get("source", ""))))
        destination = Path(os.path.expandvars(os.path.expanduser(action.get("destination", ""))))
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        # Treat a suffix-free destination as a folder, even when it does not
        # exist yet. A destination with a suffix is an explicit filename.
        if (destination.exists() and destination.is_dir()) or not destination.suffix:
            destination.mkdir(parents=True, exist_ok=True)
            destination /= source.name
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    elif kind == "open_url":
        url = action.get("url", "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        webbrowser.open(url)
    elif kind == "input_combo":
        send_input_combo(action.get("slots", []))
    elif kind not in ("", "none"):
        raise ValueError(f"Unknown action type: {kind}")

class EvdevReader:
    """Optional Linux input-event reader."""
    def __init__(self, output):
        self.output, self.stop_event, self.device, self.thread = output, threading.Event(), None, None
    @staticmethod
    def devices():
        try:
            import evdev
        except ImportError:
            return []
        found = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                found.append((path, d.name))
                d.close()
            except OSError:
                pass
        return found
    @staticmethod
    def device_details():
        try:
            import evdev
        except ImportError:
            return []
        found = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                if d.name == "12buttons2knobs Output":
                    d.close()
                    continue
                caps = d.capabilities()
                found.append({"path": path, "name": d.name, "vendor": d.info.vendor,
                              "product": d.info.product, "key_capable": evdev.ecodes.EV_KEY in caps,
                              "relative_capable": evdev.ecodes.EV_REL in caps,
                              "axis_capable": evdev.ecodes.EV_ABS in caps})
                d.close()
            except OSError:
                pass
        return found
    def stop(self):
        self.stop_event.set()
        if self.device:
            try: self.device.close()
            except OSError: pass
        self.device, self.thread = None, None
    def start(self, path):
        self.stop()
        self.stop_event = threading.Event()
        if not path:
            return
        try:
            import evdev
        except ImportError:
            self.output.put(("error", "Install python3-evdev to read physical controls."))
            return
        def read_loop():
            try:
                device = evdev.InputDevice(path)
                self.device = device
                device.grab()
                for event in device.read_loop():
                    if self.stop_event.is_set(): break
                    if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                        self.output.put(("input", f"key:{event.code}"))
                    elif event.type == evdev.ecodes.EV_KEY and event.value == 0:
                        self.output.put(("release", f"key:{event.code}"))
                    elif event.type == evdev.ecodes.EV_KEY and event.value == 2:
                        self.output.put(("repeat", f"key:{event.code}"))
                    elif event.type == evdev.ecodes.EV_REL and event.value:
                        self.output.put(("input", f"rel:{event.code}:{'+' if event.value > 0 else '-'}"))
                    elif event.type == evdev.ecodes.EV_ABS:
                        self.output.put(("input", f"abs:{event.code}:{event.value}"))
            except (OSError, PermissionError) as exc:
                if not self.stop_event.is_set():
                    self.output.put(("error", f"Input device error: {exc}"))
        self.thread = threading.Thread(target=read_loop, daemon=True)
        self.thread.start()

class MacroPadApp:
    def __init__(self, root, background=False):
        self.root = root
        self.settings = load_settings()
        if self.settings["autostart"]:
            try: set_autostart(True)
            except OSError: pass
        self.background = background
        self._was_connected = False
        self.instance_notifier = None
        self.instance_lock_fd = None
        root.title("12buttons2knobs · Pi Control Deck")
        root.geometry(self.settings.get("geometry") or WINDOW_SIZES[self.settings["window_size"]])
        root.minsize(1000, 600)
        if self.settings["window_size"] == "Maximized":
            try: root.state("zoomed")
            except tk.TclError: pass
        self.profile = load_profile()
        self.events = queue.Queue()
        self.reader = EvdevReader(self.events)
        self.control = tk.StringVar(value=CONTROLS[0])
        self.action_type = tk.StringVar(value="Unassigned")
        self.label = tk.StringVar()
        self.command = tk.StringVar()
        self.combo_slots = [tk.StringVar(value="— None —") for _ in range(4)]
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.url = tk.StringVar()
        self.device = tk.StringVar()
        self.learn_armed = False
        self.status = tk.StringVar(value="Ready · assign an action, then click a control to test it.")
        self.keys = {}
        self.control_widgets = {}
        self.knob_canvases = []
        self.log_entries = deque(maxlen=10)
        self._style()
        self._build()
        self._load_assignment()
        root.after(60, self._poll)
        root.after(900, self._watch_controller)
        root.protocol("WM_DELETE_WINDOW", self.close)
        if background:
            root.withdraw()

    def _style(self):
        colors = THEMES[self.settings["theme"]]
        bg, panel, fg, muted, key, keyfg = (colors[k] for k in ("bg", "panel", "fg", "muted", "key", "keyfg"))
        accent = ACCENTS[self.settings["accent"]]
        self.colors = {"bg": bg, "panel": panel, "fg": fg, "muted": muted,
                       "key": key, "keyfg": keyfg, "accent": accent}
        self.root.configure(bg=bg)
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TFrame", background=bg)
        s.configure("Panel.TFrame", background=panel)
        s.configure("TLabel", background=bg, foreground=fg, font=("DejaVu Sans", 10))
        s.configure("Panel.TLabel", background=panel, foreground=fg, font=("DejaVu Sans", 10))
        s.configure("Title.TLabel", background=bg, foreground=fg, font=("DejaVu Sans", 19, "bold"))
        s.configure("Sub.TLabel", background=bg, foreground=muted, font=("DejaVu Sans", 9))
        s.configure("Key.TButton", background=key, foreground=keyfg,
                    font=("DejaVu Sans", 10, "bold"), padding=12)
        s.map("Key.TButton", background=[("active", accent), ("pressed", accent)])
        s.configure("Accent.TButton", background=accent, foreground="white", padding=8)
        s.map("Accent.TButton", background=[("active", accent)])
        s.configure("TCombobox", fieldbackground=panel, background=panel, foreground=fg)
        s.configure("TEntry", fieldbackground=panel, foreground=fg)
        s.configure("TCheckbutton", background=panel, foreground=fg)
        s.map("TCheckbutton", background=[("active", panel)])
        s.configure("TLabelframe", background=panel, foreground=fg)
        s.configure("TLabelframe.Label", background=panel, foreground=accent)

    def _build(self):
        outer = ttk.Frame(self.root, padding=18); outer.pack(fill="both", expand=True)
        head = ttk.Frame(outer); head.pack(fill="x", pady=(0, 14))
        ttk.Label(head, text="12BUTTONS  ·  2KNOBS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, text="Pi Control Deck / assign controls to apps, files, URLs, and commands",
                  style="Sub.TLabel").pack(anchor="w", pady=(3, 0))
        body = ttk.Frame(outer); body.pack(fill="both", expand=True)
        self.deck = ttk.Frame(body, style="Panel.TFrame", padding=16)
        self.deck.pack(side="left", fill="both", expand=True, padx=(0, 14))
        self.editor_host = ttk.Frame(body, style="Panel.TFrame", width=570)
        self.editor_host.pack(side="right", fill="y"); self.editor_host.pack_propagate(False)
        self.editor_canvas = tk.Canvas(self.editor_host, bg=self.colors["panel"], highlightthickness=0, width=548)
        self.editor_scrollbar = ttk.Scrollbar(self.editor_host, orient="vertical", command=self.editor_canvas.yview)
        self.editor_canvas.configure(yscrollcommand=self.editor_scrollbar.set)
        self.editor_scrollbar.pack(side="right", fill="y")
        self.editor_canvas.pack(side="left", fill="both", expand=True)
        self.editor = ttk.Frame(self.editor_canvas, style="Panel.TFrame", padding=16)
        self.editor_window = self.editor_canvas.create_window((0, 0), window=self.editor, anchor="nw")
        self.editor.bind("<Configure>", lambda _e: self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all")))
        self.editor_canvas.bind("<Configure>", lambda e: self.editor_canvas.itemconfigure(self.editor_window, width=e.width))
        self._build_deck(); self._build_editor()
        foot = ttk.Frame(outer); foot.pack(fill="x", pady=(12, 0))
        ttk.Label(foot, textvariable=self.status, style="Sub.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(foot, text="Load profile…", command=self._open_profile).pack(side="right")
        ttk.Button(foot, text="Appearance / startup…", command=self._open_settings).pack(side="right", padx=(8, 0))
        ttk.Button(foot, text="Save profile", command=self._save).pack(side="right", padx=(8, 0))

    def _build_deck(self):
        ttk.Label(self.deck, text="CONTROL SURFACE", style="Panel.TLabel",
                  font=("DejaVu Sans", 11, "bold")).pack(anchor="w", pady=(0, 12))
        area = ttk.Frame(self.deck, style="Panel.TFrame"); area.pack(fill="both", expand=True)
        keys = ttk.Frame(area, style="Panel.TFrame"); keys.pack(side="left", fill="both", expand=True, padx=(0, 14))
        for i in range(12):
            control = f"button_{i+1:02d}"; row, col = divmod(i, 4)
            b = ttk.Button(keys, text=self._text(control), style="Key.TButton",
                           command=lambda c=control: self._activate(c))
            b.grid(row=row, column=col, padx=6, pady=7, sticky="nsew")
            self.keys[control] = b
            self.control_widgets[control] = b
            keys.grid_columnconfigure(col, weight=1, uniform="key")
            keys.grid_rowconfigure(row, weight=1, uniform="key")
        ttk.Label(self.deck, text="Touch the pad to light its matching key. Click a key to test its assignment.",
                  style="Panel.TLabel").pack(anchor="w", pady=(14, 0))

    def _knob(self, parent, n):
        box = ttk.Frame(parent, style="Panel.TFrame", padding=(5, 2, 5, 5)); box.pack(side="left", fill="x", expand=True)
        ttk.Label(box, text=f"KNOB {n}", style="Panel.TLabel",
                  font=("DejaVu Sans", 9, "bold")).pack(pady=(2, 4))
        c = tk.Canvas(box, width=74, height=74, bg=self.colors["panel"], highlightthickness=0); c.pack()
        c.create_oval(7, 7, 67, 67, fill=self.colors["bg"], outline=self.colors["muted"], width=3)
        c.create_oval(15, 15, 59, 59, fill=self.colors["panel"], outline=self.colors["muted"], width=2)
        c.create_line(37, 37, 37, 20, fill=self.colors["accent"], width=4)
        self.knob_canvases.append(c)
        row = ttk.Frame(box, style="Panel.TFrame"); row.pack(fill="x", pady=(6, 0))
        for text, suffix in (("◀", "ccw"), ("Press", "press"), ("▶", "cw")):
            control = f"knob_{n}_{suffix}"
            button = ttk.Button(row, text=text, command=lambda k=control: self._activate(k))
            button.pack(side="left", padx=1, fill="x", expand=True)
            self.control_widgets[control] = button

    def _build_editor(self):
        ttk.Label(self.editor, text="KNOBS + ASSIGNMENTS", style="Panel.TLabel",
                  font=("DejaVu Sans", 11, "bold")).pack(anchor="w", pady=(0, 5))
        knobs = ttk.Frame(self.editor, style="Panel.TFrame")
        knobs.pack(fill="x", pady=(0, 8))
        for n in (1, 2): self._knob(knobs, n)
        ttk.Separator(self.editor).pack(fill="x", pady=(0, 8))
        ttk.Label(self.editor, text="ASSIGN CONTROL", style="Panel.TLabel",
                  font=("DejaVu Sans", 11, "bold")).pack(anchor="w", pady=(0, 7))
        ttk.Label(self.editor, text="Control", style="Panel.TLabel").pack(anchor="w")
        combo = ttk.Combobox(self.editor, textvariable=self.control, values=CONTROLS, state="readonly", width=46)
        combo.pack(fill="x", pady=(3, 8)); combo.bind("<<ComboboxSelected>>", lambda _e: self._load_assignment())
        ttk.Label(self.editor, text="Deck label", style="Panel.TLabel").pack(anchor="w")
        ttk.Entry(self.editor, textvariable=self.label).pack(fill="x", pady=(3, 8))
        ttk.Label(self.editor, text="Action", style="Panel.TLabel").pack(anchor="w")
        choice = ttk.Combobox(self.editor, textvariable=self.action_type, values=ACTION_TYPES, state="readonly")
        choice.pack(fill="x", pady=(3, 8)); choice.bind("<<ComboboxSelected>>", lambda _e: self._show_fields())
        self.fields = ttk.Frame(self.editor, style="Panel.TFrame"); self.fields.pack(fill="x")
        self._show_fields()
        row = ttk.Frame(self.editor, style="Panel.TFrame"); row.pack(fill="x", pady=(8, 15))
        ttk.Button(row, text="Apply assignment", style="Accent.TButton", command=self._apply).pack(side="left")
        ttk.Button(row, text="Test", command=self._test).pack(side="left", padx=7)
        ttk.Separator(self.editor).pack(fill="x", pady=4)
        ttk.Label(self.editor, text="PHYSICAL USB INPUT", style="Panel.TLabel",
                  font=("DejaVu Sans", 10, "bold")).pack(anchor="w", pady=(10, 7))
        self.device_combo = ttk.Combobox(self.editor, textvariable=self.device, state="readonly", width=64, height=10)
        self.device_combo.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(self.editor, style="Panel.TFrame"); row.pack(fill="x")
        ttk.Button(row, text="Refresh", command=self._refresh_devices).pack(side="left")
        ttk.Button(row, text="Connect", command=self._connect).pack(side="left", padx=5)
        ttk.Button(row, text="Learn selected", command=self._learn).pack(side="left")
        ttk.Label(self.editor, text="Pick an event endpoint, Connect, then choose a control and click Learn. "
                  "The live log shows events from the connected endpoint. Requires Linux evdev access.",
                  style="Panel.TLabel", wraplength=500,
                  justify="left").pack(anchor="w", pady=(7, 0))
        ttk.Separator(self.editor).pack(fill="x", pady=(10, 6))
        log_head = ttk.Frame(self.editor, style="Panel.TFrame")
        log_head.pack(fill="x")
        ttk.Label(log_head, text="LIVE INPUT / ACTION LOG · LAST 10", style="Panel.TLabel",
                  font=("DejaVu Sans", 9, "bold")).pack(side="left", anchor="w")
        ttk.Button(log_head, text="Copy last 10", command=self._copy_log).pack(side="right")
        self.log_text = tk.Text(self.editor, height=10, wrap="char", state="disabled",
                                bg=self.colors["bg"], fg=self.colors["fg"],
                                insertbackground=self.colors["fg"], relief="flat",
                                font=("DejaVu Sans Mono", 8), padx=5, pady=5)
        self.log_text.pack(fill="x", pady=(5, 0))
        self._refresh_devices()

    def _open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Appearance and startup")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        frame.pack(fill="both", expand=True)
        theme_var = tk.StringVar(value=self.settings["theme"])
        accent_var = tk.StringVar(value=self.settings["accent"])
        size_var = tk.StringVar(value=self.settings["window_size"])
        autostart_var = tk.BooleanVar(value=self.settings["autostart"])
        ttk.Label(frame, text="Appearance", style="Panel.TLabel",
                  font=("DejaVu Sans", 12, "bold")).pack(anchor="w", pady=(0, 10))
        for label, variable, choices in (("Color theme", theme_var, tuple(THEMES)),
                                         ("Accent color", accent_var, tuple(ACCENTS)),
                                         ("Window size on launch", size_var, tuple(WINDOW_SIZES))):
            ttk.Label(frame, text=label, style="Panel.TLabel").pack(anchor="w")
            ttk.Combobox(frame, textvariable=variable, values=choices, state="readonly", width=28).pack(fill="x", pady=(3, 10))
        ttk.Checkbutton(frame, text="Start monitor at login; open deck when pad is plugged in",
                        variable=autostart_var).pack(anchor="w", pady=(2, 14))
        def apply_settings():
            self.settings.update(theme=theme_var.get(), accent=accent_var.get(),
                                  window_size=size_var.get(), autostart=autostart_var.get(), geometry="")
            try:
                set_autostart(self.settings["autostart"])
                save_settings(self.settings)
            except OSError as exc:
                messagebox.showerror("Settings could not be saved", str(exc), parent=dialog)
                return
            self._style()
            for canvas in self.knob_canvases:
                canvas.configure(bg=self.colors["panel"])
                canvas.itemconfigure(1, fill=self.colors["bg"], outline=self.colors["muted"])
                canvas.itemconfigure(2, fill=self.colors["panel"], outline=self.colors["muted"])
                canvas.itemconfigure(3, fill=self.colors["accent"])
            if size_var.get() == "Maximized":
                try: self.root.state("zoomed")
                except tk.TclError: self.root.geometry(WINDOW_SIZES["Maximized"])
            else:
                try: self.root.state("normal")
                except tk.TclError: pass
                self.root.geometry(WINDOW_SIZES[size_var.get()])
            self.status.set("Appearance and startup settings saved.")
            self._log("SETTINGS appearance/startup updated")
            dialog.destroy()
        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Apply", style="Accent.TButton", command=apply_settings).pack(side="right")
        ttk.Button(row, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 8))

    def _watch_controller(self):
        details = EvdevReader.device_details()
        matching = next((item for item in details
                         if (item["vendor"], item["product"]) == PAD_USB_ID and item["key_capable"]), None)
        if matching and not self._was_connected:
            self._was_connected = True
            self._refresh_devices()
            label = next((label for label, path in self.device_paths.items() if path == matching["path"]), "")
            if label:
                self.device.set(label)
                if self.background and not self.root.winfo_viewable():
                    self.show_window()
                self._connect()
        elif not matching and self._was_connected:
            self._was_connected = False
            self.reader.stop()
            self.status.set("Controller unplugged. Waiting for it to reconnect.")
            self._log("DISCONNECT controller unplugged")
        self.root.after(1400, self._watch_controller)

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        try: self.root.focus_force()
        except tk.TclError: pass

    def _show_fields(self):
        for w in self.fields.winfo_children(): w.destroy()
        kind = self.action_type.get()
        if kind == "Run command": self._field("Command and arguments", self.command)
        elif kind == "Send key/button combo":
            ttk.Label(self.fields, text="Choose up to four outputs (for example Ctrl + J). "
                      "Selections are tapped together.", style="Panel.TLabel", wraplength=500,
                      justify="left").pack(anchor="w", pady=(2, 6))
            slots = ttk.Frame(self.fields, style="Panel.TFrame")
            slots.pack(fill="x")
            for index, variable in enumerate(self.combo_slots):
                column = ttk.Frame(slots, style="Panel.TFrame")
                column.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 4, 0))
                ttk.Label(column, text=f"Slot {index + 1}", style="Panel.TLabel").pack(anchor="w")
                ttk.Combobox(column, textvariable=variable, values=INPUT_OUTPUT_OPTIONS,
                             state="readonly", width=12, height=14).pack(fill="x", pady=(3, 0))
                slots.grid_columnconfigure(index, weight=1, uniform="combo-slot")
        elif kind == "Copy file":
            self._field("Source file", self.source); self._field("Copy to (file or folder)", self.destination)
        elif kind == "Open URL": self._field("Web address", self.url)

    def _field(self, title, var):
        ttk.Label(self.fields, text=title, style="Panel.TLabel").pack(anchor="w", pady=(2, 3))
        ttk.Entry(self.fields, textvariable=var).pack(fill="x", pady=(0, 7))

    def _form_action(self):
        kind = self.action_type.get()
        if kind == "Run command": return {"type": "command", "command": self.command.get().strip()}
        if kind == "Send key/button combo":
            selected = [variable.get() for variable in self.combo_slots if variable.get() != "— None —"]
            return {"type": "input_combo", "slots": selected} if selected else {}
        if kind == "Copy file": return {"type": "copy_file", "source": self.source.get().strip(),
                                        "destination": self.destination.get().strip()}
        if kind == "Open URL": return {"type": "open_url", "url": self.url.get().strip()}
        return {}

    def _apply(self):
        control = self.control.get()
        if self.label.get().strip(): self.profile["labels"][control] = self.label.get().strip()
        else: self.profile["labels"].pop(control, None)
        action = self._form_action()
        if action: self.profile["actions"][control] = action
        else: self.profile["actions"].pop(control, None)
        self._refresh_deck(); self._save(True)
        self.status.set(f"Saved assignment for {CONTROL_LABELS[control]}.")
        action = self.profile["actions"].get(control)
        summary = " + ".join(action.get("slots", [])) if action and action.get("type") == "input_combo" else (action.get("type", "Unassigned") if action else "Unassigned")
        self._log(f"ASSIGN {CONTROL_LABELS[control]} → {summary}")

    def _load_assignment(self):
        control = self.control.get()
        self.label.set(self.profile["labels"].get(control, ""))
        action = self.profile["actions"].get(control, {})
        kinds = {"command": "Run command", "input_combo": "Send key/button combo",
                 "copy_file": "Copy file", "open_url": "Open URL"}
        self.action_type.set(kinds.get(action.get("type"), "Unassigned"))
        self.command.set(action.get("command", "")); self.source.set(action.get("source", ""))
        self.destination.set(action.get("destination", "")); self.url.set(action.get("url", ""))
        selected = list(action.get("slots", [])) if action.get("type") == "input_combo" else []
        for index, variable in enumerate(self.combo_slots):
            variable.set(selected[index] if index < len(selected) and selected[index] in INPUT_OUTPUT_CATALOG
                         else "— None —")
        if hasattr(self, "fields"): self._show_fields()

    def _text(self, control): return self.profile["labels"].get(control, CONTROL_LABELS[control])
    def _refresh_deck(self):
        for control, button in self.keys.items(): button.configure(text=self._text(control))
    def _activate(self, control):
        self.control.set(control); self._load_assignment(); self._run(control)
    def _run(self, control):
        action = self.profile["actions"].get(control)
        if not action:
            self.status.set(f"{CONTROL_LABELS[control]} has no action assigned.")
            self._log(f"UNASSIGNED action for {CONTROL_LABELS[control]}")
            return
        try:
            perform_action(action)
            self.status.set(f"Ran {self.profile['labels'].get(control, CONTROL_LABELS[control])}.")
            summary = " + ".join(action.get("slots", [])) if action.get("type") == "input_combo" else action.get("type", "unknown")
            self._log(f"ACTION {CONTROL_LABELS[control]} → {summary} OK")
        except Exception as exc:
            self.status.set(f"Action failed: {exc}")
            self._log(f"ERROR action {CONTROL_LABELS[control]}: {exc}")
            messagebox.showerror("Action failed", str(exc))
    def _test(self):
        control = self.control.get(); self._apply(); self._run(control)
    def _save(self, silent=False):
        try:
            save_profile(self.profile)
            if not silent:
                self.status.set(f"Profile saved: {CONFIG_PATH}")
                self._log("PROFILE saved")
        except OSError as exc: messagebox.showerror("Could not save profile", str(exc))
    def _open_profile(self):
        path = filedialog.askopenfilename(title="Load profile",
            filetypes=[("JSON profile", "*.json"), ("All files", "*.*")])
        if path:
            self.profile = load_profile(path); self._refresh_deck(); self._load_assignment()
            self.status.set(f"Loaded profile {self.profile.get('name', 'Default')}.")
            self._log(f"PROFILE loaded {Path(path).name}")
    def _refresh_devices(self):
        found = EvdevReader.device_details()
        found.sort(key=lambda item: (0 if (item["vendor"], item["product"]) == PAD_USB_ID else 1,
                                    0 if item["key_capable"] else 1,
                                    item["name"].lower(), item["path"]))
        self.device_paths = {}
        self.device_meta_by_path = {}
        for item in found:
            event = Path(item["path"]).name
            usb_id = f'{item["vendor"]:04x}:{item["product"]:04x}'
            is_pad = (item["vendor"], item["product"]) == PAD_USB_ID
            kinds = "+".join(name for name, enabled in (("KEY", item["key_capable"]),
                              ("REL", item["relative_capable"]), ("ABS", item["axis_capable"])) if enabled) or "OTHER"
            prefix = f"★ THIS PAD · {kinds}" if is_pad else kinds
            label = f'{prefix} | {item["name"]} | {usb_id} | {event}'
            self.device_paths[label] = item["path"]
            self.device_meta_by_path[item["path"]] = {"name": item["name"], "usb_id": usb_id}
        values = list(self.device_paths); self.device_combo.configure(values=values)
        active = next((label for label, path in self.device_paths.items()
                       if path == self.profile.get("input_device")), "")
        if active: self.device.set(active)
        elif values:
            preferred = next((label for label in values if label.startswith("★ THIS PAD")), values[0])
            self.device.set(preferred)
        else:
            self.device.set(""); self.status.set("No evdev input devices found. Install evdev and check permissions.")
    def _connect(self):
        path = self.device_paths.get(self.device.get(), "")
        if not path:
            self.status.set("Choose a detected device first.")
            self._log("ERROR connect: no device selected")
            return
        self.profile["input_device"] = path; self.reader.start(path); self._save(True)
        self.status.set(f"Listening to {self.device.get()}.")
        self._log(f"CONNECT {self.device.get()}")
    def _learn(self):
        if not self.profile.get("input_device"):
            self.status.set("Choose and connect the physical input first.")
            self._log("ERROR learn: connect an input device first")
            return
        self.learn_armed = True
        self.status.set(f"Learning {CONTROL_LABELS[self.control.get()]}: press or turn it now.")
        self._log(f"LEARN armed for {CONTROL_LABELS[self.control.get()]}")

    def _log(self, message):
        """Append one timestamped entry; deque caps the visible/copyable history at ten."""
        self.log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        if hasattr(self, "log_text"):
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", "\n".join(self.log_entries))
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

    def _copy_log(self):
        contents = "\n".join(self.log_entries)
        self.root.clipboard_clear()
        self.root.clipboard_append(contents)
        self.root.update_idletasks()
        self.status.set(f"Copied {len(self.log_entries)} log entr{'y' if len(self.log_entries) == 1 else 'ies'}.")

    def _event_source(self):
        path = getattr(self.reader.device, "path", None) if self.reader.device else None
        if path:
            meta = getattr(self, "device_meta_by_path", {}).get(path, {})
            return f"{meta.get('name', Path(path).name)} {meta.get('usb_id', '')} {Path(path).name}".strip()
        return self.device.get() or "input"

    @staticmethod
    def _format_input(value):
        if value.startswith("key:"):
            try:
                code = int(value.split(":", 1)[1])
                if code in PAD_BUTTON_CODES:
                    return f"key {PAD_BUTTON_NAMES[PAD_BUTTON_CODES.index(code)]}"
                # These are the number keys reported by the tested encoder.
                knob_keys = {2: "1", 4: "3", 5: "4", 7: "6"}
                if code in knob_keys:
                    return f"key {knob_keys[code]} (knob)"
                return f"key code {code}"
            except ValueError:
                return value
        if value.startswith("rel:"):
            _, code, direction = (value.split(":") + [""])[:3]
            return f"relative axis {code} {('right/up' if direction == '+' else 'left/down')}"
        if value.startswith("abs:"):
            _, code, axis_value = (value.split(":") + [""])[:3]
            return f"absolute axis {code} = {axis_value}"
        return value

    def _light_control(self, control, held=True, timed=False):
        widget = self.control_widgets.get(control)
        if not widget:
            return
        if held:
            widget.state(["pressed"])
            if timed:
                self.root.after(240, lambda w=widget: w.state(["!pressed"]))
        else:
            widget.state(["!pressed"])

    @staticmethod
    def _known_button(value):
        if not value.startswith("key:"):
            return None
        try:
            index = PAD_BUTTON_CODES.index(int(value.split(":", 1)[1]))
        except (ValueError, IndexError):
            return None
        return f"button_{index + 1:02d}"
    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "error":
                    self.status.set(value)
                    self._log(f"ERROR {value}")
                elif kind == "show": self.show_window()
                elif kind == "repeat":
                    self._log(f"INPUT {self._event_source()} · {self._format_input(value)} repeat")
                elif kind == "release":
                    self._log(f"INPUT {self._event_source()} · {self._format_input(value)} up")
                    control = self.profile["bindings"].get(value)
                    if control not in CONTROLS: control = self._known_button(value)
                    if control in CONTROLS: self._light_control(control, held=False)
                elif kind == "input":
                    self._log(f"INPUT {self._event_source()} · {self._format_input(value)} down")
                    if self.learn_armed:
                        self.profile["bindings"][value] = self.control.get()
                        self.learn_armed = False; self._save(True)
                        self._light_control(self.control.get())
                        self.status.set(f"Bound {value} to {CONTROL_LABELS[self.control.get()]}.")
                        self._log(f"BOUND {self._format_input(value)} → {CONTROL_LABELS[self.control.get()]}")
                    else:
                        control = self.profile["bindings"].get(value)
                        if control in CONTROLS:
                            self._light_control(control, timed=value.startswith("rel:"))
                            self._run(control)
                        else:
                            hinted = self._known_button(value)
                            if hinted:
                                self._light_control(hinted)
                                index = int(hinted[-2:]) - 1
                                self.status.set(f"Detected Button {index + 1:02d} (key {PAD_BUTTON_NAMES[index]}). Select it and click Learn selected to bind it.")
                                self._log(f"UNBOUND input; suggested {CONTROL_LABELS[hinted]}")
                            else:
                                self.status.set(f"Detected {value}, but it is unassigned. Select a control and click Learn selected.")
                                self._log(f"UNBOUND input {value}")
        except queue.Empty: pass
        self.root.after(60, self._poll)
    def close(self):
        self.reader.stop()
        close_virtual_input()
        if self.instance_notifier:
            self.instance_notifier.close()
            self.instance_notifier = None
        try:
            if self.root.state() == "zoomed":
                self.settings["window_size"] = "Maximized"
            else:
                self.settings["geometry"] = self.root.geometry()
            save_settings(self.settings)
        except (OSError, tk.TclError):
            pass
        self.root.destroy()
        if self.instance_lock_fd is not None:
            os.close(self.instance_lock_fd)
            self.instance_lock_fd = None

def main():
    parser = argparse.ArgumentParser(description="12-button / 2-knob Pi control deck")
    parser.add_argument("--background", action="store_true",
                        help="wait hidden for the known controller, then open and connect")
    args = parser.parse_args()
    lock_fd = acquire_instance_lock()
    if lock_fd is None:
        return
    app = None
    try:
        root = tk.Tk()
        app = MacroPadApp(root, background=args.background)
        app.instance_lock_fd = lock_fd
        app.instance_notifier = InstanceNotifier(app)
        root.mainloop()
    finally:
        if app and app.instance_notifier:
            app.instance_notifier.close()
            app.instance_notifier = None
        if app and app.instance_lock_fd is not None:
            os.close(app.instance_lock_fd)
            app.instance_lock_fd = None
        elif not app:
            os.close(lock_fd)

if __name__ == "__main__":
    main()
