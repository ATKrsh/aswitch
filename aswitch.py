# aswitch.py
# ASwitch — Combined Window Switcher (Left Click) + Browser Tab Switcher (Right Click)
# Always-on-top, translucent floating desktop widget for Windows.

import sys
import os
import io

# Force stdout/stderr to UTF-8 (or dummy if running without console)
class _DummyWriter:
    def write(self, *a, **k): pass
    def flush(self, *a, **k): pass

if sys.stdout is None:
    sys.stdout = _DummyWriter()
else:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = _DummyWriter()
else:
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import faulthandler
try:
    faulthandler.enable()
except Exception:
    pass

import ctypes
try:
    _con = ctypes.windll.kernel32.GetConsoleWindow()
    if _con:
        ctypes.windll.user32.ShowWindow(_con, 0)
except Exception:
    pass

import ctypes.wintypes
import math
import time
import subprocess
import threading
import base64
import winreg
from urllib.parse import urlparse
from urllib.request import urlopen

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QSystemTrayIcon,
                             QMenu, QAction, QSlider, QWidgetAction, QLabel, QHBoxLayout)
from PyQt5.QtCore import (Qt, QPoint, QPointF, QTimer, QPropertyAnimation,
                          QVariantAnimation, QRectF, pyqtSignal)
from PyQt5.QtGui import (QIcon, QPixmap, QCursor, QPainter, QPen, QBrush,
                         QColor, QPainterPath)
from PyQt5.QtWinExtras import QtWin

# =============================================================================
#  Win32 Declarations  (unified from both apps)
# =============================================================================
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32  = ctypes.windll.shell32

# --- Shell / icon extraction ---
shell32.ExtractIconW.argtypes = [ctypes.wintypes.HINSTANCE, ctypes.c_wchar_p, ctypes.c_int]
shell32.ExtractIconW.restype  = ctypes.wintypes.HICON
if hasattr(user32, 'DestroyIcon'):
    user32.DestroyIcon.argtypes = [ctypes.wintypes.HICON]
    user32.DestroyIcon.restype  = ctypes.wintypes.BOOL

# --- Process ---
kernel32.OpenProcess.argtypes  = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
kernel32.OpenProcess.restype   = ctypes.wintypes.HANDLE
kernel32.CloseHandle.argtypes  = [ctypes.wintypes.HANDLE]
kernel32.CloseHandle.restype   = ctypes.c_bool
kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_ulong,
    ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong),
]
kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype  = ctypes.wintypes.HMODULE

# --- Window text / class ---
user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype  = ctypes.c_ulong

IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
IsWindowVisible.restype  = ctypes.wintypes.BOOL

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
GetWindowTextW.restype  = ctypes.c_int

GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
GetWindowTextLengthW.restype  = ctypes.c_int

GetParent = user32.GetParent
GetParent.argtypes = [ctypes.wintypes.HWND]
GetParent.restype  = ctypes.wintypes.HWND

user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype  = ctypes.c_int

# --- Window style (32/64-bit compat) ---
GWL_EXSTYLE      = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED    = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA        = 0x00000002
SW_RESTORE       = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

if hasattr(user32, "GetWindowLongPtrW"):
    GetWindowLongW = user32.GetWindowLongPtrW
    GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    GetWindowLongW.restype  = ctypes.c_ssize_t
    SetWindowLongW = user32.SetWindowLongPtrW
    SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    SetWindowLongW.restype  = ctypes.c_ssize_t
else:
    GetWindowLongW = user32.GetWindowLongW
    GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    GetWindowLongW.restype  = ctypes.c_long
    SetWindowLongW = user32.SetWindowLongW
    SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
    SetWindowLongW.restype  = ctypes.c_long

SetForegroundWindow = user32.SetForegroundWindow
SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
SetForegroundWindow.restype  = ctypes.wintypes.BOOL

ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
ShowWindow.restype  = ctypes.wintypes.BOOL

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.argtypes = []
GetForegroundWindow.restype  = ctypes.wintypes.HWND

IsWindow = user32.IsWindow
IsWindow.argtypes = [ctypes.wintypes.HWND]
IsWindow.restype  = ctypes.wintypes.BOOL

IsIconic = user32.IsIconic
IsIconic.argtypes = [ctypes.wintypes.HWND]
IsIconic.restype  = ctypes.wintypes.BOOL

SetLayeredWindowAttributes = user32.SetLayeredWindowAttributes
SetLayeredWindowAttributes.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.COLORREF,
                                       ctypes.c_byte, ctypes.wintypes.DWORD]
SetLayeredWindowAttributes.restype  = ctypes.wintypes.BOOL

SetWindowPos = user32.SetWindowPos
SetWindowPos.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
SetWindowPos.restype  = ctypes.wintypes.BOOL

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [EnumWindowsProc, ctypes.wintypes.LPARAM]
EnumWindows.restype  = ctypes.wintypes.BOOL

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype  = ctypes.c_uint

user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_ulong, ctypes.c_void_p]
user32.keybd_event.restype  = None

# Key constants for tab switching
VK_CONTROL      = 0x11
VK_SHIFT        = 0x10
VK_TAB          = 0x09
VK_PRIOR        = 0x21  # Page Up
VK_NEXT         = 0x22  # Page Down
KEYEVENTF_KEYUP = 0x0002

# Mouse Hook (for global middle-click in fly mode)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
)

