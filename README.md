# Fishbot UI (React/TS, tkinter replacement)

Drop-in for your existing project structure (matches the DM Monitor reference
you shared: `context/themeContext.tsx`, `motion/react`, `lucide-react`,
Tailwind utility classes). Two themes carried over as-is: `minimal` (black)
and `cutesy` (pink/purple), toggled the same way as your DM Monitor app.

## Files

- `src/lib/fishbotBridge.ts` — the contract between this UI and the native
  side (window detection, screen capture, key injection, calibration). Field
  names in `FishbotConfig` match `fishbot_gui_cfg.json` 1:1 so you can
  serialize straight through. Includes a **mock bridge** so the UI runs
  standalone in a browser for preview before you wire a backend.
- `src/context/fishbotContext.tsx` — app state: config, live status stream,
  selected game window, start/stop, calibration triggers.
- `src/screens/WindowSetupScreen.tsx` — on mount, calls
  `bridge.findWindow("NTE")` automatically. If it resolves, shows a
  "Connected to ..." confirmation and a Continue button — no manual step
  needed. Only if that search comes back empty does it fall back to
  `bridge.listWindows()` and a manual pick list (this satisfies "auto-detect
  NTE first, only prompt manually if not found").
- `src/screens/DashboardScreen.tsx` — Start/Stop (F8), live state
  (`MINIGAME`/`IDLE`/`HOOKED`/`RESULT`/`NONE`), bar found flags, `err`/held
  key, loops/s, F-button ratios, and a small derived event log.
- `src/screens/SettingsScreen.tsx` — deadzone/lead/invert, F-button
  thresholds (`blue_min`/`grey_min`/`white_min`), min-gap/repeat, per-state
  action toggles, calibration buttons, debug preview toggle, admin/UIPI
  warning + relaunch button (per handoff §5.4/§7), reset to defaults.

## Wiring to the real backend

This UI never touches Win32/mss/pydirectinput directly. Whatever process
owns that (a `pywebview` host around the existing `fishbot_gui_v3.py` logic,
or a small Node/Electron/Tauri shim that shells out to it) needs to inject
`window.fishbot` implementing the `FishbotBridge` interface before this app
mounts. Suggested path of least resistance given the code you already have:

1. Keep the Python side (`frame_rect`, `find_blob`, `classify`, the worker
   loop) almost unchanged.
2. Run it inside `pywebview`, which lets you `expose()` Python functions to
   JS and `evaluate_js()` to push status updates — map those directly onto
   the `FishbotBridge` methods (`findWindow`, `listWindows`, `start`, `stop`,
   `calibrateBar`, `calibrateFButton`, `onStatus`).
3. Load this React app's built `index.html` as the pywebview window content
   instead of tkinter's `Tk()` root.

Until that's wired up, `npm run dev` on this app alone will run against the
mock bridge (`findWindow` "succeeds" after ~1s, status stream fakes a
MINIGAME → HOOKED → RESULT cycle) so you can review the UI/UX in isolation.

## Not yet ported from the handoff

- The debug preview window itself (`cv2.imshow`) is still native-side; the
  toggle here just needs to reach the backend.
- Admin relaunch (`relaunchAsAdmin`) needs a native implementation
  (`ShellExecuteW` with `"runas"`), same as v1's button.
- `calibrateBar`/`calibrateFButton` are expected to open the *native*
  `cv2.selectROI` + eyedropper flow (per §3 of the handoff) and resolve with
  the result — this UI doesn't re-implement the screenshot/ROI picker itself.
