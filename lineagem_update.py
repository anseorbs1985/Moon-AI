"""
lineagem_update.py — 메인런처 [🔄 업데이트] 버튼용 원클릭 업데이트.

git pull(Moon-AI) → 런처 종료 → 파일을 실행 폴더(바탕화면)로 복사 → 워치독으로 재시작.
- 코드 파일(.py)은 항상 저장소 버전으로 동기화.
- 데이터 파일(coords.json 등)은 '이번 pull에서 실제로 바뀐 것만' 복사
  → 이 컴퓨터에서 아직 push 안 한 좌표를 실수로 덮어쓰지 않음.
"""
import os, sys, subprocess, shutil, time, json
import tkinter as tk

def _merge_local_first(remote, local, stats):
    """로컬 우선 병합: 이 컴퓨터에 이미 등록된 좌표/값은 절대 건드리지 않고,
    로컬이 비어 있는 슬롯·새로 생긴 키만 원격(GitHub)에서 채운다."""
    if local is None:
        return remote
    if remote is None:
        return local
    if isinstance(local, dict) and isinstance(remote, dict):
        lc = local.get("coords")
        if isinstance(lc, list):                   # 슬롯 dict
            if any(c for c in lc):
                if local != remote:
                    stats[0] += 1                  # 로컬 등록 슬롯 → 통째로 유지
                return local
            return remote                          # 로컬 미등록 슬롯 → 원격으로 채움
        out = {}
        for k in set(remote) | set(local):
            out[k] = _merge_local_first(remote.get(k), local.get(k), stats)
        return out
    if isinstance(local, list) and isinstance(remote, list):
        out = []
        for i in range(max(len(remote), len(local))):
            li = local[i] if i < len(local) else None
            ri = remote[i] if i < len(remote) else None
            out.append(_merge_local_first(ri, li, stats))
        return out
    if local != "" and local is not None:          # 스칼라: 로컬 값 있으면 유지
        return local
    return remote

HERE = os.path.dirname(os.path.abspath(__file__))


def _is_repo(p):
    return bool(p) and os.path.isdir(os.path.join(p, ".git"))


def find_repo(here):
    """저장소 위치를 자동으로 찾는다 — 컴퓨터마다 폴더 구조가 달라도 되도록.
    (실행 폴더 아래 / 실행 폴더 자체 / 상위 폴더 / 사용자 폴더·바탕화면 순으로 탐색)"""
    home = os.path.expanduser("~")
    cands = [
        os.path.join(here, "Moon-AI"),          # 실행 폴더\Moon-AI (기본 배치)
        here,                                    # 실행 폴더가 곧 저장소
        os.path.join(home, "Moon-AI"),           # C:\Users\<이름>\Moon-AI
        os.path.join(home, "Desktop", "Moon-AI"),
        os.path.join(home, "OneDrive", "Desktop", "Moon-AI"),
    ]
    # 상위 폴더로 거슬러 올라가며 탐색 (…\Moon-AI\ 안에서 실행된 경우 포함)
    p = here
    for _ in range(4):
        cands.append(p)
        cands.append(os.path.join(p, "Moon-AI"))
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    for c in cands:
        if _is_repo(c):
            return c
    return None


REPO = find_repo(HERE)
# 배포 대상(DESK)은 런처가 실제로 실행되는 폴더. 저장소 안에서 실행됐다면 그 상위.
DESK = os.path.dirname(HERE) if os.path.basename(HERE).lower() == "moon-ai" else HERE

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


def backup_coords():
    """pull 전에 좌표 파일을 LOCALAPPDATA\\MoonAI\\backups 에 백업 — 날아가도 복구 가능."""
    try:
        import datetime as dt
        bdir = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI", "backups")
        os.makedirs(bdir, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        n = 0
        for src_dir, tag in ((DESK, "desk"), (REPO, "repo")):
            if not src_dir:
                continue
            for f in ("coords.json", "island_coords.json", "local_config.json"):
                s = os.path.join(src_dir, f)
                if os.path.exists(s):
                    shutil.copy2(s, os.path.join(bdir, f"{stamp}_{tag}_{f}"))
                    n += 1
        fns = sorted(os.listdir(bdir))
        for fn in fns[:-120]:                  # 오래된 백업 정리
            try: os.remove(os.path.join(bdir, fn))
            except Exception: pass
        return n
    except Exception:
        return 0


def _launcher_running():
    """메인런처 창이 떠 있는지 확인 (최소화 상태도 True)."""
    import ctypes
    u = ctypes.windll.user32
    found = []
    def cb(h, _):
        if u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, b, 256)
            if "리니지M 자동 실행" in b.value:
                found.append(h)
        return True
    WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    u.EnumWindows(WN(cb), 0)
    return bool(found)


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


