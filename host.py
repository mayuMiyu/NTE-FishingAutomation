"""
Fishbot desktop host: opens the built React UI (fishbot-app/dist) in a
native pywebview window and exposes the detection/steering engine to it as
a JS-callable API (window.pywebview.api.*), matching src/lib/pywebviewBridge.ts
on the frontend side.

Run after building the UI:
    cd fishbot-app && npm run build && cd ..
    python host.py

Requires: pip install pywebview opencv-python mss numpy pydirectinput keyboard
Windows only (uses ctypes/user32 for window lookup, same as fishbot.py).
"""

import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np
import mss
import pydirectinput
import keyboard
import webview

try:
    import winsound
except ImportError:
    winsound = None

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

pydirectinput.PAUSE = 0

# When run as a plain script, "here" is this file's folder. When frozen by
# PyInstaller (--onefile), bundled data (--add-data) is unpacked at runtime
# into sys._MEIPASS instead, and CFG_FILE should live next to the actual
# .exe (sys.executable) so settings persist between runs, not inside the
# temp unpack folder that PyInstaller wipes.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    CFG_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
    CFG_DIR = BASE_DIR

CFG_FILE = CFG_DIR / "fishbot_gui_cfg.json"
DIST_INDEX = BASE_DIR / "fishbot-app" / "dist" / "index.html"

STATES = ("IDLE", "HOOKED", "RESULT")

DEFAULT_CONFIG = {
    "window_title": "",
    "bar": None, "fbtn": None,
    "fish": None, "rod": None,
    "steer": True, "invert_ad": False,
    "deadzone": 0.15, "lead": 0.08,
    "f_repeat": 0.0, "f_min_gap": 0.6, "f_debounce": 0.25,
    "blue_min": 0.02, "grey_min": 0.06, "white_min": 0.008,
    "act": {"IDLE": True, "HOOKED": True, "RESULT": True},
    "debug_preview": False,
}

# per-color HSV tolerance (hue, sat, val) - rod is tighter, pale yellow gets
# mimicked by sunset clouds. See FISHBOT_HANDOFF.md §3.
TOL = {"fish": (10, 70, 70), "rod": (8, 50, 60)}

