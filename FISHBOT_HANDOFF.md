# Fishbot: Project Handoff

Context document for any agent (or human) picking this project up. It covers what the program is, what works, what broke and why, and what is still open. Statements are marked **[verified]** (the user confirmed it or it was tested against real screenshots) or **[unverified]** (written and compile-checked only).

> **Environment caveat:** all code was written in a Linux sandbox. It was only `py_compile`-checked and unit-tested offline against user screenshots. The GUIs and key injection have **never been executed by the author**. Everything Windows/in-game is only as verified as the user's own reports.

---

## 1. What the program is

A screen-reading bot that plays the **fishing minigame in the game "NTE"** (Windows PC, user is in the Philippines, Python-capable). It does not use YOLO or any ML model.

### The minigame UI (top of screen)
- A long horizontal **grey/dark track** (the "fishing bar").
- A **teal/green pill** on the track = the **fish bar** (moves around on its own).
- A thin **yellow/pale-yellow vertical marker** = the **rod bar** (the player controls it).
- Goal: keep the yellow rod marker **inside the teal fish bar** at all times.
- Controls: **`A` moves the rod left, `D` moves it right** (hold to move; the marker has some inertia).
- Left icon shows "Fish Stamina", right icon shows "Fishing Line" (not used by the bot).

### The "F button" (bottom-right HUD, outside the minigame)
A circular button with a hook icon and an "F" key badge. It has three visual states:

| State | Look | Meaning / intended action |
|---|---|---|
| `IDLE` (before fishing) | white hook on dark-teal bg, faint ring | press F to cast |
| `HOOKED` (fish on hook) | **bright blue ring** (~`#1E78F5`) around the hook | press F to hook |
| `RESULT` (after successful catch) | **light grey filled disc** (~`#BDBDBD`), dark hook | press F to continue/collect |

While the minigame bar is on screen the F button is not the focus; the bot steers instead.

### Core approach: color masks, not YOLO
The user's first idea was YOLO plus a color picker. The decision was to **skip YOLO**: the bars are flat solid colors on a fixed UI, so HSV thresholding (OpenCV) is faster, needs no training data, and is more accurate. The "color picker" idea was kept as a **calibration eyedropper**.

Per frame:
1. Grab the small bar region with `mss`.
2. Convert to HSV; mask the fish-bar color and the rod color.
3. Find the fish bar's left/right edges and the rod's center x.
4. If rod is right of fish center → hold `A`; if left → hold `D`; inside a deadzone → release.
5. (v3 only) When no minigame is detected, classify the F button's state and tap `F`.

Keys are sent with `pydirectinput` (scan-code `SendInput`).

---

## 2. Files (all in `/mnt/user-data/outputs/`)

| File | What it is | Config file | Status |
|---|---|---|---|
| `fishbot.py` | Original **CLI**: `calibrate` / `run [--debug]`, F8 start/pause, F9 quit. Absolute screen coordinates. | `fishbot_cfg.json` | **[verified] user said it was "completely working"** for steering. Still uses the old `span()` detector (no shape validation). |
| `fishbot_gui_v1.py` | **GUI only** (tkinter). Same logic as the CLI, fixed screen coords. Most heavily iterated file. | `fishbot_cfg.json` (same as CLI, absolute path next to script) | Steering **not confirmed working** in-game (see §4). |
| `fishbot_gui_v2.py` | v1 + **window-relative regions** (game-window dropdown; bar stored as fractions of the client area, follows moves/resizes). | `fishbot_v2_cfg.json` | **[unverified]** never reported on by the user. |
| `fishbot_gui_v3.py` | v2 + **F-button 3-state triggers** (detect state, press F per state). Full-featured target version. | `fishbot_gui_cfg.json` | **[unverified]** never reported on by the user. |
| `fishbot_gui.py` | **Stale duplicate** of v3 from before later fixes. **Delete it.** | `fishbot_gui_cfg.json` | Do not use. |

