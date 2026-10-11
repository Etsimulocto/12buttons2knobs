#!/usr/bin/env python3
"""12buttons2knobs: Raspberry Pi macro-pad dashboard and assignment app."""
from __future__ import annotations
import argparse, fcntl, json, os, queue, shlex, shutil, socket, subprocess, threading, time, webbrowser
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
WINDOW_SIZES = {"Compact": "920x640", "Standard": "1100x740", "Large": "1320x860", "Maximized": "1100x740"}
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
ACTION_TYPES = ("Unassigned", "Run command", "Copy file", "Open URL")

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
                found.append({"path": path, "name": d.name, "vendor": d.info.vendor, "product": d.info.product})
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
                    elif event.type == evdev.ecodes.EV_REL and event.value:
                        self.output.put(("input", f"rel:{event.code}:{'+' if event.value > 0 else '-'}"))
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
        root.minsize(760, 520)
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
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.url = tk.StringVar()
        self.device = tk.StringVar()
        self.learn_armed = False
        self.status = tk.StringVar(value="Ready · assign an action, then click a control to test it.")
        self.keys = {}
        self.control_widgets = {}
        self.knob_canvases = []
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
        self.editor = ttk.Frame(body, style="Panel.TFrame", padding=16, width=360)
        self.editor.pack(side="right", fill="y"); self.editor.pack_propagate(False)
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
        knobs = ttk.Frame(area, style="Panel.TFrame"); knobs.pack(side="right", fill="y")
        for n in (1, 2): self._knob(knobs, n)
        ttk.Label(self.deck, text="Click a key or knob action to test its assignment.",
                  style="Panel.TLabel").pack(anchor="w", pady=(14, 0))

    def _knob(self, parent, n):
        box = ttk.Frame(parent, style="Panel.TFrame", padding=(4, 0, 4, 14)); box.pack(fill="x")
        ttk.Label(box, text=f"KNOB {n}", style="Panel.TLabel",
                  font=("DejaVu Sans", 9, "bold")).pack(pady=(2, 5))
        c = tk.Canvas(box, width=100, height=100, bg=self.colors["panel"], highlightthickness=0); c.pack()
        c.create_oval(11, 11, 89, 89, fill=self.colors["bg"], outline=self.colors["muted"], width=3)
        c.create_oval(20, 20, 80, 80, fill=self.colors["panel"], outline=self.colors["muted"], width=2)
        c.create_line(50, 50, 50, 27, fill=self.colors["accent"], width=4)
        self.knob_canvases.append(c)
        row = ttk.Frame(box, style="Panel.TFrame"); row.pack(fill="x", pady=(6, 0))
        for text, suffix in (("◀", "ccw"), ("Press", "press"), ("▶", "cw")):
            control = f"knob_{n}_{suffix}"
            button = ttk.Button(row, text=text, command=lambda k=control: self._activate(k))
            button.pack(side="left", padx=2)
            self.control_widgets[control] = button

    def _build_editor(self):
        ttk.Label(self.editor, text="ASSIGN CONTROL", style="Panel.TLabel",
                  font=("DejaVu Sans", 11, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(self.editor, text="Control", style="Panel.TLabel").pack(anchor="w")
        combo = ttk.Combobox(self.editor, textvariable=self.control, values=CONTROLS, state="readonly")
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
        self.device_combo = ttk.Combobox(self.editor, textvariable=self.device, state="readonly")
        self.device_combo.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(self.editor, style="Panel.TFrame"); row.pack(fill="x")
        ttk.Button(row, text="Refresh", command=self._refresh_devices).pack(side="left")
        ttk.Button(row, text="Connect", command=self._connect).pack(side="left", padx=5)
        ttk.Button(row, text="Learn selected", command=self._learn).pack(side="left")
        ttk.Label(self.editor, text="Select a control, click Learn, then press or turn it. "
                  "Requires Linux evdev access.", style="Panel.TLabel", wraplength=320,
                  justify="left").pack(anchor="w", pady=(7, 0))
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
            dialog.destroy()
        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Apply", style="Accent.TButton", command=apply_settings).pack(side="right")
        ttk.Button(row, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 8))

    def _watch_controller(self):
        details = EvdevReader.device_details()
        matching = next((item for item in details
                         if (item["vendor"], item["product"]) == PAD_USB_ID), None)
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
        elif kind == "Copy file":
            self._field("Source file", self.source); self._field("Copy to (file or folder)", self.destination)
        elif kind == "Open URL": self._field("Web address", self.url)

    def _field(self, title, var):
        ttk.Label(self.fields, text=title, style="Panel.TLabel").pack(anchor="w", pady=(2, 3))
        ttk.Entry(self.fields, textvariable=var).pack(fill="x", pady=(0, 7))

    def _form_action(self):
        kind = self.action_type.get()
        if kind == "Run command": return {"type": "command", "command": self.command.get().strip()}
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

    def _load_assignment(self):
        control = self.control.get()
        self.label.set(self.profile["labels"].get(control, ""))
        action = self.profile["actions"].get(control, {})
        kinds = {"command": "Run command", "copy_file": "Copy file", "open_url": "Open URL"}
        self.action_type.set(kinds.get(action.get("type"), "Unassigned"))
        self.command.set(action.get("command", "")); self.source.set(action.get("source", ""))
        self.destination.set(action.get("destination", "")); self.url.set(action.get("url", ""))
        if hasattr(self, "fields"): self._show_fields()

    def _text(self, control): return self.profile["labels"].get(control, CONTROL_LABELS[control])
    def _refresh_deck(self):
        for control, button in self.keys.items(): button.configure(text=self._text(control))
    def _activate(self, control):
        self.control.set(control); self._load_assignment(); self._run(control)
    def _run(self, control):
        action = self.profile["actions"].get(control)
        if not action:
            self.status.set(f"{CONTROL_LABELS[control]} has no action assigned."); return
        try:
            perform_action(action)
            self.status.set(f"Ran {self.profile['labels'].get(control, CONTROL_LABELS[control])}.")
        except Exception as exc:
            self.status.set(f"Action failed: {exc}"); messagebox.showerror("Action failed", str(exc))
    def _test(self):
        control = self.control.get(); self._apply(); self._run(control)
    def _save(self, silent=False):
        try:
            save_profile(self.profile)
            if not silent: self.status.set(f"Profile saved: {CONFIG_PATH}")
        except OSError as exc: messagebox.showerror("Could not save profile", str(exc))
    def _open_profile(self):
        path = filedialog.askopenfilename(title="Load profile",
            filetypes=[("JSON profile", "*.json"), ("All files", "*.*")])
        if path:
            self.profile = load_profile(path); self._refresh_deck(); self._load_assignment()
            self.status.set(f"Loaded profile {self.profile.get('name', 'Default')}.")
    def _refresh_devices(self):
        found = EvdevReader.devices()
        self.device_paths = {f"{name} — {path}": path for path, name in found}
        values = list(self.device_paths); self.device_combo.configure(values=values)
        active = next((label for label, path in self.device_paths.items()
                       if path == self.profile.get("input_device")), "")
        if active: self.device.set(active)
        elif values: self.device.set(values[0])
        else:
            self.device.set(""); self.status.set("No evdev input found. Install evdev and check permissions.")
    def _connect(self):
        path = self.device_paths.get(self.device.get(), "")
        if not path: self.status.set("Choose a detected device first."); return
        self.profile["input_device"] = path; self.reader.start(path); self._save(True)
        self.status.set(f"Listening to {self.device.get()}.")
    def _learn(self):
        if not self.profile.get("input_device"):
            self.status.set("Choose and connect the physical input first."); return
        self.learn_armed = True
        self.status.set(f"Learning {CONTROL_LABELS[self.control.get()]}: press or turn it now.")

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
                if kind == "error": self.status.set(value)
                elif kind == "show": self.show_window()
                elif kind == "release":
                    control = self.profile["bindings"].get(value)
                    if control not in CONTROLS: control = self._known_button(value)
                    if control in CONTROLS: self._light_control(control, held=False)
                elif self.learn_armed:
                    self.profile["bindings"][value] = self.control.get()
                    self.learn_armed = False; self._save(True)
                    self._light_control(self.control.get())
                    self.status.set(f"Bound {value} to {CONTROL_LABELS[self.control.get()]}.")
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
                        else:
                            self.status.set(f"Detected {value}, but it is unassigned. Select a control and click Learn selected.")
        except queue.Empty: pass
        self.root.after(60, self._poll)
    def close(self):
        self.reader.stop()
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
