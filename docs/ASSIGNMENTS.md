# Assignment ideas

Each of the 12 buttons and each knob's clockwise, counter-clockwise, and press events can have its own action.

## Copy a Skycam image

Choose a button, select Copy file, and enter the current image's source path and a destination file or folder. The app copies that file when the control is activated. If Skycam uses changing filenames, assign a small script or command that picks the newest image and copies it.

## Launch an app or script

Choose Run command and enter the executable plus arguments. Examples:

    vlc ~/Videos/demo.mp4
    python3 ~/scripts/my_action.py

Commands run as the desktop user without a shell. Pipes and redirection are not interpreted; put multi-step tasks in a script and launch the script.

## Send a keyboard, mouse, or gamepad combo

Choose **Send key/button combo** to make one physical pad control tap up to four outputs at the same time. The four dropdown slots include keyboard modifiers and keys, mouse buttons and wheel directions, gamepad buttons, DPAD directions, stick directions, and triggers. For example, set slot 1 to **CTRL** and slot 2 to **J** for Ctrl+J, or choose **DPAD UP**. Leave unused slots at **— None —**.

This sends a short press/release through Linux `/dev/uinput`. It requires `python3-evdev` and permission to create virtual input devices. If the app reports a uinput permission error, check that `/dev/uinput` exists and that the logged-in user can write to it; do not run the whole GUI as root.

## Open a web page

Choose Open URL and enter a complete http:// or https:// address.

## Knobs

Assign clockwise, counter-clockwise, and press separately. For example, use clockwise and counter-clockwise to launch scripts that raise and lower system volume.
