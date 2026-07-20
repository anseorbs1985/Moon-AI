"""
lineagem_update.py — 메인런처 [🔄 업데이트] 버튼용 원클릭 업데이트.

git pull(Moon-AI) → 런처 종료 → 파일을 실행 폴더(바탕화면)로 복사 → 워치독으로 재시작.
- 코드 파일(.py)은 항상 저장소 버전으로 동기화.
- 데이터 파일(coords.json 등)은 '이번 pull에서 실제로 바뀐 것만' 복사
  → 이 컴퓨터에서 아직 push 안 한 좌표를 실수로 덮어쓰지 않음.
"""
import os, sys, subprocess, shutil, time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(HERE).lower() == "moon-ai":
    DESK, REPO = os.path.dirname(HERE), HERE
else:
    DESK, REPO = HERE, os.path.join(HERE, "Moon-AI")

CODE_FILES = ["lineagem_launcher.py", "lineagem_ocr.py", "lineagem_island.py",
              "lineagem_dungeon.py", "lineagem_watchdog.py", "precise_click.py",
              "open_launcher.pyw", "lineagem_update.py"]
# 다야 측정값/좌표(daya_counts·history·regions)는 머신별 데이터 — 업데이트로 절대 덮어쓰지 않음
DATA_FILES = ["coords.json", "island_coords.json", "island_counts.json"]
DATA_DIRS  = ["reroll_templates"]

root = tk.Tk(); root.title("🔄 리니지M 업데이트")
root.geometry("470x320+420+320")
root.attributes("-topmost", True)
txt = tk.Text(root, font=("맑은 고딕", 9))
txt.pack(fill="both", expand=True, padx=6, pady=6)


def log(m):
    txt.insert("end", m + "\n"); txt.see("end"); root.update()


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          creationflags=0x08000000)  # CREATE_NO_WINDOW


CLAUDE_AUMID = "Claude_pzs8sxrjxfjjc!Claude"   # 클로드 데스크톱 앱 실행 ID


def _find_claude_hwnd():
    import ctypes
    u = ctypes.windll.user32
    found = []
    def cb(h, _):
        if u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, buf, 256)
            if buf.value.strip().lower() == "claude":
                found.append(h)
        return True
    WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    u.EnumWindows(WN(cb), 0)
    return found[0] if found else None


def ask_claude(reason):
    """업데이트 실패 시 클로드 앱을 열고 해결 지시문(실패 상세 포함)을 자동 입력해 실행시킨다.
    성공적으로 넘겼으면 True."""
    import ctypes
    u = ctypes.windll.user32
    # 실패 상세(git 상태) 수집 — 클로드가 바로 분석할 수 있게 지시문에 포함
    st = sh(["git", "status", "--short"], REPO).stdout.strip().splitlines()[:10]
    detail = ("\n[git status]\n" + "\n".join(st)) if st else ""
    prompt = (f"메인런처 [업데이트] 버튼이 실패했어. 원인: {reason}{detail}\n"
              f"{REPO} 저장소의 git 상태(로컬 변경/충돌)를 분석해서 해결하고, "
              "git pull 후 코드 파일들을 바탕화면으로 복사하고 워치독으로 메인런처를 재시작해서 "
              "업데이트를 끝까지 마무리해줘.")
    # 1) 지시문을 클립보드에
    root.clipboard_clear(); root.clipboard_append(prompt); root.update()
    # 2) 클로드 앱 찾기(없으면 실행)
    h = _find_claude_hwnd()
    if not h:
        log("   클로드 앱 실행 중...")
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{CLAUDE_AUMID}"])
        for _ in range(20):
            time.sleep(1)
            h = _find_claude_hwnd()
            if h:
                break
    if not h:
        log("⚠ 클로드 앱을 열지 못했습니다 — 직접 클로드에 '업데이트 실패 해결해줘'라고 말해주세요")
        return False
    # 3) 앞으로 올리고 지시문 붙여넣기 + 전송
    u.ShowWindow(h, 9)   # SW_RESTORE
    try:
        u.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(2.0)      # 입력창 포커스 잡힐 시간
    KEYUP = 0x0002
    u.keybd_event(0x11, 0, 0, 0)        # Ctrl down
    u.keybd_event(0x56, 0, 0, 0)        # V down
    u.keybd_event(0x56, 0, KEYUP, 0)    # V up
    u.keybd_event(0x11, 0, KEYUP, 0)    # Ctrl up
    time.sleep(0.6)
    u.keybd_event(0x0D, 0, 0, 0)        # Enter
    u.keybd_event(0x0D, 0, KEYUP, 0)
    log("✔ 클로드에게 해결을 요청했습니다 — 클로드 창에서 진행 상황을 확인하세요")
    return True


