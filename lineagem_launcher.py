import ctypes
_ocr_reader = None
def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import ctypes, sys, os
        # 콘솔 창 숨기기
        try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except: pass
        os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
        import warnings; warnings.filterwarnings("ignore")
        import easyocr
        _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
    return _ocr_reader

# 콘솔 창 숨기기
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass

# 단일 인스턴스 보장 — 이미 실행 중이면 기존 창 앞으로 띄우고 종료
_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "LineageMAutoLauncher_Mutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    import sys
    sys.exit(0)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
from tkinter import messagebox
import subprocess, time, threading, json, random
import pyautogui
import pygetwindow as gw
import os
import win32gui, win32con

def _find_purple_exe():
    import glob as _glob
    candidates = _glob.glob(r"C:\Program Files (x86)\NCSOFT\Purple\*\Purple.exe")
    if candidates:
        return sorted(candidates)[-1]          # 가장 최신 버전
    return r"C:\Program Files (x86)\NCSOFT\Purple\Purple.exe"
PURPLE_EXE    = _find_purple_exe()
BASE          = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR      = os.path.join(BASE, "lineagem_logs")
os.makedirs(LOGS_DIR, exist_ok=True)
CONFIG_FILE   = os.path.join(BASE, "coords.json")
LOCAL_FILE    = os.path.join(BASE, "local_config.json")   # 머신별 설정(깃 공유 안 함, *.json 자동 제외)
LOCAL_KEYS    = ("profile_target_id", "doll_slots")       # coords.json이 아닌 이 컴퓨터에만 저장할 키
#               └ 인형탐험 좌표는 머신별로 다르게 유지 — 깃에 올리지 않음 (2026-07-17 사용자 요청)
ACCOUNTS_FILE = os.path.join(BASE, "accounts.json")
REROLL_DIR    = os.path.join(BASE, "reroll_templates")   # 아이템 리롤 타깃 이미지 저장
pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0.05

# ── 정밀 클릭 (전역) ───────────────────────────────────────────────
# 기본 pyautogui.click 은 좌표로 "이동하며" 클릭해서, 실행 중 마우스가 움직이거나
# 이동 경로 위에 클릭이 찍히는 오클릭이 생긴다. SetCursorPos 로 지정 좌표에
# 커서를 딱 고정한 뒤 그 자리에서 눌러, 방해 없이 정확히 그 지점만 찍는다.
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP   = 0x0004
_orig_pyautogui_click = pyautogui.click
def _precise_click(x=None, y=None, *args, **kwargs):
    """지정 좌표에 커서를 고정하고, 클릭하는 ~60ms 동안만 물리 입력을 차단해
    사용자가 마우스를 움직여도 방해 없이 그 지점만 정확히 찍는다.
    클릭 사이(대기 중)에는 차단이 풀려 마우스를 자유롭게 쓸 수 있다."""
    try:
        u = ctypes.windll.user32
        blocked = False
        try:
            blocked = bool(u.BlockInput(True))   # 물리 마우스/키보드 잠깐 차단
            if x is not None and y is not None:
                ix, iy = int(x), int(y)
                u.SetCursorPos(ix, iy)
                time.sleep(0.015)
                u.SetCursorPos(ix, iy)           # 클릭 직전 한 번 더 고정
            u.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            u.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        finally:
            if blocked:
                u.BlockInput(False)              # 반드시 차단 해제 (락 방지)
        time.sleep(0.02)
    except Exception:
        try: u.BlockInput(False)
        except Exception: pass
        return _orig_pyautogui_click(x, y, *args, **kwargs)
pyautogui.click = _precise_click

CLICK_SLOTS    = 16
GROUP_SIZE     = 8
HUNT_SLOTS     = 16
HUNT_CLICKS    = 5
HUNT_INTERVAL  = 1.4   # 사냥 슬롯 내 클릭 간격(초) — 실제 0.8~1.0초 랜덤
HUNT_SLOT_INTERVAL = 3.5  # 사냥 슬롯 간 간격(초) — 실제로 2~4초 랜덤
CLICK_INNER_INTERVAL = 2.5   # 클릭 슬롯 내 클릭 간격(초, 클릭1→클릭2)
CLICK_SLOT_INTERVAL  = 3.5   # 클릭 슬롯 간 간격(초, #01→#02)
CLICK_INTERVAL = CLICK_SLOT_INTERVAL  # 하위 호환
MAIL_SLOTS     = 16
MAIL_CLICKS    = 6
MAIL_INTERVAL  = 1.6   # 우편함 클릭 간격(초)
DUNGEON_SLOTS  = 16
DUNGEON_CLICKS = 3
DUNGEON_HOVER  = 1.5
PAST_SLOTS     = 16
PAST_CLICKS    = 3
PAST_INTERVAL  = 4.0   # 과거의말하는섬 클릭 간격(초)
SCHED_SLOTS        = 16
SCHED_CLICKS       = 3
SCHED_INTERVAL     = 2.5
PASS_SLOTS         = 16
PASS_CLICKS        = 9
PASS_INNER_MIN     = 2.9   # 패스권 좌표(클릭) 간 간격 — 씹힘 방지로 또 1초 더 늘림
PASS_INNER_MAX     = 3.2
PASS_SLOT_MIN      = 2.0
PASS_SLOT_MAX      = 8.0
PASS_LABELS        = [f"클릭{j+1}" for j in range(PASS_CLICKS)]
DUNGEON_INTERVAL = 2.0 # 클릭 사이 간격(초)
SEQ_SLOTS      = 16    # 연속 클릭 슬롯 수 (고정)
SEQ_MIN        = 0.7   # 연속 클릭 슬롯간 최소 간격(초)
SEQ_MAX        = 1.4   # 연속 클릭 슬롯간 최대 간격(초)
DC_SLOTS       = 16    # 일반던전충전 슬롯 수 (고정)
DC_MIN         = 1.0   # 좌표(슬롯) 간 간격(초) — 1~16 슬롯 사이 랜덤
DC_MAX         = 2.5
DC_TAPS_MIN    = 7     # 한 좌표당 연속 클릭 횟수(최소)
DC_TAPS_MAX    = 9     # 한 좌표당 연속 클릭 횟수(최대)
DC_BURST_MIN   = 1.0   # 한 좌표의 7~9회 클릭을 이 시간(초) 안에 모두 실행
DC_BURST_MAX   = 2.0
DOLL_SLOTS     = 16    # 인형 탐험 슬롯 수
DOLL_CLICKS    = 18    # 각 슬롯 좌표(클릭) 수
DOLL_MIN       = 2.0   # 슬롯 안 좌표 간 클릭 간격(초) — 2~3초 (1·2·3번 모두)
DOLL_MAX       = 3.0
DOLL_LEAD_MIN  = 0.5   # 슬롯의 '첫 클릭 전' 여유(바로 클릭하지 않음) — 0.5~1초
DOLL_LEAD_MAX  = 1.0
DOLL_SLOT_MIN  = 2.0   # 슬롯 간 간격(초) — 2~4초 랜덤
DOLL_SLOT_MAX  = 4.0
EXTRA_GAP_MIN  = 0.9   # 씹힘 방지용 추가 좌표간 간격 (사냥·전체실행·인형탐험 제외 전 기능)
EXTRA_GAP_MAX  = 1.6

DEFAULT_CFG = {
    "lineagem":    None,
    "game_start":  None,
    "multiplay":   None,
    "profile_btn": None,
    "google_acc":  None,
    "confirm_btn": None,
    "profile_target_id": "",
    "profile_id_area": None,
    "profile_reveal_btn": None,
    "char_btns":   [],
    "click_slots": [[None, None]] * CLICK_SLOTS,
    "hunt_slots":  [{"name": "미등록", "coords": [None] * HUNT_CLICKS}
                    for _ in range(HUNT_SLOTS)],
    "mail_slots":  [{"name": "미등록", "coords": [None] * MAIL_CLICKS}
                    for _ in range(MAIL_SLOTS)],
    "window_positions": [],
    "dungeon_slots": [{"name": "미등록", "coords": [None] * DUNGEON_CLICKS}
                      for _ in range(DUNGEON_SLOTS)],
    "past_slots":   [{"name": "미등록", "coords": [None] * PAST_CLICKS}
                     for _ in range(PAST_SLOTS)],
    "sched_slots":  [{"name": "미등록", "coords": [None] * SCHED_CLICKS}
                     for _ in range(SCHED_SLOTS)],
    "pass_slots":   [{"name": "미등록", "coords": [None]*PASS_CLICKS} for _ in range(PASS_SLOTS)],
    "seq_slots":    [None]*SEQ_SLOTS,   # 연속 클릭 좌표 (각 [x,y] 또는 None)
    "seq_hotkey":   None,               # 연속 클릭 실행 단축키 (가상키 코드)
    "seq_on":       False,              # 연속 클릭 단축키 활성화 상태 (재시작 유지)
    "seq_min":      SEQ_MIN,
    "seq_max":      SEQ_MAX,
    "dc_slots":     [None]*DC_SLOTS,    # 일반던전충전 좌표 (각 [x,y] 또는 None)
    "dc_hotkey":    None,               # 일반던전충전 실행 단축키 (가상키 코드)
    "dc_on":        False,              # 일반던전충전 단축키 활성화 상태 (재시작 유지)
    "dc_min":       DC_MIN,
    "dc_max":       DC_MAX,
    "doll_slots":   [{"name": "미등록", "coords": [None]*DOLL_CLICKS}
                     for _ in range(DOLL_SLOTS)],   # 인형 탐험 (16슬롯 × 18좌표)
    # 아이템 리롤(새로고침 매크로)
    "reroll_refresh_btn": None,   # 새로고침 버튼 좌표 [x,y]
    "reroll_confirm_btn": None,   # 발견 시 자동으로 누를 확인 버튼 좌표 [x,y]
    "reroll_item_area":   None,   # 아이템 이미지 캡처 영역 {x,y,w,h}
    "reroll_threshold":   0.90,   # 일치 판정 유사도(0~1)
    "reroll_wait":        1.0,    # 새로고침 후 대기(초)
    "reroll_targets":     [],     # [{enabled: bool} × 4], 이미지는 reroll_templates/target_N.png
}

LABELS = {
    "lineagem":    "리니지M 버튼 (좌측)",
    "game_start":  "게임 실행 버튼",
    "multiplay":   "멀티플레이 버튼",
    "profile_btn":    "프로필 버튼 (우상단)",
    "google_acc":     "구글 계정 (프로필 클릭 후)",
    "confirm_btn":    "확인 버튼 (계정전환 팝업)",
    "profile_reveal_btn": "아이디 표시 클릭 (확인 전)",
}


