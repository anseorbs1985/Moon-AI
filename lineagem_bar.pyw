"""
lineagem_bar.pyw — 섬/던전 4개(에카·잊섬·악몽·오만)만 쓰는 작은 런처 (2026-08-24)

메인런처가 크고 무거워서, 자주 쓰는 네 던전의 **슬롯 실행**만 뺀 창.
  · 위: 던전 고르는 탭 + [⌖ 좌표창] [▶ 전체실행]
  · 아래: 그 던전의 4×4 슬롯 — 누르면 그 슬롯만 실행
  · ◐ 로 '섬/던전 실행기 창'의 투명도 (뒤가 비쳐 보이게), ≡ 로 이동, ✕ 로 닫기
물약·층수·프리셋 같은 설정은 **메인런처/던전 창 그대로** — 여기서는 실행만 한다.
설정 저장: LOCALAPPDATA/MoonAI/bar.json (위치), ui.json (던전창 투명도)
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
LOGF   = os.path.join(LOCAL, "repeat_log.txt")
ISLAND = os.path.join(BASE, "lineagem_island.py")
COORDS = os.path.join(BASE, "island_coords.json")

# (던전번호, 이름, 색, island_coords.json 의 키) — 메인런처와 같은 번호
DUNS = [
    (3, "에카", "#27ae60", "화요일_에카"),
    (2, "잊섬", "#2980b9", "월요일_잊혀진섬"),
    (1, "악몽", "#8e44ad", "토요일_악몽의섬"),
    (0, "오만", "#e67e22", "수금_오만의탑"),
]
ALPHAS = [1.0, 0.85, 0.7, 0.55, 0.4]
NIGHT_KEY = "토요일_악몽의섬"      # 실행하면 2시간 6회 반복이 걸리는 던전
NIGHT_H, NIGHT_N = 2, 6


def jload(path, d=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or (d if d is not None else {})
    except Exception:
        return d if d is not None else {}


def jsave(path, d):
    try:
        os.makedirs(LOCAL, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def rlog(msg):
    try:
        os.makedirs(LOCAL, exist_ok=True)
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%m-%d %H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


class Bar(tk.Tk):
    BG, BG2, FG, DIM = "#23272e", "#2b3038", "#e6e6e6", "#9aa4b0"

    def __init__(self):
        super().__init__()
        self.cfg = jload(CFG)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.BG)
        self.cur = int(self.cfg.get("dun", 2))       # 마지막에 보던 던전 탭
        self._drag = None
        self._build()
        self._show(self.cur)
        self._place()

    # ── 화면 ────────────────────────────────────────────────────────
    def _build(self):
        pad = tk.Frame(self, bg=self.BG, highlightbackground="#d6dde5",
                       highlightthickness=1)
        pad.pack(fill="both", expand=True)

        top = tk.Frame(pad, bg=self.BG)
        top.pack(fill="x", padx=3, pady=(3, 0))
        grip = tk.Label(top, text="≡", font=("맑은 고딕", 10, "bold"),
                        bg=self.BG, fg=self.DIM, cursor="fleur")
        grip.pack(side="left", padx=(0, 4))
        for w in (grip, top, pad, self):
            w.bind("<Button-1>", self._grab)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._drop)

        self.tabs = []
        for i, (idx, name, col, key) in enumerate(DUNS):
            b = tk.Button(top, text=name, font=("맑은 고딕", 8, "bold"),
                          bd=0, width=5, pady=2,
                          command=lambda k=i: self._show(k))
            b.pack(side="left", padx=1)
            self.tabs.append(b)

        _a = int(float(jload(UI).get("island_alpha", 1.0)) * 100)
        self.abtn = tk.Button(top, text=f"◐{_a}", font=("맑은 고딕", 8, "bold"),
                              bg="#566573", fg="white", bd=0, width=5, pady=2,
                              command=self._cycle_alpha)
        self.abtn.pack(side="left", padx=(6, 0))
        tk.Button(top, text="✕", font=("맑은 고딕", 8, "bold"), bg="#c0392b",
                  fg="white", bd=0, width=3, pady=2,
                  command=self._quit).pack(side="left", padx=(3, 0))

        act = tk.Frame(pad, bg=self.BG)
        act.pack(fill="x", padx=3, pady=(3, 0))
        tk.Button(act, text="⌖ 좌표창", font=("맑은 고딕", 8, "bold"),
                  bg="#3a4149", fg=self.FG, bd=0, pady=2,
                  command=self._open_win).pack(side="left")
        self.runall = tk.Button(act, text="▶ 전체실행", font=("맑은 고딕", 8, "bold"),
                                fg="white", bd=0, pady=2, command=self._run_all)
        self.runall.pack(side="left", padx=(3, 0))
        tk.Button(act, text="↻", font=("맑은 고딕", 8, "bold"), bg="#566573",
                  fg="white", bd=0, width=3, pady=2,
                  command=lambda: self._show(self.cur)).pack(side="left", padx=(3, 0))

        self.grid_f = tk.Frame(pad, bg=self.BG)
        self.grid_f.pack(padx=3, pady=3)
        self.slots = []
        for i in range(16):
            b = tk.Button(self.grid_f, font=("맑은 고딕", 8, "bold"), bd=0,
                          width=4, pady=2,
                          command=lambda x=i: self._run_slot(x))
            b.grid(row=i % 4, column=i // 4, padx=1, pady=1)
            self.slots.append(b)

        self.lbl = tk.Label(pad, text="", font=("맑은 고딕", 7), bg=self.BG,
                            fg=self.DIM, anchor="w")
        self.lbl.pack(fill="x", padx=4, pady=(0, 3))

    def _show(self, tab_i):
        """탭 바꾸기 — 그 던전의 슬롯 상태(좌표 등록·반복 남은 횟수)를 보여준다."""
        self.cur = tab_i
        self.cfg["dun"] = tab_i
        jsave(CFG, self.cfg)
        idx, name, col, key = DUNS[tab_i]
        for i, b in enumerate(self.tabs):
            on = (i == tab_i)
            b.config(bg=DUNS[i][2] if on else "#3a4149",
                     fg="white" if on else self.DIM)
        self.runall.config(bg=col, activebackground=col)
        slots = jload(COORDS).get(key) or []
        st = jload(REPF)
        live = 0
        for i, b in enumerate(self.slots):
            s = slots[i] if i < len(slots) else None
            has = bool(s and any(s.get("coords") or []))
            e = st.get(f"{key}|{i}")
            if not has:
                b.config(text="·", bg=self.BG2, fg="#555", state="disabled")
                continue
            live += 1
            if e:
                b.config(text=f"{i+1:02d}·{int(e.get('left', 0))}",
                         bg="#1e8449", fg="white", state="normal")
            else:
                b.config(text=f"{i+1:02d}", bg="#3a4149", fg=self.FG, state="normal")
        self.lbl.config(text=f"{name} — 좌표 있는 슬롯 {live}개 "
                             f"(초록=반복 걸림·남은횟수)")
        self.after(50, self._place)

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

    # ── 기능 ────────────────────────────────────────────────────────
    def _cycle_alpha(self):
        ui = jload(UI)
        cur = float(ui.get("island_alpha", 1.0))
        nxt = ALPHAS[(ALPHAS.index(min(ALPHAS, key=lambda a: abs(a - cur))) + 1)
                     % len(ALPHAS)]
        ui["island_alpha"] = nxt
        jsave(UI, ui)
        self.abtn.config(text=f"◐{int(nxt*100)}")
        self.lbl.config(text=f"던전 창 투명도 {int(nxt*100)}% "
                             f"(다음에 여는 창부터 적용)")

    def _spawn(self, args):
        try:
            subprocess.Popen(["pythonw", ISLAND] + args)
            return True
        except Exception as e:
            self.lbl.config(text=f"실행 실패: {e}")
            return False

    def _arm_night(self, key, idxs):
        """악몽의섬은 실행하면 2시간 6회 반복이 걸린다 (메인런처와 같은 규칙).
        다른 던전은 건드리지 않는다."""
        if key != NIGHT_KEY or not idxs:
            return
        st = jload(REPF)
        st.pop("_off", None)
        now = time.time()
        for i in idxs:
            st[f"{key}|{i}"] = {"h": NIGHT_H, "left": max(0, NIGHT_N - 1), "run": 1,
                                "next": now + NIGHT_H * 3600
                                        + random.uniform(2, 7) * 60}
            md = st.get("_mode") or {}
            md[f"{key}|{i}"] = "h2"
            st["_mode"] = md
        jsave(REPF, st)
        # 설정에도 주기를 되살린다 — 안 그러면 관리자가 '꺼진 슬롯'으로 보고 지운다
        cfg = jload(COORDS)
        for i in idxs:
            try:
                cfg[key][i]["repeat_h"] = NIGHT_H
                cfg[key][i]["repeat_n"] = NIGHT_N
            except Exception:
                pass
        jsave(COORDS, cfg)
        rlog(f"{key} — 막대런처 실행 {[i+1 for i in idxs]} "
             f"({NIGHT_H}시간 {NIGHT_N}회, 남은 {NIGHT_N-1}회) (사용자)")

    def _run_slot(self, i):
        idx, name, col, key = DUNS[self.cur]
        if self._spawn([str(idx), "--run", "--slot", str(i + 1)]):
            self._arm_night(key, [i])
            self.lbl.config(text=f"{name} #{i+1:02d} 실행")
            self.after(1500, lambda: self._show(self.cur))

    def _run_all(self):
        idx, name, col, key = DUNS[self.cur]
        slots = jload(COORDS).get(key) or []
        sel = [i for i, s in enumerate(slots[:16])
               if isinstance(s, dict) and any(s.get("coords") or [])]
        if not sel:
            self.lbl.config(text=f"{name} — 좌표가 등록된 슬롯이 없습니다")
            return
        args = [str(idx), "--run", "--slots", ",".join(str(i + 1) for i in sel),
                "--lanes", "2"]
        if self._spawn(args):
            self._arm_night(key, sel)
            self.lbl.config(text=f"{name} 전체실행 — {len(sel)}슬롯")
            self.after(1500, lambda: self._show(self.cur))

    def _open_win(self):
        idx, name, col, key = DUNS[self.cur]
        if self._spawn([str(idx)]):
            self.lbl.config(text=f"{name} 좌표·설정 창 열림 (실행 안 함)")

    def _quit(self):
        self.cfg["x"], self.cfg["y"] = self.winfo_x(), self.winfo_y()
        jsave(CFG, self.cfg)
        self.destroy()


if __name__ == "__main__":
    Bar().mainloop()
