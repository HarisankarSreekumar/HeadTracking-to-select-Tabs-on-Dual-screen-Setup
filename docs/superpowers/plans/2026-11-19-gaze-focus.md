# Gaze Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows tray app that watches the user's head/eye direction through a webcam and focuses the top window on whichever of two monitors they turn to.

**Architecture:** A camera loop feeds MediaPipe face landmarks into pure functions (gaze angle → smoothing → monitor classification with hysteresis → dwell gate). A `Controller` turns a settled target monitor into a Win32 focus call. All decision logic is pure Python with injected dependencies so it is unit-tested on Linux; Win32/camera/tray code is thin and imported lazily.

**Tech Stack:** Python 3.10+, numpy, opencv-python, mediapipe, pywin32, pystray, Pillow, keyboard, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-gaze-focus-design.md`

## Global Constraints

- Windows 10/11 runtime; development and unit tests run on Linux — no module imported by tests may import `win32*`, `pystray`, `keyboard`, or `mediapipe` at module top level.
- Exactly two monitors supported; anything else → don't act, ask for recalibration.
- Default dwell 0.5 s, adjustable in config.
- Default hotkey `ctrl+alt+g` toggles pause.
- Config stored as JSON at `%APPDATA%\GazeFocus\config.json`.
- No face detected → never switch focus.
- Package name `gaze_focus`, source in `gaze_focus/`, tests in `tests/`.

## Review Focus

1. **Face lost** (user stands up, looks down at phone) → no switch; smoothing and dwell reset so the first frames back don't trigger a stale switch. Test: Task 6 `test_face_lost_resets_and_never_focuses`.
2. **Target monitor has no eligible windows** (empty desktop, only minimized windows) → nothing happens, no exception. Test: Task 4 `test_pick_window_none_when_monitor_empty`.
3. **Foreground window already on the target monitor** (user clicked something there themselves) → don't re-focus a different window. Test: Task 6 `test_no_focus_when_foreground_already_on_target`.
4. **Monitors changed since calibration** (one unplugged, IDs differ) → don't act; surface "recalibrate" status. Test: Task 6 `test_unknown_monitors_requires_recalibration`.
5. **Webcam unavailable/busy** (Teams holds it) → status message and retry every 5 s, no crash. Test: Task 6 `test_camera_open_failure_retries`.

---

### Task 1: Project scaffold + config

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `gaze_focus/__init__.py`, `gaze_focus/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `@dataclass Config: dwell_s: float = 0.5; hysteresis_deg: float = 3.0; smoothing_frames: int = 5; eye_weight: float = 0.5; hotkey: str = "ctrl+alt+g"; camera_index: int = 0; calibration: dict[str, float] = field(default_factory=dict)` (monitor id → calibrated gaze yaw in degrees)
  - `default_config_path() -> Path` (`%APPDATA%\GazeFocus\config.json`; falls back to `~/.gaze_focus/config.json` if APPDATA unset)
  - `load_config(path: Path) -> Config`, `save_config(cfg: Config, path: Path) -> None`

- [ ] **Step 1: Write failing tests** — `test_load_missing_returns_defaults` (`dwell_s == 0.5`, `hotkey == "ctrl+alt+g"`, `calibration == {}`); `test_roundtrip` (save cfg with `calibration={"\\\\.\\DISPLAY1": -20.0, "\\\\.\\DISPLAY2": 18.5}`, `dwell_s=0.8`, load equals original); `test_corrupt_file_returns_defaults` (file contains `"{not json"`); `test_unknown_keys_ignored` (extra key `"foo": 1` loads fine).
- [ ] **Step 2: Run** `pytest tests/test_config.py -v` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `config.py`; `save_config` creates parent dirs. `requirements.txt` lists runtime deps; pin `pywin32`, `keyboard`, `pystray` with `; sys_platform == "win32"` markers so `pip install -r requirements.txt` works on Linux. Dev dep: pytest.
- [ ] **Step 4: Run** `pytest tests/test_config.py -v` — Expected: 4 passed.
- [ ] **Step 5: Commit** `feat: project scaffold and config`

### Task 2: Smoothing, monitor classification, dwell gate

**Files:**
- Create: `gaze_focus/classifier.py`
- Test: `tests/test_classifier.py`