# ---------------------------------------------------------------- win32 helpers (ported from fishbot.py)
user32 = ctypes.windll.user32
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def list_windows_raw():
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                found.append((buf.value, hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def find_hwnd(title):
    wins = list_windows_raw()
    for t, h in wins:
        if t == title:
            return h
    for t, h in wins:
        if title.lower() in t.lower():
            return h
    return None


_primary = {}


def frame_rect(title):
    """(left, top, width, height) of the game's client area, or None."""
    if not title:
        if not _primary:
            with mss.mss() as s:
                m = s.monitors[1]
            _primary.update(m)
        return _primary["left"], _primary["top"], _primary["width"], _primary["height"]
    hwnd = find_hwnd(title)
    if not hwnd or user32.IsIconic(hwnd):
        return None
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    if rc.right < 50 or rc.bottom < 50:
        return None
    return pt.x, pt.y, rc.right, rc.bottom


# ---------------------------------------------------------------- vision helpers (ported from fishbot.py)
def rel_to_abs(rel, fr):
    l, t, w, h = fr
    return {
        "left": int(l + rel["x"] * w), "top": int(t + rel["y"] * h),
        "width": max(1, int(rel["w"] * w)), "height": max(1, int(rel["h"] * h)),
    }


def grab(sct, region):
    return np.array(sct.grab(region))[:, :, :3]  # BGR


def hex_of(bgr):
    b, g, r = [int(x) for x in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"


def hsv_range(bgr, ht, st, vt):
    h, s, v = [int(x) for x in cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0]]
    return ([max(h - ht, 0), max(s - st, 0), max(v - vt, 0)],
            [min(h + ht, 179), min(s + st, 255), min(v + vt, 255)])


def find_blob(mask, min_w, min_h, max_w=None, close_w=1):
    if close_w > 1:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, close_w), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best = None
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if w < min_w or h < min_h or (max_w and w > max_w) or area < 0.5 * w * h:
            continue
        if best is None or area > best[2]:
            best = (x, x + w - 1, area)
    return (best[0], best[1]) if best else None


def classify(img, cfg):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    n = H.size
    blue = ((H >= 100) & (H <= 115) & (S >= 170) & (V >= 200)).sum() / n
    grey = ((S <= 45) & (V >= 140) & (V <= 235)).sum() / n
    white = ((S <= 60) & (V >= 235)).sum() / n
    if blue >= cfg["blue_min"]:
        st = "HOOKED"
    elif grey >= cfg["grey_min"]:
        st = "RESULT"
    elif white >= cfg["white_min"]:
        st = "IDLE"
    else:
        st = "NONE"
    return st, (blue, grey, white)


def snapshot(cfg):
    fr = frame_rect(cfg["window_title"])
    if not fr:
        raise RuntimeError("Game window not found / minimized.")
    l, t, w, h = fr
    with mss.mss() as sct:
        img = grab(sct, {"left": l, "top": t, "width": w, "height": h})
    if winsound:
        winsound.Beep(1000, 120)
    return img, fr


def select_roi(img, title):
    sc = min(1.0, 1500 / img.shape[1])
    view = cv2.resize(img, None, fx=sc, fy=sc) if sc < 1 else img
    x, y, w, h = cv2.selectROI(title, view, showCrosshair=False)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        return None
    return int(x / sc), int(y / sc), int(w / sc), int(h / sc)


def pick_colors(roi, items):
    """Zoomed eyedropper. items = [(key, label)]. Rejects sat<80 clicks
    (sky/grey) and re-prompts, per FISHBOT_HANDOFF.md §5.1's fix."""
    scale = max(1, 1200 // roi.shape[1])
    big = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    banner, out = 30, {}
    for key, label in items:
        while True:
            clicked = []

            def cb(ev, cx, cy, *_):
                if ev == cv2.EVENT_LBUTTONDOWN and cy >= banner:
                    clicked.append((cx // scale, (cy - banner) // scale))

            canvas = np.full((big.shape[0] + banner, big.shape[1], 3), 30, np.uint8)
            canvas[banner:, :] = big
            cv2.putText(canvas, f"Click the {label}", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.imshow("calibrate", canvas)
            cv2.setMouseCallback("calibrate", cb)
            while not clicked:
                if cv2.waitKey(30) == 27:
                    cv2.destroyAllWindows()
                    return None
            x, y = clicked[0]
            bgr = roi[min(y, roi.shape[0] - 1), min(x, roi.shape[1] - 1)]
            s = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0][1]
            if s < 80:
                continue  # rejected: too grey/sky, re-ask
            ht, st, vt = TOL[key]
            lo, hi = hsv_range(bgr, ht, st, vt)
            out[key] = {"hex": hex_of(bgr), "lo": lo, "hi": hi}
            break
    cv2.destroyAllWindows()
    return out


def retune(cfg):
    for key, tol in TOL.items():
        c = cfg.get(key)
        if c and c.get("hex"):
            hx = c["hex"]
            bgr = np.array([int(hx[5:7], 16), int(hx[3:5], 16), int(hx[1:3], 16)], np.uint8)
            c["lo"], c["hi"] = hsv_range(bgr, *tol)


# ---------------------------------------------------------------- config persistence
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CFG_FILE.exists():
        try:
            cfg.update(json.loads(CFG_FILE.read_text()))
        except Exception:
            pass
    retune(cfg)
    return cfg


def save_config(cfg):
    CFG_FILE.write_text(json.dumps(cfg, indent=2))


# ---------------------------------------------------------------- the exposed API
class Api:
    def __init__(self):
        self.cfg = load_config()
        self.armed = False
        self.stop_flag = threading.Event()
        self.window = None
        self.debug_open = False
        threading.Thread(target=self._bot_loop, daemon=True).start()
        keyboard.add_hotkey("f8", self._hotkey_toggle)
        keyboard.add_hotkey("f9", self._hotkey_quit)

    def set_window(self, w):
        self.window = w  # webview.Window, set after create_window()

    # ---- global hotkeys (F8 start/stop, F9 quit) - work even when the
    # game window has focus, unlike clicking the app's own Start button
    # (see FISHBOT_HANDOFF.md §5.4 on focus-stealing).
    def _hotkey_toggle(self):
        self.armed = not self.armed
        if not self.armed:
            pydirectinput.keyUp("a")
            pydirectinput.keyUp("d")

    def _hotkey_quit(self):
        self.stop()
        self.stop_flag.set()
        if self.window:
            self.window.destroy()

    # ---- window discovery
    def find_window(self, title_hint):
        for title, hwnd in list_windows_raw():
            if title_hint.lower() in title.lower():
                return {"title": title, "hwnd": hwnd}
        return None

    def list_windows(self):
        return [{"title": t, "hwnd": h} for t, h in list_windows_raw()]

    # ---- config
    def get_config(self):
        return self.cfg

    def set_config(self, patch):
        act = self.cfg.get("act", {})
        if "act" in patch:
            act = {**act, **patch["act"]}
        self.cfg.update(patch)
        self.cfg["act"] = act
        save_config(self.cfg)
        return self.cfg

    # ---- run control
    def start(self):
        self.armed = True

    def stop(self):
        self.armed = False
        pydirectinput.keyUp("a")
        pydirectinput.keyUp("d")

    def is_admin(self):
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def relaunch_as_admin(self):
        import sys
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

    # ---- calibration (opens native OpenCV windows, blocks the calling JS
    # promise until the user finishes clicking)
    def calibrate_bar(self):
        img, fr = snapshot(self.cfg)
        roi = select_roi(img, "Drag a TIGHT box around the grey track, then ENTER")
        if not roi:
            return None
        x, y, w, h = roi
        picks = pick_colors(img[y:y + h, x:x + w], [("fish", "TEAL fish bar"), ("rod", "YELLOW rod marker")])
        if not picks:
            return None
        bar = {"x": x / fr[2], "y": y / fr[3], "w": w / fr[2], "h": h / fr[3]}
        self.cfg["bar"], self.cfg["fish"], self.cfg["rod"] = bar, picks["fish"], picks["rod"]
        save_config(self.cfg)
        return {"bar": bar, "fish": picks["fish"], "rod": picks["rod"]}

    def calibrate_f_button(self):
        img, fr = snapshot(self.cfg)
        roi = select_roi(img, "Drag a box around the F button CIRCLE only, then ENTER")
        if not roi:
            return None
        x, y, w, h = roi
        fbtn = {"x": x / fr[2], "y": y / fr[3], "w": w / fr[2], "h": h / fr[3]}
        self.cfg["fbtn"] = fbtn
        save_config(self.cfg)
        return fbtn

    # ---- background worker: mirrors fishbot_gui_v3's bot_loop, pushes
    # status to JS instead of drawing tkinter widgets
    def _bot_loop(self):
        held = None
        fr, fr_t = None, 0
        pend, pend_since, conf = "NONE", 0, "NONE"
        fired, last_press = False, 0
        awaiting_bite = False

        with mss.mss() as sct:
            while not self.stop_flag.is_set():
                now = time.time()
                cfg = self.cfg
                armed = self.armed

                if fr is None or now - fr_t > 0.25:
                    fr, fr_t = frame_rect(cfg["window_title"]), now
                if not fr:
                    self._push_status({
                        "state": "NONE", "armed": armed, "barFound": {"fish": False, "rod": False},
                        "ratios": None, "err": None, "heldKey": None, "loopsPerSec": 0,
                        "message": "game window not found",
                    })
                    time.sleep(0.3)
                    continue

                steering, fs, rs = False, None, None
                if cfg["bar"] and cfg["fish"] and cfg["rod"]:
                    frame = grab(sct, rel_to_abs(cfg["bar"], fr))
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    fs = find_blob(cv2.inRange(hsv, np.array(cfg["fish"]["lo"]), np.array(cfg["fish"]["hi"])),
                                   12, max(4, int(0.2 * frame.shape[0])), None, 15)
                    rs = find_blob(cv2.inRange(hsv, np.array(cfg["rod"]["lo"]), np.array(cfg["rod"]["hi"])),
                                   2, max(4, int(0.4 * frame.shape[0])), int(0.08 * frame.shape[1]))
                    steering = bool(fs and rs)

                err = None
                want = None
                if steering and armed and cfg["steer"]:
                    rod_x = (rs[0] + rs[1]) / 2
                    err = rod_x - (fs[0] + fs[1]) / 2
                    if cfg.get("invert_ad"):
                        err = -err
                    dz = max(3, (fs[1] - fs[0]) * cfg["deadzone"])
                    if err > dz:
                        want = "a"
                    elif err < -dz:
                        want = "d"
                if want != held or not armed:
                    pydirectinput.keyUp("a")
                    pydirectinput.keyUp("d")
                    if want and armed:
                        pydirectinput.keyDown(want)
                    held = want if armed else None

                ratios = None
                if steering:
                    st = "MINIGAME"
                elif cfg["fbtn"]:
                    st, ratios = classify(grab(sct, rel_to_abs(cfg["fbtn"], fr)), cfg)
                    ratios = {"blue": ratios[0], "grey": ratios[1], "white": ratios[2]}
                else:
                    st = "NONE"

                if st != pend:
                    pend, pend_since = st, now
                if pend != conf and now - pend_since >= cfg["f_debounce"]:
                    conf, fired = pend, False
                if armed and conf in STATES and cfg["act"].get(conf) and now - last_press >= cfg["f_min_gap"]:
                    if not (conf == "IDLE" and awaiting_bite):
                        rep = cfg["f_repeat"]
                        if not fired or (rep > 0 and now - last_press >= rep):
                            pydirectinput.press("f")
                            fired, last_press = True, time.time()
                            awaiting_bite = conf == "IDLE" or (conf in ("HOOKED", "RESULT") and False)

                self._push_status({
                    "state": conf if conf != "NONE" else st,
                    "armed": armed,
                    "barFound": {"fish": bool(fs), "rod": bool(rs)},
                    "ratios": ratios,
                    "err": round(err) if err is not None else None,
                    "heldKey": held,
                    "loopsPerSec": 0,  # left as a future enhancement (see fishbot.py's live diagnostic line)
                    "message": "",
                })

                time.sleep(0.005 if armed else 0.05)

    def _push_status(self, status):
        if self.window:
            try:
                self.window.evaluate_js(f"window.__fishbotPushStatus && window.__fishbotPushStatus({json.dumps(status)})")
            except Exception:
                pass


def main():
    if not DIST_INDEX.exists():
        raise SystemExit(f"Build the UI first: cd fishbot-app && npm run build\n(missing {DIST_INDEX})")

    api = Api()
    window = webview.create_window("Fishbot", str(DIST_INDEX), width=440, height=640, js_api=api)
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
