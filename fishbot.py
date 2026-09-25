import ctypes, json, os, threading, time
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
import mss
import pydirectinput
import keyboard

try:
    import winsound
except ImportError:
    winsound = None

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

pydirectinput.PAUSE = 0
CFG_FILE = "fishbot_gui_cfg.json"
OLD_CFG = "fishbot_cfg.json"          # old CLI config, only used to reuse the bar colors
H_TOL, S_TOL, V_TOL = 10, 70, 70
STATES = ("IDLE", "HOOKED", "RESULT")
STATE_LABELS = {"IDLE": "before fishing (hook icon)",
                "HOOKED": "fish on hook (blue ring)",
                "RESULT": "after catch (grey disc)"}

DEFAULTS = {
    "window_title": "",              # "" = primary monitor
    "bar": None, "fbtn": None,       # [x, y, w, h] as fractions of the game frame
    "fish": None, "rod": None,       # {"hex", "lo", "hi"}
    "steer": True, "deadzone": 0.15,
    "f_repeat": 0.0,                 # 0 = press F once each time a state is entered
    "blue_min": 0.02, "grey_min": 0.06, "white_min": 0.025,
    "act": {"IDLE": True, "HOOKED": True, "RESULT": True},
}

# ---------------------------------------------------------------- win32 helpers
user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
if user32:
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM) if user32 else None
    HWND_TOPMOST = -1
    SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE = 0x0010, 0x0002, 0x0001
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]

def pin_on_top_no_focus(title):
    """Make a window always-on-top without stealing focus from it."""
    h = find_hwnd(title)
    if h:
        user32.SetWindowPos(h, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                             SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE)

def list_windows():
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
    wins = list_windows()
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


# ---------------------------------------------------------------- vision helpers
def rel_to_abs(rel, fr):
    l, t, w, h = fr
    x, y, rw, rh = rel
    return {"left": int(l + x * w), "top": int(t + y * h),
            "width": max(1, int(rw * w)), "height": max(1, int(rh * h))}


def grab(sct, region):
    return np.array(sct.grab(region))[:, :, :3]  # BGR


def hex_of(bgr):
    b, g, r = [int(x) for x in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"


# per-color tolerance (hue, sat, val). The rod is a pale yellow that sunset clouds can mimic, so it's tighter.
TOL = {"fish": (10, 70, 70), "rod": (8, 50, 60)}


def hsv_range(bgr, ht=H_TOL, st=S_TOL, vt=V_TOL):
    h, s, v = [int(x) for x in cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0]]
    return ([max(h - ht, 0), max(s - st, 0), max(v - vt, 0)],
            [min(h + ht, 179), min(s + st, 255), min(v + vt, 255)])


def find_blob(mask, min_w, min_h, max_w=None, close_w=1):
    """Biggest solid blob that has the right SHAPE -> (left, right) column, or None.
    Stops stray same-colored pixels (clouds, water) from counting as the bar/marker."""
    if close_w > 1:     # bridge the gap the rod marker leaves in the teal bar
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


def retune(cfg):
    """Re-derive the HSV ranges from the saved hex so old configs get the new tolerances too."""
    for key, tol in TOL.items():
        c = cfg.get(key)
        if c and c.get("hex"):
            hx = c["hex"]
            bgr = np.array([int(hx[5:7], 16), int(hx[3:5], 16), int(hx[1:3], 16)], np.uint8)
            c["lo"], c["hi"] = hsv_range(bgr, *tol)


def span(mask):
    cols = np.where(mask.any(axis=0))[0]
    return (cols[0], cols[-1]) if len(cols) >= 2 else None


