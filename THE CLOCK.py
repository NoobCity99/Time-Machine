import sys
import time
import math
import platform
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

# =============================================================================
# === GUI Color Scheme Editor ==================================================
# Tweak these to change the overall look and clock progress colors.
# (Countdown color/sound settings live in their own section below, as requested)
# =============================================================================
SCHEME = {
    "bg": "#101316",
    "panel_bg": "#161a1f",
    "fg": "#e6f0ff",
    "muted": "#9aa7b2",
    "accent": "#79c0ff",
    "button_bg": "#222830",
    "button_fg": "#e6f0ff",
    "tab_bg": "#0d1117",
    "tab_active_bg": "#1c2128",
    "tab_fg": "#d7e2ee",
    "lcd_fg": "#b7ffb7",   # default text color for the LCD-look displays (clock/stopwatch/countdown)
    "lcd_dim": "#466b46",  # dimmer tint used for static placeholders or faded look
    # Clock second-hand progress bar colors (minute sweep)
    "progress_green": "#34d058",
    "progress_yellow": "#ffdf5d",
    "progress_red": "#f85149",
    # Borders
    "bezel": "#2a3139",
}

# =============================================================================
# === Countdown Visuals & Sounds (kept separate from the GUI color editor) ====
# Digits start green, turn yellow at <=50% remaining, red for final 10%.
# Beeps for last 10 seconds.
# =============================================================================
COUNTDOWN_COLORS = {
    "start": "#34d058",   # green
    "mid": "#ffdf5d",     # yellow
    "final": "#f85149",   # red
}

# On Windows we'll try a pitched beep; elsewhere we fall back to the window bell.
def beep():
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 120)  # frequency Hz, duration ms
        else:
            # Fallback – short bell
            root.bell()
    except Exception:
        try:
            root.bell()
        except Exception:
            pass

# =============================================================================
# Utilities
# =============================================================================
def try_lcd_font(root):
    """
    Try to find a 'vintage digital/LCD' font if installed; fall back gracefully.
    Good candidates: 'Digital-7 Mono', 'DS-Digital', 'LCDMono2', 'Quartz', etc.
    """
    candidates = [
        "Digital-7 Mono", "Digital-7", "DS-Digital", "LCDMono2", "LCD", "Quartz",
        "Seven Segment", "Segment7", "Let's go Digital", "DSEG7 Classic", "DSEG14 Classic"
    ]
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    # Courier New has that monospaced, squared-off vibe as a decent fallback
    return "Courier New"

def hms_tenths(elapsed_seconds):
    """Return (hours, minutes, seconds, tenths) from float seconds."""
    total_tenths = int(round(elapsed_seconds * 10))
    hours = total_tenths // (36000)
    rem = total_tenths % 36000
    minutes = rem // 600
    rem = rem % 600
    seconds = rem // 10
    tenths = rem % 10
    return hours, minutes, seconds, tenths

def parse_time_entry(s):
    """
    Parse "H:MM:SS", "MM:SS", "SS", or "H:MM" formats into seconds.
    Accepts spaces; returns int seconds or raises ValueError.
    """
    s = s.strip()
    if not s:
        raise ValueError("Empty time")
    parts = [p for p in s.split(":") if p != ""]
    if len(parts) == 1:
        # seconds
        return int(parts[0])
    elif len(parts) == 2:
        # MM:SS or H:MM (we'll assume MM:SS, but be generous: if second >= 60, treat as H:MM)
        a, b = parts
        a, b = int(a), int(b)
        if b >= 60:
            # assume H:MM
            return a * 3600 + b * 60
        # assume MM:SS
        return a * 60 + b
    elif len(parts) == 3:
        h, m, s2 = map(int, parts)
        return h * 3600 + m * 60 + s2
    else:
        raise ValueError("Too many ':' parts")

