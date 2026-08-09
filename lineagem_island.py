import ctypes
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass

# 기존 인스턴스 종료 후 단일 실행
import subprocess, sys, os as _os
_my_pid = str(_os.getpid())

def _island_cmd_arg(cmdline):
    """명령줄에서 lineagem_island.py 바로 뒤 인자(컬럼 번호) 추출 — 없으면 None."""
    toks = cmdline.split()
    for i, t in enumerate(toks):
        if t.lower().rstrip('"').endswith("lineagem_island.py"):
            if i + 1 < len(toks) and not toks[i + 1].startswith("--"):
                return toks[i + 1].strip('"')
            return None
    return None

try:
    out = subprocess.check_output(
        'wmic process where "name=\'pythonw.exe\'" get processid,commandline /format:csv',
        shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore")
    _my_arg = sys.argv[1] if len(sys.argv) > 1 else None
    for line in out.splitlines():
        if "lineagem_island" not in line.lower():
            continue
        parts = line.strip().split(",")
        pid = parts[-1].strip()
        if not pid or pid == _my_pid:
            continue
        if _my_arg is None:
            # 전체 실행기: 기존 전부 종료 (기존 동작)
            subprocess.call(f"taskkill /F /PID {pid}", shell=True, stderr=subprocess.DEVNULL)
        else:
            # 단독 컬럼 모드: '같은 컬럼'으로 떠 있는 창만 종료 → 중복 방지, 다른 컬럼은 공존
            cl = ",".join(parts[1:-1])
            if _island_cmd_arg(cl) == _my_arg:
                subprocess.call(f"taskkill /F /PID {pid}", shell=True, stderr=subprocess.DEVNULL)
except Exception:
    pass
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
import time, threading, json, os, random
import pyautogui

try:
    from precise_click import install as _install_precise_click
    _install_precise_click(pyautogui)   # 마우스가 움직여도 지정 좌표에 정확히 클릭
    _PRECISE_OK = True
except Exception:
    _PRECISE_OK = False


_EXT_SCANS = {0x48, 0x50, 0x4B, 0x4D}   # 방향키 스캔코드 (확장키 플래그 필요)

def _send_scan_key(scan_codes, down):
    """SendInput 스캔코드 방식 키 입력 — 게임(DirectInput)도 인식한다.
    WASD 등 일반키는 확장 플래그 없이, 방향키는 확장 플래그로 보낸다."""
    import ctypes
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP       = 0x0002
    KEYEVENTF_SCANCODE    = 0x0008
    ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]

    class _IU(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", ctypes.c_ulong), ("u", _IU)]

    arr = (INPUT * len(scan_codes))()
    for i, sc in enumerate(scan_codes):
        flags = KEYEVENTF_SCANCODE
        if sc in _EXT_SCANS:
            flags |= KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= KEYEVENTF_KEYUP
        arr[i].type = 1  # INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(0, sc, flags, 0, None)
    ctypes.windll.user32.SendInput(len(arr), arr, ctypes.sizeof(INPUT))

MOUSE_IDLE_SEC = 5.0  # 마우스 정지 후 재개까지 대기 시간

def wait_mouse_idle(stop_fn, status_fn, idle_sec=MOUSE_IDLE_SEC):
    """마우스가 움직이는 중일 때만 대기. 안 움직이면 즉시 True 반환."""
    prev = pyautogui.position()
    time.sleep(0.1)
    cur = pyautogui.position()
    if cur == prev:
        return not stop_fn()
    status_fn(f"⏸ 마우스 움직임 감지 — {int(idle_sec)}초 정지 후 재개...")
    last_move = time.time()
    prev = cur
    while True:
        if stop_fn(): return False
        time.sleep(0.1)
        cur = pyautogui.position()
        if cur != prev:
            last_move = time.time()
            prev = cur
        elif time.time() - last_move >= idle_sec:
            return True

import datetime
BASE        = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "island_coords.json")
COUNT_FILE  = os.path.join(BASE, "island_counts.json")
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05

SLOTS        = 16
CLICKS       = 6
HOVER_WAIT   = 2.0
CLICK_INTERVAL = 2.0  # 클릭 간격(초) — 현재 2초
CLICK_LABELS = ["클릭1", "클릭2", "추가", "클릭3", "클릭4", "클릭5"]

# 던전별 좌표 개수 (기본 6개, 예외만 지정)
CLICKS_BY_KEY = {"월요일_잊혀진섬": 27, "수금_오만의탑": 30,   # 오만 30 · 잊섬 27 · 에카 27
                 "토요일_악몽의섬": 26, "화요일_에카": 27}

def clicks_for(key):
    return CLICKS_BY_KEY.get(key, CLICKS)

def labels_for(key):
    n = clicks_for(key)
    if n == CLICKS:
        return CLICK_LABELS
    return [f"클릭{i+1}" for i in range(n)]

DUNGEONS = [
    {"key": "수금_오만의탑",   "label": "수~금\n오만의탑",   "color": "#e67e22"},
    {"key": "토요일_악몽의섬", "label": "토요일\n악몽의섬",   "color": "#8e44ad"},
    {"key": "월요일_잊혀진섬", "label": "월요일\n잊혀진섬",   "color": "#2980b9"},
    {"key": "화요일_에카",     "label": "화요일\n  에카  ",   "color": "#27ae60"},
    {"key": "귀환주문서",      "label": "귀환\n주문서",       "color": "#c0392b"},
    {"key": "카매사오기",      "label": "카매\n사오기",       "color": "#1a5276"},
]

# 클릭 대신 마우스 이동만 할 좌표 인덱스 (던전키: {인덱스, ...})
MOVE_ONLY_INDICES = {
    "카매사오기": {1},  # 클릭2는 이동만
}

# (2026-08-09) 좌표 클릭 사이 간격을 전체적으로 12~17% 늦춘다 —
# 초반은 잘 되는데 뒤로 갈수록 클릭이 씹히는 것 같다는 사용자 피드백.
SLOW_MIN, SLOW_MAX = 1.12, 1.17


def slow_factor():
    """클릭 간격에 곱할 배율 (12~17% 랜덤 지연)."""
    return random.uniform(SLOW_MIN, SLOW_MAX)


def today():
    return datetime.date.today().isoformat()