class MouseHook:
    def __init__(self, signal_emitter):
        self.signal_emitter = signal_emitter
        self.hook_id = None
        self._c_callback = HOOKPROC(self._hook_callback)

    def install(self):
        try:
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                                  ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            self.hook_id = user32.SetWindowsHookExW(
                14, self._c_callback, kernel32.GetModuleHandleW(None), 0)
            if self.hook_id:
                print("[Hook] Mouse hook installed.", flush=True)
            else:
                print("[Hook Error] Failed to install mouse hook.", flush=True)
        except Exception as e:
            print(f"[Hook Error] {e}", flush=True)

    def uninstall(self):
        if self.hook_id:
            try:
                user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
                user32.UnhookWindowsHookEx.restype  = ctypes.c_bool
                user32.UnhookWindowsHookEx(self.hook_id)
            except Exception:
                pass
            self.hook_id = None
            print("[Hook] Mouse hook uninstalled.", flush=True)

    def _hook_callback(self, nCode, wParam, lParam):
        try:
            if nCode >= 0 and wParam == 0x0207:   # WM_MBUTTONDOWN
                self.signal_emitter()
        except Exception:
            pass
        try:
            user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            res = user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)
            return res if res is not None else 0
        except Exception:
            return 0

# =============================================================================
#  Window Management Helpers  (from windowswitch)
# =============================================================================
def get_window_title(hwnd):
    length = GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()

def set_window_opacity(hwnd, alpha):
    try:
        style = GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not (style & WS_EX_LAYERED):
            SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
    except Exception as e:
        print(f"[Fade Error] set opacity: {e}")

def restore_window_style(hwnd, original_style):
    try:
        if original_style is not None:
            SetWindowLongW(hwnd, GWL_EXSTYLE, original_style)
            SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception as e:
        print(f"[Fade Error] restore style: {e}")

def pause_video_player(hwnd):
    if not hwnd:
        return
    title = get_window_title(hwnd).lower()
    video_kw = ['vlc', 'movies & tv', 'media player', 'youtube', 'potplayer',
                'kmplayer', 'mpv', 'netflix', 'prime video', 'mplayer']
    if any(kw in title for kw in video_kw):
        print(f"[Media] Pausing: {title}", flush=True)
        INPUT_KEYBOARD = 1
        VK_SPACE = 0x20

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
                        ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
                        ("dwExtraInfo", ctypes.wintypes.ULONG))

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = (("ki", KEYBDINPUT), ("mi", ctypes.c_byte * 28), ("hi", ctypes.c_byte * 32))
            _anonymous_ = ("_input",)
            _fields_ = (("type", ctypes.wintypes.DWORD), ("_input", _INPUT))

        inp_down = INPUT(); inp_down.type = INPUT_KEYBOARD
        inp_down.ki = KEYBDINPUT(wVk=VK_SPACE, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        inp_up = INPUT(); inp_up.type = INPUT_KEYBOARD
        inp_up.ki = KEYBDINPUT(wVk=VK_SPACE, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        arr = (INPUT * 2)(inp_down, inp_up)
        ctypes.windll.user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))
        time.sleep(0.1)

def get_window_icon(hwnd):
    if not hwnd or not IsWindow(hwnd):
        return None
    extracted = None
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if h:
                try:
                    buf = ctypes.create_unicode_buffer(512)
                    size = ctypes.c_ulong(512)
                    if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        hicon = shell32.ExtractIconW(0, buf.value, 0)
                        if hicon and getattr(hicon, 'value', 0) > 1:
                            px = QtWin.fromHICON(hicon)
                            user32.DestroyIcon(hicon)
                            if not px.isNull():
                                extracted = px
                finally:
                    kernel32.CloseHandle(h)
    except Exception:
        pass
    if extracted and not extracted.isNull():
        return extracted
    # Fallback: WM_GETICON
    try:
        if hasattr(user32, 'SendMessageW'):
            SendMessageW = user32.SendMessageW
            SendMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint,
                                     ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
            SendMessageW.restype = ctypes.c_void_p
            for it in (2, 0, 1):
                hicon = SendMessageW(hwnd, 0x007F, it, 0)
                if hicon:
                    px = QtWin.fromHICON(hicon)
                    if not px.isNull():
                        return px
    except Exception:
        pass
    # Fallback: GetClassLong
    try:
        if hasattr(user32, 'GetClassLongPtrW'):
            GCL = user32.GetClassLongPtrW
            GCL.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            GCL.restype  = ctypes.c_void_p
        else:
            GCL = user32.GetClassLongW
            GCL.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            GCL.restype  = ctypes.c_ulong
        for gcl in (-34, -14):
            hicon = GCL(hwnd, gcl)
            if hicon:
                px = QtWin.fromHICON(hicon)
                if not px.isNull():
                    return px
    except Exception:
        pass
    return None

def is_user_application(hwnd):
    if not IsWindow(hwnd) or not IsWindowVisible(hwnd):
        return False
    title = get_window_title(hwnd)
    if not title or GetParent(hwnd):
        return False
    ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW:
        return False
    ignored = ["Program Manager", "Start", "Settings", "Cortana",
               "Windows Shell Experience Host", "Microsoft Text Input Application",
               "ASwitch", "Assistive Window Switcher", "BTab Switcher"]
    if title in ignored:
        return False
    return True

def get_user_windows():
    wins = []
    def cb(hwnd, _lp):
        if is_user_application(hwnd):
            wins.append(hwnd)
        return True
    EnumWindows(EnumWindowsProc(cb), 0)
    return wins

def get_active_window_id():
    hwnd = GetForegroundWindow()
    if hwnd and is_user_application(hwnd):
        return hwnd
    return None

def switch_to_window(wid):
    if IsIconic(wid):
        ShowWindow(wid, SW_RESTORE)
    SetForegroundWindow(wid)
    return True

def is_valid_window(wid):
    return bool(IsWindow(wid))

