# -*- coding: utf-8 -*-
u"""🩺 로컬 진단 — 좌표가 왜 안 들어오나 · 녹화가 왜 안 먹히나 (2026-11-04).

    py check_local.py

🚫 아무것도 바꾸지 않는다. 클릭도 하지 않는다. **보여주기만** 한다.
사용자: *"로컬에 역산한 좌표들이 안 들어온다니까"* ·
       *"여전히 마우스/키 녹화하기 안 돼. 재부팅을 하고 다시 시작해도 안 들어와 있다고"*
"""
import sys, os, io, json, glob, hashlib, time
import ast

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

# ── ⑦ 🌙 수호성 ──────────────────────────────────
#    🚨 안 돼요 신고가 오면 **여기부터** 본다.
#       수호성은 ① 그림 ② 자동 켬/끔 ③ **확대한 창(1200px 넘음)**
#       셋이 다 맞아야 돌아간다. 하나라도 안 맞으면 **조용히** 지나간다.
_IMGD = os.path.join(DESK, "click_templates")
try:
    LOG = io.open(os.path.join(LA, "click_log.txt"), encoding="utf-8",
                  errors="replace").read().split(chr(10))[-4000:]
except Exception:
    LOG = []
print("\n⑦ 🌙 수호성")
_sw = []
try:
    for f in sorted(os.listdir(_IMGD)):
        if f.startswith("suho_") and f.lower().endswith(".png"):
            _sw.append(f)
except Exception:
    pass
_need = ("suho_screen", "suho_info", "suho_card", "suho_ok")
_miss = [n for n in _need if not any(f.startswith(n) for f in _sw)]
print("   그림 %d장  %s" % (len(_sw), ", ".join(_sw[:10]) or "(없다)"))
if _miss:
    print("   ⚠ **없는 그림: %s** → 🔄 업데이트를 한 번 더 눌러주세요"
          % ", ".join(_miss))
else:
    print("   ✔ 필요한 그림은 다 있다")
_cf = jload(os.path.join(DESK, "coords.json")) or {}
_on = _cf.get("suho_auto_on", True)
print("   자동 띄우기: %s" % ("✔ 켬" if _on else
      "⚠ **꿈** — 각성 옆 [🌙 수호성] 옆 버튼으로 켜주세요"))

#    🖥 지금 리니지M 창 크기 — **1200px 넘는 창이 없으면 수호성은 안 돌다**
_wins = []
try:
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _cb(h, _):
        try:
            if not u.IsWindowVisible(h) or u.IsIconic(h):
                return True
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            t = b.value or ""
            if not t.startswith("\ub9ac\ub2c8\uc9c0M") or t.startswith("\ub9ac\ub2c8\uc9c0M \uc790\ub3d9 \uc2e4\ud589"):
                return True
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            _wins.append((t, r.right - r.left, r.bottom - r.top))
        except Exception:
            pass
        return True
    u.EnumWindows(CB(_cb), 0)
except Exception as e:
    print("   (창 목록을 못 읽었다 %s)" % str(e)[:40])
if _wins:
    _big = [w for w in _wins if w[1] >= 1200]
    print("   리니지M 창 %d개 · 가로: %s"
          % (len(_wins), ", ".join(str(w[1]) for w in _wins[:8])))
    if _big:
        print("   ✔ 1200px 넘는 창 %d개 — 수호성을 할 수 있다 (%s %dx%d)"
              % (len(_big), _big[0][0][:20], _big[0][1], _big[0][2]))
    else:
        print("   ⚠ **전부 작은 창이다** — 수호성은 🔍 **확대한 창(1200px 이상)에서만** 한다.")
        print("     작은 창에서는 카드 장수·수호석 판정이 흔들려 돈을 써버릴 수 있어 막아두었다")
else:
    print("   (리니지M 창이 안 켜져 있다)")

