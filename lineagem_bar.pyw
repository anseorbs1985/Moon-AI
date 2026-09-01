"""
lineagem_bar.pyw — 요약 런처 (2026-08-24 사용자 요청)

메인런처 전체를 켜지 않고, **메인런처의 악몽의섬 판 딱 그 정도**만 띄운다.
  · 탭: 악몽의섬 / 에카 / 잊혀진섬 / 오만의탑
  · 슬롯마다  [실행] · [⏰ 2h n회][✕] · [+ 선택]
  · [✔ 전체선택] [▶ 선택실행] [선택해제] / 악몽의섬은 [🔄 초기화] [⏰ 2h 6회]
  · ◐ 로 '섬/던전 실행기 창' 투명도, ≡ 로 이동, ✕ 로 닫기
좌표·물약·층수·프리셋 등 설정은 **각 던전 창 그대로** — 여기서는 실행/반복만 다룬다.
저장: LOCALAPPDATA/MoonAI/bar.json(위치·탭), ui.json(던전창 투명도),
      island_repeat.json(반복 — 메인런처와 같은 파일)
"""
import os
import json
import time
import random
import subprocess
import tkinter as tk

BASE   = os.path.dirname(os.path.abspath(__file__))
LOCAL  = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
CFG    = os.path.join(LOCAL, "bar.json")
UI     = os.path.join(LOCAL, "ui.json")
REPF   = os.path.join(LOCAL, "island_repeat.json")
RUNF   = os.path.join(LOCAL, "island_run.json")     # 실행 중 표시 (섬 실행기가 남긴다)
LOGF   = os.path.join(LOCAL, "repeat_log.txt")
ISLAND = os.path.join(BASE, "lineagem_island.py")
COORDS = os.path.join(BASE, "island_coords.json")

# (던전번호, 이름, 키, 색) — 메인런처 DUN_TABS 와 같은 순서
DUNS = [(1, "악몽의섬", "토요일_악몽의섬", "#8e44ad"),
        (3, "에카",     "화요일_에카",     "#27ae60"),
        (2, "잊혀진섬", "월요일_잊혀진섬", "#2980b9"),
        (0, "오만의탑", "수금_오만의탑",   "#e67e22")]
NIGHT = "토요일_악몽의섬"
NH, NN = 2, 6                       # 악몽의섬 — 2시간 6회
ALPHAS = [1.0, 0.85, 0.7, 0.55, 0.4]
LEFT_COLORS = {6: "#1e8449", 5: "#27ae60", 4: "#16a085",
               3: "#2980b9", 2: "#8e44ad", 1: "#c0392b"}


def jload(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) or (d if d is not None else {})
    except Exception:
        return d if d is not None else {}


def jsave(p, d):
    try:
        os.makedirs(LOCAL, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass


def rlog(m):
    try:
        os.makedirs(LOCAL, exist_ok=True)
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%m-%d %H:%M:%S] ") + m + "\n")
    except Exception:
        pass