Dependencies: `pip install opencv-python mss numpy pydirectinput keyboard` (+ stdlib `tkinter`, `ctypes`, `winsound`). Windows only.

Hotkeys (all GUIs): **F8** start/stop, **F9** quit.

---

## 3. How each piece works (reference)

### Calibration
- Screenshot (after a 3 s delay so the user can switch to the game; a beep confirms the capture).
- User drags a **tight box around the grey track** (`cv2.selectROI`).
- Zoomed **eyedropper** window: click the **teal fish bar**, then the **yellow rod marker**. Clicks with saturation < 80 are rejected (guards against clicking sky/grey).
- Stores hex + HSV `lo`/`hi` per color.
- The grey track color itself is **not detected**. The ROI is chosen manually; the track is only a visual anchor.

### HSV tolerances
- `fish`: hue ±10, sat ±70, val ±70.
- `rod`: hue ±8, sat ±50, val ±60 (tighter, because the rod is a **pale** yellow that sunset clouds can mimic). Ranges are **re-derived from the saved hex at load time** (`retune()`), so old configs get the new tolerances without recalibrating.

### Detection (`find_blob`), v1/v2/v3 only
Replaced the naive "leftmost/rightmost matching column" `span()` (see §5, false positives). Now uses connected components with shape rules:
- **Fish**: solid blob, width ≥ 12 px, height ≥ 20 % of ROI height; horizontal morphological close (15 px) to bridge the gap the rod marker leaves in the teal bar.
- **Rod**: solid blob, width 2 px to 8 % of ROI width, height ≥ 40 % of ROI height.
- Solidity rule: blob area ≥ 50 % of its bounding box.
- Tested offline on the user's screenshots: finds fish `(324,469)` and rod `(364,367)` in a real minigame frame; finds nothing in an empty-sky frame.

### Steering logic (v1 has the most complete version)
- `err = rod_x + vel * lead − fish_center` where `vel` is a smoothed rod velocity (px/s) and `lead` (default 0.08 s) predicts overshoot so the key is released early.
- Deadzone = fraction of the fish-bar width (default 0.15, **recommended 0.10 to 0.25**, spinner capped at 0.4).
- `Invert A/D` checkbox exists in case direction is reversed.
- Key held only while needed; released on direction change / stop.

### Window-relative regions (v2/v3)
- Uses `ctypes` (`EnumWindows`, `GetClientRect`, `ClientToScreen`) to get the game window's client rect ~4×/s.
- Bar/F-button regions saved as **fractions** of that rect, so moving/resizing the window is followed. "(full screen)" option = primary monitor.
- Process is set DPI-aware so coordinates match `mss`.

### F-button state machine (v3)
- `classify()` on the F-button crop, ratios of pixels:
  - `blue` = H 100–115, S ≥ 170, V ≥ 200 → `HOOKED` if ≥ `blue_min` (0.02)
  - `grey` = S ≤ 45, V 140–235 → `RESULT` if ≥ `grey_min` (0.06)
  - `white` = S ≤ 60, V ≥ 235 → `IDLE` if ≥ `white_min` (0.008)
  - else `NONE`
- If the rod+fish blobs are both found → state `MINIGAME` (steering; no F presses).
- A state must be stable **0.25 s** before it counts; F is tapped once per state entry (hold 50 ms); global 0.6 s minimum between F presses; optional "repeat every N s" (0 = once per entry). Per-state checkboxes choose which states press F.
- Tested offline only on **three small crops** (one per state) the user supplied; all classified correctly. Real ROI ratios are unverified.

### Threading / GUI
- Worker thread runs capture + control; tkinter main thread polls a status dict every 100 ms. Hotkey callbacks only set flags in a set (`self.req`) consumed by the main thread.
- Optional **Debug preview** (cv2 window, 2× scale) drawn from the worker thread: blue box on the fish bar, red line on the rod.

---

## 4. What was accomplished