**Interfaces:**
- Produces:
  - `class Smoother(n: int)`: `update(x: float) -> float` (mean of last n), `reset() -> None`
  - `class MonitorClassifier(calibration: dict[str, float], hysteresis_deg: float)`: `classify(gaze_yaw: float) -> str | None`, `reset() -> None`. Raises `ValueError` if `len(calibration) != 2`.
  - `class DwellGate(dwell_s: float)`: `update(target: str | None, now: float) -> str | None`, `reset() -> None`

- [ ] **Step 1: Write failing tests**
  - `test_smoother_mean`: n=3, updates 0,3,6,9 → last returns 6.0; after `reset()`, `update(10)` → 10.0
  - `test_classify_basic`: cal `{"L": -20, "R": 20}`, hyst 3 → `classify(-15) == "L"`, `classify(15) == "R"`
  - `test_classify_hysteresis`: from state "L", `classify(2)` stays "L" (within midpoint+3), `classify(4)` → "R"; then `classify(-2)` stays "R", `classify(-4)` → "L"
  - `test_classify_first_reading_inside_band_uses_midpoint`: fresh classifier, `classify(1) == "R"`
  - `test_classify_requires_two_monitors`: `MonitorClassifier({"L": 0}, 3)` raises ValueError
  - `test_dwell_fires_once_after_dwell`: dwell 0.5: `update("R", 0.0)` None, `update("R", 0.4)` None, `update("R", 0.5) == "R"`, `update("R", 0.9)` None (already fired)
  - `test_dwell_glance_ignored`: `update("R",0)`, `update("R",0.3)`, `update("L",0.35)`, `update("R",0.6)` → all None
  - `test_dwell_none_resets`: `update("R",0)`, `update(None,0.3)`, `update("R",0.4)` None, `update("R",0.9) == "R"`
- [ ] **Step 2: Run** `pytest tests/test_classifier.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement.** Classifier: sort the two monitors by calibrated yaw; midpoint split; if current state is set, switch only when gaze crosses midpoint by more than `hysteresis_deg` toward the other side. DwellGate: track `(candidate, since, fired)`; fire when same candidate held `>= dwell_s` and not yet fired.
- [ ] **Step 4: Run** — Expected: 8 passed.
- [ ] **Step 5: Commit** `feat: gaze smoothing, monitor classifier, dwell gate`

### Task 3: Gaze angle from face landmarks

**Files:**
- Create: `gaze_focus/gaze.py`, `gaze_focus/tracker.py`
- Test: `tests/test_gaze.py`

**Interfaces:**
- Produces:
  - `MODEL_POINTS: np.ndarray` (6×3 generic face model: nose tip, chin, left/right eye outer corner, left/right mouth corner) and `LANDMARK_IDS = (1, 152, 263, 33, 291, 61)` (MediaPipe Face Mesh indices, same order)
  - `head_yaw_deg(image_points: np.ndarray, frame_w: int, frame_h: int) -> float` — 6×2 pixel points; `cv2.solvePnP` with focal = frame_w, centre principal point; positive = user turned to their right.
  - `iris_offset(eye_outer: np.ndarray, eye_inner: np.ndarray, iris: np.ndarray) -> float` — 2D points; position of iris along the corner-to-corner line, mapped to [-1, 1], 0 = centred, clamped.
  - `combined_gaze(head_yaw: float, eye_offset: float, eye_weight: float, eye_range_deg: float = 15.0) -> float` = `head_yaw + eye_weight * eye_offset * eye_range_deg`
  - `tracker.FaceTracker(camera_index: int)`: `open() -> bool`, `read_gaze(eye_weight: float) -> float | None` (None if no frame or no face), `close() -> None`. Imports mediapipe/cv2 inside `open()`. Uses Face Mesh with `refine_landmarks=True`, max 1 face; iris centres 468 (right) / 473 (left); averages both eyes' offsets. Not unit-tested (needs camera).

- [ ] **Step 1: Write failing tests**
  - `test_head_yaw_frontal_near_zero`: project `MODEL_POINTS` (translated 600 mm in front of camera, no rotation) with `cv2.projectPoints` at 1280×720 → `abs(head_yaw_deg(...)) < 2`
  - `test_head_yaw_recovers_rotation`: same with yaw of +25° and −25° → result within 3° of expected and correct sign
  - `test_iris_offset_centre_and_edges`: outer (0,0), inner (10,0): iris (5,0) → 0.0; (10,0) → 1.0; (0,0) → -1.0; (15,0) → 1.0 (clamped)
  - `test_combined_gaze`: `combined_gaze(10, 0.5, 0.5) == 13.75`
- [ ] **Step 2: Run** `pytest tests/test_gaze.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `gaze.py` (yaw from `cv2.RQDecomp3x3` of the Rodrigues matrix; fix sign so the test convention holds) and `tracker.py`.
- [ ] **Step 4: Run** — Expected: 4 passed.
- [ ] **Step 5: Commit** `feat: head yaw and iris offset gaze estimation`

