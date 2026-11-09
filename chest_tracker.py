"""
Fortnite chest tracker (screen-watching).

Only takes screenshots of your display, like OBS does. It never reads or
touches the game's memory or files.

Setup:   pip install mss opencv-python numpy
Steps:   python chest_tracker.py calibrate   (once)
         python chest_tracker.py test        (beeps + saves a log while you play)
         python chest_tracker.py run         (while you play)
         python chest_tracker.py stats       (see your totals)

Set Fortnite to Windowed Fullscreen so screen capture works.
"""
import argparse
import csv
import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import cv2
import mss
import numpy as np

try:
    import winsound
except ImportError:  # not on Windows
    winsound = None

BASE = Path(__file__).parent
CFG_FILE = BASE / "config.json"
TPL_FILE = BASE / "prompt_template.png"
LOG_FILE = BASE / "chest_log.csv"
DEBUG_DIR = BASE / "debug"

# OpenCV hue ranges (0-179), ordered lowest to highest rarity.
RARITIES = [
    ("Uncommon", (45, 75)),
    ("Rare", (95, 115)),
    ("Epic", (125, 155)),
    ("Legendary", (6, 18)),
    ("Mythic", (20, 33)),
]

MSS = getattr(mss, "MSS", None) or mss.mss

DEFAULTS = {
    "monitor": 1,
    "threshold": 0.70,    # template match score needed to count the prompt as visible
    "min_visible": 0.0,   # seconds the prompt must be seen before it counts
    "gone_after": 0.25,   # seconds the prompt must be gone to count as "opened"
    "settle": 0.7,        # seconds to wait for loot to appear before reading it
    "cooldown": 2.0,      # seconds to ignore new chests after one is logged
    "min_pixels": 400,    # NEW rarity-colored pixels (increase after opening) needed
    "bright": 190,        # brightness cutoff for the white prompt text/icon
    "require_loot": False,
    "detect_rarity": False,  # experimental: guess rarity from loot colors
}


def make_dpi_aware():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def grab(sct, monitor_idx, box=None):
    mon = sct.monitors[monitor_idx]
    if box is None:
        region = mon
    else:
        x, y, w, h = box
        w = min(w, mon["width"] - x)
        h = min(h, mon["height"] - y)
        region = {"left": mon["left"] + x, "top": mon["top"] + y, "width": w, "height": h}
    return np.array(sct.grab(region))[:, :, :3]


def countdown(seconds, msg):
    print(msg)
    for i in range(seconds, 0, -1):
        print(f"  {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  Capturing.   ")


def pick_box(title, img, prompt):
    print(prompt)
    x, y, w, h = cv2.selectROI(title, img, False)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        raise SystemExit("No box selected. Run calibrate again.")
    return [int(x), int(y), int(w), int(h)]


def calibrate(args):
    if args.prompt_only and CFG_FILE.exists():
        cfg = dict(DEFAULTS)
        cfg.update(json.loads(CFG_FILE.read_text()))
        cfg["min_pixels"] = max(cfg["min_pixels"], 400)
    else:
        cfg = dict(DEFAULTS, monitor=args.monitor)
    with MSS() as sct:
        countdown(8, "Step 1: Switch to Fortnite and stand next to an UNOPENED chest so its "
                     "SEARCH prompt is on screen. Keep it there.")
        img = grab(sct, cfg["monitor"])
        px, py, pw, ph = pick_box(
            "Box ONLY the prompt label, then press ENTER", img,
            "Drag a TIGHT box around just the prompt label (the dark box with the icon and the "
            "word SEARCH). Do NOT include the chest. Press ENTER.")
        cv2.imwrite(str(TPL_FILE), img[py:py + ph, px:px + pw])
        cfg["prompt_box"] = [px, py, pw, ph]

        if "loot_box" not in cfg:
            countdown(8, "\nStep 2: Switch back to the game and open the chest. "
                         "Keep the loot on screen until the capture.")
            img = grab(sct, cfg["monitor"])
            cfg["loot_box"] = pick_box(
                "Drag a box over where the loot shows up, then press ENTER", img,
                "Drag a box over the area where the loot items appear, press ENTER.")
    CFG_FILE.write_text(json.dumps(cfg, indent=2))
    print(f"Saved {CFG_FILE.name}. Next, try: python chest_tracker.py test")


def load_config():
    if not CFG_FILE.exists() or not TPL_FILE.exists():
        raise SystemExit("Not calibrated yet. Run: python chest_tracker.py calibrate")
    cfg = dict(DEFAULTS)
    cfg.update(json.loads(CFG_FILE.read_text()))
    return cfg, prep(cv2.imread(str(TPL_FILE)), cfg["bright"])


