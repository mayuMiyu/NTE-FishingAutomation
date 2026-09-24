import ctypes, json, os, threading, time
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
CFG_FILE = "fishbot_cfg.json"
H_TOL, S_TOL, V_TOL = 10, 70, 70
 
 
# ---------------------------------------------------------------- helpers
def grab(sct, region):
    return np.array(sct.grab(region))[:, :, :3]  # BGR
 
 
def hex_of(bgr):
    b, g, r = [int(x) for x in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"
 
 
def hsv_range(bgr):
    h, s, v = [int(x) for x in cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0]]
    return ([max(h - H_TOL, 0), max(s - S_TOL, 0), max(v - V_TOL, 0)],
            [min(h + H_TOL, 179), min(s + S_TOL, 255), min(v + V_TOL, 255)])
 
 
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
            lo, hi = hsv_range(bgr)
            out[key] = {"hex": hex_of(bgr), "lo": lo, "hi": hi}
            break
    cv2.destroyAllWindows()
    return out
 
 
def load_cfg():
    cfg = {"mon": None, "fish": None, "rod": None, "steer": True, "deadzone": 0.15,
           "lead": 0.08, "invert": False}
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE) as f:
            cfg.update(json.load(f))
    return cfg
 
 
# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        self.cfg = load_cfg()
        self.armed = False
        self.counting = False
        self.cd_token = 0
        self.debug = False
        self.req = set()
        self.status = {"bar": "-", "msg": ""}
        self.stop = threading.Event()
 
        self.root = tk.Tk()
        self.root.title("Fishing bot v1")
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
 
        f = ttk.LabelFrame(r, text="Calibration (3 sec delay so you can switch to the game)")
        f.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Button(f, text="Calibrate bar + colors", command=self.delayed).grid(row=0, column=0, padx=6, pady=6)
        self.cal_lbl = ttk.Label(f, text="")
        self.cal_lbl.grid(row=1, column=0, sticky="w", padx=6)
        self.update_cal_label()
 
        f = ttk.LabelFrame(r, text="Minigame steering (A / D)")
        f.grid(row=1, column=0, sticky="ew", **pad)
        v = tk.BooleanVar(value=self.cfg["steer"])
        self.bind("steer", v, bool)
        ttk.Checkbutton(f, text="Steer with A/D", variable=v).grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(f, text="Deadzone (fraction of fish bar):").grid(row=1, column=0, sticky="w", padx=6)
        v = tk.DoubleVar(value=self.cfg["deadzone"])
        self.bind("deadzone", v)
        ttk.Spinbox(f, from_=0.02, to=0.6, increment=0.02, textvariable=v, width=6).grid(row=1, column=1, padx=6, pady=4)
        ttk.Label(f, text="Lead (sec, releases early to stop overshoot):").grid(row=2, column=0, sticky="w", padx=6)
        v = tk.DoubleVar(value=self.cfg["lead"])
        self.bind("lead", v)
        ttk.Spinbox(f, from_=0.0, to=0.5, increment=0.02, textvariable=v, width=6).grid(row=2, column=1, padx=6, pady=4)
        v = tk.BooleanVar(value=self.cfg["invert"])
        self.bind("invert", v, bool)
        ttk.Checkbutton(f, text="Invert A/D (if it steers the wrong way)", variable=v).grid(row=3, column=0, sticky="w", padx=6)
 
        f = ttk.LabelFrame(r, text="Live")
        f.grid(row=2, column=0, sticky="ew", **pad)
        self.bar_lbl = ttk.Label(f, text="")
        self.bar_lbl.grid(row=0, column=0, sticky="w", padx=6)
        self.msg_lbl = ttk.Label(f, text="", foreground="#a33")
        self.msg_lbl.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 4))
 
        f = ttk.Frame(r)
        f.grid(row=3, column=0, sticky="ew", **pad)
        self.go_btn = ttk.Button(f, text="Start  (F8)", command=lambda: self.toggle(3))
        self.go_btn.grid(row=0, column=0, padx=4)
        ttk.Button(f, text="Quit  (F9)", command=self.quit).grid(row=0, column=1, padx=4)
        self.dbg_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Debug preview", variable=self.dbg_var,
                        command=lambda: setattr(self, "debug", self.dbg_var.get())).grid(row=0, column=2, padx=10)
 
    def update_cal_label(self):
        c = self.cfg
        ok = c["mon"] and c["fish"] and c["rod"]
        txt = f"bar area set | fish {c['fish']['hex']} | rod {c['rod']['hex']}" if ok else "NOT CALIBRATED"
        self.cal_lbl.config(text=txt)
 
    def save(self):
        with open(CFG_FILE, "w") as f:
            json.dump(self.cfg, f, indent=2)
 
    # ---------- calibration
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
        with mss.mss() as sct:
            m = sct.monitors[1]
            img = grab(sct, m)
        if winsound:
            winsound.Beep(1000, 120)
        sc = min(1.0, 1500 / img.shape[1])
        view = cv2.resize(img, None, fx=sc, fy=sc) if sc < 1 else img
        x, y, w, h = cv2.selectROI("Drag a TIGHT box around the grey track, then ENTER", view, showCrosshair=False)
        cv2.destroyAllWindows()
        if w == 0 or h == 0:
            return
        x, y, w, h = int(x / sc), int(y / sc), int(w / sc), int(h / sc)
        picks = pick_colors(img[y:y + h, x:x + w], [("fish", "TEAL fish bar"), ("rod", "YELLOW rod marker")])
        if not picks:
            return
        self.cfg["mon"] = {"left": x + m["left"], "top": y + m["top"], "width": w, "height": h}
        self.cfg.update(picks)
 
    # ---------- controls
    def toggle(self, delay=0):
        self.cd_token += 1                      # cancels any running countdown
        if self.counting and not delay:         # F8 during countdown = start right now
            self.arm()
            return
        if self.armed or self.counting:         # stop / cancel
            self.armed = self.counting = False
            self.go_btn.config(text="Start  (F8)")
            return
        if delay:
            self.counting = True
            self.countdown(delay, self.cd_token)
        else:
            self.arm()
 
    def countdown(self, n, token):
        if token != self.cd_token:
            return
        if n > 0:
            self.go_btn.config(text=f"Click the game!  {n}...  (cancel)")
            self.root.after(1000, lambda: self.countdown(n - 1, token))
        else:
            self.arm()
 
    def arm(self):
        self.armed, self.counting = True, False
        self.go_btn.config(text="Stop  (F8)")
 
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
        if "dbg_off" in self.req:               # debug window was closed with the X
            self.req.discard("dbg_off")
            self.dbg_var.set(False)
        s = self.status
        self.bar_lbl.config(text=f"{'RUNNING' if self.armed else 'stopped (detect only)'}   |   {s['bar']}")
        self.msg_lbl.config(text=s["msg"])
        self.root.after(100, self.poll)
 
    # ---------- worker thread
    def bot_loop(self):
        cfg = self.cfg
        held, dbg_open, dbg_frames = None, False, 0
        last_rod, last_t, vel, loops, hz, hz_t = None, 0.0, 0.0, 0, 0, time.time()
 
        def release():
            pydirectinput.keyUp("a")
            pydirectinput.keyUp("d")
 
        with mss.mss() as sct:
            mon1 = sct.monitors[1]
            while not self.stop.is_set():
                armed = self.armed
                if not (cfg["mon"] and cfg["fish"] and cfg["rod"]):
                    self.status = {"bar": "-", "msg": "not calibrated"}
                    time.sleep(0.3)
                    continue
 
                frame = grab(sct, cfg["mon"])
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                fs = span(cv2.inRange(hsv, np.array(cfg["fish"]["lo"]), np.array(cfg["fish"]["hi"])))
                rs = span(cv2.inRange(hsv, np.array(cfg["rod"]["lo"]), np.array(cfg["rod"]["hi"])))
 
                now = time.time()
                rod_x = (rs[0] + rs[1]) / 2 if rs else None
                if rod_x is not None and last_rod is not None and now > last_t:
                    vel = 0.6 * vel + 0.4 * (rod_x - last_rod) / (now - last_t)   # px/sec, smoothed
                elif rod_x is None:
                    vel = 0.0
                last_rod, last_t = rod_x, now
 
                want, err = None, None
                if fs and rs:
                    err = rod_x + vel * cfg["lead"] - (fs[0] + fs[1]) / 2        # predicted offset from fish center
                    dz = max(3, (fs[1] - fs[0]) * cfg["deadzone"])
                    if armed and cfg["steer"]:
                        to_left, to_right = ("d", "a") if cfg["invert"] else ("a", "d")
                        if err > dz:
                            want = to_left      # rod right of fish -> go left
                        elif err < -dz:
                            want = to_right     # rod left of fish -> go right
                if not armed:
                    if held:
                        release()
                        held = None
                elif want != held:
                    release()
                    if want:
                        pydirectinput.keyDown(want)
                    held = want
 
                loops += 1
                if now - hz_t >= 1.0:
                    hz, loops, hz_t = loops, 0, now
                err_txt = f"{err:+.0f}px" if err is not None else "-"
                self.status = {"bar": f"fish {'found' if fs else '-'}   rod {'found' if rs else '-'}   |   "
                                      f"err {err_txt}   key {held or '-'}   {hz} loops/s", "msg": ""}
 
                if self.debug:
                    view = frame.copy()
                    if fs:
                        cv2.rectangle(view, (int(fs[0]), 0), (int(fs[1]), view.shape[0] - 1), (255, 200, 0), 1)
                    if rs:
                        cx = int((rs[0] + rs[1]) / 2)
                        cv2.line(view, (cx, 0), (cx, view.shape[0]), (0, 0, 255), 1)
                    view = cv2.resize(view, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                    cv2.imshow("debug", view)
                    if dbg_frames == 0:
                        # park it on the opposite half of the screen so it never films itself
                        in_top = cfg["mon"]["top"] < mon1["top"] + mon1["height"] / 2
                        y = mon1["top"] + 20 if not in_top else mon1["top"] + mon1["height"] - view.shape[0] - 140
                        cv2.moveWindow("debug", mon1["left"] + 20, max(0, y))
                    cv2.waitKey(1)
                    dbg_open, dbg_frames = True, dbg_frames + 1
                    if dbg_frames > 5 and cv2.getWindowProperty("debug", cv2.WND_PROP_VISIBLE) < 1:
                        self.debug = False          # closed with the X -> untick the checkbox
                        self.req.add("dbg_off")
                elif dbg_open:
                    try:
                        cv2.destroyWindow("debug")
                    except cv2.error:
                        pass
                    dbg_open, dbg_frames = False, 0
 
                time.sleep(0.005 if armed else 0.03)
        release()
 
 
if __name__ == "__main__":
    App().root.mainloop()