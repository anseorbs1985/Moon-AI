# -*- coding: utf-8 -*-
r"""💰 **다야 OCR 의 확대·깨우기 좌표를 지금 격자로 다시 잡는다** (2026-11-09).

사용자: *"다야 OCR 수량 파악하는 거 **좌표 제대로 맞는지 확인**도 좀 해줘 안 맞는 거 같아"*

### 다야 OCR 은 이렇게 돈다 (`lineagem_ocr.py` 의 `_ocr_region`)
```
① wake_N 클릭 — '절전모드 해제'   ② in_N 클릭 — 상단바의 확대(□) 버튼
③ common 영역 캡처 — **확대된 화면**의 고정 자리   ④ out 클릭 — 축소
```
그래서 `common`·`out` 은 **확대 화면 기준이라 격자와 무관**하고
(7월 캡처본 16장을 눈으로 확인 — 다야 숫자가 또렷하다),
**`in_N`·`wake_N` 만 화면 절대좌표**라 창 배치가 바뀌면 통째로 어긋난다.

### 🚨 2026-11-03 에 창을 491x276 → 546x307 로 키우며 격자가 바뀌었다
```
옛 격자 x   8 ·  690 · 1361 · 2011      새 격자 x  0 · 602 · 1204 · 1806
옛 격자 y  56 ·  374 ·  692 · 1010      새 격자 y 40 · 387 ·  734 · 1081
```
실측(2026-11-09) — 지금 그 좌표가 가리키는 것:
```
in_8  (439,671) → **게임 화면 한복판**      in_12 (439,985) → 게임 화면 한복판
in_7  (2443,354) → 🚨 **메인런처 버튼**     out  (2445,21) → 🚨 메인런처 창
```
그래서 11-03 뒤로는 **한 번도 제대로 못 읽었다** (`daya_counts.json` 이 10-27 자).

### ✅ 이 도구가 하는 일 — **실측한 창 안 상대좌표**를 지금 16창에 다시 더한다
```
in_N    상단바(ngptop) 안 (486, 20)   — 확대 □ 버튼. 밝은 덩어리로 실측
wake_N  게임창 안       (507, 106)   — '절전모드 해제'. fix_sleep.png 로 16/16 실측
🚫 common·out 은 건드리지 않는다 (확대 화면 기준이라 멀쩡하다)
```
번호는 **런처와 같은 열 우선**(`_grid16`)으로 매긴다 —
옛 좌표는 **줄 우선**으로 찍혀 있어 표의 번호가 뒤섞여 있었다.

사용법:
    py fix_daya_zoom.py          보여만 준다
    py fix_daya_zoom.py --go     고친다 (백업 먼저)
"""
import io, os, sys, json, time, ctypes
import ctypes.wintypes as w

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GO = "--go" in sys.argv
BASE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
REG = os.path.join(LOCAL, "daya_regions.json")
BK = os.path.join(LOCAL, "backups")

# 📏 실측한 창 안 상대좌표 (2026-11-09 · 546x307 창 / 546x40 상단바)
#    🚫 숫자를 짐작으로 바꾸지 말 것 — 아래 '왜 이 값인가' 를 먼저 읽는다.
IN_REL = (486, 20)      # 상단바의 확대 □ 버튼 — 오른쪽 끝에서 60px
#   ≡406 · _446 · □486 · ✕526  (밝은 덩어리로 잰 값) → □ 가 확대다
WAKE_REL = (507, 106)   # 게임창의 '절전모드 해제' 글자 — 16/16 전부 이 자리
BAR_W, BAR_H = 546, 40  # 잴 때의 상단바 크기
WIN_W, WIN_H = 546, 307  # 잴 때의 게임창 크기

u = ctypes.windll.user32


def wins():
    """상단바(ngptop)와 게임창을 모은다."""
    bars, games = [], []

    def cb(h, l):
        if not u.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(h, b, 256)
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, c, 256)
        r = w.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        t = (r.left, r.top, r.right - r.left, r.bottom - r.top)
        if c.value == "GLFW30":
            if b.value == "ngptop":
                bars.append(t)
            elif (b.value.startswith("리니지") and "자동 실행" not in b.value
                  and t[2] > 300 and not u.GetWindow(h, 4)):
                games.append((b.value,) + t)
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)(cb), 0)
    return bars, games


def grid16(items, xi, yi):
    """🧭 런처 `_grid16` 과 **같은 규칙** — 열로 묶고 각 열에서 위 4개.

    ⚠ 클라가 16개를 넘어도(아래에 여분을 세워둬도) 격자 16개만 고른다.
    """
    if len(items) < 16:
        return None
    cols = []
    for it in sorted(items, key=lambda t: t[xi]):
        if cols and it[xi] - cols[-1][-1][xi] <= 200:
            cols[-1].append(it)
        else:
            cols.append([it])
    cols = [c for c in cols if len(c) >= 4]
    if len(cols) < 4:
        return None
    cols.sort(key=lambda c: -len(c))
    cols = sorted(cols[:4], key=lambda c: c[0][xi])
    out = []
    for c in cols:
        out += sorted(c, key=lambda t: t[yi])[:4]
    return out if len(out) == 16 else None


