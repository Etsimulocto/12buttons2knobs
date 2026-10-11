# Assignment ideas

Each of the 12 buttons and each knob's clockwise, counter-clockwise, and press events can have its own action.

## Copy a Skycam image

Choose a button, select Copy file, and enter the current image's source path and a destination file or folder. The app copies that file when the control is activated. If Skycam uses changing filenames, assign a small script or command that picks the newest image and copies it.

## Launch an app or script

Choose Run command and enter the executable plus arguments. Examples:

    vlc ~/Videos/demo.mp4
    python3 ~/scripts/my_action.py

Commands run as the desktop user without a shell. Pipes and redirection are not interpreted; put multi-step tasks in a script and launch the script.

## Open a web page

Choose Open URL and enter a complete http:// or https:// address.

## Knobs

Assign clockwise, counter-clockwise, and press separately. For example, use clockwise and counter-clockwise to launch scripts that raise and lower system volume.
