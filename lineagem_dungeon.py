import ctypes
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
from tkinter import ttk, messagebox
import time, threading, json, os
import pyautogui

BASE        = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "dungeon_coords.json")
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05

SLOTS         = 16
CLICKS        = 3        # 메뉴클릭 + 확장후클릭1 + 확장후클릭2
HOVER_WAIT    = 1.5      # 메뉴 올린 후 확장 대기(초)
CLICK_INTERVAL = 2.0     # 클릭 사이 간격(초)
CLICK_LABELS  = ["메뉴", "클릭1", "클릭2"]

# 요일 탭 목록 — 추가/삭제 자유
DAYS = ["주말", "월", "화", "수", "목", "금"]

def load_cfg():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    for day in DAYS:
        if day not in data:
            data[day] = [{"name": "미등록", "coords": [None]*CLICKS} for _ in range(SLOTS)]
    return data

def save_cfg(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class CoordOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.25)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        c = tk.Canvas(self, bg="black", highlightthickness=0)
        c.pack(fill="both", expand=True)
        si = app._reg_slot_idx; ci = app._reg_click_idx
        lbl = f"슬롯 #{si+1} [{CLICK_LABELS[ci]}] 위치 클릭하세요  (ESC: 취소)"
        c.create_text(self.winfo_screenwidth()//2, 60, text=lbl,
                      fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

    def _on_click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        self.app.on_coord(x, y)


class DungeonApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("리니지M 던전 실행기")
        self.attributes("-topmost", True)
        sh = self.winfo_screenheight()
        self.geometry(f"900x{sh * 2 // 3}+0+0")
        self.resizable(True, True)

        self.cfg = load_cfg()
        self._stop_flag   = False
        self._reg_day     = None
        self._reg_slot_idx  = 0
        self._reg_click_idx = 0

        self._build_ui()

    def _build_ui(self):
        # 상단 버튼 행
        top = tk.Frame(self); top.pack(fill="x", padx=8, pady=6)
        tk.Label(top, text="🏰  리니지M 던전 실행기",
                 font=("맑은 고딕", 13, "bold"), fg="#e67e22").pack(side="left")

        self._run_btn = tk.Button(top, text="▶  실행",
            font=("맑은 고딕", 10, "bold"), bg="#e67e22", fg="white",
            activebackground="#b35400", width=10, height=1,
            command=self._start)
        self._run_btn.pack(side="right", padx=(4,0))
        self._stop_btn = tk.Button(top, text="■ 멈춤",
            font=("맑은 고딕", 10, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=7, height=1,
            command=self._stop, state="disabled")
        self._stop_btn.pack(side="right", padx=(4,0))

        # 상태바
        self._status = tk.StringVar(value="탭을 선택하고 좌표를 등록하세요")
        tk.Label(self, textvariable=self._status, font=("맑은 고딕", 8),
                 fg="#555", anchor="w").pack(fill="x", padx=10, pady=(0,4))

        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=8, pady=2)

        # 요일 탭
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=4)

        self._tab_data = {}  # day -> {name_vars, click_vars, click_btns}

        for day in DAYS:
            frame = tk.Frame(nb)
            nb.add(frame, text=f"  {day}  ")
            self._build_day_tab(frame, day)

    def _build_day_tab(self, parent, day):
        outer = tk.Frame(parent); outer.pack(fill="both", expand=True, padx=2, pady=2)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(fid, width=e.width))

        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        name_vars  = []
        click_vars = []
        click_btns = []

        slots = self.cfg.get(day, [])
        while len(slots) < SLOTS:
            slots.append({"name": "미등록", "coords": [None]*CLICKS})
        self.cfg[day] = slots

        for i in range(SLOTS):
            row = tk.Frame(inner, bd=1, relief="groove")
            row.pack(fill="x", padx=4, pady=2)

            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=3).pack(side="left", padx=(4,0))

            nv = tk.StringVar(value=slots[i].get("name", "미등록"))
            name_vars.append(nv)
            ent = tk.Entry(row, textvariable=nv, font=("맑은 고딕", 9), width=8)
            ent.pack(side="left", padx=4)
            ent.bind("<FocusOut>", lambda e, d=day, x=i: self._save_name(d, x))
            ent.bind("<Return>",   lambda e, d=day, x=i: self._save_name(d, x))

            cvars = []
            cbtns = []
            for j in range(CLICKS):
                cv = tk.StringVar()
                cvars.append(cv)
                cell = tk.Frame(row)
                cell.pack(side="left", padx=3)
                tk.Label(cell, text=CLICK_LABELS[j], font=("맑은 고딕", 7),
                         fg="#888").pack()
                btn = tk.Button(cell, textvariable=cv, font=("맑은 고딕", 7),
                                width=4, pady=0,
                                command=lambda d=day, x=i, c=j: self._reg_click(d, x, c))
                btn.pack()
                cbtns.append(btn)
            click_vars.append(cvars)
            click_btns.append(cbtns)

            for w in row.winfo_children():
                w.bind("<MouseWheel>", _wheel)
            row.bind("<MouseWheel>", _wheel)

            tk.Button(row, text="▶", font=("맑은 고딕", 9), fg="white", bg="#e67e22",
                      width=2, command=lambda d=day, x=i: self._test(d, x)
                      ).pack(side="right", padx=(0,2))
            tk.Button(row, text="×", font=("맑은 고딕", 9), fg="red",
                      width=2, command=lambda d=day, x=i: self._del(d, x)
                      ).pack(side="right", padx=2)

        self._tab_data[day] = {
            "name_vars":  name_vars,
            "click_vars": click_vars,
            "click_btns": click_btns,
        }
        self._refresh_day(day)

    def _refresh_day(self, day):
        td = self._tab_data.get(day)
        if not td: return
        slots = self.cfg.get(day, [])
        for i in range(SLOTS):
            if i >= len(slots): break
            td["name_vars"][i].set(slots[i].get("name", "미등록"))
            coords = slots[i].get("coords", [None]*CLICKS)
            for j in range(CLICKS):
                c = coords[j] if j < len(coords) else None
                td["click_vars"][i][j].set("✔" if c else "등록")
                td["click_btns"][i][j].config(
                    fg="white" if c else "black",
                    bg="#e67e22" if c else "SystemButtonFace"
                )

    def _save_name(self, day, idx):
        name = self._tab_data[day]["name_vars"][idx].get().strip() or "미등록"
        self.cfg[day][idx]["name"] = name
        save_cfg(self.cfg)

    def _reg_click(self, day, slot_idx, click_idx):
        self._reg_day       = day
        self._reg_slot_idx  = slot_idx
        self._reg_click_idx = click_idx
        lbl = CLICK_LABELS[click_idx]
        self._status.set(f"3초 후 [{day}] 슬롯#{slot_idx+1} [{lbl}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2), CoordOverlay(self)])

    def on_coord(self, x, y):
        day = self._reg_day
        si  = self._reg_slot_idx
        ci  = self._reg_click_idx
        self.cfg[day][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg)
        self._refresh_day(day)
        lbl = CLICK_LABELS[ci]
        self._status.set(f"✔ [{day}] #{si+1} [{lbl}] 등록: ({x},{y})")
        self.deiconify()

    def _del(self, day, idx):
        self.cfg[day][idx] = {"name": "미등록", "coords": [None]*CLICKS}
        save_cfg(self.cfg)
        self._refresh_day(day)

    def _test(self, day, idx):
        threading.Thread(target=self._run, args=(day, idx), daemon=True).start()

    def _start(self):
        # 현재 선택된 탭의 day 찾기
        nb = [w for w in self.winfo_children() if isinstance(w, ttk.Notebook)][0]
        tab_text = nb.tab(nb.select(), "text").strip()
        self._stop_flag = False
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        threading.Thread(target=self._run, args=(tab_text,), daemon=True).start()

    def _stop(self):
        self._stop_flag = True
        self._status.set("멈추는 중...")

    def _run(self, day, slot_idx=None):
        try:
            slots = self.cfg.get(day, [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(c for c in s.get("coords", []))]
            for si, slot in targets:
                if self._stop_flag: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*CLICKS)
                if not coords[0]: continue
                # 메뉴 위로 이동 → 대기 → 클릭
                self._status.set(f"🏰 [{day}][{name}] 메뉴 이동...")
                pyautogui.moveTo(*coords[0])
                time.sleep(HOVER_WAIT)
                pyautogui.click(*coords[0])
                time.sleep(CLICK_INTERVAL)
                # 확장 후 클릭1, 클릭2
                for j in range(1, CLICKS):
                    if self._stop_flag: break
                    if coords[j]:
                        self._status.set(f"🏰 [{day}][{name}] {CLICK_LABELS[j]}...")
                        pyautogui.click(*coords[j])
                        if j < CLICKS - 1:
                            time.sleep(CLICK_INTERVAL)
            self._status.set("✔ 던전 실행 완료!")
        except Exception as e:
            self._status.set(f"오류: {e}")
        finally:
            self._run_btn.config(state="normal")
            self._stop_btn.config(state="disabled")


if __name__ == "__main__":
    app = DungeonApp()
    app.mainloop()
