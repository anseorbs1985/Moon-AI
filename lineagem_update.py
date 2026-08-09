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


def _merge_3way(base, remote, local, stats):
    """3자 병합: base(이 컴퓨터가 마지막으로 받았던 원격 버전) 기준으로
    - 로컬이 base에서 안 바뀐 부분 → 원격(메인의 수정) 반영
    - 로컬이 직접 수정한 부분 → 로컬 유지
    - 둘 다 바뀐 부분 → 안쪽으로 내려가 항목별 판정, 최종 충돌은 로컬 우선.
    stats = [로컬 유지 수, 원격 반영 수]"""
    if local == base:                              # 로컬 무수정 → 원격 채택
        if remote != local:
            stats[1] += 1
        return remote
    if remote == base:                             # 원격 무변경 → 로컬 유지
        stats[0] += 1
        return local
    if isinstance(remote, dict) and isinstance(local, dict):
        b = base if isinstance(base, dict) else {}
        out = {}
        for k in set(remote) | set(local):
            out[k] = _merge_3way(b.get(k), remote.get(k), local.get(k), stats)
        return out
    if isinstance(remote, list) and isinstance(local, list):
        b = base if isinstance(base, list) else []
        out = []
        for i in range(max(len(remote), len(local))):
            bi = b[i] if i < len(b) else None
            ri = remote[i] if i < len(remote) else None
            li = local[i] if i < len(local) else None
            if li is None:
                out.append(ri)
            elif ri is None:
                out.append(li)
            else:
                out.append(_merge_3way(bi, ri, li, stats))
        return out
    stats[0] += 1                                  # 스칼라 충돌 → 로컬 우선
    return local


def _count_coords(path):
    """파일 안의 [x, y] 좌표 개수 — 동기화 결과 확인용."""
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        cnt = [0]
        def walk(v):
            if isinstance(v, list):
                if (len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
                    cnt[0] += 1
                else:
                    for x in v: walk(x)
            elif isinstance(v, dict):
                for x in v.values(): walk(x)
        walk(data)
        return cnt[0]
    except Exception:
        return -1


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
              "open_launcher.pyw", "lineagem_update.py", "moon.ico"]
# 2026-08-05: 업데이트(🔄) 한 번으로 좌표까지 받게 복귀 — 메인이 올린 좌표를
# 메인이 아닌 컴퓨터가 통째로 받는다. 덮어쓰기 전 자동 백업 + 런처의 [♻ 좌표복구]로
# 자기가 저장해둔 좌표로 언제든 되돌릴 수 있음.
# 다야 측정값(daya_counts·history)은 머신별 — 업데이트로 절대 덮어쓰지 않음
# 2026-08-09: 로컬은 섬/던전 좌표(island_coords.json)만 받는다.
# coords.json(메인런처 좌표)은 컴퓨터마다 달라서 동기화하지 않음.
# 2026-08-09: 좌표는 컴퓨터마다 위치가 달라 더 이상 통째로 배포하지 않는다.
#             대신 아래 sync_times()가 '클릭 간격(시간)'만 합쳐 넣는다.
DATA_FILES = ["island_counts.json"]
DATA_DIRS  = ["reroll_templates"]


def sync_times(log):
    """좌표는 그대로 두고 '클릭 간격(gap_list)'만 메인 것으로 맞춘다.
    share_times.json 에 적힌 던전만 대상 (컴퓨터마다 좌표 위치가 다르기 때문)."""
    try:
        man = os.path.join(REPO, "share_times.json")
        if not os.path.exists(man):
            return
        with open(man, encoding="utf-8") as f:
            keys = (json.load(f) or {}).get("keys") or []
        if not keys:
            return
        src_p = os.path.join(REPO, "island_coords.json")
        dst_p = os.path.join(DESK, "island_coords.json")
        if not (os.path.exists(src_p) and os.path.exists(dst_p)):
            log("   시간 동기화: 섬/던전 좌표 파일이 없어 건너뜁니다")
            return
        with open(src_p, encoding="utf-8") as f:
            src = json.load(f)
        with open(dst_p, encoding="utf-8") as f:
            dst = json.load(f)
        n = 0
        for key in keys:
            a, b = src.get(key), dst.get(key)
            if not isinstance(a, list) or not isinstance(b, list):
                continue
            for i, s_slot in enumerate(a):
                if i >= len(b) or not isinstance(s_slot, dict) or not isinstance(b[i], dict):
                    continue
                gl = s_slot.get("gap_list")
                if gl is not None and b[i].get("gap_list") != gl:
                    b[i]["gap_list"] = list(gl)      # 시간만 교체 — 좌표는 그대로
                    n += 1
        if not n:
            log("   시간 동기화: 이미 메인과 같습니다")
            return
        tmp = dst_p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dst, f, ensure_ascii=False, indent=2)
        os.replace(tmp, dst_p)
        log(f"   ⏱ 클릭 간격(시간) 동기화: {', '.join(keys)} — 슬롯 {n}개 (좌표는 그대로)")
    except Exception as e:
        log(f"   ⚠ 시간 동기화 실패: {e}")