def prep(img, bright):
    """Keep only the bright white pixels (prompt text/icon), ignoring the background."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.threshold(gray, bright, 255, cv2.THRESH_BINARY)[1]


def rarity_counts(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    vivid = (hsv[..., 1] > 130) & (hsv[..., 2] > 160)
    hue = hsv[..., 0]
    return {name: int((vivid & (hue >= lo) & (hue <= hi)).sum())
            for name, (lo, hi) in RARITIES}


def delta_counts(after, before):
    return {k: after[k] - before[k] for k in after}


def best_rarity(counts, min_pixels):
    best = None
    for name, _ in RARITIES:  # ascending, so the last match is the highest rarity
        if counts[name] >= min_pixels:
            best = name
    return best


def search_box(cfg, tpl):
    """The prompt follows the chest around the screen, so search the whole screen."""
    return None


def prompt_score(sct, cfg, tpl, box):
    frame = grab(sct, cfg["monitor"], box)
    mask = prep(frame, cfg["bright"])
    if mask.shape[0] < tpl.shape[0] or mask.shape[1] < tpl.shape[1]:
        return 0.0, frame
    res = np.nan_to_num(cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED))
    _, score, _, (lx, ly) = cv2.minMaxLoc(res)
    th, tw = tpl.shape[:2]
    m = 20
    crop = frame[max(0, ly - m):ly + th + m, max(0, lx - m):lx + tw + m]
    return float(score), crop


def count_logged():
    if not LOG_FILE.exists():
        return 0
    with open(LOG_FILE) as f:
        return max(0, sum(1 for _ in f) - 1)


def log_chest(rarity):
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "best_rarity"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), rarity])
    total = count_logged()
    print(f"[{datetime.now():%H:%M:%S}] Chest #{total}: {rarity}")
    return total


def make_click_through(root):
    """Let mouse clicks pass through the overlay to the game."""
    try:
        import ctypes
        root.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = user32.GetWindowLongW(hwnd, -20)
        # layered | transparent | toolwindow (hidden from Alt+Tab)
        user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80)
    except Exception:
        pass


def show_overlay(state, x, y):
    import tkinter as tk
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.8)
    root.geometry(f"+{x}+{y}")
    bg = "#101428"
    root.configure(bg=bg)
    label = tk.Label(root, text="", font=("Segoe UI", 16, "bold"),
                     fg="#ffffff", bg=bg, padx=14, pady=8)
    label.pack()
    make_click_through(root)

    def poll():
        label.config(text=f"Chests: {state['session']}   Total: {state['total']}")
        root.attributes("-topmost", True)
        root.after(300, poll)

    poll()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


def test(args):
    cfg, tpl = load_config()
    box = search_box(cfg, tpl)
    out = BASE / "test_log.csv"
    DEBUG_DIR.mkdir(exist_ok=True)
    rarity_on = cfg["detect_rarity"]
    print(f"Test running for {args.seconds} seconds. Switch to Fortnite NOW and open some chests.")
    print("High beep = chest prompt detected." + (" Two low beeps = new loot colors." if rarity_on else ""))
    names = [n for n, _ in RARITIES]
    max_score = 0.0
    max_delta = {n: 0 for n in names}
    prompt_on = loot_on = saved_screen = False
    history = []
    start = time.time()
    with open(out, "w", newline="") as f, MSS() as sct:
        w = csv.writer(f)
        w.writerow(["seconds", "prompt_score"] + [n + "_increase" for n in names])
        try:
            while time.time() - start < args.seconds:
                now = time.time()
                if not saved_screen and now - start > 10:
                    cv2.imwrite(str(DEBUG_DIR / "screen_check.png"), grab(sct, cfg["monitor"]))
                    saved_screen = True
                score, crop = prompt_score(sct, cfg, tpl, box)
                if score > max_score:
                    max_score = score
                    cv2.imwrite(str(DEBUG_DIR / "best_prompt_view.png"), crop)

                delta = {n: 0 for n in names}
                if rarity_on:
                    counts = rarity_counts(grab(sct, cfg["monitor"], cfg["loot_box"]))
                    history.append((now, counts))
                    while len(history) > 1 and history[1][0] <= now - 1.5:
                        history.pop(0)
                    delta = delta_counts(counts, history[0][1])
                    for n in names:
                        max_delta[n] = max(max_delta[n], delta[n])
                w.writerow([f"{now - start:.1f}", f"{score:.2f}"] + [delta[n] for n in names])

                if score >= cfg["threshold"] and not prompt_on and winsound:
                    winsound.Beep(1200, 150)
                prompt_on = score >= cfg["threshold"]

                has_loot = rarity_on and best_rarity(delta, cfg["min_pixels"]) is not None
                if has_loot and not loot_on and winsound:
                    winsound.Beep(500, 120)
                    winsound.Beep(500, 120)
                loot_on = has_loot
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
    print("\nTest finished.")
    print(f"Highest prompt score: {max_score:.2f} (needs {cfg['threshold']:.2f})")
    if rarity_on:
        print("Biggest color increase (need " + str(cfg["min_pixels"]) + "+): "
              + ", ".join(f"{n} {max_delta[n]}" for n in names))
    print(f"Timeline saved to {out.name}. Screenshots saved in the debug folder.")


def run(args):
    cfg, tpl = load_config()
    if args.no_loot_check:
        cfg["require_loot"] = False
    rarity_on = cfg["detect_rarity"]
    box = search_box(cfg, tpl)
    state = {"session": 0, "total": count_logged()}

    def loop():
        seen_since = last_seen = baseline = None
        last_log = last_weak = 0.0
        print("Watching for chest openings. Ctrl+C to stop.")
        with MSS() as sct:
            while True:
                now = time.time()
                score, _ = prompt_score(sct, cfg, tpl, box)
                if score >= cfg["threshold"]:
                    if seen_since is None:
                        seen_since = now
                        print(f"[{datetime.now():%H:%M:%S}] Prompt seen (score {score:.2f})")
                    last_seen = now
                    if rarity_on:
                        baseline = rarity_counts(grab(sct, cfg["monitor"], cfg["loot_box"]))
                elif seen_since is not None and now - last_seen >= cfg["gone_after"]:
                    visible_for = last_seen - seen_since
                    seen_since = None
                    ok = visible_for >= cfg["min_visible"] and now - last_log >= cfg["cooldown"]
                    why = "" if ok else (" -> too short, ignored" if visible_for < cfg["min_visible"]
                                         else " -> within cooldown, ignored")
                    print(f"[{datetime.now():%H:%M:%S}] Prompt gone after {visible_for:.2f}s{why}")
                    if ok:
                        rarity = None
                        if rarity_on:
                            time.sleep(cfg["settle"])
                            loot = grab(sct, cfg["monitor"], cfg["loot_box"])
                            after = rarity_counts(loot)
                            delta = delta_counts(after, baseline) if baseline else after
                            rarity = best_rarity(delta, cfg["min_pixels"])
                            if args.debug:
                                DEBUG_DIR.mkdir(exist_ok=True)
                                cv2.imwrite(str(DEBUG_DIR / f"{datetime.now():%H%M%S}_{rarity}.png"), loot)
                        if rarity or not (rarity_on and cfg["require_loot"]):
                            state["total"] = log_chest(rarity or "Unknown")
                            state["session"] += 1
                            last_log = time.time()
                        else:
                            print(f"[{datetime.now():%H:%M:%S}] Prompt vanished but no new loot colors; skipped.")
                if 0.5 <= score < cfg["threshold"] and seen_since is None and now - last_weak > 1.0:
                    print(f"[{datetime.now():%H:%M:%S}] Weak match {score:.2f} (needs {cfg['threshold']:.2f})")
                    last_weak = now
                time.sleep(0.05)

    def guarded():
        try:
            loop()
        except Exception:
            traceback.print_exc()

    if args.overlay:
        threading.Thread(target=guarded, daemon=True).start()
        print(f"Overlay on at ({args.x}, {args.y}). Press Ctrl+C in this window to stop.")
        show_overlay(state, args.x, args.y)
        print("\nStopped.")
    else:
        try:
            loop()
        except KeyboardInterrupt:
            print("\nStopped.")


def stats(args):
    if not LOG_FILE.exists():
        raise SystemExit("No chests logged yet.")
    with open(LOG_FILE) as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    print(f"Total chests: {total}")
    for name in ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Unknown"]:
        n = sum(1 for r in rows if r["best_rarity"] == name)
        if n or name != "Unknown":
            print(f"  {name:<10} {n:>4}  ({n / total * 100:.0f}%)")


def main():
    make_dpi_aware()
    p = argparse.ArgumentParser(description="Fortnite chest tracker")
    p.add_argument("--monitor", type=int, default=1, help="monitor number (calibrate only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--prompt-only", action="store_true", help="redo only the prompt box")
    c.set_defaults(fn=calibrate)
    t = sub.add_parser("test")
    t.add_argument("--seconds", type=int, default=60, help="how long to record")
    t.set_defaults(fn=test)
    r = sub.add_parser("run")
    r.add_argument("--no-loot-check", action="store_true", help="log every prompt disappearance")
    r.add_argument("--debug", action="store_true", help="save loot-area screenshots to ./debug")
    r.add_argument("--overlay", action="store_true", help="show a small chest counter over the game")
    r.add_argument("--x", type=int, default=20, help="overlay left position in pixels")
    r.add_argument("--y", type=int, default=80, help="overlay top position in pixels")
    r.set_defaults(fn=run)
    sub.add_parser("stats").set_defaults(fn=stats)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()