# =============================================================================
# Clock Tab
# =============================================================================
class ClockTab(ttk.Frame):
    def __init__(self, parent, lcd_family, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self["padding"] = 10
        self.configure(style="Panel.TFrame")

        # Clock face container
        outer = ttk.Frame(self, style="Panel.TFrame", padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        # Rectangular bezel
        bezel = tk.Frame(outer, bg=SCHEME["bezel"], bd=0, highlightthickness=0)
        bezel.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        # Bezel ring effect
        bezel_inner = tk.Frame(bezel, bg=SCHEME["bezel"])
        bezel_inner.pack(fill="both", expand=True, padx=6, pady=6)

        # Inner face (only one)
        self.face = tk.Frame(bezel_inner, bg=SCHEME["panel_bg"], bd=0, highlightthickness=0)
        self.face.pack(fill="both", expand=True)

        # Time label
        self.time_var = tk.StringVar(value="")
        self.time_lbl = tk.Label(
            self.face,
            textvariable=self.time_var,
            bg=SCHEME["panel_bg"],
            fg=SCHEME["lcd_fg"],
            font=(lcd_family, 64, "bold"),
        )
        self.time_lbl.pack(padx=20, pady=(20, 10), fill="x")

        # Progress canvas (second-hand sweep)
        self.progress_canvas = tk.Canvas(
            self.face, height=14, highlightthickness=0, bd=0, bg=SCHEME["panel_bg"]
        )
        self.progress_canvas.pack(fill="x", padx=20, pady=(0, 16))

        # Redraw track on resize so it fits new width
        self.bind("<Configure>", self._on_resize)

        # Start update loop
        self._tick()

    def _on_resize(self, _event):
        # Draw an empty track so the bar fits the new width immediately
        self.draw_progress_bar(0.0)

    def draw_progress_bar(self, frac: float):
        self.progress_canvas.delete("all")
        w = self.progress_canvas.winfo_width()
        h = self.progress_canvas.winfo_height()
        if w <= 1 or h <= 1:
            return  # not laid out yet

        if frac < 0.5:
            color = SCHEME["progress_green"]
        elif frac < 0.9:
            color = SCHEME["progress_yellow"]
        else:
            color = SCHEME["progress_red"]

        # background track
        self.progress_canvas.create_rectangle(0, 0, w, h, fill=SCHEME["bg"], width=0)
        # filled portion
        self.progress_canvas.create_rectangle(0, 0, int(w * frac), h, fill=color, width=0)

    def _tick(self):
        t = time.localtime()
        self.time_var.set(time.strftime("%H:%M:%S", t))
        frac = (t.tm_sec + (time.time() % 1.0)) / 60.0
        self.draw_progress_bar(frac)
        self.after(100, self._tick)


# =============================================================================
# Stopwatch Tab
# =============================================================================
class StopwatchTab(ttk.Frame):
    def __init__(self, parent, lcd_family, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self["padding"] = 10
        self.configure(style="Panel.TFrame")

        self.running = False
        self.start_ts = None   # monotonic when started
        self.base_elapsed = 0.0  # accumulated when stopped
        self.update_job = None
        self.lap_window = None
        self.lap_count = 0
        self.last_lap_elapsed = 0.0

        # Display
        self.var = tk.StringVar(value="00:00:00.0")
        self.lbl = tk.Label(
            self,
            textvariable=self.var,
            bg=SCHEME["panel_bg"],
            fg=SCHEME["lcd_fg"],
            font=(lcd_family, 56, "bold"),
            bd=0, highlightthickness=0
        )
        self.lbl.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 6))

        # Buttons
        self.start_btn = ttk.Button(self, text="Start", command=self.toggle)
        self.reset_btn = ttk.Button(self, text="Reset", command=self.reset)
        self.lap_btn = ttk.Button(self, text="Lap", command=self.lap)

        self.start_btn.grid(row=1, column=0, padx=4, pady=6, sticky="ew")
        self.reset_btn.grid(row=1, column=1, padx=4, pady=6, sticky="ew")
        self.lap_btn.grid(row=1, column=2, padx=4, pady=6, sticky="ew")

        for i in range(3):
            self.columnconfigure(i, weight=1)

    def current_elapsed(self):
        if self.running and self.start_ts is not None:
            return self.base_elapsed + (time.monotonic() - self.start_ts)
        return self.base_elapsed

    def update_display(self):
        elapsed = self.current_elapsed()
        h, m, s, t = hms_tenths(elapsed)
        self.var.set(f"{h:02d}:{m:02d}:{s:02d}.{t}")
        # schedule next update at ~every 100 ms
        self.update_job = self.after(100, self.update_display)

    def toggle(self):
        if not self.running:
            # start
            self.running = True
            self.start_ts = time.monotonic()
            self.start_btn.configure(text="Stop")
            if self.update_job is None:
                self.update_display()
        else:
            # stop
            self.running = False
            if self.start_ts is not None:
                self.base_elapsed += (time.monotonic() - self.start_ts)
            self.start_ts = None
            self.start_btn.configure(text="Start")
            if self.update_job is not None:
                self.after_cancel(self.update_job)
                self.update_job = None
            # ensure display settles on exact value
            self.update_display()
            if self.update_job is not None:
                self.after_cancel(self.update_job)
                self.update_job = None

    def reset(self):
        self.running = False
        self.start_ts = None
        self.base_elapsed = 0.0
        self.last_lap_elapsed = 0.0
        self.start_btn.configure(text="Start")
        if self.update_job is not None:
            self.after_cancel(self.update_job)
            self.update_job = None
        self.var.set("00:00:00.0")
        # Clear lap list if open
        if self.lap_window and self.lap_window.winfo_exists():
            self.lap_list.delete(0, "end")
            self.lap_count = 0

    def ensure_lap_window(self):
        if self.lap_window and self.lap_window.winfo_exists():
            return
        self.lap_window = tk.Toplevel(self)
        self.lap_window.title("Laps")
        self.lap_window.configure(bg=SCHEME["panel_bg"])
        self.lap_window.geometry("260x320")
        self.lap_window.resizable(False, True)

        header = tk.Label(self.lap_window, text="Lap Times", bg=SCHEME["panel_bg"], fg=SCHEME["fg"],
                          font=("Segoe UI", 12, "bold"))
        header.pack(padx=8, pady=6)

        self.lap_list = tk.Listbox(
            self.lap_window,
            bg=SCHEME["bg"],
            fg=SCHEME["fg"],
            highlightthickness=0,
            bd=0,
            font=("Consolas", 11)
        )
        self.lap_list.pack(fill="both", expand=True, padx=8, pady=8)

    def lap(self):
        self.ensure_lap_window()
        total = self.current_elapsed()
        lap_time = total - self.last_lap_elapsed
        self.last_lap_elapsed = total
        self.lap_count += 1
        h, m, s, t = hms_tenths(total)
        lh, lm, ls, lt = hms_tenths(lap_time)
        self.lap_list.insert(
            "end",
            f"Lap {self.lap_count:02d}  |  +{lh:02d}:{lm:02d}:{ls:02d}.{lt}  |  {h:02d}:{m:02d}:{s:02d}.{t}"
        )
        # Auto-scroll
        self.lap_list.see("end")

# =============================================================================
# Countdown Timer Tab
# =============================================================================
class CountdownTab(ttk.Frame):
    def __init__(self, parent, lcd_family, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self["padding"] = 10
        self.configure(style="Panel.TFrame")

        self.total_seconds = 0
        self.remaining = 0
        self.running = False
        self.job = None
        self.last_whole_sec = None  # to control beeps

        # Display
        self.var = tk.StringVar(value="00:00:00")
        self.lbl = tk.Label(
            self,
            textvariable=self.var,
            bg=SCHEME["panel_bg"],
            fg=SCHEME["lcd_fg"],
            font=(lcd_family, 56, "bold"),
            bd=0, highlightthickness=0
        )
        self.lbl.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(10, 6))

        # Entry row
        ttk.Label(self, text="Time:", style="Muted.TLabel").grid(row=1, column=0, sticky="e", padx=(10, 4))
        self.entry = ttk.Entry(self, width=12)
        self.entry.grid(row=1, column=1, sticky="w")
        ttk.Label(self, text="(H:MM:SS, MM:SS, or SS)", style="Muted.TLabel").grid(row=1, column=2, columnspan=2, sticky="w")

        # Buttons
        self.set_btn = ttk.Button(self, text="Set", command=self.set_time)
        self.start_btn = ttk.Button(self, text="Start", command=self.toggle)
        self.reset_btn = ttk.Button(self, text="Reset", command=self.reset)

        self.set_btn.grid(row=2, column=0, padx=4, pady=8, sticky="ew")
        self.start_btn.grid(row=2, column=1, padx=4, pady=8, sticky="ew")
        self.reset_btn.grid(row=2, column=2, padx=4, pady=8, sticky="ew")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)

    def set_time(self):
        try:
            seconds = parse_time_entry(self.entry.get())
            if seconds <= 0:
                raise ValueError("Non-positive time")
            self.total_seconds = seconds
            self.remaining = seconds
            self.last_whole_sec = None
            self.update_display(force_color=True)
        except ValueError:
            messagebox.showerror("Invalid time", "Please enter time as H:MM:SS, MM:SS, or SS (positive integers).")

    def toggle(self):
        if self.total_seconds <= 0 and self.remaining <= 0:
            # try to set from entry
            try:
                self.set_time()
            except Exception:
                return
        if not self.running:
            self.running = True
            self.start_btn.configure(text="Pause")
            self._tick()
        else:
            self.running = False
            self.start_btn.configure(text="Start")
            if self.job is not None:
                self.after_cancel(self.job)
                self.job = None

    def reset(self):
        self.running = False
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.remaining = self.total_seconds
        self.last_whole_sec = None
        self.start_btn.configure(text="Start")
        self.update_display(force_color=True)

    def update_display(self, force_color=False):
        # Show as HH:MM:SS
        r = max(0, int(round(self.remaining)))
        h = r // 3600
        m = (r % 3600) // 60
        s = r % 60
        self.var.set(f"{h:02d}:{m:02d}:{s:02d}")

        # Color by remaining fraction
        if self.total_seconds > 0:
            frac = self.remaining / self.total_seconds
            if frac <= 0.10:
                color = COUNTDOWN_COLORS["final"]
            elif frac <= 0.50:
                color = COUNTDOWN_COLORS["mid"]
            else:
                color = COUNTDOWN_COLORS["start"]
        else:
            color = SCHEME["lcd_fg"]
        # Only update if changed or forced
        if force_color or self.lbl.cget("fg") != color:
            self.lbl.configure(fg=color)

    def _tick(self):
        if not self.running:
            return
        self.remaining -= 0.1
        if self.remaining < 0:
            self.remaining = 0

        # Beep for last 10 whole seconds (once per second)
        whole = int(math.ceil(self.remaining))
        if whole <= 10 and whole > 0:
            if self.last_whole_sec != whole:
                beep()
        self.last_whole_sec = whole

        self.update_display()

        if self.remaining <= 0:
            self.running = False
            self.start_btn.configure(text="Start")
            # Final short triple beep
            for _ in range(3):
                beep()
                self.after(120)
            return

        self.job = self.after(100, self._tick)

