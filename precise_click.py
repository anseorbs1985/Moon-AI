"""
precise_click.py — 사용자가 마우스를 움직여도 클릭이 항상 지정 좌표에 찍히게 하는 공용 패치.

pyautogui.click / moveTo / mouseDown / mouseUp 을 SendInput 기반으로 교체한다.
SendInput 은 '한 번의 호출에 담긴 이벤트들 사이에 물리 마우스나 다른 프로그램의
입력이 끼어들지 않음'을 Windows 가 보장하므로(문서 명시), [이동+누름+뗌]을 한 번에
보내면 실행 중 사용자가 마우스를 움직여도 클릭은 지정 좌표에 정확히 찍힌다.
(기존 BlockInput 방식은 관리자 권한이 아니면 조용히 실패해 경합이 남아 있었음)
"""
import ctypes
import ctypes.wintypes
import time

_MOVE   = 0x0001
_LDOWN  = 0x0002
_LUP    = 0x0004
_ABS    = 0x8000
_VDESK  = 0x4000


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


def _abs_xy(x, y):
    """가상 데스크톱(모니터 전체) 기준 0~65535 정규화 좌표."""
    u = ctypes.windll.user32
    vx = u.GetSystemMetrics(76); vy = u.GetSystemMetrics(77)
    vw = u.GetSystemMetrics(78) or 1; vh = u.GetSystemMetrics(79) or 1
    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    return nx, ny


def _send(x, y, btn_flags):
    """btn_flags 의 각 이벤트를 지정 좌표 고정(이동+절대좌표)으로 한 번에 전송."""
    u = ctypes.windll.user32
    nx, ny = _abs_xy(int(x), int(y))
    n = len(btn_flags)
    arr = (_INPUT * n)()
    for i, fl in enumerate(btn_flags):
        arr[i].type = 0                      # INPUT_MOUSE
        arr[i].mi.dx = nx; arr[i].mi.dy = ny
        arr[i].mi.mouseData = 0
        arr[i].mi.dwFlags = _MOVE | _ABS | _VDESK | fl
        arr[i].mi.time = 0; arr[i].mi.dwExtraInfo = 0
    return u.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT)) == n


def install(pyautogui):
    """pyautogui 의 click/moveTo/mouseDown/mouseUp 을 정밀 버전으로 교체."""
    orig_click = pyautogui.click
    orig_move  = pyautogui.moveTo
    orig_down  = pyautogui.mouseDown
    orig_up    = pyautogui.mouseUp
    last_move  = [None]   # 최근 moveTo 타깃 — 좌표 없는 click() 이 이 지점을 찍음

    def click(x=None, y=None, *a, **kw):
        try:
            if x is None or y is None:
                if last_move[0] is not None:
                    x, y = last_move[0]
                else:
                    pt = ctypes.wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                    x, y = pt.x, pt.y
            if _send(x, y, [0, _LDOWN, _LUP]):
                time.sleep(0.02)
                return
        except Exception:
            pass
        return orig_click(x, y, *a, **kw)

    def moveTo(x=None, y=None, *a, **kw):
        try:
            if x is not None and y is not None:
                last_move[0] = (int(x), int(y))
                if not kw.get("duration") and _send(x, y, [0]):
                    return
        except Exception:
            pass
        return orig_move(x, y, *a, **kw)

    def mouseDown(x=None, y=None, *a, **kw):
        try:
            if x is not None and y is not None and _send(x, y, [0, _LDOWN]):
                return
        except Exception:
            pass
        return orig_down(x, y, *a, **kw)

    def mouseUp(x=None, y=None, *a, **kw):
        try:
            if x is not None and y is not None and _send(x, y, [0, _LUP]):
                return
        except Exception:
            pass
        return orig_up(x, y, *a, **kw)

    pyautogui.click = click
    pyautogui.moveTo = moveTo
    pyautogui.mouseDown = mouseDown
    pyautogui.mouseUp = mouseUp