def toggle_show_desktop():
    try:
        import tempfile
        vbs = os.path.join(tempfile.gettempdir(), "toggle_desktop.vbs")
        if not os.path.exists(vbs):
            with open(vbs, "w") as f:
                f.write('Dim shell\nSet shell = CreateObject("Shell.Application")\nshell.ToggleDesktop\n')
        subprocess.Popen(["wscript.exe", vbs], creationflags=0x08000000)
    except Exception as e:
        print(f"[Toggle Desktop Error] {e}")

def set_run_at_startup(enabled=True):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "ASwitch"
    if getattr(sys, 'frozen', False):
        exe_path = f'"{os.path.abspath(sys.executable)}"'
    else:
        exe_path = f'"{os.path.abspath(sys.executable)}" "{os.path.abspath(sys.argv[0])}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[Startup] Error: {e}", flush=True)
        return False

def is_run_at_startup():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "ASwitch")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False

# =============================================================================
#  Browser Detection  (from btabswitch)
# =============================================================================
BROWSER_CLASSES = {'Chrome_WidgetWin_1', 'MozillaWindowClass', 'IEFrame'}
BROWSER_KEYWORDS = {
    'chrome', 'firefox', 'edge', 'brave', 'opera', 'vivaldi', 'browser',
    'explorer', 'safari', 'arc', 'thorium', 'wolf', 'waterfox', 'maxthon',
    'yandex', 'coccoc', 'whale', 'sidekick', 'slimjet', 'seamonkey', 'avant',
    'tor', 'wave'
}
BROWSER_PROCS = frozenset([
    'chrome.exe', 'firefox.exe', 'msedge.exe', 'brave.exe', 'opera.exe',
    'operagx.exe', 'vivaldi.exe', 'iexplore.exe', 'waterfox.exe',
    'librewolf.exe', 'arc.exe', 'thorium.exe', 'yandex.exe'
])

def _window_class(hwnd):
    try:
        buf = ctypes.create_unicode_buffer(260)
        user32.GetClassNameW(hwnd, buf, 260)
        return buf.value.strip()
    except Exception:
        return ''

def _proc_name(hwnd):
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ''
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ''
        buf  = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(h)
        return os.path.basename(buf.value).lower()
    except Exception:
        return ''

def is_browser(hwnd):
    if not hwnd or not IsWindow(hwnd):
        return False
    proc = _proc_name(hwnd)
    if not proc:
        return False
    if proc in BROWSER_PROCS:
        return True
    cls = _window_class(hwnd)
    if cls in BROWSER_CLASSES and any(kw in proc for kw in BROWSER_KEYWORDS):
        return True
    return False

# =============================================================================
#  Tab Switching Key Simulation  (from btabswitch)
# =============================================================================
def _kpress(vk):  user32.keybd_event(vk, 0, 0, 0)
def _krel(vk):    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

def send_ctrl_pageup():
    _kpress(VK_CONTROL);  time.sleep(0.02)
    _kpress(VK_PRIOR);    time.sleep(0.02)
    _krel(VK_PRIOR);      time.sleep(0.02)
    _krel(VK_CONTROL)

def send_ctrl_pagedown():
    _kpress(VK_CONTROL);  time.sleep(0.02)
    _kpress(VK_NEXT);     time.sleep(0.02)
    _krel(VK_NEXT);       time.sleep(0.02)
    _krel(VK_CONTROL)

# =============================================================================
#  Favicon Manager  (async website favicon fetching via UIAutomation + Google API)
# =============================================================================
class FaviconManager:
    """Fetches website favicons in background threads."""

    def __init__(self):
        self._cache = {}            # domain -> PNG bytes
        self._lock  = threading.Lock()
        self._pending = set()
        # Latest result (read by main thread)
        self._result_domain = None
        self._result_data   = None
        self._result_ready  = False

    def request(self, hwnd):
        """Kick off an async favicon fetch for the browser at *hwnd*."""
        t = threading.Thread(target=self._worker, args=(int(hwnd),), daemon=True)
        t.start()

    def poll_result(self):
        """Main thread: returns (domain, png_bytes) if a new result is ready, else None."""
        with self._lock:
            if self._result_ready:
                self._result_ready = False
                return (self._result_domain, self._result_data)
        return None

    def get_cached(self, domain):
        with self._lock:
            return self._cache.get(domain)

    # ── background worker ────────────────────────────────────────────────────
    def _worker(self, hwnd):
        try:
            raw = self._get_browser_url(hwnd)
            if not raw:
                return
            domain = self._parse_domain(raw)
            if not domain:
                return

            with self._lock:
                if domain in self._cache:
                    self._result_domain = domain
                    self._result_data   = self._cache[domain]
                    self._result_ready  = True
                    return
                if domain in self._pending:
                    return
                self._pending.add(domain)

            try:
                url = f"https://www.google.com/s2/favicons?sz=64&domain={domain}"
                data = urlopen(url, timeout=4).read()
                with self._lock:
                    self._cache[domain] = data
                    self._pending.discard(domain)
                    self._result_domain = domain
                    self._result_data   = data
                    self._result_ready  = True
            except Exception:
                with self._lock:
                    self._pending.discard(domain)
        except Exception:
            pass

    def _parse_domain(self, raw):
        url = raw.strip()
        if not url:
            return None
        if '://' not in url:
            url = 'https://' + url
        try:
            p = urlparse(url)
            d = p.netloc or p.path.split('/')[0]
            d = d.split(':')[0]
            if '.' in d:
                return d
        except Exception:
            pass
        return None

    def _get_browser_url(self, hwnd):
        """Use PowerShell + .NET UIAutomation to read the address bar value."""
        try:
            ps = (
                "$ErrorActionPreference='SilentlyContinue';"
                "Add-Type -AssemblyName UIAutomationClient;"
                f"$r=[System.Windows.Automation.AutomationElement]::FromHandle({hwnd});"
                "$c=New-Object System.Windows.Automation.PropertyCondition("
                "[System.Windows.Automation.AutomationElement]::ControlTypeProperty,"
                "[System.Windows.Automation.ControlType]::Edit);"
                "$all=$r.FindAll([System.Windows.Automation.TreeScope]::Descendants,$c);"
                "$best='';"
                "foreach($e in $all){"
                "try{$n=$e.Current.Name;"
                "$vp=$e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern);"
                "$v=$vp.Current.Value;"
                "if($v){"
                "if($n -match 'address|url|location'){$v;exit}"
                "if(-not $best -and $v -match '[\\w.-]+\\.[a-zA-Z]{2,}'){$best=$v}"
                "}}catch{}};"
                "if($best){$best}"
            )
            r = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                capture_output=True, text=True, timeout=4,
                creationflags=0x08000000   # CREATE_NO_WINDOW
            )
            return r.stdout.strip() if r.stdout else None
        except Exception:
            return None