def main():
    if not os.path.exists(REG):
        print("🚫 %s 가 없습니다." % REG)
        return 1
    d = json.load(io.open(REG, encoding="utf-8-sig"))
    z = dict(d.get("__zoom__") or {})

    bars, games = wins()
    print("=" * 94)
    print("💰 다야 OCR 좌표 — 상단바 %d · 게임창 %d" % (len(bars), len(games)))
    print("=" * 94)

    gl = grid16(games, 1, 2)
    bl = grid16([("", ) + b for b in bars], 1, 2)
    if not gl or not bl:
        print("🚫 리니지M 창 16개를 격자로 못 찾았습니다 — 아무것도 하지 않습니다.")
        print("   (클라를 4열 4줄로 띄운 뒤 다시 실행해 주세요)")
        return 1

    # 🧭 상단바는 게임창 **바로 위에 같은 x** 로 붙는다 → 그 짝을 찾는다
    pair = []
    for nm, gx, gy, gw, gh in gl:
        best, bd = None, 10 ** 9
        for _, bx, by, bw, bh in bl:
            dd = abs(bx - gx) + abs((by + bh) - gy)
            if dd < bd:
                best, bd = (bx, by, bw, bh), dd
        pair.append((nm, (gx, gy, gw, gh), best, bd))

    bad = [p for p in pair if p[3] > 8]
    if bad:
        print("🚫 게임창과 상단바의 짝을 못 지었습니다 (%d개) — 아무것도 하지 않습니다."
              % len(bad))
        for p in bad[:3]:
            print("   %s 게임창%s 상단바%s 어긋남 %d" % (p[0][:12], p[1], p[2], p[3]))
        return 1

    print()
    print("%-4s %-13s %-20s %-20s %s" % ("슬롯", "이름", "확대 in (지금→새)",
                                         "깨우기 wake", "바뀜"))
    new_in, new_wk = {}, {}
    for i, (nm, (gx, gy, gw, gh), (bx, by, bw, bh), _) in enumerate(pair):
        # 상단바 — 크기가 거의 안 변했다. 오른쪽 끝 기준이라 폭 비율로 맞춘다
        ix = bx + int(round(IN_REL[0] * bw / float(BAR_W)))
        iy = by + int(round(IN_REL[1] * bh / float(BAR_H)))
        # 게임창 — 크기 비율로
        wx = gx + int(round(WAKE_REL[0] * gw / float(WIN_W)))
        wy = gy + int(round(WAKE_REL[1] * gh / float(WIN_H)))
        oi = z.get("in_%d" % i)
        ow = z.get("wake_%d" % i)
        ch = []
        if list(oi or []) != [ix, iy]:
            ch.append("in")
        if list(ow or []) != [wx, wy]:
            ch.append("wake")
        new_in[i], new_wk[i] = [ix, iy], [wx, wy]
        print("  #%02d %-12s %-9s→%-10s %-9s→%-10s %s"
              % (i + 1, nm[6:][:11],
                 ("(%d,%d)" % tuple(oi)) if oi else "-", "(%d,%d)" % (ix, iy),
                 ("(%d,%d)" % tuple(ow)) if ow else "-", "(%d,%d)" % (wx, wy),
                 "·".join(ch) or "그대로"))

    print()
    print("🚫 건드리지 않는 것 — common %s · out %s"
          % (d.get("common"), z.get("out")))
    print("   (둘 다 **확대된 화면** 기준이라 창 배치와 무관하다 — 7월 캡처본 16장에")
    print("    다야 숫자가 또렷하게 담겨 있었다)")

    if not GO:
        print()
        print("👀 보여주기만 했습니다. 실제로 고치려면  py fix_daya_zoom.py --go")
        return 0

    # 📦 백업
    try:
        os.makedirs(BK, exist_ok=True)
        tag = time.strftime("%Y%m%d_%H%M%S")
        bp = os.path.join(BK, "%s_before_dayazoom_daya_regions.json" % tag)
        io.open(bp, "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=2))
        print()
        print("📦 백업 %s" % bp)
    except Exception as e:
        print("🚫 백업 실패 — 아무것도 하지 않습니다: %s" % e)
        return 1

    for i in range(16):
        z["in_%d" % i] = new_in[i]
        z["wake_%d" % i] = new_wk[i]
    d["__zoom__"] = z
    tmp = REG + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=2))
    os.replace(tmp, REG)
    print("✔ 고쳤습니다 — in 16개 · wake 16개 (common·out 은 그대로)")
    print("   번호는 런처와 같은 **열 우선**입니다 (#01 = 왼쪽 위, #02 = 그 아래)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
