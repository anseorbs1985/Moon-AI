"""
다야 수량 OCR 등록/스캔 모듈
- 드래그로 영역 캡처
- 위에서 복사 기능
- easyocr로 숫자 인식
"""
import ctypes
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass

import tkinter as tk
from tkinter import messagebox
import json, os, threading, datetime
import pyautogui
from PIL import ImageGrab

try:
    from precise_click import install as _install_precise_click
    _install_precise_click(pyautogui)   # 마우스가 움직여도 지정 좌표에 정확히 클릭
except Exception:
    pass

BASE       = os.path.dirname(os.path.abspath(__file__))
OCR_FILE   = os.path.join(BASE, "daya_regions.json")
# 다야 측정 데이터는 git/업데이트가 못 건드리는 로컬 앱데이터 폴더에 저장
LOCAL_DATA = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
try:
    os.makedirs(os.path.join(LOCAL_DATA, "daya_crops"), exist_ok=True)
    _old = os.path.join(BASE, "daya_counts.json")
    if os.path.exists(_old) and not os.path.exists(os.path.join(LOCAL_DATA, "daya_counts.json")):
        import shutil as _sh
        _sh.copy2(_old, os.path.join(LOCAL_DATA, "daya_counts.json"))
except Exception:
    pass
COUNT_FILE = os.path.join(LOCAL_DATA, "daya_counts.json")
SLOTS      = 16

_reader = None
def get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _reader


