# -*- coding: utf-8 -*-
r"""🪟 **누가 클라를 축소하나** — 하나를 키워두고 0.2초마다 지켜본다.

🚫 게임에 클릭·키를 보내지 않는다. **창 크기만** 건드리고 끝나면 **원래대로** 돌린다.
"""
import ctypes, time, sys, io, os
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
u = ctypes.windll.user32
LOGP = os.path.join(os.environ["LOCALAPPDATA"], "MoonAI", "click_log.txt")

WANT = sys.argv[1] if len(sys.argv) > 1 else "아웃로"
SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
BIGW, BIGH = 2504, 1352


def wins():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if not u.IsWindowVisible(h):
            return True
        n = u.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1)
        t = b.value
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, c, 256)
        if (c.value == "GLFW30" and t.startswith("리니지M")
                and "자동 실행" not in t and "ngptop" not in t
                and u.GetWindow(h, 4) == 0):
            out.append((h, t))
        return True
    u.EnumWindows(cb, 0)
    return out


def rect(h):
    r = wintypes.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def logsize():
    try:
        return os.path.getsize(LOGP)
    except Exception:
        return 0


tgt = None
for h, t in wins():
    if WANT in t:
        tgt = (h, t)
        break
if not tgt:
    print("🚨 '%s' 창을 못 찾았다" % WANT)
    sys.exit(1)
H, T = tgt
x0, y0, w0, h0 = rect(H)
L0 = logsize()
print("=" * 92)
print("🪟 %s  원래 (%d,%d) %dx%d  → %dx%d 로 키우고 %.0f초 지켜본다"
      % (T, x0, y0, w0, h0, BIGW, BIGH, SEC))
print("   🚫 게임 클릭·키 없음 · 끝나면 원래대로")
print("=" * 92)

SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
try:
    u.SetWindowPos(H, 0, 0, 0, BIGW, BIGH, SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.3)
    cur = rect(H)
    print("   키운 직후  %dx%d" % (cur[2], cur[3]))
    last = cur
    t0 = time.time()
    changed = []
    while time.time() - t0 < SEC:
        time.sleep(0.2)
        r = rect(H)
        if r != last:
            el = time.time() - t0
            shrink = (r[2] < last[2] - 4 or r[3] < last[3] - 4)
            print("   %5.1f초  %dx%d (%d,%d)  %s"
                  % (el, r[2], r[3], r[0], r[1],
                     "🚨 **줄었다**" if shrink else "바뀜"))
            changed.append((el, last, r, shrink))
            last = r
    print()
    if not changed:
        print("   → ✔ **12초 동안 아무도 안 건드렸다** (런처는 범인이 아니다)")
    else:
        sh = [c for c in changed if c[3]]
        print("   → 🚨 **%d번 바뀌었다 (줄어든 것 %d번)**" % (len(changed), len(sh)))
finally:
    u.SetWindowPos(H, 0, x0, y0, w0, h0, SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.2)
    r = rect(H)
    print()
    print("   🔙 원래대로 (%d,%d) %dx%d  %s"
          % (r[0], r[1], r[2], r[3],
             "✔" if (r[2], r[3]) == (w0, h0) else "⚠ 다르다"))

L1 = logsize()
if L1 > L0:
    print()
    print("── 그 사이 런처가 남긴 기록 ──")
    with io.open(LOGP, "r", encoding="utf-8", errors="replace") as f:
        f.seek(L0)
        for ln in f.read().splitlines():
            print("   " + ln[:110])
else:
    print()
    print("── 그 사이 런처 기록: **없음** ──")
