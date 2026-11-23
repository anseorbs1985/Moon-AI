# -*- coding: utf-8 -*-
r"""🔁 **돌고 있는 작업을 죽이지 않고** 런처를 재시작한다.

🚨 2026-11-11 사고 — 퀘스트받기가 11클라째 돌고 있는데 배포하느라 워치독을
   돌려 **그 자리에서 죽였다**. 사용자: *"왜 1개 클라만 하고 꺼버리냐"*
   요약 로그(`🎁 … 받았습니다`)가 없는 것이 그 증거였다.

   py safe_restart.py            돌고 있으면 **기다렸다가** 재시작
   py safe_restart.py --check    보기만 한다 (재시작 안 함)
   py safe_restart.py --force    기다리지 않고 바로 (🚫 꼭 필요할 때만)
"""
import io, os, re, sys, time, json, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI")
LOG = os.path.join(LOCAL, "click_log.txt")
RUN = os.path.join(LOCAL, "island_run.json")

# 🎯 **작업이 도는 중**이라는 표시 — 이 태그가 최근에 찍혔으면 기다린다.
#    🚫 감시·확인만 하는 것(`[물약감시]`·`[격자]`·`[마을감시]`·`[클릭확인]`)은 뺀다.
BUSY_TAGS = ("[퀘스트]", "[사냥]", "[스케줄]", "[절전해제]", "[과거섬]",
             "[용던고고]", "[작위]", "[인형탐험]", "[우편]", "[도감]",
             "[각성강화]", "[수호성]", "[클릭]", "[오만의탑]", "fix #",
             "[보조서커스]", "[아이템정리]")
# ⏳ **오래 쉬면서 도는 작업** — 기다리는 동안(4분 등) 로그가 없어 위 25초 판정으로는 '조용하다' 가 된다
#    (2026-11-23 📜 서커스주문서). 시작 줄 뒤에 끝 줄도, 그 뒤 런처 재시작도 없으면 **돌고 있다**.
LONG_TASKS = (("[서커스주문서]", "📜 시작", "📜 끝"),
              ("[거래소등록]", "💱 시작", "💱 끝"))
LONG_MAX = 4 * 3600.0
BUSY_SEC = 25.0        # 이 안에 작업 로그가 있으면 **돌고 있다**
WAIT_MAX = 600.0       # 최대 이만큼 기다린다
NO = 0x08000000        # CREATE_NO_WINDOW — 검은 창이 번쩍이지 않게


def last_busy():
    """(몇 초 전, 그 줄) — 작업 로그가 없으면 (None, '')"""
    try:
        with io.open(LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 60000))
            txt = f.read().decode("utf-8", "replace")
    except Exception:
        return None, ""
    now = time.localtime()
    best = None
    for ln in txt.splitlines():
        if not any(t in ln for t in BUSY_TAGS):
            continue
        m = re.match(r"(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)", ln)
        if not m:
            continue
        mo, d, hh, mm, ss = (int(x) for x in m.groups())
        try:
            t = time.mktime((now.tm_year, mo, d, hh, mm, ss, 0, 0, -1))
        except Exception:
            continue
        best = (time.time() - t, ln.strip())
    return best if best else (None, "")


def island_alive():
    try:
        pid = int((json.load(io.open(RUN, encoding="utf-8-sig")) or {}).get("pid") or 0)
    except Exception:
        return 0
    if pid <= 0:
        return 0
    try:
        o = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=NO).stdout
        return pid if str(pid) in o else 0
    except Exception:
        return 0


def long_open():
    """오래 도는 작업이 아직 안 끝났나 → 그 시작 줄 (없으면 '')"""
    try:
        with io.open(LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return ""
    now = time.localtime()
    for tag, st, en in LONG_TASKS:
        last = None
        for ln in lines:
            if "[재시작] 켜짐" in ln:
                last = None                      # 런처가 다시 켜졌으면 그 작업은 죽었다
            elif tag in ln and st in ln:
                last = ln
            elif tag in ln and en in ln:
                last = None
        if last:
            m = re.match(r"(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)", last)
            try:
                mo, d, hh, mm, ss = (int(x) for x in m.groups())
                if time.time() - time.mktime((now.tm_year, mo, d, hh, mm, ss, 0, 0, -1)) < LONG_MAX:
                    return last.strip()
            except Exception:
                return last.strip()
    return ""


def busy_now():
    """(바쁜가, 이유)"""
    pid = island_alive()
    if pid:
        return True, "🏝 섬/던전 실행기가 돌고 있다 (pid %d)" % pid
    lo = long_open()
    if lo:
        return True, "⏳ 오래 도는 작업이 아직 안 끝났다 — %s" % lo[:90]
    age, ln = last_busy()
    if age is not None and age < BUSY_SEC:
        return True, "⏳ %.0f초 전 작업 로그 — %s" % (age, ln[:90])
    return False, ("✔ 조용하다" if age is None
                   else "✔ 조용하다 (마지막 작업 로그 %.0f초 전)" % age)


def main():
    chk = "--check" in sys.argv
    force = "--force" in sys.argv
    t0 = time.time()
    while True:
        b, why = busy_now()
        if not b or force:
            if b:
                print("⚠ 돌고 있지만 --force 라 그냥 간다 — %s" % why)
            else:
                print(why)
            break
        el = time.time() - t0
        if el >= WAIT_MAX:
            print("🚨 %.0f초를 기다렸는데 아직 돈다 — %s" % (el, why))
            print("   그대로 재시작하면 그 작업이 **죽는다**. 끝나고 다시 부르거나")
            print("   정말 필요하면 py safe_restart.py --force")
            return 2
        print("⏳ 기다린다 (%.0fs) — %s" % (el, why), flush=True)
        time.sleep(5)
    if chk:
        print("(--check — 재시작하지 않았다)")
        return 0
    print("🔁 워치독으로 재시작한다...")
    subprocess.run(["schtasks", "/run", "/tn", "LineageM_Watchdog"],
                   capture_output=True, creationflags=NO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