# =============================================================================
# Main App
# =============================================================================
class TripleTimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Digital Clock • Stopwatch • Countdown")
        self.configure(bg=SCHEME["bg"])
        self.minsize(520, 320)

        # Theming
        self.style = ttk.Style(self)
        # Use 'clam' for consistent ttk theming
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Colors & styles
        self.style.configure("TFrame", background=SCHEME["bg"])
        self.style.configure("Panel.TFrame", background=SCHEME["panel_bg"])
        self.style.configure("TLabel", background=SCHEME["bg"], foreground=SCHEME["fg"])
        self.style.configure("Muted.TLabel", background=SCHEME["bg"], foreground=SCHEME["muted"])
        self.style.configure("TButton", background=SCHEME["button_bg"], foreground=SCHEME["button_fg"])
        self.style.map("TButton",
                       background=[("active", SCHEME["tab_active_bg"])],
                       foreground=[("active", SCHEME["fg"])])

        # Notebook tabs
        self.style.configure("TNotebook", background=SCHEME["tab_bg"])
        self.style.configure("TNotebook.Tab", background=SCHEME["tab_bg"], foreground=SCHEME["tab_fg"])
        self.style.map("TNotebook.Tab",
                       background=[("selected", SCHEME["tab_active_bg"])],
                       foreground=[("selected", SCHEME["tab_fg"])])

        # Attempt LCD-ish font
        lcd_family = try_lcd_font(self)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.clock_tab = ClockTab(nb, lcd_family)
        self.stopwatch_tab = StopwatchTab(nb, lcd_family)
        self.countdown_tab = CountdownTab(nb, lcd_family)

        nb.add(self.clock_tab, text="CLOCK")
        nb.add(self.stopwatch_tab, text="Stopwatch")
        nb.add(self.countdown_tab, text="Countdown Timer")

        # App should default to the CLOCK tab on startup
        nb.select(0)

        # Nice keyboard shortcuts
        self.bind_all("<Control-1>", lambda e: nb.select(0))
        self.bind_all("<Control-2>", lambda e: nb.select(1))
        self.bind_all("<Control-3>", lambda e: nb.select(2))

def main():
    global root
    root = TripleTimerApp()
    # Center the window nicely on first run
    root.update_idletasks()
    w = 720
    h = 420
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = int((sw - w) / 2)
    y = int((sh - h) / 3)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.mainloop()

if __name__ == "__main__":
    main()
