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
import random

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

# ── 커서를 전혀 움직이지 않는 클릭 (창에 메시지로 직접 전달) ──────────────
# 사용자가 마우스를 쓰는 동안에도 겹치지 않는다. 다만 게임이 이런 '가짜 입력'을
# 받아주는지는 프로그램마다 달라서, 반드시 먼저 테스트해보고 써야 한다.
# 게임 쪽 창의 클래스 — 클라이언트 본체(GLFW30)뿐 아니라 그 위의 상단바(ngptop)와
# 옆의 이벤트 패널(CEFCLIENT)도 '눌러야 하는 창'이다. 스케줄 클릭1(상단바)·
# 클릭2(옆 패널)가 여기에 해당해서, 이걸 빼면 런처·클로드 창에 가려 클릭이 씹힌다.
GAME_CLASSES = ("GLFW30", "CEFCLIENT")


def _win_class(h):
    try:
        b = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(h, b, 256)
        return b.value
    except Exception:
        return ""


def is_game_window(h):
    """게임(클라이언트·상단바·옆 패널) 창이면 True. 런처·클로드 창은 False."""
    u = ctypes.windll.user32
    cls = _win_class(h)
    if cls in GAME_CLASSES:
        return True
    n = u.GetWindowTextLengthW(h)
    if not n:
        return False
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    t = buf.value
    # '리니지M 자동 실행'(런처 Tk 창)은 넓은 영역을 덮고 있어 클릭을 삼킨다 → 제외
    return t.startswith("리니지M") and "자동 실행" not in t


def game_window_at(x, y):
    """그 좌표를 품고 있는 게임 창 핸들 — 다른 창이 위에 덮여 있어도 찾아낸다.
    (WindowFromPoint 는 '맨 위 창'을 주기 때문에, 런처·클로드 창이 가리면
     클릭이 엉뚱한 창으로 가서 게임이 못 받는다 → 씹힘의 주된 원인)"""
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(h, _):
        try:
            if not u.IsWindowVisible(h) or u.IsIconic(h):
                return True
            if not is_game_window(h):
                return True
            r = ctypes.wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.left <= x < r.right and r.top <= y < r.bottom:
                found.append(h)
        except Exception:
            pass
        return True

    try:
        u.EnumWindows(_cb, 0)          # 위(앞)에서 아래 순서 — 첫 번째가 맨 위 게임 창
    except Exception:
        return None
    return found[0] if found else None


LAST = {}      # 마지막으로 신호를 보낸 창 (진단용 — 런처가 기록에 적는다)


def window_title(h):
    """창 제목 (없으면 빈 문자열)."""
    try:
        u = ctypes.windll.user32
        n = u.GetWindowTextLengthW(h)
        if not n:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _target_hwnd(x, y):
    """클릭을 보낼 창 — 그 자리의 리니지M 창을 우선한다.
    어느 창으로 갔는지 LAST 에 남긴다 (씹힘 진단용)."""
    u = ctypes.windll.user32
    h = game_window_at(x, y)
    if h:
        LAST.clear()
        LAST.update(hwnd=int(h), title=window_title(h), game=True)
        return h
    pt = ctypes.wintypes.POINT(int(x), int(y))     # 리니지M이 아니면 예전처럼
    h2 = u.WindowFromPoint(pt) or None
    LAST.clear()
    LAST.update(hwnd=int(h2) if h2 else 0,
                title=window_title(h2) if h2 else "", game=False)
    return h2


def post_click(x, y, double=False):
    """화면 좌표 (x, y) 의 리니지M 창에 클릭 메시지를 보낸다. 커서는 그대로 둔다.
    창을 못 찾으면 False (부르는 쪽에서 진짜 클릭으로 넘어간다)."""
    u = ctypes.windll.user32
    hwnd = _target_hwnd(x, y)
    if not hwnd:
        return False
    cpt = ctypes.wintypes.POINT(int(x), int(y))
    u.ScreenToClient(hwnd, ctypes.byref(cpt))
    lp = ((cpt.y & 0xFFFF) << 16) | (cpt.x & 0xFFFF)
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
    MK_LBUTTON = 0x0001
    # 누르는 시간이 너무 짧으면 게임이 무시한다 → 60~110ms 로 사람처럼
    u.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.02)
    u.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(random.uniform(0.06, 0.11))
    u.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    if double:
        time.sleep(0.06)
        u.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        time.sleep(random.uniform(0.06, 0.11))
        u.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    return True


def post_move(x, y):
    """커서를 옮기지 않고 그 자리에 '마우스가 올라갔다'는 신호만 보낸다.
    (스케줄의 '마우스 이동'처럼 올려놓기만 하면 되는 자리에 쓴다)"""
    u = ctypes.windll.user32
    hwnd = _target_hwnd(x, y)
    if not hwnd:
        return False
    cpt = ctypes.wintypes.POINT(int(x), int(y))
    u.ScreenToClient(hwnd, ctypes.byref(cpt))
    lp = ((cpt.y & 0xFFFF) << 16) | (cpt.x & 0xFFFF)
    u.PostMessageW(hwnd, 0x0200, 0, lp)          # WM_MOUSEMOVE
    return True


def post_wheel(x, y, notches):
    """커서를 옮기지 않고 그 자리에 휠을 굴린다 (양수=위로)."""
    u = ctypes.windll.user32
    hwnd = _target_hwnd(x, y)
    if not hwnd:
        return False
    lp = ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)   # 휠은 화면 좌표
    wp = (int(notches) * 120) << 16
    u.PostMessageW(hwnd, 0x020A, wp, lp)                  # WM_MOUSEWHEEL
    return True
