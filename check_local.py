# -*- coding: utf-8 -*-
u"""🩺 로컬 진단 — 좌표가 왜 안 들어오나 · 녹화가 왜 안 먹히나 (2026-11-04).

    py check_local.py

🚫 아무것도 바꾸지 않는다. 클릭도 하지 않는다. **보여주기만** 한다.
사용자: *"로컬에 역산한 좌표들이 안 들어온다니까"* ·
       *"여전히 마우스/키 녹화하기 안 돼. 재부팅을 하고 다시 시작해도 안 들어와 있다고"*
"""
import sys, os, io, json, glob, hashlib, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
DESK = HERE if not os.path.basename(HERE).startswith("Moon-AI") else os.path.dirname(HERE)
for _c in (DESK, os.path.join(os.path.expanduser("~"), "Desktop"),
           os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")):
    if os.path.exists(os.path.join(_c, "lineagem_launcher.py")):
        DESK = _c
        break
REPO = HERE if os.path.exists(os.path.join(HERE, "share_island.json")) \
    else os.path.join(DESK, "Moon-AI")
LA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI")


def md5(p):
    try:
        return hashlib.md5(io.open(p, "rb").read()).hexdigest()[:8]
    except Exception:
        return "------"


def sz(p):
    try:
        return os.path.getsize(p)
    except Exception:
        return -1


def when(p):
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
    except Exception:
        return "--"


def jload(p):
    try:
        return json.load(io.open(p, encoding="utf-8-sig"))
    except Exception:
        return None


print("=" * 72)
print("🩺 로컬 진단   바탕화면: %s" % DESK)
print("              저장소  : %s" % REPO)
print("=" * 72)

# ── ① 코드가 왔나 ───────────────────────────────────────────────────
print("\n① 코드가 저장소 것과 같은가  (다르면 🔄 업데이트를 한 번 더)")
same = True
for f in ("lineagem_launcher.py", "lineagem_update.py", "lineagem_island.py",
          "precise_click.py"):
    a, b = os.path.join(DESK, f), os.path.join(REPO, f)
    ma, mb = md5(a), md5(b)
    ok = (ma == mb and ma != "------")
    same = same and ok
    print("   %s %-24s 바탕 %s %9d B %s   저장소 %s"
          % ("✔" if ok else "✘", f, ma, sz(a), when(a), mb))
print("   → %s" % ("전부 같다" if same
                   else "⚠ 다르다 — 코드를 아직 못 받았다. 🔄 를 한 번 더 누르세요"))

# ── ② 이 컴퓨터는 로컬인가 ──────────────────────────────────────────
lc = jload(os.path.join(DESK, "local_config.json")) or {}
print("\n② local_config.json   is_main=%r · pc_name=%r"
      % (lc.get("is_main"), lc.get("pc_name")))
if lc.get("is_main"):
    print("   ⚠ **메인으로 설정돼 있다** — 그래서 좌표 배포가 통째로 건너뛰어진다!")
    print("     (sync_island_keys·sync_coord_keys 는 `if not is_main:` 안에 있다)")
    print("     로컬이라면 local_config.json 의 is_main 을 지우세요.")

# ── ③ 좌표 잠금 ────────────────────────────────────────────────────
ck = jload(os.path.join(LA, "coord_lock.json")) or {}
print("\n③ 🔒 좌표잠금 (%s)" % os.path.join(LA, "coord_lock.json"))
print("   keys  : %s" % (ck.get("keys") or "(없음)"))
print("   island: %s" % (ck.get("island") or "(없음)"))

# ── ④ 배포 지시서 ──────────────────────────────────────────────────
si = jload(os.path.join(REPO, "share_island.json")) or {}
sc = jload(os.path.join(REPO, "share_coords.json")) or {}
print("\n④ 배포 지시서")
print("   share_island.json  keys %d · presets=%r · ignore_lock=%r"
      % (len(si.get("keys") or []), si.get("presets"), si.get("ignore_lock")))
print("   share_coords.json  keys %d · force %d · ignore_lock=%r"
      % (len(sc.get("keys") or []), len(sc.get("force") or []), sc.get("ignore_lock")))
try:
    sys.path.insert(0, REPO)
    import lineagem_update as U
    print("   NEVER_ISLAND=%r · NEVER_COORD_KEYS=%r"
          % (U.NEVER_ISLAND, sorted(U.NEVER_COORD_KEYS)))
    import inspect
    src = inspect.getsource(U.sync_island_keys)
    print("   sync_island_keys 가 ignore_lock 을 보는가: %s"
          % ("✔ 본다" if "ignore_lock" in src else "✘ 모른다 — 옛 코드다"))
except Exception as e:
    print("   ⚠ lineagem_update 를 못 읽었다: %s" % e)

# ── ⑤ 던전 좌표가 메인 것과 같은가 ─────────────────────────────────
print("\n⑤ 던전 좌표가 메인 것과 같은가  (✔=받았다 / ✘=아직 로컬 것)")
mine = jload(os.path.join(DESK, "island_coords.json")) or {}
main = jload(os.path.join(REPO, "share_island_data.json")) or {}
kc = si.get("keep_cells") or {}
if not main:
    print("   ⚠ share_island_data.json 이 없다 — 저장소를 못 받았다")
for k in (si.get("keys") or []):
    a, b = mine.get(k), main.get(k)
    if not isinstance(a, list) or not isinstance(b, list):
        print("   ?  %-16s 로컬 %s · 메인 %s" % (k, type(a).__name__, type(b).__name__))
        continue
    cells = set(int(x) for x in (kc.get(k) or [])) if isinstance(kc, dict) \
        else set(int(x) for x in (kc or []))
    nsame = ndiff = 0
    for s1, s2 in zip(a, b):
        c1 = (s1 or {}).get("coords") or []
        c2 = (s2 or {}).get("coords") or []
        for i, (p, q) in enumerate(zip(c1, c2)):
            if i in cells:
                continue
            if p == q:
                nsame += 1
            else:
                ndiff += 1
    tot = nsame + ndiff
    pct = (100.0 * nsame / tot) if tot else 0
    print("   %s %-16s 같은 좌표 %d/%d (%.0f%%)%s"
          % ("✔" if pct > 95 else "✘", k, nsame, tot, pct,
             "   ← 아직 안 받았다" if pct <= 95 else ""))

# ── ⑥ 녹화·키보드 교체 ─────────────────────────────────────────────
print("\n⑥ 🎹 녹화 / ⌨ 키보드 교체")
zr = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Purple", "zone")
zs = []
if os.path.isdir(zr):
    for g in sorted(os.listdir(zr)):
        if len(g) == 36 and g.count("-") == 4 and os.path.isdir(os.path.join(zr, g, "lm")):
            zs.append(g)
print("   퍼플 zone 폴더: %d개   (%s)" % (len(zs), zr))
if not zs:
    print("   ⚠ 하나도 없다 — 퍼플로 리니지M 을 한 번 켰다 꺼야 폴더가 생긴다")
pm = jload(os.path.join(LA, "purple_zones.json")) or {}
print("   기억해둔 슬롯↔폴더 짝: %d개 (%s)"
      % (len(pm.get("slots") or []), pm.get("at", "-")))
try:
    sys.path.insert(0, DESK)
    import lineagem_launcher as LL
    print("   런처에 slot_zones_disk 가 있는가: %s"
          % ("✔ 있다" if hasattr(LL, "slot_zones_disk") else
             "✘ 없다 — 런처 코드가 옛 판이다 (🔄 한 번 더)"))
    if hasattr(LL, "slot_zones_disk"):
        print("   slot_zones_disk() → %d개" % len(LL.slot_zones_disk()))
except Exception as e:
    print("   ⚠ 런처를 못 읽었다 (런처가 켜져 있으면 정상): %s" % str(e)[:60])
kd = os.path.join(DESK, "키설정교체")
print("   폴더: %s" % kd)
for sub in ("1", "2", "3", "4", "5", "6", "키보드"):
    d = os.path.join(kd, sub)
    fs = [f for f in (os.listdir(d) if os.path.isdir(d) else [])
          if os.path.isfile(os.path.join(d, f))]
    print("     %-6s %s" % (sub, (" · ".join("%s (%d B)" % (f, sz(os.path.join(d, f)))
                                             for f in fs) if fs else "(빈 칸)")))

# ── ⑦ 업데이트 기록 ────────────────────────────────────────────────
ul = os.path.join(LA, "update_log.txt")
print("\n⑦ 업데이트 기록 마지막 40줄  (%s)" % ul)
try:
    lines = io.open(ul, encoding="utf-8", errors="replace").read().split("\n")
    for ln in lines[-40:]:
        if ln.strip():
            print("   " + ln.rstrip())
except Exception as e:
    print("   (없다 — 업데이트를 아직 새 코드로 돌리지 않았다) %s" % str(e)[:50])
print("\n" + "=" * 72)
