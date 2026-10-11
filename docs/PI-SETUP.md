# Raspberry Pi setup

## Requirements

- Raspberry Pi OS or another Linux desktop with Python 3 and Tkinter.
- Optional evdev package for physical USB/HID input mapping.

If Tkinter is missing, install it with: sudo apt install python3-tk

Install the optional input reader with: sudo apt install python3-evdev

Start the app from the repository directory with: `python3 app.py`

## Open automatically when the controller is plugged in

1. Start the app once with `python3 app.py`.
2. The app installs its per-user desktop autostart entry automatically.
3. Open **Appearance / startup…** if you want to disable or restore that behavior.

After the next desktop login, a background instance waits for the tested controller USB ID `1189:8840`; when it appears, the app window opens and connects to its keyboard input endpoint. To disable it, clear **Start monitor at login; open deck when pad is plugged in** and click **Apply**. The app also detects and connects to the controller when launched normally.

## Connect the physical pad

1. Plug in the 12-button/2-knob controller.
2. Refresh the device list. It shows all evdev endpoints with event type tags (KEY, REL, ABS), USB IDs, and event numbers. The tested pad is marked **★ THIS PAD**.
3. Click Connect.
4. Select a logical control such as button_01 or knob_1_cw.
5. Click Learn selected, then press or turn that physical control.
6. Repeat for each control and assign an action.

Linux may restrict access to /dev/input/event*. Check permissions with ls -l /dev/input/event*. Do not run the whole GUI as root. If access is denied, use the distro's input group or a device-specific udev rule, then log out and back in. Device paths can change after reconnecting.

If you see **Device or resource busy**, an older app/monitor process still has the controller grabbed. Close that copy or stop its process once, update the app, and relaunch; the current version prevents duplicate app instances and raises the window already listening to the pad.

This controller exposes its 12 buttons as A–L keyboard events and knob input as number-key events. Use **Learn selected** once per knob direction to capture the exact event. Other controllers may expose relative events instead.

The two knob widgets now sit in the assignment panel, alongside the control/action menus. The wider panel gives the control and device dropdowns more room; each device label includes its USB ID and event node so similarly named endpoints are distinguishable.

The **LIVE INPUT / ACTION LOG · LAST 10** sits below Physical USB Input. It reports press/release events and relative/absolute input from the connected endpoint, plus learn/bind changes, assignments, action success/failure, and input errors. Click **Copy last 10** to copy the entries for troubleshooting. The app retains at most ten entries in memory; changing the selected endpoint and clicking Connect switches what the log monitors.

To make a physical control send a keyboard shortcut or gamepad/mouse output, choose **Send key/button combo** in Assign Control and fill up to four dropdown slots. The virtual outputs use Linux `/dev/uinput`; `python3-evdev` and write permission to `/dev/uinput` are required. The log reports permission or device errors if the virtual input device cannot be created.

When a button is touched, its matching on-screen key lights even before an action is assigned. An unknown/unbound input is also shown in the status line; choose the target control, click **Learn selected**, and press it again to bind it.

The **Appearance / startup…** window offers Midnight, Light, and Graphite themes; five accent choices; Compact, Standard, Large, and Maximized launch sizes. The main window can also be resized directly, and its last size is saved.

## Profile storage

The active profile is saved at ~/.config/12buttons2knobs/profile.json. Use Load profile to select an exported JSON profile. Save profile writes to the active user's config directory.