def load_accounts():
    try:
        with open(ACCOUNTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return [{"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""} for _ in range(20)]


def load_local():
    """머신별 설정(local_config.json) 읽기 — 없으면 빈 dict."""
    try:
        with open(LOCAL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_local(data):
    try:
        with open(LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _apply_local(cfg):
    """머신별 키를 로컬 파일 값으로 덮어씀. 로컬에 없고 coords.json에 값이 있으면 로컬로 1회 이관."""
    local = load_local()
    changed = False
    for k in LOCAL_KEYS:
        if k in local:
            cfg[k] = local[k]                 # 이 컴퓨터 값 우선
        elif cfg.get(k):
            local[k] = cfg[k]; changed = True  # 기존 coords.json 값 → 로컬로 이관(최초 1회)
    if changed:
        save_local(local)
    return cfg

def save_accounts(data):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_cfg():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CFG)
        cfg.update(data)
        # char_btns
        normalized = []
        for item in cfg.get("char_btns", []):
            if isinstance(item, dict) and item.get("btn"):
                normalized.append(item["btn"])
            elif isinstance(item, list):
                normalized.append(item)
        cfg["char_btns"] = normalized
        # click_slots (5번 슬롯=idx4 은 3개 좌표)
        slots, norm = cfg.get("click_slots", []), []
        for i, s in enumerate(slots):
            size = 3 if i == 4 else 2
            if isinstance(s, list) and len(s) >= 2 and isinstance(s[0], (list, type(None))):
                while len(s) < size: s.append(None)
                norm.append(s[:size])
            else:
                norm.append([None] * size)
        while len(norm) < CLICK_SLOTS:
            i = len(norm)
            norm.append([None, None, None] if i == 4 else [None, None])
        cfg["click_slots"] = norm[:CLICK_SLOTS]
        # hunt_slots
        hunt, nh = cfg.get("hunt_slots", []), []
        for h in hunt:
            if isinstance(h, dict):
                c = h.get("coords", [None] * HUNT_CLICKS)
                while len(c) < HUNT_CLICKS: c.append(None)
                entry = dict(h)  # 모든 키 보존 (assigned_window 등)
                entry["name"] = h.get("name", "미등록")
                entry["coords"] = c[:HUNT_CLICKS]
                nh.append(entry)
            else:
                nh.append({"name": "미등록", "coords": [None] * HUNT_CLICKS})
        while len(nh) < HUNT_SLOTS:
            nh.append({"name": "미등록", "coords": [None] * HUNT_CLICKS})
        cfg["hunt_slots"] = nh[:HUNT_SLOTS]
        # mail_slots (6 clicks: 기존 5개짜리는 끝에 None 추가)
        ml, nm = cfg.get("mail_slots", []), []
        for m in ml:
            if isinstance(m, dict):
                c = m.get("coords", [None] * MAIL_CLICKS)
                while len(c) < MAIL_CLICKS: c.append(None)
                nm.append({"name": m.get("name", "미등록"), "coords": c[:MAIL_CLICKS]})
            else:
                nm.append({"name": "미등록", "coords": [None] * MAIL_CLICKS})
        while len(nm) < MAIL_SLOTS:
            nm.append({"name": "미등록", "coords": [None] * MAIL_CLICKS})
        cfg["mail_slots"] = nm[:MAIL_SLOTS]
        # past_slots (3 clicks: 기존 2개짜리는 앞에 None 삽입)
        pl, np2 = cfg.get("past_slots", []), []
        for p in pl:
            if isinstance(p, dict):
                c = p.get("coords", [None] * PAST_CLICKS)
                if len(c) == 2:  # 구버전 → 앞에 None 삽입
                    c = [None] + c
                while len(c) < PAST_CLICKS: c.append(None)
                np2.append({"name": p.get("name", "미등록"), "coords": c[:PAST_CLICKS]})
            else:
                np2.append({"name": "미등록", "coords": [None] * PAST_CLICKS})
        while len(np2) < PAST_SLOTS:
            np2.append({"name": "미등록", "coords": [None] * PAST_CLICKS})
        cfg["past_slots"] = np2[:PAST_SLOTS]
        # sched_slots (3 clicks: 기존 2개짜리는 앞에 None 삽입)
        sl, ns = cfg.get("sched_slots", []), []
        for s in sl:
            if isinstance(s, dict):
                c = s.get("coords", [None] * SCHED_CLICKS)
                if len(c) == 2:  # 구버전 → 앞에 None 삽입
                    c = [None] + c
                while len(c) < SCHED_CLICKS: c.append(None)
                ns.append({"name": s.get("name", "미등록"), "coords": c[:SCHED_CLICKS]})
            else:
                ns.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
        while len(ns) < SCHED_SLOTS:
            ns.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
        cfg["sched_slots"] = ns[:SCHED_SLOTS]
        ps = cfg.get("pass_slots", [])
        while len(ps) < PASS_SLOTS:
            ps.append({"name": "미등록", "coords": [None]*PASS_CLICKS})
        for s in ps:
            c = s.get("coords", [])
            while len(c) < PASS_CLICKS: c.append(None)
            s["coords"] = c[:PASS_CLICKS]
        cfg["pass_slots"] = ps[:PASS_SLOTS]
        # seq_slots (연속 클릭 좌표 16개 고정)
        sq = cfg.get("seq_slots", [])
        if not isinstance(sq, list):
            sq = []
        while len(sq) < SEQ_SLOTS:
            sq.append(None)
        cfg["seq_slots"] = sq[:SEQ_SLOTS]
        # dc_slots (일반던전충전 좌표 16개 고정)
        dq = cfg.get("dc_slots", [])
        if not isinstance(dq, list):
            dq = []
        while len(dq) < DC_SLOTS:
            dq.append(None)
        cfg["dc_slots"] = dq[:DC_SLOTS]
        # doll_slots (인형 탐험 16슬롯 × 18좌표)
        dl, ndl = cfg.get("doll_slots", []), []
        for s in dl:
            c = s.get("coords", [None]*DOLL_CLICKS) if isinstance(s, dict) else [None]*DOLL_CLICKS
            while len(c) < DOLL_CLICKS: c.append(None)
            ndl.append({"name": s.get("name", "미등록") if isinstance(s, dict) else "미등록",
                        "coords": c[:DOLL_CLICKS],
                        "enabled": s.get("enabled", True) if isinstance(s, dict) else True})
        while len(ndl) < DOLL_SLOTS:
            ndl.append({"name": "미등록", "coords": [None]*DOLL_CLICKS, "enabled": True})
        cfg["doll_slots"] = ndl[:DOLL_SLOTS]
        return _apply_local(cfg)
    return _apply_local(dict(DEFAULT_CFG))

def save_cfg(cfg):
    # 머신별 키는 로컬 파일에만 저장하고, 공유되는 coords.json에서는 제외
    local = load_local()
    for k in LOCAL_KEYS:
        if k in cfg:
            local[k] = cfg[k]
    save_local(local)
    shared = {k: v for k, v in cfg.items() if k not in LOCAL_KEYS}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(shared, f, ensure_ascii=False, indent=2)

def find_purple():
    for w in gw.getAllWindows():
        if "purple" in w.title.lower() or "lineage" in w.title.lower():
            return w
    return None


def close_purple_popup_if_visible(cfg, status_fn=None):
    """Purple 팝업 감지 후 체크박스 → X 버튼 클릭으로 닫기.
    감지: X버튼 좌표의 픽셀이 등록된 색상과 일치할 때만 클릭.
    """
    from PIL import ImageGrab
    chk  = cfg.get("purple_popup_checkbox")   # [x, y]
    cls  = cfg.get("purple_popup_close")       # [x, y]
    det  = cfg.get("purple_popup_detect")      # [x, y]
    col  = cfg.get("purple_popup_color")       # [r, g, b]
    tol  = 30  # 색상 허용 오차

    if not (cls and det and col):
        return  # 미등록

    try:
        shot = ImageGrab.grab(all_screens=False)
        px   = shot.getpixel((det[0], det[1]))
        r, g, b = px[0], px[1], px[2]
        if (abs(r - col[0]) > tol or
            abs(g - col[1]) > tol or
            abs(b - col[2]) > tol):
            return  # 팝업 없음
    except Exception:
        return

    if status_fn:
        status_fn("⚠ 퍼플 팝업 감지 — 자동으로 닫는 중...")
    if chk:
        pyautogui.click(*chk)
        time.sleep(0.4)
    pyautogui.click(*cls)
    time.sleep(0.3)
    if status_fn:
        status_fn("✔ 퍼플 팝업 닫기 완료")


class WindowSizeLock:
    """폴링으로 창 크기 고정. 최소화만 허용, 최대화/리사이즈 모두 차단."""
    SWP_NOZORDER   = 0x0004
    SWP_NOACTIVATE = 0x0010

    def __init__(self):
        self._locks   = {}   # hwnd -> (x, y, w, h)
        self._thread  = None
        self._running = False

    def lock_all(self, hwnds):
        self.unlock()
        for hwnd in hwnds:
            try:
                r = win32gui.GetWindowRect(hwnd)
                self._locks[hwnd] = (r[0], r[1], r[2]-r[0], r[3]-r[1])
            except Exception:
                pass
        if self._locks:
            self._running = True
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()
        return self._locks

    def unlock(self):
        self._running = False
        self._locks = {}

    def is_locked(self):
        return self._running and bool(self._locks)

    def pause(self, seconds):
        """일시 정지 후 자동 재개"""
        self._paused_until = time.time() + seconds

    def _watch(self):
        user32 = ctypes.windll.user32
        self._paused_until = 0
        while self._running:
            if time.time() < self._paused_until:
                time.sleep(0.3); continue
            for hwnd, rect in list(self._locks.items()):
                try:
                    if not win32gui.IsWindow(hwnd):
                        self._locks.pop(hwnd, None); continue
                    if user32.IsIconic(hwnd):
                        continue
                    cr = win32gui.GetWindowRect(hwnd)
                    cw, ch = cr[2]-cr[0], cr[3]-cr[1]
                    if cw != rect[2] or ch != rect[3]:
                        user32.SetWindowPos(hwnd, 0, rect[0], rect[1],
                                            rect[2], rect[3],
                                            self.SWP_NOZORDER | self.SWP_NOACTIVATE)
                except Exception:
                    pass
            time.sleep(0.3)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("리니지M 자동 실행")
        sh = self.winfo_screenheight()
        self.geometry(f"2117x1010+76+75")   # 콘텐츠에 맞춘 높이 (작업표시줄 위로)
        self.resizable(True, True)
        self.bind("<Map>", self._on_main_map)
        self.bind("<Unmap>", self._on_main_unmap)   # 런처 최소화 시 클로드도 같이 내림
        self.bind("<FocusIn>", self._bring_to_front)
        self.after(150, self._fit_main_height)
        # 유휴(2분 무조작) 시 메인런처 자동 최소화 — 조작 감지용
        self._last_activity = time.time()
        self.bind_all("<Button>", self._mark_activity, add="+")
        self.bind_all("<Key>",    self._mark_activity, add="+")
        # 런처↔클로드 최소화 커플링은 시작 20초 후부터 (워치독 시작 최소화 제외)
        self._unmap_couple_ok = False
        self.after(20000, lambda: setattr(self, "_unmap_couple_ok", True))

        self.cfg = load_cfg()
        self._accounts = load_accounts()
        while len(self._accounts) < 20:
            self._accounts.append({"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""})
        self._acc_type_vars = [tk.StringVar(value=a.get("type", "구글")) for a in self._accounts]
        self._acc_vars = [
            [tk.StringVar(value=a.get(f"f{j+1}", "")) for j in range(5)]
            for a in self._accounts
        ]
        self._acc_type_btns = [None] * 16   # 계정 관리 창 OptionMenu 참조 (창 재오픈 대비)
        self._reg_target   = None
        self._busy_task      = None   # 현재 실행 중인 개별 작업 이름 (동시 실행 방지)
        self._stop_flag      = False
        self._running        = False  # 전체 자동실행 중 여부
        self._click_stop     = False
        self._hunt_stop      = False
        self._sched_any_stop = False
        self._mail_on      = True
        self._mail_triggered_date = None
        self._past_triggered_date = None
        self._purple_triggered_date = None
        self._win_lock     = WindowSizeLock()
        self._hp_stop      = False
        self._seq_on       = bool(self.cfg.get("seq_on", False))
        self._seq_running  = False
        self._dc_on        = bool(self.cfg.get("dc_on", False))
        self._dc_running   = False
        self._doll_stop    = False
        self._task_queue   = []   # 연속으로 누른 실행/재측정 순차 실행 대기열
        self._build_ui()
        self._sync_sched_click1()   # 스케줄 클릭1 = 과거섬 클릭1 (시작 시 1회 동기화)
        self.after(1000, self._mail_scheduler_tick)
        self.after(1000, self._past_scheduler_tick)
        self.after(30000, self._subwin_autoclose_tick)   # 서브창 3분 무조작 자동닫기
        self.after(2000, self._queue_tick)               # 실행 대기열 순차 처리
        self.after(1000, self._purple_check_tick)
        threading.Thread(target=self._seq_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._dc_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._popup_guard_loop, daemon=True).start()
        threading.Thread(target=self._claude_attention_loop, daemon=True).start()
        # 작업 중에는 클로드를 강제로 내리지 않는다(예전 시작 버스트 제거).
        # 대신 클로드 앱을 화면 가운데로 유지 (아이디 영역 등 안 가리게, 사용자가 옮기면 중단)
        self.after(2000, self._center_claude_tick)
        self.after(3000, self._claude_minimize_tick)
        self.after(20000, self._idle_minimize_tick)         # 2분 무조작 시 메인런처 자동 최소화
        self.after(30000, self._claude_idle_minimize_tick)  # 3분 무입력 시 클로드 앱 최소화
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._set_sleep_prevention(False)
        self.destroy()

    def _open_ocr(self):
        if self._is_busy(exclude="다야OCR"):
            self._enqueue("다야OCR 창", self._open_ocr); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self._ocr_proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py")])
        self.iconify()

    def _open_ocr_scan(self):
        if self._is_busy(exclude="다야OCR"):
            self._enqueue("다야OCR 스캔", self._open_ocr_scan); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self._ocr_proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py"), "--scan"])
        self.iconify()

    def _open_island(self):
        import subprocess
        self.iconify()
        self._minimize_claude()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py")])
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _watch_island(self, proc):
        proc.wait()
        self._island_proc = None
        if not (self._pass_win and self._pass_win.winfo_exists()):
            self.after(0, self.deiconify)
        self._restore_claude()

    def _restore_claude(self):
        try:
            import win32gui, win32con
            def _do(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Claude" in title and win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.EnumWindows(_do, None)
        except Exception:
            pass


    # ── UI 빌드 ────────────────────────────────────────────────────────
    def _build_ui(self):
        # 제목
        tk.Label(self, text="리니지M 자동 실행",
                 font=("맑은 고딕", 13, "bold"), fg="#c8a951").pack(pady=(10, 2))

        # 계정 수
        row_acc = tk.Frame(self); row_acc.pack(fill="x", padx=16, pady=2)
        tk.Label(row_acc, text="전환할 계정 수:", font=("맑은 고딕", 9)).pack(side="left")
        self.acc_count = tk.IntVar(value=2)
        tk.Spinbox(row_acc, from_=1, to=16, textvariable=self.acc_count,
                   width=4, font=("맑은 고딕", 9), state="normal").pack(side="left", padx=4)

        # 실행 / 멈춤
        btn_row = tk.Frame(self); btn_row.pack(pady=6)
        tk.Button(btn_row, text="🔑 계정\n관리",
            font=("맑은 고딕", 9, "bold"), bg="#16a085", fg="white",
            activebackground="#0e6655", width=7, height=2,
            command=self._open_accounts_win).pack(side="left", padx=(0, 6))
        self.btn_start = tk.Button(btn_row, text="▶  전체 자동 실행",
            font=("맑은 고딕", 12, "bold"), bg="#c8a951", fg="white",
            activebackground="#a88930", width=15, height=2, command=self._start)
        self.btn_start.pack(side="left", padx=(0, 4))
        self.btn_stop = tk.Button(btn_row, text="■ 멈춤",
            font=("맑은 고딕", 10, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=7, height=2,
            command=self._stop)
        self.btn_stop.pack(side="left")

        # 9시 클릭 스케줄러
        tk.Frame(btn_row, width=10).pack(side="left")
        self.btn_mail = tk.Button(btn_row, text="🕘 22:30~23:30 클릭  ON",
            font=("맑은 고딕", 9, "bold"), bg="#27ae60", fg="white",
            activebackground="#5d6d7e", width=13, height=2,
            command=self._toggle_mail)
        self.btn_mail.pack(side="left")

        self._btn_layout_toggle = tk.Button(btn_row, text="🖼 배치보기",
            font=("맑은 고딕", 7), width=6, height=2,
            command=self._toggle_layout_preview)
        # layout toggle 참조 유지 (내부 사용)

        tk.Frame(btn_row, width=20).pack(side="left")
        tk.Button(btn_row, text="🏝 섬/던전 실행기",
            font=("맑은 고딕", 11, "bold"), bg="#2c3e50", fg="white",
            width=14, height=2,
            command=self._open_island).pack(side="left")
        tk.Button(btn_row, text="🎫 패스권\n새로운 등록",
            font=("맑은 고딕", 10, "bold"), bg="#6c3483", fg="white",
            width=10, height=2,
            command=self._open_pass_win).pack(side="left", padx=(4,0))
        tk.Button(btn_row, text="💬 클로드\n앞으로",
            font=("맑은 고딕", 9, "bold"), bg="#c0392b", fg="white",
            width=8, height=2,
            command=self._raise_claude).pack(side="left", padx=(4,0))

        tk.Frame(btn_row, width=10).pack(side="left")
        popup_box = tk.Frame(btn_row, bd=1, relief="groove", padx=4, pady=2)
        popup_box.pack(side="left")
        tk.Label(popup_box, text="퍼플 팝업 자동닫기",
                 font=("맑은 고딕", 7, "bold"), fg="#8e44ad").pack()
        pb_row = tk.Frame(popup_box); pb_row.pack()
        tk.Button(pb_row, text="☑ 체크박스\n좌표 등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_checkbox).pack(side="left", padx=1)
        tk.Button(pb_row, text="✕ 닫기버튼\n좌표 등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_close).pack(side="left", padx=1)
        tk.Button(pb_row, text="🎨 감지픽셀\n등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_detect).pack(side="left", padx=1)
        self._popup_status_var = tk.StringVar(value=self._popup_reg_label())
        tk.Label(popup_box, textvariable=self._popup_status_var,
                 font=("맑은 고딕", 6), fg="#7f8c8d").pack()

        # 퍼플 팝업 자동닫기 우측: 오림의 일기장(아이템 리롤) — 크게
        tk.Frame(btn_row, width=10).pack(side="left")
        tk.Button(btn_row, text="📖 오림의\n일기장", font=("맑은 고딕", 13, "bold"),
                  bg="#a04000", fg="white", activebackground="#7a3000",
                  width=11, height=3, command=self._open_reroll_win).pack(side="left")

        # 다야 카운트 데이터 변수 (UI는 별도 창)
        self._cnt_total_var = tk.StringVar(value="합계: 0")
        self._cnt_cell_vars = [tk.StringVar(value="-") for _ in range(16)]
        self._cnt_load  = self._make_cnt_loader()
        self._cnt_today = self._make_today_fn()
        self._refresh_count()
        self._schedule_count_refresh()


        # 배치 스크린샷 미리보기 (기본 숨김)
        self._layout_img_label = None
        self._layout_preview_frame = tk.Frame(self)
        self._layout_preview_visible = False

        self.status = tk.StringVar(value="버튼을 눌러 시작하세요")
        self.status_label_widget = tk.Label(self, textvariable=self.status, font=("맑은 고딕", 8),
                 fg="#555", wraplength=600)
        self.status_label_widget.pack(pady=(0, 2))

        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=10, pady=3)

        # ── 섹션 버튼 행 (좌표등록·과거섬·스케줄·사냥 등 직접 표시) ──
        self._sec_row = tk.Frame(self); self._sec_row.pack(pady=4)
        self._build_sec_row()

        # ── 배열창 재배치(슬롯별 그리드) + 다야 수량 ──
        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=10, pady=(4,2))
        front_row = tk.Frame(self); front_row.pack(pady=4, anchor="n")

        # 배열창 재배치 왼쪽: (1행) 일반던전충전+실행  (2행) 인형탐험+실행 — 각 버튼 옆에 실행
        dc_col = tk.Frame(front_row); dc_col.pack(side="left", padx=(4,8), anchor="n")
        r1 = tk.Frame(dc_col); r1.pack(anchor="n")
        tk.Button(r1, text="🎯 일반\n던전충전",
            font=("맑은 고딕", 9, "bold"), bg="#6c3483", fg="white",
            activebackground="#512e6f", width=7, height=2,
            command=self._open_dc_win).pack(side="left")
        tk.Button(r1, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_dc).pack(side="left", padx=(2,0))
        r2 = tk.Frame(dc_col); r2.pack(anchor="n", pady=(4,0))
        tk.Button(r2, text="🧸 인형\n탐험",
            font=("맑은 고딕", 9, "bold"), bg="#b9770e", fg="white",
            activebackground="#8a5809", width=7, height=2,
            command=self._open_doll_win).pack(side="left")
        tk.Button(r2, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_doll).pack(side="left", padx=(2,0))

        winmgmt = tk.Frame(front_row); winmgmt.pack(side="left", padx=(4,10), anchor="n")
        self._build_winmgmt(winmgmt)

        tk.Frame(front_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=(4,8))

        # 다야 수량 컨트롤 + 그리드
        daya_inner = tk.Frame(front_row); daya_inner.pack(side="left", anchor="n")
        ctrl = tk.Frame(daya_inner); ctrl.pack(side="left", padx=(4,8), anchor="n")
        tk.Label(ctrl, text="💰 다야 수량", font=("맑은 고딕", 9, "bold"), fg="#2c3e50").pack(anchor="w")
        tk.Button(ctrl, text="📊 OCR 실행", font=("맑은 고딕", 8, "bold"),
                  bg="#27ae60", fg="white", width=10,
                  command=self._open_ocr).pack(fill="x", pady=1)
        tk.Button(ctrl, text="📋 복사", font=("맑은 고딕", 8, "bold"),
                  bg="#2471a3", fg="white", width=10,
                  command=self._copy_daya_counts).pack(fill="x", pady=1)
        tk.Label(ctrl, textvariable=self._cnt_total_var,
                 font=("맑은 고딕", 10, "bold"), fg="#c0392b").pack(anchor="w", pady=(4,0))

        self._cnt_img_labels = []
        self._cnt_thumbs = [None] * 16
        grid = tk.Frame(daya_inner); grid.pack(side="left", anchor="n")
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(grid, bd=1, relief="groove")
                cell.grid(row=r, column=c, padx=1, pady=1, sticky="n")
                head = tk.Frame(cell); head.pack()
                tk.Label(head, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")
                cntlbl = tk.Label(head, textvariable=self._cnt_cell_vars[idx],
                         font=("맑은 고딕", 11, "bold"), fg="#2980b9", cursor="hand2")
                cntlbl.pack(side="left", padx=(2,0))
                cntlbl.bind("<Button-1>", lambda e, x=idx: self._edit_daya_count(x))
                imbox = tk.Frame(cell, width=93, height=33, bg="#f4f4f4")
                imbox.pack()
                imbox.pack_propagate(False)
                imlbl = tk.Label(imbox, bg="#f4f4f4", fg="#ccc", font=("맑은 고딕", 7))
                imlbl.pack(fill="both", expand=True)
                self._cnt_img_labels.append(imlbl)
                tk.Button(cell, text="재측정", font=("맑은 고딕", 6, "bold"),
                          bg="#27ae60", fg="white", pady=0,
                          command=lambda x=idx: self._rescan_daya_slot(x)).pack(fill="x")
        self._load_daya_thumbs()

        # 다야 수량 우측: 귀환주문서 슬롯별 실행 그리드 (좌표는 섬/던전 실행기에서 관리)
        tk.Frame(front_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=(8,8))
        return_col = tk.Frame(front_row); return_col.pack(side="left", anchor="n")
        self._build_return_grid(return_col)

        # 서브창 핸들 초기화
        self._settings_win = None
        self._hunt_win     = None
        self._mail_win     = None
        self._past_win2    = None
        self._sched_win    = None
        self._dungeon_win  = None
        self._daya_win     = None
        self._pass_win     = None
        self._accounts_win = None
        self._reroll_win   = None
        self._reroll_running = False
        self._reroll_thumbs  = [None] * 4   # 타깃 미리보기 PhotoImage 참조 유지
        self._island_proc  = None
        self._pass_name_vars    = []
        self._pass_click_vars   = []
        self._pass_click_btns   = []
        self._pass_coord_sv     = []
        self._pass_detail_frames= []
        self._pass_row_frames   = []
        self._refresh_ui()

    # ── 섹션 창 열기 ────────────────────────────────────────────────────
    def _minimize_claude(self):
        try:
            import win32gui, win32con
            def _do(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Claude" in title and win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            win32gui.EnumWindows(_do, None)
        except Exception:
            pass

    def _open_section_win(self, attr, title, build_fn, w=420, h=700, pinnable=False):
        win = getattr(self, attr, None)
        if win and win.winfo_exists():
            win.lift(); return
        win = tk.Toplevel(self)
        win.title(title)
        win.attributes("-topmost", True)
        # 저장된 위치가 있으면 복원, 없으면 기본 크기
        pos_key = f"_win_pos_{attr}"
        saved = self.cfg.get(pos_key)
        if saved:
            win.geometry(f"{w}x{h}+{saved[0]}+{saved[1]}")
        else:
            win.geometry(f"{w}x{h}")
        win.resizable(True, True)
        setattr(self, attr, win)
        # 서브창: 3분간 조작 없으면 자동으로 닫고 메인런처 복원
        win._last_active = time.time()
        def _bump(e=None, w=win): w._last_active = time.time()
        for _seq in ("<Button>", "<Key>", "<Motion>"):
            win.bind(_seq, _bump, add="+")
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self._close_subwin(w))
        build_fn(win)
        if pinnable:
            self._add_drag_bar(win, attr, pos_key)
        self._refresh_ui()
        # 내용 너비에 맞게 창 너비 자동 조정
        def _fit():
            win.update_idletasks()
            needed = win.winfo_reqwidth() + 10
            win.geometry(f"{needed}x{h}")
        win.after(80, _fit)

    def _close_subwin(self, win):
        """서브창을 닫고 메인런처를 앞으로 띄운다."""
        try:
            if win and win.winfo_exists():
                win.destroy()
        except Exception:
            pass
        def _raise():
            try:
                self.deiconify(); self.lift(); self.focus_force()
            except Exception:
                pass
        self.after(60, _raise)

    def _subwin_autoclose_tick(self):
        """열려있는 서브창이 3분간 조작이 없으면 자동으로 닫는다(실행 중엔 유지)."""
        try:
            if not self._is_busy():   # 실행 중이면 창을 건드리지 않음
                now = time.time()
                for w in self._section_wins():
                    if now - getattr(w, "_last_active", now) >= 180:
                        self._close_subwin(w)
                        break   # 한 번에 하나씩(복원 충돌 방지)
        except Exception:
            pass
        self.after(20000, self._subwin_autoclose_tick)

    def _add_drag_bar(self, win, attr, pos_key):
        """창 하단에 드래그 이동바 추가. 이동 후 위치를 cfg에 저장."""
        bar = tk.Frame(win, bg="#555", height=18, cursor="fleur")
        bar.pack(side="bottom", fill="x")
        lbl = tk.Label(bar, text="⠿ 여기를 드래그해서 창 이동", bg="#555", fg="#ccc",
                       font=("맑은 고딕", 7), cursor="fleur")
        lbl.pack()

        _drag = {"x": 0, "y": 0}

        def _start(e):
            _drag["x"] = e.x_root - win.winfo_x()
            _drag["y"] = e.y_root - win.winfo_y()

        def _drag_move(e):
            nx = e.x_root - _drag["x"]
            ny = e.y_root - _drag["y"]
            win.geometry(f"+{nx}+{ny}")

        def _end(e):
            nx = win.winfo_x()
            ny = win.winfo_y()
            self.cfg[pos_key] = [nx, ny]
            self._save_cfg()

        for w in (bar, lbl):
            w.bind("<ButtonPress-1>", _start)
            w.bind("<B1-Motion>", _drag_move)
            w.bind("<ButtonRelease-1>", _end)

    def _open_settings_win(self):
        self._open_section_win("_settings_win", "⚙ 좌표 등록", self._build_left, w=320, h=680)

    def _open_hunt_win(self):
        self._open_section_win("_hunt_win", "🏹 사냥", self._build_right, w=440, h=700)

    def _open_accounts_win(self):
        self._open_section_win("_accounts_win", "🔑 계정 관리", self._build_accounts, w=560, h=560)

    def _open_reroll_win(self):
        self._open_section_win("_reroll_win", "📖 오림의 일기장", self._build_reroll, w=440, h=800)

    def _open_mail_win(self):
        self._open_section_win("_mail_win", "📬 우편함", self._build_mail, w=300, h=700)

    def _open_past_win(self):
        self._open_section_win("_past_win2", "🏝 과거의말하는섬", self._build_past, w=280, h=700, pinnable=True)

    def _open_past_slot(self, idx):
        """해당 던전 컬럼만 단독으로 섬/던전 실행기 열기."""
        self.iconify()
        self._minimize_claude()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py"), str(idx)])
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _run_island_slot(self, idx):
        """해당 던전 단독창 열고 자동 실행."""
        if self._is_busy():
            self._enqueue(f"섬/던전 #{idx+1:02d}", lambda: self._run_island_slot(idx)); return
        self.iconify()
        self._minimize_claude()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py"), str(idx), "--run"])
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _open_sched_win(self):
        self._open_section_win("_sched_win", "📅 매일매일 스케줄", self._build_sched, w=300, h=700)

    def _open_dungeon_win(self):
        self._open_section_win("_dungeon_win", "🏰 주말던전", self._build_dungeon, w=160, h=700, pinnable=True)

    def _open_daya_win(self):
        self._open_section_win("_daya_win", "💰 다야 카운트", self._build_daya_panel, w=500, h=260)

    def _build_daya_panel(self, parent):
        cnt_box = tk.Frame(parent); cnt_box.pack(padx=8, pady=8, fill="both", expand=True)
        tk.Label(cnt_box, text="현재 다야 수량",
                 font=("맑은 고딕", 14, "bold"), fg="#2c3e50").grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        tk.Button(cnt_box, text="📊 OCR", font=("맑은 고딕", 7, "bold"), bg="#27ae60", fg="white",
                  width=8, command=self._open_ocr).grid(row=0, column=2, columnspan=2, sticky="w", padx=2)
        tk.Button(cnt_box, text="📋 복사", font=("맑은 고딕", 7, "bold"), bg="#2471a3", fg="white",
                  width=8, command=self._copy_daya_counts).grid(row=0, column=4, columnspan=2, sticky="w", padx=2)
        tk.Label(cnt_box, textvariable=self._cnt_total_var,
                 font=("맑은 고딕", 14, "bold"), fg="#c0392b").grid(row=0, column=6, columnspan=4, sticky="e", padx=4)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(cnt_box, bd=1, relief="flat", width=70, height=44)
                cell.grid(row=r+1, column=c, padx=2, pady=2)
                cell.pack_propagate(False)
                tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 10), fg="#aaa").pack()
                tk.Label(cell, textvariable=self._cnt_cell_vars[idx],
                         font=("맑은 고딕", 14, "bold"), fg="#2980b9").pack()

    def _make_cnt_loader(self):
        import datetime as _dt
        count_file = os.path.join(BASE, "daya_counts.json")
        def load():
            try:
                with open(count_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return load

    def _make_today_fn(self):
        import datetime as _dt
        return lambda: _dt.date.today().isoformat()

    def _copy_daya_counts(self):
        values = [v.get().replace(",", "").replace("-", "0") for v in self._cnt_cell_vars]
        rows = ["\t".join(values[r*4:(r+1)*4]) for r in range(4)]
        text = "\n".join(rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("✔ 다야 수량 클립보드 복사 완료 — 엑셀에 붙여넣기 하세요")

    def _refresh_count(self):
        data = self._cnt_load()
        # 가장 최근 날짜 데이터를 항상 표시 (OCR 실행 시만 갱신됨)
        if not data:
            day_data = {}
        else:
            latest_day = max(data.keys())
            day_data = data.get(latest_day, {})
        total = 0
        for i in range(16):
            v = day_data.get(str(i), 0)
            self._cnt_cell_vars[i].set(f"{v:,}" if v else "-")
            total += v
        self._cnt_total_var.set(f"합계: {total:,}")
        self._load_daya_thumbs()

    def _load_daya_thumbs(self):
        """daya_crops/slot_i.png (OCR가 캡처한 숫자 이미지)을 각 셀에 표시."""
        labels = getattr(self, "_cnt_img_labels", None)
        if not labels:
            return
        try:
            from PIL import Image, ImageTk
        except Exception:
            return
        crop_dir = os.path.join(BASE, "daya_crops")
        for i, lbl in enumerate(labels):
            p = os.path.join(crop_dir, f"slot_{i}.png")
            try:
                if os.path.exists(p):
                    with Image.open(p) as _im0:
                        im = _im0.copy()
                    scale = 30.0 / max(im.height, 1)          # 기존 20px → 1.5배(30px)
                    w = max(1, min(180, int(im.width * scale)))
                    im = im.resize((w, 30), Image.LANCZOS)
                    ph = ImageTk.PhotoImage(im)
                    self._cnt_thumbs[i] = ph            # 참조 유지
                    lbl.config(image=ph, text="")
                else:
                    lbl.config(image="", text="-")
            except Exception:
                pass

    def _rescan_daya_slot(self, idx):
        """해당 슬롯 하나만 다야 OCR 재측정 (별도 프로세스 --slot)."""
        if self._is_busy():
            self._enqueue(f"다야 재측정 #{idx+1:02d}", lambda: self._rescan_daya_slot(idx)); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self.status.set(f"🔎 #{idx+1:02d} 다야 재측정 중... (OCR 로딩 포함 잠시)")
        # 런처/클로드가 게임(숫자 영역)을 가리지 않게 최소화하고 실행
        self._minimize_claude()
        self.iconify()
        try:
            proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py"), "--slot", str(idx)])
        except Exception as e:
            self.deiconify()
            self.status.set(f"재측정 실행 오류: {e}"); return
        self._ocr_proc = proc   # busy 락이 인식 → 다른 작업과 겹침 방지
        threading.Thread(target=self._watch_rescan, args=(proc, idx), daemon=True).start()

    def _watch_rescan(self, proc, idx):
        try:
            proc.wait()
        except Exception:
            pass
        def _done():
            self.deiconify(); self.lift()   # 끝나면 런처 다시 보여주기
            self._refresh_count()           # 숫자 + 캡처 사진(썸네일) 갱신
            self.status.set(f"✔ #{idx+1:02d} 다야 재측정 완료")
        self.after(0, _done)

    def _edit_daya_count(self, idx):
        """다야 수량 숫자를 클릭 → 손으로 수정 (OCR 오표기 보정)."""
        from tkinter import simpledialog
        cur_txt = self._cnt_cell_vars[idx].get().replace(",", "")
        try:
            cur = int(cur_txt) if cur_txt not in ("", "-", "?") else 0
        except Exception:
            cur = 0
        val = simpledialog.askinteger(
            "다야 수량 수정", f"#{idx+1:02d} 다야 수량을 입력하세요\n(캡처 이미지를 보고 맞는 숫자로)",
            initialvalue=cur, minvalue=0, parent=self)
        if val is None:
            return   # 취소
        self._save_daya_count_manual(idx, val)
        self._refresh_count()
        self.status.set(f"✔ #{idx+1:02d} 다야 수량 수동 수정: {val:,}")

    def _save_daya_count_manual(self, idx, val):
        """daya_counts.json의 최신 날짜 데이터에 수정값을 기록(표시와 동일한 날짜)."""
        p = os.path.join(BASE, "daya_counts.json")
        try:
            with open(p, encoding="utf-8") as f:
                counts = json.load(f)
        except Exception:
            counts = {}
        import datetime as _dt
        day = max(counts.keys()) if counts else _dt.date.today().isoformat()
        counts.setdefault(day, {})[str(idx)] = val
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(counts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.status.set(f"저장 오류: {e}")

    def _schedule_count_refresh(self):
        self._refresh_count()
        self.after(30000, self._schedule_count_refresh)  # 30초마다 자동갱신

    def _preview_coord(self, x, y):
        """마우스를 해당 좌표로 이동해서 위치 미리보기"""
        import threading as _th
        def _move():
            try:
                pyautogui.moveTo(x, y, duration=0.25)
            except Exception:
                pass
        self.status.set(f"미리보기: ({x},{y}) — 마우스가 해당 위치로 이동합니다")
        _th.Thread(target=_move, daemon=True).start()

    def _build_left(self, parent):
        # 좌표 등록
        tk.Label(parent, text="좌표 등록  (버튼 → 3초 후 해당 위치 클릭)",
                 font=("맑은 고딕", 8), fg="#888").pack(anchor="w", padx=4)
        self._coord_vars = {}
        for key, label in LABELS.items():
            row = tk.Frame(parent); row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=label, font=("맑은 고딕", 8),
                     width=18, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._coord_vars[key] = var
            tk.Label(row, textvariable=var, font=("맑은 고딕", 7),
                     fg="gray", width=12).pack(side="left")
            tk.Button(row, text="등록", font=("맑은 고딕", 7),
                      command=lambda k=key: self._reg_coord(k)).pack(side="right")
            tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                      command=lambda k=key: self._preview_label_coord(k)).pack(side="right", padx=1)

        # 프로필 아이디 OCR 설정
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)
        area_row = tk.Frame(parent); area_row.pack(fill="x", padx=4, pady=2)
        tk.Label(area_row, text="아이디 표시 영역", font=("맑은 고딕", 8), width=18, anchor="w").pack(side="left")
        self._profile_area_var = tk.StringVar(value="등록됨" if self.cfg.get("profile_id_area") else "미등록")
        tk.Label(area_row, textvariable=self._profile_area_var, font=("맑은 고딕", 7), fg="gray", width=12).pack(side="left")
        tk.Button(area_row, text="등록", font=("맑은 고딕", 7),
                  command=self._reg_profile_id_area).pack(side="right")
        tk.Button(area_row, text="테스트", font=("맑은 고딕", 7), bg="#7d3c98", fg="white",
                  command=self._test_profile_ocr).pack(side="right", padx=2)

        pid_row = tk.Frame(parent); pid_row.pack(fill="x", padx=4, pady=2)
        tk.Label(pid_row, text="사용할 아이디", font=("맑은 고딕", 8), width=18, anchor="w").pack(side="left")
        self._profile_target_var = tk.StringVar(value=self.cfg.get("profile_target_id", ""))
        tk.Entry(pid_row, textvariable=self._profile_target_var, font=("맑은 고딕", 8),
                 fg="#2471a3", width=14).pack(side="left")
        def _save_pid():
            self.cfg["profile_target_id"] = self._profile_target_var.get().strip()
            save_cfg(self.cfg)
            self.status.set(f"✔ 아이디 저장: '{self.cfg['profile_target_id']}'")
        tk.Button(pid_row, text="저장", font=("맑은 고딕", 7), bg="#2471a3", fg="white",
                  command=_save_pid).pack(side="left", padx=2)

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)

        # 캐릭터 접속 버튼
        char_hdr = tk.Frame(parent); char_hdr.pack(fill="x", padx=4, pady=1)
        self._char_count_var = tk.StringVar()
        tk.Label(char_hdr, text="캐릭터 접속 버튼", font=("맑은 고딕", 9, "bold")).pack(side="left")
        tk.Label(char_hdr, textvariable=self._char_count_var,
                 font=("맑은 고딕", 8), fg="#c8a951").pack(side="left", padx=4)
        tk.Button(char_hdr, text="+ 추가", font=("맑은 고딕", 7),
                  command=self._reg_char_btn).pack(side="right")
        tk.Button(char_hdr, text="전체삭제", font=("맑은 고딕", 7), fg="red",
                  command=self._clear_char_btns).pack(side="right", padx=2)
        # 캐릭터 버튼 목록 (동적)
        self._char_rows_frame = tk.Frame(parent)
        self._char_rows_frame.pack(fill="x", padx=4)

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)

        # 클릭 슬롯
        tk.Label(parent, text="클릭 등록  (슬롯당 2번 클릭 등록 / 3초 간격)",
                 font=("맑은 고딕", 8), fg="#888").pack(anchor="w", padx=4)

        self._slot_vars = []
        for g in range(CLICK_SLOTS // GROUP_SIZE):
            grp = tk.LabelFrame(parent,
                                text=f"그룹 {g+1}  ({g*GROUP_SIZE+1}~{(g+1)*GROUP_SIZE}번)",
                                font=("맑은 고딕", 7), padx=2, pady=1)
            grp.pack(fill="x", padx=4, pady=1)
            for i in range(GROUP_SIZE):
                idx = g * GROUP_SIZE + i
                row = tk.Frame(grp); row.pack(fill="x", pady=2)
                tk.Label(row, text=f"#{idx+1:02d}", font=("맑은 고딕", 8, "bold"),
                         width=4).pack(side="left", padx=(2,0))
                var = tk.StringVar()
                self._slot_vars.append(var)
                tk.Label(row, textvariable=var, font=("맑은 고딕", 7),
                         fg="gray", width=16).pack(side="left", padx=(2,4))
                # 왼쪽부터: ①②(개별등록) — 오른쪽부터: 등록 삭제 👁 ↑복사
                if idx > 0:
                    tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                              command=lambda x=idx: self._group_copy_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                          command=lambda x=idx: self._preview_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="삭제", font=("맑은 고딕", 7), fg="#c0392b",
                          command=lambda x=idx: self._del_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="전체등록", font=("맑은 고딕", 7),
                          command=lambda x=idx: self._reg_slot(x)).pack(side="right", padx=(0,4))
                tk.Button(row, text="②등록", font=("맑은 고딕", 7), width=5,
                          command=lambda x=idx: self._reg_slot_step(x, 1)).pack(side="left", padx=(0,2))
                tk.Button(row, text="①등록", font=("맑은 고딕", 7), width=5,
                          command=lambda x=idx: self._reg_slot_step(x, 0)).pack(side="left", padx=(0,2))
                if idx == 4:
                    tk.Button(row, text="③등록", font=("맑은 고딕", 7), width=5,
                              command=lambda x=idx: self._reg_slot_step(x, 2)).pack(side="left", padx=(0,2))

        # 클릭 실행 버튼
        cr = tk.Frame(parent); cr.pack(pady=4)
        self.btn_click_run = tk.Button(cr, text="▶  클릭 실행 (32번)",
            font=("맑은 고딕", 9, "bold"), bg="#2980b9", fg="white",
            activebackground="#1a5e8a", width=16, height=2, command=self._start_click)
        self.btn_click_run.pack(side="left", padx=(0, 3))
        self.btn_click_stop = tk.Button(cr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_click_stop", True) or
                            self.status.set("클릭 멈추는 중..."),
            state="disabled")
        self.btn_click_stop.pack(side="left")

    def _build_winmgmt(self, parent):
        """배열창 재배치 — 좌측 전체 관리 버튼 열 + 슬롯별(01~16) 개별 재배치 그리드.
        그리드는 세로(열 우선) 번호: 01~04가 첫 열, 05~08이 둘째 열…"""
        # 좌측: 전체 창 관리 버튼 열 (다야 수량 컨트롤 열과 동일 형식)
        ctrl = tk.Frame(parent); ctrl.pack(side="left", padx=(4,8), anchor="n")
        tk.Label(ctrl, text="🪟 배열창 재배치", font=("맑은 고딕", 9, "bold"),
                 fg="#2c3e50").pack(anchor="w")
        for text, color, cmd in [
            ("📍 위치 전체저장", "#5d6d7e", self._save_all_window_pos),
            ("📐 창 전체복원",   "#1a5276", self._restore_all_windows),
            ("🔢 번호 재지정",   "#7d3c98", self._renumber_windows),
            ("📷 이름 영역등록", "#b7770d", self._reg_name_area),
            ("🔍 이름 자동인식", "#1e8449", self._ocr_all_names),
        ]:
            tk.Button(ctrl, text=text, font=("맑은 고딕", 7, "bold"),
                      bg=color, fg="white", width=12,
                      command=cmd).pack(fill="x", pady=1)

        # 우측: 슬롯별 재배치 그리드 (세로 번호 배치)
        wg = tk.Frame(parent); wg.pack(side="left", anchor="n")
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg); cell.grid(row=r, column=c, padx=6, pady=5)
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#888").pack()
            tk.Button(cell, text="재배치", font=("맑은 고딕", 7, "bold"),
                      bg="#1a5276", fg="white", width=6,
                      command=lambda x=idx: self._restore_single_window(x)).pack()

    def _build_return_grid(self, parent):
        """귀환주문서 슬롯별 실행 그리드 (좌표는 섬/던전 실행기에서 관리, 여기선 실행만).
        배열창 재배치와 동일한 세로(열 우선) 번호 배치."""
        tk.Label(parent, text="📜 귀환주문서", font=("맑은 고딕", 9, "bold"),
                 fg="#2c3e50").pack(anchor="w", pady=(0, 2))
        wg = tk.Frame(parent); wg.pack(anchor="w")
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg); cell.grid(row=r, column=c, padx=6, pady=5)
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#888").pack()
            tk.Button(cell, text="실행", font=("맑은 고딕", 7, "bold"),
                      bg="#c0392b", fg="white", width=6,
                      command=lambda x=idx: self._run_return_slot(x)).pack()

    def _run_return_slot(self, slot_idx):
        """귀환주문서(섬/던전 실행기의 컬럼) 슬롯 하나만 메인 런처에서 단독 실행."""
        if getattr(self, "_return_running", False):
            self.status.set("귀환주문서 실행 중입니다"); return
        ipath = os.path.join(BASE, "island_coords.json")
        try:
            with open(ipath, encoding="utf-8") as f:
                icfg = json.load(f)
        except Exception:
            self.status.set("island_coords.json 을 찾을 수 없습니다"); return
        slots = icfg.get("귀환주문서", [])
        if slot_idx >= len(slots) or not any(c for c in slots[slot_idx].get("coords", [])):
            self.status.set(f"귀환주문서 #{slot_idx+1:02d} — 등록된 좌표 없음 (섬/던전 실행기에서 등록)")
            return
        name   = slots[slot_idx].get("name", f"#{slot_idx+1}")
        coords = slots[slot_idx].get("coords", [])
        if not self._try_busy_or_queue("귀환주문서", lambda: self._run_return_slot(slot_idx),
                                       label=f"귀환주문서 #{slot_idx+1:02d}"): return
        self._return_running = True
        self._return_stop    = False
        self.status.set(f"2초 후 귀환주문서 [{name}] 실행...")
        self._minimize_claude()
        self.iconify()
        threading.Thread(target=self._run_task,
                         args=("귀환주문서", self._run_return_worker, name, coords), daemon=True).start()

    def _run_return_worker(self, name, coords):
        CLICK_INTERVAL = 2.0   # island 실행 간격과 동일 (클릭 사이 대기)
        SETTLE_DELAY   = 0.7   # 좌표 이동 후 클릭 전 대기 (씹힘 방지)
        try:
            time.sleep(2)
            for j, c in enumerate(coords):
                if getattr(self, "_return_stop", False):
                    break
                if not c:
                    continue
                self.after(0, lambda n=name, j=j: self.status.set(f"🌀 귀환주문서 [{n}] 클릭{j+1}..."))
                pyautogui.moveTo(*c)
                time.sleep(SETTLE_DELAY)     # 커서 안착 후 클릭 → 씹힘 방지
                pyautogui.click()
                time.sleep(CLICK_INTERVAL + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.after(0, lambda n=name: self.status.set(f"✔ 귀환주문서 [{n}] 완료"))
        except Exception as e:
            self.after(0, lambda e=e: self.status.set(f"귀환주문서 오류: {e}"))
        finally:
            self._return_running = False
            self.after(0, self._raise_main)

    ACC_TYPES  = ["구글",    "NC",      "전번",    "페이스북"]
    ACC_COLORS = ["#DB4437", "#e67e22", "#27ae60", "#6c3483"]

    def _acc_color_for(self, idx, val):
        """계정 유형 OptionMenu 배경색 갱신 (창이 열려 있을 때만)."""
        if idx >= len(self._acc_type_btns):
            return
        om = self._acc_type_btns[idx]
        if om is None:
            return
        try:
            om.config(bg=self.ACC_COLORS[self.ACC_TYPES.index(val)
                                         if val in self.ACC_TYPES else 0])
        except Exception:
            pass

    def _build_accounts(self, parent):
        """🔑 계정 관리 — 16칸 그리드 (별도 창). 유형 색상은 생성자 command로 갱신(누적 없음)."""
        acc_title = tk.Frame(parent); acc_title.pack(fill="x", padx=4, pady=(4,0))
        tk.Label(acc_title, text="🔑 계정 관리", font=("맑은 고딕", 9, "bold"), fg="#2c3e50").pack(side="left")
        tk.Button(acc_title, text="초기화", font=("맑은 고딕", 7), bg="#c0392b", fg="white",
                  command=self._clear_accounts).pack(side="right", padx=(2,0))
        tk.Button(acc_title, text="전체저장", font=("맑은 고딕", 7), bg="#27ae60", fg="white",
                  command=self._save_accounts).pack(side="right")

        TYPES, TYPE_COLORS = self.ACC_TYPES, self.ACC_COLORS
        acc_grid = tk.Frame(parent); acc_grid.pack(pady=(2,4), padx=4)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(acc_grid, bd=1, relief="groove", padx=2, pady=1)
                cell.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                top = tk.Frame(cell); top.pack(anchor="w")
                tk.Label(top, text=f"{idx+1:02d}", font=("맑은 고딕", 7, "bold"), fg="#888").pack(side="left")
                t = self._acc_type_vars[idx].get()
                om = tk.OptionMenu(top, self._acc_type_vars[idx], *TYPES,
                                   command=lambda val, i=idx: self._acc_color_for(i, val))
                om.config(font=("맑은 고딕", 7, "bold"), fg="white", width=6,
                          bg=TYPE_COLORS[TYPES.index(t) if t in TYPES else 0],
                          activebackground="#555", pady=0, relief="raised",
                          highlightthickness=0)
                for ti, (tn, tc) in enumerate(zip(TYPES, TYPE_COLORS)):
                    om["menu"].entryconfig(ti, background=tc, foreground="white",
                                          activebackground=tc, activeforeground="white",
                                          font=("맑은 고딕", 9, "bold"))
                om.pack(side="left", padx=(2,0))
                self._acc_type_btns[idx] = om
                for j in range(5):
                    tk.Entry(cell, textvariable=self._acc_vars[idx][j],
                             font=("맑은 고딕", 8), width=12).pack(fill="x", pady=(0,0))

    # ── 아이템 리롤(새로고침 매크로) ─────────────────────────────────
    def _reroll_targets_cfg(self):
        """reroll_targets 를 4칸으로 보정해 반환 (없으면 생성)."""
        t = list(self.cfg.get("reroll_targets") or [])
        while len(t) < 4:
            t.append({"enabled": False})
        self.cfg["reroll_targets"] = t
        return t

    def _reroll_reg_label(self):
        def mk(k): return "✔" if self.cfg.get(k) else "✕"
        return (f"새로고침 {mk('reroll_refresh_btn')}   확인 {mk('reroll_confirm_btn')}   "
                f"영역 {mk('reroll_item_area')}")

    def _build_reroll(self, parent):
        """🔨 아이템 리롤 — 새로고침 반복 → 타깃 아이템 발견 시 정지 + 확인 자동클릭."""
        targets = self._reroll_targets_cfg()

        self._reroll_status_var = tk.StringVar(value="상태: 대기 중")
        self._reroll_status_lbl = tk.Label(parent, textvariable=self._reroll_status_var,
            font=("맑은 고딕", 12, "bold"), fg="#c0392b", wraplength=400, justify="center")
        self._reroll_status_lbl.pack(pady=(8, 4))

        reg = tk.LabelFrame(parent, text="등록", font=("맑은 고딕", 8, "bold"))
        reg.pack(fill="x", padx=8, pady=4)
        r1 = tk.Frame(reg); r1.pack(fill="x", pady=2)
        tk.Button(r1, text="🖱 새로고침 버튼", font=("맑은 고딕", 8), width=13,
                  command=lambda: self._reg_reroll_point("reroll_refresh_btn", "새로고침 버튼")).pack(side="left", padx=2)
        tk.Button(r1, text="🖱 확인 버튼", font=("맑은 고딕", 8), width=11,
                  command=lambda: self._reg_reroll_point("reroll_confirm_btn", "확인(획득) 버튼")).pack(side="left", padx=2)
        tk.Button(r1, text="📷 아이템 영역", font=("맑은 고딕", 8), width=11,
                  command=self._reg_reroll_area).pack(side="left", padx=2)
        self._reroll_reg_var = tk.StringVar(value=self._reroll_reg_label())
        tk.Label(reg, textvariable=self._reroll_reg_var, font=("맑은 고딕", 8), fg="#555").pack(anchor="w", padx=4, pady=(2,2))

        tgt = tk.LabelFrame(parent, text="노릴 아이템 (체크=감시 / 📷=드래그로 아이콘 지정해 저장)",
                            font=("맑은 고딕", 8, "bold"))
        tgt.pack(fill="x", padx=8, pady=4)
        self._reroll_enable_vars = []
        self._reroll_thumb_lbls  = [None] * 4
        _changed = False
        for i in range(4):
            row = tk.Frame(tgt); row.pack(fill="x", pady=2)
            img_exists = os.path.exists(os.path.join(REROLL_DIR, f"target_{i+1}.png"))
            ev = tk.BooleanVar(value=img_exists)   # 이미지가 있으면 기본 감시 ON
            if targets[i].get("enabled") != img_exists:
                targets[i]["enabled"] = img_exists; _changed = True
            self._reroll_enable_vars.append(ev)
            tk.Checkbutton(row, text=f"{i+1}번", variable=ev, font=("맑은 고딕", 9, "bold"),
                           command=lambda x=i: self._toggle_reroll_target(x)).pack(side="left")
            tk.Button(row, text="📷 캡처", font=("맑은 고딕", 8), width=6,
                      command=lambda x=i: self._capture_reroll_target(x)).pack(side="left", padx=4)
            thumb = tk.Label(row, bd=1, relief="groove", width=9, height=2, text="없음",
                             font=("맑은 고딕", 7), fg="#aaa")
            thumb.pack(side="left", padx=4)
            self._reroll_thumb_lbls[i] = thumb
        self._reroll_load_thumbs()
        if _changed:
            save_cfg(self.cfg)

        cf = tk.Frame(parent); cf.pack(fill="x", padx=8, pady=4)
        tk.Label(cf, text="유사도(0~1):", font=("맑은 고딕", 8)).pack(side="left")
        self._reroll_thr_var = tk.StringVar(value=str(self.cfg.get("reroll_threshold", 0.90)))
        tk.Entry(cf, textvariable=self._reroll_thr_var, width=5, font=("맑은 고딕", 8)).pack(side="left", padx=(2,10))
        tk.Label(cf, text="새로고침 후 대기(초):", font=("맑은 고딕", 8)).pack(side="left")
        self._reroll_wait_var = tk.StringVar(value=str(self.cfg.get("reroll_wait", 1.0)))
        tk.Entry(cf, textvariable=self._reroll_wait_var, width=5, font=("맑은 고딕", 8)).pack(side="left", padx=2)
        tk.Button(cf, text="설정 저장", font=("맑은 고딕", 8), command=self._save_reroll_cfg).pack(side="left", padx=6)

        run = tk.Frame(parent); run.pack(pady=10)
        tk.Button(run, text="▶ 매크로 시작", font=("맑은 고딕", 11, "bold"),
                  bg="#27ae60", fg="white", width=12, height=2,
                  command=self._start_reroll).pack(side="left", padx=4)
        tk.Button(run, text="■ 매크로 종료", font=("맑은 고딕", 11, "bold"),
                  bg="#c0392b", fg="white", width=12, height=2,
                  command=self._stop_reroll).pack(side="left", padx=4)

    def _reroll_load_thumbs(self):
        from PIL import Image as _Img, ImageTk as _ITk
        for i in range(4):
            lbl = self._reroll_thumb_lbls[i] if hasattr(self, "_reroll_thumb_lbls") else None
            if lbl is None or not lbl.winfo_exists():
                continue
            p = os.path.join(REROLL_DIR, f"target_{i+1}.png")
            if os.path.exists(p):
                try:
                    im = _Img.open(p)
                    w0, h0 = im.size
                    # 작은 캡처는 2배 확대해 잘 보이게, 큰 건 상한(150×110)으로 축소
                    if max(w0, h0) < 90:
                        im = im.resize((w0 * 2, h0 * 2))
                    im.thumbnail((150, 110))
                    ph = _ITk.PhotoImage(im)
                    self._reroll_thumbs[i] = ph
                    # 이미지가 있으면 width/height 는 '픽셀'로 해석되므로 이미지 크기로 지정
                    lbl.config(image=ph, text="", width=im.width, height=im.height)
                except Exception:
                    lbl.config(image="", text="?", width=9, height=2)
            else:
                lbl.config(image="", text="없음", width=9, height=2)

    def _toggle_reroll_target(self, idx):
        t = self._reroll_targets_cfg()
        t[idx]["enabled"] = bool(self._reroll_enable_vars[idx].get())
        save_cfg(self.cfg)

    def _save_reroll_cfg(self):
        if not hasattr(self, "_reroll_thr_var"):
            return
        try:
            self.cfg["reroll_threshold"] = max(0.1, min(1.0, float(self._reroll_thr_var.get())))
        except Exception:
            self.cfg["reroll_threshold"] = 0.90
        try:
            self.cfg["reroll_wait"] = max(0.1, float(self._reroll_wait_var.get()))
        except Exception:
            self.cfg["reroll_wait"] = 1.0
        save_cfg(self.cfg)
        self.status.set(f"✔ 리롤 설정 저장 (유사도 {self.cfg['reroll_threshold']}, 대기 {self.cfg['reroll_wait']}초)")

    def _reg_reroll_point(self, key, label):
        self._reroll_reg_key = key
        self.status.set(f"3초 후 [{label}] 위치를 클릭하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollPointOverlay(self, label, self._on_reroll_point))])

    def _on_reroll_point(self, x, y):
        self.cfg[self._reroll_reg_key] = [x, y]
        save_cfg(self.cfg)
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if hasattr(self, "_reroll_reg_var"):
                self._reroll_reg_var.set(self._reroll_reg_label())
        self.status.set(f"✔ 좌표 등록 완료 ({x},{y})")

    def _reg_reroll_area(self):
        self.status.set("3초 후 아이템 이미지 영역을 드래그하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollAreaOverlay(self, self._on_reroll_area))])

    def _on_reroll_area(self, x, y, w, h):
        self.cfg["reroll_item_area"] = {"x": x, "y": y, "w": w, "h": h}
        save_cfg(self.cfg)
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if hasattr(self, "_reroll_reg_var"):
                self._reroll_reg_var.set(self._reroll_reg_label())
        self.status.set(f"✔ 아이템 영역 등록 ({x},{y} / {w}×{h})")

    def _capture_reroll_target(self, idx):
        """노릴 아이템 캡처 — 화면에서 직접 드래그로 아이콘 영역을 지정해 저장."""
        self.status.set(f"3초 후 {idx+1}번 타깃: 원하는 아이템 아이콘을 드래그하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollAreaOverlay(
                self,
                lambda x, y, w, h: self._on_reroll_target_area(idx, x, y, w, h),
                label=f"{idx+1}번 타깃 — 원하는 아이템 아이콘을 드래그하세요"))])

    def _on_reroll_target_area(self, idx, x, y, w, h):
        if w < 3 or h < 3:
            self.deiconify()
            if self._reroll_win and self._reroll_win.winfo_exists():
                self._reroll_win.deiconify()
            self.status.set("영역이 너무 작습니다. 다시 시도하세요"); return
        time.sleep(0.2)   # 오버레이가 완전히 사라진 뒤 캡처
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
            os.makedirs(REROLL_DIR, exist_ok=True)
            img.save(os.path.join(REROLL_DIR, f"target_{idx+1}.png"))
            t = self._reroll_targets_cfg(); t[idx]["enabled"] = True
            save_cfg(self.cfg)
            msg = f"✔ {idx+1}번 타깃 캡처 완료 ({w}×{h})"
        except Exception as e:
            msg = f"{idx+1}번 캡처 오류: {e}"
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if idx < len(getattr(self, "_reroll_enable_vars", [])):
                self._reroll_enable_vars[idx].set(True)
            self._reroll_load_thumbs()
        self.status.set(msg)

    def _reroll_status(self, text, color="#c0392b"):
        if hasattr(self, "_reroll_status_var"):
            self._reroll_status_var.set(text)
        if hasattr(self, "_reroll_status_lbl") and self._reroll_status_lbl.winfo_exists():
            self._reroll_status_lbl.config(fg=color)
        self.status.set(text)

    def _start_reroll(self):
        if self._reroll_running:
            self.status.set("이미 리롤 실행 중입니다"); return
        self._save_reroll_cfg()
        if not self.cfg.get("reroll_refresh_btn"):
            self._reroll_status("새로고침 버튼을 먼저 등록하세요", "#c0392b"); return
        if not self.cfg.get("reroll_item_area"):
            self._reroll_status("아이템 영역을 먼저 등록하세요", "#c0392b"); return
        enabled = [i for i in range(4)
                   if self._reroll_targets_cfg()[i].get("enabled")
                   and os.path.exists(os.path.join(REROLL_DIR, f"target_{i+1}.png"))]
        if not enabled:
            self._reroll_status("노릴 아이템(타깃 이미지)을 1개 이상 캡처/체크하세요", "#c0392b"); return
        self._reroll_running = True
        self._reroll_status("리롤 시작...", "#2c3e50")
        threading.Thread(target=self._reroll_loop, daemon=True).start()

    def _stop_reroll(self):
        self._reroll_running = False
        self._reroll_status("리롤 정지", "#555")

    def _reroll_loop(self):
        try:
            import cv2, numpy as np
            from PIL import ImageGrab
        except Exception as e:
            self.after(0, lambda: self._reroll_status(f"라이브러리 오류: {e}", "#c0392b"))
            self._reroll_running = False; return
        area    = self.cfg.get("reroll_item_area")
        refresh = self.cfg.get("reroll_refresh_btn")
        confirm = self.cfg.get("reroll_confirm_btn")
        thr     = float(self.cfg.get("reroll_threshold", 0.90))
        wait    = float(self.cfg.get("reroll_wait", 1.0))
        templates = []
        for i in range(4):
            if not self._reroll_targets_cfg()[i].get("enabled"):
                continue
            p = os.path.join(REROLL_DIR, f"target_{i+1}.png")
            if os.path.exists(p):
                im = cv2.imread(p)
                if im is not None:
                    templates.append((i, im))
        if not templates:
            self.after(0, lambda: self._reroll_status("타깃 이미지 없음", "#c0392b"))
            self._reroll_running = False; return
        x, y, w, h = area["x"], area["y"], area["w"], area["h"]
        count = 0
        while self._reroll_running:
            try:
                pil = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True).convert("RGB")
                cur = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            except Exception as e:
                self.after(0, lambda e=e: self._reroll_status(f"캡처 오류: {e}", "#c0392b"))
                break
            best_i, best_s = -1, -1.0
            ch, cw = cur.shape[:2]
            for i, tmpl in templates:
                th, tw = tmpl.shape[:2]
                t = tmpl
                if th > ch or tw > cw:
                    # 템플릿이 검색영역보다 크면 맞게 축소 (matchTemplate 요구조건)
                    sc = min(ch / th, cw / tw)
                    t = cv2.resize(tmpl, (max(1, int(tw*sc)), max(1, int(th*sc))))
                try:
                    score = float(cv2.matchTemplate(cur, t, cv2.TM_CCOEFF_NORMED).max())
                except Exception:
                    score = -1.0
                if score > best_s:
                    best_s, best_i = score, i
            self.after(0, lambda c=count, s=best_s: self._reroll_status(
                f"검색 중…  {c}회  (최고 유사도 {s:.3f})", "#2c3e50"))
            if best_s >= thr:
                self.after(0, lambda i=best_i, s=best_s: self._reroll_status(
                    f"상태: {i+1}번 아이템 발견!!!  (유사도 {s:.3f})", "#c0392b"))
                self._reroll_found(confirm)
                self._reroll_running = False
                break
            if refresh:
                try: pyautogui.click(refresh[0], refresh[1])
                except Exception: pass
            count += 1
            t0 = time.time()
            while self._reroll_running and time.time() - t0 < wait:
                time.sleep(0.05)
        if not self._reroll_running:
            self.after(0, lambda: self._reroll_status("리롤 종료", "#555"))

    def _reroll_found(self, confirm):
        # 발견 시: 확인(획득) 버튼 자동 클릭 → 소리 알림 → 런처 앞으로
        if confirm:
            time.sleep(0.3)
            try: pyautogui.click(confirm[0], confirm[1])
            except Exception: pass
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 180); time.sleep(0.06)
        except Exception:
            pass
        self.after(0, self._keep_launcher_front)
        if self._reroll_win and self._reroll_win.winfo_exists():
            self.after(0, lambda: (self._reroll_win.deiconify(), self._reroll_win.lift()))

    def _build_right(self, parent):
        tk.Label(parent, text=f"사냥  (슬롯당 {HUNT_CLICKS}번 클릭 / {HUNT_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#27ae60").pack(anchor="w", padx=4, pady=(4,2))

        hr = tk.Frame(parent); hr.pack(pady=3)
        self.btn_hunt_run = tk.Button(hr, text="▶  사냥 실행",
            font=("맑은 고딕", 9, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=13, height=2, command=self._start_hunt)
        self.btn_hunt_run.pack(side="left", padx=(0, 3))
        self.btn_hunt_stop = tk.Button(hr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_hunt_stop", True) or
                            self.status.set("사냥 멈추는 중..."),
            state="disabled")
        self.btn_hunt_stop.pack(side="left")
        tk.Button(hr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#8e44ad", fg="white", width=18,
            command=self._group_copy_hunt).pack(side="left", padx=(8,0))
        # 전체 창 관리 버튼(위치저장/창복원/번호재지정/이름영역/이름인식)은
        # 메인 앞쪽 "🪟 배열창 재배치" 좌측 열(_build_winmgmt)로 이동됨

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        outer = tk.Frame(parent); outer.pack(fill="x", padx=2)
        canvas = tk.Canvas(outer, highlightthickness=0, width=484, height=500)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._hunt_frame = tk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=self._hunt_frame, anchor="nw")
        self._hunt_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(fid, width=e.width))

        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_wheel)
        self._hunt_frame.bind("<MouseWheel>", _on_wheel)

        self._hunt_name_vars  = []
        self._hunt_click_vars = []   # [slot][click] StringVar
        self._hunt_click_btns = []   # [slot][click] Button 위젯
        self._hunt_assign_btns = []  # 지정 버튼 참조
        self._hunt_enable_btns = []  # 슬롯 ON/OFF 버튼 참조
        self._hunt_coord_sv   = []   # 좌표 요약 StringVar
        self._hunt_detail_frames = [] # 접이식 상세 frame
        self._hunt_row_frames = []    # row 참조 (detail after= 용)

        for i in range(HUNT_SLOTS):
            row = tk.Frame(self._hunt_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=4)
            self._hunt_row_frames.append(row)

            # 접이식 상세 frame (기본 숨김)
            detail = tk.Frame(self._hunt_frame, bg="#ecf0f1", bd=1, relief="flat")
            self._hunt_detail_frames.append(detail)

            # 지정 버튼
            aw = self.cfg.get("hunt_slots", [{}]*HUNT_SLOTS)[i].get("assigned_window") if i < len(self.cfg.get("hunt_slots",[])) else None
            assign_bg = "#27ae60" if aw else "#8e44ad"
            assign_txt = "✔지정" if aw else "지정"
            btn_assign = tk.Button(row, text=assign_txt, font=("맑은 고딕", 7), width=4,
                      bg=assign_bg, fg="white", pady=0,
                      command=lambda x=i: self._assign_window(x))
            btn_assign.pack(side="left", padx=(2,1))
            self._hunt_assign_btns.append(btn_assign)
            tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                      bg="#566573", fg="white", pady=0,
                      command=lambda x=i: self._preview_assigned_window(x)).pack(side="left", padx=(0,1))
            tk.Button(row, text="📍", font=("맑은 고딕", 7), width=2,
                      bg="#5d6d7e", fg="white", pady=0,
                      command=lambda x=i: self._save_window_pos(x)).pack(side="left", padx=(0,1))
            tk.Button(row, text="📐", font=("맑은 고딕", 7), width=2,
                      bg="#2c3e50", fg="white", pady=0,
                      command=lambda x=i: self._restore_single_window(x)).pack(side="left", padx=(0,1))
            # 슬롯 ON/OFF (OFF면 사냥/전체실행에서 건너뜀)
            en = self.cfg.get("hunt_slots", [{}]*HUNT_SLOTS)[i].get("enabled", True) if i < len(self.cfg.get("hunt_slots",[])) else True
            eb = tk.Button(row, text="ON" if en else "OFF", font=("맑은 고딕", 7, "bold"), width=4,
                           bg="#27ae60" if en else "#95a5a6", fg="white", pady=0,
                           command=lambda x=i: self._toggle_hunt_enable(x))
            eb.pack(side="left", padx=(2,1))
            self._hunt_enable_btns.append(eb)
            # 번호 + 이름
            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=4).pack(side="left", padx=(2,0))
            nv = tk.StringVar()
            self._hunt_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=(2,2))
            ent.bind("<FocusOut>", lambda e, x=i: self._save_hunt_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_hunt_name(x))

            # 좌표 접이식 버튼 (요약 표시)
            coords_saved = self.cfg.get("hunt_slots", [{}]*HUNT_SLOTS)[i].get("coords", []) if i < len(self.cfg.get("hunt_slots",[])) else []
            reg_count = sum(1 for c in coords_saved if c)
            coord_sv = tk.StringVar(value=f"좌표 {reg_count}/{HUNT_CLICKS} ▾")
            self._hunt_coord_sv.append(coord_sv)
            tk.Button(row, textvariable=coord_sv, font=("맑은 고딕", 7),
                      bg="#2980b9", fg="white", width=8, pady=0,
                      command=lambda x=i: self._toggle_hunt_detail(x)).pack(side="left", padx=(2,2))

            # 접이식 내부: 1~5 버튼
            click_vars = []
            click_btns = []
            for j in range(HUNT_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                cell = tk.Frame(detail, bg="#ecf0f1")
                cell.pack(side="left", padx=4, pady=3)
                tk.Label(cell, text=f"클릭{j+1}", font=("맑은 고딕", 7),
                         fg="#555", bg="#ecf0f1").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 7),
                                width=4, pady=1,
                                command=lambda x=i, c=j: self._reg_hunt_click(x, c))
                btn.pack()
                click_btns.append(btn)
            self._hunt_click_vars.append(click_vars)
            self._hunt_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_wheel)
            row.bind("<MouseWheel>", _on_wheel)
            detail.bind("<MouseWheel>", _on_wheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_hunt_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 8), width=2,
                      command=lambda x=i: self._preview_hunt(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_hunt(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#27ae60", width=2,
                      command=lambda x=i: self._test_hunt(x)).pack(side="right", padx=(0,2))

        # 창 열릴 때 cfg 값으로 즉시 초기화
        for i in range(HUNT_SLOTS):
            h = self.cfg["hunt_slots"][i]
            self._hunt_name_vars[i].set(h.get("name", "미등록"))
            coords = h.get("coords", [None]*HUNT_CLICKS)
            for j in range(HUNT_CLICKS):
                c = coords[j] if j < len(coords) else None
                self._hunt_click_vars[i][j].set("✔" if c else "✗")
                self._hunt_click_btns[i][j].config(
                    fg="white" if c else "#aaa",
                    bg="#27ae60" if c else "#7f8c8d")

        # 창 크기 고정
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=(6,2))
        lf = tk.LabelFrame(parent, text="🔒 창 크기 고정", font=("맑은 고딕", 8, "bold"),
                           padx=4, pady=4)
        lf.pack(fill="x", padx=4, pady=(0,4))
        self._lock_status_var = tk.StringVar(value="고정 꺼짐")
        tk.Label(lf, textvariable=self._lock_status_var, font=("맑은 고딕", 8),
                 fg="#888", anchor="w").pack(fill="x")
        btn_row = tk.Frame(lf); btn_row.pack(fill="x", pady=(3,0))
        self._btn_lock = tk.Button(btn_row, text="리니지M 창 고정",
            font=("맑은 고딕", 8, "bold"), bg="#2980b9", fg="white", width=14,
            command=self._lock_lineagem_window)
        self._btn_lock.pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="고정 해제", font=("맑은 고딕", 8),
            bg="#7f8c8d", fg="white", width=8,
            command=self._unlock_lineagem_window).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="⏸ 10분 임시해제", font=("맑은 고딕", 8),
            bg="#e67e22", fg="white", width=13,
            command=self._pause_lock).pack(side="left")

    def _lock_lineagem_window(self):
        candidates = []
        def enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return
            t = win32gui.GetWindowText(hwnd)
            if not t: return
            tl = t.lower()
            if any(k in tl for k in ("lineagem", "리니지m", "lineage m", "ncsoft")):
                candidates.append(hwnd)
        win32gui.EnumWindows(enum_cb, None)

        if not candidates:
            # 창 제목 목록 팝업으로 보여주기
            self._pick_window_dialog()
            return

        self._win_lock.lock_all(candidates)
        self._lock_status_var.set(f"리사이즈 차단 ON — {len(candidates)}개 창")
        self._btn_lock.config(bg="#27ae60")

    def _pick_window_dialog(self):
        """창 목록을 팝업으로 보여주고 선택해서 고정."""
        wins = []
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if t: wins.append((hwnd, t))
        win32gui.EnumWindows(enum_cb, None)

        dlg = tk.Toplevel(self)
        dlg.title("창 선택"); dlg.geometry("500x400"); dlg.grab_set()
        tk.Label(dlg, text="리니지M 창이 자동으로 감지되지 않았습니다.\n고정할 창을 선택하세요 (Ctrl+클릭으로 다중 선택):",
                 font=("맑은 고딕", 9), justify="left").pack(padx=8, pady=(8,4), anchor="w")
        lb = tk.Listbox(dlg, selectmode="extended", font=("맑은 고딕", 8), height=16)
        lb.pack(fill="both", expand=True, padx=8, pady=4)
        for hwnd, title in wins:
            lb.insert("end", f"[{hwnd}] {title}")

        def _apply():
            sel = lb.curselection()
            if not sel: return
            chosen = [wins[i][0] for i in sel]
            self._win_lock.lock_all(chosen)
            self._lock_status_var.set(f"리사이즈 차단 ON — {len(chosen)}개 창")
            self._btn_lock.config(bg="#27ae60")
            dlg.destroy()

        tk.Button(dlg, text="선택 고정", font=("맑은 고딕", 9, "bold"),
                  bg="#2980b9", fg="white", command=_apply).pack(pady=6)

    def _unlock_lineagem_window(self):
        self._win_lock.unlock()
        self._lock_status_var.set("고정 꺼짐")
        self._btn_lock.config(bg="#2980b9")

    def _pause_lock(self):
        if not self._win_lock.is_locked():
            return
        self._win_lock.pause(600)
        self._lock_status_var.set("⏸ 임시 해제 중 (10분)...")
        self.after(600000, lambda: self._lock_status_var.set(
            f"리사이즈 차단 ON — {len(self._win_lock._locks)}개 창") if self._win_lock.is_locked() else None)

    def _build_mail(self, parent):
        tk.Label(parent, text=f"우편함  (슬롯당 {MAIL_CLICKS}번 클릭 / {MAIL_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#8e44ad").pack(anchor="w", padx=4, pady=(4,2))

        mr = tk.Frame(parent); mr.pack(pady=3)
        self._mail_stop = False
        self.btn_mail_run = tk.Button(mr, text="▶  우편함 실행",
            font=("맑은 고딕", 9, "bold"), bg="#8e44ad", fg="white",
            activebackground="#6c3483", width=13, height=2,
            command=self._start_mail)
        self.btn_mail_run.pack(side="left", padx=(0,3))
        self.btn_mail_stop = tk.Button(mr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2, state="disabled",
            command=self._stop_mail)
        self.btn_mail_stop.pack(side="left", padx=(0,6))
        tk.Button(mr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#6c3483", fg="white", width=18,
            command=self._group_copy_mail).pack(side="left", padx=(4,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        m_outer = tk.Frame(parent); m_outer.pack(fill="both", expand=True, padx=2)
        m_canvas = tk.Canvas(m_outer, highlightthickness=0)
        m_sb = tk.Scrollbar(m_outer, orient="vertical", command=m_canvas.yview)
        m_canvas.configure(yscrollcommand=m_sb.set)
        m_sb.pack(side="right", fill="y")
        m_canvas.pack(side="left", fill="both", expand=True)
        self._mail_frame = tk.Frame(m_canvas)
        m_fid = m_canvas.create_window((0,0), window=self._mail_frame, anchor="nw")
        self._mail_frame.bind("<Configure>",
            lambda e: m_canvas.configure(scrollregion=m_canvas.bbox("all")))
        m_canvas.bind("<Configure>",
            lambda e: m_canvas.itemconfig(m_fid, width=e.width))

        def _on_mwheel(e):
            m_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        m_canvas.bind("<MouseWheel>", _on_mwheel)
        self._mail_frame.bind("<MouseWheel>", _on_mwheel)

        self._mail_name_vars  = []
        self._mail_click_vars = []
        self._mail_click_btns = []
        self._mail_coord_sv   = []
        self._mail_detail_frames = []
        self._mail_row_frames = []

        for i in range(MAIL_SLOTS):
            row = tk.Frame(self._mail_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=4)
            self._mail_row_frames.append(row)
            detail = tk.Frame(self._mail_frame, bg="#ecf0f1", bd=1, relief="flat")
            self._mail_detail_frames.append(detail)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 7, "bold"),
                     width=3).pack(side="left", padx=(2,0))
            nv = tk.StringVar()
            self._mail_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=2)
            ent.bind("<FocusOut>", lambda e, x=i: self._save_mail_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_mail_name(x))

            mail_saved = self.cfg.get("mail_slots", [{}]*MAIL_SLOTS)[i].get("coords", []) if i < len(self.cfg.get("mail_slots",[])) else []
            mail_reg = sum(1 for c in mail_saved if c)
            msv = tk.StringVar(value=f"좌표 {mail_reg}/{MAIL_CLICKS} ▾")
            self._mail_coord_sv.append(msv)
            tk.Button(row, textvariable=msv, font=("맑은 고딕", 7),
                      bg="#8e44ad", fg="white", width=8, pady=0,
                      command=lambda x=i: self._toggle_mail_detail(x)).pack(side="left", padx=(2,2))

            click_vars = []
            click_btns = []
            for j in range(MAIL_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                cell = tk.Frame(detail, bg="#ecf0f1")
                cell.pack(side="left", padx=4, pady=3)
                tk.Label(cell, text=f"클릭{j+1}", font=("맑은 고딕", 7),
                         fg="#555", bg="#ecf0f1").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 7),
                                width=4, pady=1,
                                command=lambda x=i, c=j: self._reg_mail_click(x, c))
                btn.pack()
                click_btns.append(btn)
            self._mail_click_vars.append(click_vars)
            self._mail_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_mwheel)
            row.bind("<MouseWheel>", _on_mwheel)
            detail.bind("<MouseWheel>", _on_mwheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_mail_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 8), width=2,
                      command=lambda x=i: self._preview_mail(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#8e44ad", width=2,
                      command=lambda x=i: self._test_mail(x)).pack(side="right", padx=(0,1))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_mail(x)).pack(side="right", padx=2)

        # 창 열릴 때 cfg 값으로 즉시 초기화
        for i in range(MAIL_SLOTS):
            m = self.cfg["mail_slots"][i]
            self._mail_name_vars[i].set(m.get("name", "미등록"))
            coords = m.get("coords", [None]*MAIL_CLICKS)
            for j in range(MAIL_CLICKS):
                c = coords[j] if j < len(coords) else None
                self._mail_click_vars[i][j].set("✔" if c else "✗")
                self._mail_click_btns[i][j].config(
                    fg="white" if c else "#aaa",
                    bg="#27ae60" if c else "#7f8c8d")

    def _build_dungeon(self, parent):
        tk.Label(parent, text=f"주말던전  (메뉴→{DUNGEON_HOVER}초→클릭×2)",
                 font=("맑은 고딕", 9, "bold"), fg="#e67e22").pack(anchor="w", padx=4, pady=(4,2))

        dr = tk.Frame(parent); dr.pack(pady=3)
        self._dungeon_stop = False
        self.btn_dungeon_run = tk.Button(dr, text="▶  던전 실행",
            font=("맑은 고딕", 9, "bold"), bg="#e67e22", fg="white",
            activebackground="#b35400", width=13, height=2,
            command=self._start_dungeon)
        self.btn_dungeon_run.pack(side="left", padx=(0,3))
        self.btn_dungeon_stop = tk.Button(dr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_dungeon_stop", True) or
                            self.status.set("던전 멈추는 중..."),
            state="disabled")
        self.btn_dungeon_stop.pack(side="left")

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        d_outer = tk.Frame(parent); d_outer.pack(fill="both", expand=True, padx=2)
        d_canvas = tk.Canvas(d_outer, highlightthickness=0)
        d_sb_y = tk.Scrollbar(d_outer, orient="vertical", command=d_canvas.yview)
        d_sb_x = tk.Scrollbar(parent, orient="horizontal", command=d_canvas.xview)
        d_canvas.configure(yscrollcommand=d_sb_y.set, xscrollcommand=d_sb_x.set)
        d_sb_x.pack(side="bottom", fill="x")
        d_sb_y.pack(side="right", fill="y")
        d_canvas.pack(side="left", fill="both", expand=True)
        self._dungeon_frame = tk.Frame(d_canvas)
        d_fid = d_canvas.create_window((0,0), window=self._dungeon_frame, anchor="nw")
        self._dungeon_frame.bind("<Configure>",
            lambda e: d_canvas.configure(scrollregion=d_canvas.bbox("all")))

        def _on_dwheel(e):
            d_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        d_canvas.bind("<MouseWheel>", _on_dwheel)
        self._dungeon_frame.bind("<MouseWheel>", _on_dwheel)

        self._dungeon_name_vars  = []
        self._dungeon_click_vars = []
        self._dungeon_click_btns = []
        self._dungeon_coord_sv   = []
        self._dungeon_detail_frames = []
        self._dungeon_row_frames = []

        LABELS_D = ["메뉴", "클릭1", "클릭2"]
        for i in range(DUNGEON_SLOTS):
            row = tk.Frame(self._dungeon_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=4)
            self._dungeon_row_frames.append(row)
            detail = tk.Frame(self._dungeon_frame, bg="#ecf0f1", bd=1, relief="flat")
            self._dungeon_detail_frames.append(detail)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 7, "bold"),
                     width=3).pack(side="left", padx=(2,0))
            nv = tk.StringVar()
            self._dungeon_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=6)
            ent.pack(side="left", padx=2)
            ent.bind("<FocusOut>", lambda e, x=i: self._save_dungeon_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_dungeon_name(x))

            dung_saved = self.cfg.get("dungeon_slots", [{}]*DUNGEON_SLOTS)[i].get("coords", []) if i < len(self.cfg.get("dungeon_slots",[])) else []
            dung_reg = sum(1 for c in dung_saved if c)
            dsv = tk.StringVar(value=f"좌표 {dung_reg}/{DUNGEON_CLICKS} ▾")
            self._dungeon_coord_sv.append(dsv)
            tk.Button(row, textvariable=dsv, font=("맑은 고딕", 7),
                      bg="#e67e22", fg="white", width=8, pady=0,
                      command=lambda x=i: self._toggle_dungeon_detail(x)).pack(side="left", padx=(2,2))

            click_vars = []
            click_btns = []
            for j in range(DUNGEON_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                cell = tk.Frame(detail, bg="#ecf0f1")
                cell.pack(side="left", padx=4, pady=3)
                tk.Label(cell, text=LABELS_D[j], font=("맑은 고딕", 7),
                         fg="#555", bg="#ecf0f1").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 7),
                                width=4, pady=1,
                                command=lambda x=i, c=j: self._reg_dungeon_click(x, c))
                btn.pack()
                click_btns.append(btn)
            self._dungeon_click_vars.append(click_vars)
            self._dungeon_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_dwheel)
            row.bind("<MouseWheel>", _on_dwheel)
            detail.bind("<MouseWheel>", _on_dwheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_dungeon_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 8), width=2,
                      command=lambda x=i: self._preview_dungeon(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#e67e22", width=2,
                      command=lambda x=i: self._test_dungeon(x)).pack(side="right", padx=(0,1))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_dungeon(x)).pack(side="right", padx=2)

    def _build_past(self, parent):
        tk.Label(parent, text=f"과거의말하는섬  (3번 클릭 / {PAST_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#c0392b").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._past_stop = False
        self.btn_past_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=13, height=2,
            command=self._start_past)
        self.btn_past_run.pack(side="left", padx=(0,3))
        self.btn_past_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_past_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_past_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#922b21", fg="white", width=18,
            command=self._group_copy_past).pack(side="left", padx=(8,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        p_outer = tk.Frame(parent); p_outer.pack(fill="both", expand=True, padx=2)
        p_canvas = tk.Canvas(p_outer, highlightthickness=0)
        self._past_canvas = p_canvas
        p_sb_y = tk.Scrollbar(p_outer, orient="vertical", command=p_canvas.yview)
        p_sb_x = tk.Scrollbar(parent, orient="horizontal", command=p_canvas.xview)
        p_canvas.configure(yscrollcommand=p_sb_y.set, xscrollcommand=p_sb_x.set)
        p_sb_x.pack(side="bottom", fill="x")
        p_sb_y.pack(side="right", fill="y")
        p_canvas.pack(side="left", fill="both", expand=True)
        self._past_frame = tk.Frame(p_canvas)
        p_fid = p_canvas.create_window((0,0), window=self._past_frame, anchor="nw")
        self._past_frame.bind("<Configure>",
            lambda e: p_canvas.configure(scrollregion=p_canvas.bbox("all")))

        def _on_pwheel(e):
            p_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        p_canvas.bind("<MouseWheel>", _on_pwheel)
        self._past_frame.bind("<MouseWheel>", _on_pwheel)

        self._past_name_vars  = []
        self._past_click_vars = []
        self._past_click_btns = []
        self._past_coord_sv   = []
        self._past_detail_frames = []
        self._past_row_frames = []

        _past_lbl = ["클릭1", "이동2", "클릭3"]
        for i in range(PAST_SLOTS):
            row = tk.Frame(self._past_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=4)
            self._past_row_frames.append(row)
            detail = tk.Frame(self._past_frame, bg="#ecf0f1", bd=1, relief="flat")
            self._past_detail_frames.append(detail)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=4).pack(side="left", padx=(3,0))
            nv = tk.StringVar()
            self._past_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=(2,2))
            ent.bind("<FocusIn>",  lambda e: self.lift())
            ent.bind("<FocusOut>", lambda e, x=i: self._save_past_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_past_name(x))

            past_saved = self.cfg.get("past_slots", [{}]*PAST_SLOTS)[i].get("coords", []) if i < len(self.cfg.get("past_slots",[])) else []
            past_reg = sum(1 for c in past_saved if c)
            psv = tk.StringVar(value=f"좌표 {past_reg}/{PAST_CLICKS} ▾")
            self._past_coord_sv.append(psv)
            tk.Button(row, textvariable=psv, font=("맑은 고딕", 7),
                      bg="#c0392b", fg="white", width=8, pady=0,
                      command=lambda x=i: self._toggle_past_detail(x)).pack(side="left", padx=(2,2))

            click_vars = []
            click_btns = []
            for j in range(PAST_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                cell = tk.Frame(detail, bg="#ecf0f1")
                cell.pack(side="left", padx=4, pady=3)
                tk.Label(cell, text=_past_lbl[j], font=("맑은 고딕", 7),
                         fg="#c0392b", bg="#ecf0f1").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 7),
                                width=4, pady=1,
                                command=lambda x=i, c=j: self._reg_past_click(x, c))
                btn.pack()
                click_btns.append(btn)
            self._past_click_vars.append(click_vars)
            self._past_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_pwheel)
            row.bind("<MouseWheel>", _on_pwheel)
            detail.bind("<MouseWheel>", _on_pwheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_past_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 8), width=2,
                      command=lambda x=i: self._preview_past(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_past(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#c0392b", width=2,
                      command=lambda x=i: self._test_past(x)).pack(side="right", padx=(0,2))

        # 창 열릴 때 cfg 값으로 즉시 초기화
        for i in range(PAST_SLOTS):
            p = self.cfg["past_slots"][i]
            self._past_name_vars[i].set(p.get("name", "미등록"))
            coords = p.get("coords", [None]*PAST_CLICKS)
            for j in range(PAST_CLICKS):
                c = coords[j] if j < len(coords) else None
                self._past_click_vars[i][j].set("✔" if c else "✗")
                self._past_click_btns[i][j].config(
                    fg="white" if c else "#aaa",
                    bg="#27ae60" if c else "#7f8c8d")

    def deiconify(self):
        if getattr(self, "_running", False):
            return  # 자동실행 중에는 복원 차단
        super().deiconify()

    def _raise_claude(self):
        import win32gui, win32con
        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return True
            title = win32gui.GetWindowText(hwnd)
            if "claude" in title.lower():
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                win32gui.SetForegroundWindow(hwnd)
            return True
        win32gui.EnumWindows(_cb, None)

    def _clear_accounts(self):
        from tkinter import messagebox
        if not messagebox.askyesno("초기화", "계정 정보를 전체 초기화하시겠습니까?", default="no"):
            return
        for i in range(16):
            self._acc_type_vars[i].set("구글")
            for j in range(5):
                self._acc_vars[i][j].set("")
        save_accounts([{"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""} for _ in range(20)])
        self.status.set("✔ 계정 정보 초기화 완료")

    def _save_accounts(self):
        for i in range(20):
            self._accounts[i]["type"] = self._acc_type_vars[i].get()
            for j in range(5):
                self._accounts[i][f"f{j+1}"] = self._acc_vars[i][j].get()
        save_accounts(self._accounts)
        self.status.set("✔ 계정 정보 저장 완료")

    def _target_geometry(self):
        """콘텐츠에 맞는 목표 창 크기/위치 (폭=섹션행, 높이=콘텐츠+1cm, 작업표시줄 위로)."""
        self.update_idletasks()
        needed = self.winfo_reqheight() + 38   # 슬롯 끝에서 약 1cm 여유
        x, y = 76, 75                           # 초기 위치와 동일
        work_bottom = self.winfo_screenheight() - 48   # fallback
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
            work_bottom = rect.bottom
        except Exception:
            pass
        # 창 하단이 작업표시줄 아래로 잘리지 않도록 위로 올리고, 그래도 넘치면 높이 축소
        if y + needed > work_bottom:
            y = max(0, work_bottom - needed)
            if y + needed > work_bottom:
                needed = work_bottom - y
        try:
            w = max(self._sec_row.winfo_reqwidth() + 20, self.winfo_reqwidth())
        except Exception:
            w = self.winfo_width() or 1047
        w += 76   # 좌우 약 1cm씩(≈38px) 여유 — 내용이 가운데 정렬이라 양옆에 균등 여백
        return w, needed, x, y

    def _fit_main_height(self):
        # 최소화(iconic) 상태에선 geometry 변경이 복원 크기에 안 먹으므로 normal일 때만 조정
        try:
            if self.state() != "normal":
                return
        except Exception:
            pass
        w, h, x, y = self._target_geometry()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._did_initial_fit = True   # normal 상태에서 실제로 맞췄을 때만 완료 표시

    def _bring_to_front(self, e=None):
        self.lift()

    def _raise_main(self):
        """최소화된 메인런처를 복원하고 앞으로 올림 (항상 위 고정은 안 함)"""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _on_main_unmap(self, e=None):
        """메인런처가 최소화되면 클로드 앱도 같이 최소화.
        (복원은 클로드를 직접 클릭해서 따로 열 수 있음 — 자동 복원 안 함)
        단, 시작 직후 워치독이 런처를 최소화하는 건 제외(배포/시작 시 클로드 안 내리게)."""
        if not getattr(self, "_unmap_couple_ok", False):
            return
        def _chk():
            try:
                if self.state() == "iconic":   # 실제 최소화일 때만 (withdraw/등록오버레이 제외)
                    self._minimize_claude()
            except Exception:
                pass
        self.after(120, _chk)

    def _on_main_map(self, e):
        """패스권 창이 켜져 있으면 메인 런처 최소화 유지 (섬/던전은 사용자가 직접 복원 가능)"""
        pass_open = self._pass_win and self._pass_win.winfo_exists()
        if pass_open:
            self.after(50, self.iconify)
            return
        self._last_activity = time.time()   # 다시 올라오면 유휴 타이머 리셋
        self._bring_to_front()
        # 워치독이 최소화 상태로 띄우면 시작 시 크기맞춤이 걸리지 않으므로,
        # 최초로 창이 보여질 때 딱 한 번만 콘텐츠 크기에 맞춘다(맵 이벤트 폭주 방지: 1회성).
        if not getattr(self, "_did_initial_fit", False):
            self.after(60, self._fit_main_height)

    def _open_pass_win(self):
        if self._pass_win and self._pass_win.winfo_exists():
            self._pass_win.lift(); return
        self.iconify()
        win = tk.Toplevel(self)
        win.title("🎫 패스권 새로운 등록")
        win.geometry("480x720")
        win.resizable(True, True)
        def _on_pass_close():
            win.destroy()
            if not (hasattr(self, "_island_proc") and self._island_proc and self._island_proc.poll() is None):
                self.deiconify()
        win.protocol("WM_DELETE_WINDOW", _on_pass_close)
        self._pass_win = win
        self._build_pass(win)
        self._refresh_ui()

    def _build_pass(self, parent):
        tk.Label(parent, text=f"패스권 새로운 등록  ({PASS_CLICKS}번 클릭)",
                 font=("맑은 고딕", 9, "bold"), fg="#6c3483").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._pass_stop = False
        self.btn_pass_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#6c3483", fg="white",
            activebackground="#4a235a", width=13, height=2,
            command=self._start_pass)
        self.btn_pass_run.pack(side="left", padx=(0,3))
        self.btn_pass_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_pass_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_pass_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#4a235a", fg="white", width=18,
            command=self._group_copy_pass).pack(side="left", padx=(8,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        # 그룹 이동 버튼 (4개씩 4그룹)
        PASS_GROUP = 4
        grp_row = tk.Frame(parent); grp_row.pack(fill="x", padx=4, pady=(0,2))
        self._pass_grp_btns = []
        for g in range(PASS_SLOTS // PASS_GROUP):
            s = g * PASS_GROUP + 1; e = (g+1) * PASS_GROUP
            btn = tk.Button(grp_row, text=f"#{s:02d}~#{e:02d}",
                font=("맑은 고딕", 7), width=6,
                command=lambda g=g: self._pass_scroll_to_group(g))
            btn.pack(side="left", padx=1)
            self._pass_grp_btns.append(btn)

        p_outer = tk.Frame(parent); p_outer.pack(fill="both", expand=True, padx=2)
        p_canvas = tk.Canvas(p_outer, highlightthickness=0)
        self._pass_canvas = p_canvas
        p_sb = tk.Scrollbar(p_outer, orient="vertical", command=p_canvas.yview)
        p_canvas.configure(yscrollcommand=p_sb.set)
        p_sb.pack(side="right", fill="y")
        p_canvas.pack(side="left", fill="both", expand=True)
        self._pass_frame = tk.Frame(p_canvas)
        p_fid = p_canvas.create_window((0,0), window=self._pass_frame, anchor="nw")
        self._pass_frame.bind("<Configure>",
            lambda e: p_canvas.configure(scrollregion=p_canvas.bbox("all")))
        p_canvas.bind("<Configure>",
            lambda e: p_canvas.itemconfig(p_fid, width=e.width))

        def _on_pwheel(e):
            p_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        p_canvas.bind("<MouseWheel>", _on_pwheel)
        self._pass_frame.bind("<MouseWheel>", _on_pwheel)

        self._pass_name_vars  = []
        self._pass_click_vars = []
        self._pass_click_btns = []
        self._pass_coord_sv   = []
        self._pass_detail_frames = []
        self._pass_row_frames = []

        for i in range(PASS_SLOTS):
            row = tk.Frame(self._pass_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=4)
            self._pass_row_frames.append(row)
            detail = tk.Frame(self._pass_frame, bg="#f5eef8", bd=1, relief="flat")
            self._pass_detail_frames.append(detail)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=4).pack(side="left", padx=(3,0))
            nv = tk.StringVar()
            self._pass_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=(2,2))
            ent.bind("<FocusIn>",  lambda e: self.lift())
            ent.bind("<FocusOut>", lambda e, x=i: self._save_pass_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_pass_name(x))

            pass_saved = self.cfg.get("pass_slots", [{}]*PASS_SLOTS)[i].get("coords", []) if i < len(self.cfg.get("pass_slots",[])) else []
            pass_reg = sum(1 for c in pass_saved if c)
            psv = tk.StringVar(value=f"좌표 {pass_reg}/{PASS_CLICKS} ▾")
            self._pass_coord_sv.append(psv)
            tk.Button(row, textvariable=psv, font=("맑은 고딕", 7),
                      bg="#6c3483", fg="white", width=8, pady=0,
                      command=lambda x=i: self._toggle_pass_detail(x)).pack(side="left", padx=(2,2))

            click_vars = []
            click_btns = []
            row1 = tk.Frame(detail, bg="#f5eef8"); row1.pack(fill="x", pady=(3,0))
            row2 = tk.Frame(detail, bg="#f5eef8"); row2.pack(fill="x", pady=(0,3))
            for j in range(PASS_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                parent_row = row1 if j < 5 else row2
                cell = tk.Frame(parent_row, bg="#f5eef8")
                cell.pack(side="left", padx=2)
                tk.Label(cell, text=f"클{j+1}", font=("맑은 고딕", 6),
                         fg="#6c3483", bg="#f5eef8").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 6),
                                width=3, pady=0,
                                command=lambda x=i, c=j: self._reg_pass_click(x, c))
                btn.pack()
                click_btns.append(btn)
            self._pass_click_vars.append(click_vars)
            self._pass_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_pwheel)
            row.bind("<MouseWheel>", _on_pwheel)
            detail.bind("<MouseWheel>", _on_pwheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_pass_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                      command=lambda x=i: self._preview_pass(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#6c3483", width=2,
                      command=lambda x=i: self._test_pass(x)).pack(side="right", padx=(0,1))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_pass(x)).pack(side="right", padx=2)

    def _start_pass(self):
        if not self._try_busy_or_queue("패스권", self._start_pass): return
        self._pass_stop = False
        self.btn_pass_run.config(state="disabled", bg="#f39c12", text="⏳ 실행중...")
        self.btn_pass_stop.config(state="normal")
        self._minimize_pass_ui()
        threading.Thread(target=self._run_task, args=("패스권", self._run_pass), daemon=True).start()

    def _minimize_pass_ui(self):
        """패스권 실행 시 메인 런처 + 패스권 창 + 클로드 모두 최소화 (클릭이 게임에 닿도록)."""
        self.iconify()
        try:
            if self._pass_win and self._pass_win.winfo_exists():
                self._pass_win.iconify()
        except Exception:
            pass
        self._minimize_claude()

    def _restore_pass_ui(self):
        """패스권 실행 종료 후 창 복원 — 패스권 창이 있으면 그걸, 없으면 메인을 올림."""
        try:
            if self._pass_win and self._pass_win.winfo_exists():
                self._pass_win.deiconify(); self._pass_win.lift()
                return
        except Exception:
            pass
        self.deiconify()

    def _run_pass(self, slot_idx=None):
        try:
            self.status.set("2초 후 패스권 실행...")
            self.after(0, self._minimize_pass_ui)
            time.sleep(2)
            slots = self.cfg.get("pass_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots) if any(s.get("coords", []))]
            for si, slot in targets:
                if self._pass_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*PASS_CLICKS)
                if not self._wait_mouse_idle("_pass_stop"): return
                for ci, coord in enumerate(coords):
                    if self._pass_stop: break
                    if not coord: continue
                    self.status.set(f"🎫 [{name}] {PASS_LABELS[ci]}...")
                    pyautogui.click(*coord)
                    if ci < len(coords) - 1:
                        time.sleep(random.uniform(PASS_INNER_MIN, PASS_INNER_MAX) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._pass_stop: break
                time.sleep(random.uniform(PASS_SLOT_MIN, PASS_SLOT_MAX))
            self.status.set("✔ 패스권 등록 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_pass_ui)
            try:
                if self.btn_pass_run.winfo_exists():
                    self.btn_pass_run.config(state="normal", bg="#6c3483", text="▶  실행")
                if self.btn_pass_stop.winfo_exists():
                    self.btn_pass_stop.config(state="disabled")
            except Exception:
                pass

    def _reg_pass_click(self, slot_idx, click_idx):
        self._reg_pass_slot_idx  = slot_idx
        self._reg_pass_click_idx = click_idx
        btn = self._pass_click_btns[slot_idx][click_idx]
        self._pass_canvas.update_idletasks()
        total = self._pass_canvas.bbox("all")
        if total:
            row_y = btn.winfo_y() + btn.master.winfo_y()
            frac = row_y / total[3]
            self._pass_canvas.yview_moveto(frac)
        self.status.set(f"3초 후 패스권 #{slot_idx+1} [{PASS_LABELS[click_idx]}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="pass")])

    def on_pass_coord(self, x, y):
        si = self._reg_pass_slot_idx
        ci = self._reg_pass_click_idx
        self.cfg["pass_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 패스권 #{si+1} {PASS_LABELS[ci]} 등록: ({x},{y})")
        self.deiconify()

    def _save_pass_name(self, idx):
        name = self._pass_name_vars[idx].get().strip() or "미등록"
        self.cfg["pass_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_pass(self, idx):
        threading.Thread(target=self._run_pass, args=(idx,), daemon=True).start()

    def _del_pass(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"패스권 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["pass_slots"][idx] = {"name": "미등록", "coords": [None]*PASS_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _pass_scroll_to_group(self, g):
        PASS_GROUP = 4
        total = PASS_SLOTS
        frac = (g * PASS_GROUP) / total
        self._pass_canvas.yview_moveto(frac)

    def _preview_pass(self, idx):
        coords = self.cfg["pass_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg["pass_slots"][idx].get("name", f"#{idx+1:02d}")
        total = PASS_SLOTS

        def rereg(dot_idx):
            self._reg_pass_slot_idx  = idx
            self._reg_pass_click_idx = dot_idx if dot_idx is not None else 0
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="pass"))

        def _save(dot_idx, nx, ny):
            self.cfg["pass_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 패스권 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        def _prev():
            prev_idx = (idx - 1) % total
            self._open_dot_preview_pass(prev_idx)

        def _next():
            next_idx = (idx + 1) % total
            self._open_dot_preview_pass(next_idx)

        self._open_dot_preview_with_nav(
            f"패스권 #{idx+1:02d} {name}  ({idx+1}/{total})",
            dots, rereg_fn=rereg, save_fn=_save,
            prev_fn=_prev, next_fn=_next)

    def _open_dot_preview_pass(self, idx):
        self.after(200, lambda: self._preview_pass(idx))

    def _open_dot_preview_with_nav(self, title, dots, rereg_fn, save_fn, prev_fn, next_fn):
        self.withdraw()
        if self._pass_win and self._pass_win.winfo_exists():
            self._pass_win.withdraw()
        self.after(1000, lambda: _DotPreviewOverlayNav(
            self, title, dots, rereg_fn, save_fn, prev_fn, next_fn))

    def _group_copy_pass_slot(self, idx):
        import copy
        src = self.cfg["pass_slots"][0].get("coords", [])
        dst = self.cfg["pass_slots"][idx]["coords"]
        for j in range(PASS_CLICKS):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 → #{idx+1:02d} 복사 완료")

    def _group_copy_pass(self):
        import copy
        src = self.cfg["pass_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다"); return
        for i in range(1, PASS_SLOTS):
            self.cfg["pass_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{PASS_SLOTS:02d} 전체 복사 완료")

    def _build_sched(self, parent):
        self._sync_sched_click1()   # 창 열 때 과거섬 클릭1을 그대로 반영
        tk.Label(parent, text=f"매일매일 스케줄  ({SCHED_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#16a085").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._sched_stop = False
        self.btn_sched_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#16a085", fg="white",
            activebackground="#0e6655", width=13, height=2,
            command=self._start_sched)
        self.btn_sched_run.pack(side="left", padx=(0,3))
        self.btn_sched_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_sched_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_sched_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#0e6655", fg="white", width=18,
            command=self._group_copy_sched).pack(side="left", padx=(8,0))
        tk.Button(pr, text="🔒 클릭1=과거섬",
            font=("맑은 고딕", 8), bg="#95a5a6", fg="white", width=14,
            state="disabled").pack(side="left", padx=(4,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        s_outer = tk.Frame(parent); s_outer.pack(fill="both", expand=True, padx=2)
        s_canvas = tk.Canvas(s_outer, highlightthickness=0)
        self._sched_canvas = s_canvas
        s_sb = tk.Scrollbar(s_outer, orient="vertical", command=s_canvas.yview)
        s_canvas.configure(yscrollcommand=s_sb.set)
        s_sb.pack(side="right", fill="y")
        s_canvas.pack(side="left", fill="both", expand=True)
        self._sched_frame = tk.Frame(s_canvas)
        s_fid = s_canvas.create_window((0,0), window=self._sched_frame, anchor="nw")
        self._sched_frame.bind("<Configure>",
            lambda e: s_canvas.configure(scrollregion=s_canvas.bbox("all")))
        s_canvas.bind("<Configure>",
            lambda e: s_canvas.itemconfig(s_fid, width=e.width))

        def _on_swheel(e):
            s_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        s_canvas.bind("<MouseWheel>", _on_swheel)
        self._sched_frame.bind("<MouseWheel>", _on_swheel)

        self._sched_name_vars  = []
        self._sched_click_vars = []
        self._sched_click_btns = []

        for i in range(SCHED_SLOTS):
            row = tk.Frame(self._sched_frame, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=2)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=4).pack(side="left", padx=(3,0))
            nv = tk.StringVar()
            self._sched_name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=(2,6))
            ent.bind("<FocusIn>",  lambda e: self.lift())
            ent.bind("<FocusOut>", lambda e, x=i: self._save_sched_name(x))
            ent.bind("<Return>",   lambda e, x=i: self._save_sched_name(x))

            click_vars = []
            click_btns = []
            _sched_lbl = ["클릭1", "클릭2", "클릭3"]
            for j in range(SCHED_CLICKS):
                cv = tk.StringVar()
                click_vars.append(cv)
                cell = tk.Frame(row, bd=1, relief="flat")
                cell.pack(side="left", padx=3)
                locked = (j == 0)   # 클릭1은 과거섬과 동기화 → 잠금(표시만)
                tk.Label(cell, text=("클릭1🔒" if locked else _sched_lbl[j]),
                         font=("맑은 고딕", 5),
                         fg="#c0392b" if locked else "#16a085").pack()
                if locked:
                    _cmd = lambda: self.status.set(
                        "🔒 스케줄 클릭1은 과거섬 클릭1과 동기화됩니다 — 과거섬에서 수정하세요")
                else:
                    _cmd = lambda x=i, c=j: self._reg_sched_click(x, c)
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 6),
                                width=3, pady=0, command=_cmd)
                btn.pack()
                click_btns.append(btn)
            self._sched_click_vars.append(click_vars)
            self._sched_click_btns.append(click_btns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _on_swheel)
            row.bind("<MouseWheel>", _on_swheel)

            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                          command=lambda x=i: self._group_copy_sched_slot(x)).pack(side="right", padx=(0,3))
            tk.Button(row, text="👁", font=("맑은 고딕", 8), width=2,
                      command=lambda x=i: self._preview_sched(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="×", font=("맑은 고딕", 8), fg="red", width=2,
                      command=lambda x=i: self._del_sched(x)).pack(side="right", padx=(0,2))
            tk.Button(row, text="▶", font=("맑은 고딕", 8), fg="white", bg="#16a085", width=2,
                      command=lambda x=i: self._test_sched(x)).pack(side="right", padx=(0,2))

        # 창 열릴 때 cfg 값으로 즉시 초기화
        for i in range(SCHED_SLOTS):
            s = self.cfg["sched_slots"][i]
            self._sched_name_vars[i].set(s.get("name", "미등록"))
            coords = s.get("coords", [None]*SCHED_CLICKS)
            for j in range(SCHED_CLICKS):
                c = coords[j] if j < len(coords) else None
                self._sched_click_vars[i][j].set("✔" if c else "✗")
                self._sched_click_btns[i][j].config(
                    fg="white" if c else "#aaa",
                    bg="#27ae60" if c else "#7f8c8d")

    # ── 공통 ──────────────────────────────────────────────────────────
    def _popup_reg_label(self):
        chk = "✔" if self.cfg.get("purple_popup_checkbox") else "✗"
        cls = "✔" if self.cfg.get("purple_popup_close")    else "✗"
        det = "✔" if self.cfg.get("purple_popup_detect")   else "✗"
        return f"체크박스:{chk}  닫기:{cls}  감지:{det}"

    def _reg_popup_checkbox(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [체크박스] 위에 올려두세요 — 자동 캡처")
        self.after(3000, self._capture_popup_checkbox)

    def _capture_popup_checkbox(self):
        x, y = pyautogui.position()
        self.cfg["purple_popup_checkbox"] = [x, y]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 팝업 체크박스 등록: ({x},{y})")

    def _reg_popup_close(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [✕ 닫기버튼] 위에 올려두세요 — 자동 캡처")
        self.after(3000, self._capture_popup_close)

    def _capture_popup_close(self):
        x, y = pyautogui.position()
        self.cfg["purple_popup_close"] = [x, y]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 팝업 닫기버튼 등록: ({x},{y})")

    def _reg_popup_detect(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [팝업 X버튼 주변 빈 배경] 위에 올려두세요 — 픽셀 색상 저장")
        self.after(3000, self._capture_popup_detect)

    def _capture_popup_detect(self):
        from PIL import ImageGrab
        x, y = pyautogui.position()
        shot = ImageGrab.grab(all_screens=False)
        px   = shot.getpixel((x, y))
        self.cfg["purple_popup_detect"] = [x, y]
        self.cfg["purple_popup_color"]  = [px[0], px[1], px[2]]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 감지 픽셀 등록: ({x},{y}) RGB=({px[0]},{px[1]},{px[2]})")

    def _maximize_purple(self):
        win = find_purple()
        if win:
            try: win.activate(); win.maximize()
            except: pass

    def _open_dot_preview(self, title, dots, rereg_fn, save_fn=None, dot_r=5):
        self.withdraw()
        self.after(1000, lambda: _DotPreviewOverlay(self, title, dots, rereg_fn, save_fn, dot_r))

    def _preview_label_coord(self, key):
        c = self.cfg.get(key)
        dots = [(c[0], c[1], "1")] if c else []
        self._open_dot_preview(LABELS[key], dots, lambda _: self._reg_coord(key))

    def _preview_slot(self, idx):
        pair = self.cfg["click_slots"][idx]
        c1 = pair[0] if len(pair) > 0 else None
        c2 = pair[1] if len(pair) > 1 else None
        c3 = pair[2] if idx == 4 and len(pair) > 2 else None
        dots = []
        if c1: dots.append((c1[0], c1[1], "1"))
        if c2: dots.append((c2[0], c2[1], "2"))
        if c3: dots.append((c3[0], c3[1], "3"))

        def _save(dot_idx, nx, ny):
            self.cfg["click_slots"][idx][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        def _rereg(dot_idx):
            if dot_idx is None:
                self._reg_slot(idx)
            else:
                self._reg_slot_step(idx, dot_idx)

        self._open_dot_preview(f"#{idx+1:02d} 클릭슬롯", dots,
                               rereg_fn=_rereg, save_fn=_save)

    def _preview_char(self, idx):
        btns = self.cfg.get("char_btns", [])
        c = btns[idx] if idx < len(btns) else None
        dots = [(c[0], c[1], str(idx+1))] if c else []
        def _rereg():
            self._char_rereg_idx = idx
            self.status.set(f"3초 후 캐릭터 #{idx+1} 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                      CoordOverlay(self, mode="char_rereg")])
        self._open_dot_preview(f"캐릭터 #{idx+1:02d}", dots, _rereg)

    def on_char_rereg_coord(self, x, y):
        idx = self._char_rereg_idx
        btns = self.cfg.get("char_btns", [])
        if idx < len(btns):
            btns[idx] = [x, y]
            self.cfg["char_btns"] = btns
            save_cfg(self.cfg)
            self._refresh_ui()
            self.status.set(f"✔ 캐릭터 #{idx+1} 재등록: ({x},{y})")
        self.deiconify()

    def _del_char_btn(self, idx):
        btns = self.cfg.get("char_btns", [])
        if idx < len(btns):
            btns.pop(idx)
            self.cfg["char_btns"] = btns
            save_cfg(self.cfg)
            self._refresh_ui()

    def _sync_sched_click1(self):
        """매일매일 스케줄 클릭1 = 과거의말하는섬 클릭1 (항상 동기화)"""
        changed = False
        for i in range(min(PAST_SLOTS, SCHED_SLOTS)):
            src = self.cfg["past_slots"][i]["coords"][0]
            if self.cfg["sched_slots"][i]["coords"][0] != src:
                self.cfg["sched_slots"][i]["coords"][0] = src
                changed = True
        if changed:
            save_cfg(self.cfg)

    def _build_sec_row(self):
        """섹션 버튼 행 전체 재빌드 (고정 섹션 + 과거섬/던전 슬롯)."""
        for w in self._sec_row.winfo_children():
            w.destroy()

        fixed = [
            ("⚙ 좌표 등록", "#2c3e50", self._open_settings_win,                         None,      None),
            ("귀환주문서",   "#c0392b", lambda: self._open_past_slot(4),                 "#922b21", lambda: self._run_island_slot(4)),
            ("카매사오기",   "#1a5276", lambda: self._open_past_slot(5),                 "#154360", lambda: self._run_island_slot(5)),
            ("📬 우편함",    "#2471a3", self._open_mail_win,     "#1a5276", self._start_mail),
            ("🏝 과거섬",    "#c0392b", self._open_past_win,     "#922b21", self._start_past),
            ("📅 스케줄",    "#16a085", self._open_sched_win,    "#0e6655", self._start_sched),
            ("🏰 주말던전",  "#d35400", self._open_dungeon_win,  "#a04000", self._start_dungeon),
            ("🏹 사냥",      "#27ae60", self._open_hunt_win,     "#1e8449", self._start_hunt),
            ("💰 다야OCR",   "#27ae60", self._open_ocr,          "#1e8449", self._open_ocr_scan),
            ("🔗 연속클릭",  "#7d3c98", self._open_seq_win,      "#5b2c6f", self._start_seq),
        ]
        for text, color, cmd, run_color, run_cmd in fixed:
            grp = tk.Frame(self._sec_row); grp.pack(side="left", padx=2)
            tk.Button(grp, text=text, font=("맑은 고딕", 9, "bold"),
                      bg=color, fg="white", width=9, height=2,
                      command=cmd).pack(side="top")
            if run_cmd:
                tk.Button(grp, text="▶ 실행", font=("맑은 고딕", 7, "bold"),
                          bg=run_color, fg="white", width=9, height=1,
                          command=run_cmd).pack(side="top", pady=(1, 0))
            else:
                tk.Frame(grp, height=20).pack(side="top")

        # 구분선
        tk.Frame(self._sec_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=4)

        # 과거섬 슬롯 4개 고정 (이름 하드코딩)
        _ISLAND_NAMES  = ["오만의탑", "악몽의섬", "잊혀진섬", "에카"]
        _ISLAND_COLORS = ["#8e44ad", "#2471a3", "#16a085", "#d35400"]
        past_slots = self.cfg.get("past_slots", [])
        for i, label in enumerate(_ISLAND_NAMES):
            coords    = past_slots[i].get("coords", []) if i < len(past_slots) else []
            has_coord = any(c for c in coords)
            color     = _ISLAND_COLORS[i]
            dark      = _ISLAND_COLORS[i]
            grp = tk.Frame(self._sec_row); grp.pack(side="left", padx=2)
            tk.Button(grp, text=label, font=("맑은 고딕", 9, "bold"),
                      bg=color, fg="white", width=9, height=2,
                      command=lambda x=i: self._open_past_slot(x)).pack(side="top")
            tk.Button(grp, text="▶ 실행", font=("맑은 고딕", 7, "bold"),
                      bg=dark, fg="white", width=9, height=1,
                      command=lambda x=i: self._run_island_slot(x)
                      ).pack(side="top", pady=(1, 0))

        # 버튼 행 너비에 맞게 창 자동 조정
        self.after(50, self._fit_width_to_sec_row)

    def _fit_width_to_sec_row(self):
        self._fit_main_height()

    def _build_slot_quick_btns(self):
        """메인 런처 다야 옆 섬/던전 슬롯 빠른 실행 버튼 (재호출로 갱신)."""
        for w in self._slot_inner.winfo_children():
            w.destroy()
        self._slot_quick_btns = []

        past_slots    = self.cfg.get("past_slots",    [])
        dungeon_slots = self.cfg.get("dungeon_slots", [])

        # 과거섬 슬롯 — 행으로 배치
        for i, slot in enumerate(past_slots):
            name      = slot.get("name", "").strip() or f"섬#{i+1}"
            coords    = slot.get("coords", [])
            has_coord = any(c for c in coords)
            btn = tk.Button(
                self._slot_inner,
                text=name,
                font=("맑은 고딕", 8, "bold"),
                bg="#c0392b" if has_coord else "#95a5a6",
                fg="white", width=9, height=1,
                state="normal" if has_coord else "disabled",
                command=lambda x=i: threading.Thread(
                    target=self._run_past, args=(x,), daemon=True).start()
            )
            btn.pack(fill="x", pady=1)
            self._slot_quick_btns.append(btn)

        # 던전 슬롯
        for i, slot in enumerate(dungeon_slots):
            name      = slot.get("name", "").strip() or f"던전#{i+1}"
            coords    = slot.get("coords", [])
            has_coord = any(c for c in coords)
            btn = tk.Button(
                self._slot_inner,
                text=name,
                font=("맑은 고딕", 8, "bold"),
                bg="#e67e22" if has_coord else "#95a5a6",
                fg="white", width=9, height=1,
                state="normal" if has_coord else "disabled",
                command=lambda x=i: threading.Thread(
                    target=self._run_dungeon, args=(x,), daemon=True).start()
            )
            btn.pack(fill="x", pady=1)
            self._slot_quick_btns.append(btn)

    def _refresh_ui(self):
        # 스케줄 클릭1 = 과거섬 클릭1 : 표시 갱신 전에 항상 미러링(과거섬 편집이 그대로 반영됨)
        self._sync_sched_click1()
        # debounce: 100ms 내 중복 호출 무시
        now = time.time()
        if hasattr(self, "_last_refresh") and now - self._last_refresh < 0.1:
            return
        self._last_refresh = now
        if not hasattr(self, "_coord_vars"):
            return
        for key, var in self._coord_vars.items():
            c = self.cfg.get(key)
            var.set(f"({c[0]},{c[1]})" if c else "미등록")
        # 캐릭터 버튼 동적 목록 갱신
        for w in self._char_rows_frame.winfo_children():
            w.destroy()
        btns = self.cfg.get("char_btns", [])
        for i, c in enumerate(btns):
            r = tk.Frame(self._char_rows_frame); r.pack(fill="x", pady=0)
            tk.Label(r, text=f"#{i+1:02d}", font=("맑은 고딕", 7), width=3).pack(side="left")
            coord_txt = f"({c[0]},{c[1]})" if c else "미등록"
            tk.Label(r, text=coord_txt, font=("맑은 고딕", 7), fg="gray", width=14).pack(side="left")
            tk.Button(r, text="👁", font=("맑은 고딕", 6), width=2,
                      command=lambda x=i: self._preview_char(x)).pack(side="right", padx=1)
            tk.Button(r, text="×", font=("맑은 고딕", 6), fg="red", width=2,
                      command=lambda x=i: self._del_char_btn(x)).pack(side="right", padx=1)
        n = len(btns)
        self._char_count_var.set(f"({n}개)" if n else "(미등록)")
        for i, var in enumerate(self._slot_vars):
            pair = self.cfg["click_slots"][i]
            c1 = pair[0] if len(pair) > 0 else None
            c2 = pair[1] if len(pair) > 1 else None
            c3 = pair[2] if i == 4 and len(pair) > 2 else None
            if i == 4:
                if c1 and c2 and c3:
                    var.set(f"✔ {c1} / {c2} / {c3}")
                elif c1 and c2:
                    var.set("클릭1✔ 클릭2✔ 클릭3 미등록")
                elif c1:
                    var.set("클릭1✔  클릭2 미등록")
                else:
                    var.set("미등록")
            else:
                if c1 and c2:
                    var.set(f"✔ {c1} / {c2}")
                elif c1:
                    var.set("클릭1✔  클릭2 미등록")
                else:
                    var.set("미등록")
        if hasattr(self, "_hunt_name_vars") and self._hunt_name_vars:
            for i in range(HUNT_SLOTS):
                h = self.cfg["hunt_slots"][i]
                self._hunt_name_vars[i].set(h.get("name", "미등록"))
                coords = h.get("coords", [None] * HUNT_CLICKS)
                for j in range(HUNT_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._hunt_click_vars[i][j].set("✔" if c else "✗")
                    self._hunt_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._hunt_assign_btns):
                    aw = h.get("assigned_window")
                    self._hunt_assign_btns[i].config(
                        text="✔지정" if aw else "지정",
                        bg="#27ae60" if aw else "#8e44ad"
                    )
                if hasattr(self, "_hunt_enable_btns") and i < len(self._hunt_enable_btns):
                    en = h.get("enabled", True)
                    self._hunt_enable_btns[i].config(text="ON" if en else "OFF",
                                                     bg="#27ae60" if en else "#95a5a6")
                if i < len(self._hunt_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._hunt_detail_frames) and self._hunt_detail_frames[i].winfo_ismapped()) else "▾"
                    self._hunt_coord_sv[i].set(f"좌표 {reg}/{HUNT_CLICKS} {arrow}")
        # mail 슬롯
        if hasattr(self, "_mail_name_vars") and self._mail_name_vars:
            for i in range(MAIL_SLOTS):
                m = self.cfg["mail_slots"][i]
                self._mail_name_vars[i].set(m.get("name", "미등록"))
                coords = m.get("coords", [None]*MAIL_CLICKS)
                for j in range(MAIL_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._mail_click_vars[i][j].set("✔" if c else "✗")
                    self._mail_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._mail_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._mail_detail_frames) and self._mail_detail_frames[i].winfo_ismapped()) else "▾"
                    self._mail_coord_sv[i].set(f"좌표 {reg}/{MAIL_CLICKS} {arrow}")
        # past 슬롯
        if hasattr(self, "_past_name_vars") and self._past_name_vars:
            for i in range(PAST_SLOTS):
                p = self.cfg["past_slots"][i]
                self._past_name_vars[i].set(p.get("name", "미등록"))
                coords = p.get("coords", [None]*PAST_CLICKS)
                for j in range(PAST_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._past_click_vars[i][j].set("✔" if c else "✗")
                    self._past_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._past_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._past_detail_frames) and self._past_detail_frames[i].winfo_ismapped()) else "▾"
                    self._past_coord_sv[i].set(f"좌표 {reg}/{PAST_CLICKS} {arrow}")
        # pass 슬롯
        if hasattr(self, "_pass_name_vars") and self._pass_name_vars:
            for i in range(PASS_SLOTS):
                p = self.cfg["pass_slots"][i]
                self._pass_name_vars[i].set(p.get("name", "미등록"))
                coords = p.get("coords", [None]*PASS_CLICKS)
                for j in range(PASS_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._pass_click_vars[i][j].set("✔" if c else "✗")
                    self._pass_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._pass_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._pass_detail_frames) and self._pass_detail_frames[i].winfo_ismapped()) else "▾"
                    self._pass_coord_sv[i].set(f"좌표 {reg}/{PASS_CLICKS} {arrow}")
        # 섹션 버튼 행 슬롯 갱신
        if hasattr(self, "_sec_row") and self._sec_row.winfo_exists():
            self._build_sec_row()
        # sched 슬롯 (창이 열려있을 때만)
        if hasattr(self, "_sched_name_vars") and self._sched_name_vars:
            for i in range(SCHED_SLOTS):
                s = self.cfg["sched_slots"][i]
                self._sched_name_vars[i].set(s.get("name", "미등록"))
                coords = s.get("coords", [None]*SCHED_CLICKS)
                for j in range(SCHED_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._sched_click_vars[i][j].set("✔" if c else "✗")
                    self._sched_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )

    def _wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._stop_flag: return False
            time.sleep(0.1)
        return True

    def _wait_mouse_idle(self, stop_flag_name, idle_sec=1.5):
        """마우스가 움직이는 중일 때만 대기. 안 움직이면 즉시 True 반환."""
        CHECK = 0.1
        prev = pyautogui.position()
        # 움직임이 없으면 즉시 통과
        time.sleep(CHECK)
        cur = pyautogui.position()
        if cur == prev:
            return not getattr(self, stop_flag_name, False)
        # 움직임 감지됨 → idle_sec초 동안 안 움직일 때까지 대기
        self.after(0, lambda: self.status.set(f"⏸ 마우스 움직임 감지 — {int(idle_sec)}초 정지 후 재개..."))
        last_move = time.time()
        prev = cur
        while True:
            if getattr(self, stop_flag_name, False):
                return False
            time.sleep(CHECK)
            cur = pyautogui.position()
            if cur != prev:
                last_move = time.time()
                prev = cur
            elif time.time() - last_move >= idle_sec:
                return True

    def _click_wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._click_stop: return False
            time.sleep(0.1)
        return True

    def _hunt_wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._hunt_stop: return False
            time.sleep(0.1)
        return True

    # ── 좌표 등록 ─────────────────────────────────────────────────────
    def _preprocess_ocr_img(self, img):
        """OCR용 이미지 전처리 — 단순 확대만"""
        from PIL import Image, ImageOps
        img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
        img = ImageOps.expand(img, border=20, fill=(0, 0, 0))
        return img.convert("RGB")

    def _save_ocr_as_target_id(self):
        """테스트 OCR 결과를 사용할 아이디로 저장"""
        area = self.cfg.get("profile_id_area")
        if not area:
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        def _do():
            try:
                if self.cfg.get("profile_reveal_btn"):
                    pyautogui.click(*self.cfg["profile_reveal_btn"])
                    time.sleep(1)
                ocr_id = self._ocr_profile_id()
                if ocr_id:
                    self.cfg["profile_target_id"] = ocr_id
                    save_cfg(self.cfg)
                    self.after(0, lambda: [self._profile_target_var.set(ocr_id),
                                           self.status.set(f"✔ 아이디 저장 완료: '{ocr_id}'")])
                else:
                    self.after(0, lambda: self.status.set("OCR 결과가 없습니다. 영역을 다시 확인하세요."))
            except Exception as e:
                self.after(0, lambda err=e: self.status.set(f"오류: {err}"))
        self.status.set("OCR로 아이디 읽는 중...")
        threading.Thread(target=_do, daemon=True).start()

    def _test_profile_ocr(self):
        """profile_reveal_btn 클릭 후 영역 캡처해서 이미지 열기"""
        area = self.cfg.get("profile_id_area")
        if not area:
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        def _do():
            try:
                # 캡처는 런처가 최소화된 상태에서 먼저 (런처 창이 영역을 가리지 않도록)
                # 실제 4시 판별과 동일한 창 위치 보정 경로 사용
                img = self._grab_profile_img()
                # 캡처 후 메인런처를 복원·앞으로 올려 상태바 결과를 볼 수 있게 함
                self.after(0, self._raise_main)
                self.after(0, lambda: self.status.set("OCR 분석 중..."))
                ocr_id = self._ocr_img_text(img)
                target = (self.cfg.get("profile_target_id") or "").strip()
                if target and ocr_id:
                    ratio = int(self._profile_match_ratio(ocr_id) * 100)
                    self.after(0, lambda o=ocr_id, r=ratio: self.status.set(
                        f"OCR: '{o}' / 목표: '{target}' → 일치율 {r}%"))
                else:
                    self.after(0, lambda o=ocr_id: self.status.set(
                        f"OCR 결과: '{o}' (저장된 아이디 없음)"))
            except Exception as e:
                import traceback
                try:
                    with open(os.path.join(LOGS_DIR, "ocr_error.txt"), "w", encoding="utf-8") as f:
                        f.write(traceback.format_exc())
                except Exception:
                    pass
                self.after(0, lambda err=e: self.status.set(f"오류: {err} (ocr_error.txt 확인)"))
        self.status.set("캡처 중... (첫 실행 시 30초 소요)")
        threading.Thread(target=_do, daemon=True).start()

    def _reg_profile_id_area(self):
        self.status.set("3초 후 퍼플 아이디가 표시되는 영역을 드래그하세요!")
        self.after(3000, lambda: [self.withdraw(), self.after(200, self._open_profile_area_overlay)])

    def _open_profile_area_overlay(self):
        _ProfileAreaOverlay(self)

    def _save_profile_ref_pixel(self):
        """스크롤 계정 화면에서 아이디 영역 픽셀 기준값 저장"""
        area = self.cfg.get("profile_id_area")
        if not area:
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        from PIL import ImageGrab
        import numpy as np
        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
        arr = np.array(img).flatten().tolist()
        self.cfg["profile_ref_pixel"] = arr
        save_cfg(self.cfg)
        self._profile_pix_var.set("저장됨")
        self.status.set("✔ 스크롤 계정 기준 픽셀 저장 완료")

    def _test_profile_pixel(self):
        """현재 화면과 기준 픽셀 비교 테스트"""
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            self.status.set("기준 픽셀 또는 영역이 미등록입니다."); return
        from PIL import ImageGrab
        import numpy as np
        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
        arr = np.array(img).flatten().tolist()
        n = min(len(ref), len(arr))
        diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
        matched = diff < 30
        self.status.set(f"픽셀 차이: {diff:.1f} → {'✔ 스크롤 계정 일치' if matched else '✗ 다른 계정'}")

    def _is_scroll_account_at(self, hwnd):
        """hwnd 창 위치 기준으로 profile_id_area 좌표 보정 후 픽셀 비교"""
        import win32gui
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            return False
        try:
            from PIL import ImageGrab
            import numpy as np
            wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
            ax = area["x"] + wx
            ay = area["y"] + wy
            img = ImageGrab.grab(bbox=(ax, ay, ax+area["w"], ay+area["h"]), all_screens=True)
            arr = np.array(img).flatten().tolist()
            n = min(len(ref), len(arr))
            diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
            return diff < 30
        except:
            return False

    def _is_scroll_account(self):
        """현재 화면이 스크롤 계정인지 픽셀 비교로 확인"""
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            return False
        try:
            from PIL import ImageGrab
            import numpy as np
            ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            arr = np.array(img).flatten().tolist()
            n = min(len(ref), len(arr))
            diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
            return diff < 30
        except:
            return False

    # ── 아이디 OCR 기반 계정 판별 (창 위치 보정 → 다른 컴퓨터에서도 동작) ──
    def _profile_area_bbox(self, hwnd=None):
        """아이디 영역의 실제 캡처 bbox 계산.
        등록 시 퍼플 창 위치(profile_id_area_win)가 저장돼 있으면 현재 퍼플 창
        위치와의 차이만큼 보정한다 → 창이 어디 떠 있든/다른 컴퓨터에서도 정확.
        저장된 창위치가 없으면 기존 절대좌표를 그대로 사용(하위호환)."""
        area = self.cfg.get("profile_id_area")
        if not area:
            return None
        ax, ay = area["x"], area["y"]
        reg_win = self.cfg.get("profile_id_area_win")
        if reg_win:
            cur = None
            if hwnd:
                try:
                    import win32gui
                    wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
                    cur = (wx, wy)
                except Exception:
                    cur = None
            if cur is None:
                try:
                    w = find_purple()
                    if w:
                        cur = (w.left, w.top)
                except Exception:
                    cur = None
            if cur:
                ax += cur[0] - reg_win[0]
                ay += cur[1] - reg_win[1]
        return (ax, ay, area["w"], area["h"])

    def _grab_profile_img(self, hwnd=None):
        """아이디 영역 캡처 + 전처리 후 이미지 반환(실패 시 None). 디버그 이미지 저장."""
        bbox = self._profile_area_bbox(hwnd)
        if not bbox:
            return None
        try:
            from PIL import ImageGrab
            ax, ay, aw, ah = bbox
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            try:
                img.save(os.path.join(LOGS_DIR, "profile_ocr_debug.png"))
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _ocr_img_text(self, img):
        if img is None:
            return ""
        try:
            import numpy as np
            results = _get_ocr_reader().readtext(np.array(img), detail=0, paragraph=False)
            return "".join(results).strip()
        except Exception:
            return ""

    def _ocr_profile_id(self, hwnd=None):
        """아이디 영역을 OCR로 읽어 문자열 반환."""
        return self._ocr_img_text(self._grab_profile_img(hwnd))

    def _profile_match_ratio(self, ocr_id):
        target = (self.cfg.get("profile_target_id") or "").strip()
        if not target or not ocr_id:
            return 0.0
        match = sum(1 for a, b in zip(ocr_id, target) if a == b)
        return match / max(len(target), 1)

    def _is_target_account(self, hwnd=None):
        """현재 퍼플 계정이 지정 아이디인지 OCR로 판별 → (matched, ocr_id, ratio).
        지정 아이디가 비어 있으면 (True, '', 0)로 전환하지 않음."""
        target = (self.cfg.get("profile_target_id") or "").strip()
        if not target:
            return (True, "", 0.0)
        ocr_id = self._ocr_profile_id(hwnd)
        ratio = self._profile_match_ratio(ocr_id)
        return (ratio >= 1.0, ocr_id, ratio)

    def _check_profile_and_switch(self):
        """아이디 영역 OCR → 100% 일치하면 지정 계정으로 판단"""
        area = self.cfg.get("profile_id_area")
        target = self.cfg.get("profile_target_id", "스크롤").strip()
        if not area or not target:
            return True
        try:
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(1)
            from PIL import ImageGrab
            ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            img.save(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"))
            results = _get_ocr_reader().readtext(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"),
                detail=0, paragraph=False)
            ocr_id = "".join(results).strip()
            # 100% 글자 일치 여부 확인
            match = sum(1 for a, b in zip(ocr_id, target) if a == b)
            ratio = match / max(len(target), 1)
            self.status.set(f"아이디 인식: '{ocr_id}' ({int(ratio*100)}% 일치)")
            return ratio >= 1.0
        except Exception as e:
            self.status.set(f"아이디 확인 오류: {e}")
            return True

    def _check_profile_and_switch_at(self, hwnd):
        """hwnd 창 위치를 기준으로 profile_id_area 절대좌표를 계산해서 OCR"""
        import win32gui
        area = self.cfg.get("profile_id_area")
        target = self.cfg.get("profile_target_id", "스크롤").strip()
        if not area or not target:
            return True
        try:
            # 창이 (0,0)에 있을 때 기준으로 등록된 좌표 → 현재 창 위치로 보정
            wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
            ax = area["x"] + wx
            ay = area["y"] + wy
            aw, ah = area["w"], area["h"]
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            img.save(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"))
            results = _get_ocr_reader().readtext(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"),
                detail=0, paragraph=False)
            ocr_id = "".join(results).strip()
            match = sum(1 for a, b in zip(ocr_id, target) if a == b)
            ratio = match / max(len(target), 1)
            self.status.set(f"아이디 인식: '{ocr_id}' ({int(ratio*100)}% 일치)")
            return ratio >= 1.0
        except Exception as e:
            self.status.set(f"아이디 확인 오류: {e}")
            return True

    # ── 연속 클릭 (별도 기능): 단축키/버튼으로 16개 좌표를 순서대로 1회씩 클릭 ──
    def _open_seq_win(self):
        self._open_section_win("_seq_win", "🔗 연속 클릭", self._build_seq, w=300, h=680)

    def _vk_name(self, vk):
        if not vk:
            return "미지정"
        names = {0x1B: "ESC", 0x20: "Space", 0x0D: "Enter", 0x09: "Tab",
                 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
                 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
                 0x21: "PageUp", 0x22: "PageDown"}
        if vk in names:
            return names[vk]
        if 0x70 <= vk <= 0x87:
            return f"F{vk - 0x6F}"      # F1~F24
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return chr(vk)              # 0-9, A-Z
        if 0x60 <= vk <= 0x69:
            return f"Num{vk - 0x60}"    # 넘패드 0-9
        return f"VK 0x{vk:02X}"

    def _seq_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('seq_hotkey'))}"

    def _build_seq(self, parent):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS

        tk.Label(parent, text="연속 클릭 — 단축키를 누르면 순서대로 1회씩",
                 font=("맑은 고딕", 9, "bold"), fg="#5b2c6f").pack(pady=(6, 2))

        top = tk.Frame(parent); top.pack(pady=2)
        self._seq_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                         bg="#7f8c8d", fg="white", width=6,
                                         command=self._toggle_seq)
        self._seq_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_seq).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_seq_hotkey).pack(side="left", padx=3)

        self._seq_hotkey_var = tk.StringVar(value=self._seq_hotkey_label())
        tk.Label(parent, textvariable=self._seq_hotkey_var,
                 font=("맑은 고딕", 8), fg="#5b2c6f").pack()

        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._seq_min_var = tk.StringVar(value=str(self.cfg.get("seq_min", SEQ_MIN)))
        self._seq_max_var = tk.StringVar(value=str(self.cfg.get("seq_max", SEQ_MAX)))
        tk.Entry(int_row, textvariable=self._seq_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._seq_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_seq_interval).pack(side="left", padx=3)

        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)

        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        self._seq_slot_vars = []
        for i in range(SEQ_SLOTS):
            row = tk.Frame(inner, bd=1, relief="groove"); row.pack(fill="x", padx=3, pady=1)
            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=3, fg="#5b2c6f").pack(side="left", padx=2)
            sv = tk.StringVar()
            c = seq[i] if i < len(seq) else None
            sv.set(f"({c[0]},{c[1]})" if c else "미등록")
            self._seq_slot_vars.append(sv)
            tk.Label(row, textvariable=sv, font=("맑은 고딕", 8),
                     width=12, anchor="w").pack(side="left")
            tk.Button(row, text="등록", font=("맑은 고딕", 7), bg="#7d3c98", fg="white",
                      command=lambda x=i: self._reg_seq_coord(x)).pack(side="right", padx=2)
            tk.Button(row, text="×", font=("맑은 고딕", 7), fg="red", width=2,
                      command=lambda x=i: self._del_seq_coord(x)).pack(side="right")
            row.bind("<MouseWheel>", _wheel)

        self._refresh_seq_toggle()

    def _refresh_seq_toggle(self):
        if hasattr(self, "_seq_toggle_btn") and self._seq_toggle_btn.winfo_exists():
            on = getattr(self, "_seq_on", False)
            self._seq_toggle_btn.config(text="ON" if on else "OFF",
                                        bg="#27ae60" if on else "#7f8c8d")

    def _toggle_seq(self):
        self._seq_on = not getattr(self, "_seq_on", False)
        self.cfg["seq_on"] = self._seq_on   # 재시작해도 유지되게 저장
        save_cfg(self.cfg)
        self._refresh_seq_toggle()
        if self._seq_on:
            self.status.set(f"연속클릭 ON — {self._vk_name(self.cfg.get('seq_hotkey'))} 누르면 실행")
        else:
            self.status.set("연속클릭 OFF")

    def _save_seq_interval(self):
        try:
            mn = float(self._seq_min_var.get())
            mx = float(self._seq_max_var.get())
            if mx < mn:
                mn, mx = mx, mn
            self.cfg["seq_min"] = mn
            self.cfg["seq_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_seq_coord(self, idx):
        self._seq_reg_idx = idx
        self.status.set(f"3초 후 연속클릭 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="seq")])

    def on_seq_coord(self, x, y):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS
        while len(seq) < SEQ_SLOTS:
            seq.append(None)
        seq[self._seq_reg_idx] = [x, y]
        self.cfg["seq_slots"] = seq
        save_cfg(self.cfg)
        if hasattr(self, "_seq_slot_vars") and self._seq_reg_idx < len(self._seq_slot_vars):
            self._seq_slot_vars[self._seq_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 연속클릭 #{self._seq_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_seq_coord(self, idx):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS
        if idx < len(seq):
            seq[idx] = None
            self.cfg["seq_slots"] = seq
            save_cfg(self.cfg)
        if hasattr(self, "_seq_slot_vars") and idx < len(self._seq_slot_vars):
            self._seq_slot_vars[idx].set("미등록")
        self.status.set(f"연속클릭 #{idx+1} 삭제")

    def _seq_hide(self):
        """연속클릭 실행 전, 리니지M 외 창(서브창/메인런처/클로드)을 최소화. 메인스레드에서 호출."""
        try:
            self._minimize_all()   # 서브창 + 메인 + 클로드 (다른 실행과 동일)
        except Exception:
            pass
        # iconify가 안 먹는 경우 대비 — 메인런처를 win32로도 확실히 최소화
        try:
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, "리니지M 자동 실행")
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    def _start_seq(self):
        threading.Thread(target=self._run_seq, daemon=True).start()

    def _run_seq(self):
        if getattr(self, "_seq_running", False):
            return
        seq = self.cfg.get("seq_slots") or []
        coords = [c for c in seq if c]
        if not coords:
            self.after(0, lambda: self.status.set("연속클릭: 등록된 좌표가 없습니다"))
            return
        if not self._try_busy_or_queue("연속클릭", self._start_seq):
            return
        self._seq_running = True
        try:
            # 클릭 좌표를 런처/연속클릭 창이 가리지 않도록 확실히 최소화 후 실행
            self.after(0, self._seq_hide)
            time.sleep(0.5)
            mn = float(self.cfg.get("seq_min", SEQ_MIN))
            mx = float(self.cfg.get("seq_max", SEQ_MAX))
            if mx < mn:
                mn, mx = mx, mn
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                self.after(0, lambda a=i: self.status.set(f"🔗 연속클릭 {a+1}/{n}..."))
                pyautogui.click(x, y)
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx))   # 슬롯간 간격 (설정값 그대로, 추가 간격 없음)
            self.after(0, lambda: self.status.set(f"✔ 연속클릭 완료 ({n}개)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"연속클릭 오류: {err}"))
        finally:
            self._seq_running = False
            self._clear_busy("연속클릭")
            self.after(0, self._restore_all)   # 완료 후 런처/서브창 복원

    def _assign_seq_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)  # 이전 클릭이 떼질 시간
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):  # 마우스 버튼 제외
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:  # ESC
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["seq_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_seq_hotkey_var"):
                    self._seq_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _seq_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 연속 클릭 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("seq_hotkey")
            if not getattr(self, "_seq_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_seq_running", False):
                threading.Thread(target=self._run_seq, daemon=True).start()
            prev = down

    # ── 일반던전충전 (연속클릭 복제 — 각 좌표를 7~9회 랜덤 연속 클릭) ──
    def _open_dc_win(self):
        self._open_section_win("_dc_win", "🎯 일반던전충전", self._build_dc, w=300, h=680)

    def _dc_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('dc_hotkey'))}"

    def _build_dc(self, parent):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS

        tk.Label(parent,
                 text=f"일반던전충전 — 각 좌표 {DC_BURST_MIN:.0f}~{DC_BURST_MAX:.0f}초 내 {DC_TAPS_MIN}~{DC_TAPS_MAX}회 연속 클릭",
                 font=("맑은 고딕", 9, "bold"), fg="#6c3483").pack(pady=(6, 2))

        top = tk.Frame(parent); top.pack(pady=2)
        self._dc_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                        bg="#7f8c8d", fg="white", width=6,
                                        command=self._toggle_dc)
        self._dc_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_dc).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_dc_hotkey).pack(side="left", padx=3)

        self._dc_hotkey_var = tk.StringVar(value=self._dc_hotkey_label())
        tk.Label(parent, textvariable=self._dc_hotkey_var,
                 font=("맑은 고딕", 8), fg="#6c3483").pack()

        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="좌표간 간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._dc_min_var = tk.StringVar(value=str(self.cfg.get("dc_min", DC_MIN)))
        self._dc_max_var = tk.StringVar(value=str(self.cfg.get("dc_max", DC_MAX)))
        tk.Entry(int_row, textvariable=self._dc_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._dc_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_dc_interval).pack(side="left", padx=3)

        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)

        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        self._dc_slot_vars = []
        for i in range(DC_SLOTS):
            row = tk.Frame(inner, bd=1, relief="groove"); row.pack(fill="x", padx=3, pady=1)
            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=3, fg="#6c3483").pack(side="left", padx=2)
            sv = tk.StringVar()
            c = dc[i] if i < len(dc) else None
            sv.set(f"({c[0]},{c[1]})" if c else "미등록")
            self._dc_slot_vars.append(sv)
            tk.Label(row, textvariable=sv, font=("맑은 고딕", 8),
                     width=12, anchor="w").pack(side="left")
            tk.Button(row, text="등록", font=("맑은 고딕", 7), bg="#6c3483", fg="white",
                      command=lambda x=i: self._reg_dc_coord(x)).pack(side="right", padx=2)
            tk.Button(row, text="×", font=("맑은 고딕", 7), fg="red", width=2,
                      command=lambda x=i: self._del_dc_coord(x)).pack(side="right")
            row.bind("<MouseWheel>", _wheel)

        self._refresh_dc_toggle()

    def _refresh_dc_toggle(self):
        if hasattr(self, "_dc_toggle_btn") and self._dc_toggle_btn.winfo_exists():
            on = getattr(self, "_dc_on", False)
            self._dc_toggle_btn.config(text="ON" if on else "OFF",
                                       bg="#27ae60" if on else "#7f8c8d")

    def _toggle_dc(self):
        self._dc_on = not getattr(self, "_dc_on", False)
        self.cfg["dc_on"] = self._dc_on   # 재시작해도 유지되게 저장
        save_cfg(self.cfg)
        self._refresh_dc_toggle()
        if self._dc_on:
            self.status.set(f"일반던전충전 ON — {self._vk_name(self.cfg.get('dc_hotkey'))} 누르면 실행")
        else:
            self.status.set("일반던전충전 OFF")

    def _save_dc_interval(self):
        try:
            mn = float(self._dc_min_var.get())
            mx = float(self._dc_max_var.get())
            if mx < mn:
                mn, mx = mx, mn
            self.cfg["dc_min"] = mn
            self.cfg["dc_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 좌표간 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_dc_coord(self, idx):
        self._dc_reg_idx = idx
        self.status.set(f"3초 후 일반던전충전 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="dc")])

    def on_dc_coord(self, x, y):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS
        while len(dc) < DC_SLOTS:
            dc.append(None)
        dc[self._dc_reg_idx] = [x, y]
        self.cfg["dc_slots"] = dc
        save_cfg(self.cfg)
        if hasattr(self, "_dc_slot_vars") and self._dc_reg_idx < len(self._dc_slot_vars):
            self._dc_slot_vars[self._dc_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 일반던전충전 #{self._dc_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_dc_coord(self, idx):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS
        if idx < len(dc):
            dc[idx] = None
            self.cfg["dc_slots"] = dc
            save_cfg(self.cfg)
        if hasattr(self, "_dc_slot_vars") and idx < len(self._dc_slot_vars):
            self._dc_slot_vars[idx].set("미등록")
        self.status.set(f"일반던전충전 #{idx+1} 삭제")

    def _start_dc(self):
        threading.Thread(target=self._run_dc, daemon=True).start()

    def _run_dc(self):
        if getattr(self, "_dc_running", False):
            return
        dc = self.cfg.get("dc_slots") or []
        coords = [c for c in dc if c]
        if not coords:
            self.after(0, lambda: self.status.set("일반던전충전: 등록된 좌표가 없습니다"))
            return
        if not self._try_busy_or_queue("일반던전충전", self._start_dc):
            return
        self._dc_running = True
        try:
            # 클릭 좌표를 런처/창이 가리지 않도록 최소화 후 실행(연속클릭과 동일)
            self.after(0, self._seq_hide)
            time.sleep(0.5)
            mn = float(self.cfg.get("dc_min", DC_MIN))
            mx = float(self.cfg.get("dc_max", DC_MAX))
            if mx < mn:
                mn, mx = mx, mn
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                taps = random.randint(DC_TAPS_MIN, DC_TAPS_MAX)   # 좌표마다 7~9회 랜덤
                window = random.uniform(DC_BURST_MIN, DC_BURST_MAX)  # 1~2초 랜덤 구간
                # 7~9회 클릭을 window(초) 안에 랜덤 간격으로 모두 실행
                gaps = taps - 1
                if gaps > 0:
                    ws = [random.random() for _ in range(gaps)]
                    s = sum(ws) or 1.0
                    intervals = [window * w / s for w in ws]
                else:
                    intervals = []
                self.after(0, lambda a=i, t=taps, w=window: self.status.set(
                    f"🎯 일반던전충전 {a+1}/{n} — {t}회 연속({w:.1f}초 내)..."))
                for k in range(taps):
                    pyautogui.click(x, y)
                    if k < taps - 1:
                        time.sleep(intervals[k])
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.after(0, lambda: self.status.set(f"✔ 일반던전충전 완료 ({n}개 좌표)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"일반던전충전 오류: {err}"))
        finally:
            self._dc_running = False
            self._clear_busy("일반던전충전")
            self.after(0, self._restore_all)   # 완료 후 런처/서브창 복원

    def _assign_dc_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)  # 이전 클릭이 떼질 시간
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):  # 마우스 버튼 제외
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:  # ESC
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["dc_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_dc_hotkey_var"):
                    self._dc_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _dc_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 일반던전충전 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("dc_hotkey")
            if not getattr(self, "_dc_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_dc_running", False):
                threading.Thread(target=self._run_dc, daemon=True).start()
            prev = down

    # ── 인형 탐험 (16슬롯 × 18좌표, 슬롯별 순차 클릭) ──
    def _open_doll_win(self):
        self._open_section_win("_doll_win", "🧸 인형 탐험", self._build_doll, w=440, h=440)

    def _build_doll(self, parent):
        tk.Label(parent, text=f"인형 탐험  (슬롯당 {DOLL_CLICKS}좌표 순차 클릭)",
                 font=("맑은 고딕", 9, "bold"), fg="#b9770e").pack(anchor="w", padx=4, pady=(4,2))

        hr = tk.Frame(parent); hr.pack(pady=3)
        self.btn_doll_run = tk.Button(hr, text="▶  인형탐험 실행",
            font=("맑은 고딕", 9, "bold"), bg="#b9770e", fg="white",
            activebackground="#8a5809", width=15, height=2, command=self._start_doll)
        self.btn_doll_run.pack(side="left", padx=(0, 3))
        self.btn_doll_stop = tk.Button(hr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_doll_stop", True) or self.status.set("인형탐험 멈추는 중..."),
            state="disabled")
        self.btn_doll_stop.pack(side="left")
        tk.Button(hr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#8e44ad", fg="white", width=18,
            command=self._group_copy_doll).pack(side="left", padx=(8,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=6, pady=3)

        # 4×4 세로(열 우선) 그리드 — 01~04 첫 열, 05~08 둘째 열, …
        wg = tk.Frame(parent); wg.pack(padx=6, pady=4)
        self._doll_enable_btns = []
        self._doll_coord_sv    = []
        for idx in range(DOLL_SLOTS):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg, bd=1, relief="groove", padx=3, pady=2)
            cell.grid(row=r, column=c, padx=5, pady=4)
            top = tk.Frame(cell); top.pack()
            tk.Label(top, text=f"{idx+1:02d}", font=("맑은 고딕", 9, "bold"), fg="#555").pack(side="left")
            en = self.cfg["doll_slots"][idx].get("enabled", True)
            eb = tk.Button(top, text="ON" if en else "OFF", font=("맑은 고딕", 7, "bold"), width=4,
                           bg="#27ae60" if en else "#95a5a6", fg="white", pady=0,
                           command=lambda x=idx: self._toggle_doll_enable(x))
            eb.pack(side="left", padx=(4,0))
            self._doll_enable_btns.append(eb)
            reg = sum(1 for cc in self.cfg["doll_slots"][idx].get("coords", []) if cc)
            sv = tk.StringVar(value=f"좌표 {reg}/{DOLL_CLICKS}")
            self._doll_coord_sv.append(sv)
            tk.Button(cell, textvariable=sv, font=("맑은 고딕", 8, "bold"),
                      bg="#b9770e", fg="white", width=10,
                      command=lambda x=idx: self._open_doll_slot(x)).pack(pady=(3,0))
            tk.Button(cell, text="▶ 테스트", font=("맑은 고딕", 7), bg="#27ae60", fg="white", width=10,
                      command=lambda x=idx: self._test_doll(x)).pack(pady=(2,1))

        self._doll_pop_win = None
        self._refresh_doll_display()

    def _open_doll_slot(self, idx):
        """슬롯 하나의 18좌표 등록 팝업 (셀의 '좌표 x/18' 클릭 시)."""
        if getattr(self, "_doll_pop_win", None) and self._doll_pop_win.winfo_exists():
            try: self._doll_pop_win.destroy()
            except Exception: pass
        win = tk.Toplevel(self); self._doll_pop_win = win; self._doll_pop_slot = idx
        win.title(f"🧸 인형탐험 #{idx+1:02d} 좌표 등록")
        win.attributes("-topmost", True)

        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        tk.Label(top, text=f"#{idx+1:02d}  이름", font=("맑은 고딕", 9, "bold")).pack(side="left")
        nv = tk.StringVar(value=self.cfg["doll_slots"][idx].get("name", "미등록"))
        self._doll_pop_name = nv
        ent = tk.Entry(top, textvariable=nv, font=("맑은 고딕", 9), width=14)
        ent.pack(side="left", padx=6)
        ent.bind("<FocusOut>", lambda e: self._save_doll_pop_name())
        ent.bind("<Return>",   lambda e: self._save_doll_pop_name())

        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        self._doll_pop_vars = []; self._doll_pop_btns = []
        coords = self.cfg["doll_slots"][idx].get("coords", [None]*DOLL_CLICKS)
        for j in range(DOLL_CLICKS):
            cc = tk.Frame(grid); cc.grid(row=j//6, column=j%6, padx=4, pady=4)
            tk.Label(cc, text=f"{j+1}", font=("맑은 고딕", 7), fg="#555").pack()
            on = j < len(coords) and coords[j]
            cv = tk.StringVar(value="✔" if on else "✗")
            self._doll_pop_vars.append(cv)
            b = tk.Button(cc, textvariable=cv, font=("맑은 고딕", 8), width=4, pady=2,
                          bg="#27ae60" if on else "#7f8c8d", fg="white",
                          command=lambda x=idx, c=j: self._reg_doll_click(x, c))
            b.pack(); self._doll_pop_btns.append(b)

        bot = tk.Frame(win); bot.pack(pady=(4,10))
        tk.Button(bot, text="👁 미리보기", font=("맑은 고딕", 8), bg="#566573", fg="white",
                  command=lambda: self._preview_doll(idx)).pack(side="left", padx=3)
        if idx > 0:
            tk.Button(bot, text="↑ 윗슬롯 복사", font=("맑은 고딕", 8), bg="#8e44ad", fg="white",
                      command=lambda: self._group_copy_doll_slot(idx)).pack(side="left", padx=3)
        tk.Button(bot, text="× 전체삭제", font=("맑은 고딕", 8), fg="white", bg="#c0392b",
                  command=lambda: self._del_doll(idx)).pack(side="left", padx=3)
        tk.Button(bot, text="닫기", font=("맑은 고딕", 8),
                  command=win.destroy).pack(side="left", padx=3)

    def _save_doll_pop_name(self):
        i = getattr(self, "_doll_pop_slot", None)
        if i is not None and getattr(self, "_doll_pop_name", None) is not None:
            self.cfg["doll_slots"][i]["name"] = self._doll_pop_name.get().strip() or "미등록"
            save_cfg(self.cfg)

    def _toggle_doll_enable(self, idx):
        cur = self.cfg["doll_slots"][idx].get("enabled", True)
        self.cfg["doll_slots"][idx]["enabled"] = not cur
        save_cfg(self.cfg)
        self._refresh_doll_display()

    def _refresh_doll_display(self):
        # 그리드 셀 (ON/OFF + 좌표 개수)
        if getattr(self, "_doll_enable_btns", None):
            for i in range(DOLL_SLOTS):
                s = self.cfg["doll_slots"][i]
                en = s.get("enabled", True)
                self._doll_enable_btns[i].config(text="ON" if en else "OFF",
                                                 bg="#27ae60" if en else "#95a5a6")
                reg = sum(1 for c in s.get("coords", []) if c)
                self._doll_coord_sv[i].set(f"좌표 {reg}/{DOLL_CLICKS}")
        # 열린 좌표 등록 팝업의 18버튼 갱신
        pw = getattr(self, "_doll_pop_win", None)
        if pw and pw.winfo_exists():
            i = self._doll_pop_slot
            coords = self.cfg["doll_slots"][i].get("coords", [None]*DOLL_CLICKS)
            for j in range(DOLL_CLICKS):
                on = j < len(coords) and coords[j]
                self._doll_pop_vars[j].set("✔" if on else "✗")
                self._doll_pop_btns[j].config(bg="#27ae60" if on else "#7f8c8d")

    def _reg_doll_click(self, slot_idx, click_idx):
        self._save_doll_pop_name()
        self._doll_reg_idx  = slot_idx
        self._doll_reg_step = click_idx
        name = self.cfg["doll_slots"][slot_idx].get("name", f"#{slot_idx+1}")
        self.status.set(f"3초 후 [{name}] 좌표{click_idx+1} 위치 클릭하세요!")
        def _go():
            pw = getattr(self, "_doll_pop_win", None)
            if pw and pw.winfo_exists():
                try: pw.withdraw()   # 팝업이 타깃 가리지 않게 잠시 숨김
                except Exception: pass
            self.withdraw(); time.sleep(0.2); CoordOverlay(self, mode="doll")
        self.after(3000, _go)

    def on_doll_coord(self, x, y):
        idx, step = self._doll_reg_idx, self._doll_reg_step
        coords = self.cfg["doll_slots"][idx].get("coords", [None]*DOLL_CLICKS)
        while len(coords) < DOLL_CLICKS: coords.append(None)
        coords[step] = [x, y]
        self.cfg["doll_slots"][idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ 인형탐험 #{idx+1} 좌표{step+1} 등록: ({x},{y})")
        self.deiconify()
        pw = getattr(self, "_doll_pop_win", None)   # 등록 팝업 다시 보이기
        if pw and pw.winfo_exists():
            try: pw.deiconify(); pw.lift()
            except Exception: pass

    def _del_doll(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"인형탐험 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["doll_slots"][idx]["coords"] = [None]*DOLL_CLICKS
        save_cfg(self.cfg); self._refresh_doll_display()

    def _test_doll(self, idx):
        h = self.cfg["doll_slots"][idx]
        coords = [c for c in h.get("coords", []) if c]
        if not coords:
            messagebox.showwarning("등록 필요", f"#{idx+1} 슬롯에 등록된 좌표가 없습니다."); return
        # 슬롯별 실행도 잠금+대기열 — 연속으로 눌러두면 한 슬롯 완료 후 다음 슬롯 실행
        busy_name = f"인형탐험 #{idx+1:02d}"
        if not self._try_busy_or_queue(busy_name, lambda: self._test_doll(idx)): return
        self._doll_stop = False
        name = h.get("name", f"#{idx+1}")
        self.iconify()
        def run():
            try:
                _clicked = 0
                for j, c in enumerate(h.get("coords", [])):
                    if not c: continue
                    if getattr(self, "_doll_stop", False): break
                    if _clicked == 0:
                        time.sleep(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX))  # 첫 클릭 전 여유
                    self.status.set(f"[{name}] 좌표{j+1} 실행...")
                    pyautogui.click(*c)
                    _clicked += 1
                    time.sleep(random.uniform(DOLL_MIN, DOLL_MAX))  # 좌표 간 간격
                self.status.set(f"✔ [{name}] 슬롯 완료!")
            except Exception as e:
                self.status.set(f"오류: {e}")
            finally:
                self._clear_busy(busy_name)   # 잠금 해제 → 대기열의 다음 슬롯이 이어서 실행
                self.deiconify()
        threading.Thread(target=run, daemon=True).start()

    def _preview_doll(self, idx):
        coords = self.cfg["doll_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg["doll_slots"][idx].get("name", f"#{idx+1:02d}")
        def rereg(dot_idx):
            self._doll_reg_idx  = idx
            self._doll_reg_step = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="doll"))
        def _save(dot_idx, nx, ny):
            self.cfg["doll_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_doll_display()
            self.status.set(f"✔ 인형탐험 #{idx+1:02d} 좌표{dot_idx+1} 이동 저장: ({nx},{ny})")
        self._open_dot_preview(f"인형탐험 #{idx+1:02d} {name}", dots, rereg_fn=rereg, save_fn=_save, dot_r=8)

    def _group_copy_doll_slot(self, idx):
        import copy
        src = self.cfg["doll_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다"); return
        self.cfg["doll_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ #{idx:02d} → #{idx+1:02d} 좌표 복사 완료")

    def _group_copy_doll(self):
        import copy
        src = self.cfg["doll_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다"); return
        for i in range(1, DOLL_SLOTS):
            self.cfg["doll_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ #01 좌표 → #02~#{DOLL_SLOTS:02d} 전체 복사 완료")

    def _doll_wait(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if getattr(self, "_doll_stop", False): return False
            time.sleep(0.05)
        return True

    def _start_doll(self):
        active = [h for h in self.cfg.get("doll_slots", [])
                  if h.get("enabled", True) and any(c for c in h.get("coords", []))]
        if not active:
            messagebox.showwarning("등록 필요", "실행할(ON) 인형 탐험 좌표가 없습니다."); return
        if not self._try_busy_or_queue("인형탐험", self._start_doll): return
        self._doll_stop = False
        if hasattr(self, "btn_doll_run"):  self.btn_doll_run.config(state="disabled")
        if hasattr(self, "btn_doll_stop"): self.btn_doll_stop.config(state="normal")
        self._minimize_claude()
        self.iconify()
        threading.Thread(target=self._run_task, args=("인형탐험", self._run_doll_standalone), daemon=True).start()

    def _run_doll_standalone(self):
        self._run_doll()
        if hasattr(self, "btn_doll_run"):  self.btn_doll_run.config(state="normal", bg="#b9770e", text="▶  인형탐험 실행")
        if hasattr(self, "btn_doll_stop"): self.btn_doll_stop.config(state="disabled")
        self._doll_stop = False
        self.after(0, self._restore_all)

    def _run_doll(self):
        try:
            slots = list(enumerate(self.cfg.get("doll_slots", [])))
            active = [(i, h) for i, h in slots
                      if h.get("enabled", True) and any(c for c in h.get("coords", []))]
            for si, (i, h) in enumerate(active):
                if getattr(self, "_doll_stop", False): self.status.set("인형탐험 멈춤"); return
                name = h.get("name", f"#{i+1}")
                coords = h.get("coords", [])
                _clicked = 0   # 이 슬롯에서 실제로 클릭한 횟수
                for j, coord in enumerate(coords):
                    if not coord: continue
                    if getattr(self, "_doll_stop", False): self.status.set("인형탐험 멈춤"); return
                    if _clicked == 0:
                        # 첫 클릭 '전' 여유 — 바로 클릭하지 않음 (0.5~1초)
                        if not self._doll_wait(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX)):
                            self.status.set("인형탐험 멈춤"); return
                    self.status.set(f"🧸 [{name}] 좌표 {j+1}/{DOLL_CLICKS}...")
                    pyautogui.click(*coord)
                    _clicked += 1
                    if j < len(coords) - 1:
                        if not self._doll_wait(random.uniform(DOLL_MIN, DOLL_MAX)):
                            self.status.set("인형탐험 멈춤"); return
                if si < len(active) - 1:
                    if not self._doll_wait(random.uniform(DOLL_SLOT_MIN, DOLL_SLOT_MAX)):
                        self.status.set("인형탐험 멈춤"); return
            self.status.set(f"✔ 인형 탐험 완료! ({len(active)}개 슬롯)")
        except Exception as e:
            self.status.set(f"인형탐험 오류: {e}")

    # ── 클로드 앱 최소화 (좌표 겹침 방지 + 야간 자동 최소화) ──
    def _minimize_claude_windows(self, only_background=False):
        """제목에 'claude'가 들어간 창을 최소화한다.
        only_background=True면 사용자가 보고 있는(포그라운드) 창은 건드리지 않는다."""
        import ctypes
        SW_MINIMIZE = 6
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow() if only_background else None
        def _cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if "claude" in buf.value.lower():
                    if only_background and hwnd == fg:
                        return True  # 사용자가 열어둔 창은 그대로 둠
                    if not user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try:
            user32.EnumWindows(WNDENUMPROC(_cb), 0)
        except Exception:
            pass

    def _claude_ui_state(self):
        """(보임여부, 포그라운드여부) — 클로드 창이 화면에 떠 있나 / 사용자가 앞에 두고 있나."""
        import ctypes
        u = ctypes.windll.user32
        fg = u.GetForegroundWindow()
        st = {"vis": False, "fg": False}
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" in b.value.lower() and not u.IsIconic(hwnd):
                    st["vis"] = True
                    if hwnd == fg:
                        st["fg"] = True
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass
        return st["vis"], st["fg"]

    def _center_claude(self):
        """클로드 앱 창을 화면 가운데로 이동 (아이디 영역 등 우측을 가리지 않게).
        크기는 그대로, 위치만 중앙으로. 최소화 상태면 건드리지 않음.
        사용자가 직접 옮겼으면(중앙 근처가 아닌 곳에 두면) 더는 강제로 안 옮김."""
        if getattr(self, "_claude_user_moved", False):
            return
        from ctypes import wintypes
        u = ctypes.windll.user32
        sw = u.GetSystemMetrics(0); sh = u.GetSystemMetrics(1)
        SWP_NOSIZE = 0x0001; SWP_NOZORDER = 0x0004; SWP_NOACTIVATE = 0x0010
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" not in b.value.lower():
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left; h = r.bottom - r.top
                if w > 200 and h > 200:   # 실제 앱 창만 (작은 부속 창 제외)
                    x = max(0, (sw - w) // 2)
                    y = max(0, (sh - h) // 2)
                    self._claude_center_pos = (x, y)
                    if abs(r.left - x) > 3 or abs(r.top - y) > 3:   # 이미 중앙이면 안 건드림
                        u.SetWindowPos(hwnd, 0, x, y, 0, 0,
                                       SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass

    def _claude_pos(self):
        """현재 클로드 앱 창의 (x, y) 반환. 없으면 None."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        res = {"p": None}
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" not in b.value.lower():
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) > 200 and (r.bottom - r.top) > 200:
                    res["p"] = (r.left, r.top)
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass
        return res["p"]

    def _center_claude_tick(self):
        """클로드를 화면 가운데로 유지. 단, 사용자가 직접 옮기면(우리가 둔 위치에서 벗어나면) 중단."""
        try:
            if not getattr(self, "_claude_user_moved", False):
                cur = self._claude_pos()
                cp = getattr(self, "_claude_center_pos", None)
                if cur and cp and (abs(cur[0] - cp[0]) > 20 or abs(cur[1] - cp[1]) > 20):
                    self._claude_user_moved = True   # 사용자가 옮김 → 더는 강제 중앙 배치 안 함
                else:
                    self._center_claude()
        except Exception:
            pass
        self.after(8000, self._center_claude_tick)

    def _claude_minimize_tick(self):
        """밤 11시~새벽 6시엔 클로드 앱을 최소화 유지.
        단, 사용자가 직접 클로드를 열면(포그라운드로) 자동 최소화를 멈추고,
        사용자가 다시 최소화하면 재개한다 — 사용자가 클릭해서 연 걸 계속 내리지 않도록."""
        import datetime
        vis, fg = self._claude_ui_state()
        if fg:
            self._claude_user_open = True    # 사용자가 열어둠 → 자동 최소화 중지
        elif not vis:
            self._claude_user_open = False   # 클로드가 안 보임(최소화됨) → 재개
        h = datetime.datetime.now().hour
        if (h >= 23 or h < 6) and not getattr(self, "_claude_user_open", False):
            self._minimize_claude_windows(only_background=True)
        self.after(30000, self._claude_minimize_tick)

    def _system_idle_ms(self):
        """시스템 전체 마지막 입력(마우스·키보드) 이후 경과 시간(ms)."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO(); lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return ctypes.windll.kernel32.GetTickCount() - lii.dwTime

    def _claude_idle_minimize_tick(self):
        """사용자가 3분간 아무 작업(입력)도 안 하면 클로드 앱도 최소화.
        (매크로 실행 중엔 pyautogui가 입력을 내서 유휴가 아니므로 발동 안 함)"""
        try:
            if self._system_idle_ms() >= 180000:   # 3분
                self._minimize_claude_windows(only_background=False)
        except Exception:
            pass
        self.after(20000, self._claude_idle_minimize_tick)

    def _claude_attention_loop(self):
        """클로드 앱이 주의를 요청(작업표시줄 플래시)하면 자동으로 복원해서 앞으로.
        승인(항상 허용/한번 허용) 등 클릭이 필요할 때, 최소화돼 있어도 스스로 올라오게 한다.
        사용자가 그냥 최소화한 경우와 구분하려고, 짧은 시간에 '반복되는' 상태변화(=플래시)만 복원한다."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        EVENT_OBJECT_STATECHANGE = 0x800A
        WINEVENT_OUTOFCONTEXT = 0x0000
        OBJID_WINDOW = 0
        hits = {}   # hwnd -> [최근 상태변화 시각들]

        def _is_claude(hwnd):
            try:
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                return "claude" in b.value.lower()
            except Exception:
                return False

        WEP = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                 wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _cb(hHook, event, hwnd, idObject, idChild, dwThread, dwMs):
            try:
                if not hwnd or idObject != OBJID_WINDOW:
                    return
                if not u.IsIconic(hwnd):     # 이미 보이면 무시
                    return
                if not _is_claude(hwnd):
                    return
                now = time.time()
                ts = [t for t in hits.get(hwnd, []) if now - t < 2.0] + [now]
                hits[hwnd] = ts
                # 2초 안에 상태변화 3번 이상 = 플래시(주의 요청) → 복원
                if len(ts) >= 3:
                    hits[hwnd] = []
                    u.ShowWindow(hwnd, 9)    # SW_RESTORE
                    try: u.SetForegroundWindow(hwnd)
                    except Exception: pass
                    try: self._center_claude()   # 복원 시 가운데로
                    except Exception: pass
            except Exception:
                pass

        cb = WEP(_cb)
        self._claude_wineventproc = cb   # 콜백 GC 방지 (참조 유지)
        try:
            u.SetWinEventHook(EVENT_OBJECT_STATECHANGE, EVENT_OBJECT_STATECHANGE,
                              0, cb, 0, 0, WINEVENT_OUTOFCONTEXT)
        except Exception:
            return
        msg = wintypes.MSG()
        while True:
            try:
                r = u.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r == 0 or r == -1:
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                time.sleep(0.5)

    def _mark_activity(self, e=None):
        """메인런처(및 서브창) 조작 감지 — 유휴 최소화 타이머 리셋."""
        self._last_activity = time.time()

    def _idle_minimize_tick(self):
        """2분간 아무 조작이 없으면 메인런처를 최소화(뒤 화면 가리지 않게).
        사용자가 클릭해서 다시 올리면(맵 이벤트) 타이머가 리셋된다."""
        try:
            idle = time.time() - getattr(self, "_last_activity", time.time())
            running = getattr(self, "_running", False)  # 전체 자동실행 중이면 관여 안 함
            if not running and idle >= 120:
                try: normal = (self.state() == "normal")
                except Exception: normal = False
                if normal:
                    self.iconify()
        except Exception:
            pass
        self.after(15000, self._idle_minimize_tick)

    def _popup_guard_loop(self):
        """실행 방해 팝업 감시·정리.
        - 우하단 윈도우 알림 토스트: 항상 숨김(안전).
        - 항상 위(topmost) 낯선 팝업(업데이트 나그 등): 실행 중(런처 최소화 상태)일 때만 최소화.
        우리 런처/서브창(같은 PID)·게임(Purple/리니지M)·바탕화면/작업표시줄은 건드리지 않음."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        SW_HIDE = 0
        SW_MINIMIZE = 6
        my_pid = os.getpid()
        SKIP_CLASSES = {
            "progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
            "button", "trayclockwclass", "notifyiconoverflowwindow",
            "tooltips_class32", "windows.ui.input.inputsite.windowclass",
        }
        sw = u.GetSystemMetrics(0)
        sh = u.GetSystemMetrics(1)
        k = ctypes.windll.kernel32
        # 게임/퍼플/NCSoft 계열 프로세스 — 이 창들은 절대 건드리지 않음
        # (계정 전환·구글 계정 선택 팝업이 이 CEF/웹뷰 창으로 뜸)
        SKIP_PROCS = {
            "purple.exe", "purplebox.exe", "purpleon.exe", "purpleonp.exe",
            "purple-agent.exe", "ncoverlaycefweb32.exe", "lineagem.exe",
            "msedgewebview2.exe",
        }

        def _pid_of(hwnd):
            p = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            return p.value

        def _pname_of(pid):
            try:
                h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if not h:
                    return ""
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                k.CloseHandle(h)
                return os.path.basename(buf.value).lower() if ok else ""
            except Exception:
                return ""

        def _is_game_proc(pid):
            return _pname_of(pid) in SKIP_PROCS

        def _cb(hwnd, running):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                pid = _pid_of(hwnd)
                if pid == my_pid:                    # 우리 런처/서브창
                    return True
                tb = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, tb, 256)
                title = tb.value
                cbn = ctypes.create_unicode_buffer(256); u.GetClassNameW(hwnd, cbn, 256)
                cls = cbn.value.lower()
                if cls in SKIP_CLASSES:
                    return True
                tl = title.lower()
                if "purple" in tl or "리니지m" in tl or "claude" in tl:  # 게임/런처/클로드(항상위라 오인 방지)
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left; h = r.bottom - r.top
                if w <= 0 or h <= 0:
                    return True
                # 1) 알림 토스트: 우하단 코너의 작은 CoreWindow → 숨김
                if (cls == "windows.ui.core.corewindow"
                        and r.right >= sw - 60 and r.bottom >= sh - 160
                        and w < 640 and h < 520):
                    if _is_game_proc(pid):           # 게임/퍼플/NCSoft 창 보호
                        return True
                    u.ShowWindow(hwnd, SW_HIDE)
                    return True
                # 2) 실행 중일 때만: 항상 위(topmost) 낯선 창 → 최소화
                if running and title:
                    ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    if ex & WS_EX_TOPMOST:
                        if _is_game_proc(pid):       # 게임/퍼플/NCSoft 창 보호 (전환 팝업 등)
                            return True
                        u.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        while True:
            try:
                lh = u.FindWindowW(None, "리니지M 자동 실행")
                running = bool(lh and u.IsIconic(lh))   # 런처 최소화 = 실행 중으로 간주
                cb_ptr = WNDENUMPROC(lambda h, l, rn=running: _cb(h, rn))
                u.EnumWindows(cb_ptr, 0)
            except Exception:
                pass
            time.sleep(0.5)

    def _reg_coord(self, key):
        self._reg_target = key
        self.status.set(f"3초 후 [{LABELS[key]}] 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="single")])

    def on_coord(self, x, y):
        if isinstance(self._reg_target, str) and self._reg_target.startswith("__pass_"):
            ci = int(self._reg_target.split("_")[3])
            pc = self.cfg.setdefault("pass_coords", [None]*PASS_CLICKS)
            while len(pc) < PASS_CLICKS: pc.append(None)
            pc[ci] = [x, y]
            if hasattr(self, "_pass_reg_sv") and self._pass_reg_sv:
                self._pass_reg_sv.set(f"({x},{y})")
        else:
            self.cfg[self._reg_target] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 등록: ({x},{y})")
        self.deiconify()

    def _reg_char_btn(self):
        n = len(self.cfg.get("char_btns", []))
        self.status.set(f"3초 후 캐릭터 #{n+1} 접속 버튼 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="char")])

    def on_char_coord(self, x, y):
        self.cfg.setdefault("char_btns", []).append([x, y])
        n = len(self.cfg["char_btns"])
        # 대응하는 사냥 슬롯 이름이 미등록이면 자동 설정
        hunt_slots = self.cfg.get("hunt_slots", [])
        if n - 1 < len(hunt_slots):
            if hunt_slots[n-1].get("name", "미등록") == "미등록":
                hunt_slots[n-1]["name"] = f"캐릭터{n}"
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 캐릭터 #{n} 등록: ({x},{y})  →  사냥 슬롯 #{n} 연동됨")
        self.deiconify()

    def _clear_char_btns(self):
        self.cfg["char_btns"] = []
        save_cfg(self.cfg); self._refresh_ui()

    # ── 클릭 슬롯 ─────────────────────────────────────────────────────
    def _reg_slot(self, idx):
        self._slot_target = idx
        self._slot_step   = 0
        self.cfg["click_slots"][idx] = [None, None]
        self._do_slot_step()

    def _do_slot_step(self):
        step = self._slot_step
        self.status.set(f"3초 후 #{self._slot_target+1}번 클릭{step+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="slot")])

    def on_slot_coord(self, x, y):
        idx, step = self._slot_target, self._slot_step
        slot = self.cfg["click_slots"][idx]
        while len(slot) <= step:
            slot.append(None)
        slot[step] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #{idx+1}번 클릭{step+1} 등록: ({x},{y})")
        self.deiconify()
        self._slot_step += 1
        max_steps = 3 if idx == 4 else 2
        if self._slot_step < max_steps:
            self.after(500, self._do_slot_step)
        else:
            self.status.set(f"✔ #{idx+1}번 슬롯 완료!")

    def _reg_slot_step(self, idx, step):
        """클릭1 또는 클릭2만 개별 등록"""
        if self.cfg["click_slots"][idx] is None:
            self.cfg["click_slots"][idx] = [None, None]
        self._slot_target = idx
        self._slot_step   = step
        self.status.set(f"3초 후 #{idx+1}번 클릭{step+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="slot")])

    def _group_copy_slot(self, idx):
        import copy
        src = self.cfg["click_slots"][idx-1]
        if not src or not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["click_slots"][idx] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        pair = self.cfg["click_slots"][idx]
        dots = []
        if pair[0]: dots.append((pair[0][0], pair[0][1], "1"))
        if pair[1]: dots.append((pair[1][0], pair[1][1], "2"))
        if dots:
            self.withdraw()
            self.after(300, lambda: _SlotGroupMoveOverlay(self, idx, dots))

    def _del_slot(self, idx):
        self.cfg["click_slots"][idx] = [None, None]
        save_cfg(self.cfg); self._refresh_ui()

    def _clear_click_slots(self):
        self.cfg["click_slots"] = [[None, None]] * CLICK_SLOTS
        save_cfg(self.cfg); self._refresh_ui()

    # ── 사냥 슬롯 ─────────────────────────────────────────────────────
    def _save_hunt_name(self, idx):
        name = self._hunt_name_vars[idx].get().strip() or "미등록"
        self._hunt_name_vars[idx].set(name)
        self.cfg["hunt_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _reg_hunt_click(self, slot_idx, click_idx):
        self._save_hunt_name(slot_idx)
        self._hunt_reg_idx  = slot_idx
        self._hunt_reg_step = click_idx
        name = self.cfg["hunt_slots"][slot_idx].get("name", f"#{slot_idx+1}")
        self.status.set(f"3초 후 [{name}] 클릭{click_idx+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="hunt")])

    def on_hunt_coord(self, x, y):
        idx, step = self._hunt_reg_idx, self._hunt_reg_step
        coords = self.cfg["hunt_slots"][idx].get("coords", [None] * HUNT_CLICKS)
        while len(coords) < HUNT_CLICKS:
            coords.append(None)
        coords[step] = [x, y]
        self.cfg["hunt_slots"][idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_ui()
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1}")
        self.status.set(f"✔ [{name}] 클릭{step+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_hunt_click(self, slot_idx, click_idx):
        if not messagebox.askyesno("좌표 삭제", f"사냥 #{slot_idx+1} 클릭{click_idx+1} 좌표를 삭제하시겠습니까?", default="no"):
            return
        coords = self.cfg["hunt_slots"][slot_idx].get("coords", [None] * HUNT_CLICKS)
        while len(coords) < HUNT_CLICKS:
            coords.append(None)
        coords[click_idx] = None
        self.cfg["hunt_slots"][slot_idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_ui()

    def _test_hunt(self, idx):
        h = self.cfg["hunt_slots"][idx]
        coords = [c for c in h.get("coords", []) if c]
        if not coords:
            messagebox.showwarning("등록 필요", f"#{idx+1} 슬롯에 등록된 좌표가 없습니다."); return
        name = h.get("name", f"#{idx+1}")
        self.status.set(f"[{name}] 테스트 실행 중...")
        self.iconify()
        def run():
            try:
                for j, coord in enumerate(h.get("coords", [])):
                    if not coord: continue
                    self.status.set(f"[{name}] 클릭{j+1} 테스트...")
                    pyautogui.click(*coord)
                    if j < len(h["coords"]) - 1:
                        time.sleep(random.uniform(0.1, 0.6))
                self.status.set(f"✔ [{name}] 테스트 완료!")
            except Exception as e:
                self.status.set(f"오류: {e}")
            finally:
                self.deiconify()
        threading.Thread(target=run, daemon=True).start()

    def _toggle_hunt_enable(self, idx):
        cur = self.cfg["hunt_slots"][idx].get("enabled", True)
        self.cfg["hunt_slots"][idx]["enabled"] = not cur
        save_cfg(self.cfg); self._refresh_ui()

    def _del_hunt(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"사냥 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["hunt_slots"][idx]["coords"] = [None] * HUNT_CLICKS
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_hunt(self, idx):
        coords = self.cfg["hunt_slots"][idx].get("coords", [])
        dots = [(x, y, n+1) for n, c in enumerate(coords)
                if c and len(c) >= 2 for x, y in [c[:2]]]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._hunt_reg_idx  = idx
            self._hunt_reg_step = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="hunt"))

        def _save(dot_idx, nx, ny):
            self.cfg["hunt_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 사냥 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"사냥 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=8)

    def _group_copy_hunt_slot(self, idx):
        """위 슬롯 좌표 복사 후 그룹 드래그로 위치 조정"""
        import copy
        src = self.cfg["hunt_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["hunt_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()

        # 그룹 드래그 미리보기 열기
        coords = self.cfg["hunt_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            return
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1:02d}")

        def _save_group(_, nx, ny):
            pass  # 개별 저장은 아래 group_save에서 처리

        self.withdraw()
        self.after(300, lambda: _HuntGroupMoveOverlay(self, idx, dots))

    def _group_copy_hunt(self):
        import copy
        src = self.cfg["hunt_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, HUNT_SLOTS):
            self.cfg["hunt_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{HUNT_SLOTS:02d} 전체 복사 완료")

    # ── 멈춤 ──────────────────────────────────────────────────────────
    # ── 9시 클릭 스케줄러 ─────────────────────────────────────────────
    def _set_sleep_prevention(self, prevent: bool):
        ES_CONTINUOUS       = 0x80000000
        ES_SYSTEM_REQUIRED  = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        if prevent:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    def _toggle_mail(self):
        has = any(any(s.get("coords", [])) for s in self.cfg.get("mail_slots", []))
        if not has:
            messagebox.showwarning("등록 필요", "먼저 우편함 좌표를 등록해주세요."); return
        self._mail_on = not self._mail_on
        if self._mail_on:
            self._mail_triggered_date = None
            self.btn_mail.config(text="🕘 22:30~23:30 클릭  ON", bg="#27ae60")
            self.status.set("우편 클릭 ON — 밤 10:30~11:30 랜덤 실행")
        else:
            self.btn_mail.config(text="🕘 22:30~23:30 클릭  OFF", bg="#7f8c8d")
            self.status.set("우편 클릭 OFF")

    def _mail_scheduler_tick(self):
        import datetime
        if self._mail_on:
            now = datetime.datetime.now()
            today = now.date()
            # 22:30~23:30 사이에 한 번만 트리거
            in_window = ((now.hour == 22 and now.minute >= 30) or
                         (now.hour == 23 and now.minute < 30))
            if in_window and self._mail_triggered_date != today:
                if self._is_busy():
                    self.status.set("🕘 우편 스케줄 대기 — 다른 작업 실행 중")
                else:
                    self._mail_triggered_date = today
                    self._busy_task = "우편함(스케줄)"
                    threading.Thread(target=self._run_task,
                        args=("우편함(스케줄)", self._run_mail_scheduled), daemon=True).start()
            elif self._mail_triggered_date != today:
                target = now.replace(hour=22, minute=30, second=0, microsecond=0)
                if now >= target:
                    target += datetime.timedelta(days=1)
                diff = target - now
                h, m = divmod(int(diff.total_seconds()) // 60, 60)
                self.status.set(f"🕘 우편 클릭 대기 중... (약 {h}시간 {m}분 후 22:30~23:30 실행)")
        self.after(10000, self._mail_scheduler_tick)

    def _past_scheduler_tick(self):
        import datetime
        now = datetime.datetime.now()
        today = now.date()
        is_wed = now.weekday() == 2   # 월=0 … 수=2 : 수요일엔 과거섬 스케줄 건너뜀
        if is_wed:
            self.status.set("🏝 과거섬: 수요일은 스케줄 실행 안 함 (건너뜀)")
        elif now.hour == 5 and 3 <= now.minute <= 25 and self._past_triggered_date != today:
            if self._is_busy():
                self.status.set("🏝 과거섬 스케줄 대기 — 다른 작업 실행 중")
            else:
                self._past_triggered_date = today
                self._busy_task = "과거섬(스케줄)"
                threading.Thread(target=self._run_task,
                    args=("과거섬(스케줄)", self._run_past_scheduled), daemon=True).start()
        elif self._past_triggered_date != today:
            target = now.replace(hour=5, minute=3, second=0, microsecond=0)
            if now >= target:
                target += datetime.timedelta(days=1)
            diff = target - now
            h, m = divmod(int(diff.total_seconds()) // 60, 60)
            self.status.set(f"🏝 과거섬 대기 중... (약 {h}시간 {m}분 후 5:03~5:25 실행)")
        self.after(30000, self._past_scheduler_tick)

    def _purple_check_tick(self):
        """매일 새벽 4시에 한 번 퍼플이 지정 계정인지 확인 → 아니면 전환 후 최소화"""
        import threading, datetime
        now = datetime.datetime.now()
        today = now.date()
        if now.hour == 4 and self._purple_triggered_date != today:
            if self._is_busy():
                self.status.set("🔍 4시 퍼플 확인 대기 — 다른 작업 실행 중")
            else:
                self._purple_triggered_date = today
                self._busy_task = "퍼플확인(4시)"
                threading.Thread(target=self._run_task,
                    args=("퍼플확인(4시)", self._purple_check_worker), daemon=True).start()
        self.after(60000, self._purple_check_tick)

    def _purple_check_worker(self):
        import win32gui, win32con, ctypes
        self._minimize_claude()          # 클로드(항상위)가 클릭을 가리지 않게 먼저 내림
        self.after(0, self.iconify)      # 메인런처도 내림
        win = find_purple()
        if not win:
            self.after(0, lambda: self.status.set("🔍 퍼플 확인: 퍼플 창 없음"))
            return
        hwnd = win32gui.FindWindow(None, win.title)
        orig_placement = None
        try:
            if hwnd:
                orig_placement = win32gui.GetWindowPlacement(hwnd)
                # 퍼플을 맨 앞으로 — 아이디 확인/캡처가 되려면 퍼플이 최상단이어야 함
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)
                try:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                try:
                    win32gui.BringWindowToTop(hwnd)
                except Exception:
                    pass
                time.sleep(1.2)
            self.after(0, lambda: self.status.set("🔍 퍼플 확인 중..."))

            # 1단계: 리니지M 좌측버튼(profile_reveal_btn) 클릭 → 아이디 표시 → 확인
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(2)

            matched, ocr_id, ratio = self._is_target_account(hwnd)
            self.after(0, lambda o=ocr_id, r=ratio: self.status.set(
                f"🔍 퍼플 아이디 '{o}' (일치율 {int(r*100)}%)"))

            # 2단계: 지정 아이디 아니면 전환 → 전환 후 재검증, 아직 다르면 최대 2회 재전환
            MAX_SWITCH_TRIES = 2
            attempt = 0
            while not matched and attempt < MAX_SWITCH_TRIES:
                attempt += 1
                self.after(0, lambda a=attempt: self.status.set(
                    f"🔍 지정 아이디 아님 → 전환 시도 {a}/{MAX_SWITCH_TRIES}..."))
                if self.cfg.get("profile_btn"):
                    pyautogui.click(*self.cfg["profile_btn"]); time.sleep(2)
                if self.cfg.get("google_acc"):
                    pyautogui.click(*self.cfg["google_acc"]); time.sleep(2)
                if self.cfg.get("confirm_btn"):
                    pyautogui.click(*self.cfg["confirm_btn"])
                    time.sleep(10)  # 계정 전환 후 로딩(약 8~10초) 대기
                # 전환 후 재검증 — 퍼플 hwnd가 새로 생기므로 다시 찾아 앞으로 + 아이디 재표시
                _re = win32gui.FindWindow(None, "PURPLE")
                if _re:
                    hwnd = _re
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE); time.sleep(0.5)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        win32gui.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    time.sleep(1.0)
                if self.cfg.get("profile_reveal_btn"):
                    pyautogui.click(*self.cfg["profile_reveal_btn"]); time.sleep(2)
                matched, ocr_id, ratio = self._is_target_account(hwnd)
                self.after(0, lambda o=ocr_id, r=ratio, a=attempt: self.status.set(
                    f"🔍 전환 {a}회 후 아이디 '{o}' (일치율 {int(r*100)}%)"))

            if matched:
                self.after(0, lambda: self.status.set("✔ 퍼플 지정계정 확인/전환 완료"))
            else:
                self.after(0, lambda: self.status.set(
                    f"⚠ 퍼플 전환 실패 — {MAX_SWITCH_TRIES}회 재시도했으나 지정 아이디로 못 바꿈"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"🔍 퍼플 확인 오류: {err}"))
        finally:
            # 계정 전환하면 퍼플 창이 새로 생겨 hwnd가 바뀌므로, 여기서 다시 찾아 최소화.
            # (확인/전환 중 오류가 나도 반드시 최소화 — 안 되면 다음 작업이 퍼플 위에서 막힘)
            try:
                _ph = win32gui.FindWindow(None, "PURPLE")
                if not _ph:
                    _w2 = find_purple()
                    _ph = win32gui.FindWindow(None, _w2.title) if _w2 else None
                if _ph:
                    win32gui.ShowWindow(_ph, win32con.SW_MINIMIZE)
                elif win:
                    win.minimize()
            except Exception:
                try: win.minimize()
                except Exception: pass

    def _purple_ensure_scroll(self):
        """퍼플을 지정 계정으로 전환하고 최소화."""
        try:
            import win32gui, win32con, ctypes
            hwnd = win32gui.FindWindow(None, "PURPLE")
            if not hwnd:
                self.status.set("⚠ 퍼플 창 없음 — 지정계정 확인 건너뜀")
                return

            orig_placement = win32gui.GetWindowPlacement(hwnd)

            # 1단계: 리니지M 좌측버튼(profile_reveal_btn) 클릭 → 계정 확인
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(1)

            matched, ocr_id, ratio = self._is_target_account(hwnd)
            self.status.set(f"{'✔ 아이디 확인됨' if matched else '🔄 아이디 다름 → 퍼플 전환 중...'} ('{ocr_id}' {int(ratio*100)}%)")

            if not matched:
                # 2단계: Purple 포그라운드로 가져와서 프로필 전환
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3)
                try:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(1.0)
                if self.cfg.get("profile_btn"):
                    pyautogui.click(*self.cfg["profile_btn"]); time.sleep(2)
                if self.cfg.get("google_acc"):
                    pyautogui.click(*self.cfg["google_acc"]); time.sleep(2)
                if self.cfg.get("confirm_btn"):
                    pyautogui.click(*self.cfg["confirm_btn"]); time.sleep(3)
                self.status.set("✔ 퍼플 지정계정 전환 완료")

            # 원래 상태로 복원 후 최소화
            win32gui.SetWindowPlacement(hwnd, orig_placement)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception as e:
            self.status.set(f"⚠ 퍼플 전환 오류: {e}")

    def _system_idle_seconds(self):
        """Windows 마지막 입력(마우스+키보드) 이후 경과 초"""
        import ctypes
        class _LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0

    def _wait_system_idle(self, minutes=15):
        """시스템이 minutes분 이상 유휴 상태가 될 때까지 대기. 멈춤 시 즉시 반환."""
        required = minutes * 60
        while True:
            if getattr(self, "_sched_any_stop", False):
                return
            idle = self._system_idle_seconds()
            if idle >= required:
                return
            remaining = int((required - idle) / 60)
            self.after(0, lambda r=remaining: self.status.set(
                f"⏸ 컴퓨터 사용 중 — {r}분 더 대기 후 스케줄 실행..."))
            for _ in range(60):  # 30초를 0.5초씩 나눠 stop 즉시 감지
                if getattr(self, "_sched_any_stop", False):
                    return
                time.sleep(0.5)

    def _wait_mouse_idle_sched(self, idle_sec=5.0):
        """스케줄 작업용 마우스 idle 대기 — stop flag 없이 단순 대기"""
        import pyautogui as _pg
        prev = _pg.position()
        time.sleep(0.1)
        cur = _pg.position()
        if cur == prev:
            return
        self.after(0, lambda: self.status.set(f"⏸ 마우스 움직임 감지 — {idle_sec}초 정지 후 재개..."))
        last_move = time.time()
        prev = cur
        while True:
            time.sleep(0.1)
            cur = _pg.position()
            if cur != prev:
                last_move = time.time()
                prev = cur
            elif time.time() - last_move >= idle_sec:
                return

    def _run_past_scheduled(self):
        import random, datetime
        self._sched_any_stop = False
        self._past_stop = False
        self._minimize_claude()          # 클로드(항상위)가 클릭 가리지 않게 먼저 내림
        self.after(0, self.iconify)
        slots = self.cfg.get("past_slots", [])
        active = [(i, s) for i, s in enumerate(slots)
                  if any(s.get("coords", []))]
        if not active:
            return

        # 각 슬롯마다 5:03~5:25 사이 무작위 시각 배정
        base = datetime.datetime.now().replace(hour=5, minute=3, second=0, microsecond=0)
        window = 22 * 60  # 22분
        schedule = sorted([(random.uniform(0, window), i, s) for i, s in active])

        self.status.set(f"🏝 과거섬 {len(active)}개 슬롯 랜덤 실행 대기...")
        elapsed = (datetime.datetime.now() - base).total_seconds()

        for delay, si, slot in schedule:
            wait = delay - elapsed
            if wait > 0:
                mins = int(wait // 60); secs = int(wait % 60)
                name = slot.get("name", f"#{si+1}")
                self.status.set(f"🏝 [{name}] {mins}분 {secs}초 후 실행...")
                waited = 0
                while waited < wait:
                    if getattr(self, "_sched_any_stop", False): return
                    time.sleep(0.5); waited += 0.5
            if getattr(self, "_sched_any_stop", False): return
            elapsed = (datetime.datetime.now() - base).total_seconds()
            self._run_past(slot_idx=si)

        self.status.set("✔ 과거섬 전체 슬롯 완료!")

    def _run_mail_scheduled(self):
        import random, datetime
        self._minimize_claude()          # 클로드(항상위)가 클릭 가리지 않게 먼저 내림
        self.after(0, self.iconify)
        slots = self.cfg.get("mail_slots", [])
        active = [(i, s) for i, s in enumerate(slots)
                  if any(c for c in s.get("coords", []))]
        if not active:
            return

        # 각 클라이언트마다 22:30~23:30 사이 무작위 시각 배정
        base = datetime.datetime.now().replace(hour=22, minute=30, second=0, microsecond=0)
        window = 60 * 60  # 1시간(3600초)
        schedule = sorted([(random.uniform(0, window), i, s) for i, s in active])

        self.status.set(f"🕘 22:30~23:30 우편함 {len(active)}개 랜덤 실행 대기...")
        elapsed = (datetime.datetime.now() - base).total_seconds()

        for delay, si, slot in schedule:
            wait = delay - elapsed
            if wait > 0:
                mins = int(wait // 60); secs = int(wait % 60)
                name = slot.get("name", f"#{si+1}")
                self.status.set(f"🕘 [{name}] {mins}분 {secs}초 후 실행...")
                waited = 0
                while waited < wait:
                    if getattr(self, "_sched_any_stop", False): return
                    time.sleep(0.5); waited += 0.5
            if getattr(self, "_sched_any_stop", False): return
            elapsed = (datetime.datetime.now() - base).total_seconds()
            name = slot.get("name", f"#{si+1}")
            self._wait_system_idle(15)
            if getattr(self, "_sched_any_stop", False): return
            self.status.set(f"🕘 [{name}] 우편함 클릭 중...")
            self._run_mail(slot_idx=si)

        self.status.set("✔ 전체 우편함 클릭 완료!")

    def _start_mail(self):
        if not self._try_busy_or_queue("우편함", self._start_mail): return
        self._mail_stop = False
        self._sched_any_stop = False
        if hasattr(self, "btn_mail_run"): self.btn_mail_run.config(state="disabled")
        if hasattr(self, "btn_mail_stop"): self.btn_mail_stop.config(state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("우편함", self._run_mail_standalone), daemon=True).start())

    def _stop_mail(self):
        self._mail_stop = True
        self.status.set("우편함 멈추는 중...")

    def _run_mail_standalone(self):
        self._run_mail()
        if hasattr(self, "btn_mail_run"): self.after(0, lambda: self.btn_mail_run.config(state="normal"))
        if hasattr(self, "btn_mail_stop"): self.after(0, lambda: self.btn_mail_stop.config(state="disabled"))
        self._mail_stop = False
        self.after(0, self._restore_all)

    def _run_mail(self, slot_idx=None):
        """slot_idx 지정 시 해당 슬롯만, None이면 전체 16개 랜덤 순서 실행"""
        try:
            slots = self.cfg.get("mail_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(c for c in s.get("coords", []) if c)]
                random.shuffle(targets)
            for si, slot in targets:
                if self._mail_stop: break
                name = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [])
                valid = [c for c in coords if c and len(c) >= 2]
                if not valid: continue
                for k, coord in enumerate(valid):
                    if self._mail_stop: break
                    if not self._wait_mouse_idle("_mail_stop"): break
                    self.status.set(f"🕘 [{name}] 우편함 클릭 {k+1}/{len(valid)}...")
                    pyautogui.click(*coord)
                    if k < len(valid) - 1:
                        time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if not self._mail_stop:
                    slot_wait = random.uniform(2.0, 4.0)
                    self.status.set(f"🕘 다음 슬롯 대기 {slot_wait:.1f}초...")
                    time.sleep(slot_wait)
            self.status.set("✔ 우편함 클릭 완료!" if not self._mail_stop else "우편함 멈춤")
        except Exception as e:
            self.status.set(f"오류: {e}")

    def _reg_mail_click(self, slot_idx, click_idx):
        self._reg_mail_slot_idx  = slot_idx
        self._reg_mail_click_idx = click_idx
        self.status.set(f"3초 후 우편함 #{slot_idx+1} 클릭{click_idx+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="mail")])

    def on_mail_coord(self, x, y):
        si = self._reg_mail_slot_idx
        ci = self._reg_mail_click_idx
        self.cfg["mail_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 우편함 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_mail_name(self, idx):
        name = self._mail_name_vars[idx].get().strip() or "미등록"
        self.cfg["mail_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_mail(self, idx):
        threading.Thread(target=self._run_mail, args=(idx,), daemon=True).start()

    def _del_mail(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"우편함 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["mail_slots"][idx] = {"name": "미등록", "coords": [None]*MAIL_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_mail(self, idx):
        coords = self.cfg["mail_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["mail_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_mail_slot_idx  = idx
            self._reg_mail_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="mail"))

        def _save(dot_idx, nx, ny):
            self.cfg["mail_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 우편함 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"우편함 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=8)

    def _group_copy_mail_slot(self, idx):
        import copy
        src = self.cfg["mail_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["mail_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["mail_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if dots:
            self.withdraw()
            self.after(300, lambda: _MailGroupMoveOverlay(self, idx, dots))

    def _group_copy_mail(self):
        import copy
        src = self.cfg["mail_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, MAIL_SLOTS):
            self.cfg["mail_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{MAIL_SLOTS:02d} 전체 복사 완료")

    # ── 주말던전 ──────────────────────────────────────────────────────
    def _start_dungeon(self):
        if not self._try_busy_or_queue("주말던전", self._start_dungeon): return
        self._dungeon_stop = False
        if hasattr(self, "btn_dungeon_run"): self.btn_dungeon_run.config(state="disabled")
        if hasattr(self, "btn_dungeon_stop"): self.btn_dungeon_stop.config(state="normal")
        self._minimize_claude()
        self.iconify()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("주말던전", self._run_dungeon), daemon=True).start())

    def _run_dungeon(self, slot_idx=None):
        try:
            slots = self.cfg.get("dungeon_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
            for si, slot in targets:
                if self._dungeon_stop: break
                name = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [])
                if not coords[0]: continue
                if not self._wait_mouse_idle("_dungeon_stop"): return
                # 메뉴 위로 마우스 이동 후 대기
                self.status.set(f"🏰 [{name}] 메뉴 hover...")
                pyautogui.moveTo(*coords[0])
                time.sleep(DUNGEON_HOVER)
                pyautogui.click(*coords[0])
                time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                # 확장 후 클릭1, 클릭2
                for j in range(1, DUNGEON_CLICKS):
                    if self._dungeon_stop: break
                    if coords[j]:
                        self.status.set(f"🏰 [{name}] 클릭{j}...")
                        pyautogui.click(*coords[j])
                        if j < DUNGEON_CLICKS - 1:
                            time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.status.set("✔ 던전 실행 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            if hasattr(self, "btn_dungeon_run"): self.btn_dungeon_run.config(state="normal")
            if hasattr(self, "btn_dungeon_stop"): self.btn_dungeon_stop.config(state="disabled")

    def _reg_dungeon_click(self, slot_idx, click_idx):
        self._reg_dungeon_slot_idx  = slot_idx
        self._reg_dungeon_click_idx = click_idx
        label = ["메뉴", "클릭1", "클릭2"][click_idx]
        self.status.set(f"3초 후 던전 #{slot_idx+1} [{label}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="dungeon")])

    def on_dungeon_coord(self, x, y):
        si = self._reg_dungeon_slot_idx
        ci = self._reg_dungeon_click_idx
        self.cfg["dungeon_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        label = ["메뉴", "클릭1", "클릭2"][ci]
        self.status.set(f"✔ 던전 #{si+1} [{label}] 등록: ({x},{y})")
        self.deiconify()

    def _save_dungeon_name(self, idx):
        name = self._dungeon_name_vars[idx].get().strip() or "미등록"
        self.cfg["dungeon_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_dungeon(self, idx):
        threading.Thread(target=self._run_dungeon, args=(idx,), daemon=True).start()

    def _del_dungeon(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"던전 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["dungeon_slots"][idx] = {"name": "미등록", "coords": [None]*DUNGEON_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_dungeon(self, idx):
        coords = self.cfg["dungeon_slots"][idx].get("coords", [])
        LABELS_D = ["메뉴", "클릭1", "클릭2"]
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"던전 #{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["dungeon_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_dungeon_slot_idx  = idx
            self._reg_dungeon_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="dungeon"))

        def _save(dot_idx, nx, ny):
            self.cfg["dungeon_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 던전 #{idx+1:02d} {LABELS_D[dot_idx]} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"던전 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=8)

    def _group_copy_dungeon_slot(self, idx):
        import copy
        src = self.cfg["dungeon_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"던전 #{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["dungeon_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["dungeon_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            return
        self.withdraw()
        self.after(300, lambda: _DungeonGroupMoveOverlay(self, idx, dots))

    # ── 과거의말하는섬 ────────────────────────────────────────────────
    def _start_past(self):
        if not self._try_busy_or_queue("과거섬", self._start_past): return
        self._past_stop = False
        self._sched_any_stop = False
        if hasattr(self, "btn_past_run"): self.btn_past_run.config(state="disabled", bg="#f39c12", text="⏳ 실행중...")
        if hasattr(self, "btn_past_stop"): self.btn_past_stop.config(state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("과거섬", self._run_past), daemon=True).start())

    def _run_past(self, slot_idx=None):
        try:
            self.status.set("2초 후 과거의말하는섬 실행...")
            self.after(0, self.iconify)
            time.sleep(2)
            slots = self.cfg.get("past_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
            for si, slot in targets:
                if self._past_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*PAST_CLICKS)
                # 슬롯별 랜덤 딜레이
                slot_delay = random.uniform(3.0, 15.0)
                self.status.set(f"🏝 [{name}] {slot_delay:.0f}초 후 실행...")
                elapsed = 0
                while elapsed < slot_delay:
                    if self._past_stop: break
                    time.sleep(0.5); elapsed += 0.5
                if self._past_stop: break
                # 0: 클릭1(신규) → 1: 마우스이동(hover) → 2: 클릭
                if coords[0]:
                    self.status.set(f"🏝 [{name}] 클릭1...")
                    pyautogui.click(*coords[0])
                    time.sleep(random.uniform(3.0, 6.0) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._past_stop: break
                if coords[1]:
                    self.status.set(f"🏝 [{name}] 마우스 이동...")
                    pyautogui.moveTo(*coords[1])
                    time.sleep(random.uniform(3.0, 5.0) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._past_stop: break
                if len(coords) > 2 and coords[2]:
                    self.status.set(f"🏝 [{name}] 클릭2...")
                    pyautogui.click(*coords[2])
                if self._past_stop: break
                # 슬롯 간 대기 (가끔 긴 휴식)
                pause = random.uniform(4.0, 8.0)
                if random.random() < 0.25:
                    pause += random.uniform(3.0, 7.0)
                time.sleep(pause)
            self.status.set("✔ 과거의말하는섬 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_all)
            if hasattr(self, "btn_past_run"): self.btn_past_run.config(state="normal", bg="#c0392b", text="▶  실행")
            if hasattr(self, "btn_past_stop"): self.btn_past_stop.config(state="disabled")

    def _reg_past_click(self, slot_idx, click_idx):
        self._reg_past_slot_idx  = slot_idx
        self._reg_past_click_idx = click_idx
        # 클릭한 슬롯을 맨 위로 스크롤
        btn = self._past_click_btns[slot_idx][click_idx]
        self._past_canvas.update_idletasks()
        total = self._past_canvas.bbox("all")
        if total:
            row_y = btn.winfo_y() + btn.master.winfo_y()
            frac = row_y / total[3]
            self._past_canvas.yview_moveto(frac)
        if click_idx == 1:
            # 이동 좌표는 카운트다운 후 현재 마우스 위치 자동 캡처
            self._past_hover_countdown(slot_idx, 3)
        else:
            self.status.set(f"3초 후 과거의말하는섬 #{slot_idx+1} [클릭{click_idx+1}] 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                       CoordOverlay(self, mode="past")])

    def _past_hover_countdown(self, slot_idx, remaining):
        if remaining > 0:
            self.status.set(f"⏱ {remaining}초 안에 마우스를 이동해두세요 — 자동 저장됩니다")
            self.after(1000, lambda: self._past_hover_countdown(slot_idx, remaining - 1))
        else:
            x, y = pyautogui.position()
            self.on_past_coord(x, y)

    def on_past_coord(self, x, y):
        si = self._reg_past_slot_idx
        ci = self._reg_past_click_idx
        self.cfg["past_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 과거의말하는섬 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_past_name(self, idx):
        name = self._past_name_vars[idx].get().strip() or "미등록"
        self.cfg["past_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_past(self, idx):
        threading.Thread(target=self._run_past, args=(idx,), daemon=True).start()

    def _del_past(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"과거의섬 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["past_slots"][idx] = {"name": "미등록", "coords": [None]*PAST_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_past(self, idx):
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["past_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_past_slot_idx  = idx
            self._reg_past_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="past"))

        def _save(dot_idx, nx, ny):
            self.cfg["past_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 과거섬 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"과거섬 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _group_copy_past_slot(self, idx):
        import copy
        src = self.cfg["past_slots"][idx-1].get("coords", [])
        if not any(src[1:]):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표(2,3번)가 없습니다")
            return
        dst = self.cfg["past_slots"][idx]["coords"]
        for j in (1, 2):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1, n) for n, c in enumerate(coords)
                if n > 0 and c and len(c) >= 2]
        if dots:
            self.withdraw()
            def _open_past(i=idx, d=dots):
                try:
                    _PastGroupMoveOverlay(self, i, d)
                except Exception as e:
                    self.deiconify()
                    self.status.set(f"오류: {e}")
            self.after(300, _open_past)

    def _group_copy_past_1to4(self):
        import copy
        src = self.cfg["past_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, 4):
            self.cfg["past_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        # #02~#04 순서대로 그룹 이동 오버레이 열기
        self._past_chain_move(1, end=4)

    def _past_chain_move(self, idx, end):
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            if idx + 1 < end:
                self.after(300, lambda: self._past_chain_move(idx+1, end))
            return
        self.withdraw()
        self.after(300, lambda: _PastChainMoveOverlay(self, idx, dots, idx+1, end))

    def _group_copy_past(self):
        import copy
        src = self.cfg["past_slots"][0].get("coords", [])
        if not any(src[1:]):
            self.status.set("#01 슬롯에 복사할 좌표(2,3번)가 없습니다")
            return
        for i in range(1, PAST_SLOTS):
            dst = self.cfg["past_slots"][i]["coords"]
            for j in (1, 2):
                if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{PAST_SLOTS:02d} 전체 복사 완료")

    def _start_sched(self):
        if not self._try_busy_or_queue("스케줄", self._start_sched): return
        self._sched_stop = False
        self._sched_any_stop = False
        if hasattr(self, "btn_sched_run"):
            self.btn_sched_run.config(state="disabled", bg="#f39c12", text="⏳ 실행중...")
        if hasattr(self, "btn_sched_stop"):
            self.btn_sched_stop.config(state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("스케줄", self._run_sched), daemon=True).start())

    def _run_sched(self, slot_idx=None):
        try:
            self._sync_sched_click1()   # 실행 직전 과거섬 클릭1 반영(항상 최신값으로 실행)
            self.status.set("2초 후 매일매일 스케줄 실행...")
            self.after(0, self.iconify)
            time.sleep(2)
            slots = self.cfg.get("sched_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
            for si, slot in targets:
                if self._sched_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*SCHED_CLICKS)
                if not self._wait_mouse_idle("_sched_stop"): return
                if coords[0]:
                    self.status.set(f"📅 [{name}] 클릭1...")
                    pyautogui.click(*coords[0])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._sched_stop: break
                if coords[1]:
                    self.status.set(f"📅 [{name}] 마우스 이동...")
                    pyautogui.moveTo(*coords[1])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._sched_stop: break
                if len(coords) > 2 and coords[2]:
                    self.status.set(f"📅 [{name}] 클릭2...")
                    pyautogui.click(*coords[2])
                if self._sched_stop: break
                time.sleep(4)
            self.status.set("✔ 매일매일 스케줄 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self.deiconify)
            self.after(0, self._restore_all)
            if hasattr(self, "btn_sched_run"): self.btn_sched_run.config(state="normal", bg="#16a085", text="▶  실행")
            if hasattr(self, "btn_sched_stop"): self.btn_sched_stop.config(state="disabled")

    def _reg_sched_click(self, slot_idx, click_idx):
        self._reg_sched_slot_idx  = slot_idx
        self._reg_sched_click_idx = click_idx
        btn = self._sched_click_btns[slot_idx][click_idx]
        self._sched_canvas.update_idletasks()
        total = self._sched_canvas.bbox("all")
        if total:
            row_y = btn.winfo_y() + btn.master.winfo_y()
            frac = row_y / total[3]
            self._sched_canvas.yview_moveto(frac)
        if click_idx == 1:
            # 이동 좌표는 카운트다운 후 현재 마우스 위치 자동 캡처
            self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
            self._sched_hover_countdown(slot_idx, 3)
        else:
            self.status.set(f"3초 후 스케줄 #{slot_idx+1} [클릭{click_idx+1}] 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                       CoordOverlay(self, mode="sched")])

    def _sched_hover_countdown(self, slot_idx, remaining):
        if remaining > 0:
            self.status.set(f"⏱ {remaining}초 안에 마우스를 이동해두세요 — 자동 저장됩니다")
            self.after(1000, lambda: self._sched_hover_countdown(slot_idx, remaining - 1))
        else:
            x, y = pyautogui.position()
            self.on_sched_coord(x, y)

    def on_sched_coord(self, x, y):
        si = self._reg_sched_slot_idx
        ci = self._reg_sched_click_idx
        self.cfg["sched_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 스케줄 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_sched_name(self, idx):
        name = self._sched_name_vars[idx].get().strip() or "미등록"
        self.cfg["sched_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_sched(self, idx):
        threading.Thread(target=self._run_sched, args=(idx,), daemon=True).start()

    def _del_sched(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"스케줄 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["sched_slots"][idx] = {"name": "미등록", "coords": [None]*SCHED_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_sched(self, idx):
        coords = self.cfg["sched_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["sched_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_sched_slot_idx  = idx
            self._reg_sched_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="sched"))

        def _save(dot_idx, nx, ny):
            self.cfg["sched_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 스케줄 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"스케줄 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _group_copy_sched_slot(self, idx):
        import copy
        src = self.cfg["sched_slots"][idx-1].get("coords", [])
        if not any(src[1:]):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표(2,3번)가 없습니다")
            return
        dst = self.cfg["sched_slots"][idx]["coords"]
        for j in (1, 2):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["sched_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1, n) for n, c in enumerate(coords)
                if n > 0 and c and len(c) >= 2]
        if dots:
            self.withdraw()
            def _open_sched(i=idx, d=dots):
                try:
                    _SchedGroupMoveOverlay(self, i, d)
                except Exception as e:
                    self.deiconify()
                    self.status.set(f"오류: {e}")
            self.after(300, _open_sched)

    def _group_copy_sched(self):
        import copy
        src = self.cfg["sched_slots"][0].get("coords", [])
        if not any(src[1:]):
            self.status.set("#01 슬롯에 복사할 좌표(2,3번)가 없습니다")
            return
        for i in range(1, SCHED_SLOTS):
            dst = self.cfg["sched_slots"][i]["coords"]
            for j in (1, 2):
                if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{SCHED_SLOTS:02d} 전체 복사 완료")

    def _reg_sched_click1_all(self):
        ref = self.cfg["sched_slots"][0]["coords"][0]
        if not ref:
            self.status.set("슬롯#01 클릭1 좌표가 없습니다. 먼저 등록해주세요.")
            return
        self._sched_click1_ref = list(ref)
        self.status.set(f"기준: 슬롯#01 클릭1 ({ref[0]},{ref[1]}) → 3초 후 새 위치에 마우스를 올려두세요")
        self.after(3000, self._capture_sched_click1_all)

    def _capture_sched_click1_all(self):
        nx, ny = pyautogui.position()
        ox, oy = self._sched_click1_ref
        dx, dy = nx - ox, ny - oy
        for i in range(SCHED_SLOTS):
            c = self.cfg["sched_slots"][i]["coords"][0]
            if c:
                self.cfg["sched_slots"][i]["coords"][0] = [c[0] + dx, c[1] + dy]
        save_cfg(self.cfg)
        self._refresh_ui()
        self.status.set(f"✔ 클릭1 전체 이동 완료 (dx={dx:+d}, dy={dy:+d})")

    def _take_layout_screenshot(self, count):
        import time
        time.sleep(0.4)
        try:
            from PIL import ImageGrab, ImageDraw, ImageFont
            shot = ImageGrab.grab(all_screens=True)
            draw = ImageDraw.Draw(shot)
            positions = self.cfg.get("window_positions", [])
            for idx, p in enumerate(positions):
                x, y, w, h = p["x"], p["y"], p["w"], p["h"]
                # 창 테두리
                draw.rectangle([x, y, x+w, y+h], outline=(255, 80, 80), width=3)
                # 번호 배경 박스
                pad = 6
                num_text = f"#{idx+1:02d}"
                box_w, box_h = 60, 36
                draw.rectangle([x+4, y+4, x+4+box_w, y+4+box_h], fill=(255, 80, 80))
                draw.text((x+8, y+8), num_text, fill=(255, 255, 255))
            path = os.path.join(BASE, "lineagem_logs", "window_layout.png")
            shot.save(path)
        except Exception:
            pass
        self.deiconify()
        self.lift()
        self.status.set(f"✔ 창 배치 {count}개 저장 완료")
        # 캡처 후 잠깐 보여주다 5초 후 자동 숨김
        self._show_layout_preview()
        self.after(5000, self._hide_layout_preview)

    def _section_wins(self):
        attrs = ["_settings_win","_hunt_win","_mail_win","_past_win2",
                 "_sched_win","_dungeon_win","_daya_win","_pass_win","_seq_win",
                 "_dc_win","_accounts_win","_doll_win"]
        return [getattr(self, a) for a in attrs
                if getattr(self, a, None) and getattr(self, a).winfo_exists()]

    def _minimize_all(self):
        for w in self._section_wins():
            w.iconify()
        self.iconify()
        self._minimize_claude()

    def _restore_all(self):
        self.deiconify()
        for w in self._section_wins():
            w.deiconify()

    def _show_layout_preview(self):
        # 메인+서브창 전부 최소화
        for w in self._section_wins():
            w.iconify()
        self._load_layout_preview()
        self._layout_preview_visible = True
        self.iconify()

    def _hide_layout_preview(self):
        self._layout_preview_frame.pack_forget()
        self._layout_preview_visible = False
        self._btn_layout_toggle.config(text="🖼 배치보기")
        self.deiconify()
        for w in self._section_wins():
            w.deiconify()

    def _toggle_layout_preview(self):
        if self._layout_preview_visible:
            self._hide_layout_preview()
        else:
            self._show_layout_preview()

    def _load_layout_preview(self):
        path = os.path.join(BASE, "lineagem_logs", "window_layout.png")
        frame = self._layout_preview_frame
        for w in frame.winfo_children():
            w.destroy()
        if not os.path.exists(path):
            tk.Label(frame, text="(배치 캡처 없음)", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            # 가로 폭을 프레임에 맞게 축소
            max_w = 900
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(frame, image=photo, cursor="hand2")
            lbl.image = photo
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e: __import__("subprocess").Popen(["explorer", path]))
        except Exception:
            tk.Label(frame, text="(미리보기 오류)", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")

    # ── 창 배치 ───────────────────────────────────────────────────────
    def _get_purple_hwnds(self):
        """Purple/리니지 창의 (hwnd, left, top, width, height) 목록 반환"""
        import ctypes
        result = []
        def cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if ("Purple" in title or "리니지" in title) and ctypes.windll.user32.IsWindowVisible(hwnd):
                r = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left
                h = r.bottom - r.top
                if w > 100 and h > 100:
                    result.append((hwnd, r.left, r.top, w, h))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
        return result

    def _capture_window_layout(self):
        wins = self._get_purple_hwnds()
        if not wins:
            messagebox.showwarning("창 없음", "퍼플/리니지 창을 찾을 수 없습니다."); return
        # 위치(위→아래, 왼→오른) 순으로 정렬해서 패턴만 저장
        wins_sorted = sorted(wins, key=lambda e: (e[2], e[1]))  # y, x 순
        positions = [{"x": x, "y": y, "w": w, "h": h}
                     for _, x, y, w, h in wins_sorted]
        self.cfg["window_positions"] = positions
        save_cfg(self.cfg)
        # 런처 최소화 후 스크린샷 → 복구
        self.iconify()
        self.after(600, lambda: self._take_layout_screenshot(len(positions)))

    def _clear_window_layout(self):
        self.cfg["window_positions"] = []
        save_cfg(self.cfg)
        self.status.set("창 배치 초기화 완료")

    def _apply_window_layout(self):
        positions = self.cfg.get("window_positions", [])
        if not positions:
            self.status.set("저장된 배치가 없습니다. 먼저 '현재 배치 캡처'를 눌러주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("퍼플/리니지 창을 찾을 수 없습니다."); return
        # 현재 창도 같은 기준(y, x)으로 정렬
        wins_sorted = sorted(wins, key=lambda e: (e[2], e[1]))
        SWP_NOZORDER = 0x0004
        applied = 0
        for i, (hwnd, *_) in enumerate(wins_sorted):
            if i >= len(positions): break
            p = positions[i]
            try:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, p["x"], p["y"], p["w"], p["h"], SWP_NOZORDER)
                applied += 1
            except Exception:
                pass
        self.status.set(f"✔ 창 배치 복구 완료 ({applied}개)")

    def _toggle_detail(self, detail, sv, row_frame, padx=14):
        if detail.winfo_ismapped():
            detail.pack_forget()
            sv.set(sv.get().replace("▴", "▾"))
        else:
            detail.pack(fill="x", padx=padx, pady=(0,4), after=row_frame)
            sv.set(sv.get().replace("▾", "▴"))

    def _toggle_hunt_detail(self, slot_idx):
        self._toggle_detail(self._hunt_detail_frames[slot_idx],
                            self._hunt_coord_sv[slot_idx],
                            self._hunt_row_frames[slot_idx])

    def _toggle_mail_detail(self, slot_idx):
        self._toggle_detail(self._mail_detail_frames[slot_idx],
                            self._mail_coord_sv[slot_idx],
                            self._mail_row_frames[slot_idx])

    def _toggle_dungeon_detail(self, slot_idx):
        self._toggle_detail(self._dungeon_detail_frames[slot_idx],
                            self._dungeon_coord_sv[slot_idx],
                            self._dungeon_row_frames[slot_idx])

    def _toggle_past_detail(self, slot_idx):
        self._toggle_detail(self._past_detail_frames[slot_idx],
                            self._past_coord_sv[slot_idx],
                            self._past_row_frames[slot_idx])

    def _toggle_pass_detail(self, slot_idx):
        self._toggle_detail(self._pass_detail_frames[slot_idx],
                            self._pass_coord_sv[slot_idx],
                            self._pass_row_frames[slot_idx])

    def _minimize_claude(self):
        """Claude 창 최소화"""
        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return True
            t = win32gui.GetWindowText(hwnd)
            if "claude" in t.lower():
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        win32gui.EnumWindows(_cb, None)

    def _assign_window(self, slot_idx):
        """카운트다운 후 클릭한 창을 슬롯에 지정"""
        def _countdown(n):
            if n > 0:
                self.status.set(f"#{slot_idx+1:02d} 창 지정 — {n}초 후 지정할 창을 클릭하세요!")
                self.after(1000, lambda: _countdown(n - 1))
            else:
                self.status.set(f"#{slot_idx+1:02d} 창 지정 — 지금 지정할 창을 클릭하세요! (클릭 대기 중...)")
                self._minimize_claude()
                self.withdraw()
                self.after(100, _wait_click)

        def _wait_click():
            _AssignWindowOverlay(self, slot_idx, self._on_assign_done)

        _countdown(1)

    def _on_assign_done(self, slot_idx, title):
        """지정 완료 후 버튼 초록으로 변경"""
        if slot_idx < len(self._hunt_assign_btns):
            self._hunt_assign_btns[slot_idx].config(text="✔지정", bg="#27ae60")
        self.status.set(f"✔ #{slot_idx+1:02d} 지정 완료 — [{title[:30]}]")

    def _preview_assigned_window(self, slot_idx):
        """지정된 창을 잠깐 맨 앞으로 띄워서 어떤 창인지 확인"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1:02d} — 지정된 창이 없습니다."); return
        wins = self._get_purple_hwnds()
        if not wins: return
        tx, ty = aw["cx"], aw["cy"]
        best = min(wins, key=lambda e: ((e[1]+e[3]//2-tx)**2 + (e[2]+e[4]//2-ty)**2))
        hwnd = best[0]
        HWND_TOP = 0
        SWP_NOSIZE = 0x0001; SWP_NOMOVE = 0x0002
        def _flash():
            for _ in range(3):
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                                                   SWP_NOSIZE | SWP_NOMOVE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.4)
        threading.Thread(target=_flash, daemon=True).start()
        title = aw.get("title", "")
        self.status.set(f"#{slot_idx+1:02d} 지정 창: [{title[:30]}]  {aw['w']}x{aw['h']}  @{aw['x']},{aw['y']}")

    _FIXED_W = 491
    _FIXED_H = 276

    def _find_hwnd_for_slot(self, aw, wins):
        """1) HWND  2) 창 제목 번호  3) 가장 가까운 위치 순으로 찾기"""
        # 1) HWND
        saved_hwnd = aw.get("hwnd")
        if saved_hwnd and win32gui.IsWindow(saved_hwnd):
            for e in wins:
                if e[0] == saved_hwnd:
                    return saved_hwnd
        # 2) 창 제목 (지정 시 번호 붙여놓은 경우)
        title = aw.get("title", "")
        if title:
            for e in wins:
                if win32gui.GetWindowText(e[0]) == title:
                    return e[0]
        # 3) 저장된 x,y 기준 가장 가까운 창
        sx, sy = aw.get("x"), aw.get("y")
        if sx is not None and sy is not None:
            best = min(wins, key=lambda e: (e[1]-sx)**2+(e[2]-sy)**2)
            return best[0]
        return None

    def _reg_name_area(self):
        """창 최대화 후 이름 영역 두 점 드래그로 등록"""
        self.status.set("3초 후 캐릭터 이름 영역의 좌상단을 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), self.after(200, self._open_name_area_overlay)])

    def _open_name_area_overlay(self):
        _NameAreaOverlay(self)

    def _ocr_all_names(self):
        area = self.cfg.get("name_ocr_area")
        if not area:
            self.status.set("먼저 📷 이름 영역등록 버튼으로 영역을 등록해주세요."); return
        self.iconify()
        threading.Thread(target=self._do_ocr_all_names, daemon=True).start()

    def _do_ocr_all_names(self):
        try:
            import easyocr
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: self.status.set(f"easyocr 오류: {e}")); return

        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: self.status.set("리니지M 창을 찾을 수 없습니다.")); return

        area = self.cfg.get("name_ocr_area")
        ox, oy, aw, ah = area["ox"], area["oy"], area["w"], area["h"]
        slots = self.cfg.get("hunt_slots", [])
        updated = 0

        # 열린 창 각각을 OCR 스캔 후 가장 가까운 슬롯에 이름 업데이트
        for hwnd, wx, wy in wins:
            self.after(0, lambda h=hwnd: self.status.set(f"OCR 인식 중..."))
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.6)
                import ctypes
                pt = ctypes.wintypes.POINT(0, 0)
                ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                x, y = pt.x + ox, pt.y + oy
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x, y, x+aw, y+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                name = " ".join(results).strip()
                self.after(0, lambda n=name: self.status.set(f"OCR 결과: '{n}'"))
                time.sleep(1.0)
                if not name: continue

                # 가장 가까운 슬롯 찾기 (assigned_window 위치 기준, 없으면 순서대로)
                best_si = None
                best_dist = float('inf')
                for si, slot in enumerate(slots):
                    aw_data = slot.get("assigned_window")
                    if aw_data:
                        sx, sy = aw_data.get("x", 0), aw_data.get("y", 0)
                        dist = (wx-sx)**2 + (wy-sy)**2
                        if dist < best_dist:
                            best_dist = dist
                            best_si = si
                    elif best_si is None:
                        best_si = si

                if best_si is not None:
                    self.cfg["hunt_slots"][best_si]["name"] = name
                    if best_si < len(self._hunt_name_vars):
                        self.after(0, lambda n=name, i=best_si: self._hunt_name_vars[i].set(n))
                    updated += 1
            except Exception as e:
                self.after(0, lambda e=e: self.status.set(f"OCR 오류: {e}"))

        save_cfg(self.cfg)
        self.after(0, lambda: [self.deiconify(), self.status.set(f"✔ {updated}개 슬롯 이름 자동 업데이트 완료")])

    def _renumber_windows(self):
        """지정된 슬롯의 창 제목을 번호로 다시 붙이기"""
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        count = 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw: continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            new_title = f"리니지M #{i+1:02d}"
            try:
                win32gui.SetWindowText(hwnd, new_title)
                aw["title"] = new_title
                aw["hwnd"] = hwnd
                count += 1
            except: pass
        save_cfg(self.cfg)
        self.status.set(f"✔ {count}개 창 번호 재지정 완료")

    def _save_window_pos(self, slot_idx):
        """현재 지정된 창의 위치를 저장 (크기는 491×276 고정)"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1} 슬롯 없음"); return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1} — 먼저 '지정' 버튼으로 창을 지정해주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        hwnd = self._find_hwnd_for_slot(aw, wins)
        if not hwnd:
            self.status.set(f"#{slot_idx+1} — 창을 찾을 수 없습니다. '지정' 버튼을 다시 눌러주세요."); return
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]
            w, h = self._FIXED_W, self._FIXED_H
            aw["x"], aw["y"], aw["w"], aw["h"] = x, y, w, h
            aw["cx"], aw["cy"] = x + w // 2, y + h // 2
            save_cfg(self.cfg)
            self.status.set(f"✔ #{slot_idx+1:02d} 위치 저장: {w}×{h} @{x},{y}")
        except Exception as e:
            self.status.set(f"#{slot_idx+1} 저장 오류: {e}")

    def _save_all_window_pos(self):
        """지정된 모든 슬롯의 현재 창 위치를 저장 (크기 491×276 고정)"""
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        count = 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw: continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            try:
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                w, h = self._FIXED_W, self._FIXED_H
                aw["x"], aw["y"], aw["w"], aw["h"] = x, y, w, h
                aw["cx"], aw["cy"] = x + w // 2, y + h // 2
                count += 1
            except: pass
        save_cfg(self.cfg)
        self.status.set(f"✔ {count}개 창 위치 저장 완료 (491×276 고정)")

    def _restore_all_windows(self):
        self._restore_by_position()

    def _restore_by_position(self):
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        SWP_NOZORDER = 0x0004
        count = 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw or not all(k in aw for k in ("x","y","w","h")): continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            try:
                ctypes.windll.user32.SetWindowPos(hwnd, 0, aw["x"], aw["y"], aw["w"], aw["h"], SWP_NOZORDER)
                count += 1
            except: pass
        self.status.set(f"✔ {count}개 창 위치 복원 완료")

    def _restore_by_ocr(self):
        """OCR로 각 창의 캐릭터명을 읽어 슬롯 이름과 매칭 후 복원"""
        try:
            import easyocr
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: [self.deiconify(), self.status.set(f"easyocr 오류: {e}")]); return

        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: [self.deiconify(), self.status.set("리니지M 창을 찾을 수 없습니다.")]); return

        area = self.cfg.get("name_ocr_area")
        ox, oy, aw, ah = area["ox"], area["oy"], area["w"], area["h"]
        slots = self.cfg.get("hunt_slots", [])
        SWP_NOZORDER = 0x0004
        count = 0

        for hwnd, wx, wy in wins:
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.6)
                pt = ctypes.wintypes.POINT(0, 0)
                ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                x, y = pt.x + ox, pt.y + oy
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x, y, x+aw, y+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                ocr_name = " ".join(results).strip()
                self.after(0, lambda n=ocr_name: self.status.set(f"OCR: '{n}' 매칭 중..."))

                # 슬롯 이름과 매칭
                matched_si = None
                for si, slot in enumerate(slots):
                    slot_name = slot.get("name", "").strip()
                    if slot_name and slot_name != "미등록" and slot_name in ocr_name:
                        matched_si = si
                        break

                if matched_si is not None:
                    aw_data = slots[matched_si].get("assigned_window")
                    if aw_data and all(k in aw_data for k in ("x","y","w","h")):
                        ctypes.windll.user32.SetWindowPos(hwnd, 0,
                            aw_data["x"], aw_data["y"], aw_data["w"], aw_data["h"], SWP_NOZORDER)
                        self.after(0, lambda n=ocr_name, s=matched_si: self.status.set(f"✔ '{n}' → #{s+1:02d} 복원"))
                        count += 1
                        time.sleep(0.3)
            except Exception as e:
                self.after(0, lambda e=e: self.status.set(f"오류: {e}"))

        save_cfg(self.cfg)
        self.after(0, lambda: [self.deiconify(), self.status.set(f"✔ {count}개 창 이름 매칭 복원 완료")])

    def _restore_single_by_ocr(self, slot_idx):
        """고정 영역 OCR → 현재 앞에 있는 창을 해당 슬롯 위치로 복원"""
        area = self.cfg.get("name_ocr_area")
        if not area:
            self.status.set("먼저 📷 이름 영역등록을 해주세요."); return
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1:02d} 슬롯 없음"); return
        aw_data = slots[slot_idx].get("assigned_window")
        if not aw_data or not all(k in aw_data for k in ("x","y","w","h")):
            self.status.set(f"#{slot_idx+1:02d} 저장된 위치가 없습니다. 📍 저장 먼저 해주세요."); return
        # 버튼 클릭 전 포그라운드 창 미리 기억
        prev_hwnd = win32gui.GetForegroundWindow()
        threading.Thread(target=self._do_ocr_snap, args=(slot_idx, area, aw_data, prev_hwnd), daemon=True).start()

    def _do_ocr_snap(self, slot_idx, area, aw_data, prev_hwnd):
        try:
            import easyocr
            from PIL import ImageGrab
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: self.status.set(f"easyocr 오류: {e}")); return

        slots = self.cfg.get("hunt_slots", [])
        slot_name = slots[slot_idx].get("name", "").strip()
        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: self.status.set("리니지M 창을 찾을 수 없습니다.")); return

        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        SWP_NOZORDER = 0x0004

        for hwnd, wx, wy in wins:
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                ocr_name = " ".join(results).strip()
                self.after(0, lambda n=ocr_name: self.status.set(f"OCR: '{n}' 확인 중..."))
                if slot_name and (slot_name in ocr_name or ocr_name in slot_name):
                    ctypes.windll.user32.SetWindowPos(hwnd, 0,
                        aw_data["x"], aw_data["y"], aw_data["w"], aw_data["h"], SWP_NOZORDER)
                    self.after(0, lambda: self.status.set(f"✔ '{slot_name}' → #{slot_idx+1:02d} 복원 완료"))
                    return
            except: pass

        self.after(0, lambda: self.status.set(f"'{slot_name}' 이름의 창을 찾지 못했습니다."))

    def _restore_single_window(self, slot_idx):
        """지정된 창을 저장된 위치/크기로 복구"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1} 슬롯 없음"); return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1} — 먼저 '지정' 버튼으로 창을 지정해주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        hwnd = self._find_hwnd_for_slot(aw, wins)
        if not hwnd:
            self.status.set(f"#{slot_idx+1} — 창을 찾을 수 없습니다. '지정' 버튼을 다시 눌러주세요."); return
        SWP_NOZORDER = 0x0004
        try:
            ctypes.windll.user32.SetWindowPos(hwnd, 0, aw["x"], aw["y"], aw["w"], aw["h"], SWP_NOZORDER)
            self.status.set(f"✔ #{slot_idx+1:02d} 창 복구 완료  ({aw['w']}x{aw['h']}  @{aw['x']},{aw['y']})")
        except Exception as e:
            self.status.set(f"#{slot_idx+1} 복구 오류: {e}")
        # 개별 재배치 후 메인런처가 뒤로 밀리지 않도록 항상 앞으로 유지
        self._keep_launcher_front()

    def _keep_launcher_front(self):
        """메인런처를 잠깐 topmost로 올려 앞으로 유지 (고정은 하지 않음)."""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    # ── 동시 실행 방지 (전역 잠금) ──────────────────────────────────
    def _is_busy(self, exclude=None):
        """개별 작업 / 다야 OCR / 섬·던전 실행기가 돌고 있으면 True. exclude 이름은 무시."""
        bt = getattr(self, "_busy_task", None)
        if bt and bt != exclude:
            return True
        if exclude != "다야OCR":
            proc = getattr(self, "_ocr_proc", None)
            if proc is not None and proc.poll() is None:
                return True
        ip = getattr(self, "_island_proc", None)
        if ip is not None and ip.poll() is None:
            return True
        return False

    def _busy_label(self):
        bt = getattr(self, "_busy_task", None)
        if bt:
            return bt
        proc = getattr(self, "_ocr_proc", None)
        if proc is not None and proc.poll() is None:
            return "다야OCR"
        return "다른 작업"

    def _try_busy(self, name):
        """작업 시작 시도 — 다른 작업이 실행 중이면 안내 후 False."""
        if self._is_busy(exclude=name):
            self.status.set(f"⚠ '{self._busy_label()}' 실행 중 — '{name}'은(는) 실행 안 함 (동시 실행 방지)")
            return False
        self._busy_task = name
        return True

    # ── 작업 대기열: 실행 중에 누른 실행/재측정은 쌓아뒀다가 순차 실행 ──
    def _enqueue(self, label, fn):
        """다른 작업 실행 중 → 대기열에 추가 (같은 라벨 중복 방지). 어느 스레드에서든 호출 가능."""
        if any(l == label for l, _ in self._task_queue):
            self.after(0, lambda: self.status.set(f"⏳ '{label}' 이미 대기열에 있음 (대기 {len(self._task_queue)}개)"))
            return
        self._task_queue.append((label, fn))
        n = len(self._task_queue)
        self.after(0, lambda: self.status.set(
            f"⏳ '{self._busy_label()}' 실행 중 — '{label}' 대기열 추가 (대기 {n}개)"))

    def _queue_tick(self):
        """1.5초마다 대기열 확인 — 한가해지면 다음 작업을 순서대로 실행."""
        try:
            if self._task_queue and not self._is_busy():
                label, fn = self._task_queue.pop(0)
                self.status.set(f"▶ 대기열 실행: {label} (남은 {len(self._task_queue)}개)")
                fn()
        except Exception:
            pass
        self.after(1500, self._queue_tick)

    def _try_busy_or_queue(self, name, retry_fn, label=None):
        """busy면 대기열에 넣고 False, 아니면 잠금 획득."""
        if self._is_busy(exclude=name):
            self._enqueue(label or name, retry_fn)
            return False
        self._busy_task = name
        return True

    def _clear_busy(self, name):
        if getattr(self, "_busy_task", None) == name:
            self._busy_task = None

    def _run_task(self, name, fn, *args):
        """작업 스레드 래퍼 — 끝나면 잠금 해제."""
        try:
            fn(*args)
        finally:
            self._clear_busy(name)

    def _stop(self):
        self._stop_flag      = True
        self._past_stop      = True
        self._sched_stop     = True
        self._hunt_stop      = True
        self._click_stop     = True
        self._mail_stop      = True
        self._sched_any_stop = True
        self._return_stop    = True
        self._busy_task      = None   # 잠금 해제
        self._task_queue.clear()      # 멈춤 시 대기열도 비움
        # 다야 OCR 프로세스 종료
        proc = getattr(self, "_ocr_proc", None)
        if proc and proc.poll() is None:
            try: proc.terminate()
            except: pass
            self._ocr_proc = None
        self.status.set("멈추는 중...")

    # ── 클릭 실행 ─────────────────────────────────────────────────────
    def _start_click(self):
        slots = [s for s in self.cfg.get("click_slots", []) if s[0] and s[1]]
        if not slots:
            messagebox.showwarning("등록 필요", "클릭 좌표를 먼저 등록해주세요."); return
        if not self._try_busy_or_queue("클릭실행", self._start_click): return
        self._click_stop = False
        self.btn_click_run.config(state="disabled")
        self.btn_click_stop.config(state="normal")
        self._minimize_claude()
        self.iconify()
        threading.Thread(target=self._run_task, args=("클릭실행", self._run_click_standalone), daemon=True).start()

    def _run_click_standalone(self):
        self._run_click()
        self.btn_click_run.config(state="normal")
        self.btn_click_stop.config(state="disabled")
        self._click_stop = False
        self.deiconify()

    def _run_click(self):
        try:
            active = [(i, s) for i, s in enumerate(self.cfg.get("click_slots", []))
                      if s[0] and s[1]]
            for done, (i, pair) in enumerate(active):
                if self._click_stop: self.status.set("클릭 멈춤"); return
                if not self._wait_mouse_idle("_click_stop"):
                    self.status.set("클릭 멈춤"); return
                grp = (i // GROUP_SIZE) + 1
                self.status.set(f"그룹{grp} #{i+1}번 클릭1...")
                pyautogui.click(*pair[0])
                # 좌표1 → 좌표2 사이 0.8~1.1초 (너무 빠르면 클릭 씹힘) — 16슬롯 모두
                if not self._click_wait(random.uniform(0.8, 1.1)): self.status.set("클릭 멈춤"); return
                if not self._wait_mouse_idle("_click_stop"):
                    self.status.set("클릭 멈춤"); return
                self.status.set(f"그룹{grp} #{i+1}번 클릭2...")
                pyautogui.click(*pair[1])
                if done < len(active) - 1:
                    if not self._click_wait(random.uniform(0.1, 0.5)): self.status.set("클릭 멈춤"); return
            self.status.set(f"✔ 클릭 완료! (총 {len(active)*2}번)")
        except Exception as e:
            self.status.set(f"오류: {e}")

    # ── 사냥 실행 ─────────────────────────────────────────────────────
    def _start_hunt(self):
        active = [h for h in self.cfg.get("hunt_slots", [])
                  if h.get("enabled", True) and any(c for c in h.get("coords", []))]
        if not active:
            messagebox.showwarning("등록 필요", "실행할(ON) 사냥 좌표가 없습니다."); return
        if not self._try_busy_or_queue("사냥", self._start_hunt): return
        self._hunt_stop = False
        if hasattr(self, "btn_hunt_run"): self.btn_hunt_run.config(state="disabled")
        if hasattr(self, "btn_hunt_stop"): self.btn_hunt_stop.config(state="normal")
        self._minimize_claude()
        self.iconify()
        threading.Thread(target=self._run_task, args=("사냥", self._run_hunt_standalone), daemon=True).start()

    def _run_hunt_standalone(self):
        self._run_hunt()
        if hasattr(self, "btn_hunt_run"): self.btn_hunt_run.config(state="normal")
        if hasattr(self, "btn_hunt_stop"): self.btn_hunt_stop.config(state="disabled")
        self._hunt_stop = False
        self.deiconify()

    def _run_hunt(self, limit=None):
        try:
            all_slots = list(enumerate(self.cfg.get("hunt_slots", [])))
            if limit is not None:
                all_slots = all_slots[:limit]
            active = [(i, h) for i, h in all_slots
                      if h.get("enabled", True) and any(c for c in h.get("coords", []))]
            _hunt_t0 = time.time()   # 사냥 전체 소요시간 측정 (3분=180초 목표)
            for slot_done, (i, h) in enumerate(active):
                if self._hunt_stop: self.status.set("사냥 멈춤"); return
                # 슬롯 전 대기 — 전체 3분(180초) 안에 들도록 축소: 2~12 → 1~4
                slot_delay = random.uniform(1.0, 4.0)
                name = h.get("name", f"#{i+1}")
                self.status.set(f"[{name}] {slot_delay:.0f}초 후 실행...")
                if not self._hunt_wait(slot_delay): self.status.set("사냥 멈춤"); return
                for j, coord in enumerate(h["coords"]):
                    if not coord: continue
                    if self._hunt_stop: self.status.set("사냥 멈춤"); return
                    if not self._wait_mouse_idle("_hunt_stop"):
                        self.status.set("사냥 멈춤"); return
                    self.status.set(f"[{name}] 클릭 {j+1}/{HUNT_CLICKS}...")
                    pyautogui.moveTo(*coord)
                    time.sleep(random.uniform(0.1, 0.3))
                    pyautogui.mouseDown(*coord)
                    time.sleep(random.uniform(0.1, 0.25))
                    pyautogui.mouseUp(*coord)
                    time.sleep(random.uniform(0.05, 0.15))
                    if j < HUNT_CLICKS - 1:
                        # 슬롯 안 좌표간 클릭 간격 (랜덤)
                        interval = random.uniform(0.15, 0.5)
                        if not self._hunt_wait(interval):
                            self.status.set("사냥 멈춤"); return
                # 다음 슬롯 대기
                if slot_done < len(active) - 1:
                    slot_interval = random.uniform(0.6, 1.6)
                    if random.random() < 0.2:  # 20% 확률로 짧은 추가 휴식
                        slot_interval += random.uniform(0.5, 1.2)
                    if not self._hunt_wait(slot_interval):
                        self.status.set("사냥 멈춤"); return
            # 사냥 전체 소요시간 기록 (180초 목표 확인)
            _he = time.time() - _hunt_t0
            _hmark = "✔180초이내" if _he <= 180 else "⚠180초초과!"
            _hmsg = f"✔ 사냥 완료! ({len(active)}개)  [소요 {_he:.1f}초 {_hmark}]"
            try:
                with open(os.path.join(LOGS_DIR, "run_timing.txt"), "a", encoding="utf-8") as _f:
                    import datetime as _dt
                    _f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  [사냥] {_he:.1f}초 ({_hmark})\n")
            except Exception:
                pass
            self.status.set(_hmsg)
        except Exception as e:
            import traceback
            self.status.set(f"사냥 오류: {type(e).__name__}: {e}")
            print(traceback.format_exc())

    # ── 전체 자동 실행 ────────────────────────────────────────────────
    def _start(self):
        optional = {"confirm_btn", "profile_reveal_btn"}
        missing = [LABELS[k] for k in LABELS if k not in optional and not self.cfg.get(k)]
        if not self.cfg.get("char_btns"):
            missing.append("캐릭터 접속 버튼 (1개 이상)")
        if missing:
            messagebox.showwarning("등록 필요", "먼저 등록해주세요:\n" +
                                   "\n".join(f"• {m}" for m in missing)); return
        if not self._try_busy_or_queue("전체자동실행", self._start):   # 실행 중이면 대기열로
            return
        self._stop_flag = False
        self._running   = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._minimize_claude()
        self.iconify()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        total = self.acc_count.get()
        self.after(0, self._minimize_all)
        try:
            import traceback as _tb
            _dbg = open(os.path.join(LOGS_DIR, "run_debug.txt"), "w", encoding="utf-8")
            _dbg.write("_run started\n"); _dbg.flush()
            win = find_purple()
            if win is None:
                self.status.set("퍼플 실행 중...")
                subprocess.Popen(PURPLE_EXE)
                for _ in range(30):
                    if self._stop_flag: self.status.set("멈춤"); return
                    time.sleep(1)
                    win = find_purple()
                    if win: break
            if win is None:
                self.status.set("오류: 퍼플 창 없음"); return

            try:
                import win32gui, win32con, ctypes
                hwnd = win32gui.FindWindow(None, win.title)
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.5)
                    # 작업 표시줄 제외한 실제 작업 영역으로 크기 설정
                    rc = ctypes.wintypes.RECT()
                    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP,
                                         rc.left, rc.top,
                                         rc.right - rc.left, rc.bottom - rc.top,
                                         win32con.SWP_SHOWWINDOW)
                    time.sleep(0.5)
                win32gui.SetForegroundWindow(hwnd)
            except: pass
            if not self._wait(2): self.status.set("멈춤"); return

            # 팝업 감지 및 자동 닫기 (3초 대기 후)
            self.status.set("퍼플 팝업 확인 중...")
            time.sleep(3)
            close_purple_popup_if_visible(
                self.cfg,
                lambda msg: self.after(0, lambda m=msg: self.status.set(m)))
            if not self._wait(1): self.status.set("멈춤"); return

            # ── 현재 퍼플 아이디 그대로 접속 ────────────────────────────────
            try: win.activate()
            except: pass
            if not self._wait(1): self.status.set("멈춤"); return

            for acc_idx in range(total):
                if self._stop_flag: self.status.set("멈춤"); return
                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 리니지M 클릭...")
                pyautogui.click(*self.cfg["lineagem"])
                if not self._wait(3): self.status.set("멈춤"); return

                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return
                self.status.set(f"[{acc_idx+1}/{total}] 게임 실행 클릭...")
                pyautogui.click(*self.cfg["game_start"])
                if not self._wait(5): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 멀티플레이 클릭...")
                pyautogui.click(*self.cfg["multiplay"])
                if not self._wait(6): self.status.set("멈춤"); return

                # 캐릭터 버튼 클릭 전 퍼플을 항상 위로 고정
                try:
                    import win32gui, win32con
                    _hwnd = win32gui.FindWindow(None, win.title)
                    if _hwnd:
                        win32gui.SetWindowPos(_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                        win32gui.SetForegroundWindow(_hwnd)
                except: pass

                for i, (cx, cy) in enumerate(self.cfg.get("char_btns", [])):
                    if self._stop_flag: self.status.set("멈춤"); return
                    if acc_idx == 0 and i == 0:
                        self._run_char01_t = time.time()   # 캐릭터01 접속 시각 (4분30초 제한 측정)
                    self.status.set(f"[{acc_idx+1}/{total}] 캐릭터 #{i+1} 클릭...")
                    pyautogui.click(cx, cy)
                    if not self._wait(3): self.status.set("멈춤"); return

                # 캐릭터 버튼 완료 후 항상 위 해제
                try:
                    if _hwnd:
                        win32gui.SetWindowPos(_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                except: pass

                try: _dbg.write(f"[LOOP] acc_idx={acc_idx} total={total} 마지막여부={acc_idx == total - 1}\n"); _dbg.flush()
                except Exception: pass
                if acc_idx == total - 1:
                    # ── 마지막 캐릭터 접속 후 순서 ──
                    # ① 지정계정로 전환(프로필→구글계정→확인) ② 리니지M 좌측버튼으로 지정계정 확인
                    # ③ 지정계정이면 퍼플 최소화
                    if not self._wait(3): self.status.set("멈춤"); return

                    # ① 지정 계정으로 전환
                    self.status.set("지정 계정으로 전환 중...")
                    try: _dbg.write(f"[SWITCH] 전환 시작 profile={self.cfg.get('profile_btn')} google={self.cfg.get('google_acc')} confirm={self.cfg.get('confirm_btn')}\n"); _dbg.flush()
                    except Exception: pass
                    if self.cfg.get("profile_btn"):
                        pyautogui.click(*self.cfg["profile_btn"])
                        try: _dbg.write("[SWITCH] profile_btn 클릭\n"); _dbg.flush()
                        except Exception: pass
                        if not self._wait(2): self.status.set("멈춤"); return
                    if self.cfg.get("google_acc"):
                        pyautogui.click(*self.cfg["google_acc"])
                        try: _dbg.write("[SWITCH] google_acc 클릭\n"); _dbg.flush()
                        except Exception: pass
                        if not self._wait(2): self.status.set("멈춤"); return
                    if self.cfg.get("confirm_btn"):
                        pyautogui.click(*self.cfg["confirm_btn"])
                        try: _dbg.write("[SWITCH] confirm_btn 클릭 → 로딩 10초\n"); _dbg.flush()
                        except Exception: pass
                        # 계정 전환 후 로딩(약 8초)이 끝나야 리니지M 좌측버튼이 생성됨
                        self.status.set("계정 전환 로딩 대기 중... (약 10초)")
                        if not self._wait(10): self.status.set("멈춤"); return

                    # ② 게임 창 활성화 → 리니지M 좌측버튼으로 아이디 표시 → 지정계정 확인
                    self.status.set("지정계정 확인 중...")
                    try: win.activate()
                    except Exception: pass
                    if not self._wait(1): self.status.set("멈춤"); return
                    if self.cfg.get("profile_reveal_btn"):
                        pyautogui.click(*self.cfg["profile_reveal_btn"])
                        if not self._wait(3): self.status.set("멈춤"); return
                    _matched3, _oid3, _r3 = self._is_target_account()
                    self.status.set(f"아이디 '{_oid3}' (일치율 {int(_r3*100)}%)")
                    try: _dbg.write(f"[SWITCH] 아이디 확인: '{_oid3}' 일치율 {int(_r3*100)}% matched={_matched3}\n"); _dbg.flush()
                    except Exception: pass

                    # ③ 퍼플 최소화 — 확인 성공/실패와 무관하게 항상 최소화
                    #    (다음 좌표 클릭이 퍼플 위에서 눌리지 않도록 반드시 최소화)
                    if _matched3:
                        self.status.set("✔ 지정계정 확인 → 퍼플 최소화")
                    else:
                        self.status.set(f"⚠ 지정계정 확인 실패('{_oid3}') — 그래도 최소화 진행")
                    try:
                        import win32gui, win32con
                        # 계정 전환하면 퍼플 창이 새로 생겨 win 객체가 오래됨(죽은 창) →
                        # "PURPLE" 제목으로 현재 창을 다시 찾아서 최소화
                        _p_hwnd = win32gui.FindWindow(None, "PURPLE")
                        if not _p_hwnd:
                            try: _p_hwnd = win32gui.FindWindow(None, win.title)
                            except Exception: _p_hwnd = 0
                        if _p_hwnd:
                            win32gui.ShowWindow(_p_hwnd, win32con.SW_MINIMIZE)
                        else:
                            win.minimize()
                    except Exception:
                        try: win.minimize()
                        except Exception: pass
                    try: _dbg.write("[SWITCH] 퍼플 최소화 완료 → 그룹 클릭으로\n"); _dbg.flush()
                    except Exception: pass
                    break

                self.status.set(f"[{acc_idx+1}/{total}] 로딩 대기... (15초)")
                if not self._wait(15): self.status.set("멈춤"); return
                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 프로필 클릭...")
                pyautogui.click(*self.cfg["profile_btn"])
                if not self._wait(2): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 구글 계정 클릭...")
                pyautogui.click(*self.cfg["google_acc"])
                if not self._wait(2): self.status.set("멈춤"); return

                if self.cfg.get("confirm_btn"):
                    self.status.set(f"[{acc_idx+1}/{total}] 확인 클릭...")
                    pyautogui.click(*self.cfg["confirm_btn"])

                self.status.set(f"[{acc_idx+1}/{total}] 새 계정 로딩... (15초)")
                if not self._wait(15): self.status.set("멈춤"); return

                for _ in range(10):
                    win = find_purple();
                    if win: break
                    time.sleep(1)
                if win is None:
                    self.status.set("오류: 퍼플 창 없음"); return
                try: win.activate()
                except: pass
                if not self._wait(2): self.status.set("멈춤"); return

            if self._stop_flag: self.status.set("멈춤"); return

            # 접속 완료 → 20초 대기 → 클릭 등록(그룹1,2) 실행
            self.status.set("✔ 모든 계정 접속 완료! 20초 후 클릭 등록 실행...")
            if not self._wait(20): self.status.set("멈춤"); return

            active = [(i, s) for i, s in enumerate(self.cfg.get("click_slots", []))
                      if s[0] and s[1]]
            for done, (i, pair) in enumerate(active):
                if self._stop_flag: self.status.set("멈춤"); return
                grp = (i // GROUP_SIZE) + 1
                self.status.set(f"그룹{grp} #{i+1}번 클릭1...")
                pyautogui.click(*pair[0])
                # 두번째 클릭이 좀 빨라서 0.5~0.7초 랜덤 추가로 늦춤
                if not self._wait(random.uniform(0.6, 1.2) + random.uniform(0.5, 0.7)):
                    self.status.set("멈춤"); return
                self.status.set(f"그룹{grp} #{i+1}번 클릭2...")
                pyautogui.click(*pair[1])
                if i == 4 and len(pair) > 2 and pair[2]:
                    if not self._wait(random.uniform(0.6, 1.2)): self.status.set("멈춤"); return
                    self.status.set(f"그룹{grp} #{i+1}번 클릭3...")
                    pyautogui.click(*pair[2])
                if done < len(active) - 1:
                    if not self._wait(2.5): self.status.set("멈춤"); return
            # 캐릭터01 접속 → 그룹2 완료까지 실제 소요시간 측정 (4분30초=270초 제한 확인)
            _t0 = getattr(self, "_run_char01_t", None)
            if _t0:
                _elapsed = time.time() - _t0
                _mark = "✔270초이내" if _elapsed <= 270 else "⚠270초초과!"
                _msg = f"[타이밍] 캐릭터01→그룹2 완료: {_elapsed:.1f}초 ({_mark})"
                try:
                    with open(os.path.join(LOGS_DIR, "run_timing.txt"), "a", encoding="utf-8") as _f:
                        import datetime as _dt
                        _f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {_msg}\n")
                except Exception:
                    pass
                self.status.set(_msg)
                time.sleep(1)
            # 그룹→사냥 전환 시간 35%로 축소 (5초 → 1.75초)
            self.status.set(f"✔ 클릭 등록 완료! 1.75초 후 사냥 실행 시작...")
            if not self._wait(1.75): self.status.set("멈춤"); return

            if not self._stop_flag:
                self._hunt_stop = False
                self._run_hunt()
            self.status.set("✔ 전체 실행 완료!")

        except Exception as e:
            import traceback as _tb2
            _err = f"오류: {type(e).__name__}: {e}"
            self.status.set(_err)
            try:
                with open(os.path.join(LOGS_DIR, "run_debug.txt"), "a", encoding="utf-8") as _f:
                    _f.write(_err + "\n" + _tb2.format_exc())
            except Exception:
                pass
        finally:
            self._running = False
            self._clear_busy("전체자동실행")
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            self._stop_flag = False
            self.after(0, self._restore_all)


# ── 좌표 오버레이 ─────────────────────────────────────────────────────────
class _HuntGroupMoveOverlay(tk.Toplevel):
    """사냥 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="red", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36:
            return
        self._drag  = True
        self._moved = False
        self._last  = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag:
            return
        dx = e.x - self._last[0]
        dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1:
            self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots:
            d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag  = False
            self._moved = False
        else:
            # 빈 곳 클릭 → 저장 후 닫기
            coords = self.app.cfg["hunt_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["hunt_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg)
            self.app._refresh_ui()
            self.app.status.set(f"✔ 사냥 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _DungeonGroupMoveOverlay(tk.Toplevel):
    """던전 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#e67e22", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["dungeon_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["dungeon_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg)
            self.app._refresh_ui()
            self.app.status.set(f"✔ 던전 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _PastChainMoveOverlay(tk.Toplevel):
    """과거섬 #01→#04 순차 그룹 이동: 저장하면 자동으로 다음 슬롯으로 이어짐"""
    R = 8

    def __init__(self, app, slot_idx, dots, next_idx, end):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self.next_idx = next_idx; self.end = end
        self._dots = [[x, y, num] for x, y, num in dots]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close_all())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        remain = self.end - self.slot_idx
        cv.create_text(self._sw//2, 18,
            text=f"#{self.slot_idx+1:02d} 위치 조정 ({remain}개 남음)  |  드래그: 이동  |  빈 곳 클릭: 저장→다음  |  ESC: 전체취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#c0392b", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            # 저장
            coords = self.app.cfg["past_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["past_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.destroy()
            # 다음 슬롯으로
            if self.next_idx < self.end:
                self.app._past_chain_move(self.next_idx, self.end)
            else:
                self.app.deiconify()
                self.app.status.set("✔ #01~#04 그룹 이동 저장 완료")

    def _close_all(self):
        self.destroy(); self.app.deiconify()
        self.app.status.set("취소됨")


class _PastGroupMoveOverlay(tk.Toplevel):
    """과거섬 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장
    dots: [(x, y, num, coord_idx), ...]  — coord_idx 가 실제 coords 배열 인덱스
    """
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        # dots 는 (x, y, num, coord_idx) 또는 (x, y, num) 둘 다 허용
        self._dots = [[d[0], d[1], d[2], d[3] if len(d)>3 else i]
                      for i, d in enumerate(dots)]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for d in self._dots:
            x, y, num = d[0], d[1], d[2]
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#c0392b", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["past_slots"][self.slot_idx].get("coords", [])
            for x, y, _, ci in self._dots:
                if ci < len(coords):
                    coords[ci] = [x, y]
            self.app.cfg["past_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 과거섬 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _SchedGroupMoveOverlay(tk.Toplevel):
    """스케줄 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장
    dots: [(x, y, num, coord_idx), ...]
    """
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self._dots = [[d[0], d[1], d[2], d[3] if len(d)>3 else i]
                      for i, d in enumerate(dots)]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for d in self._dots:
            x, y, num = d[0], d[1], d[2]
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#16a085", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["sched_slots"][self.slot_idx].get("coords", [])
            for x, y, _, ci in self._dots:
                if ci < len(coords):
                    coords[ci] = [x, y]
            self.app.cfg["sched_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 스케줄 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _SlotGroupMoveOverlay(tk.Toplevel):
    """클릭 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 16

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self._dots = [[x, y, num] for x, y, num in dots]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#2980b9", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 11, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            pair = [None, None]
            for x, y, num in self._dots:
                step = 0 if str(num) == "1" else 1
                pair[step] = [x, y]
            self.app.cfg["click_slots"][self.slot_idx] = pair
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _MailGroupMoveOverlay(tk.Toplevel):
    """우편함 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#8e44ad", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 7, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["mail_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["mail_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 우편함 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _DotPreviewOverlay(tk.Toplevel):
    """스크린샷 배경 + 드래그 가능한 빨간 점 미리보기.
    dots: [(x, y, num), ...]
    save_fn(dot_idx, new_x, new_y): 점 이동 시 호출
    rereg_fn: ✏ 재등록 버튼 콜백
    """
    R = 5

    def __init__(self, app, title, dots, rereg_fn, save_fn=None, dot_r=5):
        super().__init__()
        self.R        = dot_r
        self.app      = app
        self.rereg_fn = rereg_fn
        self.save_fn  = save_fn
        self._dots    = [[x, y, num] for x, y, num in dots]  # mutable
        self._drag      = None   # dragging dot index
        self._grp_drag  = False  # dragging empty space (group move)
        self._moved     = False
        self._last      = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="hand2")
        self._cv.pack(fill="both", expand=True)
        self._bx = sw - 100

        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        # 상단 안내바
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="점 드래그: 개별 이동  |  빈 곳 드래그: 전체 이동  |  빈 곳 클릭: 닫기  |  ESC: 닫기",
            fill="#aaa", font=("맑은 고딕", 10))
        bx = self._bx
        cv.create_rectangle(bx, 6, bx+90, 30, fill="#e67e22", outline="")
        cv.create_text(bx+45, 18, text="✏ 재등록", fill="white",
                       font=("맑은 고딕", 9, "bold"))
        # 점들
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="red", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 7, "bold"))

    def _hit(self, ex, ey):
        r = self.R + 6
        for i, (x, y, _) in enumerate(self._dots):
            if abs(ex - x) < r and abs(ey - y) < r:
                return i
        return None

    def _on_press(self, e):
        if e.y < 36: return
        hit = self._hit(e.x, e.y)
        if hit is not None:
            self._drag      = hit     # 개별 점 드래그
            self._grp_drag  = False
        else:
            self._drag      = None
            self._grp_drag  = True   # 빈 공간 → 그룹 드래그
        self._moved = False
        self._last  = (e.x, e.y)

    def _on_drag(self, e):
        dx = e.x - self._last[0]
        dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1:
            self._moved = True
        self._last = (e.x, e.y)
        if self._drag is not None:
            self._dots[self._drag][0] += dx
            self._dots[self._drag][1] += dy
        elif self._grp_drag:
            for d in self._dots:
                d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        # 재등록 버튼 클릭
        if self._bx <= e.x <= self._bx + 90 and 6 <= e.y <= 30:
            self._close(); self.rereg_fn(None); return
        if self._moved:
            # 드래그 후 저장
            if self._drag is not None:
                x, y, num = self._dots[self._drag]
                if self.save_fn: self.save_fn(self._drag, x, y)
            elif self._grp_drag:
                if self.save_fn:
                    for i, (x, y, _) in enumerate(self._dots):
                        self.save_fn(i, x, y)
            self._drag = None; self._grp_drag = False; self._moved = False
        elif self._drag is not None and not self._moved:
            # 점 클릭 → 개별 재등록
            dot_idx = self._drag
            self._drag = None
            self._close(); self.rereg_fn(dot_idx)
        else:
            # 빈 곳 단순 클릭 → 닫기
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _DotPreviewOverlayNav(_DotPreviewOverlay):
    """그룹 이동(이전/다음) 버튼이 추가된 미리보기 오버레이."""
    def __init__(self, app, title, dots, rereg_fn, save_fn, prev_fn, next_fn, dot_r=5):
        self._prev_fn = prev_fn
        self._next_fn = next_fn
        super().__init__(app, title, dots, rereg_fn, save_fn, dot_r)

    def _close(self):
        self.destroy()
        self.app.deiconify()
        if self.app._pass_win and self.app._pass_win.winfo_exists():
            self.app._pass_win.deiconify()

    PW = 42; PH = 18; PY = 9

    def _draw(self):
        super()._draw()
        cv = self._cv
        pw, ph, py = self.PW, self.PH, self.PY
        px = 10
        cv.create_rectangle(px, py, px+pw, py+ph, fill="#2c3e50", outline="")
        cv.create_text(px+pw//2, py+ph//2, text="◀ 이전", fill="white", font=("맑은 고딕", 7, "bold"))
        nx = px + pw + 4
        cv.create_rectangle(nx, py, nx+pw, py+ph, fill="#2c3e50", outline="")
        cv.create_text(nx+pw//2, py+ph//2, text="다음 ▶", fill="white", font=("맑은 고딕", 7, "bold"))

    def _on_release(self, e):
        pw, ph, py = self.PW, self.PH, self.PY
        px = 10; nx = px + pw + 4
        if py <= e.y <= py+ph:
            if px <= e.x <= px+pw:
                self._close(); self.app.after(300, self._prev_fn); return
            if nx <= e.x <= nx+pw:
                self._close(); self.app.after(300, self._next_fn); return
        super()._on_release(e)


class _ProfileAreaOverlay(tk.Toplevel):
    """퍼플 아이디 표시 영역 드래그 등록"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text="퍼플 아이디가 표시되는 영역을 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 16, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root, outline="cyan", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start
        x1, y1 = e.x_root, e.y_root
        self.destroy()
        self.app.cfg["profile_id_area"] = {
            "x": min(x0,x1), "y": min(y0,y1),
            "w": abs(x1-x0), "h": abs(y1-y0)
        }
        # 등록 당시 퍼플 창 위치도 저장 → 다른 컴퓨터/다른 창위치에서 자동 보정
        try:
            w = find_purple()
            if w:
                self.app.cfg["profile_id_area_win"] = [w.left, w.top]
        except Exception:
            pass
        save_cfg(self.app.cfg)
        self.app.deiconify()
        self.app._profile_area_var.set("등록됨")
        self.app.status.set("✔ 아이디 영역 등록 완료 (창 위치 보정 지원)")

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()


class _NameAreaOverlay(tk.Toplevel):
    """캐릭터 이름 OCR 영역을 드래그로 등록하는 오버레이"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None
        self._rect = None
        tk.Label(self, text="캐릭터 이름 영역을 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 18, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root,
                                                    outline="yellow", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start
        x1, y1 = e.x_root, e.y_root
        self.destroy()
        ax, ay = min(x0,x1), min(y0,y1)
        self.app.cfg["name_ocr_area"] = {
            "x": ax, "y": ay,
            "w": abs(x1-x0), "h": abs(y1-y0)
        }
        save_cfg(self.app.cfg)
        self.app.deiconify()
        self.app.status.set(f"✔ 이름 영역 등록 완료 ({ax},{ay} / {abs(x1-x0)}×{abs(y1-y0)})")

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()
        self.app.status.set("이름 영역 등록 취소")


class _AssignWindowOverlay(tk.Toplevel):
    """클릭한 창을 사냥 슬롯에 지정하는 전체화면 오버레이"""
    def __init__(self, app, slot_idx, on_done=None):
        super().__init__()
        self.app = app
        self.slot_idx = slot_idx
        self.on_done = on_done
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        tk.Label(self, text=f"#{slot_idx+1:02d} 창 지정\n지정할 리니지M 창을 클릭하세요\nESC = 취소",
                 font=("맑은 고딕", 22, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self.bind("<Button-1>", self._on_click)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_click(self, e):
        x, y = e.x_root, e.y_root
        self.destroy()
        try:
            self.app.update()
            time.sleep(0.1)
            # win32gui로 안정적으로 창 감지
            hwnd = win32gui.WindowFromPoint((x, y))
            root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT) if hwnd else hwnd
            if not root: root = hwnd
            r = win32gui.GetWindowRect(root)
            title = win32gui.GetWindowText(root) or f"hwnd:{root}"
            cx, cy = (r[0]+r[2])//2, (r[1]+r[3])//2
            slot_num = f"#{self.slot_idx+1:02d}"
            new_title = f"리니지M {slot_num}"
            try:
                win32gui.SetWindowText(root, new_title)
            except: pass
            aw = {"hwnd": root, "cx": cx, "cy": cy,
                  "x": r[0], "y": r[1],
                  "w": r[2]-r[0], "h": r[3]-r[1],
                  "title": new_title,
                  "slot_num": slot_num}
            self.app.cfg["hunt_slots"][self.slot_idx]["assigned_window"] = aw
            save_cfg(self.app.cfg)
            if self.on_done:
                self.app.after(0, lambda t=title: self.on_done(self.slot_idx, t))
        except Exception as ex:
            self.app.after(0, lambda: self.app.status.set(f"지정 오류: {type(ex).__name__}: {ex}"))
        finally:
            self.app.deiconify()

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()
        self.app.status.set(f"#{self.slot_idx+1:02d} 창 지정 취소")


class CoordOverlay(tk.Toplevel):
    def __init__(self, app, mode="single"):
        super().__init__()
        self.app  = app
        self.mode = mode
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        # 좌표 등록 시 클로드(항상 위) 창이 타깃을 가리지 않도록 캡처 전에 최소화
        try:
            app._minimize_claude()
        except Exception:
            pass
        time.sleep(0.15)   # 최소화가 화면에 반영될 시간

        from PIL import Image as _Img, ImageTk as _ITk, ImageGrab as _IG
        shot = _IG.grab(all_screens=True).resize((sw, sh))
        self._bg = _ITk.PhotoImage(shot)

        c = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=self._bg)
        c.create_rectangle(0, 0, sw, 54, fill="#1a252f", outline="")

        if mode == "char":
            n = len(app.cfg.get("char_btns", [])) + 1
            label = f"캐릭터 접속 버튼 #{n}"
        elif mode == "char_rereg":
            idx = app._char_rereg_idx
            label = f"캐릭터 #{idx+1} 새 위치"
        elif mode == "slot":
            label = f"#{app._slot_target+1}번 슬롯 클릭{app._slot_step+1}"
        elif mode == "hunt":
            idx  = app._hunt_reg_idx
            step = app._hunt_reg_step
            name = app.cfg["hunt_slots"][idx].get("name", f"#{idx+1}")
            label = f"[{name}] 클릭{step+1} 위치"
        elif mode == "mail":
            label = f"우편함 #{app._reg_mail_slot_idx+1} 클릭{app._reg_mail_click_idx+1} 위치"
        elif mode == "dungeon":
            lbl = ["메뉴", "클릭1", "클릭2"][app._reg_dungeon_click_idx]
            label = f"던전 #{app._reg_dungeon_slot_idx+1} [{lbl}] 위치"
        elif mode == "past":
            label = f"과거의말하는섬 #{app._reg_past_slot_idx+1} [클릭] 위치"
        elif mode == "pass":
            label = f"패스권 #{app._reg_pass_slot_idx+1} [{PASS_LABELS[app._reg_pass_click_idx]}] 위치"
        elif mode == "sched":
            label = f"매일매일 스케줄 #{app._reg_sched_slot_idx+1} [클릭] 위치"
        elif mode == "seq":
            label = f"연속클릭 #{app._seq_reg_idx+1} 위치"
        elif mode == "dc":
            label = f"일반던전충전 #{app._dc_reg_idx+1} 위치"
        elif mode == "doll":
            label = f"인형탐험 #{app._doll_reg_idx+1} 좌표{app._doll_reg_step+1} 위치"
        else:
            label = LABELS.get(app._reg_target, "버튼")

        c.create_text(sw//2, 27, text=f"{label}  —  클릭하세요  (ESC: 취소)",
                      fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

    def _click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        if   self.mode == "char":      self.app.on_char_coord(x, y)
        elif self.mode == "char_rereg":self.app.on_char_rereg_coord(x, y)
        elif self.mode == "slot":      self.app.on_slot_coord(x, y)
        elif self.mode == "hunt":      self.app.on_hunt_coord(x, y)
        elif self.mode == "mail":      self.app.on_mail_coord(x, y)
        elif self.mode == "dungeon":   self.app.on_dungeon_coord(x, y)
        elif self.mode == "past":      self.app.on_past_coord(x, y)
        elif self.mode == "pass":      self.app.on_pass_coord(x, y)
        elif self.mode == "sched":     self.app.on_sched_coord(x, y)
        elif self.mode == "seq":       self.app.on_seq_coord(x, y)
        elif self.mode == "dc":        self.app.on_dc_coord(x, y)
        elif self.mode == "doll":      self.app.on_doll_coord(x, y)
        else:                          self.app.on_coord(x, y)


class _RerollPointOverlay(tk.Toplevel):
    """아이템 리롤용 단일 좌표 클릭 등록 (스크린샷 배경)."""
    def __init__(self, app, label, on_pick):
        super().__init__()
        self.app = app; self.on_pick = on_pick
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True); self.attributes("-topmost", True)
        from PIL import ImageTk as _ITk, ImageGrab as _IG
        self._bg = _ITk.PhotoImage(_IG.grab(all_screens=True).resize((sw, sh)))
        c = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=self._bg)
        c.create_rectangle(0, 0, sw, 54, fill="#1a252f", outline="")
        c.create_text(sw//2, 27, text=f"{label}  —  클릭하세요  (ESC: 취소)",
                      fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._click)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        self.on_pick(x, y)

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()
        if self.app._reroll_win and self.app._reroll_win.winfo_exists():
            self.app._reroll_win.deiconify()
        self.app.status.set("좌표 등록 취소")


class _RerollAreaOverlay(tk.Toplevel):
    """아이템 리롤용 캡처 영역 드래그 등록."""
    def __init__(self, app, on_pick, label="아이템 이미지 영역을 드래그하세요"):
        super().__init__()
        self.app = app; self.on_pick = on_pick
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0"); self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text=f"{label}\nESC = 취소",
                 font=("맑은 고딕", 18, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root,
                                                    outline="yellow", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start; x1, y1 = e.x_root, e.y_root
        self.destroy()
        ax, ay = min(x0, x1), min(y0, y1)
        self.on_pick(ax, ay, abs(x1 - x0), abs(y1 - y0))

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()
        if self.app._reroll_win and self.app._reroll_win.winfo_exists():
            self.app._reroll_win.deiconify()
        self.app.status.set("영역 등록 취소")


def _watch_and_restart():
    """파일 변경 감지 시 자동 재시작"""
    watch = [
        os.path.join(BASE, "lineagem_launcher.py"),
        os.path.join(BASE, "lineagem_island.py"),
    ]
    mtimes = {f: os.path.getmtime(f) for f in watch if os.path.exists(f)}
    while True:
        time.sleep(1.5)
        for f in watch:
            if not os.path.exists(f): continue
            try:
                mt = os.path.getmtime(f)
            except OSError:
                continue
            if mt != mtimes.get(f):
                time.sleep(0.5)  # 저장 완료 대기
                subprocess.Popen(
                    [r"C:\Users\user\AppData\Local\Python\bin\pythonw.exe",
                     os.path.join(BASE, "lineagem_launcher.py")]
                )
                os._exit(0)

if __name__ == "__main__":
    threading.Thread(target=_watch_and_restart, daemon=True).start()
    App().mainloop()
