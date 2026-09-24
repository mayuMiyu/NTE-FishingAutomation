import sys, json, time
import cv2
import numpy as np
import mss
import pydirectinput
import keyboard
 
CFG_FILE = "fishbot_cfg.json"
pydirectinput.PAUSE = 0
 
# tolerance around the picked color (OpenCV HSV: H 0-179, S/V 0-255)
H_TOL, S_TOL, V_TOL = 10, 70, 70
 
# ---------- helpers ----------
def grab(sct, mon):
    return np.array(sct.grab(mon))[:, :, :3]  # BGR
 
def hsv_range(bgr_pixel):
    h, s, v = cv2.cvtColor(np.uint8([[bgr_pixel]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = int(h), int(s), int(v)
    lo = [max(h - H_TOL, 0), max(s - S_TOL, 0), max(v - V_TOL, 0)]
    hi = [min(h + H_TOL, 179), min(s + S_TOL, 255), min(v + V_TOL, 255)]
    return lo, hi
 
def hex_of(bgr):
    b, g, r = [int(x) for x in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"
 
def span(mask):
    """leftmost / rightmost column that has any matching pixel"""
    cols = np.where(mask.any(axis=0))[0]
    if len(cols) < 2:
        return None
    return cols[0], cols[-1]
 
# ---------- calibrate ----------
def calibrate():
    with mss.mss() as sct:
        full = grab(sct, sct.monitors[1])
    print("1) Drag a box around the GREY bar track only (skip the icons), press ENTER.")
    x, y, w, h = cv2.selectROI("select bar area", full, showCrosshair=False)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        print("no area selected"); return
    roi = full[y:y + h, x:x + w]
 
    # blow the crop up so it's easier to click precisely
    scale = max(1, 1200 // w)
    big = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
 
    picks = {}
    banner = 30
    for name, label in (("fish", "TEAL/GREEN fish bar"), ("rod", "YELLOW rod marker")):
        print(f"2) Click on the {label}.  (both must be visible in the screenshot)")
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
                    return
            px, py = clicked[0]
            py = min(py, roi.shape[0] - 1)
            bgr = roi[py, px]
            sat = int(cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0][1])
            if sat < 80:
                print(f"   {hex_of(bgr)} looks like sky/grey (low saturation) - click again on the {label}")
                continue
            lo, hi = hsv_range(bgr)
            picks[name] = {"hex": hex_of(bgr), "lo": lo, "hi": hi}
            print(f"   {name}: {hex_of(bgr)}  HSV range {lo} -> {hi}")
            break
    cv2.destroyAllWindows()
 
    with mss.mss() as sct:
        m = sct.monitors[1]
    cfg = {"mon": {"left": int(x) + m["left"], "top": int(y) + m["top"],
                   "width": int(w), "height": int(h)}, **picks}
    with open(CFG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"saved to {CFG_FILE}")
 
# ---------- run ----------
def release_all():
    pydirectinput.keyUp("a")
    pydirectinput.keyUp("d")
 
def run(debug=False):
    with open(CFG_FILE) as f:
        cfg = json.load(f)
    mon = cfg["mon"]
    fish_lo, fish_hi = np.array(cfg["fish"]["lo"]), np.array(cfg["fish"]["hi"])
    rod_lo, rod_hi = np.array(cfg["rod"]["lo"]), np.array(cfg["rod"]["hi"])
 
    active, held = False, None
    print("ready. F8 = start/pause, F9 = quit")
 
    with mss.mss() as sct:
        while not keyboard.is_pressed("F9"):
            if keyboard.is_pressed("F8"):
                active = not active
                if not active:
                    release_all(); held = None
                print("ACTIVE" if active else "paused")
                time.sleep(0.4)  # debounce
 
            frame = grab(sct, mon)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            fish_m = cv2.inRange(hsv, fish_lo, fish_hi)
            rod_m = cv2.inRange(hsv, rod_lo, rod_hi)
            fs, rs = span(fish_m), span(rod_m)
 
            want = None
            if active and fs and rs:
                fish_l, fish_r = fs
                rod_x = (rs[0] + rs[1]) / 2
                fish_c = (fish_l + fish_r) / 2
                dz = max(3, (fish_r - fish_l) * 0.15)   # deadzone
                err = rod_x - fish_c
                if err > dz:
                    want = "a"      # rod is right of fish -> go left
                elif err < -dz:
                    want = "d"      # rod is left of fish -> go right
 
            if active and want != held:
                release_all()
                if want:
                    pydirectinput.keyDown(want)
                held = want
 
            if debug:
                view = frame.copy()
                if fs:
                    cv2.rectangle(view, (fs[0], 0), (fs[1], view.shape[0] - 1), (255, 200, 0), 1)
                if rs:
                    cv2.line(view, (int((rs[0] + rs[1]) / 2), 0),
                             (int((rs[0] + rs[1]) / 2), view.shape[0]), (0, 0, 255), 1)
                view = cv2.resize(view, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                cv2.imshow("debug", view)
                cv2.moveWindow("debug", 50, 600)   # keep it out of the capture area
                cv2.waitKey(1)
 
            time.sleep(0.005)
    release_all()
    cv2.destroyAllWindows()
 
if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("calibrate", "run"):
        print(__doc__)
    elif sys.argv[1] == "calibrate":
        calibrate()
    else:
        run(debug="--debug" in sys.argv)