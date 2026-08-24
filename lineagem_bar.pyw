"""
lineagem_bar.pyw — 섬/던전 4개만 쓰는 얇은 막대 런처 (2026-08-24 사용자 요청)

메인런처가 크고 무거워서, 자주 쓰는 네 던전만 따로 뺀 창.
  · 항상 위, 화면 아래쪽 고정 (위치는 기억한다)
  · 불투명도 조절 — 뒤가 비쳐 보이게 (한 번 정하면 계속 유지)
  · 던전마다 [▶ 실행] + [⌖ 좌표] 두 개뿐
설정은 이 컴퓨터에만 저장한다: %LOCALAPPDATA%\\MoonAI\\bar.json
"""
import os
import json
import subprocess
import tkinter as tk

BASE  = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
CFG   = os.path.join(LOCAL, "bar.json")
ISLAND = os.path.join(BASE, "lineagem_island.py")

# 메인런처와 같은 던전 번호 (lineagem_island.py 의 DUNGEONS 순서)
DUNS = [
    (3, "에카",   "#27ae60"),
    (2, "잊섬",   "#2980b9"),
    (1, "악몽",   "#8e44ad"),
    (0, "오만",   "#e67e22"),
]
ALPHAS = [1.0, 0.85, 0.7, 0.55, 0.4]      # ◐ 를 누를 때마다 이 순서로


def load():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save(d):
    try:
        os.makedirs(LOCAL, exist_ok=True)
        tmp = CFG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CFG)
    except Exception:
        pass


class Bar(tk.Tk):
    BG = "#23272e"
    FG = "#e6e6e6"

    def __init__(self):
        super().__init__()
        self.cfg = load()
        self.overrideredirect(True)             # 제목표시줄 없이 얇게
        self.attributes("-topmost", True)
        self.configure(bg=self.BG)
        self.attributes("-alpha", float(self.cfg.get("alpha", 0.85)))
        self._build()
        self._place()
        self._drag = None

    # ── 화면 ────────────────────────────────────────────────────────
    def _build(self):
        pad = tk.Frame(self, bg=self.BG, highlightbackground="#d6dde5",
                       highlightthickness=1)
        pad.pack(fill="both", expand=True)

        grip = tk.Label(pad, text="≡", font=("맑은 고딕", 10, "bold"),
                        bg=self.BG, fg="#9aa4b0", cursor="fleur", padx=4)
        grip.pack(side="left")
        for w in (grip, pad, self):
            w.bind("<Button-1>", self._grab)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._drop)

        for idx, name, col in DUNS:
            cell = tk.Frame(pad, bg=self.BG)
            cell.pack(side="left", padx=(3, 0))
            tk.Button(cell, text=f"▶ {name}", font=("맑은 고딕", 8, "bold"),
                      bg=col, fg="white", bd=0, padx=5, pady=2,
                      activebackground=col,
                      command=lambda i=idx, n=name: self._run(i, n)).pack(side="left")
            tk.Button(cell, text="⌖", font=("맑은 고딕", 8, "bold"),
                      bg="#3a4149", fg=self.FG, bd=0, padx=3, pady=2,
                      activebackground="#4a525b",
                      command=lambda i=idx: self._open(i)).pack(side="left", padx=(1, 0))

        tk.Button(pad, text="◐", font=("맑은 고딕", 9, "bold"),
                  bg="#566573", fg="white", bd=0, padx=4, pady=2,
                  command=self._cycle_alpha).pack(side="left", padx=(6, 0))
        tk.Button(pad, text="✕", font=("맑은 고딕", 9, "bold"),
                  bg="#c0392b", fg="white", bd=0, padx=4, pady=2,
                  command=self._quit).pack(side="left", padx=(3, 3))

        self.lbl = tk.Label(pad, text="", font=("맑은 고딕", 7),
                            bg=self.BG, fg="#9aa4b0")
        self.lbl.pack(side="left", padx=(4, 6))

    def _place(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = self.cfg.get("x")
        y = self.cfg.get("y")
        if x is None or y is None:              # 처음엔 화면 아래 가운데
            x = (self.winfo_screenwidth() - w) // 2
            y = self.winfo_screenheight() - h - 60
        self.geometry(f"{w}x{h}+{int(x)}+{int(y)}")

    # ── 움직이기 ────────────────────────────────────────────────────
    def _grab(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _move(self, e):
        if not self._drag:
            return
        dx, dy = self._drag
        self.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _drop(self, _e):
        self._drag = None
        self.cfg["x"] = self.winfo_x()
        self.cfg["y"] = self.winfo_y()
        save(self.cfg)

    # ── 기능 ────────────────────────────────────────────────────────
    def _cycle_alpha(self):
        cur = float(self.cfg.get("alpha", 0.85))
        try:
            nxt = ALPHAS[(ALPHAS.index(min(ALPHAS, key=lambda a: abs(a - cur))) + 1)
                         % len(ALPHAS)]
        except Exception:
            nxt = 0.85
        self.attributes("-alpha", nxt)
        self.cfg["alpha"] = nxt
        save(self.cfg)
        self.lbl.config(text=f"투명도 {int(nxt * 100)}%")

    def _spawn(self, args):
        try:
            subprocess.Popen(["pythonw", ISLAND] + args)
            return True
        except Exception as e:
            self.lbl.config(text=f"실행 실패: {e}")
            return False

    def _run(self, idx, name):
        """그 던전 전체 실행 (메인런처의 던전 [실행]과 같다)."""
        if self._spawn([str(idx), "--run"]):
            self.lbl.config(text=f"{name} 실행")

    def _open(self, idx):
        """좌표·설정 창만 연다 (실행하지 않는다)."""
        if self._spawn([str(idx)]):
            self.lbl.config(text="좌표 창 열림")

    def _quit(self):
        self.cfg["x"] = self.winfo_x()
        self.cfg["y"] = self.winfo_y()
        save(self.cfg)
        self.destroy()


if __name__ == "__main__":
    Bar().mainloop()
