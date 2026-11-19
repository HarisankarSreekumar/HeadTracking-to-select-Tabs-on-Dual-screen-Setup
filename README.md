# Gaze Focus

Turn your head toward your other monitor and the window you last used there gets focus, so you can type straight away without clicking. Gaze Focus uses an ordinary webcam and runs in the Windows system tray.

## Requirements

- Windows 10 or 11 with two monitors
- A webcam pointed at your face (tested setup: Logitech 720p)
- Python 3.10 or newer ([python.org](https://www.python.org/downloads/); tick "Add python.exe to PATH")
- Internet access on first run, to download the 3.7 MB face model

## Install

Open PowerShell in this folder:

```bash
py -m venv .venv
```

```bash
.venv\Scripts\pip install -r requirements.txt
```

## Run

```bash
.venv\Scripts\python -m gaze_focus
```

Add `--debug` to print the measured gaze angle and status twice a second, which helps with tuning:

```bash
.venv\Scripts\python -m gaze_focus --debug
```

## Calibration

On first run, and whenever your monitors change, Gaze Focus asks you to look at each monitor in turn. For each one:

1. Sit as you normally do and turn toward the monitor named in the message.
2. Press **OK** and keep looking at that monitor for 3 seconds.

Turn your head, not just your eyes. To run calibration again (for example after moving the webcam or your chair), right-click the tray icon and choose **Recalibrate**.

## Using it

- **Tray icon:** green means running, grey paused, orange "monitors changed, recalibrate", red "webcam unavailable" (it retries every 5 seconds).
- **Ctrl+Alt+G** pauses and resumes it. Left-clicking the tray icon does the same.
- A quick glance at the other monitor doesn't switch focus. You have to look there for about half a second.
- If you click a window on the monitor yourself, Gaze Focus leaves your choice alone.

## Settings

Settings are stored in `%APPDATA%\GazeFocus\config.json`. Quit Gaze Focus before editing the file.

| Key | Default | Meaning |
|---|---|---|
| `dwell_s` | `0.5` | Seconds you must look at a monitor before it gets focus |
| `hysteresis_deg` | `3.0` | Extra degrees past the midpoint needed to switch; raise it if focus flips back and forth |
| `smoothing_frames` | `5` | Frames averaged to steady the reading |
| `eye_weight` | `0.5` | How much eye direction counts compared with head direction (`0` = head only) |
| `hotkey` | `ctrl+alt+g` | Pause/resume hotkey |
| `camera_index` | `0` | Which webcam to use, if you have more than one |
| `calibration` | — | Written by calibration; delete it to force recalibration |

## Troubleshooting

- **Red icon, "webcam unavailable":** another app (Teams, Zoom, Camera) is using the webcam, or `camera_index` is wrong. Close the other app; Gaze Focus reconnects within 5 seconds.
- **Some windows never get focus:** Windows blocks a normal program from focusing a window running as administrator (Task Manager, admin terminals). Run Gaze Focus as administrator too if you need those windows.
- **Focus switches when you didn't mean it to:** raise `dwell_s` (try `0.8`) or `hysteresis_deg` (try `5`).
- **Calibration says the monitors look the same:** turn your head further toward each monitor, or move the webcam to sit between the two screens.

## First run on Windows: checklist

Please try each of these and report back what happened:

- [ ] a. Calibration completes and says "Calibration saved".
- [ ] b. Turning to the other monitor focuses its window within about 1 second.
- [ ] c. A quick glance (under half a second) does **not** switch focus.
- [ ] d. After a switch, typing goes into the newly focused window without clicking.
- [ ] e. Ctrl+Alt+G pauses (grey icon) and resumes (green icon).
- [ ] f. Gaze Focus's CPU use in Task Manager (look for `python.exe`).

## Development

Unit tests cover the decision logic and run on any OS:

```bash
pip install numpy opencv-python pytest
```

```bash
python -m pytest
```