### Task 4: Window selection + Win32 adapter

**Files:**
- Create: `gaze_focus/windows.py` (pure), `gaze_focus/win32_adapter.py` (Win32 only)
- Test: `tests/test_windows.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) WindowInfo: hwnd: int; title: str; monitor: str; visible: bool; minimized: bool; tool_window: bool; cloaked: bool`
  - `windows.pick_window(windows_zorder: list[WindowInfo], target_monitor: str) -> WindowInfo | None` — first eligible: visible, not minimized, not tool window, not cloaked, non-empty title, `monitor == target_monitor`.
  - `win32_adapter.list_monitors() -> list[str]` (device names like `\\.\DISPLAY1`, via `EnumDisplayMonitors` + `GetMonitorInfo`)
  - `win32_adapter.list_windows() -> list[WindowInfo]` (EnumWindows = top-to-bottom Z-order; `DwmGetWindowAttribute(DWMWA_CLOAKED)` via ctypes; `WS_EX_TOOLWINDOW`)
  - `win32_adapter.foreground_monitor() -> str | None`
  - `win32_adapter.focus_window(hwnd: int) -> bool` — tap Alt via `keybd_event` (VK_MENU down/up) to lift foreground lock, then `SetForegroundWindow`; if it returns false, retry once with `AttachThreadInput` to the current foreground thread. Return whether `GetForegroundWindow() == hwnd`.

- [ ] **Step 1: Write failing tests** (pure module only)
  - `test_pick_topmost_on_target`: Z-order [A on M1, B on M2, C on M2] → target M2 returns B
  - `test_pick_skips_ineligible`: on M2 in order: minimized, tool window, cloaked, empty title, invisible, then D → returns D
  - `test_pick_window_none_when_monitor_empty`: all windows on M1 → target M2 returns None
- [ ] **Step 2: Run** `pytest tests/test_windows.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `windows.py`, then `win32_adapter.py` (not importable on Linux; nothing in tests imports it).
- [ ] **Step 4: Run** — Expected: 3 passed.
- [ ] **Step 5: Commit** `feat: window selection and Win32 focus adapter`

### Task 5: Calibration

**Files:**
- Create: `gaze_focus/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Consumes: `FaceTracker.read_gaze` (Task 3), `list_monitors` (Task 4)
- Produces:
  - `class CalibrationError(Exception)`
  - `compute_calibration(samples: dict[str, list[float]], min_samples: int = 20, min_separation_deg: float = 8.0) -> dict[str, float]` — median per monitor; raises `CalibrationError` with a user-readable message if not exactly 2 monitors, any monitor has fewer than `min_samples`, or medians differ by less than `min_separation_deg`.
  - `run_calibration(read_gaze: Callable[[], float | None], monitors: list[str], prompt: Callable[[str], None], seconds: float = 3.0, clock=time.monotonic) -> dict[str, float]` — for each monitor: `prompt("Look at monitor N and press OK")`, then collect non-None readings for `seconds`; returns `compute_calibration(...)`.

- [ ] **Step 1: Write failing tests**
  - `test_compute_median`: `{"A": [-21,-20,-19]*10, "B": [18,19,20]*10}` → `{"A": -20, "B": 19}`
  - `test_too_few_samples`: one monitor with 5 samples → CalibrationError
  - `test_too_close`: medians -2 and 3 → CalibrationError
  - `test_run_calibration_with_fakes`: fake clock advancing 0.1 s per read, fake read_gaze returning -20 for first monitor's window then 20, prompt records calls → result ≈ `{"M1": -20, "M2": 20}` and prompt called twice