_sl = [l for l in LOG if "[수호성]" in l]
print("   최근 기록 %d줄 중 마지막 8줄:" % len(_sl))
for l in _sl[-8:]:
    print("     " + l.strip()[:150])
if not _sl:
    print("     ⚠ **기록이 한 줄도 없다** — 감지가 한 번도 안 돌았다는 뜻이다.")
    print("       코드가 올지 않았거나(① 확인) 그림이 없거나 자동이 꺼져 있다")

# ── ⑧ 🩹 복구 ──────────────────────────────────────
#    🗂 복구는 **탭이 둘**이다 — 경험치 복구 · 아이템(장비) 복구.
#       그림이 하나라도 없으면 **예전 흐름(첫 줄 하나)** 으로 돌아 장비를 안 한다.
print("\n⑧ 🩹 복구")
_fn = {"fix_tab_exp": "경험치 탭", "fix_tab_item": "아이템 탭",
       "fix_all": "모두 복구", "fix_free": "일일무료복구",
       "fix_cert": "구호증서복구", "fix_quit": "종료창"}
_lack = []
for f, ko in _fn.items():
    p = os.path.join(_IMGD, f + ".png")
    if os.path.exists(p):
        print("   %-14s %-12s %6dB  %s" % (f, ko, sz(p), when(p)))
    else:
        print("   %-14s %-12s **없다**" % (f, ko))
        if f != "fix_cert":
            _lack.append(ko)
_mt = jload(os.path.join(_IMGD, "fix_tab_meta.json"))
print("   기준 창 가로: %s" % (_mt.get("w") if _mt else "(없다 → 491 로 본다)"))
if _lack:
    print("   ⚠ **%s 그림이 없다** → 탭 흐름을 안 타고 "
          "**예전처럼 첫 줄 하나만** 복구한다. 🔄 업데이트를 다시 눌러주세요" % ", ".join(_lack))
else:
    print("   ✔ 탭 흐름에 필요한 그림이 다 있다 (경험치 → 아이템 순서로 돌면 된다)")

_fl = [l for l in LOG if "fix #" in l]
print("   최근 기록 %d줄 중 마지막 14줄:" % len(_fl))
for l in _fl[-14:]:
    print("     " + l.strip()[:150])
if not _fl:
    print("     ⚠ **기록이 한 줄도 없다** — 복구를 한 번도 안 돌렸다")
_shot = os.path.join(LA, "click_templates", "_fixtab")
if os.path.isdir(_shot):
    _ss = sorted(os.listdir(_shot))[-5:]
    if _ss:
        print("   🗂 막혔을 때 저장한 화면 (%s):" % _shot)
        for f in _ss:
            print("     " + f)

# ── ⑨ 🏝 섬/던전 (잊섬 등) ─────────────────────────────────────────
# 🚨 2026-11-04 17:15~22:41 (5시간 26분) 동안 `NEVER_ISLAND=False` 로 배포가 열려
#    있었다. 그 사이 🔄 를 누른 로컬은 잊섬·악몽의섬·에카·오만의탑 좌표와
#    프리셋이 **메인 것으로 통째로** 갈렸다 (= "좌표가 날아갔다").
#    되살리기: `py fix_local_island.py` → `--go`
print("\n⑨ 🏝 섬/던전 — 좌표·실행 대상")
_if = os.path.join(DESK, "island_coords.json")
try:
    _isz, _ism = os.path.getsize(_if), time.strftime(
        "%m-%d %H:%M", time.localtime(os.path.getmtime(_if)))
except Exception:
    _isz, _ism = 0, "(없음)"
print("   island_coords.json  %s B · %s" % ("{:,}".format(_isz), _ism))
_id = {}
try:
    _id = json.load(io.open(_if, encoding="utf-8-sig")) or {}
except Exception as _e:
    print("   🚫 읽을 수 없다: %s" % str(_e)[:60])

