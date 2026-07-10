import ctypes
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass

# 기존 인스턴스 종료 후 단일 실행
import subprocess, sys, os as _os
_my_pid = str(_os.getpid())
# 단독 슬롯 모드(인자 있음)에서는 기존 인스턴스를 죽이지 않음
if len(sys.argv) <= 1:
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'pythonw.exe\'" get processid,commandline /format:csv',
            shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore")
        for line in out.splitlines():
            if "lineagem_island" in line.lower():
                parts = line.strip().split(",")
                pid = parts[-1].strip()
                if pid and pid != _my_pid:
                    subprocess.call(f"taskkill /F /PID {pid}", shell=True, stderr=subprocess.DEVNULL)
    except Exception:
        pass
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
import time, threading, json, os
import pyautogui

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
        if d["key"] not in data:
            data[d["key"]] = [{"name": "미등록", "coords": [None]*CLICKS}
                               for _ in range(SLOTS)]
        else:
            # 기존 좌표 배열이 짧으면 CLICKS 길이로 패딩
            for slot in data[d["key"]]:
                coords = slot.get("coords", [])
                while len(coords) < CLICKS:
                    coords.append(None)
                slot["coords"] = coords
    return data

def save_cfg(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class CoordOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.configure(bg="black")
        c = tk.Canvas(self, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        si  = app._reg_slot_idx
        ci  = app._reg_click_idx
        key = app._reg_key
        name = app.cfg[key][si].get("name", f"#{si+1}")
        lbl = f"[{name}]  {CLICK_LABELS[ci]} 위치를 클릭하세요   (ESC: 취소)"
        c.create_text(sw//2, 60, text=lbl, fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

    def _on_click(self, e):
        x, y = e.x, e.y
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
        lbl = f"[{CLICK_LABELS[idx]}] 위치 클릭  ({idx+1}/{CLICKS})  —  ESC: 취소"
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
            d = DUNGEONS[focus_idx]
            self.title(f"🏝 {d['label'].replace(chr(10), ' ')}")
        else:
            self.title("리니지M 섬/던전 실행기")

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        ox = int(sw * 0.03)
        oy = int(sh * 0.03)
        if focus_idx is not None:
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

        self._auto_run = len(sys.argv) > 2 and sys.argv[2] == "--run"

        self._build_ui()
        self.after(300, self._scroll_all_to_bottom)
        self.after(80, self._fit_width)
        if self._auto_run and self._focus_idx is not None:
            key = self._dungeons_to_show[0]["key"]
            self.after(500, lambda: self._start(key))

    def _fit_width(self):
        self.update_idletasks()
        needed = self.winfo_reqwidth() + 10
        h = self.winfo_height()
        self.geometry(f"{needed}x{h}")

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

        for d in self._dungeons_to_show:
            col = tk.Frame(body, bd=2, relief="groove", width=330)
            col.pack(side="left", fill="both", expand=True, padx=4, pady=2)
            col.pack_propagate(False)
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

    def _build_col(self, parent, d):
        key   = d["key"]
        color = d["color"]

        # 대표 버튼
        tk.Button(parent, text=d["label"],
                  font=("맑은 고딕", 11, "bold"), bg=color, fg="white",
                  activebackground=color, height=3, width=14,
                  command=lambda k=key: self._start(k)
                  ).pack(fill="x", padx=4, pady=(6,2))

        stop_btn = tk.Button(parent, text="■ 멈춤",
                  font=("맑은 고딕", 9, "bold"), bg="#c0392b", fg="white",
                  activebackground="#922b21", height=1,
                  command=self._stop, state="disabled")
        stop_btn.pack(fill="x", padx=4, pady=(0,2))
        self._stop_btns[key] = stop_btn

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)

        # 슬롯 스크롤
        outer = tk.Frame(parent); outer.pack(fill="both", expand=True, padx=2)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._slot_canvases.append(canvas)
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(fid, width=e.width))

        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        slots = self.cfg[key]
        for i in range(SLOTS):
            row = tk.Frame(inner, bd=1, relief="groove")
            row.pack(fill="x", padx=2, pady=1)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 7, "bold"),
                     width=3).pack(side="left", padx=(2,0))

            nv = tk.StringVar(value=slots[i].get("name", "미등록"))
            self._name_vars[key].append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 8), width=7)
            ent.pack(side="left", padx=2)
            ent.bind("<FocusOut>", lambda e, k=key, x=i: self._save_name(k, x))
            ent.bind("<Return>",   lambda e, k=key, x=i: self._save_name(k, x))

            cvars = []; cbtns = []
            for j in range(CLICKS):
                cv = tk.StringVar()
                cvars.append(cv)
                cell = tk.Frame(row); cell.pack(side="left", padx=1)
                tk.Label(cell, text=CLICK_LABELS[j],
                         font=("맑은 고딕", 5), fg="#888").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 6),
                                width=3, pady=0,
                                command=lambda k=key, x=i, c=j: self._reg(k, x, c))
                btn.pack()
                cbtns.append(btn)
            self._click_vars[key].append(cvars)
            self._click_btns[key].append(cbtns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _wheel)
            row.bind("<MouseWheel>", _wheel)

            tk.Button(row, text="▶", font=("맑은 고딕", 7), fg="white",
                      bg=color, width=1,
                      command=lambda k=key, x=i: self._test(k, x)
                      ).pack(side="right", padx=(0,1))
            tk.Button(row, text="×", font=("맑은 고딕", 7), fg="red",
                      width=1, command=lambda k=key, x=i: self._del(k, x)
                      ).pack(side="right", padx=1)
            tk.Button(row, text="👁", font=("맑은 고딕", 7),
                      width=1, command=lambda k=key, x=i: self._preview(k, x)
                      ).pack(side="right", padx=1)
            if i > 0:
                tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 6), fg="white",
                          bg="#7d6608", width=5,
                          command=lambda k=key, x=i: self._copy_from_above(k, x)
                          ).pack(side="right", padx=1)

        self._refresh(key)

    def _refresh(self, key):
        slots = self.cfg.get(key, [])
        for i in range(SLOTS):
            if i >= len(slots): break
            self._name_vars[key][i].set(slots[i].get("name", "미등록"))
            coords = slots[i].get("coords", [None]*CLICKS)
            d = next(x for x in DUNGEONS if x["key"] == key)
            for j in range(CLICKS):
                c = coords[j] if j < len(coords) else None
                self._click_vars[key][i][j].set("✔" if c else "등록")
                self._click_btns[key][i][j].config(
                    fg="white" if c else "black",
                    bg=d["color"] if c else "SystemButtonFace"
                )

    def _save_name(self, key, idx):
        name = self._name_vars[key][idx].get().strip() or "미등록"
        self.cfg[key][idx]["name"] = name
        save_cfg(self.cfg)

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
        lbl = CLICK_LABELS[click_idx]
        self._status.set(f"3초 후 슬롯#{slot_idx+1} [{lbl}] 위치 클릭하세요!")
        self.after(3000, self._open_overlay)

    def _open_overlay(self):
        self.withdraw()
        self.after(200, lambda: CoordOverlay(self))

    def on_coord(self, x, y):
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
            self._status.set(f"✔ #{si+1} [{CLICK_LABELS[ci]}] 등록: ({x},{y})")
        except Exception as e:
            self._status.set(f"오류: {e}")
        finally:
            self.deiconify()

    def _copy_from_above(self, key, idx):
        if idx == 0: return
        src = self.cfg[key][idx - 1].get("coords", [])
        if not any(src):
            self._status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        import copy
        self.cfg[key][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg)
        self._refresh(key)
        self._status.set(f"✔ #{idx+1} ← #{idx} 좌표 복사 완료")
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
        self._batch_coords = [None] * CLICKS
        self._batch_idx    = 0
        self._batch_next()

    def _batch_next(self):
        idx = self._batch_idx
        if idx >= CLICKS:
            key = self._batch_key
            for slot in self.cfg[key]:
                slot["coords"] = [list(c) if c else None for c in self._batch_coords]
            save_cfg(self.cfg)
            self._refresh(key)
            self._status.set(f"✔ [{key}] 전체 {SLOTS}슬롯 좌표 적용 완료!")
            self.deiconify()
            return
        lbl = CLICK_LABELS[idx]
        self._status.set(f"3초 후 [{lbl}] 위치를 클릭하세요! ({idx+1}/{CLICKS})")
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
        dots = [(c[0], c[1], n, ci) for n, (ci, c) in enumerate(valid, 1)]
        self.withdraw()
        self.after(1000, lambda: _IslandPreviewOverlay(self, key, idx, dots))

    def _del(self, key, idx):
        from tkinter import messagebox
        if not messagebox.askyesno("삭제 확인", f"#{idx+1} 슬롯 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg[key][idx] = {"name": "미등록", "coords": [None]*CLICKS}
        save_cfg(self.cfg); self._refresh(key)

    def _test(self, key, idx):
        self.iconify()
        threading.Thread(target=self._run, args=(key, idx), daemon=True).start()

    def _start(self, key):
        self._stop_flag  = False
        self._active_key = key
        for k, btn in self._stop_btns.items():
            btn.config(state="normal" if k == key else "disabled")
        self.iconify()
        threading.Thread(target=self._run, args=(key,), daemon=True).start()

    def _stop(self):
        self._stop_flag = True
        self._status.set("멈추는 중...")
        for btn in self._stop_btns.values():
            btn.config(state="disabled")

    def _run(self, key, slot_idx=None):
        try:
            self._status.set("2초 후 실행 시작...")
            time.sleep(2)
            slots = self.cfg.get(key, [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(c for c in s.get("coords", []))]
            d = next(x for x in DUNGEONS if x["key"] == key)
            stop_fn   = lambda: self._stop_flag
            status_fn = lambda m: self.after(0, lambda m=m: self._status.set(m))
            for si, slot in targets:
                if self._stop_flag: break
                if not wait_mouse_idle(stop_fn, status_fn): break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*CLICKS)
                if not any(coords): continue
                move_set = MOVE_ONLY_INDICES.get(key, set())
                for j, lbl in enumerate(CLICK_LABELS):
                    if self._stop_flag: break
                    if not coords[j]: continue
                    self._status.set(f"🏝 [{name}] {lbl}...")
                    if j in move_set:
                        pyautogui.moveTo(*coords[j])
                    else:
                        pyautogui.click(*coords[j])
                    time.sleep(CLICK_INTERVAL)
                self._add_count(si)
                if self._stop_flag: break
                time.sleep(5)
            self._status.set("✔ 실행 완료!")
        except Exception as e:
            self._status.set(f"오류: {e}")
        finally:
            for btn in self._stop_btns.values():
                btn.config(state="disabled")
            def _restore():
                self.attributes("-topmost", True)
                self.deiconify()
                self.lift()
                self.focus_force()
                self.after(3000, lambda: self.attributes("-topmost", False))
            self.after(0, _restore)


class _IslandGroupMoveOverlay(tk.Toplevel):
    """복사한 슬롯 좌표 전체를 그룹 드래그로 이동 후 저장"""
    R = 10

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
                           font=("맑은 고딕", 8, "bold"))

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
    R = 10

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
                           font=("맑은 고딕", 8, "bold"))

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
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self._last = (e.x, e.y)
        self._dots[self._drag][0] += dx
        self._dots[self._drag][1] += dy
        self._draw()

    def _on_release(self, e):
        if self._drag is not None and self._moved:
            x, y, num, ci = self._dots[self._drag]
            self.app.cfg[self.key][self.slot_idx]["coords"][ci] = [x, y]
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