def sync_coord_keys(log):
    """coords.json 중 '지정한 항목만' 메인 것으로 받는다 (share_coords.json 의 keys).
    나머지 좌표는 로컬 것을 그대로 지킨다 — 컴퓨터마다 위치가 다르기 때문."""
    try:
        man = os.path.join(REPO, "share_coords.json")
        if not os.path.exists(man):
            return
        with open(man, encoding="utf-8") as f:
            keys = (json.load(f) or {}).get("keys") or []
        if not keys:
            return
        src_p = os.path.join(REPO, "coords.json")
        dst_p = os.path.join(DESK, "coords.json")
        if not (os.path.exists(src_p) and os.path.exists(dst_p)):
            log("   항목 좌표 동기화: coords.json 이 없어 건너뜁니다")
            return
        with open(src_p, encoding="utf-8") as f:
            src = json.load(f)
        with open(dst_p, encoding="utf-8") as f:
            dst = json.load(f)
        got = []
        for k in keys:
            v = src.get(k)
            if v is None:
                continue
            if dst.get(k) != v:
                dst[k] = v
                got.append(f"{k}({_count_in(v)}좌표)")
        if not got:
            log("   항목 좌표 동기화: 이미 메인과 같습니다")
            return
        tmp = dst_p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dst, f, ensure_ascii=False, indent=2)
        os.replace(tmp, dst_p)
        log("   📍 지정 항목 좌표 받음: " + ", ".join(got) + " (나머지 좌표는 그대로)")
    except Exception as e:
        log(f"   ⚠ 항목 좌표 동기화 실패: {e}")


def _count_in(v):
    n = [0]
    def walk(x):
        if isinstance(x, list):
            if len(x) == 2 and all(isinstance(y, (int, float)) for y in x):
                n[0] += 1
            else:
                for y in x: walk(y)
        elif isinstance(x, dict):
            for y in x.values(): walk(y)
    walk(v)
    return n[0]


def _all_code_files():
    """저장소에 있는 코드 파일 전부 — 목록(CODE_FILES)에 안 적혀서 빠지는 일 방지.
    새 .py/.pyw 파일이 추가돼도 업데이트가 자동으로 같이 받아온다."""
    files = list(CODE_FILES)
    try:
        for f in sorted(os.listdir(REPO)):
            if f in files:
                continue
            if f.lower().endswith((".py", ".pyw")):
                files.append(f)
    except Exception:
        pass
    return files

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
    """업데이트 실패 시 클로드 앱을 열고 'git pull'을 입력+엔터 — 클로드가 바로 실행하게 한다.
    (CLAUDE.md 지침: 'git pull' = 로컬우선 병합·배포·런처 재시작까지 전체 업데이트 절차)
    성공적으로 넘겼으면 True."""
    import ctypes
    u = ctypes.windll.user32
    log(f"   실패 원인: {reason}")
    try:
        st = sh(["git", "status", "--short"], REPO).stdout.strip().splitlines()[:10]
        for s in st:
            log("   " + s)
    except Exception:
        pass
    prompt = "git pull"
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
    """(2026-08-09 사용자 지시) 10분마다 상시감시는 사용하지 않는다.
    이미 등록돼 있으면 삭제하고, 새로 만들지 않는다. 자동 실행은 새벽 4:50만."""
    try:
        q = sh(["schtasks", "/Query", "/TN", "LineageM_KeepAlive"])
        if q.returncode == 0:
            r = sh(["schtasks", "/Delete", "/F", "/TN", "LineageM_KeepAlive"])
            if r.returncode == 0:
                log("   ✔ 10분마다 상시감시(KeepAlive) 예약 작업 삭제 — 새벽 4:50만 사용")
    except Exception:
        pass