def load_regions():
    try:
        with open(OCR_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_regions(data):
    with open(OCR_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_counts():
    try:
        with open(COUNT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_counts(data):
    with open(COUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def today():
    return datetime.date.today().isoformat()


import ctypes.wintypes as _wt
import time as _time

def _minimize_claude():
    SW_MINIMIZE = 6
    def _cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        if "claude" in buf.value.lower():
            ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

def _restore_claude():
    SW_RESTORE = 9
    def _cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        if "claude" in buf.value.lower():
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

def _get_cursor():
    pt = _wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def _lmb_down():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)

def _esc_down():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)

def _wait_lmb_release():
    while _lmb_down():
        _time.sleep(0.01)

def _capture_click(cancelled):
    """LMB 클릭 위치 반환. ESC 또는 cancelled[0]=True면 None."""
    _wait_lmb_release()
    _time.sleep(0.05)
    while True:
        if cancelled[0] or _esc_down():
            return None
        if _lmb_down():
            x, y = _get_cursor()
            _wait_lmb_release()
            return (x, y)
        _time.sleep(0.01)

def _capture_drag(cancelled):
    """LMB 드래그 영역 반환 [x,y,w,h]. ESC 또는 cancelled[0]=True면 None."""
    _wait_lmb_release()
    _time.sleep(0.05)
    # 버튼 눌릴 때까지 대기
    while True:
        if cancelled[0] or _esc_down():
            return None
        if _lmb_down():
            x1, y1 = _get_cursor()
            break
        _time.sleep(0.01)
    # 버튼 놓일 때까지 대기
    while _lmb_down():
        if cancelled[0]:
            return None
        _time.sleep(0.01)
    x2, y2 = _get_cursor()
    if abs(x2-x1) < 5 or abs(y2-y1) < 5:
        return None  # 너무 작은 드래그
    return [min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)]


class _HintWin(tk.Toplevel):
    """작은 안내 창 (풀스크린 없음, 입력 차단 없음)"""
    def __init__(self, msg, on_cancel):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        w, h = 520, 48
        self.geometry(f"{w}x{h}+{(sw-w)//2}+10")
        self.configure(bg="#1a252f")
        tk.Label(self, text=msg, font=("맑은 고딕", 11), fg="white",
                 bg="#1a252f").pack(side="left", padx=12, expand=True)
        tk.Button(self, text="취소", font=("맑은 고딕", 9), bg="#c0392b", fg="white",
                  bd=0, padx=8, command=on_cancel).pack(side="right", padx=8, pady=6)


class AllCoordsOverlay(tk.Toplevel):
    """①절전 ②확대 드래그 이동 가능. ③영역은 표시만. 빈 곳 클릭 = 저장+닫기."""
    def __init__(self, app, idx, region, zoom_in, wake):
        super().__init__()
        self.app    = app
        self.idx    = idx
        self.region = list(region)  if region  else None
        self.wake   = list(wake)    if wake    else None
        self.zi     = list(zoom_in) if zoom_in else None
        self._drag  = None   # 현재 드래그 중인 대상 ("wake" / "zi")
        self._moved = False

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg = _ITk.PhotoImage(shot)

        self.cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self.cv.pack(fill="both", expand=True)
        self.cv.create_image(0, 0, anchor="nw", image=self._bg)

        cv = self.cv
        cv.create_rectangle(0, 0, sw, 36, fill="#1a252f", outline="")
        cv.create_text(sw//2, 18,
            text=f"#{idx+1:02d}  점 드래그=이동/저장  |  빈 곳 클릭=닫기  |  ESC=취소",
            fill="#ccc", font=("맑은 고딕", 10))

        self._draw()
        cv.bind("<ButtonPress-1>",   self._on_press)
        cv.bind("<B1-Motion>",       self._on_drag)
        cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._cancel())
        self.lift(); self.focus_force()

    def _r(self): return 8

    def _draw(self):
        self.cv.delete("dots")
        r = self._r()
        if self.wake:
            x, y = self.wake
            self.cv.create_oval(x-r, y-r, x+r, y+r, fill="#e67e22",
                                outline="white", width=2, tags=("dots","wk"))
            self.cv.create_text(x, y+r+7, text="①절전", fill="#e67e22",
                                font=("맑은 고딕", 7, "bold"), tags="dots")
        if self.zi:
            x, y = self.zi
            self.cv.create_oval(x-r, y-r, x+r, y+r, fill="#8e44ad",
                                outline="white", width=2, tags=("dots","zi"))
            self.cv.create_text(x, y+r+7, text="②확대", fill="#8e44ad",
                                font=("맑은 고딕", 7, "bold"), tags="dots")
        if self.region:
            x, y, w, h = self.region
            self.cv.create_rectangle(x, y, x+w, y+h, outline="red",
                                     width=2, tags="dots")
            self.cv.create_text(x+w//2, y+h//2, text="③영역", fill="red",
                                font=("맑은 고딕", 7, "bold"), tags="dots")

    def _hit(self, ex, ey):
        r = self._r() + 10
        if self.wake and abs(ex-self.wake[0]) < r and abs(ey-self.wake[1]) < r:
            return "group"
        if self.zi   and abs(ex-self.zi[0])   < r and abs(ey-self.zi[1])   < r:
            return "group"
        return None

    def _on_press(self, e):
        self._drag = self._hit(e.x, e.y)
        self._last = (e.x, e.y)
        self._moved = False

    def _on_drag(self, e):
        if self._drag != "group": return
        dx = e.x - self._last[0]
        dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1:
            self._moved = True
        self._last = (e.x, e.y)
        # ①절전 ②확대 항상 같이 이동
        if self.wake: self.wake[0] += dx; self.wake[1] += dy
        if self.zi:   self.zi[0]   += dx; self.zi[1]   += dy
        self._draw()

    def _on_release(self, e):
        if self._drag and self._moved:
            # 드래그 후 놓음 → 저장
            self._save()
            self._drag = None
            self._moved = False
        elif not self._drag:
            # 빈 곳 클릭 → 닫기
            self._close()
        else:
            # 점 위 클릭(드래그 없음) → 아무것도 안 함
            self._drag = None

    def _save(self):
        data = load_regions()
        zc = data.get("__zoom__", {})
        if self.wake: zc[f"wake_{self.idx}"] = self.wake
        if self.zi:   zc[f"in_{self.idx}"]   = self.zi
        data["__zoom__"] = zc
        save_regions(data)
        self.app._zoom_coords = zc
        self.app.after(0, self.app._refresh_zoom_ui)

    def _close(self):
        self.destroy()
        self.app.deiconify()

    def _cancel(self):
        self.destroy()
        self.app.deiconify()