1. **Approach chosen and validated**: color/HSV detection instead of YOLO.
2. **CLI bot working [verified]**: user confirmed steering worked ("completely working now") after calibration and debug-window fixes.
3. **Calibration tool** with eyedropper, banner prompts, and bad-click rejection.
4. **GUI wrapper** (v1) with start/stop, hotkeys, live readout, debug preview.
5. **Window-relative regions** (v2) so moving the game window doesn't break calibration.
6. **F-button 3-state trigger** (v3), with colors extracted from the user's three real button screenshots.
7. **Shape-validated detection** fixing a real false positive (see §5.6).
8. Quality-of-life in v1: 3 s Start countdown, debug window auto-parked away from the capture area, closing the debug window auto-unticks its checkbox, admin detection + "Relaunch as admin" button, live diagnostic line (`err`, held key, loops/s), 1 ms Windows timer request.

---

## 5. Where it failed / what went wrong

Chronological, with root cause and fix status.

1. **Wrong colors saved in config.** First calibration stored the **sky color (`#CBE4F6`) as "fish"** and the **teal bar as "rod"**; yellow was never picked. Cause: the selection box was 35 px tall so the first click landed on background, and the prompt was easy to misread. **Fixed**: on-screen banner saying what to click, saturation check rejects grey/sky clicks and re-asks.
2. **Debug window showed a dark, empty strip.** Cause: the debug window opened on top of the capture region (the bot filmed itself), plus possible multi-monitor origin offset. **Fixed**: window is parked on the opposite half of the screen; calibration adds the monitor's `left/top` offset.
3. **Absolute coordinates.** Any window shift broke the bot. **Fixed in v2/v3** (fractions of client rect).
4. **v1 GUI: steering did nothing.** Multiple suspected causes, addressed in order:
   - Clicking the GUI **Start** button steals focus, so A/D went to the GUI → added **3 s countdown** (F8 still arms instantly).
   - Debug window covering the capture area (self-capture) → parked away.
   - **Overshoot** from marker inertia → added **lead** prediction.
   - User had set **deadzone to 0.49**, so the bot only corrected near the bar's edge → recommended 0.15, capped spinner at 0.4.
   - Loop only ~**72 Hz** (Windows sleep granularity ~15 ms) → `timeBeginPeriod(1)`.
   - **Suspected UIPI/admin**: if the game runs elevated and Python doesn't, Windows silently drops injected keys. Added an admin warning + relaunch button. **This is the leading hypothesis but was not confirmed.**
   - **Status: unresolved as of the last message.** The user's last report was that the yellow marker "doesn't flinch" even with the game focused; a screenshot then showed the bot *deciding* correctly (`err +154px`, `key a`) while the user said the marker didn't respond, which points at **key delivery**, not logic.
5. **Misleading `err` reading.** The live line showing `key a` is the bot's *intent*, not proof the game received it.
6. **False "rod found" on clouds.** With the minigame inactive, sunset cream clouds matched the pale-yellow rod range; `span()` took min/max matching columns (0–297) so one stray pixel stretched the span. **Fixed** via tighter rod tolerance + connected-component shape checks (ported to v1/v2/v3). Verified on the user's screenshots; not yet re-run in-game.
7. **Ambiguity in user reports.** "Problem after our v3" was accompanied by a screenshot of the **v1** window. The actual v3 behavior has never been reported.

---

## 6. What still needs to be done