# 섬 실행기의 칸 수 (코드에서 읽는다 — 손으로 적으면 어긋난다)
_clk = {}
try:
    _isrc = io.open(os.path.join(DESK, "lineagem_island.py"),
                    encoding="utf-8").read()
    _i0 = _isrc.index("CLICKS_BY_KEY")
    _i1 = _isrc.index("}", _i0) + 1
    _clk = ast.literal_eval(_isrc[_isrc.index("{", _i0):_i1])
except Exception:
    pass


def _nco(sl):
    if not isinstance(sl, dict):
        return 0
    return len([c for c in (sl.get("coords") or []) if c])


print("   던전                 슬롯  ON  좌표합  **실행대상**  칸수   비고")
print("   " + "-" * 76)
for _k in [x for x in _id if not str(x).startswith("_")]:
    _L = _id.get(_k) or []
    if not isinstance(_L, list):
        continue
    _on = [i for i, s_ in enumerate(_L)
           if isinstance(s_, dict) and s_.get("enabled", True)]
    # 🎯 섬 실행기 `_run` 의 targets 와 **같은 조건**:
    #    enabled(없으면 ON) 이고 (좌표가 하나라도 있거나 방향이 하나라도 있다)
    _tg = [i for i, s_ in enumerate(_L)
           if isinstance(s_, dict) and s_.get("enabled", True)
           and (any(c for c in (s_.get("coords") or []))
                or any(s_.get("dirs") or []))]
    _cs = sum(_nco(s_) for s_ in _L)
    _note = ""
    if not _L:
        _note = "🚫 슬롯이 없다"
    elif not _tg:
        if not _on:
            _note = "🚫 **전부 OFF** — 그 던전 창에서 슬롯을 ON"
        else:
            _note = "🚫 **좌표·방향이 전부 비었다**"
    elif len(_tg) < len(_on):
        _note = "⚠ ON 인데 좌표가 없는 슬롯 %s" % [i + 1 for i in _on if i not in _tg]
    print("   %-20s %3d %3d %6d %8d %6s   %s"
          % (_k, len(_L), len(_on), _cs, len(_tg),
             _clk.get(_k, "-"), _note))

# 🧪 프리셋 — 11-04 배포가 `presets:True` 였다
_pr = _id.get("_presets") or {}
if _pr:
    print("   🧪 프리셋: " + " · ".join("%s %d개" % (k, len(v) if hasattr(v, "__len__")
                                                  else 0) for k, v in _pr.items()))

# 📦 '날아가기 전' 백업이 있나 (되살릴 수 있나)
_bd = os.path.join(LA, "backups")
_bad = time.mktime(time.strptime("2026-11-04 17:00", "%Y-%m-%d %H:%M"))
_old = []
for _p in glob.glob(os.path.join(_bd, "*island_coords.json")):
    try:
        _m = os.path.getmtime(_p)
    except Exception:
        continue
    if _m < _bad and os.path.getsize(_p) > 2000:
        _old.append((_m, _p))
_old.sort(reverse=True)
print("   📦 '날아가기 전'(11-04 17:00 이전) 백업 %d개%s"
      % (len(_old), ("  최근: " + time.strftime("%m-%d %H:%M",
                                               time.localtime(_old[0][0])))
         if _old else ""))
if _old:
    print("      → 되살리려면  py fix_local_island.py      (보기)")
    print("                     py fix_local_island.py --go (실행)")
else:
    print("      → 백업이 없다. 한 슬롯만 다시 찍고 그 던전 창의")
    print("        **[📋 전체붙임]** 을 누르면 16슬롯에 퍼진다 (창 위치 자동보정)")

# ⏰ 반복 상태 (꺼져 있으면 ⏰ 가 안 걸린 것 — 실행 자체와는 별개다)
_rp = os.path.join(LA, "island_repeat.json")
try:
    _rd = json.load(io.open(_rp, encoding="utf-8-sig")) or {}
    _cnt = len([k for k in _rd if "|" in str(k)])
    print("   ⏰ island_repeat.json  걸린 예약 %d개" % _cnt)