# =============================================================================
#  Color Utility
# =============================================================================
def lerp_color(c1, c2, t):
    return QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )

# =============================================================================
#  ASwitchButton  —  3-zone circular widget
# =============================================================================
class ASwitchButton(QWidget):
    OUTER_R     = 26
    INNER_R     = 11
    WIDGET_SIZE = 56

    def __init__(self, parent):
        super().__init__(parent)
        self._p = parent
        self.setFixedSize(self.WIDGET_SIZE, self.WIDGET_SIZE)
        self.setCursor(Qt.SizeAllCursor)
        self.setMouseTracking(True)

        self._is_drag   = False
        self._drag_pos  = QPoint()

        self._hover_zone  = None   # None | 'inner' | 'left' | 'right'
        self._lpress_zone = None   # Left-click active press zone
        self._rpress_zone = None   # Right-click active press zone

        # Animated hover values per zone (0.0→1.0)
        self._hover_inner = 0.0
        self._hover_left  = 0.0
        self._hover_right = 0.0

        # Left-click press flash (blue / window mode)
        self._lp_inner = 0.0
        self._lp_left  = 0.0
        self._lp_right = 0.0

        # Right-click press flash (teal / tab mode)
        self._rp_inner = 0.0
        self._rp_left  = 0.0
        self._rp_right = 0.0

        self._pt = 0.0   # pulse phase

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(28)

    def _zone(self, pos):
        cx = cy = self.WIDGET_SIZE / 2
        dx, dy = pos.x() - cx, pos.y() - cy
        r = math.hypot(dx, dy)
        if r <= self.INNER_R:
            return 'inner'
        if r <= self.OUTER_R:
            return 'left' if dx < 0 else 'right'
        return None

    def _tick(self):
        self._pt = (self._pt + 0.062) % (2 * math.pi)

        # Hover targets
        ti = 1.0 if self._hover_zone == 'inner' else 0.0
        tl = 1.0 if self._hover_zone == 'left'  else 0.0
        tr = 1.0 if self._hover_zone == 'right' else 0.0

        self._hover_inner += (ti - self._hover_inner) * 0.15
        self._hover_left  += (tl - self._hover_left)  * 0.15
        self._hover_right += (tr - self._hover_right) * 0.15

        # Left-press decay
        for zone, attr in [('inner', '_lp_inner'), ('left', '_lp_left'), ('right', '_lp_right')]:
            cur = getattr(self, attr)
            if self._lpress_zone == zone:
                setattr(self, attr, 1.0)
            else:
                setattr(self, attr, max(0.0, cur - 0.07))

        # Right-press decay
        for zone, attr in [('inner', '_rp_inner'), ('left', '_rp_left'), ('right', '_rp_right')]:
            cur = getattr(self, attr)
            if self._rpress_zone == zone:
                setattr(self, attr, 1.0)
            else:
                setattr(self, attr, max(0.0, cur - 0.07))

        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _ev):
        try:
            self._paint_impl()
        except Exception as e:
            print(f"[ASwitch] paint error: {e}", flush=True)

    def _paint_impl(self):
        p  = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        S  = self.WIDGET_SIZE
        cx = cy = S / 2.0

        # Base colour palette
        c_base   = QColor(25, 30, 40, 185)
        c_hover  = QColor(40, 50, 65, 217)
        c_lpress = QColor(0, 120, 215, 204)    # Blue  – window mode
        c_rpress = QColor(0, 180, 120, 204)    # Teal  – tab mode

        def zone_col(h, lp, rp):
            c = lerp_color(c_base, c_hover, h)
            c = lerp_color(c, c_lpress, lp)
            c = lerp_color(c, c_rpress, rp)
            return c

        p.setPen(Qt.NoPen)

        # Left half ring
        lc = zone_col(self._hover_left, self._lp_left, self._rp_left)
        p.setBrush(QBrush(lc))
        p.drawPie(QRectF(cx - self.OUTER_R, cy - self.OUTER_R,
                         self.OUTER_R * 2, self.OUTER_R * 2), 90 * 16, 180 * 16)

        # Right half ring
        rc = zone_col(self._hover_right, self._lp_right, self._rp_right)
        p.setBrush(QBrush(rc))
        p.drawPie(QRectF(cx - self.OUTER_R, cy - self.OUTER_R,
                         self.OUTER_R * 2, self.OUTER_R * 2), 270 * 16, 180 * 16)

        # Divider dashes
        div = QPen(QColor(255, 255, 255, 12)); div.setWidthF(1.0); div.setStyle(Qt.DashLine)
        p.setPen(div)
        ie = self.INNER_R + 2.5;  oe = self.OUTER_R - 1.0
        p.drawLine(QPointF(cx, cy - oe), QPointF(cx, cy - ie))
        p.drawLine(QPointF(cx, cy + ie), QPointF(cx, cy + oe))

        # Separator ring
        sp = QPen(QColor(255, 255, 255, 15)); sp.setWidthF(1.0)
        p.setPen(sp); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), self.INNER_R + 2, self.INNER_R + 2)

        # Inner circle
        ic = zone_col(self._hover_inner, self._lp_inner, self._rp_inner)
        p.setBrush(QBrush(ic)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), self.INNER_R, self.INNER_R)

        # Inner icon — favicon when browser active, else window icon
        icon_pm = None
        if self._p.browser_active and self._p.favicon_pixmap:
            icon_pm = self._p.favicon_pixmap
        elif self._p.browser_active and self._p.browser_icon_pixmap:
            icon_pm = self._p.browser_icon_pixmap
        elif self._p.active_icon_pixmap:
            icon_pm = self._p.active_icon_pixmap

        if icon_pm:
            isz = 18
            rx = cx - isz / 2.0; ry = cy - isz / 2.0
            p.drawPixmap(QRectF(rx, ry, isz, isz), icon_pm, QRectF(icon_pm.rect()))

        # Border
        is_locked  = self._p.is_locked
        is_fly     = self._p.is_fly_mode
        oh = max(self._hover_left, self._hover_right, self._hover_inner)
        olp = max(self._lp_left, self._lp_right, self._lp_inner)
        orp = max(self._rp_left, self._rp_right, self._rp_inner)

        if is_locked:
            bc = lerp_color(QColor(255, 165, 0, 153), QColor(255, 165, 0, 217), oh)
        elif is_fly:
            bc = lerp_color(QColor(138, 43, 226, 153), QColor(138, 43, 226, 217), oh)
        else:
            bc = lerp_color(QColor(255, 255, 255, 38), QColor(77, 150, 255, 128), oh)
            bc = lerp_color(bc, QColor(0, 120, 215, 255), olp)
            bc = lerp_color(bc, QColor(0, 230, 150, 255), orp)

        bp = QPen(bc); bp.setWidthF(2.0)
        p.setPen(bp); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), self.OUTER_R, self.OUTER_R)
        p.end()

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            if mods & Qt.AltModifier:
                QApplication.quit(); return
            if mods & Qt.ShiftModifier:
                self._p.toggle_lock(); event.accept(); return
            if mods & Qt.ControlModifier:
                self._p.toggle_fly_mode(); event.accept(); return
            if not self._p.is_locked and not self._p.is_fly_mode:
                self._drag_pos = event.globalPos() - self._p.frameGeometry().topLeft()
                self._is_drag  = False
            self._lpress_zone = self._zone(event.pos())
            self.update()
        elif event.button() == Qt.RightButton:
            self._rpress_zone = self._zone(event.pos())
            self.update()
        elif event.button() == Qt.MiddleButton:
            if self._p.is_fly_mode:
                self._p.quick_switch()
        event.accept()

    def mouseMoveEvent(self, event):
        z = self._zone(event.pos())
        if z != self._hover_zone:
            self._hover_zone = z
            self.update()
        if event.buttons() & Qt.LeftButton and not self._p.is_locked and not self._p.is_fly_mode:
            diff = event.globalPos() - (self._p.frameGeometry().topLeft() + self._drag_pos)
            if diff.manhattanLength() > 5:
                self._is_drag = True
            if self._is_drag:
                self._p.move(event.globalPos() - self._drag_pos)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            pz = self._lpress_zone
            self._lpress_zone = None
            self.update()
            if not self._is_drag:
                mods = event.modifiers()
                if not (mods & (Qt.AltModifier | Qt.ShiftModifier | Qt.ControlModifier)):
                    z = self._zone(event.pos())
                    if z == pz:
                        if z == 'inner':
                            self._p.quick_switch()
                        elif z == 'left':
                            self._p.cycle_left()
                        elif z == 'right':
                            self._p.cycle_right()
            self._is_drag = False
        elif event.button() == Qt.RightButton:
            pz = self._rpress_zone
            self._rpress_zone = None
            self.update()
            z = self._zone(event.pos())
            if z == pz:
                if z == 'inner':
                    self._p.tab_switch()
                elif z == 'left':
                    self._p.tab_cycle_left()
                elif z == 'right':
                    self._p.tab_cycle_right()
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()   # suppress default Qt context menu

    def leaveEvent(self, _ev):
        self._hover_zone = None
        self.update()
