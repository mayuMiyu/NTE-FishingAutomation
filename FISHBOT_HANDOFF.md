# Fishbot: Project Handoff

Context document for any agent (or human) picking this project up. It covers what the program is, what works, what broke and why, and what is still open. Statements are marked **[verified]** (the user confirmed it or it was tested against real screenshots) or **[unverified]** (written and compile-checked only).

> **Environment caveat:** all code was written in a Linux sandbox. Vision/steering logic was `py_compile`-checked and unit-tested offline against user screenshots; the new UI/packaging layer (§9) was reasoned through from symptoms the user reported, not run by the author. Everything Windows/in-game/exe-specific is only as verified as the user's own reports.

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
5. When no minigame is detected, classify the F button's state and tap `F`.

Keys are sent with `pydirectinput` (scan-code `SendInput`).

---

## 2. Files

**Current (this session's rewrite — see §9 for full detail):**

| File | What it is | Status |
|---|---|---|
| `host.py` | pywebview desktop host. Owns the vision/steering engine (ported from `fishbot_gui_v3.py`, logic unchanged) and exposes it to the UI via a JS-callable `Api` class. Replaces all tkinter GUIs. | **[unverified]** — never run against real gameplay. |
| `fishbot-app/` | React + TypeScript UI (Vite project). Two themes (`minimal` black, `cutesy` pink). Talks to `host.py` through `window.pywebview.api`. | **[unverified]** UI logic; loads and navigates correctly per user screenshots, but full click-through with a live game window not yet confirmed. |
| `fishbot_gui_cfg.json` | Config file, same schema/location as `fishbot_gui_v3.py` used. Shared by `host.py`. | Carries forward from v3. |

**Legacy (superseded by the above, kept for reference / salvage):**

| File | What it is | Config file | Status |
|---|---|---|---|
| `fishbot.py` | Original **CLI**: `calibrate` / `run [--debug]`, F8 start/pause, F9 quit. Absolute screen coordinates. | `fishbot_cfg.json` | **[verified] user said it was "completely working"** for steering. Uses the old `span()` detector (no shape validation). |
| `fishbot_gui_v1.py` | tkinter GUI, fixed screen coords. Most heavily iterated legacy file — v1's fixes (lead prediction, countdown, debug parking, `timeBeginPeriod`, admin relaunch, diagnostic line) are the ones ported into `host.py`. | `fishbot_cfg.json` | Superseded. |
| `fishbot_gui_v2.py` | v1 + window-relative regions. | `fishbot_v2_cfg.json` | Superseded. |
| `fishbot_gui_v3.py` | v2 + F-button 3-state triggers. This is the version `host.py`'s engine is ported from. | `fishbot_gui_cfg.json` | Superseded as a *UI*; its engine logic lives on in `host.py`. |
| `fishbot_gui.py` | Stale duplicate of v3. **Delete it.** | `fishbot_gui_cfg.json` | Do not use. |

Dependencies now: `pip install opencv-python mss numpy pydirectinput keyboard pywebview pyinstaller` (+ stdlib `tkinter` no longer needed for the new host; `ctypes`, `winsound`, `winreg`, `subprocess`, `tempfile`, `urllib` are stdlib). Windows only. Node/npm needed to build `fishbot-app`.

Hotkeys (`host.py`): **F8** start/stop, **F9** quit — registered globally via the `keyboard` library, so they work even while the game window has focus (unlike clicking the UI's own Start button).

---

## 3. How each piece works (reference — engine internals, unchanged by the UI rewrite)

### Calibration
- Screenshot (after a 3 s delay so the user can switch to the game; a beep confirms the capture).
- User drags a **tight box around the grey track** (`cv2.selectROI`).
- Zoomed **eyedropper** window: click the **teal fish bar**, then the **yellow rod marker**. Clicks with saturation < 80 are rejected (guards against clicking sky/grey).
- Stores hex + HSV `lo`/`hi` per color.
- The grey track color itself is **not detected**. The ROI is chosen manually; the track is only a visual anchor.
- In `host.py` this is triggered from the UI's Settings screen (`calibrate_bar` / `calibrate_f_button` API calls) but still opens **native OpenCV windows** on top of everything — that part was not redesigned into the web UI.

### HSV tolerances
- `fish`: hue ±10, sat ±70, val ±70.
- `rod`: hue ±8, sat ±50, val ±60 (tighter, because the rod is a **pale** yellow that sunset clouds can mimic). Ranges are **re-derived from the saved hex at load time** (`retune()`), so old configs get the new tolerances without recalibrating.

### Detection (`find_blob`)
Uses connected components with shape rules:
- **Fish**: solid blob, width ≥ 12 px, height ≥ 20 % of ROI height; horizontal morphological close (15 px) to bridge the gap the rod marker leaves in the teal bar.
- **Rod**: solid blob, width 2 px to 8 % of ROI width, height ≥ 40 % of ROI height.
- Solidity rule: blob area ≥ 50 % of its bounding box.
- Tested offline on the user's screenshots: finds fish `(324,469)` and rod `(364,367)` in a real minigame frame; finds nothing in an empty-sky frame.

### Steering logic
- `err = rod_x − fish_center`, sign optionally flipped by `invert_ad`.
- Deadzone = fraction of the fish-bar width (default 0.15, recommended 0.10–0.25).
- Key held only while needed; released on direction change / stop / disarm.
- **Not yet ported into `host.py`: velocity-smoothed `lead` overshoot prediction.** The `lead` config field exists and is exposed in the UI, but `_bot_loop` in `host.py` does not currently read it — steering is still plain proportional deadzone control. Flagged as an open item in §6.

### Window-relative regions
- Uses `ctypes` (`EnumWindows`, `GetClientRect`, `ClientToScreen`) to get the game window's client rect ~4×/s.
- Bar/F-button regions saved as **fractions** of that rect. Empty title = primary monitor fallback.
- Process is set DPI-aware so coordinates match `mss`.

### F-button state machine
- `classify()` on the F-button crop, ratios of pixels:
  - `blue` = H 100–115, S ≥ 170, V ≥ 200 → `HOOKED` if ≥ `blue_min` (0.02)
  - `grey` = S ≤ 45, V 140–235 → `RESULT` if ≥ `grey_min` (0.06)
  - `white` = S ≤ 60, V ≥ 235 → `IDLE` if ≥ `white_min` (0.008)
  - else `NONE`
- If the rod+fish blobs are both found → state `MINIGAME` (steering; no F presses).
- A state must be stable **0.25 s** before it counts; F is tapped once per state entry; global 0.6 s minimum between F presses; optional "repeat every N s". Per-state checkboxes (exposed in the new Settings screen) choose which states press F.
- Tested offline only on three small crops (one per state); real ROI ratios still unverified in-game.

### Threading / status reporting (new in `host.py`)
- `_bot_loop` runs on a background thread, same responsibilities as v3's worker thread.
- Instead of tkinter widgets, status is pushed to the web UI via `window.evaluate_js(...)` calling a JS-side callback (`window.__fishbotPushStatus`) roughly every loop iteration.
- **`loops/s` is currently always reported as `0`** — the counter itself was not ported over. Cosmetic only; doesn't affect bot behavior. Flagged in §6.
- The **debug preview** (cv2 window showing the capture with overlays) exists as a config toggle (`debug_preview`) surfaced in the UI, but is **not wired to anything in `host.py`** yet — toggling it currently does nothing.

---

## 4. What was accomplished

1. **Approach chosen and validated**: color/HSV detection instead of YOLO.
2. **CLI bot working [verified]**: user confirmed steering worked ("completely working now") after calibration and debug-window fixes.
3. **Calibration tool** with eyedropper, banner prompts, and bad-click rejection.
4. **tkinter GUI generations v1–v3**: start/stop, hotkeys, live readout, debug preview, window-relative regions, F-button 3-state trigger.
5. **Shape-validated detection**, fixing a real false positive (see §5.6).
6. **Full UI rewrite to React/TypeScript** (this session): two-theme (`minimal`/`cutesy`) desktop-style UI (setup/dashboard/settings screens), matching a separate reference project's visual language.
7. **Automatic game-window detection**: the setup screen searches for "NTE" on load and only falls back to a manual window picker if that search fails, per explicit requirement.
8. **pywebview desktop host** (`host.py`): exposes the ported v3 engine to the React UI as a typed JS API; config schema kept snake_case to match the existing JSON on disk.
9. **Global F8/F9 hotkeys** restored in the new host (via the `keyboard` library), so start/stop and quit work regardless of window focus.
10. **PyInstaller packaging** to a standalone `.exe` (`--onefile --windowed`), with path handling that works both as a raw script and frozen.
11. **WebView2 dependency handled defensively**: rather than bundling a ~200MB Chromium via a Qt backend, `host.py` checks the registry for WebView2 at startup and, if missing, asks the user's permission before running Microsoft's small official installer — see §9.

---

## 5. Where it failed / what went wrong

Chronological, with root cause and fix status. Items 1–7 are from the original tkinter-era work; items 8+ are from this session's UI/packaging rewrite.

1. **Wrong colors saved in config.** First calibration stored the sky color as "fish" and the teal bar as "rod". **Fixed**: on-screen banner + saturation-check rejection, re-asks on bad click.
2. **Debug window showed a dark, empty strip** (bot filming itself). **Fixed**: window parked on the opposite half of the screen.
3. **Absolute coordinates broke on window move.** **Fixed in v2/v3** (fractions of client rect), carried into `host.py`.
4. **v1 GUI: steering did nothing in-game.** Multiple suspected causes were addressed (focus-stealing Start button → 3 s countdown; debug window self-capture → parked; overshoot → `lead`; deadzone misconfigured → capped/recommended; loop rate → `timeBeginPeriod(1)`; **suspected UIPI/elevation mismatch**, added admin warning + relaunch). **Status: never conclusively resolved** — last v1 report showed the bot deciding correctly (`err +154px`, `key a`) while the marker didn't move, pointing at key delivery rather than logic. This is still open against `host.py` too (see §6).
5. **Misleading `err` reading** — it's the bot's intent, not proof the game received the key.
6. **False "rod found" on clouds**, from a naive min/max-column detector. **Fixed** via tighter rod tolerance + connected-component shape checks.
7. **Ambiguity in user reports**: a "v3 problem" report once turned out to be a screenshot of v1.
8. **Duplicate title bar.** Once `host.py` opened the UI in a real OS window, the React app's own decorative title bar (copied from a reference project meant for in-browser preview, with non-functional minimize/square/close icons) rendered *underneath* the real OS title bar, producing a visibly doubled chrome. **Fixed**: window created with `frameless=True` / `easy_drag=True`; the React title bar's icons now call real `minimize_window` / `toggle_maximize_window` / `close_window` API methods instead of being decorative.
9. **App froze ("Not Responding") on any click** shortly after first pywebview integration. Root cause narrowed to pywebview falling back to the legacy MSHTML/IE rendering engine when Microsoft Edge WebView2 isn't present or detected correctly — known to be fragile with frequent JS calls. **Mitigation, not a confirmed fix**: `ensure_webview2()` now checks for WebView2 at startup and offers to install it; the freeze was not re-tested end-to-end after this change.
10. **"Invalid hook call" / duplicate React copies** during dev setup — traced to a stray root-level `package.json`/`node_modules` created by an accidental `npm install` run one directory above the actual Vite project (`fishbot-app`). Fixed by deleting the outer copies; this is a dev-environment gotcha, not a code bug, but worth flagging since it's easy to reintroduce by running npm commands from the wrong folder.
11. **Dependencies silently dropped after a `node_modules` wipe** — `react-router`, `motion`, and `lucide-react` were installed in a separate step from the initial Vite scaffold and weren't captured consistently; a `node_modules`/lockfile wipe-and-reinstall lost them until reinstalled explicitly. Not a code issue, but confirm `fishbot-app/package.json` lists all four (`react-router`, `motion`, `lucide-react`, and the Tailwind Vite plugin) as real dependencies before handing this off, so a clean `npm install` alone is sufficient next time.

---

## 6. What still needs to be done

### Blocking / high priority — carried over, still unresolved
- [ ] **Confirm key delivery in the game** with `host.py`. Start via F8 (or the UI button) with the game focused, and check whether the marker actually moves. This is the single most important unresolved question in the whole project and predates this session's rewrite.
- [ ] **Verify the new UI + `host.py` end-to-end against real gameplay** — window auto-detect, calibration flow (does the native OpenCV window pop correctly on top of the frameless pywebview window?), steering, F-button presses, and the F8/F9 hotkeys, all with NTE actually running.
- [ ] **Tune `lead` and `deadzone`** against real fish behavior — only ever sanity-checked with a toy simulation.

### New from this session
- [ ] **Port `lead` overshoot prediction into `host.py`'s `_bot_loop`** — the config field and UI slider exist but aren't read by the steering code yet (see §3).
- [ ] **Wire up `loops/s`** in the status push (currently hardcoded to `0`).
- [ ] **Wire up the `debug_preview` toggle** to actually open/close a cv2 debug window from `host.py` (currently a no-op).
- [ ] **Re-verify the "Not Responding" freeze is actually gone** now that `frameless=True` + `ensure_webview2()` are in place — this was diagnosed, not confirmed fixed.
- [ ] **First-run UX of the PyInstaller exe**: onefile builds unpack to a temp dir on every launch (slow first open), and an unsigned exe that injects keystrokes will likely get flagged by antivirus/SmartScreen the first time a new user runs it. Neither is a bug, but worth documenting for end users, or addressing later with code signing if this gets distributed more widely.
- [ ] **Confirm `fishbot-app/package.json` pins its dependencies correctly** (see §5.11) so a fresh `npm install` on a clean checkout reproduces the working environment.

### F-button work still to verify
- [ ] Calibrate the F-button ROI on the real game and watch live `blue/grey/white` ratios per state; tune thresholds.
- [ ] Unknown game flow: what F does in each state, what the button looks like right after casting, whether it's hidden during the minigame.
- [ ] Watch for false `IDLE`/`RESULT` from bright backgrounds behind the button if the ROI is loose.

### Cleanup / nice to have
- [ ] Delete stale `fishbot_gui.py`.
- [ ] Once `host.py` is confirmed working end-to-end, the legacy `fishbot_gui_v1/v2/v3.py` tkinter files can likely be archived/removed — their logic now lives in `host.py`.
- [ ] Add a "test detection" action (surfaced as a button in Settings) that snapshots the ROI and reports found/not-found without needing the live loop.
- [ ] Optional PD/proportional pulse control if hold-until-centered still oscillates.
- [ ] Multi-monitor support beyond monitor 1.
- [ ] Consider code-signing the exe if it's going to be distributed to people beyond the original user, to reduce SmartScreen friction.

---

## 7. Gotchas for the next agent

- **Don't cover the capture area.** The bot reads real screen pixels; any window over the bar/F-button gets read instead of the game. This now includes the Fishbot app's own window if the user drags it on top of the capture region.
- **Exclusive fullscreen may capture black** with `mss`; use borderless/windowed.
- **Focus matters**: injected keys go to whatever window is in the foreground. This is why F8/F9 are global hotkeys in `host.py` rather than relying on clicking the app's own Start button.
- **UIPI/elevation**: a non-admin process cannot inject input into an elevated process. Symptoms: detection fine, intent correct, game ignores keys. `host.py` carries forward the admin-detection + relaunch-as-admin feature from v1.
- **Config is per-generation.** The legacy CLI/v1 share `fishbot_cfg.json` (absolute pixels); v2/v3/`host.py` share `fishbot_gui_cfg.json` (relative fractions). Not interchangeable.
- **`retune()` overwrites saved `lo/hi`** from the saved hex on every load — hand-editing HSV ranges in the JSON has no effect. Change `TOL` in code instead (or the hex).
- **Sunset/lighting changes** can shift sky colors around the bar; the pale rod color is the weakest link.
- **Terms of service / anti-cheat**: automating input may violate the game's ToS or trigger anti-cheat. The user was warned once; use at their own risk.
- **New (UI/packaging):** when doing any npm work, always confirm you're `cd`'d into `fishbot-app` first — a `package.json`/`node_modules` created one level up (in the project root) will shadow the real project's dependencies and cause duplicate-React "Invalid hook call" errors (see §5.10). Similarly, run PyInstaller from the project root (where `host.py` lives), not from inside `fishbot-app`.
- **New:** `host.py`'s `DIST_INDEX` / `CFG_FILE` path resolution branches on `sys.frozen` — if you add new bundled data files, remember they land in `sys._MEIPASS` (temp, wiped between runs) when frozen, not next to the exe. Anything that needs to persist (like the config JSON) must be written next to `sys.executable` instead.

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

---

## 9. UI Rewrite & Desktop Packaging (this session)

### Architecture
```
NTEfishingautomation/
├── host.py                  # pywebview host + ported engine (replaces all tkinter GUIs)
├── fishbot_gui_cfg.json      # shared config, same schema as v3
├── fishbot.py, fishbot_gui_v1/v2/v3.py, fishbot_gui.py   # legacy, see §2
└── fishbot-app/               # React + TypeScript UI (Vite project)
    ├── dist/                   # built output host.py loads (npm run build)
    └── src/
        ├── App.tsx                       # routes: /setup, /dashboard, /settings
        ├── DesktopLayout.tsx             # window chrome; wired to real window controls
        ├── main.tsx                      # installs the pywebview bridge, then renders
        ├── context/
        │   ├── themeContext.tsx          # minimal/cutesy theme toggle
        │   └── fishbotContext.tsx        # app state, wraps the bridge
        ├── lib/
        │   ├── fishbotBridge.ts          # types (mirror fishbot_gui_cfg.json) + mock bridge
        │   └── pywebviewBridge.ts        # wires window.fishbot to window.pywebview.api
        └── screens/
            ├── WindowSetupScreen.tsx     # auto-searches "NTE", manual picker only on failure
            ├── DashboardScreen.tsx       # start/stop, live state, diagnostics
            └── SettingsScreen.tsx        # steering/F-button tuning, calibration, admin relaunch
```

The UI never touches Win32/mss/pydirectinput directly — it only calls `window.fishbot.*`, which either talks to real Python (`pywebviewBridge.ts` → `host.py`'s `Api` class) or, if no pywebview host is present (e.g. plain `npm run dev` in a browser), falls back to a mock implementation in `fishbotBridge.ts` for UI-only preview.

### WebView2 handling
`host.py` checks the registry for the WebView2 runtime at startup (`ensure_webview2()`). If missing, it shows a native message box explaining the app cannot run without it and asks permission to install; on "Yes" it downloads Microsoft's small official Evergreen Bootstrapper and runs the real installer UI (not silent, so the user sees what's being installed). This was chosen over bundling a Qt/QtWebEngine backend (~150–250MB per copy) since most Windows 10 machines updated since ~Nov 2021, and all Windows 11 machines, already have WebView2 — only very outdated or LTSC installs would hit this path.

### Procedure: run in development
```
cd fishbot-app
npm install
npm run dev          # browser preview against the mock bridge — no Python needed
```

### Procedure: run the real desktop app (unpackaged)
```
cd fishbot-app
npm run build         # produces fishbot-app/dist/
cd ..
pip install opencv-python mss numpy pydirectinput keyboard pywebview
python host.py
```

### Procedure: build a standalone .exe
```
cd fishbot-app
npm run build
cd ..
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name FishGrabber --add-data "fishbot-app/dist;fishbot-app/dist" host.py
```
Output: `dist/FishGrabber.exe` (a new `dist/` at the project root — distinct from `fishbot-app/dist/`). This is the file to hand to another user; it needs no separate Python or Node install on their machine, only (per above) WebView2, which it will offer to install itself if missing.
