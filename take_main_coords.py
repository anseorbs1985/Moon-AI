# -*- coding: utf-8 -*-
r"""📥 **메인 좌표를 통째로 받는다** — 새로 세팅한 컴퓨터용 (2026-11-18 사용자 요청).

사용자: *"좌표 전부다 가져올려면 뭐라고 쳐야해? 지금 배치도 전부 옛날꺼야 신규로 받아야해"*

    py take_main_coords.py         무엇을 받을지 **보여만** 준다 (아무것도 안 바꾼다)
    py take_main_coords.py --go    받는다 → 런처 재시작

하는 일
  ① GitHub 의 **최신** coords.json · island_coords.json 을 가져온다
     (`git show origin/main:…` — 이 컴퓨터 저장소 폴더의 파일은 보지 않는다.
      로컬은 좌표 파일에 skip-worktree 가 걸려 있어 낡아 있을 수 있다)
  ② 작업이 도는 중이면 기다린다 (safe_restart 와 같은 판단)
  ③ 런처·섬 실행기를 끄고
  ④ 지금 바탕화면 좌표를 %LOCALAPPDATA%\MoonAI\backups\<시각>_before_takemain_*.json 로 남기고
  ⑤ 메인 좌표로 바꾼 뒤
  ⑥ 런처를 다시 켠다 (뒤에서)

🚫 메인 컴퓨터에서는 거부한다 (메인 좌표가 원본이다).
🚫 이 컴퓨터의 계정(accounts.json)·설정(local_config.json)은 건드리지 않는다.
"""
import io, os, sys, json, time, shutil, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NO = 0x08000000                       # CREATE_NO_WINDOW
REPO = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.dirname(REPO)
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI")
FILES = ("coords.json", "island_coords.json")


def git(*a):
    r = subprocess.run(["git", "-C", REPO] + list(a), capture_output=True,
                       creationflags=NO, timeout=120)
    return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")


def count(d):
    """좌표 개수 ([x, y] 짝을 센다)"""
    n = 0
    st = [d]
    while st:
        x = st.pop()
        if isinstance(x, dict):
            st.extend(x.values())
        elif isinstance(x, list):
            if (len(x) == 2 and all(isinstance(v, (int, float)) for v in x)):
                n += 1
            else:
                st.extend(x)
    return n


def main():
    go = "--go" in sys.argv
    if not os.path.exists(os.path.join(DESK, "lineagem_launcher.py")):
        print("🚫 바탕화면(런처 폴더)을 못 찾았다:", DESK)
        return 2
    try:
        lc = json.load(io.open(os.path.join(DESK, "local_config.json"),
                               encoding="utf-8-sig"))
    except Exception:
        lc = {}
    if lc.get("is_main"):
        print("🚫 여기는 **메인 컴퓨터**다 — 메인 좌표가 원본이라 받지 않는다.")
        return 2

    print("① GitHub 에서 최신 좌표를 가져온다...")
    rc, _, err = git("fetch", "origin")
    if rc != 0:
        print("🚫 git fetch 실패:", err.strip()[:300])
        return 2
    new = {}
    for f in FILES:
        rc, out, err = git("show", "origin/main:" + f)
        if rc != 0:
            print("🚫 GitHub 에 %s 가 없다: %s" % (f, err.strip()[:200]))
            return 2
        try:
            new[f] = (out, json.loads(out.decode("utf-8-sig")))
        except Exception as e:
            print("🚫 %s 를 못 읽었다: %s" % (f, e))
            return 2
        rc, when, _ = git("log", "-1", "--format=%ci", "origin/main", "--", f)
        cur = os.path.join(DESK, f)
        try:
            old = json.load(io.open(cur, encoding="utf-8-sig"))
            oc = "%d개" % count(old)
        except Exception:
            oc = "없음"
        print("   %-20s GitHub 판 %s · 좌표 %d개   (지금 이 컴퓨터 %s)"
              % (f, when.decode().strip()[:16], count(new[f][1]), oc))

    if not go:
        print()
        print("(보기만 했다 — 받으려면:  py take_main_coords.py --go )")
        return 0

    # ② 작업이 도는 중이면 기다린다
    try:
        sys.path.insert(0, REPO)
        import safe_restart as sr
        t0 = time.time()
        while True:
            b, why = sr.busy_now()
            if not b:
                break
            if time.time() - t0 > sr.WAIT_MAX:
                print("🚨 작업이 끝나지 않는다 — 끝난 뒤 다시 실행하세요:", why)
                return 2
            print("⏳ 작업이 끝나기를 기다린다 —", why, flush=True)
            time.sleep(5)
    except Exception as e:
        print("⚠ 작업 확인을 못 했다 (그대로 진행):", e)

    # ③ 런처·섬 실행기 끄기
    print("③ 런처를 끈다...")
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR "
          "Name='python.exe'\" | Where-Object { $_.CommandLine -match "
          "'lineagem_launcher|lineagem_island|lineagem_ocr|lineagem_dungeon' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, creationflags=NO, timeout=60)
    time.sleep(2.0)

    # ④ 백업  ⑤ 바꾸기
    bk = os.path.join(LOCAL, "backups")
    os.makedirs(bk, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    for f in FILES:
        cur = os.path.join(DESK, f)
        if os.path.exists(cur):
            dst = os.path.join(bk, "%s_before_takemain_%s" % (ts, f))
            shutil.copy2(cur, dst)
            print("④ 백업", dst)
        tmp = cur + ".tmp"
        with open(tmp, "wb") as fp:
            fp.write(new[f][0])
        with open(tmp, "rb") as fp:
            if fp.read() != new[f][0]:
                print("🚫 %s 쓰기 확인 실패 — 바꾸지 않았다" % f)
                os.remove(tmp)
                continue
        os.replace(tmp, cur)
        print("⑤ %s → 메인 좌표 %d개" % (f, count(new[f][1])))

    # ⑥ 런처 다시 켜기 (워치독 — 이미 떠 있으면 아무것도 안 한다)
    wd = os.path.join(DESK, "lineagem_watchdog.py")
    try:
        if os.path.exists(wd):
            exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(exe):
                exe = "pythonw"
            subprocess.Popen([exe, wd], cwd=DESK, creationflags=NO)
        else:
            subprocess.run(["schtasks", "/run", "/tn", "LineageM_Watchdog"],
                           capture_output=True, creationflags=NO)
        print("⑥ 런처를 다시 켰다")
    except Exception as e:
        print("⚠ 런처를 못 켰다 — 손으로 켜주세요:", e)

    print()
    print("✅ 끝. 이제 런처에서:")
    print("   1) 리니지M 클라 16개를 켠다")
    print("   2) [🪟 재배치] → [📐 창 전체복원]   (메인과 같은 자리·크기로)")
    print("   3) [📍 위치 전체저장]                (재부팅해도 그 자리로 뜨게)")
    print("   4) [💾 좌표저장]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