def ensure_launcher():
    """메인런처가 꺼져 있으면 반드시 다시 띄운다 (워치독 → 직접 실행 순). 떠 있으면 그대로."""
    if _launcher_running():
        return True
    sh(["schtasks", "/Run", "/TN", "LineageM_Watchdog"])
    for _ in range(15):
        time.sleep(1)
        if _launcher_running():
            return True
    log("   워치독 재시작 실패 → 런처 직접 실행")
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, os.path.join(DESK, "lineagem_launcher.py")],
                     creationflags=0x00000008 | 0x00000200)  # DETACHED
    for _ in range(15):
        time.sleep(1)
        if _launcher_running():
            return True
    return False


def _show_launcher():
    """메인런처 창을 복원해서 화면에 보여준다 (워치독의 시작 최소화 이후에 실행)."""
    import ctypes
    u = ctypes.windll.user32
    found = []
    def cb(h, _):
        if u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, b, 256)
            if "리니지M 자동 실행" in b.value:
                found.append(h)
        return True
    WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    u.EnumWindows(WN(cb), 0)
    for h in found:
        u.ShowWindow(h, 9)          # SW_RESTORE
        try:
            u.SetForegroundWindow(h)
        except Exception:
            pass


def ensure_keepalive():
    """런처 상시 유지용 예약 작업(10분마다 워치독)이 없으면 자동 등록 — 모든 컴퓨터 공통."""
    try:
        q = sh(["schtasks", "/Query", "/TN", "LineageM_KeepAlive"])
        if q.returncode == 0:
            return
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        wd = os.path.join(DESK, "lineagem_watchdog.py")
        r = sh(["schtasks", "/Create", "/F", "/TN", "LineageM_KeepAlive",
                "/SC", "MINUTE", "/MO", "10",
                "/TR", f'"{exe}" "{wd}"'])
        if r.returncode == 0:
            log("   ✔ 런처 상시감시(KeepAlive, 10분마다) 예약 작업 등록")
    except Exception:
        pass


def finish(msg=""):
    """모든 종료 경로 공통: 런처 재시작 확인 → 창 띄워서 보여줌 → '5초 후 꺼짐' 알림 → 종료."""
    ensure_keepalive()               # 상시감시 예약 작업 보장 (없으면 등록)
    ok = ensure_launcher()
    if ok:
        time.sleep(2)               # 워치독의 시작 최소화가 지나간 뒤
        _show_launcher()            # 런처 창을 화면에 띄워서 보여줌 (이후엔 10분 유휴 최소화가 처리)
    if msg:
        log(""); log(msg)
    log("✔ 메인런처 실행 확인 (창 표시)" if ok else "⚠ 메인런처 재시작 실패 — 클로드 확인 필요")
    log("이 창은 5초 후에 꺼집니다")
    root.after(5000, root.destroy)