def ensure_autostart_0450():
    """새벽 4시 50분 자동 시작 예약 작업 — 그 시각에 런처가 꺼져 있으면 워치독이 되살린다.
    (워치독은 이미 켜져 있으면 아무것도 하지 않으므로 중복 실행 걱정 없음)"""
    try:
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        wd = os.path.join(DESK, "lineagem_watchdog.py")
        q = sh(["schtasks", "/Query", "/TN", "LineageM_AutoStart_0450"])
        if q.returncode == 0:
            return
        r = sh(["schtasks", "/Create", "/F", "/TN", "LineageM_AutoStart_0450",
                "/SC", "DAILY", "/ST", "04:50",
                "/TR", f'"{exe}" "{wd}"'])
        if r.returncode == 0:
            log("   ✔ 새벽 4:50 자동 시작 예약 작업 등록 (꺼져 있으면 자동 실행)")
        else:
            log(f"   ⚠ 4:50 자동 시작 등록 실패: {(r.stderr or r.stdout or '').strip()[:60]}")
    except Exception:
        pass


def ensure_shortcut_icon():
    """바탕화면 메인런처 바로가기 아이콘을 moon.ico로 통일 (모든 컴퓨터 공통)."""
    try:
        ico = os.path.join(DESK, "moon.ico")
        if not os.path.exists(ico):
            return
        ps = (
            "$sh = New-Object -ComObject WScript.Shell; "
            "$dt = [Environment]::GetFolderPath('Desktop'); "
            "Get-ChildItem \"$dt\\*.lnk\" | ForEach-Object { "
            "$s = $sh.CreateShortcut($_.FullName); "
            "if (($s.Arguments -match 'open_launcher|lineagem_launcher') -or "
            "($s.TargetPath -match 'open_launcher|lineagem_launcher')) { "
            "if ($s.IconLocation -notmatch 'moon') { "
            "$s.IconLocation = '" + ico.replace("\\", "\\\\") + ",0'; $s.Save() } } }"
        )
        sh(["powershell", "-NoProfile", "-Command", ps])
    except Exception:
        pass


