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
CFG_FILE = "fishbot_v2_cfg.json"
OLD_CFG = "fishbot_cfg.json"          # only used to reuse the bar colors
H_TOL, S_TOL, V_TOL = 10, 70, 70
 
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
                _primary.update(s.monitors[1])
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
 
 
#vision helpers
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
    cfg = {"window_title": "", "bar": None, "fish": None, "rod": None, "steer": True, "deadzone": 0.15}
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE) as f:
            cfg.update(json.load(f))
    elif os.path.exists(OLD_CFG):       # reuse old colors so you don't re-click them
        with open(OLD_CFG) as f:
            old = json.load(f)
        cfg["fish"], cfg["rod"] = old.get("fish"), old.get("rod")
    retune(cfg)
    return cfg
 
 
# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        self.cfg = load_cfg()
        self.armed = False
        self.debug = False
        self.req = set()
        self.status = {"bar": "-", "msg": ""}
        self.stop = threading.Event()
 
        self.root = tk.Tk()
        self.root.title("Fishing bot v2")
        self.build_ui()
        keyboard.add_hotkey("f8", lambda: self.req.add("toggle"))
        keyboard.add_hotkey("f9", lambda: self.req.add("quit"))
        self.worker = threading.Thread(target=self.bot_loop, daemon=True)
        self.worker.start()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.poll()
 
    # ---------- UI
    def bind(self, key, var, cast=float):
        def upd(*_):
            try:
                self.cfg[key] = cast(var.get())
            except (tk.TclError, ValueError):
                pass
        var.trace_add("write", upd)
 
    def build_ui(self):
        r, pad = self.root, {"padx": 8, "pady": 4}
 
        f = ttk.LabelFrame(r, text="Game window")
        f.grid(row=0, column=0, sticky="ew", **pad)
        self.win_var = tk.StringVar(value=self.cfg["window_title"] or "(full screen)")
        self.win_box = ttk.Combobox(f, textvariable=self.win_var, state="readonly", width=44)
        self.win_box.grid(row=0, column=0, padx=6, pady=6)
        self.win_box.bind("<<ComboboxSelected>>", self.on_window)
        ttk.Button(f, text="Refresh", command=self.refresh_windows).grid(row=0, column=1, padx=6)
        self.refresh_windows()
 
        f = ttk.LabelFrame(r, text="Calibration (3 sec delay so you can switch to the game)")
        f.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Button(f, text="Calibrate bar + colors", command=self.delayed).grid(row=0, column=0, padx=6, pady=6)
        self.cal_lbl = ttk.Label(f, text="")
        self.cal_lbl.grid(row=1, column=0, sticky="w", padx=6)
        self.update_cal_label()
 
        f = ttk.LabelFrame(r, text="Minigame steering (A / D)")
        f.grid(row=2, column=0, sticky="ew", **pad)
        v = tk.BooleanVar(value=self.cfg["steer"])
        self.bind("steer", v, bool)
        ttk.Checkbutton(f, text="Steer with A/D", variable=v).grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(f, text="Deadzone (fraction of fish bar):").grid(row=1, column=0, sticky="w", padx=6)
        v = tk.DoubleVar(value=self.cfg["deadzone"])
        self.bind("deadzone", v)
        ttk.Spinbox(f, from_=0.02, to=0.6, increment=0.02, textvariable=v, width=6).grid(row=1, column=1, padx=6, pady=4)
 
        f = ttk.LabelFrame(r, text="Live")
        f.grid(row=3, column=0, sticky="ew", **pad)
        self.bar_lbl = ttk.Label(f, text="")
        self.bar_lbl.grid(row=0, column=0, sticky="w", padx=6)
        self.msg_lbl = ttk.Label(f, text="", foreground="#a33")
        self.msg_lbl.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 4))
 
        f = ttk.Frame(r)
        f.grid(row=4, column=0, sticky="ew", **pad)
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
        ok = c["bar"] and c["fish"] and c["rod"]
        txt = f"bar area set | fish {c['fish']['hex']} | rod {c['rod']['hex']}" if ok else "NOT CALIBRATED"
        self.cal_lbl.config(text=txt)
 
    def save(self):
        with open(CFG_FILE, "w") as f:
            json.dump(self.cfg, f, indent=2)
 
    #calibration
    def delayed(self):
        self.armed = False
        self.root.withdraw()
        self.root.after(3000, self._run_cal)
 
    def _run_cal(self):
        try:
            self.cal_bar()
        except Exception as e:
            messagebox.showerror("Calibration failed", str(e))
        finally:
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.update_cal_label()
            self.save()
 
    def cal_bar(self):
        fr = frame_rect(self.cfg["window_title"])
        if not fr:
            raise RuntimeError("Game window not found / minimized. Pick it in the dropdown.")
        l, t, w, h = fr
        with mss.mss() as sct:
            img = grab(sct, {"left": l, "top": t, "width": w, "height": h})
        if winsound:
            winsound.Beep(1000, 120)
        sc = min(1.0, 1500 / img.shape[1])
        view = cv2.resize(img, None, fx=sc, fy=sc) if sc < 1 else img
        x, y, rw, rh = cv2.selectROI("Drag a TIGHT box around the grey track, then ENTER", view, showCrosshair=False)
        cv2.destroyAllWindows()
        if rw == 0 or rh == 0:
            return
        x, y, rw, rh = int(x / sc), int(y / sc), int(rw / sc), int(rh / sc)
        picks = pick_colors(img[y:y + rh, x:x + rw], [("fish", "TEAL fish bar"), ("rod", "YELLOW rod marker")])
        if not picks:
            return
        self.cfg["bar"] = [x / w, y / h, rw / w, rh / h]     # fractions of the game frame
        self.cfg.update(picks)
 
    #controls
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
        s = self.status
        self.bar_lbl.config(text=f"{'RUNNING' if self.armed else 'stopped (detect only)'}   |   {s['bar']}")
        self.msg_lbl.config(text=s["msg"])
        self.root.after(100, self.poll)
 
    #worker thread
    def bot_loop(self):
        cfg = self.cfg
        held, dbg_open = None, False
        fr, fr_t = None, 0
 
        def release():
            pydirectinput.keyUp("a")
            pydirectinput.keyUp("d")
 
        with mss.mss() as sct:
            while not self.stop.is_set():
                now = time.time()
                armed = self.armed
                if not (cfg["bar"] and cfg["fish"] and cfg["rod"]):
                    self.status = {"bar": "-", "msg": "not calibrated"}
                    time.sleep(0.3)
                    continue
                if fr is None or now - fr_t > 0.25:      # follows the window if it moves/resizes
                    fr, fr_t = frame_rect(cfg["window_title"]), now
                if not fr:
                    release()
                    held = None
                    self.status = {"bar": "-", "msg": "game window not found"}
                    time.sleep(0.3)
                    continue
 
                frame = grab(sct, rel_to_abs(cfg["bar"], fr))
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                fs = find_blob(cv2.inRange(hsv, np.array(cfg["fish"]["lo"]), np.array(cfg["fish"]["hi"])),
                         12, max(4, int(0.2 * frame.shape[0])), None, 15)
                rs = find_blob(cv2.inRange(hsv, np.array(cfg["rod"]["lo"]), np.array(cfg["rod"]["hi"])),
                         2, max(4, int(0.4 * frame.shape[0])), int(0.08 * frame.shape[1]))
 
                want = None
                if armed and cfg["steer"] and fs and rs:
                    err = (rs[0] + rs[1]) / 2 - (fs[0] + fs[1]) / 2
                    dz = max(3, (fs[1] - fs[0]) * cfg["deadzone"])
                    if err > dz:
                        want = "a"      # rod right of fish -> go left
                    elif err < -dz:
                        want = "d"      # rod left of fish -> go right
                if want != held or not armed:
                    release()
                    if want and armed:
                        pydirectinput.keyDown(want)
                    held = want if armed else None
 
                self.status = {"bar": f"fish {'found' if fs else '-'}   rod {'found' if rs else '-'}", "msg": ""}
 
                if self.debug:
                    view = frame.copy()
                    if fs:
                        cv2.rectangle(view, (int(fs[0]), 0), (int(fs[1]), view.shape[0] - 1), (255, 200, 0), 1)
                    if rs:
                        cx = int((rs[0] + rs[1]) / 2)
                        cv2.line(view, (cx, 0), (cx, view.shape[0]), (0, 0, 255), 1)
                    cv2.imshow("debug", cv2.resize(view, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
                    cv2.waitKey(1)
                    dbg_open = True
                elif dbg_open:
                    cv2.destroyWindow("debug")
                    dbg_open = False
 
                time.sleep(0.005 if armed else 0.03)
        release()
 
 
if __name__ == "__main__":
    App().root.mainloop()