class GroupMoveOverlay(tk.Toplevel):
    """절전+확대 좌표 전체를 드래그로 한번에 이동. 영역/축소 좌표는 제외."""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg = _ITk.PhotoImage(shot)

        self.cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self.cv.pack(fill="both", expand=True)
        self.cv.create_image(0, 0, anchor="nw", image=self._bg)

        # 상단 안내바
        self.cv.create_rectangle(0, 0, sw, 36, fill="#1a252f", outline="")
        self.cv.create_text(sw//2, 18,
            text="절전+확대 좌표 전체 이동  |  드래그해서 이동  |  ESC: 취소",
            fill="#ccc", font=("맑은 고딕", 10))

        # 현재 좌표 수집 (영역/축소 제외)
        zc = app._zoom_coords
        self._dots = {}  # key -> [x, y]
        for i in range(SLOTS):
            for kind in ("wake", "in"):
                key = f"{kind}_{i}"
                c = zc.get(key)
                if c:
                    self._dots[key] = list(c)

        self._drag_start = None
        self._draw_dots()

        self.cv.bind("<ButtonPress-1>",   self._on_press)
        self.cv.bind("<B1-Motion>",       self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._cancel())
        self.lift(); self.focus_force()

    def _draw_dots(self):
        self.cv.delete("dots")
        r = 6
        zc = self.app._zoom_coords
        for key, (x, y) in self._dots.items():
            kind = "wake" if key.startswith("wake") else "in"
            color = "#e67e22" if kind == "wake" else "#8e44ad"
            label = "①" if kind == "wake" else "②"
            self.cv.create_oval(x-r, y-r, x+r, y+r,
                                fill=color, outline="white", width=1, tags="dots")
            self.cv.create_text(x, y+r+6, text=label,
                                fill=color, font=("맑은 고딕", 7, "bold"), tags="dots")

    def _on_press(self, e):
        self._drag_start = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag_start:
            return
        dx = e.x - self._drag_start[0]
        dy = e.y - self._drag_start[1]
        self._drag_start = (e.x, e.y)
        for key in self._dots:
            self._dots[key][0] += dx
            self._dots[key][1] += dy
        self._draw_dots()

    def _on_release(self, e):
        # 저장
        data = load_regions()
        zc = data.get("__zoom__", {})
        for key, pos in self._dots.items():
            zc[key] = pos
        data["__zoom__"] = zc
        save_regions(data)
        self.app._zoom_coords = zc
        self.app.after(0, self.app._refresh_zoom_ui)
        self.app.after(0, self.app._refresh_ui)
        self.destroy()
        self.app.deiconify()
        self.app.after(50, lambda: self.app._status.set("✔ 그룹 이동 저장 완료"))

    def _cancel(self):
        self.destroy()
        self.app.deiconify()


class OCRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # 게임 클라이언트들이 CPU를 100% 잡고 있어도 OCR이 CPU를 우선 받도록
        # 이 프로세스를 높은 우선순위로 설정 (게임보다 먼저 스케줄됨)
        try:
            _k = ctypes.windll.kernel32
            _k.SetPriorityClass(_k.GetCurrentProcess(), 0x00000080)  # HIGH_PRIORITY_CLASS
        except Exception:
            pass
        self.title("다야 수량 OCR")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # 작업표시줄을 제외한 작업영역 하단까지 세로로 확장 (상단 위치는 유지)
        try:
            import ctypes.wintypes as _wt
            _rc = _wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(_rc), 0)  # SPI_GETWORKAREA
            _work_bottom = _rc.bottom
        except Exception:
            _work_bottom = sh
        _top = sh // 6
        _h = _work_bottom - _top - 40   # 창 프레임(≈39px) 감안 → 하단이 작업표시줄 바로 위에 안착
        self.geometry(f"700x{_h}+{sw//2-350}+{_top}")
        self.resizable(True, True)

        self.regions = load_regions()
        self._region_vars  = []
        self._result_vars  = []
        self._zoom_in_vars = []
        self._wake_vars    = []

        self._build_ui()
        self._refresh_ui()
        self._refresh_zoom_ui()

        # 3분간 조작이 없으면 자동으로 닫고 메인런처를 앞으로 띄운다
        import time as _t
        self._last_active = _t.time()
        def _bump(e=None): self._last_active = _t.time()
        for _seq in ("<Button>", "<Key>", "<Motion>"):
            self.bind_all(_seq, _bump, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(20000, self._idle_close_tick)

    def _on_close(self):
        self._raise_main_launcher()
        self.destroy()

    def _idle_close_tick(self):
        import time as _t
        try:
            if not getattr(self, "_scanning", False) \
               and _t.time() - getattr(self, "_last_active", _t.time()) >= 180:
                self._raise_main_launcher()
                self.destroy()
                return
        except Exception:
            pass
        self.after(20000, self._idle_close_tick)

    def _raise_main_launcher(self):
        """다야 OCR 창이 닫힐 때 메인런처를 앞으로 띄운다."""
        try:
            import win32gui, win32con
            h = win32gui.FindWindow(None, "리니지M 자동 실행")
            if h:
                win32gui.ShowWindow(h, win32con.SW_RESTORE)
                try:
                    win32gui.SetForegroundWindow(h)
                except Exception:
                    pass
        except Exception:
            pass

    def _build_ui(self):
        hdr = tk.Frame(self, bg="#2c3e50"); hdr.pack(fill="x")
        tk.Label(hdr, text="📊 다야 수량 OCR",
                 font=("맑은 고딕", 12, "bold"), fg="white", bg="#2c3e50",
                 pady=8).pack(side="left", padx=12)

        # 축소(공통) + 대기 설정 패널
        zoom_frame = tk.Frame(self, bd=1, relief="groove")
        zoom_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(zoom_frame, text="공통 설정",
                 font=("맑은 고딕", 9, "bold"), fg="#2c3e50").grid(row=0, column=0, padx=6, pady=2)

        self._zoom_out_var = tk.StringVar(value="미등록")
        self._region_common_var = tk.StringVar(value="미등록")

        tk.Button(zoom_frame, text="📍 축소 좌표", font=("맑은 고딕", 8, "bold"), bg="#2980b9", fg="white",
                  width=10, command=lambda: self._reg_zoom("out")).grid(row=0, column=1, padx=6, pady=4)
        tk.Label(zoom_frame, textvariable=self._zoom_out_var,
                 font=("맑은 고딕", 7), fg="#2980b9", width=12).grid(row=0, column=2, padx=2)
        tk.Button(zoom_frame, text="👁", font=("맑은 고딕", 8),
                  command=self._preview_zoom_out).grid(row=0, column=3, padx=2)

        tk.Frame(zoom_frame, width=1, bg="#ccc").grid(row=0, column=4, sticky="ns", padx=6, pady=4)

        tk.Button(zoom_frame, text="③ 영역 등록 (공통)", font=("맑은 고딕", 8, "bold"), bg="#2c3e50", fg="white",
                  width=16, command=self._reg_common_region).grid(row=0, column=5, padx=6, pady=4)
        tk.Label(zoom_frame, textvariable=self._region_common_var,
                 font=("맑은 고딕", 7), fg="#555", width=14).grid(row=0, column=6, padx=2)

        tk.Frame(zoom_frame, width=1, bg="#ccc").grid(row=0, column=7, sticky="ns", padx=6, pady=4)

        tk.Button(zoom_frame, text="🔀 그룹 이동", font=("맑은 고딕", 8, "bold"), bg="#16a085", fg="white",
                  width=10, command=self._group_move).grid(row=0, column=8, padx=6, pady=4)

        tk.Frame(zoom_frame, width=1, bg="#ccc").grid(row=0, column=9, sticky="ns", padx=6, pady=4)

        tk.Label(zoom_frame, text="절전(초):", font=("맑은 고딕", 8)).grid(row=0, column=10, padx=(4,2))
        self._wake_wait_var = tk.StringVar(value="1.8")
        tk.Entry(zoom_frame, textvariable=self._wake_wait_var,
                 width=4, font=("맑은 고딕", 9)).grid(row=0, column=11, padx=2)
        tk.Label(zoom_frame, text="줌인(초):", font=("맑은 고딕", 8)).grid(row=0, column=12, padx=(6,2))
        self._zoom_wait_var = tk.StringVar(value="3.0")
        tk.Entry(zoom_frame, textvariable=self._zoom_wait_var,
                 width=4, font=("맑은 고딕", 9)).grid(row=0, column=13, padx=2)
        tk.Label(zoom_frame, text="줌아웃(초):", font=("맑은 고딕", 8)).grid(row=0, column=14, padx=(6,2))
        self._zoomout_wait_var = tk.StringVar(value="1.4")
        tk.Entry(zoom_frame, textvariable=self._zoomout_wait_var,
                 width=4, font=("맑은 고딕", 9)).grid(row=0, column=15, padx=2)

        raw = load_regions()
        self._zoom_coords = raw.get("__zoom__", {})

        self._status = tk.StringVar(value="영역을 등록하고 스캔하세요")
        tk.Label(self, textvariable=self._status,
                 font=("맑은 고딕", 8), fg="#555", anchor="w").pack(fill="x", padx=10, pady=3)
        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=8)

        btn_row = tk.Frame(self); btn_row.pack(pady=6)
        tk.Button(btn_row, text="▶ 전체 스캔",
                  font=("맑은 고딕", 10, "bold"), bg="#27ae60", fg="white",
                  width=12, height=2, command=self._scan_all).pack(side="left", padx=4)
        tk.Button(btn_row, text="전체 초기화",
                  font=("맑은 고딕", 8), width=8, height=2,
                  command=self._clear_all).pack(side="left", padx=4)
        tk.Button(btn_row, text="📋 엑셀복사",
                  font=("맑은 고딕", 8), width=8, height=2,
                  bg="#2471a3", fg="white",
                  command=self._copy_to_clipboard).pack(side="left", padx=4)

        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=8, pady=2)

        # 슬롯 리스트
        outer = tk.Frame(self); outer.pack(fill="both", expand=True, padx=6, pady=4)
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

        for i in range(SLOTS):
            card = tk.Frame(inner, bd=1, relief="groove"); card.pack(fill="x", padx=4, pady=2)

            # 상단: 번호 + 다야수량 + 스캔/미리보기/복사 버튼
            top = tk.Frame(card); top.pack(fill="x")
            tk.Label(top, text=f"#{i+1:02d}", font=("맑은 고딕", 9, "bold"),
                     width=3, fg="#2c3e50").pack(side="left", padx=(4,2))

            res = tk.StringVar(value="-")
            self._result_vars.append(res)
            tk.Label(top, textvariable=res, font=("맑은 고딕", 12, "bold"),
                     fg="#2980b9", width=7).pack(side="left", padx=4)

            tk.Button(top, text="▶ 스캔", font=("맑은 고딕", 7), bg="#27ae60", fg="white",
                      width=5, command=lambda x=i: self._scan_one(x)).pack(side="right", padx=2)
            tk.Button(top, text="📷", font=("맑은 고딕", 7),
                      width=2, command=lambda x=i: self._check_capture(x)).pack(side="right", padx=1)
            tk.Button(top, text="👁 미리보기", font=("맑은 고딕", 7), bg="#f39c12", fg="white",
                      width=7, command=lambda x=i: self._preview(x)).pack(side="right", padx=2)
            if i > 0:
                tk.Button(top, text="↑복사", font=("맑은 고딕", 6), bg="#7d6608", fg="white",
                          width=4, command=lambda x=i: self._copy_above(x)).pack(side="right", padx=2)
            tk.Button(top, text="×삭제", font=("맑은 고딕", 7), fg="red",
                      width=4, command=lambda x=i: self._del(x)).pack(side="right", padx=1)

            # 하단: 좌표 등록 + 이동 버튼
            bot = tk.Frame(card, bg="#f8f8f8"); bot.pack(fill="x", pady=(0,2))

            # 절전
            tk.Button(bot, text="① 절전등록", font=("맑은 고딕", 7), bg="#e67e22", fg="white",
                      width=8, command=lambda x=i: self._reg_zoom("wake", x)).pack(side="left", padx=(6,1))
            wv = tk.StringVar(value="미등록")
            self._wake_vars.append(wv)
            tk.Label(bot, textvariable=wv, font=("맑은 고딕", 7),
                     fg="#e67e22", width=10, anchor="w").pack(side="left", padx=(0,6))

            # 확대
            tk.Button(bot, text="② 확대등록", font=("맑은 고딕", 7), bg="#8e44ad", fg="white",
                      width=8, command=lambda x=i: self._reg_zoom_in(x)).pack(side="left", padx=(0,1))
            zv = tk.StringVar(value="미등록")
            self._zoom_in_vars.append(zv)
            tk.Label(bot, textvariable=zv, font=("맑은 고딕", 7),
                     fg="#8e44ad", width=10, anchor="w").pack(side="left", padx=(0,6))

            rv = tk.StringVar(value="미등록")
            self._region_vars.append(rv)

    def _refresh_ui(self):
        r = self.regions.get("common")
        self._region_common_var.set(f"x{r[0]} y{r[1]} {r[2]}×{r[3]}" if r else "미등록")

    def _reg_common_region(self):
        self._do_drag_capture("common")

    def _reg(self, idx):
        self._do_drag_capture(idx)

    def _do_drag_capture(self, idx):
        lbl = "공통 영역" if idx == "common" else f"#{idx+1:02d}"
        self._status.set(f"[{lbl}] 마우스로 드래그하세요 (ESC/취소버튼: 취소)")
        cancelled = [False]
        hint = _HintWin(f"[{lbl}] 영역을 드래그하세요  (ESC: 취소)", lambda: cancelled.__setitem__(0, True))
        self.withdraw()
        def _run():
            region = _capture_drag(cancelled)
            self.after(0, lambda: hint.destroy())
            self.after(0, self.deiconify)
            if region:
                self.after(50, lambda: self._on_region_captured(idx, region))
            else:
                self.after(50, lambda: self._status.set("취소됨"))
        threading.Thread(target=_run, daemon=True).start()

    def _on_region_captured(self, idx, region):
        self.regions[idx] = region
        save_regions(self.regions)
        self._refresh_ui()
        self._status.set(f"✔ 영역 등록: x{region[0]} y{region[1]} {region[2]}×{region[3]}")

    def _preview(self, idx):
        r  = self.regions.get("common")
        zi = self._zoom_coords.get(f"in_{idx}")
        wk = self._zoom_coords.get(f"wake_{idx}")
        if not r and not zi and not wk:
            self._status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        self.withdraw()
        self.after(100, lambda: AllCoordsOverlay(self, idx, r, zi, wk))

    def on_region_moved(self, idx, region):
        self.regions[str(idx)] = region
        save_regions(self.regions)
        self._refresh_ui()
        self._status.set(f"✔ #{idx+1:02d} 영역 이동 저장: {region}")
        self.deiconify()

    def _copy_above(self, idx):
        # 영역은 공통이므로 ①절전 + ②확대만 복사
        copied = []
        for kind, label in (("wake", "절전"), ("in", "확대")):
            src_c = self._zoom_coords.get(f"{kind}_{idx-1}")
            if src_c:
                self._zoom_coords[f"{kind}_{idx}"] = list(src_c)
                copied.append(label)
        if not copied:
            self._status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        data = load_regions()
        data["__zoom__"] = self._zoom_coords
        save_regions(data)
        self._refresh_zoom_ui()
        self._status.set(f"✔ #{idx+1:02d} ← #{idx:02d} 복사 완료 ({'+'.join(copied)})")

    def _del(self, idx):
        self.regions.pop(str(idx), None)
        save_regions(self.regions)
        self._result_vars[idx].set("-")
        self._refresh_ui()

    def _copy_to_clipboard(self):
        values = [v.get() for v in self._result_vars]
        text = "\t".join(values)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status.set(f"✔ 클립보드 복사 완료 ({len(values)}개 — 엑셀에 붙여넣기 하세요)")

    def _clear_all(self):
        if messagebox.askyesno("초기화", "전체 영역을 삭제할까요?"):
            self.regions = {}
            save_regions(self.regions)
            self._refresh_ui()
            for v in self._result_vars:
                v.set("-")

    def _refresh_zoom_ui(self):
        zo = self._zoom_coords.get("out")
        self._zoom_out_var.set(f"({zo[0]},{zo[1]})" if zo else "미등록")
        for i, v in enumerate(self._zoom_in_vars):
            zi = self._zoom_coords.get(f"in_{i}")
            v.set(f"확대({zi[0]},{zi[1]})" if zi else "확대?")
        for i, v in enumerate(self._wake_vars):
            wk = self._zoom_coords.get(f"wake_{i}")
            v.set(f"절전({wk[0]},{wk[1]})" if wk else "절전?")

    def _reg_zoom(self, kind, slot_idx=None):
        if kind == "wake" and slot_idx is not None:
            label = f"#{slot_idx+1:02d} 절전해제"
        else:
            label = {"out": "축소", "wake": "절전해제"}.get(kind, f"#{slot_idx+1:02d} 확대")
        self._do_click_capture(kind, slot_idx, label)

    def _do_click_capture(self, kind, slot_idx, label):
        self._status.set(f"[{label}] 등록할 위치를 클릭하세요 (ESC/취소버튼: 취소)")
        cancelled = [False]
        hint = _HintWin(f"[{label}] 등록할 위치를 클릭하세요  (ESC: 취소)", lambda: cancelled.__setitem__(0, True))
        self.withdraw()
        def _run():
            pos = _capture_click(cancelled)
            self.after(0, lambda: hint.destroy())
            self.after(0, self.deiconify)
            if pos:
                self.after(50, lambda: self._on_zoom_captured(kind, slot_idx, label, pos[0], pos[1]))
            else:
                self.after(50, lambda: self._status.set("취소됨"))
        threading.Thread(target=_run, daemon=True).start()

    def _on_zoom_captured(self, kind, slot_idx, label, x, y):
        if kind == "out":
            key = "out"
        elif kind == "wake":
            key = f"wake_{slot_idx}" if slot_idx is not None else "wake"
        else:
            key = f"in_{slot_idx}"
        self._zoom_coords[key] = [x, y]
        data = load_regions()
        data["__zoom__"] = self._zoom_coords
        save_regions(data)
        self._refresh_zoom_ui()
        self._status.set(f"✔ {label} 좌표 저장: ({x},{y})")

    def _reg_zoom_in(self, idx):
        self._reg_zoom("in", slot_idx=idx)

    def _preview_zoom_out(self):
        zo = self._zoom_coords.get("out")
        if not zo:
            self._status.set("축소 좌표가 등록되지 않았습니다")
            return
        msg = f"축소 좌표: ({zo[0]}, {zo[1]})\n\n클릭하면 닫힙니다"
        messagebox.showinfo("축소 좌표", msg)

    def _group_move(self):
        """절전+확대 좌표 전체를 드래그로 한번에 이동"""
        self.withdraw()
        self.after(300, lambda: GroupMoveOverlay(self))

    def _ocr_region(self, region, save_debug=False, slot_idx=None):
        import time
        from PIL import Image, ImageEnhance
        x, y, w, h = region
        wake_wait   = float(self._wake_wait_var.get()    or "0.8")
        zoom_wait   = float(self._zoom_wait_var.get()    or "2.0")
        zoomout_wait= float(self._zoomout_wait_var.get() or "0.4")

        wk = self._zoom_coords.get(f"wake_{slot_idx}") if slot_idx is not None else None
        zo = self._zoom_coords.get("out")
        zi = self._zoom_coords.get(f"in_{slot_idx}") if slot_idx is not None else None

        # 1. 절전해제
        if wk:
            pyautogui.click(*wk)
            time.sleep(wake_wait)

        # 2. 확대
        if zi:
            pyautogui.click(*zi)
            time.sleep(zoom_wait)

        # 3. 캡처
        img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)

        # 4. 축소
        if zo:
            pyautogui.click(*zo)
            time.sleep(zoomout_wait)

        # 이미지 전처리
        import numpy as np
        import cv2
        from PIL import ImageFilter, ImageEnhance
        img = img.resize((img.width*2, img.height*2), Image.LANCZOS)
        img = img.convert("L")  # 그레이스케일
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        # 슬롯별 캡처(전처리) 이미지 저장 — 메인런처에서 눈으로 숫자 확인용
        if slot_idx is not None:
            try:
                _cd = os.path.join(LOCAL_DATA, "daya_crops")
                os.makedirs(_cd, exist_ok=True)
                img.convert("RGB").save(os.path.join(_cd, f"slot_{slot_idx}.png"))
            except Exception:
                pass
        img_np = np.array(img)
        # 이진화 (숫자 배경 분리)
        _, img_np = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        img = Image.fromarray(img_np).convert("RGB")

        if save_debug:
            img.save(os.path.join(BASE, "ocr_debug.png"))

        img_np = np.array(img)
        reader = get_reader()
        results = reader.readtext(img_np, detail=1, paragraph=False,
                                  allowlist="0123456789.,")

        # 신뢰도 0.2 이상, 왼쪽→오른쪽 순서로 이어붙이기
        valid = [(bbox, txt, conf) for bbox, txt, conf in results
                 if conf >= 0.2 and any(c.isdigit() for c in txt)]
        valid.sort(key=lambda r: r[0][0][0])  # bbox 좌측 x 기준 정렬
        nums = "".join(c for r in valid for c in r[1] if c.isdigit())
        return int(nums) if nums else 0

    def _ocr_with_retry(self, r, idx, retries=1, interval=1.5, save_debug=False):
        import time
        for attempt in range(1, retries+1):
            self.after(0, lambda a=attempt: self._status.set(
                f"#{idx+1:02d} 스캔 중... (시도 {a}/{retries})"))
            val = self._ocr_region(r, save_debug=(save_debug and attempt==1), slot_idx=idx)
            if val > 0:
                return val
            if attempt < retries:
                self.after(0, lambda a=attempt: self._status.set(
                    f"#{idx+1:02d} 미인식 → {interval:.0f}초 후 재시도... ({a}/{retries})"))
                time.sleep(interval)
        return 0

    def _get_common_region(self):
        return self.regions.get("common")

    def _scan_one(self, idx):
        r = self._get_common_region()
        if not r:
            self._status.set("공통 영역이 등록되지 않았습니다 (상단 공통 설정에서 등록)")
            return
        self.withdraw()
        def _run():
            try:
                val = self._ocr_with_retry(r, idx, save_debug=True)
                self._result_vars[idx].set(str(val) if val else "?")
                self._save_count(idx, val)
                self.after(0, lambda: self._status.set(
                    f"✔ #{idx+1:02d} = {val}" if val else f"⚠ #{idx+1:02d} 인식 실패 (ocr_debug.png 확인)"))
            except Exception as e:
                self.after(0, lambda: self._status.set(f"오류: {e}"))
            finally:
                self.after(0, self.deiconify)
        threading.Thread(target=_run, daemon=True).start()

    def _check_capture(self, idx):
        r = self._get_common_region()
        if not r:
            self._status.set("공통 영역이 등록되지 않았습니다")
            return
        x, y, w, h = r
        from PIL import ImageGrab as IG
        img = IG.grab(bbox=(x, y, x+w, y+h), all_screens=True)
        path = os.path.join(BASE, "ocr_debug.png")
        img.save(path)
        self._status.set(f"✔ 저장: {path}")
        import subprocess
        subprocess.Popen(["explorer", path])

    def _scan_all(self, auto=False):
        if getattr(self, "_scanning", False):
            return
        r = self._get_common_region()
        if not r:
            self._status.set("공통 영역이 등록되지 않았습니다")
            return
        self._scanning = True
        self.withdraw()
        _minimize_claude()
        def _run():
            try:
                label = "자동" if auto else "전체"
                self.after(0, lambda: self._status.set(f"{label} 스캔 시작..."))
                counts = load_counts()
                day = today()
                if day not in counts:
                    counts[day] = {}
                for i in range(SLOTS):
                    try:
                        val = self._ocr_with_retry(r, i)
                        self._result_vars[i].set(str(val) if val else "?")
                        counts[day][str(i)] = val
                    except Exception as e:
                        self.after(0, lambda m=f"#{i+1:02d} 오류: {e}": self._status.set(m))
                    import time; time.sleep(1.4)   # 슬롯간 간격 (2.0 → 30% 단축)
                save_counts(counts)
                self.after(0, lambda: self._status.set("✔ 스캔 완료!"))
            finally:
                self._scanning = False
                if getattr(self, "_close_after_scan", False):
                    # 창 없는 즉시실행 모드(--close): 끝나면 메인런처 띄우고 종료
                    _restore_claude()
                    self.after(0, lambda: (self._raise_main_launcher(), self.destroy()))
                else:
                    self.after(0, self.deiconify)
                    _restore_claude()
        threading.Thread(target=_run, daemon=True).start()

    def _toggle_auto(self):
        if getattr(self, "_auto_on", False):
            self._auto_on = False
            self._btn_auto.config(text="⏱ 자동(2분)", bg="#7f8c8d")
            self._status.set("자동 스캔 중지")
        else:
            self._auto_on = True
            self._btn_auto.config(text="⏹ 자동중지", bg="#c0392b")
            self._status.set("자동 스캔 시작 (2분 간격)")
            self._auto_tick()

    def _auto_tick(self):
        if not getattr(self, "_auto_on", False):
            return
        self._scan_all(auto=True)
        self.after(120_000, self._auto_tick)

    def _save_count(self, idx, val):
        counts = load_counts()
        day = today()
        if day not in counts:
            counts[day] = {}
        counts[day][str(idx)] = val
        save_counts(counts)

    def _rescan_and_close(self, idx):
        """단일 슬롯만 OCR 재측정 → 저장 → 메인런처 띄우고 종료 (--slot 모드)."""
        r = self._get_common_region()
        if not r:
            self._raise_main_launcher(); self.destroy(); return
        self._scanning = True
        self.withdraw()
        _minimize_claude()
        def _run():
            try:
                val = self._ocr_with_retry(r, idx)
                self._save_count(idx, val)
            except Exception:
                pass
            finally:
                self._scanning = False
                self.after(0, lambda: (self._raise_main_launcher(), self.destroy()))
        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import sys as _sys
    app = OCRApp()
    if "--scan" in _sys.argv:
        if "--close" in _sys.argv:
            app._close_after_scan = True
            app.withdraw()          # 창 없이 바로 스캔
        app.after(500, app._scan_all)
    elif "--slot" in _sys.argv:
        try:
            _i = int(_sys.argv[_sys.argv.index("--slot") + 1])
        except Exception:
            _i = None
        if _i is not None:
            app.after(400, lambda: app._rescan_and_close(_i))
    app.mainloop()