def classify(img, cfg):
    """Look at the F-button crop and decide which of the 3 states it's in."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    n = H.size
    blue = ((H >= 100) & (H <= 115) & (S >= 170) & (V >= 200)).sum() / n    # ring  ~#1E78F5
    grey = ((S <= 45) & (V >= 140) & (V <= 235)).sum() / n                  # disc  ~#BDBDBD
    white = ((S <= 60) & (V >= 235)).sum() / n                              # hook icon
    if blue >= cfg["blue_min"]:
        st = "HOOKED"
    elif grey >= cfg["grey_min"]:
        st = "RESULT"
    elif white >= cfg["white_min"]:
        st = "IDLE"
    else:
        st = "NONE"
    return st, (blue, grey, white)


def pick_colors(roi, items):
    """Zoomed eyedropper. items = [(key, label)]. Returns {key: {hex, lo, hi}} or None."""
    scale = max(1, 1200 // roi.shape[1])
    big = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    banner, out = 30, {}
    for key, label in items:
        while True:
            clicked = []
            def cb(ev, cx, cy, *_):
                if ev == cv2.EVENT_LBUTTONDOWN and cy >= banner:
                    clicked.append((cx // scale, (cy - banner) // scale))
            shown = cv2.copyMakeBorder(big, banner, 0, 0, 0, cv2.BORDER_CONSTANT, value=(40, 40, 40))
            cv2.putText(shown, f"CLICK THE {label.upper()}  (ESC = cancel)", (5, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.imshow("click color", shown)
            cv2.setMouseCallback("click color", cb)
            while not clicked:
                if cv2.waitKey(20) == 27:
                    cv2.destroyAllWindows()
                    return None
            px, py = clicked[0]
            bgr = roi[min(py, roi.shape[0] - 1), min(px, roi.shape[1] - 1)]
            sat = int(cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0][1])
            if sat < 80:
                continue  # sky/grey - ask again
            lo, hi = hsv_range(bgr, *TOL[key])
            out[key] = {"hex": hex_of(bgr), "lo": lo, "hi": hi}
            break
    cv2.destroyAllWindows()
    return out


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE) as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k == "act":
                cfg["act"].update(v)
            else:
                cfg[k] = v
    elif os.path.exists(OLD_CFG):       # reuse old colors so you don't re-click them
        with open(OLD_CFG) as f:
            old = json.load(f)
        cfg["fish"], cfg["rod"] = old.get("fish"), old.get("rod")
    retune(cfg)
    return cfg


def tap(key, hold=1):
    pydirectinput.keyDown(key)
    time.sleep(hold)
    pydirectinput.keyUp(key)


# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        self.cfg = load_cfg()
        self.armed = False
        self.debug = False
        self.req = set()
        self.status = {"state": "NONE", "ratios": None, "bar": "-", "msg": ""}
        self.stop = threading.Event()

        self.root = tk.Tk()
        self.root.title("Fishing bot")
        self.build_ui()
        keyboard.add_hotkey("f8", lambda: self.req.add("toggle"))
        keyboard.add_hotkey("f9", lambda: self.req.add("quit"))
        self.worker = threading.Thread(target=self.bot_loop, daemon=True)
        self.worker.start()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.poll()

    # ---------- UI
    def bind(self, key, var, cast=float, sub=None):
        def upd(*_):
            try:
                v = cast(var.get())
            except (tk.TclError, ValueError):
                return
            if sub:
                self.cfg[key][sub] = v
            else:
                self.cfg[key] = v
        var.trace_add("write", upd)

    def build_ui(self):
        r, pad = self.root, {"padx": 8, "pady": 4}

        # game window
        f = ttk.LabelFrame(r, text="Game window")
        f.grid(row=0, column=0, sticky="ew", **pad)
        self.win_var = tk.StringVar(value=self.cfg["window_title"] or "(full screen)")
        self.win_box = ttk.Combobox(f, textvariable=self.win_var, state="readonly", width=44)
        self.win_box.grid(row=0, column=0, padx=6, pady=6)
        self.win_box.bind("<<ComboboxSelected>>", self.on_window)
        ttk.Button(f, text="Refresh", command=self.refresh_windows).grid(row=0, column=1, padx=6)
        self.refresh_windows()

        # calibration
        f = ttk.LabelFrame(r, text="Calibration (3 sec delay so you can switch to the game)")
        f.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Button(f, text="Calibrate bar + colors",
                   command=lambda: self.delayed(self.cal_bar)).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(f, text="Calibrate F button",
                   command=lambda: self.delayed(self.cal_fbtn)).grid(row=0, column=1, padx=6, pady=6)
        self.cal_lbl = ttk.Label(f, text="")
        self.cal_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        self.update_cal_label()

        # triggers
        f = ttk.LabelFrame(r, text="Press F when the button shows...")
        f.grid(row=2, column=0, sticky="ew", **pad)
        for i, st in enumerate(STATES):
            v = tk.BooleanVar(value=self.cfg["act"][st])
            self.bind("act", v, bool, st)
            ttk.Checkbutton(f, text=STATE_LABELS[st], variable=v).grid(row=i, column=0, sticky="w", padx=6)
        ttk.Label(f, text="Repeat every (s), 0 = once per state:").grid(row=3, column=0, sticky="w", padx=6)
        v = tk.DoubleVar(value=self.cfg["f_repeat"])
        self.bind("f_repeat", v)
        ttk.Spinbox(f, from_=0, to=30, increment=0.5, textvariable=v, width=6).grid(row=3, column=1, padx=6, pady=4)

        # steering
        f = ttk.LabelFrame(r, text="Minigame steering (A / D)")
        f.grid(row=3, column=0, sticky="ew", **pad)
        v = tk.BooleanVar(value=self.cfg["steer"])
        self.bind("steer", v, bool)
        ttk.Checkbutton(f, text="Steer with A/D", variable=v).grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(f, text="Deadzone (fraction of fish bar):").grid(row=1, column=0, sticky="w", padx=6)
        v = tk.DoubleVar(value=self.cfg["deadzone"])
        self.bind("deadzone", v)
        ttk.Spinbox(f, from_=0.02, to=0.6, increment=0.02, textvariable=v, width=6).grid(row=1, column=1, padx=6, pady=4)

        # tuning
        f = ttk.LabelFrame(r, text="F-button detection thresholds (see live readout below)")
        f.grid(row=4, column=0, sticky="ew", **pad)
        for i, (k, lbl) in enumerate((("blue_min", "blue ring"), ("grey_min", "grey disc"), ("white_min", "white hook"))):
            ttk.Label(f, text=lbl).grid(row=0, column=i * 2, padx=(6, 2))
            v = tk.DoubleVar(value=self.cfg[k])
            self.bind(k, v)
            ttk.Spinbox(f, from_=0.001, to=0.5, increment=0.005, textvariable=v, width=6).grid(row=0, column=i * 2 + 1, padx=(0, 6), pady=6)

        # live status
        f = ttk.LabelFrame(r, text="Live")
        f.grid(row=5, column=0, sticky="ew", **pad)
        self.st_lbl = ttk.Label(f, text="state: -", font=("Segoe UI", 11, "bold"))
        self.st_lbl.grid(row=0, column=0, sticky="w", padx=6)
        self.ratio_lbl = ttk.Label(f, text="")
        self.ratio_lbl.grid(row=1, column=0, sticky="w", padx=6)
        self.bar_lbl = ttk.Label(f, text="")
        self.bar_lbl.grid(row=2, column=0, sticky="w", padx=6)
        self.msg_lbl = ttk.Label(f, text="", foreground="#a33")
        self.msg_lbl.grid(row=3, column=0, sticky="w", padx=6, pady=(0, 4))

        # controls
        f = ttk.Frame(r)
        f.grid(row=6, column=0, sticky="ew", **pad)
        self.go_btn = ttk.Button(f, text="Start  (F8)", command=self.toggle)
        self.go_btn.grid(row=0, column=0, padx=4)
        ttk.Button(f, text="Quit  (F9)", command=self.quit).grid(row=0, column=1, padx=4)
        self.dbg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Debug preview", variable=self.dbg_var,
                        command=lambda: setattr(self, "debug", self.dbg_var.get())).grid(row=0, column=2, padx=10)

    def refresh_windows(self):
        titles = sorted({t for t, _ in list_windows()})
        self.win_box["values"] = ["(full screen)"] + titles

    def on_window(self, _=None):
        t = self.win_var.get()
        self.cfg["window_title"] = "" if t == "(full screen)" else t
        self.save()

    def update_cal_label(self):
        c = self.cfg
        bar = f"bar: {'set' if c['bar'] else 'NOT SET'}"
        col = "colors: " + (f"fish {c['fish']['hex']}, rod {c['rod']['hex']}" if c["fish"] and c["rod"] else "NOT SET")
        fb = f"F button: {'set' if c['fbtn'] else 'NOT SET'}"
        self.cal_lbl.config(text=f"{bar}   |   {col}   |   {fb}")

    def save(self):
        with open(CFG_FILE, "w") as f:
            json.dump(self.cfg, f, indent=2)

    # ---------- calibration
    def delayed(self, fn):
        self.armed = False
        self.root.withdraw()
        self.root.after(3000, lambda: self._run_cal(fn))

    def _run_cal(self, fn):
        try:
            fn()
        except Exception as e:
            messagebox.showerror("Calibration failed", str(e))
        finally:
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.update_cal_label()
            self.save()

    def snapshot(self):
        fr = frame_rect(self.cfg["window_title"])
        if not fr:
            raise RuntimeError("Game window not found / minimized. Pick it in the dropdown.")
        l, t, w, h = fr
        with mss.mss() as sct:
            img = grab(sct, {"left": l, "top": t, "width": w, "height": h})
        if winsound:
            winsound.Beep(1000, 120)
        return img, fr

    def select_roi(self, img, title):
        sc = min(1.0, 1500 / img.shape[1])
        view = cv2.resize(img, None, fx=sc, fy=sc) if sc < 1 else img
        x, y, w, h = cv2.selectROI(title, view, showCrosshair=False)
        cv2.destroyAllWindows()
        if w == 0 or h == 0:
            return None
        return int(x / sc), int(y / sc), int(w / sc), int(h / sc)

    def cal_bar(self):
        img, fr = self.snapshot()
        roi = self.select_roi(img, "Drag a TIGHT box around the grey track, then ENTER")
        if not roi:
            return
        x, y, w, h = roi
        picks = pick_colors(img[y:y + h, x:x + w], [("fish", "TEAL fish bar"), ("rod", "YELLOW rod marker")])
        if not picks:
            return
        self.cfg["bar"] = [x / fr[2], y / fr[3], w / fr[2], h / fr[3]]
        self.cfg.update(picks)

    def cal_fbtn(self):
        img, fr = self.snapshot()
        roi = self.select_roi(img, "Drag a box around the F button CIRCLE only (no letter badge), then ENTER")
        if not roi:
            return
        x, y, w, h = roi
        self.cfg["fbtn"] = [x / fr[2], y / fr[3], w / fr[2], h / fr[3]]

    # ---------- controls
    def toggle(self):
        self.armed = not self.armed
        self.go_btn.config(text="Stop  (F8)" if self.armed else "Start  (F8)")
        if self.armed and self.cfg["window_title"]:
            try:
                h = find_hwnd(self.cfg["window_title"])
                if h:
                    user32.SetForegroundWindow(h)
            except Exception:
                pass

    def quit(self):
        self.armed = False
        self.stop.set()
        self.save()
        time.sleep(0.1)
        for k in ("a", "d"):
            pydirectinput.keyUp(k)
        self.root.destroy()

    def poll(self):
        if "quit" in self.req:
            return self.quit()
        if "toggle" in self.req:
            self.req.discard("toggle")
            self.toggle()
        if "dbg_off" in self.req:            # debug window was closed with the X
            self.req.discard("dbg_off")
            self.dbg_var.set(False)
            
        s = self.status
        self.st_lbl.config(text=f"state: {s['state']}   ({'RUNNING' if self.armed else 'stopped - detect only'})")
        if s["ratios"]:
            b, g, w = s["ratios"]
            self.ratio_lbl.config(text=f"F button  blue {b:.3f}   grey {g:.3f}   white {w:.3f}")
        else:
            self.ratio_lbl.config(text="")
        self.bar_lbl.config(text=s["bar"])
        self.msg_lbl.config(text=s["msg"])
        self.root.after(100, self.poll)

    # ---------- worker thread
    def bot_loop(self):
        cfg = self.cfg
        held = None
        fr, fr_t = None, 0
        pend, pend_since, conf = "NONE", 0, "NONE"
        fired, last_press, dbg_open = False, 0, False
        pend, pend_since, conf = "NONE", 0, "NONE"
        fired, last_press, dbg_open = False, 0, False
        awaiting_bite = False

        def release():
            pydirectinput.keyUp("a")
            pydirectinput.keyUp("d")

        with mss.mss() as sct:
            while not self.stop.is_set():
                now = time.time()
                armed = self.armed
                if fr is None or now - fr_t > 0.25:      # follows the window if it moves/resizes
                    fr, fr_t = frame_rect(cfg["window_title"]), now
                if not fr:
                    self.status = {"state": "NONE", "ratios": None, "bar": "", "msg": "game window not found"}
                    time.sleep(0.3)
                    continue

                # ---- minigame bar
                steering, bar_txt, frame, fs, rs = False, "bar: not calibrated", None, None, None
                if cfg["bar"] and cfg["fish"] and cfg["rod"]:
                    frame = grab(sct, rel_to_abs(cfg["bar"], fr))
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    fs = find_blob(cv2.inRange(hsv, np.array(cfg["fish"]["lo"]), np.array(cfg["fish"]["hi"])),
                         12, max(4, int(0.2 * frame.shape[0])), None, 15)
                    rs = find_blob(cv2.inRange(hsv, np.array(cfg["rod"]["lo"]), np.array(cfg["rod"]["hi"])),
                         2, max(4, int(0.4 * frame.shape[0])), int(0.08 * frame.shape[1]))
                    steering = bool(fs and rs)
                    bar_txt = f"bar: fish {'found' if fs else '-'}   rod {'found' if rs else '-'}"

                want = None
                if steering and armed and cfg["steer"]:
                    rod_x = (rs[0] + rs[1]) / 2
                    err = rod_x - (fs[0] + fs[1]) / 2
                    dz = max(3, (fs[1] - fs[0]) * cfg["deadzone"])
                    if err > dz:
                        want = "a"
                    elif err < -dz:
                        want = "d"
                if want != held or not armed:
                    release()
                    if want and armed:
                        pydirectinput.keyDown(want)
                    held = want if armed else None

                # ---- F button state
                ratios = None
                if steering:
                    st = "MINIGAME"
                elif cfg["fbtn"]:
                    st, ratios = classify(grab(sct, rel_to_abs(cfg["fbtn"], fr)), cfg)
                else:
                    st = "NONE"

                if st != pend:
                    pend, pend_since = st, now
                if pend != conf and now - pend_since >= 0.25:       # must hold steady for 0.25s
                    conf, fired = pend, False
                if armed and conf in STATES and cfg["act"].get(conf) and now - last_press >= 0.6:
                    if conf == "IDLE" and awaiting_bite:
                        pass  # already cast - ignore the identical-looking idle icon until we see a real state change
                    else:
                        rep = cfg["f_repeat"]
                        if not fired or (rep > 0 and now - last_press >= rep):
                            tap("f")
                            fired, last_press = True, time.time()
                            if conf == "IDLE":
                                awaiting_bite = True
                            elif conf in ("HOOKED", "RESULT"):
                                awaiting_bite = False

                self.status = {"state": conf if conf != "NONE" else st, "ratios": ratios,
                               "bar": bar_txt, "msg": ""}

                # ---- optional debug preview
                                # ---- optional debug preview
                if self.debug and frame is not None:
                    view = frame.copy()
                    if fs:
                        cv2.rectangle(view, (int(fs[0]), 0), (int(fs[1]), view.shape[0] - 1), (255, 200, 0), 1)
                    if rs:
                        cx = int((rs[0] + rs[1]) / 2)
                        cv2.line(view, (cx, 0), (cx, view.shape[0]), (0, 0, 255), 1)
                    cv2.imshow("debug", cv2.resize(view, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
                    cv2.waitKey(1)
                    if not dbg_open:                     # just opened this cycle
                        pin_on_top_no_focus("debug")
                    dbg_open = True
                    # closed via the window's own [X] -> reflect that in the checkbox
                    if cv2.getWindowProperty("debug", cv2.WND_PROP_VISIBLE) < 1:
                        self.debug = False
                        self.req.add("dbg_off")
                        dbg_open = False
                elif dbg_open:
                    cv2.destroyWindow("debug")
                    dbg_open = False

                time.sleep(0.005 if armed else 0.03)
        release()


if __name__ == "__main__":
    App().root.mainloop()