class Bar(tk.Tk):
    BG, BG2, FG, DIM = "#23272e", "#2b3038", "#e6e6e6", "#9aa4b0"

    def __init__(self):
        super().__init__()
        self.cfg = jload(CFG)
        self.overrideredirect(True)
        # 항상 위로 두지 않는다 — 다른 창을 누르면 뒤로 물러난다 (2026-08-24 사용자 지시).
        # 다시 보고 싶으면 메인런처의 [📏 요약런처] 버튼을 누른다.
        self.attributes("-topmost", False)
        self.configure(bg=self.BG)
        self.tab = int(self.cfg.get("tab", 0) or 0)
        self.sel = set()
        self.queue = []           # 실행 중이면 여기에 쌓아둔다
        self.proc = None
        self._drag = None
        self.cfg["pid"] = os.getpid()      # 메인런처가 '이미 떠 있나' 확인할 때 쓴다
        jsave(CFG, self.cfg)
        self._build()
        self._show(self.tab)
        self._place()
        self.after(20000, self._tick)
        self.after(1000, self._raise_watch)
        self.bind("<Button-1>", self._touch, add="+")
        self.bind("<FocusOut>", lambda _e: self._maybe_back(), add="+")

    # ── 화면 ────────────────────────────────────────────────────────
    def _build(self):
        pad = tk.Frame(self, bg=self.BG, highlightbackground="#d6dde5",
                       highlightthickness=1)
        pad.pack(fill="both", expand=True)

        top = tk.Frame(pad, bg=self.BG); top.pack(fill="x", padx=3, pady=(3, 0))
        grip = tk.Label(top, text="≡", font=("맑은 고딕", 10, "bold"),
                        bg=self.BG, fg=self.DIM, cursor="fleur")
        grip.pack(side="left", padx=(0, 4))
        for w in (grip, top, pad, self):
            w.bind("<Button-1>", self._grab)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._drop)

        self.tabs = []
        for i, (_d, name, _k, _c) in enumerate(DUNS):
            b = tk.Button(top, text=name, font=("맑은 고딕", 8, "bold"), bd=0,
                          padx=5, pady=2, command=lambda k=i: self._show(k))
            b.pack(side="left", padx=1)
            self.tabs.append(b)
        _a = int(float(jload(UI).get("island_alpha", 1.0)) * 100)
        self.abtn = tk.Button(top, text=f"◐{_a}", font=("맑은 고딕", 8, "bold"),
                              bg="#566573", fg="white", bd=0, padx=4, pady=2,
                              command=self._alpha)
        self.abtn.pack(side="left", padx=(6, 0))
        tk.Button(top, text="✕", font=("맑은 고딕", 8, "bold"), bg="#c0392b",
                  fg="white", bd=0, padx=5, pady=2,
                  command=self._quit).pack(side="left", padx=(3, 0))

        r1 = tk.Frame(pad, bg=self.BG); r1.pack(fill="x", padx=3, pady=(3, 0))
        tk.Button(r1, text="✔ 전체선택", font=("맑은 고딕", 8, "bold"), bd=0,
                  bg="#e67e22", fg="white", pady=2,
                  command=self._sel_all).pack(side="left")
        tk.Button(r1, text="▶ 선택실행", font=("맑은 고딕", 8, "bold"), bd=0,
                  bg="#1e8449", fg="white", pady=2,
                  command=self._run_sel).pack(side="left", padx=3)
        tk.Button(r1, text="해제", font=("맑은 고딕", 8), bd=0,
                  bg="#7f8c8d", fg="white", pady=2,
                  command=self._sel_clear).pack(side="left")
        tk.Button(r1, text="⌖", font=("맑은 고딕", 8, "bold"), bd=0,
                  bg="#3a4149", fg=self.FG, padx=5, pady=2,
                  command=self._open_win).pack(side="left", padx=(3, 0))

        self.r2 = tk.Frame(pad, bg=self.BG); self.r2.pack(fill="x", padx=3, pady=(2, 0))
        self.b_reset = tk.Button(self.r2, text="🔄 초기화", font=("맑은 고딕", 8, "bold"),
                                 bd=0, bg="#196f3d", fg="white", pady=2,
                                 command=lambda: self._rearm(True))
        self.b_2h = tk.Button(self.r2, text="⏰ 2h 6회", font=("맑은 고딕", 8, "bold"),
                              bd=0, bg="#1f618d", fg="white", pady=2,
                              command=lambda: self._rearm(False))

        gf = tk.Frame(pad, bg=self.BG); gf.pack(padx=3, pady=3)
        self.cells = []
        for i in range(16):
            c = tk.Frame(gf, bg=self.BG)
            c.grid(row=i % 4, column=i // 4, padx=2, pady=1)
            run = tk.Button(c, text="실행", font=("맑은 고딕", 7, "bold"), bd=0,
                            bg="#2471a3", fg="white", width=7,
                            command=lambda x=i: self._run_one(x))
            run.pack()
            rr = tk.Frame(c, bg=self.BG); rr.pack(pady=(1, 0))
            rep = tk.Button(rr, text="⏰", font=("맑은 고딕", 7, "bold"), bd=0,
                            bg="#7f8c8d", fg="white", width=5,
                            command=lambda x=i: self._rep_toggle(x))
            rep.pack(side="left")
            can = tk.Button(rr, text="✕", font=("맑은 고딕", 7, "bold"), bd=0,
                            bg="#c0392b", fg="white", width=1,
                            command=lambda x=i: self._rep_cancel(x))
            can.pack(side="left", padx=(1, 0))
            mode = tk.Button(c, font=("맑은 고딕", 7, "bold"), bd=0, width=7,
                             command=lambda x=i: self._mode_toggle(x))
            mode.pack(pady=(1, 0))
            plus = tk.Button(c, text="+", font=("맑은 고딕", 7, "bold"), bd=0,
                             bg="#3a4149", fg="#e67e22", width=7,
                             command=lambda x=i: self._sel_toggle(x))
            plus.pack(pady=(1, 0))
            self.cells.append((run, rep, plus, mode))

        self.lbl = tk.Label(pad, text="", font=("맑은 고딕", 7), bg=self.BG,
                            fg=self.DIM, anchor="w")
        self.lbl.pack(fill="x", padx=4, pady=(0, 3))

    # ── 상태 ────────────────────────────────────────────────────────
    def _cur(self):
        return DUNS[self.tab]

    def _slots(self):
        return jload(COORDS).get(self._cur()[2]) or []

    def _show(self, t):
        self.tab = t
        self.cfg["tab"] = t
        jsave(CFG, self.cfg)
        self.sel = set()
        didx, name, key, col = DUNS[t]
        for i, b in enumerate(self.tabs):
            on = (i == t)
            b.config(bg=DUNS[i][3] if on else "#3a4149",
                     fg="white" if on else self.DIM)
        # 초기화 버튼은 악몽의섬에서만
        if key == NIGHT:
            self.b_reset.pack(side="left")
            self.b_2h.pack(side="left", padx=(3, 0))
        else:
            self.b_reset.pack_forget()
            self.b_2h.pack_forget()
        self._refresh()
        self.after(30, self._place)

    def _refresh(self):
        key = self._cur()[2]
        slots, st = self._slots(), jload(REPF)
        live = 0
        for i, (run, rep, plus, mode) in enumerate(self.cells):
            s = slots[i] if i < len(slots) else None
            has = bool(s and any(s.get("coords") or []))
            for w in (run, rep, plus, mode):
                w.config(state=("normal" if has else "disabled"))
            if not has:
                run.config(text="·", bg=self.BG2)
                rep.config(text="", bg=self.BG2)
                plus.config(text="", bg=self.BG2)
                mode.config(text="", bg=self.BG2)
                continue
            if key == NIGHT:            # 첫 대기 방식 — 악몽의섬만
                m = (st.get("_mode") or {}).get(f"{key}|{i}", "first")
                if m == "h2":
                    mode.config(text="2h마다", bg="#1f618d", fg="white")
                else:
                    mode.config(text="4h→2h", bg="#196f3d", fg="white")
            else:
                mode.config(text="—", bg=self.BG2, fg=self.DIM)
            live += 1
            q = [n for n, (_a, _l, ix) in enumerate(self.queue, 1) if i in ix]
            if q:
                run.config(text=f"대기{q[0]}", bg="#e67e22")
            else:
                run.config(text=f"{i+1:02d} 실행", bg="#2471a3")
            e = st.get(f"{key}|{i}")
            if e:
                n = int(e.get("left", 0))
                rep.config(text=f"{int(e.get('h', 2))}h {n}회",
                           bg=LEFT_COLORS.get(n, "#34495e"))
            else:
                rep.config(text="⏰꺼짐", bg="#7f8c8d")
            on = i in self.sel
            plus.config(text="✔" if on else "+",
                        bg="#e67e22" if on else "#3a4149",
                        fg="white" if on else "#e67e22")
        self.lbl.config(text=f"{self._cur()[1]} — 좌표 {live}개"
                             + (f" · 선택 {sorted(x+1 for x in self.sel)}" if self.sel else ""))

    def _tick(self):
        """반복·좌표 파일이 **바뀌면 곧바로** 화면을 맞춘다 (2026-08-29 사용자 지시).

        예전엔 20초마다 통째로 새로 그려서, 메인런처에서 ⏰ 를 꺼도
        작은 런처에는 한참 뒤에야 반영됐다. 이제 **1초마다 파일 시각만 보고**,
        바뀌었을 때만 다시 그린다 (부하 거의 없음)."""
        try:
            import os as _os
            _m = 0.0
            for _f in (REPF, COORDS):
                try:
                    _m += _os.path.getmtime(_f)
                except Exception:
                    pass
            if _m != getattr(self, "_sync_mtime", None):
                self._sync_mtime = _m
                self._refresh()
        except Exception:
            try:
                self._refresh()
            except Exception:
                pass
        self.after(1000, self._tick)

    def _place(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            x = (self.winfo_screenwidth() - w) // 2
            y = self.winfo_screenheight() - h - 60
        self.geometry(f"{w}x{h}+{int(x)}+{int(y)}")

    # ── 이동 ────────────────────────────────────────────────────────
    def _grab(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _move(self, e):
        if self._drag:
            dx, dy = self._drag
            self.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _drop(self, _e):
        self._drag = None
        self.cfg["x"], self.cfg["y"] = self.winfo_x(), self.winfo_y()
        jsave(CFG, self.cfg)

    # ── 선택 ────────────────────────────────────────────────────────
    def _sel_toggle(self, i):
        self.sel.discard(i) if i in self.sel else self.sel.add(i)
        self._refresh()

    def _sel_all(self):
        able = {i for i, s in enumerate(self._slots()[:16])
                if isinstance(s, dict) and any(s.get("coords") or [])}
        self.sel = set() if self.sel >= able and able else able
        self._refresh()

    def _sel_clear(self):
        self.sel = set()
        self._refresh()

    # ── 반복 (메인런처와 같은 규칙) ─────────────────────────────────
    def _arm(self, idxs):
        """실행하면 반복이 걸린다 — 악몽의섬만 2시간 6회.
        다른 던전은 사용자가 ⏰ 를 켜둔 슬롯만 (여기서 새로 켜지 않는다)."""
        key = self._cur()[2]
        if key != NIGHT or not idxs:
            return
        st = jload(REPF)
        st.pop("_off", None)
        md = st.get("_mode") or {}
        now = time.time()
        for i in idxs:
            st[f"{key}|{i}"] = {"h": NH, "left": max(0, NN - 1), "run": 1,
                                "next": now + NH * 3600 + random.uniform(2, 7) * 60}
            md[f"{key}|{i}"] = "h2"
        st["_mode"] = md
        jsave(REPF, st)
        cfg = jload(COORDS)                 # 주기도 되살린다 (안 그러면 관리자가 지운다)
        for i in idxs:
            try:
                cfg[key][i]["repeat_h"] = NH
                cfg[key][i]["repeat_n"] = NN
            except Exception:
                pass
        jsave(COORDS, cfg)
        rlog(f"{key} — 요약런처 실행 {[i+1 for i in idxs]} "
             f"({NH}시간 {NN}회, 남은 {NN-1}회) (사용자)")

    def _rep_toggle(self, i):
        """그 슬롯 반복 끄기 / 다시 켜기 (악몽의섬만 새로 켤 수 있다)."""
        key = self._cur()[2]
        st = jload(REPF)
        k = f"{key}|{i}"
        if k in st:
            st.pop(k, None)
            jsave(REPF, st)
            rlog(f"{key} #{i+1:02d} 반복 끔 (요약런처·사용자)")
        elif key == NIGHT:
            self._arm([i])
            st = jload(REPF)
            e = st.get(k) or {}
            e["left"], e["run"] = NN, 0        # 실행한 게 아니라 켜기만 한 것
            e["next"] = time.time() + NH * 3600
            st[k] = e
            jsave(REPF, st)
        else:
            self.lbl.config(text="이 던전은 던전 창에서 ⏰ 를 켜주세요")
            return
        self._refresh()

    def _mode_toggle(self, i):
        """첫 대기 방식 — [4h→2h] ↔ [2h마다] (악몽의섬만). 반복을 켜지는 않는다."""
        key = self._cur()[2]
        if key != NIGHT:
            self.lbl.config(text="첫 대기 선택은 악몽의섬만 있습니다")
            return
        st = jload(REPF)
        md, fd = st.get("_mode") or {}, st.get("_first") or {}
        k = f"{key}|{i}"
        nxt = "h2" if md.get(k, "first") == "first" else "first"
        md[k], fd[k] = nxt, (nxt == "first")
        st["_mode"], st["_first"] = md, fd
        e = st.get(k)
        if e and not int(e.get("run", 0)):     # 아직 안 돈 예약이면 시각도 맞춘다
            e["next"] = time.time() + (4 if nxt == "first" else NH) * 3600
            st[k] = e
        jsave(REPF, st)
        rlog(f"{key} #{i+1:02d} "
             + ("4h→2h" if nxt == "first" else "2h마다") + " 로 변경 (요약런처)")
        self._refresh()

    def _rep_cancel(self, i):
        key = self._cur()[2]
        st = jload(REPF)
        st.pop(f"{key}|{i}", None)
        jsave(REPF, st)
        cfg = jload(COORDS)
        try:
            cfg[key][i]["repeat_h"] = 0
            jsave(COORDS, cfg)
        except Exception:
            pass
        rlog(f"{key} #{i+1:02d} 반복 취소 ✕ (요약런처·사용자)")
        self._refresh()

    def _rearm(self, first_4h):
        """악몽의섬 설정만 기본값으로 (예약은 지운다 — 반복은 실행할 때 걸린다)."""
        key = self._cur()[2]
        if key != NIGHT:
            return
        st = jload(REPF)
        md, fd = st.get("_mode") or {}, st.get("_first") or {}
        cfg = jload(COORDS)
        cnt = 0
        for i, s in enumerate(self._slots()[:16]):
            if not (isinstance(s, dict) and any(s.get("coords") or [])):
                continue
            st.pop(f"{key}|{i}", None)
            md[f"{key}|{i}"] = "first" if first_4h else "h2"
            fd[f"{key}|{i}"] = bool(first_4h)
            try:
                cfg[key][i]["repeat_h"] = NH
                cfg[key][i]["repeat_n"] = NN
            except Exception:
                pass
            cnt += 1
        st["_mode"], st["_first"] = md, fd
        jsave(REPF, st)
        jsave(COORDS, cfg)
        rlog(f"{key} — 요약런처 설정 초기화 "
             f"({'4시간 → 2시간' if first_4h else '2시간'} {NN}회). 반복은 켜지 않음 (사용자)")
        self.lbl.config(text=f"설정 초기화 — {cnt}개 슬롯 "
                             f"({'4h→2h' if first_4h else '2h'} {NN}회). 실행하면 걸립니다")
        self._refresh()

    # ── 실행 ────────────────────────────────────────────────────────
    def _touch(self, _e=None):
        """이 창을 누르면 앞으로 올라온다."""
        try:
            self.lift()
        except Exception:
            pass

    def _maybe_back(self):
        """다른 창을 누르면 뒤로 물러난다 (실행 중이면 이미 뒤에 있다)."""
        try:
            self.lower()
        except Exception:
            pass

    def _raise_watch(self):
        """메인런처가 [📏 요약런처] 를 다시 누르면 이 창을 앞으로 올린다."""
        try:
            r = float(jload(CFG).get("raise") or 0)
            if r > float(getattr(self, "_last_raise", 0)):
                self._last_raise = r
                self.deiconify()
                self.lift()
                self.attributes("-topmost", True)
                self.after(400, lambda: self.attributes("-topmost", False))
        except Exception:
            pass
        self.after(1000, self._raise_watch)

    def _to_back(self):
        """실행 중에는 맨 뒤로 — 항상 위로 떠 있으면 좌표 클릭을 이 창이 먹는다."""
        try:
            self.lower()
        except Exception:
            pass
        if not getattr(self, "_wait_done", False):
            self._wait_done = True
            self.after(3000, self._back_watch)

    def _back_watch(self):
        """실행이 끝나면 다시 앞(항상 위)으로 돌려놓는다."""
        if self._busy() or self.queue:
            self.after(4000, self._back_watch)
            return
        self._wait_done = False
        try:
            self.lift()          # 끝나면 다시 보이게 (항상 위로 두지는 않는다)
        except Exception:
            pass
        self.lbl.config(text="✔ 실행 완료 — 창을 다시 앞으로")
        self._refresh()

    def _busy(self):
        """지금 섬/던전 실행기가 돌고 있나 — 표시 파일 하나만 본다(즉시).
        (예전엔 wmic 로 프로세스를 뒤져서 버튼이 1~3초씩 멈췄다)"""
        if self.proc and self.proc.poll() is None:
            return True
        d = jload(RUNF)
        pid = int(d.get("pid") or 0)
        if not pid:
            return False
        try:      # 그 번호의 프로세스가 아직 살아 있나 (커널에 바로 물어본다)
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return bool(ok and code.value == 259)      # STILL_ACTIVE
        except Exception:
            return False

    def _spawn(self, args, label="", idxs=None):
        """실행 중이면 대기열에 쌓았다가 끝난 뒤 하나씩 (겹쳐 돌면 클릭이 엉킨다)."""
        if self._busy():
            self.queue.append((args, label, tuple(idxs or ())))
            self.lbl.config(text=f"실행 중 — 대기열에 넣음 ({len(self.queue)}개 대기)")
            self._watch_queue()
            return False
        try:
            self.proc = subprocess.Popen(["pythonw", ISLAND] + args)
            return True
        except Exception as e:
            self.lbl.config(text=f"실행 실패: {e}")
            return False

    def _watch_queue(self):
        """앞 작업이 끝나면 대기열의 다음 것을 돌린다."""
        if getattr(self, "_watching", False):
            return
        self._watching = True

        def tick():
            if not self.queue:
                self._watching = False
                return
            if self._busy():
                self.after(4000, tick)
                return
            args, label, _ix = self.queue.pop(0)
            try:
                self.proc = subprocess.Popen(["pythonw", ISLAND] + args)
                self.lbl.config(text=f"대기열 실행 — {label} (남은 {len(self.queue)}개)")
                self._to_back()
                self._refresh()
            except Exception as e:
                self.lbl.config(text=f"대기열 실행 실패: {e}")
            self.after(6000, tick)
        self.after(2000, tick)

    def _run_one(self, i):
        didx, name, key, _c = self._cur()
        ran = self._spawn([str(didx), "--run", "--slot", str(i + 1)],
                          f"{name} #{i+1:02d}", [i])
        self._arm([i])
        if ran:
            self.lbl.config(text=f"{name} #{i+1:02d} 실행")
            self._to_back()
        self.after(1500, self._refresh)

    def _run_sel(self):
        didx, name, key, _c = self._cur()
        sel = sorted(self.sel)
        if not sel:
            self.lbl.config(text="슬롯을 고르세요 ([+] 또는 [✔ 전체선택])")
            return
        ran = self._spawn([str(didx), "--run", "--slots",
                           ",".join(str(i + 1) for i in sel), "--lanes", "2"],
                          f"{name} {len(sel)}슬롯", sel)
        self._arm(sel)
        self.sel = set()
        if ran:
            self.lbl.config(text=f"{name} 선택실행 — {len(sel)}슬롯")
            self._to_back()
        self.after(1500, self._refresh)

    def _open_win(self):
        didx, name, _k, _c = self._cur()
        if self._spawn([str(didx)]):
            self.lbl.config(text=f"{name} 좌표·설정 창 열림 (실행 안 함)")

    def _alpha(self):
        ui = jload(UI)
        cur = float(ui.get("island_alpha", 1.0))
        nxt = ALPHAS[(ALPHAS.index(min(ALPHAS, key=lambda a: abs(a - cur))) + 1)
                     % len(ALPHAS)]
        ui["island_alpha"] = nxt
        jsave(UI, ui)
        self.abtn.config(text=f"◐{int(nxt*100)}")
        self.lbl.config(text=f"던전 창 투명도 {int(nxt*100)}%")

    def _quit(self):
        """창만 닫는다 — 돌던 작업·⏰ 반복은 그대로 둔다."""
        self.cfg["x"], self.cfg["y"] = self.winfo_x(), self.winfo_y()
        self.cfg["pid"] = 0
        jsave(CFG, self.cfg)
        self.destroy()


if __name__ == "__main__":
    Bar().mainloop()
