import asyncio
import threading
import tkinter as tk
from tkinter import scrolledtext
import sys

sys.path.insert(0, r"C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\Lib\site-packages")
sys.path.insert(0, r"C:\ZZZ-OD\ZZZ-autorun\scripts")
from ocrcheck import find_game_pid, find_hwnd_by_pid, capture_window, ocr_image, KEYWORD, GAME_EXE

INTERVAL_MS = 1500


class OcrTestApp:
    def __init__(self, root):
        self.root = root
        root.title("OCR Test")
        root.geometry("620x420")

        self.status_var = tk.StringVar(value="Waiting...")
        self.status_lbl = tk.Label(root, textvariable=self.status_var,
                                   font=("Arial", 16, "bold"), fg="gray")
        self.status_lbl.pack(pady=10)

        self.text_box = scrolledtext.ScrolledText(root, wrap=tk.WORD,
                                                  font=("Consolas", 9), height=16)
        self.text_box.pack(fill=tk.BOTH, expand=True, padx=10)

        btn = tk.Button(root, text="Scan Now", command=self.trigger_scan)
        btn.pack(pady=8)

        self._scanning = False
        self.schedule_scan()

    def log(self, msg):
        self.text_box.insert(tk.END, msg + "\n")
        self.text_box.see(tk.END)

    def trigger_scan(self):
        if not self._scanning:
            threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        self._scanning = True
        try:
            pid = find_game_pid(GAME_EXE)
            if not pid:
                self.root.after(0, self._update, "NO_GAME", "gray", "[NO_GAME]")
                return

            hwnd = find_hwnd_by_pid(pid)
            if not hwnd:
                self.root.after(0, self._update, "NO_GAME", "gray", "[NO_HWND]")
                return

            img = capture_window(hwnd)
            if img is None:
                self.root.after(0, self._update, "NO_GAME", "gray", "[NO_IMG]")
                return

            text = asyncio.run(ocr_image(img))
            preview = text[:100] + ("..." if len(text) > 100 else "")

            if KEYWORD in text:
                self.root.after(0, self._update, "FOUND", "green",
                                f"[FOUND] {preview}")
            else:
                self.root.after(0, self._update, "NOT_FOUND", "black",
                                f"[NOT_FOUND] {preview}")
        except Exception as e:
            self.root.after(0, self._update, "ERROR", "red", f"[ERROR] {e}")
        finally:
            self._scanning = False

    def _update(self, status, color, log_msg):
        self.status_var.set(status)
        self.status_lbl.config(fg=color)
        self.log(log_msg)

    def schedule_scan(self):
        self.trigger_scan()
        self.root.after(INTERVAL_MS, self.schedule_scan)


if __name__ == "__main__":
    root = tk.Tk()
    app = OcrTestApp(root)
    root.mainloop()