except Exception:
    print("   ⏰ island_repeat.json  (없다 — 걸린 예약 없음)")

# 🗒 최근 실행 기록 — 왜 안 돌았는지가 여기 남는다
_rl = os.path.join(LA, "repeat_log.txt")
try:
    _ls = [l.rstrip() for l in io.open(_rl, encoding="utf-8",
                                       errors="replace").read().split("\n")
           if l.strip()]
    print("   🗒 repeat_log.txt 마지막 14줄:")
    for l in _ls[-14:]:
        print("     " + l[:112])
except Exception:
    print("   🗒 repeat_log.txt (없다 — 섬/던전을 한 번도 안 돌렸다)")

# ── ⑨-2 🗡 라스타바드 (2026-11-14) ─────────────────────────────────
# 사용자: *"여기에서 라바는 잘되는데 로컬에서 안되는 상황임"*
# 메인에서는 로컬 화면도 기록도 볼 수 없다 — 원인이 갈리는 것을 한 화면에 모은다.
print("\n⑨-2 🗡 라스타바드 — 슬롯 설정 · 그림 · 최근 기록")
_RK = "토요일_악몽의섬"
try:
    _ct = os.path.join(DESK, "click_templates")
    _need = ["rasta_28.png", "rasta_28_meta.json", "rasta_29.png", "rasta_31.png",
             "rasta_31_meta.json", "rasta_32.png", "rasta_33.png", "rasta_33_meta.json",
             "rasta_34.png", "rasta_36.png", "rasta_36_thr.json", "card_라스타바드.png"]
    _miss = [n for n in _need if not os.path.exists(os.path.join(_ct, n))]
    print("   그림: " + ("✔ 필요한 것이 다 있다" if not _miss
                         else "🚫 **없는 것** " + ", ".join(_miss) + "  → 🔄 업데이트"))
    for _n in ("rasta_28_meta.json", "rasta_33_meta.json"):
        try:
            print("     %s = %s" % (_n, json.dumps(json.load(io.open(
                os.path.join(_ct, _n), encoding="utf-8")), ensure_ascii=False)))
        except Exception:
            pass
    _isrc2 = ""
    try:
        _isrc2 = io.open(os.path.join(DESK, "lineagem_island.py"), encoding="utf-8").read()
    except Exception:
        pass
    _has = [(k, (k in _isrc2)) for k in ("_rec_here", "_rec_settle", "rasta_short",
                                         "rasta_find_pair", "_rasta_auto_xy",
                                         "_preset_ship_overlay")]
    print("   코드: " + " · ".join("%s %s" % (k, "✔" if v else "🚫없음") for k, v in _has))
    # 🚢 프리셋 배포판 (2026-11-14) — 로컬은 칸6·27~34 를 이 파일 것으로 맞춘다
    _ship = None
    try:
        _ship = json.load(io.open(os.path.join(_ct, "rasta_preset.json"), encoding="utf-8-sig"))
        _sf = (_ship.get("floors") or {})
        print("   🚢 프리셋 배포판: ✔ ver %s · %s" % (_ship.get("ver"), " / ".join(
            "%s %s" % (f, " ".join("%d%s" % (int(k) + 1, {"img": "🖼", "see": "👁", "rec": "⏺", "del": "✖",
                                                          "card": "🃏"}.get(v.get("act"), "↗"))
                                   for k, v in sorted(_sf[f].items(), key=lambda kv: int(kv[0]))))
            for f in _sf)))
    except Exception:
        print("   🚢 프리셋 배포판: 🚫 **없다** (click_templates\\rasta_preset.json) → 🔄 업데이트")
    # 지금 리니지M 창 격자 (녹화 좌표가 자기 클라 안인지 보려고)
    _gr = []
    try:
        import ctypes
        from ctypes import wintypes
        _u = ctypes.windll.user32
        _ws = []
        def _cb(h, _l):
            if _u.IsWindowVisible(h):
                b = ctypes.create_unicode_buffer(200); _u.GetWindowTextW(h, b, 200)
                c = ctypes.create_unicode_buffer(60); _u.GetClassNameW(h, c, 60)
                if b.value.startswith(u"리니지M l") and c.value == "GLFW30":
                    r = wintypes.RECT(); _u.GetWindowRect(h, ctypes.byref(r))
                    if r.right - r.left > 100:
                        _ws.append((r.left, r.top, r.right, r.bottom))
            return True
        _u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(_cb), 0)
        _xs = sorted(set(w[0] for w in _ws))
        _cols = []
        for x in _xs:
            if not _cols or x - _cols[-1][-1] > 200:
                _cols.append([x])
            else:
                _cols[-1].append(x)
        for col in _cols[:4]:
            _gr += sorted([w for w in _ws if w[0] in col], key=lambda w: w[1])[:4]
        print("   리니지M 창 %d개 · 격자 %d개 · 크기 %s" % (
            len(_ws), len(_gr), sorted(set("%dx%d" % (w[2] - w[0], w[3] - w[1]) for w in _ws))))
    except Exception as _e:
        print("   (창을 못 읽었다 %s)" % str(_e)[:40])
    _sl = _id.get(_RK) or []
    _rs = []
    for _i, _s in enumerate(_sl):
        if not isinstance(_s, dict):
            continue
        _ra = _s.get("rasta") or {}
        if not any(str(k).isdigit() and 26 <= int(k) + 1 <= 35 for k in _ra):
            if _s.get("auto_home"):
                print("   #%02d 🔁 **악몽의섬으로 바뀌어 있다** (원래 '%s' — 라스타바드가 열리면 되돌아온다)"
                      % (_i + 1, _s.get("auto_home")))
            continue
        _rs.append(_i)
        _rc = _s.get("recs") or {}
        _bad = []
        for _k, _ev in sorted(_rc.items(), key=lambda kv: int(kv[0])):
            if not (26 <= int(_k) + 1 <= 35):
                continue
            _m = [(e[2], e[3]) for e in _ev if len(e) >= 4 and e[1] in ("md", "mu", "mm")]
            if _m and len(_gr) == 16:
                _r = _gr[_i]
                if not (_r[0] <= _m[0][0] < _r[2] and _r[1] <= _m[0][1] < _r[3]):
                    _wh = next((n + 1 for n, q in enumerate(_gr)
                                if q[0] <= _m[0][0] < q[2] and q[1] <= _m[0][1] < q[3]), 0)
                    _bad.append("칸%d→#%02d" % (int(_k) + 1, _wh))
        _co = _s.get("coords") or []
        print("   #%02d %-16s %s · 그림칸 %s · 녹화칸 %s · 칸29~35 좌표 %s%s%s" % (
            _i + 1, (_s.get("name") or "")[:16],
            ("ON" if _s.get("enabled", True) else "OFF"),
            ",".join(str(int(k) + 1) for k in sorted(_ra, key=int)),
            ",".join(str(int(k) + 1) for k in sorted(_rc, key=int)) or "없음",
            [j + 1 for j in range(28, 35) if j < len(_co) and _co[j]] or "없음",
            (" · 🗡첫 포털만" if _s.get("rasta_to") == 1 else ""),
            (("  🚨 **녹화가 다른 클라 좌표** " + " ".join(_bad)
              + " (새 코드는 틀 때 스스로 고친다)") if _bad else "")))
        # 🚢 이 슬롯이 배포판과 같은 구성인가 — 다르면 옛 프리셋으로 걸린 슬롯이다
        try:
            _sr = ((_ship or {}).get("floors") or {}).get(u"라스타바드") or {}
            _df = []
            for _k, _v in _sr.items():
                if int(_k) < 26:
                    continue
                _a = _v.get("act")
                if _a in ("img", "see"):
                    if ((_ra.get(_k) or {}).get("mode")) != _a:
                        _df.append("칸%d(그림 아님)" % (int(_k) + 1))
                    elif list((_ra.get(_k) or {}).get("off") or []) != list(_v.get("off") or []):
                        _df.append("칸%d(📍 다름)" % (int(_k) + 1))
                elif _a == "rec":
                    if not _rc.get(_k):
                        _df.append("칸%d(녹화 없음)" % (int(_k) + 1))
                    elif len(_rc.get(_k)) != len(_v.get("ev") or []):
                        _df.append("칸%d(녹화 다름)" % (int(_k) + 1))
            for _k in _rc:
                if 26 <= int(_k) < 34 and (_sr.get(_k) or {}).get("act") != "rec":
                    _df.append("칸%d(옛 녹화)" % (int(_k) + 1))
            if _sr:
                print("        " + ("✔ 배포판과 같은 구성" if not _df else
                                    "🚨 **옛 프리셋 구성이다** " + " ".join(_df)
                                    + " → 이 슬롯에서 프리셋 [라스타바드 …] 를 **다시 한 번** 누르세요"))
        except Exception:
            pass
    if not _rs:
        print("   ⚠ 라스타바드 프리셋이 걸린 슬롯이 **없다** — 그 슬롯에서 프리셋 [라스타바드 …] 를 눌러야 한다")
    _pp = (_id.get("_presets") or {}).get(_RK) or []
    for _pi, _p in enumerate(_pp):
        if isinstance(_p, dict) and (_p.get("floor") or "") == u"라스타바드":
            _it = _p.get("items") or {}
            print("   🧪 프리셋 '%s' src %s · 칸 %s" % (
                _p.get("name"), _p.get("src"),
                " ".join("%d%s" % (int(k) + 1, {"img": "🖼", "see": "👁", "rec": "⏺", "del": "✖",
                                                "card": "🃏"}.get((_it[k] or {}).get("act"), "↗"))
                         for k in sorted(_it, key=int)) or "(비어 있다)"))
    _rl2 = os.path.join(LA, "repeat_log.txt")
    _ls2 = [l.rstrip() for l in io.open(_rl2, encoding="utf-8", errors="replace").read().split("\n")
            if (u"[라스타]" in l or u"[전환]" in l or u"[녹화]" in l or u"[중단]" in l
                or (u"[카드]" in l and _RK in l) or u"[시작맞춤]" in l)]
    print("   🗒 라스타바드·카드·전환 기록 마지막 24줄 (어느 칸에서 멈췄는지가 여기 있다):")
    for l in _ls2[-24:]:
        print("     " + l[:150])
    _sd = os.path.join(LA, "click_templates", "_rasta")
    _fs = sorted(glob.glob(os.path.join(_sd, "*.png")), key=os.path.getmtime)
    print("   🗂 멈춘 화면 %d장 (%s)" % (len(_fs), _sd))
    for _p in _fs[-8:]:
        print("     " + os.path.basename(_p))
except Exception as _e:
    print("   (라스타바드 항목 오류: %s)" % str(_e)[:80])

# ── ⑩ 업데이트 기록 ────────────────────────────────────────────────
ul = os.path.join(LA, "update_log.txt")
print("\n⑩ 업데이트 기록 마지막 40줄  (%s)" % ul)
try:
    lines = io.open(ul, encoding="utf-8", errors="replace").read().split("\n")
    for ln in lines[-40:]:
        if ln.strip():
            print("   " + ln.rstrip())
except Exception as e:
    print("   (없다 — 업데이트를 아직 새 코드로 돌리지 않았다) %s" % str(e)[:50])
print("\n" + "=" * 72)