### Blocking / high priority
- [ ] **Confirm key delivery in the game.** Run as admin (or match the game's elevation), Start via F8 with the game focused, and check whether the marker moves when the line says `key a`/`key d`. If not, try alternatives: `SendInput` directly via `ctypes` with scancodes, `pyautogui`, a hardware-level approach, or check for game-side input blocking (anti-cheat).
- [ ] **Verify v1 end-to-end in the real minigame** after the shape-detection fix: `fish found / rod found` only during the minigame, sensible `err`, key toggling, `loops/s` ≥ 100 with debug off.
- [ ] **Tune** `lead` (default 0.08) and `deadzone` (default 0.15) against real fish behavior. The controller was only sanity-checked with a toy simulation, which was inconclusive.

### Port improvements to v2 and v3 (currently missing)
v2/v3 only received the blob-detection/tolerance patch. They **lack** everything below that v1 has:
- [ ] `lead` prediction and `Invert A/D`
- [ ] Start button 3 s countdown (focus problem will recur there)
- [ ] Debug window parking (they can still film themselves) and close-detect → auto-untick
- [ ] `timeBeginPeriod(1)`
- [ ] Admin detection / relaunch, absolute config path
- [ ] The diagnostic status line (`err`, key, loops/s)
- [ ] The key-release cleanup (only release when a key is actually held)

### F-button work (v3) still to verify
- [ ] Calibrate the F-button ROI on the real game and watch the live `blue / grey / white` ratios in each state; tune the three thresholds.
- [ ] **Unknown game flow**: what F does in each state, what the button looks like right after casting (could still look like `IDLE` and cause repeat presses), and whether the button is hidden during the minigame. The current design presses once per state entry to avoid spamming; adjust once the real flow is known.
- [ ] Watch for false `IDLE`/`RESULT` from bright backgrounds behind the button (clouds, water) if the ROI is loose.

### Cleanup / nice to have
- [ ] Delete stale `fishbot_gui.py`; optionally back-port shape detection into `fishbot.py`.
- [ ] Merge v1–v3 into a single maintained file once v3 has all v1 fixes (the three-file split was for staged testing).
- [ ] Add a "test detection" button that snapshots the ROI and reports found/not-found without needing the live loop.
- [ ] Optional PD/proportional pulse control if hold-until-centered still oscillates.
- [ ] Multi-monitor support beyond monitor 1 (calibration and fallback frame use `sct.monitors[1]` only).

---

## 7. Gotchas for the next agent

- **Don't cover the capture area.** The bot reads real screen pixels; the GUI or any window over the bar/F-button gets read instead of the game.
- **Exclusive fullscreen may capture black** with `mss`; use borderless/windowed.
- **Focus matters**: injected keys go to whatever window is in the foreground. Clicking the GUI's Start button moves focus away from the game.
- **UIPI/elevation**: a non-admin process cannot inject input into an elevated process. Symptoms: detection fine, intent correct, game ignores keys.
- **Config is per-version.** v1 shares `fishbot_cfg.json` with the CLI (absolute pixels); v2 and v3 use different files with relative fractions. They are not interchangeable.
- **`retune()` overwrites saved `lo/hi`** from the saved hex on every load, so hand-editing HSV ranges in the JSON has no effect. Change `TOL` in code instead (or edit the hex).
- **Sunset/lighting changes** can shift the sky colors around the bar; the pale rod color is the weakest link. If false positives return, tighten `TOL["rod"]` or add a check that the rod blob sits on the dark track.
- **Terms of service / anti-cheat**: automating input may violate the game's ToS or trigger anti-cheat. The user was warned once; use at their own risk.

## 8. Key reference values

| Item | Value |
|---|---|
| Fish bar (teal) picks seen | `#29C6AB`, `#2ED1B1` |
| Rod marker (pale yellow) picks seen | `#FEF7A4`, `#FEF9AA` |
| F-button HOOKED ring | ~`#1E78F5` (HSV ≈ 108, 224, 245) |
| F-button RESULT disc | ~`#BDBDBD` (HSV ≈ 0, 0, 189) |
| F-button IDLE background | dark teal ~`#014455` (RESULT bg dark navy ~`#063556`) |
| Typical bar ROI seen | ~605–611 × 35–37 px |
| Default thresholds | `blue_min 0.02`, `grey_min 0.06`, `white_min 0.008`, deadzone 0.15, lead 0.08 s, F debounce 0.25 s, F min gap 0.6 s |