def finish(msg=""):
    """모든 종료 경로 공통: 런처 재시작 확인 → 창 띄워서 보여줌 → '5초 후 꺼짐' 알림 → 종료."""
    ensure_keepalive()               # 상시감시 예약 작업 보장 (없으면 등록)
    ensure_autostart_0450()          # 새벽 4:50 자동 시작 보장 (없으면 등록)
    ensure_shortcut_icon()           # 바로가기 아이콘 통일 (moon.ico)
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
    global REPO
    try:
        if not REPO:
            # 자동복구: 저장소가 없으면 바로 새로 받는다
            dest = os.path.join(HERE, "Moon-AI")
            log("⚠ Moon-AI 저장소가 없습니다 — git clone으로 새로 받는 중...")
            r = sh(["git", "clone", "https://github.com/anseorbs1985/Moon-AI.git", dest])
            if r.returncode == 0 and _is_repo(dest):
                REPO = dest
                log(f"   ✔ clone 완료: {dest}")
            else:
                err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "clone 실패"
                ask_claude(f"저장소 없음 + clone 실패: {err}")
                finish()
                return
        log(f"저장소: {REPO}")
        _bn = backup_coords()
        log(f"0) 좌표 자동 백업 {_bn}개 (LOCALAPPDATA\\MoonAI\\backups)")
        MERGE_FILES = ("coords.json", "island_coords.json")   # 동기화 대상 좌표 (메인이 원본)
        # 좌표 동기화 정책: 좌표는 모든 컴퓨터가 동일하고 메인이 유일한 원본.
        # 메인이 아닌 컴퓨터는 병합 없이 '통째로' 원격(메인) 버전으로 맞춘다.
        is_main = False
        try:
            with open(os.path.join(DESK, "local_config.json"), encoding="utf-8") as fp:
                is_main = bool(json.load(fp).get("is_main"))
        except Exception:
            pass
        log("1) GitHub에서 최신 버전 받는 중...")
        old = sh(["git", "rev-parse", "HEAD"], REPO).stdout.strip()
        if not is_main:
            # 로컬 컴퓨터: 저장소 상태가 어떻든 원격과 100% 일치시킨다 (충돌·병합 개념 없음)
            sh(["git", "fetch", "origin", "main"], REPO)
            r = sh(["git", "reset", "--hard", "origin/main"], REPO)
            if r.returncode != 0:
                err = (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "git 동기화 실패")
                log("⚠ 원격 동기화 실패 — 클로드에게 넘깁니다")
                ask_claude(err)
                finish()
                return
            log("   ✔ 저장소를 원격(메인)과 100% 일치시켰습니다")
        else:
            r = sh(["git", "pull", "--ff-only", "origin", "main"], REPO)
            log("   " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()))
            if r.returncode != 0:
                # 1차 자동복구: 로컬 변경을 stash로 백업하고 재시도 (대부분 여기서 해결)
                log("⚠ git pull 실패 — 로컬 변경을 백업(stash)하고 재시도...")
                sh(["git", "stash", "push", "--include-untracked", "-m", "업데이트 자동백업"], REPO)
                r = sh(["git", "pull", "--ff-only", "origin", "main"], REPO)
                if r.returncode != 0:
                    # 2차 자동복구: 원격 기준으로 강제 동기화 (기존 상태는 백업 브랜치에 보관)
                    stamp = time.strftime("%Y%m%d_%H%M%S")
                    log("⚠ 재시도도 실패 — 원격 기준 강제 동기화 (이전 상태는 backup_" + stamp + " 브랜치 보관)")
                    sh(["git", "branch", f"backup_{stamp}"], REPO)
                    sh(["git", "fetch", "origin", "main"], REPO)
                    r = sh(["git", "reset", "--hard", "origin/main"], REPO)
                    if r.returncode != 0:
                        # 3차: 클로드에 'git pull' 입력해 즉시 실행시킴
                        err = (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "git 동기화 실패")
                        log("⚠ 강제 동기화도 실패 — 클로드에게 넘깁니다")
                        ask_claude(err)
                        finish()
                        return
                    log("   ✔ 강제 동기화 완료")
                else:
                    log("   ✔ 로컬 변경은 stash로 백업했고 최신 버전을 받았습니다")
        new = sh(["git", "rev-parse", "HEAD"], REPO).stdout.strip()
        changed = []
        if old != new:
            changed = sh(["git", "diff", "--name-only", old, new], REPO).stdout.split()
            log(f"2) 새 버전 반영: {old[:7]} → {new[:7]} (변경 {len(changed)}개 파일)")
        else:
            log("2) 이미 최신입니다 — 코드 파일만 동기화합니다")

        # 2-1) 업데이터 자신이 새 버전이면 — 새 업데이터로 갈아타고 이어서 진행한다.
        #      (예전엔 다음 번 업데이트에야 새 로직이 적용돼 두 번 눌러야 했음)
        try:
            _me_repo = os.path.join(REPO, "lineagem_update.py")
            _me_desk = os.path.join(DESK, "lineagem_update.py")
            _relaunched = "--relaunched" in sys.argv
            _differs = False
            if os.path.exists(_me_repo) and os.path.exists(_me_desk):
                with open(_me_repo, "rb") as _fa, open(_me_desk, "rb") as _fb:
                    _differs = _fa.read() != _fb.read()
            if _differs and not _relaunched:
                log("2-1) 업데이트 프로그램이 새 버전 — 새 버전으로 갈아타고 계속합니다")
                shutil.copy2(_me_repo, _me_desk)
                _exe = sys.executable.replace("python.exe", "pythonw.exe")
                subprocess.Popen([_exe, _me_desk, "--relaunched"],
                                 creationflags=0x08000000)
                root.after(300, root.destroy)
                return
        except Exception as _e:
            log(f"   ⚠ 업데이터 자체 갱신 확인 실패: {_e}")

        log("3) 런처·실행기·OCR 전부 종료... (좌표를 되돌려 쓰는 프로세스 차단)")
        sh(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'lineagem_launcher|lineagem_island|lineagem_ocr|lineagem_dungeon' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
        time.sleep(1.2)

        # 복사가 실패해도 런처는 반드시 다시 띄운다(꺼진 채로 방치 금지) → 오류는 잡아두고 뒤에서 보고
        copy_err = None
        for _copy_try in (1, 2):
          try:
            log("4) 파일 복사..." if _copy_try == 1 else "4) 파일 복사 재시도...")
            n = 0
            code_fail = []
            for f in _all_code_files():               # 코드는 항상 동기화 (저장소 전체)
                s = os.path.join(REPO, f)
                if not os.path.exists(s):
                    continue
                dst = os.path.join(DESK, f)
                okc = False
                for _t in (1, 2, 3):                  # 파일이 잠겨 있을 수 있어 3회까지 재시도
                    try:
                        shutil.copy2(s, dst)
                        with open(s, "rb") as fa, open(dst, "rb") as fb:
                            okc = fa.read() == fb.read()   # 바이트 단위 검증
                    except Exception:
                        okc = False
                    if okc:
                        break
                    time.sleep(0.6)
                if okc:
                    n += 1
                else:
                    code_fail.append(f)
            if code_fail:
                log("   ⚠ 코드 복사 실패: " + ", ".join(code_fail))
                raise RuntimeError("코드 복사 실패: " + ", ".join(code_fail))
            # 데이터(좌표): 병합 없음 — 메인이 아니면 원격(메인) 버전으로 통째로 동기화.
            # 메인 컴퓨터는 자기(바탕화면) 좌표가 원본이므로 절대 덮어쓰지 않음.
            for f in DATA_FILES:
                s = os.path.join(REPO, f)
                if not os.path.exists(s):
                    continue
                dst = os.path.join(DESK, f)
                if is_main and f in MERGE_FILES:
                    log(f"   {f}: 메인 컴퓨터 — 로컬 원본 유지")
                    continue
                try:
                    with open(s, "rb") as fa, open(dst, "rb") as fb:
                        if fa.read() == fb.read():
                            log(f"   {f}: 이미 메인과 동일")
                            continue
                except Exception:
                    pass                       # 로컬에 없거나 비교 실패 → 반영 진행
                # 덮어쓰기 직전 현재 좌표를 따로 백업 (되돌리고 싶을 때 대비)
                if f in MERGE_FILES and os.path.exists(dst):
                    try:
                        import datetime as _dt
                        _bd = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI", "backups")
                        os.makedirs(_bd, exist_ok=True)
                        _st = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        shutil.copy2(dst, os.path.join(_bd, f"{_st}_before_update_{f}"))
                    except Exception:
                        pass
                shutil.copy2(s, dst); n += 1
                # 복사 검증 — 메인과 바이트 단위로 일치하는지 확인
                try:
                    with open(s, "rb") as fa, open(dst, "rb") as fb:
                        ok = fa.read() == fb.read()
                except Exception:
                    ok = False
                if ok:
                    log(f"   좌표 동기화: {f} — 메인과 100% 일치 확인 ✔ (좌표 {_count_coords(dst)}개)")
                    if f in MERGE_FILES:
                        log(f"      (이전 좌표는 백업됨 — 되돌리려면 런처 [♻ 좌표복구])")
                else:
                    log(f"   ⚠ {f} 복사 검증 실패 — 업데이트를 한 번 더 실행해주세요")
            if not is_main:
                sync_times(log)          # 좌표는 그대로, 시간만 메인과 맞춤
                sync_coord_keys(log)     # 지정한 항목(낚시녹임 등)만 좌표도 받음
            # 다야 OCR 캡처영역(daya_regions.json)도 메인과 동일하게 동기화
            # (측정값 daya_counts/history는 머신별 데이터라 절대 건드리지 않음)
            try:
                src_r = os.path.join(REPO, "daya_regions.json")
                if os.path.exists(src_r) and not is_main:
                    ldir = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI")
                    os.makedirs(ldir, exist_ok=True)
                    dst_r = os.path.join(ldir, "daya_regions.json")
                    same_r = False
                    try:
                        with open(src_r, "rb") as fa, open(dst_r, "rb") as fb:
                            same_r = fa.read() == fb.read()
                    except Exception:
                        pass
                    if not same_r:
                        shutil.copy2(src_r, dst_r); n += 1
                        log("   다야 OCR 영역 동기화: daya_regions.json — 메인과 동일하게 반영 ✔")
            except Exception as e:
                log(f"   ⚠ 다야 영역 동기화 실패: {e}")
            for d in DATA_DIRS:
                sdir, ddir = os.path.join(REPO, d), os.path.join(DESK, d)
                if not os.path.isdir(sdir):
                    continue
                os.makedirs(ddir, exist_ok=True)
                for fn in os.listdir(sdir):
                    sp_, dp_ = os.path.join(sdir, fn), os.path.join(ddir, fn)
                    if (not os.path.exists(dp_)
                            or os.path.getsize(sp_) != os.path.getsize(dp_)):
                        shutil.copy2(sp_, dp_); n += 1
                        log(f"   데이터 갱신: {d}/{fn}")
            # 프리셋만 키 단위로 동기화 — coords.json 전체는 건드리지 않고
            # 프리셋 정의(_doll_presets 등)만 메인 것으로 맞춘다 (좌표는 로컬 유지)
            try:
                _src = os.path.join(REPO, "coords.json")
                _dst = os.path.join(DESK, "coords.json")
                if os.path.exists(_src) and os.path.exists(_dst):
                    with open(_src, encoding="utf-8") as _f:
                        _rem = json.load(_f)
                    with open(_dst, encoding="utf-8") as _f:
                        _loc = json.load(_f)
                    _keys = [k for k in _rem if k.startswith("_")]   # _doll_presets 등
                    _ch = [k for k in _keys if _loc.get(k) != _rem[k]]
                    if _ch:
                        for k in _ch:
                            _loc[k] = _rem[k]
                        with open(_dst, "w", encoding="utf-8") as _f:
                            json.dump(_loc, _f, ensure_ascii=False, indent=2)
                        log(f"   프리셋 동기화: {', '.join(_ch)} — 메인 것으로 반영 ✔")
                    else:
                        log("   프리셋: 이미 메인과 동일")
            except Exception as _e:
                log(f"   ⚠ 프리셋 동기화 실패: {_e}")

            # 🛟 좌표 파일이 없거나 비어 있으면 자동 복구
            #    1순위: 이 컴퓨터의 자동 백업  2순위: 저장소(메인) 좌표
            #    좌표가 멀쩡한 컴퓨터는 절대 건드리지 않는다 (머신별 원본 유지)
            try:
                bdir = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI", "backups")
                bfns = sorted(os.listdir(bdir), reverse=True) if os.path.isdir(bdir) else []
                for f in ("coords.json", "island_coords.json"):
                    dst = os.path.join(DESK, f)
                    if os.path.exists(dst) and os.path.getsize(dst) > 2000:
                        log(f"   {f}: 로컬 좌표 정상 — 그대로 유지")
                        continue
                    picked = None
                    for tag in ("_desk_", "_repo_"):   # 이 컴퓨터(desk) 백업 우선
                        for fn in bfns:
                            if fn.endswith(f"{tag}{f}"):
                                p_ = os.path.join(bdir, fn)
                                if os.path.getsize(p_) > 2000:
                                    picked = p_; break
                        if picked: break
                    src_repo = os.path.join(REPO, f)
                    if picked:
                        shutil.copy2(picked, dst); n += 1
                        log(f"   🛟 {f} 유실 → 이 컴퓨터 백업에서 복구 ✔ ({os.path.basename(picked)})")
                    elif os.path.exists(src_repo) and os.path.getsize(src_repo) > 2000:
                        shutil.copy2(src_repo, dst); n += 1
                        log(f"   🛟 {f} 유실 → 메인 좌표로 복구 ✔ (좌표 {_count_coords(dst)}개)")
                    else:
                        log(f"   ⚠ {f} 유실 — 복구본을 못 찾음, 클로드에게 '좌표 복구해줘'라고 요청하세요")
            except Exception as e:
                log(f"   ⚠ 좌표 자동복구 확인 실패: {e}")
            log(f"   복사 {n}개 완료")
            # 업데이트 횟수 누적 (머신별 — local_config.json)
            try:
                _lp = os.path.join(DESK, "local_config.json")
                try:
                    with open(_lp, encoding="utf-8") as _f:
                        _lc = json.load(_f)
                except Exception:
                    _lc = {}
                _lc["update_count"] = int(_lc.get("update_count", 0)) + 1
                import datetime as _dt2
                _lc["update_last"] = _dt2.datetime.now().strftime("%m-%d %H:%M")
                with open(_lp, "w", encoding="utf-8") as _f:
                    json.dump(_lc, _f, ensure_ascii=False, indent=2)
                log(f"   업데이트 누적 {_lc['update_count']}회")
            except Exception as _e:
                log(f"   ⚠ 업데이트 횟수 기록 실패: {_e}")
            copy_err = None
            break
          except Exception as e:
            copy_err = e
            log(f"⚠ 파일 복사 중 오류: {e}")
            if _copy_try == 1:
                # 자동복구: 파일 점유가 흔한 원인 — 런처를 다시 종료하고 한 번 더
                log("   → 런처를 다시 종료하고 복사를 재시도합니다...")
                sh(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'lineagem_launcher|lineagem_island|lineagem_ocr|lineagem_dungeon' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
                time.sleep(2)
            else:
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
