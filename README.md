# 12buttons2knobs

A Raspberry Pi control deck for the 12-button, 2-knob USB macro pad. The desktop app mirrors the hardware layout and lets each button, encoder direction, and encoder press trigger a configurable action.

## What it does

- Shows 12 keys in a 4 × 3 grid with two rotary controls beside them.
- Lets each key and each knob action receive a custom label and assignment.
- Supports launching a command or application, copying a file, or opening a web URL.
- Includes on-screen controls so assignments can be tested before the physical pad is connected.
- Reads Linux input events with evdev and has a learn mode to map physical controls to app controls.
- Offers Midnight, Light, and Graphite themes, five accent colors, resizable windows, and launch-size presets.
- Installs a per-user login monitor on first launch; it opens and connects the deck when the verified controller is plugged in.
- Stores the active profile in the current user's configuration folder.

A useful first mapping is a button that copies the latest Skycam image into a selected folder. Other buttons can launch tools, run scripts, or open project links. Knob turns and presses can each run their own action.

## Quick start on Raspberry Pi

Install Python's Tk interface and the optional Linux input reader:

    sudo apt update
    sudo apt install python3-tk python3-evdev

Run the app from the project folder:

    python3 app.py

The UI can be explored without the physical controller. To map hardware, plug in the pad, refresh the input-device list, select it, and click Connect. Select a logical control, click Learn selected, then press or turn the matching control on the pad.

Open **Appearance / startup…** to change the theme, accent, or launch size. The first app launch adds a desktop autostart entry for the current user; after login, the app waits in the background and opens when the pad is connected. Turn off **Start monitor at login** there to remove the entry. The pad is identified by USB vendor/product `1189:8840`.

See [Raspberry Pi setup](docs/PI-SETUP.md) for permissions and device troubleshooting, and [assignment ideas](docs/ASSIGNMENTS.md) for examples.

## Example: copy an image

Select a button, set its action to **Copy file**, and enter the source image path and destination. For example, the included profile template uses:

- Source: ~/Pictures/Skycam/latest.png
- Destination folder: ~/Pictures/Selected

Those are placeholders; replace them with the paths Skycam actually uses on the Pi. If Skycam names each image differently, a small script can find the newest image and copy it; assign that script as a command.

## Profiles

- Save profile writes to ~/.config/12buttons2knobs/profile.json.
- Load profile opens another JSON profile, including profiles/example.json.
- Profiles can be copied and shared as ordinary JSON files.

## Current status

The visual deck, assignment editor, profile save/load, action runner, evdev learn mode, appearance settings, window sizing, and optional plug-triggered launch monitor are implemented. On the tested Raspberry Pi controller, the 12 buttons send keyboard keys A–L; the knobs emit number keys including 1, 3, 4, and 6. Learn mode records these input events. The exact knob-direction mapping still needs to be learned on the device.

The profile supports 12 buttons plus six knob events: clockwise, counter-clockwise, and press for each knob. Actions run locally as the logged-in user. Command actions are split into arguments and do not use a shell; put multi-step commands in a script.

## Repository map

- app.py — Tkinter application and optional input-event reader.
- profiles/example.json — sample file-copy assignment.
- docs/PI-SETUP.md — Raspberry Pi install and input-device setup.
- docs/ASSIGNMENTS.md — action examples and behavior.
- tests/test_app.py — profile and action tests.

## Development checks

Run the standard-library tests with:

    python3 -m unittest discover -s tests -v

The GUI requires a desktop session. Hardware learning requires evdev and read access to /dev/input/event*.
