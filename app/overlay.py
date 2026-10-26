"""The floating recording indicator (Tk, so it never takes focus).

Styles: 'pill' (bottom centre), 'capsule' (slim, top centre), 'dot' (small, bottom centre, no text)
and 'off'. While recording, the pill and capsule widen to show the live transcript.
"""
import ctypes
import time
import tkinter as tk
import tkinter.font as tkfont

TRANSPARENT = "#ff00fe"
ACCENT = "#ef7b45"
BG = "#16161b"


class Overlay:
    def __init__(self, root):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=TRANSPARENT)
        self.top.attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.top, width=10, height=10, bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.top.geometry("10x10+-3000+-3000")
        self.top.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x80)  # NOACTIVATE | TOOLWINDOW
        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.small = tkfont.Font(family="Segoe UI", size=9)
        self.bold = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.style = "pill"
        self.levels = [0.0] * 14
        self.visible = False
        self.hide_at = None
        self.text, self.mode, self.live, self.label = "", "rec", "", ""
        self.size = (0, 0)

    # public ------------------------------------------------------------------------
    def show(self, text, mode="rec", hide_after=None, label=""):
        """mode: 'rec' (level meter + live text), 'busy' (animated dots) or 'info'."""
        if self.style == "off" and mode == "rec":
            return
        self.visible, self.text, self.mode = True, text, mode
        self.hide_at = time.time() + hide_after if hide_after else None
        if mode == "rec":
            self.levels = [0.0] * len(self.levels)
            self.live, self.label = "", label
        self.draw()

    def set_live(self, text):
        self.live = text
        if self.visible and self.mode == "rec":
            self.draw()

    def hide(self):
        self.visible = False
        self.size = (0, 0)
        self.top.geometry("10x10+-3000+-3000")

    def tick(self, level):
        if not self.visible:
            return
        if self.hide_at and time.time() > self.hide_at:
            self.hide()
            return
        if self.mode == "rec":
            self.levels = self.levels[1:] + [min(1.0, level * 12)]
        self.draw()

    # drawing -----------------------------------------------------------------------
    def _place(self, w, h):
        if (w, h) != self.size:
            self.size = (w, h)
            self.canvas.config(width=w, height=h)
            sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
            y = 14 if self.style == "capsule" else sh - h - 96
            self.top.geometry(f"{w}x{h}+{(sw - w) // 2}+{y}")
            self.top.lift()

    def _pill(self, w, h):
        c = self.canvas
        c.delete("all")
        c.create_oval(0, 0, h, h, fill=BG, outline=BG)
        c.create_oval(w - h, 0, w, h, fill=BG, outline=BG)
        c.create_rectangle(h // 2, 0, w - h // 2, h, fill=BG, outline=BG)

    def draw(self):
        c = self.canvas
        if self.style == "dot":
            self._draw_dot()
            return
        h = 34 if self.style == "capsule" else 46
        if self.mode != "rec":
            label = self.text + ("." * (int(time.time() * 3) % 4) if self.mode == "busy" else "")
            w = max(170, self.bold.measure(self.text + "...") + 48)
            self._place(w, h)
            self._pill(w, h)
            c.create_text(w / 2, h / 2, text=label, fill=ACCENT if self.mode == "busy" else "#f0f0f0", font=self.bold)
            return
        n = len(self.levels)
        bars_w = n * 6
        live = self.live.strip()
        w = 560 if live else 92 + bars_w + (self.small.measure(self.label or "esc") + 10)
        self._place(w, h)
        self._pill(w, h)
        pulse = 0.5 + 0.5 * abs((time.time() * 1.6) % 2 - 1)
        r = (4 if h < 40 else 5) + 2 * pulse
        cx = h / 2 + 4
        c.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r, fill="#ff4d4f", outline="")
        x0 = cx + 16
        for i, v in enumerate(self.levels):
            x = x0 + i * 6
            bh = 3 + v * (h - 18)
            c.create_rectangle(x, h / 2 - bh / 2, x + 3, h / 2 + bh / 2, fill="#ffffff" if v > 0.05 else "#55555f", outline="")
        if live:
            room = w - (x0 + bars_w + 14) - h / 2
            shown = live
            while shown and self.font.measure(shown) > room:  # keep the newest words visible
                shown = shown[1:]
            if shown != live:
                shown = "…" + shown.lstrip()
            c.create_text(x0 + bars_w + 14, h / 2, text=shown, fill="#f0f0f0", font=self.font, anchor="w")
        else:
            c.create_text(w - h / 2 + 2, h / 2, text=self.label or "esc", fill=ACCENT if self.label else "#8a8a96",
                          font=self.small, anchor="e")

    def _draw_dot(self):
        c, s = self.canvas, 40
        self._place(s, s)
        c.delete("all")
        c.create_oval(0, 0, s, s, fill=BG, outline=BG)
        if self.mode == "rec":
            level = max(self.levels[-3:])
            r = 6 + 7 * min(1.0, level)
            c.create_oval(s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r, fill="#ff4d4f", outline="")
        else:  # busy / info: a small spinning arc
            a = (time.time() * 360) % 360
            c.create_arc(9, 9, s - 9, s - 9, start=a, extent=270, style="arc", outline=ACCENT, width=3)
            if self.mode == "info":
                self.hide_at = self.hide_at or time.time() + 1
