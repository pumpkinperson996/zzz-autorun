import asyncio
import ctypes
import ctypes.wintypes
import struct

import win32gui
import win32process
import mss
from PIL import Image

from winrt.windows.media.ocr import OcrEngine
from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
from winrt.windows.security.cryptography import CryptographicBuffer

KEYWORD = "其他地方登录"  # 其他地方登录
GAME_EXE = "ZenlessZoneZero.exe"

TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              ctypes.c_uint32),
        ("cntUsage",            ctypes.c_uint32),
        ("th32ProcessID",       ctypes.c_uint32),
        ("th32DefaultHeapID",   ctypes.c_size_t),
        ("th32ModuleID",        ctypes.c_uint32),
        ("cntThreads",          ctypes.c_uint32),
        ("th32ParentProcessID", ctypes.c_uint32),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             ctypes.c_uint32),
        ("szExeFile",           ctypes.c_char * 260),
    ]


def find_game_pid(exe_name: str):
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pid = None
    try:
        if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(entry)):
            while True:
                if exe_name.lower().encode() in entry.szExeFile.lower():
                    pid = entry.th32ProcessID
                    break
                if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(entry)):
                    break
    finally:
        ctypes.windll.kernel32.CloseHandle(snap)
    return pid


def find_hwnd_by_pid(pid: int):
    result = [None]
    def cb(hwnd, _):
        if result[0]:
            return
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid and win32gui.IsWindowVisible(hwnd):
                result[0] = hwnd
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    return result[0]


def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None
    with mss.MSS() as sct:
        region = {"left": left, "top": top, "width": w, "height": h}
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


async def ocr_image(img: Image.Image) -> str:
    img_bgra = img.convert("RGBA")
    r, g, b, a = img_bgra.split()
    img_bgra = Image.merge("RGBA", (b, g, r, a))
    pixel_bytes = img_bgra.tobytes()

    buf = CryptographicBuffer.create_from_byte_array(pixel_bytes)
    soft_bmp = SoftwareBitmap.create_copy_from_buffer(
        buf, BitmapPixelFormat.BGRA8, img.width, img.height)

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return "NO_ENGINE"

    result = await engine.recognize_async(soft_bmp)
    return result.text.replace(" ", "")


async def main() -> str:
    pid = find_game_pid(GAME_EXE)
    if not pid:
        return "NO_GAME"

    hwnd = find_hwnd_by_pid(pid)
    if not hwnd:
        return "NO_GAME"

    img = capture_window(hwnd)
    if img is None:
        return "NO_GAME"

    text = await ocr_image(img)
    return "FOUND" if KEYWORD in text else "NOT_FOUND"


if __name__ == "__main__":
    import sys
    out_file = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        result = asyncio.run(main())
    except Exception as e:
        result = f"ERROR: {e}"
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        print(result)
