"""Mini floating widget: a small always-on-top Parlo button. Click to start/stop dictation, drag to
move, right-click for a menu. It never takes keyboard focus, so the words still go to the app you
were typing in."""
import ctypes
import tkinter as tk

from PIL import Image, ImageTk

from icon import make_icon

KEY = "#ff00fe"  # transparent colour around the rounded tile
SIZE = 54


def _tile(recording):
    img = make_icon(SIZE, recording=recording)
    flat = Image.new("RGBA", img.size, KEY)
    alpha = img.split()[3].point(lambda a: 255 if a > 110 else 0)  # hard edge against the key colour
    flat.paste(img, (0, 0), alpha)
    return ImageTk.PhotoImage(flat.convert("RGB"))


class Widget:
    def __init__(self, root, pos, on_click, on_open, on_hide, on_moved):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=KEY)
        self.top.attributes("-transparentcolor", KEY)
        self.images = {False: _tile(False), True: _tile(True)}
        self.label = tk.Label(self.top, image=self.images[False], bg=KEY, bd=0, cursor="hand2")
        self.label.pack()
        sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        x, y = pos if pos else (sw - SIZE - 28, sh - SIZE - 120)
        self.top.geometry(f"{SIZE}x{SIZE}+{int(x)}+{int(y)}")
        self.top.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x80)  # NOACTIVATE | TOOLWINDOW
        self.on_click, self.on_moved = on_click, on_moved
        self.menu = tk.Menu(self.top, tearoff=0)
        self.menu.add_command(label="Open Parlo", command=on_open)
        self.menu.add_command(label="Hide widget", command=on_hide)
        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._drag)
        self.label.bind("<ButtonRelease-1>", self._release)
        self.label.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self.start = None
        self.moved = False
        self.recording = False

    def _press(self, e):
        self.start = (e.x_root, e.y_root, self.top.winfo_x(), self.top.winfo_y())
        self.moved = False

    def _drag(self, e):
        if not self.start:
            return
        dx, dy = e.x_root - self.start[0], e.y_root - self.start[1]
        if abs(dx) + abs(dy) > 4:
            self.moved = True
        if self.moved:
            self.top.geometry(f"+{self.start[2] + dx}+{self.start[3] + dy}")

    def _release(self, e):
        if self.moved:
            self.on_moved(self.top.winfo_x(), self.top.winfo_y())
        else:
            self.on_click()
        self.start = None

    def set_state(self, state):
        recording = state == "recording"
        if recording != self.recording:
            self.recording = recording
            self.label.configure(image=self.images[recording])

    def destroy(self):
        self.top.destroy()