def main():
    try:
        if not REPO:
            log("⚠ Moon-AI 저장소를 찾을 수 없습니다. 아래 위치 중 한 곳에 있어야 합니다:")
            log(f"   · {os.path.join(HERE, 'Moon-AI')}")
            log(f"   · {os.path.join(os.path.expanduser('~'), 'Moon-AI')}")
            log("")
            log("해결: 저장소 폴더(Moon-AI)를 런처 폴더 안으로 옮기거나, 아래 명령으로 새로 받으세요.")
            log(f'   git clone https://github.com/anseorbs1985/Moon-AI.git "{os.path.join(HERE, "Moon-AI")}"')
            ask_claude("Moon-AI 저장소 폴더를 찾을 수 없음 — 저장소를 찾거나 clone해서 업데이트를 마무리해줘")
            finish()
            return
        log(f"저장소: {REPO}")
        _bn = backup_coords()
        log(f"0) 좌표 자동 백업 {_bn}개 (LOCALAPPDATA\\MoonAI\\backups)")
        # 병합용 스냅샷: 로컬(현재 사용 중) 좌표 — pull 전에 확보
        MERGE_FILES = ("coords.json", "island_coords.json")
        local_snap = {}
        for f in MERGE_FILES:
            try:
                with open(os.path.join(DESK, f), encoding="utf-8") as fp:
                    local_snap[f] = json.load(fp)
            except Exception:
                local_snap[f] = None
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
                ask_claude(err)
                finish()
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

        # 복사가 실패해도 런처는 반드시 다시 띄운다(꺼진 채로 방치 금지) → 오류는 잡아두고 뒤에서 보고
        copy_err = None
        try:
            log("4) 파일 복사...")
            n = 0
            for f in CODE_FILES:                      # 코드는 항상 동기화
                s = os.path.join(REPO, f)
                if os.path.exists(s):
                    shutil.copy2(s, os.path.join(DESK, f)); n += 1
            for f in DATA_FILES:                      # 데이터는 이번 pull에서 바뀐 것만
                if f in changed and os.path.exists(os.path.join(REPO, f)):
                    dst = os.path.join(DESK, f)
                    if f in MERGE_FILES and local_snap.get(f) is not None:
                        # 로컬 우선 병합: 이 컴퓨터에 등록된 좌표는 그대로, 빈 곳만 원격에서 채움
                        try:
                            with open(os.path.join(REPO, f), encoding="utf-8") as fp:
                                remote = json.load(fp)
                            stats = [0]
                            merged = _merge_local_first(remote, local_snap[f], stats)
                            with open(dst, "w", encoding="utf-8") as fp:
                                json.dump(merged, fp, ensure_ascii=False, indent=2)
                            n += 1
                            log(f"   데이터 병합: {f} (로컬 등록 {stats[0]}곳 유지, 빈 곳만 원격 반영)")
                            continue
                        except Exception as e:
                            log(f"   병합 실패({e}) → 원격 버전으로 대체")
                    shutil.copy2(os.path.join(REPO, f), dst); n += 1
                    log(f"   데이터 갱신: {f}")
            for d in DATA_DIRS:
                if any(c.startswith(d + "/") for c in changed):
                    sdir, ddir = os.path.join(REPO, d), os.path.join(DESK, d)
                    os.makedirs(ddir, exist_ok=True)
                    for fn in os.listdir(sdir):
                        shutil.copy2(os.path.join(sdir, fn), os.path.join(ddir, fn))
                    log(f"   데이터 갱신: {d}/")
            log(f"   복사 {n}개 완료")
        except Exception as e:
            copy_err = e
            log(f"⚠ 파일 복사 중 오류: {e}")
            log("   → 메인런처부터 다시 띄운 뒤 보고합니다")

        log("5) 런처 재시작...")
        ok = ensure_launcher()
        if ok and copy_err is None:
            finish("✔ 업데이트 완료!")
        elif ok:                                  # 런처는 살렸지만 복사 실패 → 클로드에 마무리 요청
            log("⚠ 파일 복사가 실패했습니다 — 클로드에게 마무리를 요청합니다")
            ask_claude(f"업데이트 중 파일 복사 실패: {copy_err}")
            finish()
        else:
            log("⚠ 런처가 재시작되지 않았습니다 — 클로드에게 확인을 요청합니다")
            ask_claude("업데이트 후 메인런처가 재시작되지 않음 (워치독 실행과 직접 실행 모두 창이 안 뜸 — "
                       "런처가 시작 직후 죽는 오류일 수 있으니 python으로 직접 실행해 에러를 확인해줘)")
            finish()
    except Exception as e:
        log(f"오류: {e}")
        finish("⚠ 오류가 있었지만 메인런처는 다시 띄웁니다")


root.after(200, main)
root.mainloop()