- [ ] **Step 2: Run** `pytest tests/test_calibration.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: 4 passed.
- [ ] **Step 5: Commit** `feat: monitor calibration`

### Task 6: Controller + app (camera loop, tray, hotkey)

**Files:**
- Create: `gaze_focus/controller.py` (pure), `gaze_focus/app.py`, `gaze_focus/__main__.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: Config (1), Smoother/MonitorClassifier/DwellGate (2), FaceTracker (3), pick_window + win32_adapter (4), run_calibration (5)
- Produces:
  - `class Controller(cfg: Config, current_monitors: Callable[[], list[str]], list_windows: Callable[[], list[WindowInfo]], foreground_monitor: Callable[[], str | None], focus_window: Callable[[int], bool])`
    - `status: str` — one of `"running"`, `"paused"`, `"needs_calibration"`, `"no_camera"`
    - `paused: bool`, `toggle_pause() -> None` (also resets smoother/dwell)
    - `on_gaze(gaze: float | None, now: float) -> int | None` — returns hwnd focused, else None. Flow: paused → None; calibration keys ≠ set of current monitors → status `needs_calibration`, None; gaze None → reset smoother + dwell, None; smooth → classify → dwell; on fire: if `foreground_monitor() == target` → None; else `pick_window` → `focus_window`.
    - `recalibrated(calibration: dict[str, float]) -> None` — rebuilds classifier, status `running`.
  - `class CameraLoop(open_tracker: Callable[[], FaceTracker | None], controller: Controller, clock, sleep, retry_s: float = 5.0)`: `step() -> None` (one iteration; if no tracker, try opening; on failure set `controller.status = "no_camera"` and wait `retry_s` before the next attempt).
  - `app.main() -> None`: load config; if no valid calibration, run calibration first (prompts via `ctypes.windll.user32.MessageBoxW`); start CameraLoop in a thread (~20 fps, `time.sleep` to cap); pystray icon whose tooltip shows `status`, menu: Pause/Resume, Recalibrate, Quit; `keyboard.add_hotkey(cfg.hotkey, controller.toggle_pause)`. Run with `python -m gaze_focus`.

- [ ] **Step 1: Write failing tests** (fakes for all callables; cfg calibration `{"M1": -20, "M2": 20}`, dwell 0.5, smoothing 1)
  - `test_switches_after_dwell`: foreground on M1, windows [W1 on M1, W2 on M2]; `on_gaze(20, 0.0)` None, `on_gaze(20, 0.6)` == W2.hwnd; focus fake called once
  - `test_face_lost_resets_and_never_focuses`: `on_gaze(20,0)`, `on_gaze(None,0.3)`, `on_gaze(20,0.6)` → None; focus never called
  - `test_no_focus_when_foreground_already_on_target`: foreground on M2; gaze 20 for 0.6 s → None, focus not called
  - `test_paused_does_nothing`: `toggle_pause()`; gaze 20 for 1 s → None, `status == "paused"`
  - `test_unknown_monitors_requires_recalibration`: current_monitors returns `["M1", "M3"]` → `on_gaze(20, 1.0)` None, `status == "needs_calibration"`, focus not called
  - `test_camera_open_failure_retries`: open_tracker returns None; fake clock; `step()` at t=0 → status `"no_camera"`, 1 open attempt; `step()` at t=2 → still 1 attempt; `step()` at t=5.1 → 2 attempts
- [ ] **Step 2: Run** `pytest tests/test_controller.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `controller.py`, then `app.py` and `__main__.py`.
- [ ] **Step 4: Run** `pytest -v` — Expected: all tests in repo pass (29).
- [ ] **Step 5: Commit** `feat: controller, camera loop, tray app`

### Task 7: README + Windows verification checklist

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**: install (`py -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`), run (`.venv\Scripts\python -m gaze_focus`), calibration steps, hotkey, config keys and defaults, troubleshooting (camera busy, focus not switching → try running as same privilege level as target app; elevated windows can't be focused from a non-elevated app).
- [ ] **Step 2: Add "First run on Windows" checklist** for the user to report back: (a) calibration completes; (b) turning to other monitor focuses its window within ~1 s; (c) quick glance does not switch; (d) typing goes to the newly focused window without clicking; (e) Ctrl+Alt+G pauses/resumes; (f) CPU usage in Task Manager.
- [ ] **Step 3: Run** `pytest -v` — Expected: all pass.
- [ ] **Step 4: Commit** `docs: README and Windows verification checklist`
