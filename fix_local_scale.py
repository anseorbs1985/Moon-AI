# -*- coding: utf-8 -*-
r"""📐 **섬/던전 좌표를 지금 창 크기로 역산한다** — 로컬 전용 (2026-11-09).

사용자: *"로컬에 섬/던전 실행기 좌표를 복구했는데 그냥 개판임.
        **역산 안 된 정보로 되어 있어서** 개판이야"*

### 🔎 무슨 일인가
2026-11-03 에 클라 창을 **491x276 → 546x307** 로 키우고 메인 좌표를 비율로
환산("역산")했다. 그런데 좌표는 **머신별**이라 로컬은 그 환산을 받지 못했다.
그래서 로컬이 옛 백업에서 되살리면 **491 시절 좌표**가 들어와 전부 어긋난다.

### ✅ 이 도구가 하는 일
좌표만 보고 **옛 격자를 스스로 역산**해 지금 창에 맞게 비율 환산한다.
```
① 지금 리니지M 창 16개를 읽는다 → 지금 격자·창 크기
② **같은 칸(j)을 가진 슬롯 쌍의 좌표 차이**로 옛 격자 간격을 구한다
   (같은 칸은 창 안 같은 자리라, 그 차이가 곧 격자 간격이다)
③ 옛 창 크기 = 격자 간격 − (옆바·상단바 두께, 지금 창에서 실제로 잰다)
④ 옛 창 왼쪽위는 '모든 좌표가 창 안에 들어가는 범위' 의 가운데로 잡는다
⑤ 새 좌표 = 지금창왼쪽위 + (옛 − 옛창왼쪽위) × (W새/W옛, H새/H옛)
⑥ **녹화(recs)의 마우스 좌표도** 같이 환산한다
```
🚫 **환산 뒤 모든 좌표가 자기 슬롯 창 안에 들어가지 않으면 거부한다.**
🚫 메인에서는 거부한다. 직전 상태는 `before_scale` 로 백업한다.

### 쓰는 법
```
py fix_local_scale.py --from 491x276            보여만 준다 (숫자를 확인하세요)
py fix_local_scale.py --from 491x276 --go      환산한다
py fix_local_scale.py --go           환산한다
py fix_local_scale.py 잊혀진섬 --go    그 던전만
py fix_local_scale.py --coords --go  coords.json(런처 좌표)도 같이
```
"""
import io, os, sys, json, time, shutil, ctypes
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
BK = os.path.join(LOCAL, "backups")
ISL = os.path.join(BASE, "island_coords.json")

# 격자 전제 — 슬롯 번호는 **열 우선** (1~4 가 1열, 5~8 이 2열 …)
COLS, ROWS = 4, 4
# 🚫 **환산하지 않는 던전** — 좌표가 게임창이 아니라 **옆 패널(CEFCLIENT)** 기준이다.
#    게임창 비율로 환산하면 틀린다 (2026-11-03 메인 환산에서도 이 둘은 손대지 않았다).
#    실측: 억지로 환산하면 오차 평균 361px.
#    🚫 빼지 말 것. 꼭 필요하면 이름을 직접 줘서 포함시킨다.
SKIP = (u"귀환주문서", u"카매사오기")
# 🔁 두 번 환산하면 두 배로 어긋난다 → 끝낼 때 이 크기를 적어두고, 같으면 거부한다
MARK_W, MARK_H = "_scale_w", "_scale_h"


def jload(p):
    try:
        with io.open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def is_main():
    return bool((jload(os.path.join(BASE, "local_config.json")) or {}).get("is_main"))