def main():
    try:
        if not os.path.isdir(os.path.join(REPO, ".git")):
            log(f"⚠ 저장소를 찾을 수 없습니다: {REPO}")
            return
        log("1) GitHub에서 최신 버전 받는 중...")
        old = sh(["git", "rev-parse", "HEAD"], REPO).stdout.strip()
        r = sh(["git", "pull", "--ff-only", "origin", "main"], REPO)
        log("   " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()))
        if r.returncode != 0:
            # 1차 자동복구: 로컬 변경을 stash로 백업하고 재시도 (대부분 여기서 해결)
            log("⚠ git pull 실패 — 로컬 변경을 백업(stash)하고 재시도...")
            sh(["git", "stash", "push", "--include-untracked", "-m", "업데이트 자동백업"], REPO)
            r = sh(["git", "pull", "--ff-only", "origin", "main"], REPO)
            if r.returncode != 0:
                # 2차: 클로드를 열어 해결 지시문 자동 입력
                err = (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "git pull 충돌")
                log("⚠ 자동복구도 실패 — 클로드에게 해결을 맡깁니다")
                if ask_claude(err):
                    log("이 창은 5초 후 자동으로 닫힙니다")
                    root.after(5000, root.destroy)   # 클로드에 넘겼으면 창도 자동 종료
                return
            log("   ✔ 로컬 변경은 stash로 백업했고 최신 버전을 받았습니다")
        new = sh(["git", "rev-parse", "HEAD"], REPO).stdout.strip()
        changed = []
        if old != new:
            changed = sh(["git", "diff", "--name-only", old, new], REPO).stdout.split()
            log(f"2) 새 버전 반영: {old[:7]} → {new[:7]} (변경 {len(changed)}개 파일)")
        else:
            log("2) 이미 최신입니다 — 코드 파일만 동기화합니다")

        log("3) 메인런처 종료...")
        sh(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*lineagem_launcher*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
        time.sleep(1.2)

        log("4) 파일 복사...")
        n = 0
        for f in CODE_FILES:                      # 코드는 항상 동기화
            s = os.path.join(REPO, f)
            if os.path.exists(s):
                shutil.copy2(s, os.path.join(DESK, f)); n += 1
        for f in DATA_FILES:                      # 데이터는 이번 pull에서 바뀐 것만
            if f in changed and os.path.exists(os.path.join(REPO, f)):
                shutil.copy2(os.path.join(REPO, f), os.path.join(DESK, f)); n += 1
                log(f"   데이터 갱신: {f}")
        for d in DATA_DIRS:
            if any(c.startswith(d + "/") for c in changed):
                sdir, ddir = os.path.join(REPO, d), os.path.join(DESK, d)
                os.makedirs(ddir, exist_ok=True)
                for fn in os.listdir(sdir):
                    shutil.copy2(os.path.join(sdir, fn), os.path.join(ddir, fn))
                log(f"   데이터 갱신: {d}/")
        log(f"   복사 {n}개 완료")

        log("5) 런처 재시작...")
        r = sh(["schtasks", "/Run", "/TN", "LineageM_Watchdog"])
        if r.returncode != 0:                     # 워치독 작업이 없으면 직접 실행
            exe = sys.executable.replace("python.exe", "pythonw.exe")
            subprocess.Popen([exe, os.path.join(DESK, "lineagem_launcher.py")])
            log("   (워치독 작업이 없어 런처를 직접 실행)")
        log("")
        log("✔ 업데이트 완료! 이 창은 5초 후 자동으로 닫힙니다")
        root.after(5000, root.destroy)
    except Exception as e:
        log(f"오류: {e}")


root.after(200, main)
root.mainloop()
