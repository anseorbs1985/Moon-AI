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
DATA_FILES = ["coords.json", "island_coords.json", "daya_regions.json",
              "island_counts.json", "daya_counts.json"]
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
            log("⚠ git pull 실패 — 저장소에 로컬 변경/충돌이 있는 것 같습니다")
            log("   (Moon-AI 폴더에서 직접 확인이 필요합니다)")
            return
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