# =============================================================================
#  ASwitchWidget  —  main floating window
# =============================================================================
class ASwitchWidget(QWidget):
    middle_click_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.SubWindow | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(56, 56)
        self.setWindowTitle("ASwitch")

        # Embedded icon (from windowswitch)
        icon_data = base64.b64decode("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")
        px = QPixmap(); px.loadFromData(icon_data)
        self.app_icon = QIcon(px)
        self.setWindowIcon(self.app_icon)

        # ── State ─────────────────────────────────────────────────────────────
        self.opacity_pct = 50
        self.size_pct    = 50
        self.setWindowOpacity(self.opacity_pct / 100.0)

        self.is_locked   = False
        self.is_fly_mode = False

        # Window-switch state
        self.active_icon_pixmap = None
        self.current_hwnd  = None
        self.last_hwnd     = None
        self.is_cycling    = False
        self.cycle_list    = []
        self.cycle_index   = 0
        self.last_cycle_time = 0.0

        # Tab-switch state
        self.browser_active      = False
        self.browser_hwnd        = None
        self.browser_icon_pixmap = None
        self.favicon_pixmap      = None
        self._tab_switch_dir     = 1
        self._last_browser_title = ""

        # Favicon
        self._fav_mgr = FaviconManager()

        # ── UI ────────────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = ASwitchButton(self)
        layout.addWidget(self.button)

        # ── Timers ────────────────────────────────────────────────────────────
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(150)

        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(120)

        # Window fade transition
        self.anim_hwnd_out = None;  self.anim_hwnd_in = None
        self.anim_style_out = None; self.anim_style_in = None
        self.window_fade_anim = None

        # Fly mode
        self.saved_position = None
        self.fly_timer = QTimer(self)
        self.fly_timer.timeout.connect(self._update_fly)

        # Drag
        self.drag_position = QPoint()
        self.is_dragging = False

        # Mouse hook (global middle-click for fly mode)
        self.mouse_hook = MouseHook(self.middle_click_signal.emit)
        self.middle_click_signal.connect(self._on_global_middle)
        self.mouse_hook.install()

        # WS_EX_NOACTIVATE
        hwnd = int(self.winId())
        ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
        SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

        # Tray
        self._setup_tray()

    # ── Unified poll (window history + browser detection + favicon) ───────────
    def _poll(self):
        # Reset cycling timeout
        if self.is_cycling and (time.time() - self.last_cycle_time > 2.0):
            self.is_cycling = False
            self.cycle_list = []

        active_id = get_active_window_id()

        # --- Window history ---
        if active_id and active_id != int(self.winId()):
            if active_id != self.current_hwnd:
                self.last_hwnd = self.current_hwnd
                self.current_hwnd = active_id
                self.active_icon_pixmap = get_window_icon(active_id)
                self.button.update()
        elif not active_id:
            if self.active_icon_pixmap is not None:
                self.active_icon_pixmap = None
                self.button.update()

        # --- Browser detection + favicon ---
        fg = GetForegroundWindow()
        if fg and fg != int(self.winId()):
            br = is_browser(fg)
            if br:
                title = get_window_title(fg)
                if fg != self.browser_hwnd or self.browser_icon_pixmap is None:
                    self.browser_hwnd = fg
                    self.browser_icon_pixmap = get_window_icon(fg)
                # Detect tab change via title change → fetch new favicon
                if title != self._last_browser_title:
                    self._last_browser_title = title
                    self._fav_mgr.request(fg)
            if br != self.browser_active:
                self.browser_active = br
                self.button.update()
        else:
            if self.browser_active:
                self.browser_active = False
                self.button.update()

        # --- Pick up async favicon results ---
        res = self._fav_mgr.poll_result()
        if res:
            _dom, data = res
            if data:
                pm = QPixmap()
                pm.loadFromData(data)
                if not pm.isNull():
                    self.favicon_pixmap = pm
                    self.button.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  LEFT-CLICK: Window switching  (from windowswitch)
    # ══════════════════════════════════════════════════════════════════════════
    def quick_switch(self):
        if self.is_dragging:
            return
        user_wins = get_user_windows()
        if len(user_wins) <= 1:
            if len(user_wins) == 1:
                t = user_wins[0]
                if IsIconic(t):
                    switch_to_window(t)
                else:
                    toggle_show_desktop()
            else:
                toggle_show_desktop()
            return
        if self.last_hwnd and is_valid_window(self.last_hwnd):
            h_out = self.current_hwnd
            h_in  = self.last_hwnd
            if h_out == h_in:
                return
            print(f"[Window] Switch → '{get_window_title(h_in)}'", flush=True)
            self._start_window_fade(h_out, h_in)
        else:
            print("[Window] No valid last window.", flush=True)

    def cycle_left(self):
        self._do_cycle(-1)

    def cycle_right(self):
        self._do_cycle(1)

    def _do_cycle(self, direction):
        now = time.time()
        if not self.is_cycling or not self.cycle_list or (now - self.last_cycle_time > 2.0):
            self.is_cycling = True
            self.cycle_list = get_user_windows()
            fg = get_active_window_id()
            self.cycle_index = self.cycle_list.index(fg) if fg in self.cycle_list else 0
        if not self.cycle_list:
            self.is_cycling = False
            return
        self.cycle_index = (self.cycle_index + direction) % len(self.cycle_list)
        target = self.cycle_list[self.cycle_index]
        if is_valid_window(target):
            hwnd_out = get_active_window_id()
            if hwnd_out and hwnd_out != target:
                pause_video_player(hwnd_out)
                self._start_window_fade(hwnd_out, target)
            else:
                switch_to_window(target)
        self.last_cycle_time = now

    def _start_window_fade(self, h_out, h_in):
        if self.window_fade_anim and self.window_fade_anim.state() == QVariantAnimation.Running:
            self.window_fade_anim.stop()
            self._on_fade_done()
        self.anim_hwnd_out = h_out;  self.anim_hwnd_in = h_in
        self.anim_style_out = None
        self.anim_style_in = GetWindowLongW(h_in, GWL_EXSTYLE) if h_in and IsWindow(h_in) else None
        if self.anim_hwnd_in and IsWindow(self.anim_hwnd_in):
            if IsIconic(self.anim_hwnd_in):
                ShowWindow(self.anim_hwnd_in, SW_RESTORE)
            set_window_opacity(self.anim_hwnd_in, 0)
            SetForegroundWindow(self.anim_hwnd_in)
        self.window_fade_anim = QVariantAnimation(self)
        self.window_fade_anim.setDuration(120)
        self.window_fade_anim.setStartValue(0.0)
        self.window_fade_anim.setEndValue(1.0)
        self.window_fade_anim.valueChanged.connect(self._on_fade_step)
        self.window_fade_anim.finished.connect(self._on_fade_done)
        self.window_fade_anim.start()

    def _on_fade_step(self, v):
        if self.anim_hwnd_in and IsWindow(self.anim_hwnd_in):
            set_window_opacity(self.anim_hwnd_in, int(v * 255))

    def _on_fade_done(self):
        if self.anim_hwnd_in and IsWindow(self.anim_hwnd_in):
            restore_window_style(self.anim_hwnd_in, self.anim_style_in)
        self.anim_hwnd_out = self.anim_hwnd_in = None
        self.anim_style_out = self.anim_style_in = None

    # ══════════════════════════════════════════════════════════════════════════
    #  RIGHT-CLICK: Browser tab switching  (from btabswitch)
    # ══════════════════════════════════════════════════════════════════════════
    def _focus_browser(self):
        h = self.browser_hwnd
        if h and IsWindow(h):
            if IsIconic(h):
                ShowWindow(h, SW_RESTORE)
            SetForegroundWindow(h)
            time.sleep(0.05)

    def tab_switch(self):
        self._focus_browser()
        if self._tab_switch_dir == 1:
            print("[Tab] Switch → Ctrl+PageUp", flush=True)
            send_ctrl_pageup()
            self._tab_switch_dir = -1
        else:
            print("[Tab] Switch → Ctrl+PageDown", flush=True)
            send_ctrl_pagedown()
            self._tab_switch_dir = 1

    def tab_cycle_left(self):
        print("[Tab] Cycle ←", flush=True)
        self._focus_browser()
        send_ctrl_pageup()
        self._tab_switch_dir = -1

    def tab_cycle_right(self):
        print("[Tab] Cycle →", flush=True)
        self._focus_browser()
        send_ctrl_pagedown()
        self._tab_switch_dir = 1

    # ══════════════════════════════════════════════════════════════════════════
    #  Shared: opacity, drag, tray, lock, fly mode, startup
    # ══════════════════════════════════════════════════════════════════════════
    def _fade_to(self, target):
        self.fade_animation.stop()
        self.fade_animation.setStartValue(self.windowOpacity())
        self.fade_animation.setEndValue(target)
        self.fade_animation.start()

    def enterEvent(self, e):
        self._fade_to(min(1.0, self.opacity_pct / 100.0 + 0.40))
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._fade_to(self.opacity_pct / 100.0)
        super().leaveEvent(e)

    # ── Drag fallback ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            if mods & Qt.AltModifier:
                QApplication.quit(); return
            if mods & Qt.ShiftModifier:
                self.toggle_lock(); event.accept(); return
            if mods & Qt.ControlModifier:
                self.toggle_fly_mode(); event.accept(); return
            if not self.is_locked and not self.is_fly_mode:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_dragging = False
            event.accept()
        elif event.button() == Qt.MiddleButton:
            if self.is_fly_mode:
                self.quick_switch(); event.accept(); return
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.is_locked and not self.is_fly_mode:
            diff = event.globalPos() - (self.frameGeometry().topLeft() + self.drag_position)
            if diff.manhattanLength() > 5:
                self.is_dragging = True
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_dragging:
                self.is_dragging = False
            else:
                mods = event.modifiers()
                if not (mods & (Qt.AltModifier | Qt.ShiftModifier | Qt.ControlModifier)):
                    self.quick_switch()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ── Fly mode ──────────────────────────────────────────────────────────────
    def toggle_fly_mode(self):
        if self.is_locked:
            self.tray_icon.showMessage("ASwitch", "Unlock position first.",
                                       QSystemTrayIcon.Warning, 2000)
            return
        self.is_fly_mode = not self.is_fly_mode
        if self.is_fly_mode:
            self.saved_position = self.pos()
            self.fly_timer.start(16)
            self.tray_icon.showMessage("ASwitch", "Fly mode ON — middle-click to switch windows.",
                                       QSystemTrayIcon.Information, 2000)
        else:
            self.fly_timer.stop()
            if self.saved_position:
                self.move(self.saved_position)
            self.tray_icon.showMessage("ASwitch", "Fly mode OFF.",
                                       QSystemTrayIcon.Information, 2000)
        self._update_tooltip()

    def _update_fly(self):
        pos = QCursor.pos()
        tx = pos.x() + 20;  ty = pos.y() + 20
        scr = QApplication.primaryScreen().geometry()
        if tx + self.width() > scr.right():
            tx = pos.x() - self.width() - 20
        if ty + self.height() > scr.bottom():
            ty = pos.y() - self.height() - 20
        self.move(tx, ty)

    def _on_global_middle(self):
        if self.is_fly_mode and self.isVisible():
            self.quick_switch()

    # ── Lock ──────────────────────────────────────────────────────────────────
    def toggle_lock(self):
        if self.is_fly_mode:
            self.is_fly_mode = False
            self.fly_timer.stop()
            if self.saved_position:
                self.move(self.saved_position)
        self.is_locked = not self.is_locked
        s = "locked" if self.is_locked else "unlocked"
        self.button.setCursor(Qt.ArrowCursor if self.is_locked else Qt.SizeAllCursor)
        self.tray_icon.showMessage("ASwitch", f"Position {s}.",
                                   QSystemTrayIcon.Information, 2000)
        self._update_tooltip()
        self.button.update()

    def _update_tooltip(self):
        if self.is_locked:
            tip = "ASwitch (LOCKED)\nShift+Click to unlock"
        elif self.is_fly_mode:
            tip = "ASwitch (FLY MODE)\nMiddle-click: switch windows\nCtrl+Click: exit fly mode"
        else:
            tip = ("ASwitch\n"
                   "Left-click: Switch windows\n"
                   "Right-click: Switch browser tabs\n"
                   "Drag: move | Alt+Click: quit\n"
                   "Shift+Click: lock | Ctrl+Click: fly")
        self.button.setToolTip(tip)

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.app_icon)
        self.tray_icon.setToolTip("ASwitch")

        SLIDER_SS = """
            QSlider::groove:horizontal { height:4px; background:#374151; border-radius:2px; }
            QSlider::sub-page:horizontal { background:#00d2ff; border-radius:2px; }
            QSlider::handle:horizontal { background:#fff; width:12px; height:12px;
                                         margin:-4px 0; border-radius:6px; }
        """
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet("""
            QMenu { background-color:#1e222b; color:#e1e4ea; border:1px solid #3a4253;
                    border-radius:8px; padding:6px; font-family:'Segoe UI',sans-serif; font-size:13px; }
            QMenu::item { padding:6px 24px 6px 12px; border-radius:4px; }
            QMenu::item:selected { background-color:#2c3444; color:#00d2ff; }
            QMenu::separator { height:1px; background:#3a4253; margin:4px 6px; }
        """)

        self.action_ontop = QAction("Always on Top", self)
        self.action_ontop.setCheckable(True)
        self.action_ontop.setChecked(True)
        self.action_ontop.triggered.connect(self._toggle_ontop)
        self.tray_menu.addAction(self.action_ontop)

        self.action_lock = QAction("Lock Position", self)
        self.action_lock.setCheckable(True)
        self.action_lock.setChecked(False)
        self.action_lock.triggered.connect(lambda: self.toggle_lock())
        self.tray_menu.addAction(self.action_lock)

        self.action_fly = QAction("Fly Mode (Follow Cursor)", self)
        self.action_fly.setCheckable(True)
        self.action_fly.setChecked(False)
        self.action_fly.triggered.connect(lambda: self.toggle_fly_mode())
        self.tray_menu.addAction(self.action_fly)

        self.startup_action = QAction("Start with Windows", self)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_run_at_startup())
        self.startup_action.triggered.connect(self._toggle_startup)
        self.tray_menu.addAction(self.startup_action)

        self.tray_menu.addSeparator()

        # Opacity slider
        oc = QWidget()
        ol = QHBoxLayout(oc); ol.setContentsMargins(12, 4, 12, 4)
        ol.addWidget(self._lbl("App Opacity:", "#d1d5db"))
        self.op_slider = QSlider(Qt.Horizontal); self.op_slider.setRange(0, 100)
        self.op_slider.setValue(self.opacity_pct); self.op_slider.setFixedWidth(100)
        self.op_slider.setStyleSheet(SLIDER_SS)
        self.op_slider.valueChanged.connect(self._on_opacity)
        ol.addWidget(self.op_slider)
        self.op_val = self._lbl(f"{self.opacity_pct}%", "#00d2ff")
        ol.addWidget(self.op_val)
        ow = QWidgetAction(self); ow.setDefaultWidget(oc); self.tray_menu.addAction(ow)

        # Size slider
        sc = QWidget()
        sl = QHBoxLayout(sc); sl.setContentsMargins(12, 4, 12, 4)
        sl.addWidget(self._lbl("Size:", "#d1d5db"))
        self.sz_slider = QSlider(Qt.Horizontal); self.sz_slider.setRange(0, 100)
        self.sz_slider.setValue(self.size_pct); self.sz_slider.setFixedWidth(100)
        self.sz_slider.setStyleSheet(SLIDER_SS)
        self.sz_slider.valueChanged.connect(self._on_size)
        sl.addWidget(self.sz_slider)
        self.sz_val = self._lbl(f"{self.size_pct}%", "#00d2ff")
        sl.addWidget(self.sz_val)
        sw = QWidgetAction(self); sw.setDefaultWidget(sc); self.tray_menu.addAction(sw)

        self.tray_menu.addSeparator()

        # Help hints
        for t in ("● Inner  — L: Switch window  R: Switch tab",
                  "◀ Left   — L: Prev window    R: Prev tab",
                  "▶ Right  — L: Next window    R: Next tab"):
            a = QAction(t, self); a.setEnabled(False); self.tray_menu.addAction(a)

        self.tray_menu.addSeparator()
        qa = QAction("Quit ASwitch", self)
        qa.triggered.connect(QApplication.quit)
        self.tray_menu.addAction(qa)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray)
        self.tray_icon.show()

        self._update_tooltip()

    def _lbl(self, text, color):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")
        return l

    def _toggle_ontop(self, checked):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.SubWindow | Qt.WindowDoesNotAcceptFocus
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _on_opacity(self, v):
        self.opacity_pct = v
        self.op_val.setText(f"{v}%")
        self.setWindowOpacity(v / 100.0)

    def _on_size(self, v):
        self.size_pct = v
        self.sz_val.setText(f"{v}%")
        ns = int(32 + 56 * (v / 100.0))
        self.button.OUTER_R = max(10, int(ns * 0.464))
        self.button.INNER_R = max(4, int(ns * 0.196))
        self.button.WIDGET_SIZE = ns
        self.button.setFixedSize(ns, ns)
        self.setFixedSize(ns, ns)
        self.button.update()

    def _toggle_startup(self, checked):
        if not set_run_at_startup(checked):
            self.startup_action.setChecked(not checked)

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show(); self.raise_()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self.mouse_hook:
            self.mouse_hook.uninstall()
        super().closeEvent(event)

    def __del__(self):
        if hasattr(self, "mouse_hook") and self.mouse_hook:
            try:
                self.mouse_hook.uninstall()
            except Exception:
                pass

# =============================================================================
#  Entry Point
# =============================================================================
if __name__ == "__main__":
    log_path = os.path.join(os.path.expanduser("~"), "aswitch_error.log")
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        w = ASwitchWidget()
        scr = QApplication.primaryScreen().geometry()
        w.move(scr.width() - 80, scr.height() - 180)
        w.show()

        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        with open(log_path, "w") as f:
            f.write(traceback.format_exc())
        raise e
