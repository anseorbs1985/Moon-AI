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
# 🚫 **런처를 import 하지 않는다** — 런처가 켜져 있으면 뮤텍스에 막혀
#    **출력 한 줄 없이 그대로 멈춘다** (2026-11-04 메인에서 실제로 여기서 죽었다).
#    소스에서 이름만 찾으면 된다.
try:
    _src = io.open(os.path.join(DESK, "lineagem_launcher.py"),
                   encoding="utf-8", errors="replace").read()
    print("   런처에 slot_zones_disk 가 있는가: %s"
          % ("✔ 있다" if "def slot_zones_disk" in _src else
             "✘ 없다 — 런처 코드가 옛 판이다 (🔄 한 번 더)"))
    for _nm in ("def rec_drop_all", "def rec_spread", "def fav_write"):
        print("   %-22s %s" % (_nm[4:], "✔" if _nm in _src else "✘ 옛 판"))
except Exception as e:
    print("   ⚠ 런처 소스를 못 읽었다: %s" % str(e)[:60])

kd = os.path.join(DESK, "키설정교체")
print("   폴더: %s" % kd)
for sub in ("1", "2", "3", "4", "5", "6", "키보드"):
    d = os.path.join(kd, sub)
    fs = [f for f in (os.listdir(d) if os.path.isdir(d) else [])
          if os.path.isfile(os.path.join(d, f))]
    print("     %-6s %s" % (sub, (" · ".join("%s (%d B)" % (f, sz(os.path.join(d, f)))
                                             for f in fs) if fs else "(빈 칸)")))


# ── ⑥-2 **교체가 실제로 됐나** — 이게 핵심이다 (2026-11-04) ─────────
#    폴더에 파일이 와 있어도 **[🎹 녹화교체] 를 눌러야** 16클라에 들어간다.
#    그리고 **클라가 켜져 있으면 런처가 거부한다** (켜진 채 바꾸면 끌 때 도로 덮어쓴다).
def _titles(recs):
    out = []
    for _k, v in (recs or {}).items():
        if isinstance(v, dict) and v.get("events"):
            out.append(str(v.get("title"))[:20])
    return out


want = []
for sub in ("1", "2", "3", "4", "5", "6"):
    d = os.path.join(kd, sub)
    fs = sorted(f for f in (os.listdir(d) if os.path.isdir(d) else [])
                if f.lower().endswith(".json"))
    for f in fs[:1]:                      # 칸마다 첫 파일 기준
        want += _titles((jload(os.path.join(d, f)) or {}).get("records"))
print("")
print("   폴더에 넣은 녹화 %d개: %s" % (len(want), " · ".join(want) or "(없음)"))

try:
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    _n = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        if u32.IsWindowVisible(h):
            ln = u32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(ln + 1)
            u32.GetWindowTextW(h, b, ln + 1)
            t = b.value or ""
            if t.startswith("리니지M") and not t.startswith("리니지M 자동 실행"):
                _n[0] += 1
        return True
    u32.EnumWindows(_cb, 0)
    print("   켜진 리니지M 창: %d개  %s" % (
        _n[0], "✔ 0개 — 지금 교체할 수 있다" if _n[0] == 0 else
        "⛔ 켜져 있으면 런처가 교체를 **거부한다** (전부 끄고 누를 것)"))
except Exception as e:
    print("   켜진 클라를 못 셌다: %s" % str(e)[:50])

# ⚠ zone 폴더에는 **지금 안 쓰는 옛 것**이 섞여 있다 (메인 실측: 25개 중 16개만 사용).
#     에 기억해둔 **지금 쓰는 16개**만 본다.
# ⚠ slots 는 {"name": .., "zone": GUID} **dict 리스트**다 (옛 튜플 아님)
_use = []
for r in (pm.get("slots") or []):
    if isinstance(r, dict):
        _use.append(str(r.get("zone") or "").upper())
    elif isinstance(r, (list, tuple)) and len(r) > 1:
        _use.append(str(r[1]).upper())
_zs = [g for g in zs if g.upper() in _use] or zs
if len(_zs) != len(zs):
    print("   (지금 쓰는 %d개만 본다 — 나머지 %d개는 옛 폴더)" % (len(_zs), len(zs) - len(_zs)))
same = diff = none = 0
rows = []
for g in _zs:
    rp = os.path.join(zr, g, "lm", "records", "records.json")
    if not os.path.exists(rp):
        none += 1
        rows.append((g[:8], "records.json 없음", "-"))
        continue
    got = _titles((jload(rp) or {}).get("records"))
    ok = bool(want) and got == want
    same += ok
    diff += (not ok)
    rows.append((g[:8], when(rp),
                 "✔ 같다" if ok else "✘ 다르다 → " + (" · ".join(got[:3]) or "빈 것")))
print("   퍼플 zone 의 녹화가 폴더 것과 같은가:")
for a, b, c in rows[:18]:
    print("     %-10s %-18s %s" % (a, b, c[:56]))
print("   → 같음 %d · 다름 %d · 파일없음 %d" % (same, diff, none))
if want and diff:
    print("   ⚠ **교체가 안 됐다** — 클라를 전부 끄고 [🎹 녹화교체] 를 눌러주세요")
elif want and same and not diff:
    print("   ✔ zone 전부 폴더의 녹화로 교체돼 있다")

# ⭐ 즐겨찾기(leveldb) — 바뀐 시각만
fv = []
for g in (_zs[:4] if _zs else zs[:4]):
    ld = os.path.join(zr, g, "lm", "cache", "Local Storage", "leveldb")
    if os.path.isdir(ld):
        for f in os.listdir(ld):
            if f.endswith(".log"):
                fv.append("%s %s" % (g[:8], when(os.path.join(ld, f))))
                break
print("   ⭐ 즐겨찾기 로그가 바뀐 때: %s" % (" | ".join(fv) or "(못 찾음)"))

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
