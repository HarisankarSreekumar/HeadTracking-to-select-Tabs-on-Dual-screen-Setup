# Gaze Focus — Design

## Intent
Two-monitor Windows setup. Switching attention to the other screen today needs a click
before you can work there. Gaze Focus watches the user's head/eye direction via a
Logitech 720p webcam and automatically focuses the window on whichever monitor they turn to.

## Goals
- Detect which of two monitors the user is facing (head pose primary, eye direction secondary).
- When they settle on the other monitor, focus the top-most (last-used) window on that monitor.
- Ignore quick glances: switch only after a dwell time (default ~0.5 s, adjustable).
- One-time calibration: look at each monitor a few seconds; saved to a config file.
- Tray icon with pause/resume, recalibrate, quit; global hotkey to pause/resume.
- Light on CPU (target a few % at 15–30 fps).

## Non-goals
- Selecting a specific tab or a specific window among several on the same monitor.
- More than two monitors (design shouldn't block it, but not built now).
- macOS / Linux.

## Anti-goals (failure even if it "works")
- Stealing focus mid-typing because of a glance.
- Flapping back and forth when looking near the boundary between screens.
- Noticeably slowing the computer.

## Approaches considered
1. **Python tray app — MediaPipe Face Mesh + Win32 APIs (CHOSEN).** Fastest to build and tune;
   needs Python (or a ~100 MB packaged .exe later).
2. C#/.NET native app with an ONNX face model. Smaller exe, slightly lower CPU, much more
   work and slower to tune.
3. Dedicated eye-tracker hardware (Tobii). Ruled out: user wants to use the existing webcam,
   and head direction is enough to pick between two screens.

## Design
- **Capture:** OpenCV reads the webcam (640x480 or 720p, ~20 fps).
- **Tracking:** MediaPipe Face Mesh (with iris landmarks) → head yaw/pitch via solvePnP on a
  few stable landmarks, plus horizontal iris offset. Combined "gaze yaw" = head yaw + weighted eye offset.
- **Classification:** calibration records gaze yaw for each monitor; the split point is the
  midpoint. Hysteresis band around the split prevents flapping. Smoothed with a short moving average.
- **Dwell:** a monitor must be the classified target continuously for the dwell time before acting.
  No face detected → do nothing.
- **Focus:** if the foreground window is already on the target monitor, do nothing. Otherwise walk
  windows in Z-order (EnumWindows), take the first visible, non-minimized, non-tool, titled window
  whose MonitorFromWindow is the target, and bring it forward via SetForegroundWindow using the
  standard workaround for Windows' focus-stealing prevention (synthetic Alt key / AttachThreadInput).
- **Monitor mapping:** EnumDisplayMonitors gives monitor rectangles; calibration associates
  "left/right" gaze with the actual monitor handles.
- **UI:** pystray tray icon; `keyboard` (or RegisterHotKey) global hotkey, default Ctrl+Alt+G.
- **Config:** JSON in %APPDATA%\GazeFocus (calibration, dwell, hysteresis, hotkey, camera index).

## Constraints
- Windows 10/11, Python 3.10+, one webcam (720p Logitech).
- Development happens in a Linux container: pure logic (smoothing, classification, dwell,
  window selection over fake window lists) is unit-tested there; webcam and Win32 parts must be
  verified on the user's Windows PC.

## Left to the builder
- Exact landmark set for head pose, smoothing window size, eye-offset weight, default hysteresis.
- Optional debug window showing camera feed + current gaze/target (useful for tuning).
- Packaging to .exe (PyInstaller) — later, if wanted.
