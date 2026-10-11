# Raspberry Pi setup

## Requirements

- Raspberry Pi OS or another Linux desktop with Python 3 and Tkinter.
- Optional evdev package for physical USB/HID input mapping.

If Tkinter is missing, install it with: sudo apt install python3-tk

Install the optional input reader with: sudo apt install python3-evdev

Start the app from the repository directory with: python3 app.py

## Connect the physical pad

1. Plug in the 12-button/2-knob controller.
2. Refresh the device list and choose its Linux input-event device.
3. Click Connect.
4. Select a logical control such as button_01 or knob_1_cw.
5. Click Learn selected, then press or turn that physical control.
6. Repeat for each control and assign an action.

Linux may restrict access to /dev/input/event*. Check permissions with ls -l /dev/input/event*. Do not run the whole GUI as root. If access is denied, use the distro's input group or a device-specific udev rule, then log out and back in. Device paths can change after reconnecting.

Some controllers expose knob turns as key presses; others use relative events. Learn mode records the event it receives. If the controls do not produce events, collect evtest output and add a controller-specific adapter.

## Profile storage

The active profile is saved at ~/.config/12buttons2knobs/profile.json. Use Load profile to select an exported JSON profile. Save profile writes to the active user's config directory.