def load_counts():
    try:
        with open(COUNT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_counts(data):
    with open(COUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_cfg():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    for d in DUNGEONS:
        n = clicks_for(d["key"])
        if d["key"] not in data:
            data[d["key"]] = [{"name": "미등록", "coords": [None]*n}
                               for _ in range(SLOTS)]
        else:
            # 기존 좌표 배열이 짧으면 해당 던전의 좌표 수만큼 패딩
            for slot in data[d["key"]]:
                coords = slot.get("coords", [])
                while len(coords) < n:
                    coords.append(None)
                slot["coords"] = coords
    return data

SAVE_KEYS = None  # 이 창이 소유한 던전 키 — 단독 창은 자기 던전만 파일에 반영

def save_cfg(cfg):
    # 여러 창이 동시에 열려 있어도 서로의 데이터를 지우지 않도록,
    # 디스크 최신본을 다시 읽어 이 창이 소유한 키만 덮어쓴다 (전체 덮어쓰기 금지)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            disk = json.load(f)
    except Exception:
        disk = {}
    keys = list(SAVE_KEYS) if SAVE_KEYS else list(cfg.keys())
    # 던전 데이터가 아닌 설정 키(_presets 등)는 어느 창에서 바꿔도 항상 저장한다
    keys += [k for k in cfg if k.startswith("_") and k not in keys]
    for k in keys:
        if k in cfg:
            disk[k] = cfg[k]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(disk, f, ensure_ascii=False, indent=2)


class CoordOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(str(sw) + "x" + str(sh) + "+0+0")
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.configure(bg="black")
        c = tk.Canvas(self, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        # 안내문 — 프리셋 좌표 찍기 모드도 지원하고, 실패해도 오버레이가 죽지 않게
        lbl = "위치를 클릭하세요   (ESC: 취소)"
        try:
            pm = getattr(app, "_preset_pick", None)
            if pm:
                lbl = ("프리셋 — 클릭 " + str(pm.get("jx", 0) + 1) +
                       " 번을 바꿀 위치를 클릭하세요   (ESC: 취소)")
            else:
                si  = app._reg_slot_idx
                ci  = app._reg_click_idx
                key = app._reg_key
                name = app.cfg[key][si].get("name", "#" + str(si + 1))
                lbl = "[" + str(name) + "]  " + labels_for(key)[ci] + " 위치를 클릭하세요   (ESC: 취소)"
        except Exception:
            pass
        c.create_text(sw // 2, 60, text=lbl, fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._on_click)
        self.bind("<ButtonPress-1>", self._on_click)      # 캔버스 밖 클릭도 처리
        for w in (self, c):
            w.bind("<Escape>", self._cancel)

    def _cancel(self, _e=None):
        try: self.destroy()
        except Exception: pass
        app = self.app
        try:
            if getattr(app, "_preset_pick", None):
                app._preset_pick = None
                w = getattr(app, "_preset_win", None)
                if w and w.winfo_exists():
                    w.deiconify(); w.lift()
                app._status.set("좌표 찍기 취소")
        except Exception:
            pass
        try: app.deiconify()
        except Exception: pass

    def _on_click(self, e):
        x, y = e.x_root, e.y_root
        self.destroy(); self.update_idletasks()
        self.app.on_coord(x, y)

class MoveOverlay(tk.Toplevel):
    def __init__(self, app, step):
        super().__init__()
        self.app  = app
        self.step = step
        self.overrideredirect(True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.lift(); self.focus_force()
        self.configure(bg="black")
        c = tk.Canvas(self, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        lbl = ("이전 기준점을 클릭하세요  (ESC: 취소)"
               if step == 1 else "새 위치를 클릭하세요  (ESC: 취소)")
        c.create_text(sw//2, 60, text=lbl, fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

    def _on_click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        self.app.on_move_coord(self.step, x, y)


class BatchOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.lift(); self.focus_force()
        self.configure(bg="black")
        c = tk.Canvas(self, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        idx = app._batch_idx
        _bl = labels_for(app._batch_key)
        lbl = f"[{_bl[idx]}] 위치 클릭  ({idx+1}/{len(_bl)})  —  ESC: 취소"
        c.create_text(sw//2, 60, text=lbl, fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

    def _on_click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        self.app.on_batch_coord(x, y)


class IslandApp(tk.Tk):
    def __init__(self, focus_idx=None):
        super().__init__()
        self._focus_idx = focus_idx  # None=전체, 0~3=해당 던전만
        dungeons_to_show = [DUNGEONS[focus_idx]] if focus_idx is not None else DUNGEONS
        self._dungeons_to_show = dungeons_to_show
        if focus_idx is not None:
            global SAVE_KEYS
            SAVE_KEYS = [d["key"] for d in dungeons_to_show]

        if focus_idx is not None:
            d = DUNGEONS[focus_idx]
            self.title(f"🏝 {d['label'].replace(chr(10), ' ')}")
        else:
            self.title("리니지M 섬/던전 실행기")

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        ox = int(sw * 0.03)
        oy = int(sh * 0.03)
        # 26칸 던전(잊혀진섬·오만의탑·악몽의섬·에카) 단독 창은 확대 + 셀 스트레치
        _is_forgotten = (focus_idx is not None
                         and DUNGEONS[focus_idx]["key"] in CLICKS_BY_KEY)
        if _is_forgotten:
            try:
                cur = float(self.tk.call("tk", "scaling"))
                self.tk.call("tk", "scaling", cur * 1.14)   # 30% 축소 배율
            except Exception:
                pass
            # 사용자가 맞춰놓은 크기·위치로 고정 (2026-08-07 확정)
            self._fixed_geometry = "702x909+550+367"
            self.geometry(self._fixed_geometry)
        elif focus_idx is not None:
            self.geometry(f"500x{sh * 2 // 3}+{ox}+{oy}")
        else:
            self.geometry(f"{int(1380*1.3)}x{sh * 2 // 3}+{ox}+{oy}")
        self.resizable(True, True)

        self.cfg    = load_cfg()
        self.counts = load_counts()
        self._stop_flag     = False
        self._active_key    = None
        self._reg_key       = None
        self._reg_slot_idx  = 0
        self._reg_click_idx = 0

        self._run_btns  = {}
        self._stop_btns = {}
        self._name_vars  = {d["key"]: [] for d in DUNGEONS}
        self._click_vars = {d["key"]: [] for d in DUNGEONS}
        self._click_btns = {d["key"]: [] for d in DUNGEONS}
        self._slot_canvases = []
        self._plus_btns = {d["key"]: [] for d in DUNGEONS}   # 슬롯별 + 선택 버튼
        self._sel_order = {d["key"]: [] for d in DUNGEONS}   # +로 고른 슬롯 (누른 순서)
        self._rep_vars  = {d["key"]: [] for d in DUNGEONS}   # ⏰ 드롭다운 표시 변수
        self._numsel    = {}                                 # 번호 지정 일괄 입력칸
        self._repeat_left = {}                               # (key,idx) → 남은 반복 횟수

        self._auto_run = len(sys.argv) > 2 and sys.argv[2] == "--run"
        # --slots 1,7,14 : 그 슬롯들만 웨이브(번갈아)로 한 번에 실행
        self._auto_slots = None
        if "--slots" in sys.argv:
            try:
                raw = sys.argv[sys.argv.index("--slots") + 1]
                self._auto_slots = [int(x) - 1 for x in raw.split(",") if x.strip()]
                self._auto_run = True
            except Exception:
                self._auto_slots = None
        # --slot N : 그 슬롯 하나만 실행 (진단·테스트용)
        self._auto_slot = None
        if "--slot" in sys.argv:
            try:
                self._auto_slot = int(sys.argv[sys.argv.index("--slot") + 1]) - 1
                self._auto_run  = True
            except Exception:
                self._auto_slot = None

        self._build_ui()
        # 조작 감지 — 3분 무조작이면 메인런처 앞(클라 뒤)으로 물러남
        self._last_active = time.time()
        def _bump(e=None):
            self._last_active = time.time()
        for _sq in ("<Button>", "<Key>", "<Motion>"):
            self.bind_all(_sq, _bump, add="+")
        self.after(30000, self._idle_back_tick)
        self._repeat_next = {}
        # (2026-08-09) 슬롯 반복(2시간 N회)은 이제 '메인런처'가 관리한다 —
        # 이 창 안에서 돌리면 창을 닫는 순간 반복이 통째로 죽어버려서.
        # 여기서는 타이머를 돌리지 않는다 (⏰ 설정값만 저장하는 역할).
        self.after(1000, self._lock_tick)      # 실행 중 잠금 파일 갱신
        self.after(300, self._scroll_all_to_bottom)
        self.after(80, self._fit_width)
        if self._auto_run and self._focus_idx is not None:
            # 런처 ▶ 실행: 창을 아예 띄우지 않고 바로 실행 (과거섬처럼)
            # 창을 띄우되 바로 '메인런처 앞(클라 뒤)'으로 보낸다
            try:
                self.after(200, self._send_behind_main)
            except Exception:
                pass
            key = self._dungeons_to_show[0]["key"]
            if self._auto_slots:
                self.after(500, lambda: self._test_sel(key, self._auto_slots))
            elif self._auto_slot is not None:
                self.after(500, lambda: self._test(key, self._auto_slot))
            else:
                self.after(500, lambda: self._start(key))

    def _fit_width(self):
        # 내용 크기에 맞게 가로+세로 모두 조정 (셀에 딱 맞춤 — 길쭉한 빈 공간 제거)
        # 잊혀진섬 단독 창은 사용자 지정 크기 고정 — 자동 맞춤이 덮어쓰지 않음
        if getattr(self, "_fixed_geometry", None):
            self.geometry(self._fixed_geometry)
            return
        self.update_idletasks()
        nw = self.winfo_reqwidth() + 10
        nh = self.winfo_reqheight() + 8
        self.geometry(f"{nw}x{nh}")

    def _build_ui(self):
        # 상단 타이틀
        hdr = tk.Frame(self, bg="#2c3e50"); hdr.pack(fill="x")
        tk.Label(hdr, text="🏝  리니지M 섬/던전 실행기",
                 font=("맑은 고딕", 13, "bold"), fg="white", bg="#2c3e50",
                 pady=8).pack(side="left", padx=12)

        # 상태바
        self._status = tk.StringVar(value="버튼을 선택해 실행하세요")
        tk.Label(self, textvariable=self._status, font=("맑은 고딕", 8),
                 fg="#555", anchor="w").pack(fill="x", padx=10, pady=4)
        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=8)

        # 컬럼 패널
        body = tk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)

        _stretch = bool(getattr(self, "_fixed_geometry", None))
        for d in self._dungeons_to_show:
            col = tk.Frame(body, bd=2, relief="groove")
            if _stretch:
                # 단독(잊혀진섬) 모드: 컬럼이 창 폭을 꽉 채움 — 빈 옆공간 제거
                col.pack(side="left", padx=4, pady=2, fill="both", expand=True)
            else:
                col.pack(side="left", padx=4, pady=2, anchor="n")
            self._build_col(col, d)

        # 오른쪽 카운트 패널 (전체 모드에서만)
        if self._focus_idx is None:
            cnt_col = tk.Frame(body, bd=2, relief="groove", width=160)
            cnt_col.pack(side="left", fill="both", padx=4, pady=2)
            cnt_col.pack_propagate(False)
            self._build_count_panel(cnt_col)

    def _build_count_panel(self, parent):
        tk.Label(parent, text="📊 오늘 실행 횟수",
                 font=("맑은 고딕", 9, "bold"), fg="#2c3e50",
                 pady=6).pack(fill="x")
        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=4)

        self._total_var = tk.StringVar(value="합계: 0")
        tk.Label(parent, textvariable=self._total_var,
                 font=("맑은 고딕", 10, "bold"), fg="#c0392b",
                 pady=4).pack(fill="x")
        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=4)

        outer = tk.Frame(parent); outer.pack(fill="both", expand=True, padx=2)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._count_vars = []
        for i in range(SLOTS):
            row = tk.Frame(inner); row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 7, "bold"),
                     width=3, anchor="w").pack(side="left")
            cv = tk.StringVar(value="0")
            self._count_vars.append(cv)
            tk.Label(row, textvariable=cv, font=("맑은 고딕", 8),
                     fg="#2980b9", anchor="e", width=4).pack(side="right")

        tk.Button(parent, text="초기화", font=("맑은 고딕", 7),
                  fg="red", command=self._reset_counts).pack(pady=4)

        self._refresh_counts()

    def _refresh_counts(self):
        day = today()
        day_data = self.counts.get(day, {})
        total = 0
        for i in range(SLOTS):
            v = day_data.get(str(i), 0)
            self._count_vars[i].set(str(v))
            total += v
        self._total_var.set(f"합계: {total}")

    def _add_count(self, slot_idx):
        day = today()
        if day not in self.counts:
            self.counts[day] = {}
        key = str(slot_idx)
        self.counts[day][key] = self.counts[day].get(key, 0) + 1
        save_counts(self.counts)
        self.after(0, self._refresh_counts)

    def _reset_counts(self):
        from tkinter import messagebox
        if messagebox.askyesno("초기화", "오늘 카운트를 초기화할까요?"):
            self.counts[today()] = {}
            save_counts(self.counts)
            self._refresh_counts()

    def _scroll_all_to_bottom(self):
        for c in self._slot_canvases:
            c.update_idletasks()
            c.yview_moveto(1.0)

    # 창을 숨기거나 최소화할 때 슬롯 팝업도 같이 숨기고, 복원할 때 같이 되살린다
    # (좌표 등록/테스트 중 팝업이 화면을 가리지 않게)
    def _pop_win(self):
        pop = getattr(self, "_pop", {}) or {}
        w = pop.get("win")
        return w if (w and w.winfo_exists()) else None

    def withdraw(self):
        try:
            w = self._pop_win()
            if w: w.withdraw()
        except Exception:
            pass
        super().withdraw()

    def iconify(self):
        try:
            w = self._pop_win()
            if w: w.withdraw()
        except Exception:
            pass
        super().iconify()

    def deiconify(self):
        super().deiconify()
        try:
            w = self._pop_win()
            if w:
                w.deiconify(); w.lift()
        except Exception:
            pass

    def _build_col(self, parent, d):
        key   = d["key"]
        color = d["color"]

        # 대표 버튼
        tk.Button(parent, text=d["label"],
                  font=("맑은 고딕", 11, "bold"), bg=color, fg="white",
                  activebackground=color, height=3, width=14,
                  command=lambda k=key: self._start(k)
                  ).pack(fill="x", padx=4, pady=(6,2))

        srow = tk.Frame(parent); srow.pack(fill="x", padx=4, pady=(0,2))
        stop_btn = tk.Button(srow, text="■ 멈춤",
                  font=("맑은 고딕", 9, "bold"), bg="#c0392b", fg="white",
                  activebackground="#922b21", height=1,
                  command=self._stop, state="disabled")
        stop_btn.pack(side="left", fill="x", expand=True)
        self._stop_btns[key] = stop_btn
        # 멈춤 절반 실행 버튼 — + 골라놨으면 그것만 순서대로, 아니면 전체 실행
        tk.Button(srow, text="▶ 실행",
                  font=("맑은 고딕", 9, "bold"), bg="#1e8449", fg="white",
                  activebackground="#145a32", height=1,
                  command=lambda k=key: self._start(k)
                  ).pack(side="left", fill="x", expand=True, padx=(2, 0))
        if not _PRECISE_OK:
            self._status.set("⚠ 정밀클릭 미적용 — 마우스를 움직이면 클릭이 어긋날 수 있음 (precise_click.py 확인 필요)")

        tk.Button(parent, text="👁 전체 좌표 보기",
                  font=("맑은 고딕", 8), bg="#566573", fg="white",
                  command=lambda k=key: self._preview_all(k)
                  ).pack(fill="x", padx=4, pady=(0,2))

        # ── 번호 지정 일괄 적용 — 지정한 클릭 번호만 전 슬롯에 복사/삭제 ──
        nb = tk.LabelFrame(parent, text="번호 지정 일괄 (예: 3,7,12-14)",
                           font=("맑은 고딕", 7), fg="#7d6608", padx=3, pady=2)
        nb.pack(fill="x", padx=4, pady=(0, 3))
        r1 = tk.Frame(nb); r1.pack(fill="x")
        tk.Label(r1, text="번호", font=("맑은 고딕", 7)).pack(side="left")
        nv = tk.StringVar(value="")
        tk.Entry(r1, textvariable=nv, font=("맑은 고딕", 8), width=12).pack(side="left", padx=2)
        tk.Label(r1, text="기준", font=("맑은 고딕", 7)).pack(side="left", padx=(4, 0))
        sv = tk.StringVar(value="1")
        tk.Spinbox(r1, from_=1, to=SLOTS, textvariable=sv, width=3,
                   font=("맑은 고딕", 8)).pack(side="left", padx=2)
        self._numsel[key] = {"nums": nv, "src": sv}
        r2 = tk.Frame(nb); r2.pack(fill="x", pady=(2, 0))
        tk.Button(r2, text="📋 전 슬롯에 적용", font=("맑은 고딕", 7, "bold"),
                  bg="#2980b9", fg="white",
                  command=lambda k=key: self._nums_apply(k)).pack(side="left", fill="x", expand=True)
        tk.Button(r2, text="× 번호 삭제", font=("맑은 고딕", 7, "bold"),
                  bg="#c0392b", fg="white",
                  command=lambda k=key: self._nums_delete(k)).pack(side="left", fill="x",
                                                                   expand=True, padx=(3, 0))
        r3 = tk.Frame(nb); r3.pack(fill="x", pady=(3, 0))
        tk.Button(r3, text="⚙ 프리셋 P1~P5 설정 (이름·삭제번호·이동번호)",
                  font=("맑은 고딕", 7, "bold"), bg="#7d6608", fg="white",
                  command=lambda k=key: self._open_preset_win(k)).pack(fill="x")

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        # 슬롯 4×4 그리드 (세로 열우선 — 화면 배치와 동일)
        if not hasattr(self, "_cnt_vars"):
            self._cnt_vars = {}
            self._pop = {}
        if not hasattr(self, "_en_btns"):
            self._en_btns = {}
        self._cnt_vars[key] = []
        self._en_btns[key] = []
        if not hasattr(self, "_cell_name_vars"):
            self._cell_name_vars = {}
        self._cell_name_vars[key] = []
        if not hasattr(self, "_cell_name_ents"):
            self._cell_name_ents = {}
        self._cell_name_ents[key] = []
        _stretch = bool(getattr(self, "_fixed_geometry", None))
        wg = tk.Frame(parent)
        if _stretch:
            wg.pack(padx=2, pady=2, fill="both", expand=True)
            for _c in range(4):
                wg.grid_columnconfigure(_c, weight=1, uniform="slotcol")
        else:
            wg.pack(padx=2, pady=2)
        for i in range(SLOTS):
            r, c = i % 4, i // 4
            cell = tk.Frame(wg, bd=1, relief="groove", padx=2, pady=1)
            cell.grid(row=r, column=c, padx=2, pady=2,
                      sticky="nsew" if _stretch else "n")
            # 슬롯 이름 — 직접 입력, 팝업의 이름과 연동
            _nm = (self.cfg.get(key, [{}] * SLOTS)[i].get("name") or "").strip()
            nvv = tk.StringVar(value="" if _nm == "미등록" else _nm)
            self._cell_name_vars[key].append(nvv)
            ne = tk.Entry(cell, textvariable=nvv, font=("맑은 고딕", 8, "bold"), width=4,
                          justify="center", relief="flat", bg="#f2f2f2",
                          fg=self._preset_color(_nm))
            self._cell_name_ents.setdefault(key, []).append(ne)
            ne.pack(pady=(1, 0), fill="x")   # 셀 폭에 맞춤
            def _sv_name(e=None, k=key, x=i, v=nvv):
                # 붙여넣기 직후 늦게 도착한 FocusOut이 새 이름을 옛 값으로 덮어쓰지 않게
                if time.time() - getattr(self, "_paste_ts", 0) < 1.0:
                    return
                self.cfg[k][x]["name"] = v.get().strip() or "미등록"
                save_cfg(self.cfg)
            ne.bind("<FocusOut>", _sv_name); ne.bind("<Return>", _sv_name)
            # 타이핑할 때마다 즉시 저장 — Enter를 안 눌러도 복사에 반영되게
            nvv.trace_add("write", lambda *_a, f=_sv_name: f())
            # 프리셋 P1~P5 — 이 슬롯에 바로 적용 (이름칸 바로 아래)
            head = tk.Frame(cell); head.pack()
            tk.Label(head, text=f"{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     fg="#555").pack(side="left")
            eb = tk.Button(head, text="ON", font=("맑은 고딕", 6, "bold"), width=3,
                           bg="#27ae60", fg="white", pady=0,
                           command=lambda k=key, x=i: self._toggle_enable(k, x))
            eb.pack(side="left", padx=(3, 0))
            self._en_btns[key].append(eb)
            sv = tk.StringVar(value=f"0/{clicks_for(key)}")
            self._cnt_vars[key].append(sv)
            tk.Button(cell, textvariable=sv, font=("맑은 고딕", 7, "bold"),
                      bg=color, fg="white", width=7,
                      command=lambda k=key, x=i: self._open_slot_pop(k, x)).pack(pady=(1, 0), fill="x")
            r3 = tk.Frame(cell); r3.pack(pady=(1, 0))
            pb = tk.Button(r3, text="+", font=("맑은 고딕", 7, "bold"), width=2,
                           bg="#dfe3e6", fg="#e67e22",
                           command=lambda k=key, x=i: self._toggle_sel(k, x))
            pb.pack(side="left", padx=(0, 1))
            self._plus_btns[key].append(pb)
            tk.Button(r3, text="▶", font=("맑은 고딕", 7), fg="white", bg=color, width=2,
                      command=lambda k=key, x=i: self._test(k, x)).pack(side="left", padx=(0, 1))
            tk.Button(r3, text="👁", font=("맑은 고딕", 7), width=2,
                      bg="#566573", fg="white",
                      command=lambda k=key, x=i: self._preview(k, x)).pack(side="left", padx=(0, 1))
            tk.Button(r3, text="×", font=("맑은 고딕", 7), fg="red", width=2,
                      command=lambda k=key, x=i: self._del(k, x)).pack(side="left")
            r4 = tk.Frame(cell); r4.pack(pady=(1, 0))
            tk.Button(r4, text="복사", font=("맑은 고딕", 7), bg="#2980b9", fg="white", width=2,
                      command=lambda k=key, x=i: self._slot_copy(k, x)).pack(side="left", padx=(0, 1))
            tk.Button(r4, text="붙임", font=("맑은 고딕", 7), bg="#8e44ad", fg="white", width=2,
                      command=lambda k=key, x=i: self._slot_paste(k, x)).pack(side="left")
            # 반복 타이머 — N시간마다 자동 재실행 + 옆에 반복 횟수(1~8회) 제한
            _rh = self.cfg.get(key, [{}]*SLOTS)[i].get("repeat_h") or 0
            _rn = self.cfg.get(key, [{}]*SLOTS)[i].get("repeat_n") or 8
            r5 = tk.Frame(cell); r5.pack(pady=(1, 0))
            rv = tk.StringVar(value=f"⏰{_rh}h" if _rh else "⏰없음")
            rom = tk.OptionMenu(r5, rv, "⏰없음", "⏰1h", "⏰2h", "⏰3h", "⏰4h",
                                command=lambda val, k=key, x=i: self._set_repeat(k, x, val))
            rom.config(font=("맑은 고딕", 6), width=4, pady=0, highlightthickness=0,
                       bg="#34495e", fg="white", activebackground="#2c3e50")
            rom.pack(side="left")
            self._rep_vars[key].append(rv)
            nv = tk.StringVar(value=f"{_rn}회")
            nom = tk.OptionMenu(r5, nv, *[f"{x}회" for x in range(1, 9)],
                                command=lambda val, k=key, x=i: self._set_repeat_n(k, x, val))
            nom.config(font=("맑은 고딕", 6), width=3, pady=0, highlightthickness=0,
                       bg="#7d6608", fg="white", activebackground="#5c4a06")
            nom.pack(side="left", padx=(1, 0))
            # 이 슬롯만 반복 중지 (2시간 6회 등) — 다른 슬롯·전체 실행에는 영향 없음
            tk.Button(r5, text="■", font=("맑은 고딕", 6, "bold"), width=2, pady=0,
                      bg="#c0392b", fg="white",
                      command=lambda k=key, x=i: self._stop_repeat(k, x)
                      ).pack(side="left", padx=(1, 0))

        self._refresh(key)

    def _open_slot_pop(self, key, idx):
        """슬롯 좌표 등록 팝업 — 이름 + 클릭1~6 버튼 + 그룹복사."""
        d = next(x for x in DUNGEONS if x["key"] == key)
        old = self._pop.get("win")
        if old and old.winfo_exists():
            try: old.destroy()
            except Exception: pass
        win = tk.Toplevel(self)
        self._pop = {"win": win, "key": key, "slot": idx, "vars": [], "btns": [],
                     "dir_vars": []}
        win.title(f"{d['label'].replace(chr(10), ' ')} #{idx+1:02d} 좌표 등록")
        win.attributes("-topmost", True)
        slot = self.cfg[key][idx]
        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text=f"#{idx+1:02d}  이름", font=("맑은 고딕", 9, "bold")).pack(side="left")
        nv = tk.StringVar(value=slot.get("name", "미등록"))
        ent = tk.Entry(top, textvariable=nv, font=("맑은 고딕", 9), width=14)
        ent.pack(side="left", padx=6)
        def _sv(e=None):
            self.cfg[key][idx]["name"] = nv.get().strip() or "미등록"
            save_cfg(self.cfg)
        ent.bind("<FocusOut>", _sv); ent.bind("<Return>", _sv)
        tk.Button(top, text="⚙ 프리셋 설정", font=("맑은 고딕", 8, "bold"),
                  bg="#7d6608", fg="white", padx=4,
                  command=lambda k=key: self._open_preset_win(k)).pack(side="left", padx=(8, 0))
        # 프리셋 — 층별로 줄을 나눠 배치 (누르면 이 슬롯에 바로 적용)
        self._build_preset_rows(win, key, idx)
        tk.Label(win, text=f"버튼: [✔등록][×삭제][▶테스트][⏺녹화 — 3초 뒤 녹화, ESC 종료, 저장되면 빨간 ●]  |  [방향]: 이동·⇩끌어내리기  |  'ㅡ'=대기 초(8~10=랜덤, 비우면 {CLICK_INTERVAL})",
                 font=("맑은 고딕", 7), fg="#888").pack()
        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        _n_clicks = clicks_for(key)
        _labels   = labels_for(key)
        coords = slot.get("coords", [None] * _n_clicks)
        # 클릭별 간격 목록 (gap_list[j] = 클릭 j+1 뒤 대기 초, None=기본)
        gl = list(slot.get("gap_list") or [])
        while len(gl) < _n_clicks - 1:
            gl.append(None)
        gap_vars = []
        def _save_gaps(e=None):
            out = []
            for v in gap_vars:
                s = v.get().strip().replace("초", "")
                out.append(s if s else None)   # 문자열 그대로 저장 (숫자·이동 조합)
            self.cfg[key][idx]["gap_list"] = out
            save_cfg(self.cfg)
        self._pop["save_gaps"] = _save_gaps
        # 클릭칸 이름표 — 캐릭/용도별로 구분할 수 있게 직접 수정 가능 (슬롯마다 저장)
        cn = list(slot.get("click_names") or [])
        while len(cn) < _n_clicks:
            cn.append(None)
        name_vars = []
        def _save_click_names(e=None):
            out = []
            for i2, v in enumerate(name_vars):
                s = v.get().strip()
                out.append(None if (not s or s == _labels[i2]) else s)
            self.cfg[key][idx]["click_names"] = out
            save_cfg(self.cfg)
        self._pop["save_names"] = _save_click_names
        # 클릭 대신 방향키 이동으로 쓸 자리 (dirs[j] = [방향, 초] 또는 None)
        dirs = list(slot.get("dirs") or [])
        while len(dirs) < _n_clicks:
            dirs.append(None)
        DIRS = ["ㅡ", "↑", "↓", "←", "→", "↖", "↗", "↙", "↘", "⇩"]   # ⇩=끌어내리기
        dir_vars, sec_vars = [], []
        def _save_dirs(*a):
            out = []
            for dv, sv2 in zip(dir_vars, sec_vars):
                d_ = dv.get()
                if d_ not in ("↑", "↓", "←", "→", "↖", "↗", "↙", "↘", "⇩"):
                    out.append(None)
                else:
                    try:
                        s_ = float(sv2.get())
                    except Exception:
                        s_ = 1.0
                    out.append([d_, s_])
            self.cfg[key][idx]["dirs"] = out
            save_cfg(self.cfg)
        for j in range(_n_clicks):
            cc = tk.Frame(grid); cc.grid(row=j // 6, column=(j % 6) * 2, padx=2, pady=4)
            # 이름표: 클릭해서 직접 수정 (예: 물약, 이동문) — 비우면 기본 '클릭N'
            nv2 = tk.StringVar(value=cn[j] or _labels[j])
            name_vars.append(nv2)
            ne = tk.Entry(cc, textvariable=nv2, font=("맑은 고딕", 7), width=7,
                          justify="center", relief="flat", fg="#2c3e50", bg="#f2f2f2")
            ne.pack()
            ne.bind("<FocusOut>", _save_click_names); ne.bind("<Return>", _save_click_names)
            on = j < len(coords) and coords[j]
            cv = tk.StringVar(value="✔" if on else "✗")
            self._pop["vars"].append(cv)
            brow = tk.Frame(cc); brow.pack()
            b = tk.Button(brow, textvariable=cv, font=("맑은 고딕", 8), width=4, pady=2,
                          bg=d["color"] if on else "#7f8c8d", fg="white",
                          command=lambda k=key, x=idx, c=j: self._reg(k, x, c))
            b.pack(side="left"); self._pop["btns"].append(b)
            tk.Button(brow, text="×", font=("맑은 고딕", 7, "bold"), fg="red", width=1, pady=0,
                      command=lambda k=key, x=idx, c=j: self._del_click(k, x, c)
                      ).pack(side="left", padx=(1, 0))
            tk.Button(brow, text="▶", font=("맑은 고딕", 7), fg="white", bg="#1e8449",
                      width=1, pady=0,
                      command=lambda k=key, x=idx, c=j: self._test_click(k, x, c)
                      ).pack(side="left", padx=(1, 0))
            tk.Button(brow, text="👁", font=("맑은 고딕", 7), width=1, pady=0,
                      bg="#566573", fg="white",
                      command=lambda k=key, x=idx, c=j: self._preview_click(k, x, c)
                      ).pack(side="left", padx=(1, 0))
            # 녹화 버튼 — 좌표 버튼과 같은 크기, 녹화가 저장돼 있으면 빨간 ●
            _has_rec = bool((slot.get("recs") or {}).get(str(j)))
            rb = tk.Button(cc, text="●" if _has_rec else "⏺",
                           font=("맑은 고딕", 8), width=4, pady=2,
                           fg="white", bg="#c0392b" if _has_rec else "#7f8c8d",
                           command=lambda k=key, x=idx, c=j: self._start_record(k, x, c))
            rb.pack()
            self._pop.setdefault("rec_btns", []).append(rb)
            # [방향][초] 선택 — 방향을 고르면 이 자리는 클릭 대신 방향키 이동
            drow = tk.Frame(cc); drow.pack()
            cur = dirs[j]
            dv = tk.StringVar(value=(cur[0] if cur else "ㅡ"))
            sv2 = tk.StringVar(value=(f"{cur[1]:g}" if cur else "1"))
            dir_vars.append(dv); sec_vars.append(sv2)
            self._pop["dir_vars"].append(dv)
            om = tk.OptionMenu(drow, dv, *DIRS, command=lambda *_: _save_dirs())
            om.config(font=("맑은 고딕", 7), width=1, pady=0, highlightthickness=0)
            om.pack(side="left")
            om2 = tk.OptionMenu(drow, sv2, *[str(i) for i in range(1, 11)],
                                command=lambda *_: _save_dirs())
            om2.config(font=("맑은 고딕", 7), width=1, pady=0, highlightthickness=0)
            om2.pack(side="left")
            if j < _n_clicks - 1:
                # 클릭 사이 간격: ㅡ 위에 초 입력 (비우면 기본)
                gc = tk.Frame(grid); gc.grid(row=j // 6, column=(j % 6) * 2 + 1)
                _gv = gl[j]
                v = tk.StringVar(value="" if _gv is None else
                                 (f"{_gv:g}" if isinstance(_gv, (int, float)) else str(_gv)))
                gap_vars.append(v)
                en = tk.Entry(gc, textvariable=v, width=6, justify="center",
                              font=("맑은 고딕", 8))
                en.pack()
                tk.Label(gc, text="ㅡ", font=("맑은 고딕", 8, "bold"), fg="#888").pack()
                en.bind("<FocusOut>", _save_gaps); en.bind("<Return>", _save_gaps)
    # ── 프리셋 P1~P5 — 좌표 목록에서 번호별로 [그대로/삭제/위치변경]을 골라 저장 ──
    # 던전별 기본 프리셋 구성 — (층, [이름들])
    PRESET_LAYOUT = {
        "수금_오만의탑": [("3층", ["기본!!"]),
                          ("5층", ["기본!!", "빨갱이 48%", "빨갱이 82%", "주홍이 48%", "주홍이 82%"]),
                          ("6층", ["기본!!", "주홍이 48%", "주홍이 82%"]),
                          ("7층", ["기본!!", "주홍이 48%", "주홍이 82%"]),
                          ("8층", ["기본!!", "주홍이 48%", "주홍이 82%"])],
        "월요일_잊혀진섬": [("서쪽", ["기본!!", "빨갱이 48%", "빨갱이 82%",
                                      "주홍이 48%", "주홍이 82%"]),
                             ("북쪽", ["기본!!", "빨갱이 48%", "빨갱이 82%",
                                      "주홍이 48%", "주홍이 82%"])],
        "화요일_에카":     [("", ["기본!!", "빨갱이 82%",
                                  "주홍이 48%", "주홍이 82%"])],
    }
    PRESET_DEFAULT = [("", ["주홍이 기본!", "주홍이 48%", "주홍이 82%",
                            "빨갱이 기본!", "빨갱이 48%", "빨갱이 82%"])]

    # 층이 달라도 이름이 같으면 함께 저장할 클릭 번호 (0-based) — 오만의탑 12·13번
    PRESET_SYNC_CLICKS = {"수금_오만의탑": (11, 12)}
    # 이름이 같으면 '모든 클릭 설정'을 함께 저장하는 던전 (잊혀진섬 서쪽↔북쪽)
    PRESET_SYNC_ALL = ("월요일_잊혀진섬",)

    def _preset_layout(self, key):
        return self.PRESET_LAYOUT.get(key, self.PRESET_DEFAULT)

    def _presets(self, key):
        allp = self.cfg.setdefault("_presets", {})
        lst = allp.setdefault(key, [])
        want = [(fl, nm) for fl, names in self._preset_layout(key) for nm in names]
        # 구성이 바뀌었으면(개수/층 정보 없음) 이름·층만 맞춰서 채운다 (설정값은 유지)
        if len(lst) != len(want) or any("floor" not in x for x in lst):
            new = []
            for i, (fl, nm) in enumerate(want):
                old = lst[i] if i < len(lst) else {}
                new.append({"floor": fl, "name": nm, "src": old.get("src", 1),
                            "abs": old.get("abs", False), "items": old.get("items", {})})
            lst = new
            allp[key] = lst
        for pr in lst:                     # 예전 형식(dels/mods) 자동 변환
            if "items" not in pr:
                items = {}
                for n in self._parse_nums(pr.get("dels", ""), clicks_for(key)):
                    items[str(n)] = {"act": "del"}
                for k2, rel in (pr.get("mods") or {}).items():
                    items[str(k2)] = {"act": "mov", "rel": list(rel)}
                pr["items"] = items
        return lst

    def _preset_short(self, key, pi):
        """버튼용 이름 (없으면 P번호)."""
        pr = self._presets(key)[pi]
        nm = (pr.get("name") or "").strip()
        return nm if nm else ("P" + str(pi + 1))

    def _preset_full(self, key, pi):
        """층 + 이름 (슬롯 이름으로 기록할 때 사용)."""
        pr = self._presets(key)[pi]
        fl = (pr.get("floor") or "").strip()
        nm = (pr.get("name") or "").strip() or ("P" + str(pi + 1))
        return (fl + " " + nm).strip()

    @staticmethod
    def _preset_color(name):
        """이름으로 색 배정 — 기본=진회색, 주홍이=보라 계열, 빨갱이=빨강 계열
        (48% < 82% 순으로 점점 밝게)."""
        nm = (name or "").strip()
        if not nm:
            return "#2c3e50"
        if "빨갱이" in nm or "빨갱" in nm:
            if "82" in nm: return "#e74c3c"
            if "48" in nm: return "#c0392b"
            return "#7b241c"
        if "주홍" in nm:
            if "82" in nm: return "#9b59b6"
            if "48" in nm: return "#7d3c98"
            return "#5b2c6f"
        return "#2c3e50"            # 기본!! 등

    def _build_preset_rows(self, parent, key, idx):
        """프리셋 버튼을 층별 박스로 묶어 배치 — 층 제목 아래에 버튼들(많으면 2줄)."""
        wrap = tk.Frame(parent)
        wrap.pack(fill="x", padx=10, pady=(4, 2))
        if not hasattr(self, "_preset_btns"):
            self._preset_btns = {}
        self._preset_btns[key] = []
        pi = 0
        for fl, names in self._preset_layout(key):
            box = tk.LabelFrame(wrap, text=(fl or "프리셋"),
                                font=("맑은 고딕", 9, "bold"), fg="#7d6608",
                                padx=4, pady=3, bd=2, relief="groove")
            box.pack(side="left", padx=4, pady=2, anchor="n")
            per = 3 if len(names) > 3 else len(names)   # 3개 넘으면 2줄로
            rows = []
            for r in range((len(names) + per - 1) // max(per, 1)):
                _r = tk.Frame(box); _r.pack(fill="x")
                rows.append(_r)
            for k2, _nm in enumerate(names):
                _b = tk.Button(rows[k2 // per] if rows else box,
                               text=self._preset_short(key, pi),
                               font=("맑은 고딕", 8, "bold"), width=9,
                               bg=self._preset_color(self._preset_short(key, pi)),
                               fg="white", pady=2,
                               command=lambda k=key, x=idx, q=pi: self._apply_preset(k, x, q))
                _b.pack(side="left", padx=2, pady=1)
                self._preset_btns[key].append(_b)
                pi += 1
        return wrap
    def _preset_label(self, key, pi):
        pr = self._presets(key)[pi]
        n = len(pr.get("items") or {})
        nm = pr.get("name") or ("P" + str(pi + 1))
        return (nm + chr(10) + "(" + str(n) + "개)") if n else nm

    def _open_preset_win(self, key):
        """프리셋 편집 — 좌표 1~N번을 전부 보여주고 번호별로 그대로/삭제/위치변경 선택."""
        old = getattr(self, "_preset_win", None)
        if old and old.winfo_exists():
            try: old.destroy()
            except Exception: pass
        d = next(x for x in DUNGEONS if x["key"] == key)
        win = tk.Toplevel(self); self._preset_win = win
        win.title("프리셋 편집 — " + d["label"].replace(chr(10), " "))
        win.attributes("-topmost", True)
        self._pw = {"key": key, "pi": 0, "items": {}, "cells": [],
                    "name": tk.StringVar(), "src": tk.StringVar(value="1")}
        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10, 4))
        self._pw["tabs"] = []
        tabbox = tk.Frame(win); tabbox.pack(fill="x", padx=10)
        _pi = 0
        for fl, names in self._preset_layout(key):
            _box = tk.LabelFrame(tabbox, text=(fl or "프리셋"),
                                 font=("맑은 고딕", 9, "bold"), fg="#7d6608",
                                 padx=4, pady=3, bd=2, relief="groove")
            _box.pack(side="left", padx=4, pady=2, anchor="n")
            _per = 3 if len(names) > 3 else len(names)
            _rows = []
            for _r in range((len(names) + _per - 1) // max(_per, 1)):
                _f = tk.Frame(_box); _f.pack(fill="x")
                _rows.append(_f)
            for _k, _nm in enumerate(names):
                b = tk.Button(_rows[_k // _per] if _rows else _box,
                              text=self._preset_short(key, _pi),
                              font=("맑은 고딕", 8, "bold"), width=9, pady=2,
                              bg=self._preset_color(self._preset_short(key, _pi)), fg="white",
                              command=lambda x=_pi: self._preset_load(x))
                b.pack(side="left", padx=2, pady=1)
                self._pw["tabs"].append(b)
                _pi += 1
        tk.Label(top, text="이름", font=("맑은 고딕", 9, "bold")).pack(side="left", padx=(12, 2))
        tk.Entry(top, textvariable=self._pw["name"], font=("맑은 고딕", 10), width=16).pack(side="left")
        tk.Label(top, text="기준슬롯", font=("맑은 고딕", 9)).pack(side="left", padx=(10, 2))
        tk.Spinbox(top, from_=1, to=SLOTS, textvariable=self._pw["src"], width=3,
                   font=("맑은 고딕", 9)).pack(side="left")
        _h = ("번호칸을 누르면 [그대로 ↔ 삭제] 전환,  [위치]를 누르면 그 번호를 바꿀 자리를 화면에서 찍습니다." +
              chr(10) + "저장 후 슬롯 좌표 팝업에서 그 프리셋 버튼을 누르면 그 번호들만 바뀝니다 (나머지는 그대로).")
        tk.Label(win, text=_h, font=("맑은 고딕", 8), fg="#555",
                 justify="left").pack(anchor="w", padx=10)
        lg = tk.Frame(win); lg.pack(anchor="w", padx=10, pady=(2, 0))
        tk.Label(lg, text=" 그대로 ", font=("맑은 고딕", 8), bg="#dfe3e6").pack(side="left")
        tk.Label(lg, text=" ✖ 삭제 ", font=("맑은 고딕", 8), bg="#c0392b", fg="white").pack(side="left", padx=4)
        tk.Label(lg, text=" 📍 위치변경 ", font=("맑은 고딕", 8), bg="#f39c12", fg="black").pack(side="left")
        tk.Label(lg, text="  (아래 칸에 찍은 좌표가 표시됩니다)", font=("맑은 고딕", 8), fg="#888").pack(side="left")
        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        for jx in range(clicks_for(key)):
            cell = tk.Frame(grid, bd=1, relief="groove", padx=2, pady=1)
            cell.grid(row=jx // 6, column=jx % 6, padx=3, pady=3, sticky="n")
            tk.Label(cell, text=str(jx + 1), font=("맑은 고딕", 8, "bold"), fg="#555").pack()
            srow = tk.Frame(cell); srow.pack(pady=(1, 0))
            sb = tk.Button(srow, text="그대로", font=("맑은 고딕", 8), width=8,
                           bg="#dfe3e6", command=lambda x=jx: self._preset_toggle(x))
            sb.pack(side="left")
            tk.Button(srow, text="👁", font=("맑은 고딕", 8), width=2,
                      bg="#566573", fg="white",
                      command=lambda x=jx: self._preset_preview(x)).pack(side="left", padx=(2, 0))
            pb = tk.Button(cell, text="위치", font=("맑은 고딕", 8), width=8,
                           bg="#2980b9", fg="white",
                           command=lambda x=jx: self._preset_pick_one(x))
            pb.pack(pady=(1, 0))
            self._pw["cells"].append({"state": sb, "pick": pb})
        bot = tk.Frame(win); bot.pack(pady=(2, 10))
        tk.Button(bot, text="저장", font=("맑은 고딕", 10, "bold"), bg="#1e8449", fg="white",
                  width=10, command=self._preset_store).pack(side="left", padx=4)
        tk.Button(bot, text="전부 그대로", font=("맑은 고딕", 9), bg="#7f8c8d", fg="white",
                  command=self._preset_clear).pack(side="left", padx=4)
        tk.Button(bot, text="닫기", font=("맑은 고딕", 9), command=win.destroy).pack(side="left", padx=4)
        self._preset_load(0)

    def _preset_load(self, pi):
        pw = self._pw; key = pw["key"]
        pr = self._presets(key)[pi]
        pw["pi"] = pi
        pw["items"] = {k2: dict(v) for k2, v in (pr.get("items") or {}).items()}
        pw["name"].set(pr.get("name", ""))
        pw["src"].set(str(pr.get("src", 1)))
        for x, b in enumerate(pw["tabs"]):
            base = self._preset_color(self._preset_short(key, x))
            b.config(bg=base, fg="white",
                     relief="sunken" if x == pi else "raised",
                     bd=4 if x == pi else 1,
                     highlightbackground="#f1c40f")
        self._preset_refresh_cells()

    def _preset_refresh_cells(self):
        pw = self._pw
        for jx, c in enumerate(pw["cells"]):
            it = pw["items"].get(str(jx))
            if not it:                                   # 그대로 — 회색
                c["state"].config(text="그대로", bg="#dfe3e6", fg="black")
                c["pick"].config(text="위치찍기", bg="#95a5a6", fg="white",
                                 relief="raised", bd=1)
            elif it.get("act") == "del":                 # 삭제 — 빨강
                c["state"].config(text="✖ 삭제", bg="#c0392b", fg="white")
                c["pick"].config(text="위치찍기", bg="#95a5a6", fg="white",
                                 relief="raised", bd=1)
            else:                                        # 위치 지정 — 노랑/주황 (한눈에 구분)
                rel = it.get("rel") or [0, 0]
                c["state"].config(text="📍 위치변경", bg="#f39c12", fg="black")
                c["pick"].config(text="✔ " + str(rel[0]) + "," + str(rel[1]),
                                 bg="#f1c40f", fg="black", relief="sunken", bd=3)

    def _preset_preview(self, jx):
        """이 번호가 어디를 클릭하는지 점으로 보여준다.
        위치변경이 지정돼 있으면 그 자리, 아니면 기준 슬롯의 현재 좌표."""
        pw = self._pw
        key = pw["key"]
        try:
            base = int(pw["src"].get()) - 1
        except Exception:
            base = 0
        it = pw["items"].get(str(jx))
        rects = self._client_rects_by_slot()
        pos = None
        if it and it.get("act") == "mov":
            rel = it.get("rel") or [0, 0]
            pos = ([rel[0] + rects[base][0], rel[1] + rects[base][1]]
                   if (rects and not pw.get("abs")) else list(rel))
            src_txt = "프리셋 지정 위치"
        else:
            cs = self.cfg[key][base].get("coords", [])
            pos = cs[jx] if jx < len(cs) else None
            src_txt = "기준 슬롯 #" + str(base + 1) + " 현재 좌표"
        if not pos:
            self._status.set("클릭 " + str(jx + 1) + "번: 보여줄 좌표가 없습니다 (" + src_txt + " 없음)")
            return
        self._status.set("👁 클릭 " + str(jx + 1) + "번 — " + src_txt +
                         " (" + str(pos[0]) + "," + str(pos[1]) + ")")
        _PresetDotOverlay(self, jx + 1, pos, src_txt)

    def _preset_toggle(self, jx):
        pw = self._pw
        cur = pw["items"].get(str(jx))
        if not cur:
            pw["items"][str(jx)] = {"act": "del"}
            self._status.set("클릭 " + str(jx + 1) + " 번 → 삭제")
        else:
            act = cur.get("act")
            pw["items"].pop(str(jx), None)
            self._status.set("클릭 " + str(jx + 1) + " 번 → 그대로"
                             + (" (지정한 위치 해제됨)" if act == "mov" else ""))
        self._preset_refresh_cells()

    def _preset_pick_one(self, jx):
        """이 번호를 바꿀 위치를 화면에서 직접 찍는다 (기준 슬롯 클라 기준으로 저장)."""
        pw = self._pw
        try:
            base = int(pw["src"].get()) - 1
        except Exception:
            base = 0
        self._preset_pick = {"jx": jx, "base": base}
        self._status.set("클릭 " + str(jx + 1) + " 번을 바꿀 위치를 3초 후 화면에서 클릭하세요"
                         + " (기준 슬롯 #" + str(base + 1) + ")")
        self.after(1200, self._open_overlay)   # 창은 그대로 두고 바로 찍기

    def _preset_pick_done(self, x, y):
        pm = self._preset_pick or {}
        self._preset_pick = None
        jx, base = pm.get("jx", 0), pm.get("base", 0)
        rects = self._client_rects_by_slot()
        hit = None
        if rects:
            # 찍은 지점이 실제로 어느 클라이언트 안인지 자동 인식 —
            # '기준슬롯' 번호와 다른 창을 찍어도 좌표가 밀리지 않게
            for si, (l, t, r, b_) in enumerate(rects):
                if l <= x <= r and t <= y <= b_:
                    hit = si
                    break
            if hit is not None:
                base = hit
            rel = [x - rects[base][0], y - rects[base][1]]
            self._pw["abs"] = False
            try:
                self._pw["src"].set(str(base + 1))       # 인식된 슬롯을 기준으로 표시
            except Exception:
                pass
        else:
            rel = [x, y]
            self._pw["abs"] = True
        self._pw["items"][str(jx)] = {"act": "mov", "rel": rel}
        self._preset_refresh_cells()
        try:
            w = getattr(self, "_preset_win", None)
            if w and w.winfo_exists():
                w.deiconify(); w.lift(); w.attributes("-topmost", True)
        except Exception:
            pass
        self._status.set("클릭 " + str(jx + 1) + " 번 위치 지정: (" + str(x) + "," + str(y) + ")"
                         + ("  [클라 #" + str(base + 1) + " 자동 인식]" if hit is not None else "")
                         + "  — 이어서 다른 번호도 지정하세요")

    def _preset_clear(self):
        self._pw["items"] = {}
        self._preset_refresh_cells()
        self._status.set("전부 그대로로 되돌림 — [저장]을 눌러야 반영됩니다")

    def _preset_store(self):
        pw = self._pw; key = pw["key"]; pi = pw["pi"]
        try:
            src = int(pw["src"].get())
        except Exception:
            src = 1
        pres = self._presets(key)
        pres[pi] = {"floor": pres[pi].get("floor", ""),
                    "name": pw["name"].get().strip(), "src": src,
                    "abs": bool(pw.get("abs")),
                    "items": {k2: dict(v) for k2, v in pw["items"].items()}}
        # 같은 이름의 다른 층 프리셋에도 공유 클릭(12·13번)을 함께 저장
        sync = self.PRESET_SYNC_CLICKS.get(key, ())
        sync_all = key in self.PRESET_SYNC_ALL
        synced = []
        if sync or sync_all:
            me = pres[pi]
            for oi, other in enumerate(pres):
                if oi == pi or (other.get("name") or "") != (me.get("name") or ""):
                    continue
                if sync_all:                    # 전체 설정을 그대로 복사
                    other["items"] = {k3: dict(v3) for k3, v3 in me["items"].items()}
                    other["abs"] = me.get("abs", False)
                    other["src"] = me.get("src", 1)
                else:
                    oit = other.setdefault("items", {})
                    for j in sync:
                        if str(j) in me["items"]:
                            oit[str(j)] = dict(me["items"][str(j)])
                        else:
                            oit.pop(str(j), None)
                synced.append(other.get("floor") or ("P" + str(oi + 1)))
        self.cfg["_presets"][key] = pres
        save_cfg(self.cfg)
        self._refresh_preset_btns(key)
        dels = sorted(int(k2) + 1 for k2, v in pw["items"].items() if v.get("act") == "del")
        movs = sorted(int(k2) + 1 for k2, v in pw["items"].items() if v.get("act") == "mov")
        msg = ("저장 — 삭제 " + str(dels or "없음") + " / 이동 " + str(movs or "없음"))
        if synced:
            what = "전체 설정" if sync_all else ("클릭 " + ",".join(str(j + 1) for j in sync) + "번")
            msg += ("   [" + what + "을 " + " ".join(synced) + " '" +
                    (pres[pi].get("name") or "") + "'에도 같이 저장]")
        self._status.set(msg)

    def _refresh_preset_btns(self, key):
        for pi, b in enumerate(getattr(self, "_preset_btns", {}).get(key, [])):
            try:
                if b.winfo_exists():
                    b.config(text=self._preset_label(key, pi))
            except Exception:
                pass
        for row in getattr(self, "_cell_preset_btns", {}).get(key, []):
            for pi, b in enumerate(row):
                try:
                    if b.winfo_exists():
                        b.config(text=self._preset_short(key, pi))
                except Exception:
                    pass

    def _apply_preset(self, key, idx, pi):
        """슬롯 팝업의 프리셋 버튼 — 이 슬롯의 해당 번호만 삭제/이동 (나머지는 그대로)."""
        pr = self._presets(key)[pi]
        items = pr.get("items") or {}
        if not items:
            self._status.set("P" + str(pi + 1) + "에 저장된 내용이 없습니다 — 프리셋 설정에서 만들어주세요")
            return
        nclk = clicks_for(key)
        slot = self.cfg[key][idx]
        cs = slot.setdefault("coords", [])
        while len(cs) < nclk: cs.append(None)
        ds = slot.setdefault("dirs", [])
        rc = slot.setdefault("recs", {})
        rects = self._client_rects_by_slot()
        dels, movs = [], []
        for k2, it in items.items():
            j = int(k2)
            if j >= nclk: continue
            if it.get("act") == "del":
                cs[j] = None
                if j < len(ds): ds[j] = None
                rc.pop(str(j), None)
                dels.append(j + 1)
            else:
                rel = it.get("rel") or [0, 0]
                if rects and not pr.get("abs"):
                    cs[j] = [rel[0] + rects[idx][0], rel[1] + rects[idx][1]]
                else:
                    cs[j] = [rel[0], rel[1]]
                movs.append(j + 1)
        # 어떤 프리셋을 적용했는지 슬롯 이름에 남긴다 (미등록 → 프리셋 이름)
        nm = self._preset_full(key, pi)
        self._paste_ts = time.time()      # 늦게 오는 이름칸 저장이 덮어쓰지 않게
        slot["name"] = nm
        try:
            self._cell_name_vars[key][idx].set(nm)
        except Exception:
            pass
        save_cfg(self.cfg)
        self._refresh(key)
        if self._pop.get("win") and self._pop["win"].winfo_exists() and self._pop.get("slot") == idx:
            self.after(50, lambda: self._open_slot_pop(key, idx))
        self._status.set("#" + str(idx + 1) + " " + nm + " 적용 — 삭제 " +
                         str(sorted(dels) or "없음") + " / 이동 " + str(sorted(movs) or "없음"))

    def _commit_pending_edits(self, key=None, idx=None):
        """열려 있는 좌표 팝업의 미저장 편집(간격·이름표)을 즉시 반영.
        Entry는 FocusOut 때만 저장돼서, 고치자마자 [복사]를 누르면 옛 값이 복사된다."""
        p = getattr(self, "_pop", {}) or {}
        w = p.get("win")
        if not (w and w.winfo_exists()):
            return
        if key is not None and (p.get("key") != key or p.get("slot") != idx):
            return
        for fn_key in ("save_gaps", "save_names"):
            fn = p.get(fn_key)
            if callable(fn):
                try: fn()
                except Exception: pass

    def _client_rects_by_slot(self):
        """리니지M 클라이언트 창 16개를 화면 배치(세로 열우선 01~16) 순서로 반환.
        16개가 정확히 안 보이면 None (위치 보정 불가)."""
        try:
            import win32gui
            wins = []
            def cb(h, _):
                if win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h):
                    t = win32gui.GetWindowText(h)
                    if t.startswith("리니지M l"):
                        l, tp, r, b = win32gui.GetWindowRect(h)
                        if r - l > 100 and b - tp > 100:
                            wins.append((l, tp, r, b))
                return True
            win32gui.EnumWindows(cb, None)
            if len(wins) != 16:
                return None
            wins.sort(key=lambda w: w[0])                     # x(열) 정렬
            cols = [sorted(wins[i*4:(i+1)*4], key=lambda w: w[1]) for i in range(4)]
            return [w for col in cols for w in col]           # 01~16 (열 우선)
        except Exception:
            return None

    def _slot_copy(self, key, idx):
        """슬롯 좌표 복사 — 원하는 슬롯에서 [붙임]으로 붙여넣기 (인형탐험과 동일)."""
        import copy
        self._commit_pending_edits(key, idx)   # 팝업에서 방금 고친 값까지 반영
        slot = self.cfg[key][idx]
        coords = slot.get("coords", [])
        if not (any(coords) or any(d for d in (slot.get("dirs") or []) if d)):
            self._status.set(f"#{idx+1:02d} 복사할 좌표가 없습니다"); return
        # 좌표 + 사이 시간(gap_list) + 방향/⇩(dirs) + 이름표 + 녹화(recs)까지 전부 복사
        self._slot_clip = {"key": key, "src": idx,
                           "name": slot.get("name", "미등록"),
                           "coords": copy.deepcopy(coords),
                           "gap_list": copy.deepcopy(slot.get("gap_list") or []),
                           "dirs": copy.deepcopy(slot.get("dirs") or []),
                           "click_names": copy.deepcopy(slot.get("click_names") or []),
                           "recs": copy.deepcopy(slot.get("recs") or {})}
        self._status.set(f"📋 #{idx+1:02d} 좌표 {sum(1 for c in coords if c)}개 + 시간·방향·이름·녹화 복사됨 — 원하는 슬롯의 [붙임]을 누르세요")

    def _slot_paste(self, key, idx):
        """복사한 좌표 붙여넣기 — 클라이언트 창 위치 자동보정 (인형탐험과 동일)."""
        import copy
        self._commit_pending_edits()      # 열린 팝업의 미저장 편집 먼저 확정
        clip = getattr(self, "_slot_clip", None)
        if not clip or clip.get("key") != key:
            self._status.set("먼저 이 던전의 슬롯에서 [복사]를 누르세요"); return
        shifted = copy.deepcopy(clip["coords"])
        src = clip["src"]; note = ""
        if src != idx:
            rects = self._client_rects_by_slot()
            if rects:
                dx = rects[idx][0] - rects[src][0]
                dy = rects[idx][1] - rects[src][1]
                for c in shifted:
                    if c:
                        c[0] += dx; c[1] += dy
                note = f" — 클라이언트 위치 자동보정 ({dx:+},{dy:+})"
            else:
                note = " — ⚠ 클라이언트 16개 감지 실패, 원본 위치 그대로"
        self._paste_ts = time.time()   # 늦게 오는 이름칸 FocusOut 저장 차단
        self.cfg[key][idx]["coords"] = shifted
        # 슬롯 이름(위에 적은 글씨)도 함께 붙여넣기
        _nm = clip.get("name")
        if _nm and _nm != "미등록":
            self.cfg[key][idx]["name"] = _nm
            try:                       # 화면의 이름칸도 즉시 갱신
                self._cell_name_vars[key][idx].set(_nm)
            except Exception:
                pass
        # 사이 시간·방향·이름표도 그대로 붙여넣기
        self.cfg[key][idx]["gap_list"]    = copy.deepcopy(clip.get("gap_list") or [])
        self.cfg[key][idx]["dirs"]        = copy.deepcopy(clip.get("dirs") or [])
        self.cfg[key][idx]["click_names"] = copy.deepcopy(clip.get("click_names") or [])
        # 녹화도 붙여넣기 — 마우스 이벤트 좌표는 클라 위치 차이만큼 보정
        recs = copy.deepcopy(clip.get("recs") or {})
        if src != idx:
            try:
                rects = self._client_rects_by_slot()
                if rects:
                    rdx = rects[idx][0] - rects[src][0]
                    rdy = rects[idx][1] - rects[src][1]
                    for ev_list in recs.values():
                        for ev in ev_list:
                            if ev[1] in ("md", "mu", "mm"):
                                ev[2] += rdx; ev[3] += rdy
            except Exception:
                pass
        self.cfg[key][idx]["recs"] = recs
        save_cfg(self.cfg)
        self._refresh(key)
        # 늦게 도착하는 FocusOut이 이름을 되돌렸을 수 있으니 잠시 뒤 한 번 더 확정
        def _fix_name(k=key, x=idx, nm=_nm):
            if not nm or nm == "미등록":
                return
            if self.cfg[k][x].get("name") != nm:
                self.cfg[k][x]["name"] = nm
                save_cfg(self.cfg)
            try:
                self._cell_name_vars[k][x].set(nm)
            except Exception:
                pass
        self.after(300, _fix_name)
        self._status.set(f"✔ #{idx+1:02d} 붙여넣기 완료 (시간·방향·이름 포함){note}")

    def _toggle_enable(self, key, idx):
        """슬롯 ON/OFF — OFF 슬롯은 대표(전체) 실행에서 건너뜀 (개별 ▶은 그대로 실행)."""
        s = self.cfg[key][idx]
        s["enabled"] = not s.get("enabled", True)
        save_cfg(self.cfg)
        self._refresh(key)

    def _refresh(self, key):
        slots = self.cfg.get(key, [])
        # 그리드 셀 (좌표 개수)
        for i, sv in enumerate(self._cnt_vars.get(key, [])):
            if i >= len(slots): break
            coords = slots[i].get("coords", [])
            sv.set(f"{sum(1 for c in coords if c)}/{clicks_for(key)}")
        # 슬롯 이름 표시 동기화 (팝업에서 바꾼 이름 반영)
        for i, v in enumerate(getattr(self, "_cell_name_vars", {}).get(key, [])):
            if i >= len(slots): break
            try:
                nm = (slots[i].get("name") or "").strip()
                nm = "" if nm == "미등록" else nm
                if v.get() != nm:
                    v.set(nm)
                ents = getattr(self, "_cell_name_ents", {}).get(key, [])
                if i < len(ents) and ents[i].winfo_exists():
                    ents[i].config(fg=self._preset_color(nm))
            except Exception:
                pass
        # ON/OFF 토글 표시
        for i, eb in enumerate(getattr(self, "_en_btns", {}).get(key, [])):
            if i >= len(slots): break
            try:
                en = slots[i].get("enabled", True)
                eb.config(text="ON" if en else "OFF",
                          bg="#27ae60" if en else "#7f8c8d")
            except Exception:
                pass
        # 열린 등록 팝업 갱신
        pop = getattr(self, "_pop", {})
        win = pop.get("win")
        if win and win.winfo_exists() and pop.get("key") == key:
            i = pop["slot"]
            if i < len(slots):
                d = next(x for x in DUNGEONS if x["key"] == key)
                coords = slots[i].get("coords", [])
                for j, cv in enumerate(pop.get("vars", [])):
                    on = j < len(coords) and coords[j]
                    cv.set("✔" if on else "✗")
                    try:
                        pop["btns"][j].config(bg=d["color"] if on else "#7f8c8d")
                    except Exception:
                        pass

    def _reg_scroll(self, key, slot_idx, sc_var):
        self._status.set(f"3초 후 슬롯#{slot_idx+1} 스크롤 위치에 마우스를 올려두세요!")
        def _capture():
            time.sleep(3)
            x, y = pyautogui.position()
            self.cfg[key][slot_idx]["scroll_coord"] = [x, y]
            save_cfg(self.cfg)
            sc_var.set("✔")
            self._status.set(f"✔ #{slot_idx+1} 스크롤 좌표 등록: ({x},{y})")
        threading.Thread(target=_capture, daemon=True).start()

    def _reg(self, key, slot_idx, click_idx):
        self._reg_key       = key
        self._reg_slot_idx  = slot_idx
        self._reg_click_idx = click_idx
        lbl = labels_for(key)[click_idx]
        self._status.set(f"3초 후 슬롯#{slot_idx+1} [{lbl}] 위치 클릭하세요!")
        self.after(3000, self._open_overlay)

    def _open_overlay(self):
        # 프리셋 좌표 찍기 중에는 창을 숨기지 않는다 (편집을 계속 이어서 하도록)
        if getattr(self, "_preset_pick", None):
            CoordOverlay(self)
            return
        self.withdraw()
        self.after(200, lambda: CoordOverlay(self))

    def on_coord(self, x, y):
        # 프리셋 좌표 찍기 모드 — 슬롯 좌표가 아니라 프리셋에 저장
        pm = getattr(self, "_preset_pick", None)
        if pm:
            self._preset_pick_done(x, y)   # 창을 숨기지 않았으므로 복원도 불필요
            return
        try:
            key = self._reg_key
            si  = self._reg_slot_idx
            ci  = self._reg_click_idx
            coords = list(self.cfg[key][si].get("coords", []))
            while len(coords) <= ci:
                coords.append(None)
            coords[ci] = [x, y]
            self.cfg[key][si]["coords"] = coords
            save_cfg(self.cfg)
            self._refresh(key)
            self._status.set(f"✔ #{si+1} [{labels_for(key)[ci]}] 등록: ({x},{y})")
        except Exception as e:
            self._status.set(f"오류: {e}")
        finally:
            self.deiconify()

    def _copy_from_above(self, key, idx):
        if idx == 0: return
        prev = self.cfg[key][idx - 1]
        src = prev.get("coords", [])
        if not any(src):
            self._status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        import copy
        self.cfg[key][idx]["coords"]      = copy.deepcopy(src)
        _pn = (prev.get("name") or "").strip()
        if _pn and _pn != "미등록":
            self.cfg[key][idx]["name"]    = _pn      # 위 슬롯 이름도 함께 복사
        self.cfg[key][idx]["gap_list"]    = copy.deepcopy(prev.get("gap_list") or [])
        self.cfg[key][idx]["dirs"]        = copy.deepcopy(prev.get("dirs") or [])
        self.cfg[key][idx]["click_names"] = copy.deepcopy(prev.get("click_names") or [])
        self.cfg[key][idx]["recs"]        = copy.deepcopy(prev.get("recs") or {})
        save_cfg(self.cfg)
        self._refresh(key)
        self._status.set(f"✔ #{idx+1} ← #{idx} 좌표·시간·방향·이름 복사 완료")
        coords = self.cfg[key][idx].get("coords", [])
        dots = [(c[0], c[1], n+1, n) for n, c in enumerate(coords) if c and len(c) >= 2]
        if dots:
            self.withdraw()
            self.after(300, lambda: _IslandGroupMoveOverlay(self, key, idx, dots))

    def _copy_to_all(self, key):
        """#01 좌표를 전체 슬롯에 복사 후 순서대로 빠른 클릭 이동 시작"""
        src = self.cfg[key][0].get("coords", [])
        if not any(src):
            self._status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        import copy
        for i in range(1, SLOTS):
            self.cfg[key][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg)
        self._refresh(key)
        self._status.set(f"✔ #01 → 전체 복사 완료. 슬롯마다 클릭1 위치를 클릭하세요.")
        ref = src[0]  # 슬롯1 클릭1 기준점
        self._chain_move(key, 1, ref)

    def _chain_move(self, key, idx, ref):
        if idx >= SLOTS:
            self.deiconify()
            self._status.set("✔ 전체 슬롯 이동 완료!")
            return
        coords = self.cfg[key][idx].get("coords", [])
        if not any(coords):
            self._chain_move(key, idx + 1, ref)
            return
        active = sum(1 for s in self.cfg[key] if any(s.get("coords", [])))
        self.withdraw()
        self.after(150, lambda: _QuickPosOverlay(
            self, key, idx, ref, active,
            on_close=lambda: self._chain_move(key, idx + 1, ref)))

    def _batch_move(self, key):
        d = next(x for x in DUNGEONS if x["key"] == key)
        self._move_key = key
        self._status.set(f"3초 후 [{d['label'].replace(chr(10),' ')}] 이전 기준점을 클릭하세요")
        self.after(3000, lambda: self._open_move_overlay(step=1))

    def _open_move_overlay(self, step):
        self.withdraw()
        self.after(200, lambda: MoveOverlay(self, step))

    def on_move_coord(self, step, x, y):
        if step == 1:
            self._move_from = (x, y)
            self._status.set(f"3초 후 새 위치를 클릭하세요")
            self.after(3000, lambda: self._open_move_overlay(step=2))
        else:
            self.deiconify()
            dx = x - self._move_from[0]
            dy = y - self._move_from[1]
            key = self._move_key
            for slot in self.cfg[key]:
                coords = slot.get("coords", [])
                for i, c in enumerate(coords):
                    if c:
                        coords[i] = [c[0] + dx, c[1] + dy]
            save_cfg(self.cfg)
            self._refresh(key)
            self._status.set(f"✔ 전체 좌표 ({dx:+d}, {dy:+d}) 이동 완료!")

    def _batch_edit(self, key):
        from tkinter import messagebox
        d = next(x for x in DUNGEONS if x["key"] == key)
        ok = messagebox.askyesno(
            "전체 좌표 수정",
            f"[{d['label'].replace(chr(10), ' ')}] 전체 {SLOTS}슬롯 좌표를 새로 등록합니다.\n기존 좌표가 모두 덮어씌워집니다. 계속하시겠습니까?",
            icon="warning"
        )
        if not ok: return
        self._batch_key    = key
        self._batch_coords = [None] * clicks_for(key)
        self._batch_idx    = 0
        self._batch_next()

    def _batch_next(self):
        idx = self._batch_idx
        if idx >= clicks_for(self._batch_key):
            key = self._batch_key
            for slot in self.cfg[key]:
                slot["coords"] = [list(c) if c else None for c in self._batch_coords]
            save_cfg(self.cfg)
            self._refresh(key)
            self._status.set(f"✔ [{key}] 전체 {SLOTS}슬롯 좌표 적용 완료!")
            self.deiconify()
            return
        lbl = labels_for(self._batch_key)[idx]
        self._status.set(f"3초 후 [{lbl}] 위치를 클릭하세요! ({idx+1}/{clicks_for(self._batch_key)})")
        self._reg_key       = self._batch_key
        self._reg_slot_idx  = 0
        self._reg_click_idx = idx
        self.after(3000, self._open_batch_overlay)

    def _open_batch_overlay(self):
        self.withdraw()
        self.after(200, lambda: BatchOverlay(self))

    def on_batch_coord(self, x, y):
        self._batch_coords[self._batch_idx] = [x, y]
        self._batch_idx += 1
        self._batch_next()

    def _preview(self, key, idx):
        all_coords = self.cfg[key][idx].get("coords", [])
        valid = [(ci, c) for ci, c in enumerate(all_coords) if c]
        if not valid:
            self._status.set("등록된 좌표가 없습니다")
            return
        # 점 번호 = 실제 클릭 번호 (클릭1, 클릭2 …) — 중간이 비어도 번호가 안 밀림
        dots = [(c[0], c[1], ci + 1, ci) for ci, c in valid]
        self.withdraw()
        self.after(1000, lambda: _IslandPreviewOverlay(self, key, idx, dots))

    def _preview_click(self, key, idx, ci):
        """좌표 하나만 미리보기 — 그 클릭 위치를 점으로 표시, 드래그하면 수정 저장."""
        coords = self.cfg[key][idx].get("coords", [])
        c = coords[ci] if ci < len(coords) else None
        if not c:
            self._status.set(f"클릭{ci+1}: 등록된 좌표가 없습니다")
            return
        dots = [(c[0], c[1], ci + 1, ci)]
        self.withdraw()
        self.after(600, lambda: _IslandPreviewOverlay(self, key, idx, dots))

    def _preview_all(self, key):
        """이 던전의 16슬롯 전체 좌표 미리보기 — 점 드래그로 개별 수정 저장."""
        dots = []
        for si, s in enumerate(self.cfg.get(key, [])):
            for ci, c in enumerate(s.get("coords", [])):
                if c:
                    dots.append((c[0], c[1], f"{si+1}-{ci+1}", (si, ci)))
        if not dots:
            self._status.set("등록된 좌표가 없습니다")
            return
        self.withdraw()
        self.after(1000, lambda: _IslandPreviewOverlay(self, key, None, dots))

    def _test_click(self, key, idx, ci):
        """좌표 하나만 단독 테스트 — 그 자리의 동작(클릭/방향이동/⇩끌기)을 1회 실행."""
        def run():
            try:
                slot = self.cfg[key][idx]
                name = slot.get("name", f"#{idx+1}")
                coords = slot.get("coords", [])
                dirs = slot.get("dirs") or []
                c = coords[ci] if ci < len(coords) else None
                d_ = dirs[ci] if ci < len(dirs) else None
                cn = slot.get("click_names") or []
                lbl = (cn[ci] if ci < len(cn) and cn[ci] else labels_for(key)[ci])
                time.sleep(0.3)
                rec = (slot.get("recs") or {}).get(str(ci))
                if d_ and d_[0] == "⏺":
                    d_ = None
                # 방향 이동/녹화 테스트는 키 입력이라 그 슬롯의 클라를 먼저 포커스
                if (d_ and d_[0] != "⇩") or rec:
                    self._focus_client_for_slot(idx)
                if rec and not (d_ or c):
                    self._play_events(rec, name)
                    self._status.set(f"✔ [{name}] {lbl} 녹화 재생 완료"); return
                if d_ and d_[0] == "⇩":
                    if not c:
                        self._status.set(f"{lbl}: ⇩는 좌표 등록이 필요합니다"); return
                    dist = max(30, int(float(d_[1]) * 30))
                    sx, sy = c
                    self._status.set(f"🖱 [{name}] {lbl} 끌어내리기 {dist}px 테스트...")
                    pyautogui.mouseDown(sx, sy); time.sleep(0.08)
                    for st in range(1, 7):
                        pyautogui.moveTo(sx, sy + int(dist * st / 6)); time.sleep(0.02)
                    pyautogui.mouseUp(sx, sy + dist)
                elif d_:
                    self._hold_arrow(d_[0], float(d_[1]), name)
                elif c:
                    self._status.set(f"🏝 [{name}] {lbl} 클릭 테스트...")
                    pyautogui.click(*c)
                else:
                    self._status.set(f"{lbl}: 등록된 좌표/동작이 없습니다"); return
                if rec and not self._stop_flag:
                    self._play_events(rec, name)   # 클릭/이동 후 녹화도 이어서 재생
                self._status.set(f"✔ [{name}] {lbl} 테스트 완료")
            except Exception as e:
                self._status.set(f"테스트 오류: {e}")
        # 단일 좌표 테스트는 금방 끝나므로 창을 최소화하지 않고 그대로 실행
        self._stop_flag = False
        threading.Thread(target=run, daemon=True).start()

    def _del_click(self, key, idx, ci):
        """좌표 하나만 삭제 — 실행 때 그 자리는 건너뛰고 다음 좌표부터 진행."""
        slot = self.cfg[key][idx]
        coords = slot.get("coords", [])
        if ci < len(coords):
            coords[ci] = None
            slot["coords"] = coords
        dirs = slot.get("dirs") or []
        if ci < len(dirs) and dirs[ci]:
            dirs[ci] = None
            slot["dirs"] = dirs
        recs = slot.get("recs") or {}
        if str(ci) in recs:
            del recs[str(ci)]
            slot["recs"] = recs
        save_cfg(self.cfg)
        self._refresh(key)
        # 열려 있는 팝업의 방향 드롭다운·녹화 버튼도 초기화 표시
        pop = getattr(self, "_pop", {}) or {}
        if (pop.get("win") and pop["win"].winfo_exists()
                and pop.get("key") == key and pop.get("slot") == idx):
            dvs = pop.get("dir_vars") or []
            if ci < len(dvs):
                dvs[ci].set("ㅡ")
            rbs = pop.get("rec_btns") or []
            if ci < len(rbs):
                try:
                    rbs[ci].config(text="⏺", bg="#7f8c8d")
                except Exception:
                    pass
        self._status.set(f"#{idx+1} {labels_for(key)[ci]} 삭제 — 좌표·방향·녹화 모두 초기화")

    def _del(self, key, idx):
        from tkinter import messagebox
        if not messagebox.askyesno("삭제 확인", f"#{idx+1} 슬롯 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg[key][idx] = {"name": "미등록", "coords": [None]*clicks_for(key)}
        save_cfg(self.cfg); self._refresh(key)

    def _minimize_claude(self):
        # 클로드 창(항상 위)이 클릭을 가리지 않게 최소화
        try:
            import win32gui, win32con
            def _do(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Claude" in title and win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            win32gui.EnumWindows(_do, None)
        except Exception:
            pass

    @staticmethod
    def _repeat_delay(h):
        """반복 주기(초) — 매번 랜덤 여유를 더해 실행 시각이 겹치지 않게.
        1h→1:01~1:07, 2h→2:02~2:07, 3h→3:02~3:06, 4h→4:02~4:07 랜덤."""
        extra = {1: (1, 7), 2: (2, 7), 3: (2, 6), 4: (2, 7)}.get(h, (1, 7))
        return h * 3600 + random.uniform(extra[0], extra[1]) * 60

    def _set_repeat(self, key, idx, val):
        """슬롯 반복 타이머 설정 — ⏰없음/1h/2h/3h/4h (매 실행 랜덤 여유분)."""
        h = {"⏰없음": 0, "⏰1h": 1, "⏰2h": 2, "⏰3h": 3, "⏰4h": 4}.get(val, 0)
        self.cfg[key][idx]["repeat_h"] = h
        save_cfg(self.cfg)
        if not hasattr(self, "_repeat_next"):
            self._repeat_next = {}
        if h:
            self._repeat_next[(key, idx)] = time.time() + self._repeat_delay(h)
            n = self.cfg[key][idx].get("repeat_n") or 8
            self._repeat_left[(key, idx)] = n
            self._status.set(f"⏰ #{idx+1}: 약 {h}시간마다 자동 재실행 × {n}회 — 실행기가 켜져 있는 동안")
        else:
            self._repeat_next.pop((key, idx), None)
            self._repeat_left.pop((key, idx), None)
            self._status.set(f"#{idx+1}: 반복 끔")

    def _set_repeat_n(self, key, idx, val):
        """슬롯 반복 횟수 제한 — 1~8회 (다 채우면 반복 자동 종료)."""
        try:
            n = int(str(val).replace("회", ""))
        except Exception:
            n = 8
        self.cfg[key][idx]["repeat_n"] = n
        save_cfg(self.cfg)
        self._repeat_left[(key, idx)] = n   # 남은 횟수도 새로 시작
        self._status.set(f"#{idx+1}: 반복 횟수 {n}회로 설정")

    def _rlog(self, msg):
        """반복 실행 기록 — 나중에 무슨 일이 있었는지 추적용."""
        try:
            import datetime as _dt
            d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "repeat_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"[{_dt.datetime.now():%m-%d %H:%M:%S}] {msg}" + chr(10))
        except Exception:
            pass

    def _stop_repeat(self, key, idx):
        """이 슬롯의 반복(⏰)만 중지 — 예약된 다음 실행을 취소한다."""
        self.cfg[key][idx]["repeat_h"] = 0
        save_cfg(self.cfg)
        self._repeat_next.pop((key, idx), None)
        self._repeat_left.pop((key, idx), None)
        try:
            self._rep_vars[key][idx].set("⏰없음")
        except Exception:
            pass
        self._status.set("■ #" + str(idx + 1) + " 반복 중지 — 이 슬롯은 더 이상 자동 실행되지 않습니다")
        self._rlog(key + " #" + str(idx + 1) + " 반복 수동 중지")

    def _repeat_tick(self):
        """반복 타이머 — 시간이 된 슬롯을 '한 번에 하나씩' 순서대로 실행한다.
        (예전엔 같은 틱에서 여러 슬롯을 동시에 띄워 클릭이 충돌하고 일부가 누락됐다)"""
        nxt_ms = 15000
        try:
            if not hasattr(self, "_repeat_next"):
                self._repeat_next = {}
            now = time.time()
            due = []                       # 실행할 차례가 된 슬롯들
            for d in DUNGEONS:
                key = d["key"]
                for i, s in enumerate(self.cfg.get(key, [])):
                    h = s.get("repeat_h") or 0
                    if not h:
                        self._repeat_next.pop((key, i), None)
                        self._repeat_left.pop((key, i), None)
                        continue
                    nxt = self._repeat_next.get((key, i))
                    if nxt is None:
                        self._repeat_next[(key, i)] = now + self._repeat_delay(h)
                    elif now >= nxt:
                        due.append((nxt, key, i, h, s))
            if due:
                # 실행 중이면 아무것도 시작하지 않고 짧게 재확인 (차례는 그대로 유지)
                if getattr(self, "_slot_running", False) or getattr(self, "_repeat_busy", False):
                    return
                due.sort()                 # 가장 오래 밀린 것부터
                _, key, i, h, s = due[0]
                left = self._repeat_left.get((key, i))
                if left is None:
                    left = s.get("repeat_n") or 8
                left -= 1
                if left <= 0:
                    self._repeat_left.pop((key, i), None)
                    self._repeat_next.pop((key, i), None)
                    self.cfg[key][i]["repeat_h"] = 0
                    save_cfg(self.cfg)
                    try:
                        self._rep_vars[key][i].set("⏰없음")
                    except Exception:
                        pass
                    self._status.set(f"⏰ #{i+1} 반복 {s.get('repeat_n') or 8}회 완료 — 마지막 실행")
                    self._rlog(f"{key} #{i+1:02d} 마지막 회차 실행 (반복 종료)")
                else:
                    self._repeat_left[(key, i)] = left
                    self._repeat_next[(key, i)] = time.time() + self._repeat_delay(h)
                    self._status.set(f"⏰ #{i+1} {h}시간 반복 자동 실행 (남은 {left}회, "
                                     f"대기 {len(due)-1}개)")
                    self._rlog(f"{key} #{i+1:02d} 실행 (남은 {left}회, 대기 {len(due)-1}개)")
                self._repeat_busy = True          # 스레드 시작 전에 먼저 잠금 (경합 방지)
                self._test(key, i)
                nxt_ms = 5000                      # 남은 대기분을 빨리 이어서
            elif self._repeat_next:
                nxt_ms = 15000
        except Exception as e:
            self._rlog(f"반복 오류: {e!r}")
        self.after(nxt_ms, self._repeat_tick)
    @staticmethod
    def _lock_path():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "island_running.lock")

    def _lock_tick(self):
        """실행 중인 동안 1초마다 잠금 파일을 갱신 — 런처가 이걸 보고
        '아직 돌고 있다'를 판단한다 (프로세스 핸들만 믿으면 놓치는 경우가 있어서)."""
        try:
            if getattr(self, "_slot_running", False):
                with open(self._lock_path(), "w", encoding="utf-8") as f:
                    f.write(f"{os.getpid()} {time.time():.0f}")
            else:
                try: os.remove(self._lock_path())
                except FileNotFoundError: pass
        except Exception:
            pass
        self.after(1000, self._lock_tick)

    def _test_sel(self, key, sel):
        """고른 슬롯들을 웨이브(번갈아)로 한 번에 — 반복 차례가 여러 개일 때 쓴다."""
        self._slot_running = True
        self._send_behind_main()
        self.iconify()
        self._minimize_claude()
        threading.Thread(target=self._run, args=(key,),
                         kwargs={"sel_list": list(sel)}, daemon=True).start()

    def _test(self, key, idx):
        self._slot_running = True          # 스레드가 뜨기 전에 먼저 잠가 중복 실행 차단
        # (2026-08-09) 슬롯 개별 실행에서도 메인런처를 맨 뒤로 내린다 —
        # 예전엔 이 창만 최소화해서 메인런처가 앞에 그대로 남아 클릭을 가렸다
        self._send_behind_main()
        self.iconify()
        self._minimize_claude()
        threading.Thread(target=self._run, args=(key, idx), daemon=True).start()

    def _send_behind_main(self):
        """이 창을 '메인런처 바로 앞'에 배치 — 리니지M 클라이언트 뒤, 메인런처 위.
        최소화하지 않으므로 개별 실행을 이어서 누르기 편하다."""
        try:
            import win32gui, win32con
            main  = win32gui.FindWindow(None, "리니지M 자동 실행")
            flags = (win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            if main:
                # 메인런처를 먼저 맨 뒤로 (이 창 처리가 실패해도 메인은 확실히 내려간다)
                win32gui.SetWindowPos(main, win32con.HWND_BOTTOM, 0, 0, 0, 0, flags)
            self.update_idletasks()
            me = self.winfo_id()
            try:
                me = win32gui.GetParent(me) or me      # 실제 최상위 창 핸들
            except Exception:
                pass
            if main:
                # 메인런처 바로 위(앞)에 이 창을 놓는다
                win32gui.SetWindowPos(me, main, 0, 0, 0, 0, flags)
            else:
                win32gui.SetWindowPos(me, win32con.HWND_BOTTOM, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def _idle_back_tick(self):
        """3분 넘게 조작이 없으면 스스로 메인런처 앞(=클라 뒤)으로 물러난다."""
        try:
            if (not getattr(self, "_slot_running", False)
                    and time.time() - getattr(self, "_last_active", 0) > 180
                    and self.state() == "normal"):
                self._send_behind_main()
        except Exception:
            pass
        self.after(30000, self._idle_back_tick)

    def _start(self, key):
        # +로 고른 슬롯이 있으면 그것만 누른 순서대로, 없으면 전체 실행
        sel = list(self._sel_order.get(key, []))
        self._stop_flag  = False
        self._active_key = key
        for k, btn in self._stop_btns.items():
            btn.config(state="normal" if k == key else "disabled")
        # 창은 켜두되 '메인런처 바로 앞(클라 뒤)'으로 물러난다 (최소화 안 함)
        self._send_behind_main()
        self._minimize_claude()
        threading.Thread(target=self._run, args=(key,),
                         kwargs={"sel_list": sel or None}, daemon=True).start()

    # ── + 선택: 누르면 담기(누른 순서 번호 표시), 다시 누르면 빼기 ──
    def _toggle_sel(self, key, idx):
        sel = self._sel_order.setdefault(key, [])
        if idx in sel:
            sel.remove(idx)
        else:
            sel.append(idx)
        self._refresh_sel(key)
        n = len(sel)
        self._status.set(f"＋ {n}개 선택됨 — 실행 누르면 순서대로 실행" if n else "＋ 선택 없음 — 실행 누르면 전체 실행")

    def _refresh_sel(self, key):
        sel = self._sel_order.get(key, [])
        for i, b in enumerate(self._plus_btns.get(key, [])):
            try:
                if i in sel:
                    b.config(text=str(sel.index(i) + 1), bg="#e67e22", fg="white")
                else:
                    b.config(text="+", bg="#dfe3e6", fg="#e67e22")
            except Exception:
                pass

    def _focus_client_for_slot(self, si):
        """슬롯 번호(화면 배치 01~16 열우선)의 클라 창을 포커스 — 키 입력이 게임으로 가게."""
        try:
            import win32gui, ctypes
            wins = []
            def cb(h, _):
                if win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h):
                    t = win32gui.GetWindowText(h)
                    if t.startswith("리니지M l"):
                        l, tp, r, b = win32gui.GetWindowRect(h)
                        if r - l > 100 and b - tp > 100:
                            wins.append((h, l, tp))
                return True
            win32gui.EnumWindows(cb, None)
            if len(wins) != 16:
                return False
            wins.sort(key=lambda w: w[1])
            cols = [sorted(wins[i*4:(i+1)*4], key=lambda w: w[2]) for i in range(4)]
            hs = [w[0] for col in cols for w in col]
            if si >= len(hs):
                return False
            u = ctypes.windll.user32
            u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)   # ALT 탭핑
            win32gui.SetForegroundWindow(hs[si])
            time.sleep(0.3)
            return True
        except Exception:
            return False

    # ── 녹화/재생 (⏺) — 사용자의 마우스·방향키 입력을 그대로 담았다가 재생 ──
    def _start_record(self, key, idx, ci):
        """⏺ 버튼: 3초 뒤부터 마우스(클릭·드래그)와 방향키를 녹화, ESC로 종료.
        녹화 중에는 화면 상단에 빨간 표시줄이 떠서 상태를 보여준다."""
        # 항상 위 녹화 표시줄 — 창을 숨겨도 이건 보임
        ind = tk.Toplevel(self)
        ind.overrideredirect(True)
        ind.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        ind.geometry(f"440x44+{(sw - 440) // 2}+8")
        ind.configure(bg="#7b241c")
        iv = tk.StringVar(value="⏺ 3초 후 녹화 시작...")
        tk.Label(ind, textvariable=iv, bg="#7b241c", fg="white",
                 font=("맑은 고딕", 12, "bold")).pack(expand=True, fill="both")

        def set_iv(t):
            try:
                self.after(0, iv.set, t)
            except Exception:
                pass

        def close_ind():
            try:
                self.after(0, ind.destroy)
            except Exception:
                pass

        def rec():
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            for n in (3, 2, 1):
                set_iv(f"⏺ {n}초 후 녹화 시작 — 준비하세요")
                time.sleep(1)
            set_iv("🔴 녹화 중! (최대 5분) 마우스 클릭·드래그, WASD·방향키 기록 — ESC로 종료")
            events = []
            t0 = time.time()
            # 기록 대상 키: 방향키 + WASD (이 게임 이동키)
            ARROWS = {0x25: 1, 0x26: 1, 0x27: 1, 0x28: 1,
                      0x57: 1, 0x41: 1, 0x53: 1, 0x44: 1}
            prev_btn = False
            prev_keys = {vk: False for vk in ARROWS}
            last_mm = 0.0
            pt = wintypes.POINT()
            while time.time() - t0 < 300:   # 최대 5분 (예전 60초 → 연장)
                if u.GetAsyncKeyState(0x1B) & 0x8000:   # ESC
                    break
                t = round(time.time() - t0, 3)
                u.GetCursorPos(ctypes.byref(pt))
                btn = bool(u.GetAsyncKeyState(0x01) & 0x8000)
                if btn != prev_btn:
                    events.append([t, "md" if btn else "mu", pt.x, pt.y])
                    prev_btn = btn
                elif btn and t - last_mm >= 0.03:
                    events.append([t, "mm", pt.x, pt.y]); last_mm = t
                for vk in ARROWS:
                    k = bool(u.GetAsyncKeyState(vk) & 0x8000)
                    if k != prev_keys[vk]:
                        events.append([t, "kd" if k else "ku", vk])
                        prev_keys[vk] = k
                time.sleep(0.01)
            # 안 떼고 끝난 입력 정리
            tend = round(time.time() - t0, 3)
            if prev_btn:
                u.GetCursorPos(ctypes.byref(pt))
                events.append([tend, "mu", pt.x, pt.y])
            for vk, on in prev_keys.items():
                if on:
                    events.append([tend, "ku", vk])
            close_ind()
            if not events:
                # 빈 녹화는 저장하지 않음 — 헷갈림 방지
                self.after(0, self.deiconify)
                self._status.set("⚠ 녹화된 동작이 없어 저장 안 함 — 녹화 중에 마우스 클릭·드래그나 방향키를 써야 기록됩니다")
                return
            slot = self.cfg[key][idx]
            recs = slot.get("recs") or {}
            recs[str(ci)] = events
            slot["recs"] = recs
            save_cfg(self.cfg)
            dur = events[-1][0] if events else 0
            def _upd():
                self.deiconify()
                pop = getattr(self, "_pop", {}) or {}
                if pop.get("key") == key and pop.get("slot") == idx:
                    btns = pop.get("rec_btns") or []
                    if ci < len(btns):
                        try:
                            btns[ci].config(text="●", bg="#c0392b")
                        except Exception:
                            pass
            self.after(0, _upd)
            self._status.set(f"✔ 녹화 저장 ({dur:.1f}초, 동작 {len(events)}개) — 실행 때 이 자리에서 재생됩니다")
        self.withdraw()
        threading.Thread(target=rec, daemon=True).start()

    def _play_events(self, events, name):
        """녹화 재생 — 저장된 타이밍 그대로 마우스/이동키(WASD·방향키) 입력."""
        SCAN = {0x26: 0x48, 0x28: 0x50, 0x25: 0x4B, 0x27: 0x4D,
                0x57: 0x11, 0x41: 0x1E, 0x53: 0x1F, 0x44: 0x20}
        self._status.set(f"▶ [{name}] 녹화 재생 중... ({(events[-1][0] if events else 0):.1f}초)")
        t0 = time.time()
        held = set()
        try:
            for ev in events:
                if self._stop_flag: break
                while time.time() - t0 < ev[0]:
                    if self._stop_flag: break
                    time.sleep(0.005)
                typ = ev[1]
                if typ == "mm":
                    pyautogui.moveTo(ev[2], ev[3])
                elif typ == "md":
                    pyautogui.mouseDown(ev[2], ev[3])
                elif typ == "mu":
                    pyautogui.mouseUp(ev[2], ev[3])
                elif typ == "kd":
                    _send_scan_key([SCAN[ev[2]]], True); held.add(ev[2])
                elif typ == "ku":
                    _send_scan_key([SCAN[ev[2]]], False); held.discard(ev[2])
        finally:
            for vk in list(held):                       # 중단 시 눌린 키 해제
                _send_scan_key([SCAN[vk]], False)
        time.sleep(0.15)

    def _hold_arrow(self, word, sec, name):
        """방향키를 sec초 동안 눌러 이동 — 대각선(↖↗↙↘)은 두 키 동시 홀드.
        스캔코드 SendInput 방식이라 게임(DirectInput)도 인식. 직전 클릭으로 포커스된 클라가 받는다."""
        # 이 게임은 WASD로만 이동 — 방향 선택을 WASD 스캔코드로 보낸다
        W, A, S, D = 0x11, 0x1E, 0x1F, 0x20
        SCS = {"상": [W], "위": [W], "↑": [W],
               "하": [S], "아": [S], "↓": [S],
               "좌": [A], "왼": [A], "←": [A],
               "우": [D], "오": [D], "→": [D],
               "↖": [W, A], "↗": [W, D],
               "↙": [S, A], "↘": [S, D]}
        scs = SCS.get(word) or SCS.get(word[0])
        if not scs or sec <= 0:
            return
        self._status.set(f"🏃 [{name}] {word} {sec}초 이동...")
        _send_scan_key(scs, True)
        t0 = time.time()
        try:
            # 홀드 유지 — 일부 게임은 반복 입력을 봐야 계속 걷기 때문에 0.4초마다 다시 눌러줌
            while time.time() - t0 < sec:
                if self._stop_flag: break
                time.sleep(0.4)
                if time.time() - t0 < sec and not self._stop_flag:
                    _send_scan_key(scs, True)
        finally:
            _send_scan_key(scs, False)
        time.sleep(0.15)

    def _do_moves(self, spec, name):
        """'하3 우1.5 상2 좌0.5' — 방향키를 순서대로 지정 초만큼 눌러 이동."""
        import re
        for m in re.finditer(r"(상|위|하|아래|좌|왼쪽?|우|오른쪽?)\s*:?\s*([0-9]+(?:\.[0-9]+)?)", spec):
            if self._stop_flag: break
            self._hold_arrow(m.group(1), float(m.group(2)), name)

    def _do_gap_spec(self, spec, name):
        """클릭 사이 'ㅡ' 칸 해석 — 숫자=대기 초, "8~10"=그 사이 랜덤 초,
        방향+숫자=방향키 이동, 적힌 순서대로. 해석할 게 없으면 기본 간격."""
        import re
        acted = False
        pat = (r"(상|위|하|아래|좌|왼쪽?|우|오른쪽?)?\s*:?\s*"
               r"([0-9]+(?:\.[0-9]+)?)(?:\s*[~\-]\s*([0-9]+(?:\.[0-9]+)?))?")
        for m in re.finditer(pat, spec):
            if self._stop_flag: break
            word = m.group(1)
            a = float(m.group(2))
            b = m.group(3)
            sec = a if b is None else random.uniform(min(a, float(b)), max(a, float(b)))
            acted = True
            if word:
                self._hold_arrow(word, sec, name)
            else:
                sec *= random.uniform(1.10, 1.25) * slow_factor()  # 10~25% 랜덤 + 전체 12~17% 지연
                if b is not None:
                    self._status.set(f"⏱ [{name}] {sec:.1f}초 대기 (랜덤 {m.group(2)}~{b} +α)...")
                t0 = time.time()
                while time.time() - t0 < sec:
                    if self._stop_flag: break
                    time.sleep(0.05)
        if not acted:
            time.sleep(CLICK_INTERVAL * random.uniform(1.10, 1.25) * slow_factor())

    def _stop(self):
        self._stop_flag = True
        self._status.set("멈추는 중...")
        for btn in self._stop_btns.values():
            btn.config(state="disabled")

    # ── 웨이브(번갈아) 실행 — 클릭1을 전 슬롯에 쫙 → 클릭2 쫙 … (과거섬식) ──
    WAVE_KEYS = ("수금_오만의탑", "토요일_악몽의섬")

    def _do_one_click(self, key, si, slot, j, lbl, move_set, tag=""):
        """슬롯의 j번째 자리 1개 실행 (드래그/방향키/클릭/녹화). 실행했으면 True."""
        name   = slot.get("name", f"#{si+1}")
        coords = slot.get("coords", [])
        dirs   = slot.get("dirs") or []
        recs   = slot.get("recs") or {}
        d_ = dirs[j] if j < len(dirs) else None
        if d_ and d_[0] == "⏺":
            d_ = None
        c = coords[j] if j < len(coords) else None
        rec = recs.get(str(j))
        did = False
        if d_ and d_[0] == "⇩":
            if c:
                dist = max(30, int(float(d_[1]) * 30))
                sx, sy = c
                self._status.set(f"🖱 [{name}] {lbl} 끌어내리기 {dist}px...{tag}")
                pyautogui.mouseDown(sx, sy)
                time.sleep(0.08)
                for _st in range(1, 7):
                    pyautogui.moveTo(sx, sy + int(dist * _st / 6))
                    time.sleep(0.02)
                pyautogui.mouseUp(sx, sy + dist)
                did = True
        elif d_:
            self._hold_arrow(d_[0], float(d_[1]), name)
            did = True
        elif c:
            _cn = slot.get("click_names") or []
            _disp = _cn[j] if (j < len(_cn) and _cn[j]) else lbl
            self._status.set(f"🏝 [{name}] {_disp}{tag}")
            if j in move_set:
                pyautogui.moveTo(*c)
            else:
                pyautogui.click(*c)
            did = True
        if rec and not self._stop_flag:
            self._play_events(rec, name)
            did = True
        return did

    @staticmethod
    def _gap_seconds(g):
        """gap_list 값을 초로 — 숫자면 그 값, '8~10'이면 그 범위 랜덤, 비면 기본."""
        if g is None or g == "":
            return CLICK_INTERVAL
        if isinstance(g, (int, float)):
            return float(g)
        t = str(g).strip()
        try:
            if "~" in t:
                a, b = t.split("~")
                return random.uniform(float(a), float(b))
            return float(t)
        except Exception:
            return CLICK_INTERVAL

    def _sim_total(self, state, total, pace, lanes=4):
        """실제 클릭 없이 스케줄만 돌려 예상 소요시간(초)을 계산 (동시 lanes개 제한 포함)."""
        prog = {si: {"j": 0, "due": st["due"] - min(x["due"] for x in state.values()),
                     "sp": st["sp"], "slot": st["slot"]} for si, st in state.items()}
        order   = list(prog.keys())
        active  = order[:lanes]
        waiting = order[lanes:]
        t = 0.0
        guard = 0
        while guard < 40000:
            guard += 1
            for si in [x for x in active if prog[x]["j"] >= total]:
                active.remove(si)
                if waiting:
                    nx = waiting.pop(0)
                    prog[nx]["due"] = t + 1.2
                    active.append(nx)
            alive = [si for si in active if prog[si]["j"] < total]
            if not alive:
                break
            ready = [si for si in alive if prog[si]["due"] <= t]
            if not ready:
                t = min(prog[si]["due"] for si in alive)
                continue
            si = ready[0]
            p  = prog[si]; j = p["j"]
            cs = p["slot"].get("coords", [])
            did = j < len(cs) and cs[j]
            p["j"] = j + 1
            if did:
                gl = p["slot"].get("gap_list") or []
                p["due"] = t + self._gap_seconds(gl[j] if j < len(gl) else None) * p["sp"] * pace * 1.05
                t += 0.525          # 클릭 사이 평균 텀 (0.35~0.7)
            else:
                p["due"] = t
        return t

    def _calc_pace(self, state, total, target_sec):
        """목표 시간에 맞는 배속을 이분 탐색으로 찾는다 (최소 배속 1.0 = 등록한 간격 그대로)."""
        try:
            lo, hi = 1.0, 8.0
            if self._sim_total(state, total, lo) >= target_sec:
                return lo                      # 그냥 둬도 목표보다 오래 걸림
            for _ in range(18):
                mid = (lo + hi) / 2
                if self._sim_total(state, total, mid) < target_sec:
                    lo = mid
                else:
                    hi = mid
            return round((lo + hi) / 2, 2)
        except Exception:
            return 1.0

    def _run_wave(self, key, targets):
        """랜덤 번갈아 실행 — 슬롯마다 자기 시간표를 따로 돌리고,
        지금 할 차례가 된 슬롯 중에서 무작위로 하나씩 눌러준다.
        (1번을 두어 번 누르다 11번을 한 번 누르는 식 — 정해진 순서 없음)
        각 대기 시간은 슬롯마다 10~20% 랜덤으로 다르게 흐른다."""
        labels    = labels_for(key)
        move_set  = MOVE_ONLY_INDICES.get(key, set())
        stop_fn   = lambda: self._stop_flag
        status_fn = lambda m: self.after(0, lambda m=m: self._status.set(m))
        now = time.time()
        # 슬롯별 진행 상태: [다음에 할 클릭 번호, 언제 할 차례인지, 슬롯 고유 속도]
        state = {}
        for si, slot in targets:
            state[si] = {"slot": slot, "j": 0,
                         "due": now + random.uniform(0, 20.0),     # 시작 시점 넓게 흩뿌림
                         "sp": random.uniform(1.10, 1.20)}         # 이 슬롯 전체 10~20% 완화
        total = len(labels)
        # 목표 소요시간 랜덤 — 실행 전에 내부 시뮬레이션으로 배속을 맞춘다
        target_sec = random.uniform(252, 284) * slow_factor()   # 전체 12~17% 지연 (약 4:42~5:32)
        pace = self._calc_pace(state, total, target_sec)
        # 동시에 진행할 슬롯 수 제한 — 한 번에 4개만 돌리고, 하나가 끝나면 다음 슬롯 투입
        LANES = 4
        order = [si for si, _s in targets]
        random.shuffle(order)
        active = order[:LANES]
        waiting = order[LANES:]
        self._status.set(f"🎲 랜덤 실행 — 동시 {LANES}슬롯씩 (목표 "
                         f"{int(target_sec//60)}분 {int(target_sec%60)}초, 배속 ×{pace:.2f})")
        done_cnt = 0
        while not self._stop_flag:
            # 끝난 슬롯 자리에 대기 중인 슬롯을 채워 넣는다
            fin = [si for si in active if state[si]["j"] >= total]
            for si in fin:
                active.remove(si)
                if waiting:
                    nx = waiting.pop(random.randrange(len(waiting)))   # 투입 순서도 랜덤
                    state[nx]["due"] = time.time() + random.uniform(0.5, 4.0)
                    active.append(nx)
                    self._status.set(f"➡ #{si+1:02d} 완료 — #{nx+1:02d} 투입 "
                                     f"(진행 {done_cnt}회 / 남은 {len(waiting)}슬롯)")
            alive = [si for si in active if state[si]["j"] < total]
            if not alive:
                break
            now = time.time()
            ready = [si for si in alive if state[si]["due"] <= now]
            if not ready:
                nxt = min(state[si]["due"] for si in alive)
                w = max(0.05, min(nxt - now, 1.0))
                self._status.set(f"⏱ 다음 차례까지 {max(0, nxt - now):.1f}초  "
                                 f"(진행 {done_cnt}회 / 남은 슬롯 {len(alive)}개)")
                time.sleep(w)
                continue
            si = random.choice(ready)          # 차례가 된 것 중 무작위 선택
            st = state[si]
            j  = st["j"]
            if not wait_mouse_idle(stop_fn, status_fn): return
            if self._stop_flag: break
            did = self._do_one_click(key, si, st["slot"], j, labels[j], move_set,
                                     tag=f"  (#{si+1:02d} {j+1}/{total})")
            st["j"] = j + 1
            if did:
                done_cnt += 1
                gl = st["slot"].get("gap_list") or []
                g  = gl[j] if j < len(gl) else None
                # 매 클릭마다 큰 편차(0.7~1.7배) — 슬롯마다 시간이 제각각 흘러
                # 어떤 슬롯은 연달아 두세 번, 어떤 슬롯은 한참 쉬었다 눌린다
                st["due"] = (time.time() + self._gap_seconds(g) * st["sp"] * pace
                             * random.uniform(0.55, 1.5))
            else:
                st["due"] = time.time()        # 빈 자리는 기다리지 않고 바로 다음으로
            # 마우스는 하나 — 클릭끼리 최소 간격을 둬서 씹힘 방지
            time.sleep(random.uniform(0.35, 0.7))   # 클릭 사이 텀 (창 전환 여유)
        if not self._stop_flag:
            time.sleep(2)          # (2026-08-09) 마지막 클릭 후 2초 뒤 마무리
        for si, _s in targets:
            self._add_count(si)

    def _run(self, key, slot_idx=None, sel_list=None):
        self._slot_running = True
        try:
            self._status.set("2초 후 실행 시작...")
            time.sleep(2)
            slots = self.cfg.get(key, [])
            if sel_list:
                # +로 고른 슬롯만, 누른 순서 그대로 (셔플 없음)
                targets = [(i, slots[i]) for i in sel_list if i < len(slots)]
            elif slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if s.get("enabled", True)
                           and (any(c for c in s.get("coords", [])) or any(s.get("dirs") or []))]
                random.shuffle(targets)   # 슬롯 실행 순서 매번 랜덤
                if key == "카매사오기":
                    # (2026-08-09) 카매사오기는 02~04 슬롯이 항상 마지막에 실행돼야 한다.
                    # (앞 슬롯들이 먼저 끝나야 이 슬롯들이 할 일이 생김)
                    targets.sort(key=lambda t: 1 if t[0] in (1, 2, 3) else 0)
            d = next(x for x in DUNGEONS if x["key"] == key)
            stop_fn   = lambda: self._stop_flag
            status_fn = lambda m: self.after(0, lambda m=m: self._status.set(m))
            # 오만의탑·악몽의섬: 슬롯 하나씩이 아니라 번갈아(웨이브) 실행
            if key in self.WAVE_KEYS and slot_idx is None and len(targets) > 1:
                self._status.set(f"🌊 번갈아 실행 — {len(targets)}개 슬롯을 클릭 순서대로 돌립니다")
                self._run_wave(key, targets)
                self._status.set("✔ 실행 완료!" if not self._stop_flag else "멈춤")
                return
            for ti, (si, slot) in enumerate(targets):
                if self._stop_flag: break
                if ti > 0:
                    # 슬롯 사이 간격 — 7~13초 랜덤
                    _sg = random.uniform(7, 13)
                    self._status.set(f"⏱ 다음 슬롯까지 {_sg:.1f}초 (랜덤 7~13)...")
                    _t0 = time.time()
                    while time.time() - _t0 < _sg:
                        if self._stop_flag: break
                        time.sleep(0.1)
                    if self._stop_flag: break
                if not wait_mouse_idle(stop_fn, status_fn): break
                name   = slot.get("name", f"#{si+1}")
                _labels = labels_for(key)
                coords = slot.get("coords", [None]*len(_labels))
                while len(coords) < len(_labels):
                    coords.append(None)
                dirs = slot.get("dirs") or []
                if not any(coords) and not any(dirs) and not (slot.get("recs") or {}):
                    continue
                move_set = MOVE_ONLY_INDICES.get(key, set())
                # 클릭별 간격(gap_list) — 팝업의 'ㅡ' 위 칸에 적은 초, 비우면 기본
                gl = slot.get("gap_list") or []
                recs = slot.get("recs") or {}
                # 간격 10~20% 추가 완화 — 오만의탑·악몽의섬은 항상 적용(사용자 지정),
                # 나머지는 녹화 없는 슬롯만 (녹화가 있으면 재생 시점이 밀려 화면이 어긋남)
                _slow_always = key in ("수금_오만의탑", "토요일_악몽의섬")
                _slow = (random.uniform(1.10, 1.20)
                         if (_slow_always or not any(recs.values())) else 1.0)
                for j, lbl in enumerate(_labels):
                    if self._stop_flag: break
                    if key == "카매사오기":
                        # 사용자가 마우스를 쓰는 중이면 클릭이 엉뚱한 곳에 들어가거나 씹힌다 →
                        # 마우스가 멈출 때까지 기다렸다가 누른다 (웨이브 실행과 동일한 보호)
                        if not wait_mouse_idle(stop_fn, status_fn): break
                    d_ = dirs[j] if j < len(dirs) else None
                    if d_ and d_[0] == "⏺":   # 구버전 데이터 호환 — 이제 녹화는 별도 버튼
                        d_ = None
                    rec = recs.get(str(j))
                    did = False
                    if d_ and d_[0] == "⇩":
                        # 등록한 좌표를 짧게 누르고 아래로 살짝 끌어내리기 (스크롤)
                        if coords[j]:
                            dist = max(30, int(float(d_[1]) * 30))   # 1=30px(살짝) ~ 10=300px
                            sx, sy = coords[j]
                            self._status.set(f"🖱 [{name}] {lbl} 끌어내리기 {dist}px...")
                            pyautogui.mouseDown(sx, sy)
                            time.sleep(0.08)
                            _steps = 6
                            for _st in range(1, _steps + 1):
                                pyautogui.moveTo(sx, sy + int(dist * _st / _steps))
                                time.sleep(0.02)
                            pyautogui.mouseUp(sx, sy + dist)
                            did = True
                    elif d_:
                        # 이 자리는 클릭 대신 방향키 이동 ([방향, 초] — 대각선 포함)
                        self._hold_arrow(d_[0], float(d_[1]), name)
                        did = True
                    elif coords[j]:
                        _cn = slot.get("click_names") or []
                        _disp = _cn[j] if (j < len(_cn) and _cn[j]) else lbl
                        self._status.set(f"🏝 [{name}] {_disp}...")
                        if j in move_set:
                            pyautogui.moveTo(*coords[j])
                        else:
                            pyautogui.click(*coords[j])
                        did = True
                    if rec and not self._stop_flag:
                        # 녹화는 클릭과 별개 — 이 자리 동작 후 녹화 재생
                        self._play_events(rec, name)
                        did = True
                    if not did:
                        continue
                    self._rlog(f"[클릭] {key} #{si+1:02d} {j+1}번({lbl}) 실행")
                    g = gl[j] if j < len(gl) else None
                    # 좌표 간 간격 10~25% 랜덤 증가 (× 녹화 없는 슬롯은 _slow 추가 완화)
                    _mult = (random.uniform(1.10, 1.25) * _slow * 1.05
                             * slow_factor())      # 전체 12~17% 추가 지연
                    if g is None or g == "":
                        time.sleep(CLICK_INTERVAL * _mult)
                    elif isinstance(g, (int, float)):
                        time.sleep(float(g) * _mult)
                    else:
                        self._do_gap_spec(str(g), name)   # 대기 토큰에 10~25% 증가 적용됨
                self._add_count(si)
                if self._stop_flag: break
                time.sleep(5)
            if not self._stop_flag:
                # (2026-08-09) 마지막 번호를 누르자마자 끝내지 않고 2초 뒤에 마무리
                time.sleep(2)
            self._status.set("✔ 실행 완료!")
        except Exception as e:
            self._status.set(f"오류: {e}")
        finally:
            self._slot_running = False
            self._repeat_busy = False
            for btn in self._stop_btns.values():
                btn.config(state="disabled")
            if sel_list:
                # 선택 실행 끝 — 담아둔 + 선택 비우고 버튼 원상복구
                self._sel_order[key] = []
                self.after(0, lambda: self._refresh_sel(key))
            if getattr(self, "_auto_run", False):
                # 런처 ▶ 자동 실행 모드: 완료 후 창을 띄우지 않고 스스로 종료 —
                # 런처가 종료를 감지하고 대기열의 다음 던전을 이어서 실행한다
                self.after(500, self.destroy)
            else:
                # 끝나도 앞으로 튀어나오지 않고 '메인런처 바로 앞(클라 뒤)'에 대기 —
                # 개별 실행을 이어서 누르려면 작업표시줄/클릭으로 올리면 된다
                def _restore():
                    self.deiconify()
                    self._send_behind_main()
                self.after(0, _restore)


class _PresetDotOverlay(tk.Toplevel):
    """프리셋 번호 미리보기 — 반투명 화면에 점 하나 표시, 아무 키/클릭으로 닫기."""

    def __init__(self, app, num, pos, note=""):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(str(sw) + "x" + str(sh) + "+0+0")
        self.attributes("-alpha", 0.35)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        cv = tk.Canvas(self, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(sw // 2, 40,
                       text="클릭 " + str(num) + "번 위치  (" + note + ")  —  아무 곳이나 클릭하면 닫힘",
                       fill="white", font=("맑은 고딕", 13))
        x, y = int(pos[0]), int(pos[1])
        for r, col in ((26, "#f1c40f"), (16, "#e67e22"), (6, "#e74c3c")):
            cv.create_oval(x - r, y - r, x + r, y + r, outline=col, width=2)
        cv.create_line(x - 40, y, x + 40, y, fill="#f1c40f")
        cv.create_line(x, y - 40, x, y + 40, fill="#f1c40f")
        cv.create_text(x, y - 34, text=str(num), fill="white", font=("맑은 고딕", 11, "bold"))
        for w in (self, cv):
            w.bind("<Button-1>", lambda e: self.destroy())
            w.bind("<Escape>", lambda e: self.destroy())
        self.after(6000, lambda: self.winfo_exists() and self.destroy())


class _IslandGroupMoveOverlay(tk.Toplevel):
    """복사한 슬롯 좌표 전체를 그룹 드래그로 이동 후 저장"""
    R = 5

    def __init__(self, app, key, slot_idx, dots, on_close=None):
        super().__init__()
        self.app      = app
        self.key      = key
        self.slot_idx = slot_idx
        self._on_close = on_close
        # [x, y, num, coord_idx]
        self._dots  = [[x, y, num, ci] for x, y, num, ci in dots]
        self._drag  = False
        self._moved = False
        self._last  = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
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
        d = next((x for x in DUNGEONS if x["key"] == self.key), None)
        color = d["color"] if d else "red"
        for x, y, num, _ in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 6, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg[self.key][self.slot_idx].get("coords", [])
            for x, y, num, ci in self._dots:
                if ci < len(coords) and coords[ci]:
                    coords[ci] = [x, y]
            self.app.cfg[self.key][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg)
            self.app._refresh(self.key)
            self.app._status.set(f"✔ #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy()
        if self._on_close:
            self.app.after(300, self._on_close)
        else:
            self.app.deiconify()


class _QuickPosOverlay(tk.Toplevel):
    """슬롯마다 클릭 한 번으로 좌표 전체를 이동하는 빠른 이동 오버레이"""

    def __init__(self, app, key, slot_idx, ref_coord, total_slots, on_close=None):
        super().__init__()
        self.app         = app
        self.key         = key
        self.slot_idx    = slot_idx   # 현재 처리 중인 슬롯
        self.ref_coord   = ref_coord  # 슬롯1 기준 좌표 (클릭1)
        self.total_slots = total_slots
        self._on_close   = on_close

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-alpha", 0.01)  # 거의 투명 — 클릭만 잡음

        # 상단 안내 바
        bar = tk.Toplevel(self)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bar.geometry(f"{sw}x44+0+0")
        bar.configure(bg="#1a252f")
        d = next((x for x in DUNGEONS if x["key"] == key), None)
        color = d["color"] if d else "#e74c3c"
        tk.Label(bar, text=f"슬롯 #{slot_idx+1:02d} / {total_slots}  —  이 슬롯의 클릭1 위치를 클릭하세요   |   ESC: 건너뜀",
                 font=("맑은 고딕", 12, "bold"), fg=color, bg="#1a252f").pack(expand=True)
        self._bar = bar

        cv = tk.Canvas(self, highlightthickness=0, cursor="crosshair",
                       bg="black")
        cv.pack(fill="both", expand=True)
        cv.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: self._skip())
        self.lift(); self.focus_force()

    def _on_click(self, e):
        rx, ry = self.ref_coord
        dx, dy = e.x - rx, e.y - ry
        coords = self.app.cfg[self.key][self.slot_idx].get("coords", [])
        for i, c in enumerate(coords):
            if c:
                coords[i] = [c[0] + dx, c[1] + dy]
        self.app.cfg[self.key][self.slot_idx]["coords"] = coords
        save_cfg(self.app.cfg)
        self.app._refresh(self.key)
        self.app._status.set(f"✔ #{self.slot_idx+1:02d} 이동 완료 ({dx:+d},{dy:+d})")
        self._next()

    def _skip(self):
        self.app._status.set(f"⏭ #{self.slot_idx+1:02d} 건너뜀")
        self._next()

    def _next(self):
        self._bar.destroy()
        self.destroy()
        if self._on_close:
            self.app.after(150, self._on_close)
        else:
            self.app.deiconify()


class _IslandPreviewOverlay(tk.Toplevel):
    """스크린샷 배경 + 개별 드래그 수정 미리보기
    dots: [(x, y, num, coord_idx), ...]
    """
    R = 5

    def __init__(self, app, key, slot_idx, dots):
        super().__init__()
        self.app       = app
        self.key       = key
        self.slot_idx  = slot_idx
        # [x, y, num, coord_idx]
        self._dots  = [[x, y, num, ci] for x, y, num, ci in dots]
        self._drag  = None
        self._moved = False
        self._last  = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="hand2")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="점을 드래그해 이동 저장  |  빈 곳 클릭: 닫기  |  ESC: 닫기",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num, _ in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="red", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 6, "bold"))

    def _hit(self, ex, ey):
        r = self.R + 6
        for i, (x, y, _, __) in enumerate(self._dots):
            if abs(ex - x) < r and abs(ey - y) < r:
                return i
        return None

    def _on_press(self, e):
        hit = self._hit(e.x, e.y)
        self._drag  = hit
        self._moved = False
        self._last  = (e.x, e.y)

    def _on_drag(self, e):
        if self._drag is None: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        self._dots[self._drag][0] += dx
        self._dots[self._drag][1] += dy
        self._draw()

    def _on_release(self, e):
        if self._drag is not None and self._moved:
            x, y, num, ci = self._dots[self._drag]
            # 전체보기(slot_idx=None)에서는 ci가 (슬롯, 클릭) 튜플로 들어온다
            si, cj = ci if isinstance(ci, tuple) else (self.slot_idx, ci)
            self.app.cfg[self.key][si]["coords"][cj] = [x, y]
            save_cfg(self.app.cfg)
            self.app._refresh(self.key)
            self.app._status.set(f"✔ 클릭{num} 이동 저장: ({x},{y})")
            self._drag = None; self._moved = False
        elif self._drag is None:
            self._close()
        else:
            self._drag = None

    def _close(self):
        self.destroy()
        self.app.deiconify()


if __name__ == "__main__":
    focus = None
    if len(sys.argv) > 1:
        try:
            focus = int(sys.argv[1])
        except ValueError:
            pass
    app = IslandApp(focus_idx=focus)
    app.mainloop()