def med(v):
    v = sorted(v)
    if not v:
        return 0.0
    n = len(v)
    return float(v[n // 2]) if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def game_wins():
    """지금 떠 있는 리니지M **게임 창**을 격자 순서(열 우선)로."""
    u = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h) and not u.IsIconic(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            t = b.value
            c = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, c, 256)
            if (t.startswith(u"리니지M") and u"자동 실행" not in t
                    and c.value == "GLFW30" and u.GetWindow(h, 4) == 0):
                r = wintypes.RECT()
                u.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left > 300 and r.bottom - r.top > 150:
                    out.append([r.left, r.top, r.right, r.bottom, t])
        return True

    u.EnumWindows(cb, 0)
    if len(out) < COLS * ROWS:
        return out, None
    # 열로 묶고(가로 200px 안이면 같은 열) 각 열에서 위→아래
    out.sort(key=lambda w: w[0])
    cols, cur = [], [out[0]]
    for w in out[1:]:
        if w[0] - cur[-1][0] > 200:
            cols.append(cur)
            cur = [w]
        else:
            cur.append(w)
    cols.append(cur)
    cols = [c for c in cols if len(c) >= ROWS][:COLS]
    if len(cols) < COLS:
        return out, None
    grid = []
    for c in cols:
        c.sort(key=lambda w: w[1])
        grid += c[:ROWS]
    return out, grid


def bars(grid):
    """지금 격자에서 **옆바·상단바 두께**를 실제로 잰다."""
    W = grid[0][2] - grid[0][0]
    H = grid[0][3] - grid[0][1]
    gx = med([grid[i * ROWS][0] - grid[(i - 1) * ROWS][0] for i in range(1, COLS)])
    gy = med([grid[i][1] - grid[i - 1][1] for i in range(1, ROWS)])
    return W, H, gx, gy, int(round(gx - W)), int(round(gy - H))


def all_xy(slots):
    """[(슬롯0based, 칸, x, y, 어디), ...] — 좌표·녹화 마우스."""
    out = []
    for i, s in enumerate(slots):
        if not isinstance(s, dict):
            continue
        for j, c in enumerate(s.get("coords") or []):
            if c and len(c) >= 2:
                out.append((i, j, int(c[0]), int(c[1]), "coords"))
        for rk in ("recs", "recs_off"):
            for k, ev in (s.get(rk) or {}).items():
                for a, e in enumerate(ev or []):
                    if len(e) >= 4 and str(e[1]) in ("md", "mm", "mu"):
                        out.append((i, "%s|%s|%d" % (rk, k, a),
                                    int(e[2]), int(e[3]), rk))
    return out


def slot_box(pts, W, H):
    """슬롯마다 **옛 창 왼쪽위**를 따로 구한다 -> {슬롯: (x, y, 폭x, 폭y)}.

    그 슬롯 좌표가 **창 안(0..W, 0..H)** 에 들어가는 구간의 가운데를 쓴다.
    🚫 격자 간격을 쓰지 말 것 — 옛 배치는 창이 딱 붙어 있지 않아
       `창크기 = 간격 - 바` 가정이 틀린다 (실측 격자 683 · 창 491).
    구간 폭이 **좁을수록 정확하다** (좌표가 창 전체에 퍼져 있을 때).
    `None` = 그 슬롯 좌표가 창 크기보다 넓게 퍼져 있다 (크기 입력이 틀렸다)."""
    per = {}
    for i, j, x, y, w in pts:
        a = per.setdefault(i, [x, x, y, y])
        a[0] = min(a[0], x)
        a[1] = max(a[1], x)
        a[2] = min(a[2], y)
        a[3] = max(a[3], y)
    out = {}
    for i, (nx, xx, ny, xy) in per.items():
        lo_x, hi_x = xx - W, nx
        lo_y, hi_y = xy - H, ny
        if lo_x > hi_x or lo_y > hi_y:
            return None, i, (xx - nx, xy - ny)
        out[i] = ((lo_x + hi_x) / 2.0, (lo_y + hi_y) / 2.0,
                  hi_x - lo_x, hi_y - lo_y)
    return out, None, None


def spread(pts):
    """슬롯별 좌표가 퍼진 폭의 **최대** — 옛 창 크기의 하한이다."""
    per = {}
    for i, j, x, y, w in pts:
        a = per.setdefault(i, [x, x, y, y])
        a[0] = min(a[0], x); a[1] = max(a[1], x)
        a[2] = min(a[2], y); a[3] = max(a[3], y)
    if not per:
        return 0, 0
    return (max(a[1] - a[0] for a in per.values()),
            max(a[3] - a[2] for a in per.values()))


def main():
    if is_main():
        print()
        print(u"🚫 **여기는 메인 컴퓨터다** — 메인 좌표는 이미 역산돼 있다.")
        print(u"   이 도구는 **로컬에서만** 쓴다.")
        return 2

    argv = sys.argv[1:]
    go = "--go" in argv
    # 📐 **옛 창 크기** — 좌표만으로는 알 수 없다 (격자 간격 != 창 크기 + 바).
    #    로컬은 자기가 무엇을 썼는지 안다. 보통 491x276 이다.
    OW = OH = 0
    if "--from" in argv:
        try:
            _v = argv[argv.index("--from") + 1].lower().replace("*", "x")
            OW, OH = [int(t) for t in _v.split("x")[:2]]
        except Exception:
            OW = OH = 0
    _sk = False
    want = []
    for a in argv:
        if _sk:
            _sk = False
            continue
        if a == "--from":
            _sk = True
            continue
        if not a.startswith("-"):
            want.append(a)

    wins, grid = game_wins()
    print()
    print("=" * 96)
    print(u"📐 섬/던전 좌표를 **지금 창 크기로 역산** — 로컬 전용")
    print("=" * 96)
    print(u"   리니지M 게임 창 %d개" % len(wins))
    if grid is None:
        print()
        print(u"🚫 **4열 4줄 격자를 못 찾았다** (16개가 격자로 떠 있어야 한다).")
        print(u"   클라를 격자로 배치하고 다시 돌려주세요.")
        return 1
    W, H, GX, GY, SIDE, TOP = bars(grid)
    print(u"   지금 창 %dx%d · 격자 간격 %.0f x %.0f · 옆바 %dpx · 상단바 %dpx"
          % (W, H, GX, GY, SIDE, TOP))

    d = jload(ISL)
    if d is None:
        print(u"🚫 island_coords.json 을 못 읽는다: %s" % ISL)
        return 1
    keys = [k for k in d if not str(k).startswith("_") and isinstance(d[k], list)]
    if want:
        keys = [k for k in keys if any(w in k for w in want)]
    else:
        _sk = [k for k in keys if k in SKIP]
        keys = [k for k in keys if k not in SKIP]
        if _sk:
            print(u"   🚫 환산하지 않는 던전: %s" % u" · ".join(_sk))
            print(u"      (좌표가 **옆 패널** 기준이라 게임창 비율로 환산하면 틀린다)")
    # 🔁 이미 이 창 크기로 환산했으면 **또 하지 않는다** (두 배로 어긋난다)
    try:
        if int(d.get(MARK_W) or 0) == W and int(d.get(MARK_H) or 0) == H:
            print()
            print(u"✔ **이미 %dx%d 로 환산해 두었다** — 또 하면 두 배로 어긋난다." % (W, H))
            print(u"   되돌리려면  py fix_local_island.py --undo --go")
            return 0
    except Exception:
        pass
    if not keys:
        print(u"   되살릴 던전이 없다")
        return 1

    # 📐 옛 창 크기가 없으면 **하한**을 보여주고 멈춘다
    if not (OW > 100 and OH > 80):
        print()
        print(u"   📐 **옛 창 크기를 알려주세요** — 좌표만으로는 알 수 없습니다")
        print(u"      (옛 배치는 창이 딱 붙어 있지 않아 격자 간격으로 유도할 수 없습니다)")
        for k in keys:
            pts = all_xy(d[k])
            if not pts:
                continue
            sw, sh = spread(pts)
            print(u"      %-20s 좌표가 퍼진 폭 %dx%d  → 옛 창은 **이보다 커야** 한다"
                  % (k, sw, sh))
        print()
        print(u"   보통 **491x276** 입니다. 이렇게 돌려주세요:")
        print(u"      py fix_local_scale.py --from 491x276")
        print(u"      py fix_local_scale.py --from 491x276 --go")
        return 1

    plan = []
    print()
    print(u"   옛 창 크기 : **%dx%d** (알려주신 값) → 지금 %dx%d  배율 %.3f / %.3f"
          % (OW, OH, W, H, W / float(OW), H / float(OH)))
    print()
    print(u"   던전                 좌표  슬롯자리 폭(평균/최대)   결과")
    print("   " + "-" * 74)
    for k in keys:
        slots = d[k]
        pts = all_xy(slots)
        if not pts:
            print(u"   %-20s (좌표 없음)" % k)
            continue
        if abs(OW - W) < 3 and abs(OH - H) < 3:
            print(u"   %-20s 옛 크기가 지금과 같다 — **할 일 없음**" % k)
            continue
        box, badi, sp = slot_box(pts, OW, OH)
        if box is None:
            print(u"   %-20s 🚫 #%02d 좌표가 %dx%d 로 퍼져 있다 — 옛 창이 "
                  u"**%dx%d 보다 크다**" % (k, badi + 1, sp[0], sp[1], OW, OH))
            continue
        _wx = [b[2] for b in box.values()]
        _wy = [b[3] for b in box.values()]
        print(u"   %-20s %4d  x %.0f/%.0f · y %.0f/%.0f        환산한다"
              % (k, len(pts), sum(_wx) / len(_wx), max(_wx),
                 sum(_wy) / len(_wy), max(_wy)))
        plan.append((k, slots, pts, box, W / float(OW), H / float(OH)))

    if not plan:
        print()
        print(u"✔ **환산할 것이 없다.**")
        return 0

    # 환산 + 검증
    print()
    print(u"   🔍 환산해 보고 **전부 자기 슬롯 창 안에 들어가는지** 검사한다")
    newv, bad = {}, []
    for (k, slots, pts, box, kx, ky) in plan:
        for i, j, x, y, w in pts:
            bx, by = box[i][0], box[i][1]
            rx, ry = x - bx, y - by
            L, T = grid[i][0], grid[i][1]
            nx = int(round(L + rx * kx))
            ny = int(round(T + ry * ky))
            newv[(k, i, j)] = (nx, ny)
            if not (L - 2 <= nx <= L + W + 2 and T - 2 <= ny <= T + H + 2):
                bad.append((k, i + 1, j, x, y, nx, ny))
    print(u"      환산한 좌표 %d개 · **창 밖으로 나간 것 %d개**" % (len(newv), len(bad)))
    for b in bad[:6]:
        print(u"        🚫 %s #%02d 칸%s  (%d,%d) → (%d,%d)" % b)
    if bad:
        print()
        print(u"🚫 **환산을 하지 않는다** — 격자 역산이 틀린 것이다.")
        print(u"   그 대신 한 슬롯만 지금 창에서 찍고 그 던전 창의")
        print(u"   **[📋 전체붙임]** 을 눌러주세요 (클라 위치가 자동 보정됩니다).")
        return 1

    # 미리보기 — 첫 던전 첫 슬롯 몇 칸
    k0, slots0, _b0 = plan[0][0], plan[0][1], plan[0][3]
    print()
    print(u"   📍 미리보기 — %s #01 (창 안 좌표로 보여준다)" % k0)
    L, T = grid[0][0], grid[0][1]
    n = 0
    for j, c in enumerate(slots0[0].get("coords") or []):
        if not c or n >= 8 or (k0, 0, j) not in newv:
            continue
        nx, ny = newv[(k0, 0, j)]
        print(u"      칸%-3d 지금 (%4d,%4d) 창안(%4.0f,%4.0f)  →  (%4d,%4d) 창안(%3d,%3d)"
              % (j + 1, c[0], c[1], c[0] - _b0[0][0], c[1] - _b0[0][1],
                 nx, ny, nx - L, ny - T))
        n += 1

    if not go:
        print()
        print("=" * 96)
        print(u"  숫자가 맞으면 **--go** 를 붙여 다시 실행하세요:")
        print(u"     py fix_local_scale.py%s --go"
              % ("" if not want else " " + " ".join(want)))
        print(u"  ⚠ 먼저 **메인런처와 섬/던전 실행기를 꺼주세요**")
        print("=" * 96)
        return 0

    try:
        os.makedirs(BK, exist_ok=True)
        bkp = os.path.join(BK, time.strftime("%Y%m%d_%H%M%S")
                           + "_before_scale_island_coords.json")
        shutil.copy2(ISL, bkp)
        print()
        print(u"   📦 직전 상태를 남겼다: %s" % os.path.basename(bkp))
    except Exception as e:
        print(u"🚫 백업을 못 만들어 중단한다: %s" % e)
        return 1

    nco = nrc = 0
    for (k, slots, pts, box, kx, ky) in plan:
        for i, j, x, y, w in pts:
            nx, ny = newv[(k, i, j)]
            s = slots[i]
            if w == "coords":
                s["coords"][j][0], s["coords"][j][1] = nx, ny
                nco += 1
            else:
                rk, ck, ai = str(j).split("|")
                ev = (s.get(rk) or {}).get(ck)
                if ev and int(ai) < len(ev):
                    ev[int(ai)][2], ev[int(ai)][3] = nx, ny
                    nrc += 1

    d[MARK_W], d[MARK_H] = int(W), int(H)      # 🔁 두 번 환산 방지 표시
    tmp = ISL + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    if os.path.getsize(tmp) < 2000:
        os.remove(tmp)
        print(u"🚫 쓴 파일이 너무 작다 — 중단 (원본 그대로)")
        return 1
    os.replace(tmp, ISL)

    print()
    print(u"✅ **역산했다** — 좌표 %d개 · 녹화 마우스 %d개" % (nco, nrc))
    for p in plan:
        print(u"   %-20s %dx%d → %dx%d" % (p[0], OW, OH, W, H))
    print()
    print(u"   메인런처를 다시 켜고, 그 던전 창을 **닫았다 다시 열어** 확인하세요.")
    print(u"   틀렸으면  py fix_local_island.py --undo --go  로 되돌릴 수 있습니다")
    print(u"   (또는 %s)" % os.path.basename(bkp))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(u"🚫 오류: %s" % e)
        sys.exit(1)
