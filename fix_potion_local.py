# -*- coding: utf-8 -*-
"""💊 **로컬의 물약 칸을 그 컴퓨터 창 크기에 맞게 고친다** (2026-11-09).

사용자: *"로컬에 지금 잊혀진섬에 대한 **물약사는 좌표가 바보가 된 상황**이야
다른곳을 완전 클릭해. 여기(메인)는 정상인데 어떻게 처리하면 좋을까"*

### 🚨 왜 로컬만 틀어지나
프리셋은 **창 안 상대좌표(`rel`)** 를 쓰는데, `_apply_preset` 은
```python
cs[j] = [rel[0] + 창왼쪽, rel[1] + 창위]      # 창 **크기** 보정이 없다
```
메인 프리셋은 **546x307 기준**이다. 로컬 클라 창이 그보다 작으면(491x276 등)
**프리셋을 눌러도 계속 빗나간다.** 좌표는 머신별이라 배포도 못 한다.

### ✅ 이 도구가 하는 일
메인에서 실측한 물약 좌표(아래 `POTION_REL`, 546x307 기준)를
**그 컴퓨터 창 크기로 비율 환산**해 넣는다. **사람이 좌표를 다시 찍지 않아도 된다.**
```
py fix_potion_local.py                  보여만 준다 (지금 값 vs 고칠 값)
py fix_potion_local.py --go             고친다
py fix_potion_local.py --key 월요일_잊혀진섬 --go    그 던전만
```
- 🚫 **메인에서는 거부한다** (메인이 이 값의 원본이다)
- 🚫 슬롯 **이름에 물약이 안 적힌 슬롯은 건드리지 않는다**
- 📦 고치기 전에 `backups\<시각>_before_potion_island_coords.json` 로 백업
- 🧪 프리셋에도 **그 컴퓨터 기준 값**과 `bw`/`bh`(기준 창 크기)를 적어둔다
  → 다음에 프리셋을 눌러도 맞는다

⚠ **런처·섬 실행기를 끄고 돌릴 것** (켜져 있으면 저장이 덮어써진다).
"""
import io, os, sys, json, time, shutil, ctypes
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "island_coords.json")
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
BK = os.path.join(LOCAL, "backups")

# 📏 메인에서 실측한 값 — **창 546x307 기준 창 안 상대좌표**
#    칸1 = 물약 종류(상품 리스트) · 칸2 = Max 49.9% / 82.9% (얼마어치 살까)
#    🚫 이 값을 손으로 고치지 말 것 — 메인 프리셋에서 그대로 뽑았다.
BASE_W, BASE_H = 546, 307
CELL = {                      # 던전별 물약 칸 (0부터)
    "수금_오만의탑":   (11, 12),
    "토요일_악몽의섬": (16, 17),
    "월요일_잊혀진섬": (13, 14),
    "화요일_에카":     (11, 12),
}
POTION_REL = {
    "수금_오만의탑": {
        "빨갱이 48%": [[95, 97], [311, 276]], "빨갱이 82%": [[98, 96], [355, 279]],
        "주홍이 48%": [[90, 131], [310, 279]], "주홍이 82%": [[92, 130], [354, 276]]},
    "토요일_악몽의섬": {
        "빨갱이 48%": [[91, 91], [309, 275]], "빨갱이 82%": [[83, 93], [349, 275]],
        "주홍이 48%": [[89, 129], [311, 275]], "주홍이 82%": [[86, 129], [349, 273]]},
    "월요일_잊혀진섬": {
        "빨갱이 48%": [[90, 133], [314, 277]], "빨갱이 82%": [[86, 133], [351, 278]],
        "주홍이 48%": [[87, 168], [311, 277]], "주홍이 82%": [[90, 166], [351, 277]]},
    "화요일_에카": {
        "빨갱이 82%": [[83, 93], [354, 275]],
        "주홍이 48%": [[87, 131], [309, 274]], "주홍이 82%": [[76, 129], [348, 274]]},
}


def is_main():
    try:
        with io.open(os.path.join(BASE, "local_config.json"), encoding="utf-8-sig") as f:
            return bool((json.load(f) or {}).get("is_main"))
    except Exception:
        return False


def grid16():
    """리니지M 게임 창을 격자(열 우선) 순서로 16개 — 격자 밖은 버린다.

    ⚠ `_client_rects_by_slot` 과 같은 규칙 (2026-10-13): 여분을 격자 **아래**에
      세워두므로, 열마다 y 가 작은 것부터 4개만 쓴다."""
    u = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h) and not u.IsIconic(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            ti = b.value
            c = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, c, 256)
            if (ti.startswith("리니지M") and "자동 실행" not in ti
                    and c.value == "GLFW30" and u.GetWindow(h, 4) == 0):
                r = wintypes.RECT()
                u.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left > 300:
                    out.append([r.left, r.top, r.right, r.bottom, ti])
        return True

    u.EnumWindows(cb, 0)
    cols = {}
    for w in out:
        for cx in list(cols):
            if abs(cx - w[0]) <= 200:
                cols[cx].append(w)
                break
        else:
            cols[w[0]] = [w]
    best = sorted(cols.values(), key=lambda v: -len(v))[:4]
    best.sort(key=lambda v: v[0][0])
    res = []
    for col in best:
        col.sort(key=lambda w: w[1])
        res.extend(col[:4])
    return res if len(res) == 16 else out[:16] if len(out) >= 16 else []


def potion_of(name):
    """슬롯 이름에서 물약 종류·퍼센트를 읽는다 → '주홍이 48%' 같은 키."""
    s = str(name or "")
    kind = "주홍이" if "주홍이" in s else ("빨갱이" if "빨갱이" in s else None)
    pct = "82%" if "82" in s else ("48%" if "48" in s else None)
    return "%s %s" % (kind, pct) if kind and pct else None


def main():
    if is_main():
        print("🚫 **여기는 메인 컴퓨터다.** 메인 좌표가 이 값의 원본이므로 돌리지 않는다.")
        print("   (로컬 컴퓨터에서 돌려주세요)")
        return 2
    go = "--go" in sys.argv
    keys = [a for a in sys.argv[1:] if a in CELL]
    if "--key" in sys.argv:
        i = sys.argv.index("--key")
        if i + 1 < len(sys.argv) and sys.argv[i + 1] in CELL:
            keys = [sys.argv[i + 1]]
    if not keys:
        keys = list(CELL)

    try:
        cfg = json.load(io.open(CFG, encoding="utf-8-sig"))
    except Exception as e:
        print("🚫 island_coords.json 을 못 읽었다: %s" % e)
        return 1

    W = grid16()
    if len(W) < 16:
        print("🚫 리니지M 창 16개를 못 찾았다 (지금 %d개) — 클라를 다 띄우고 다시 돌려주세요"
              % len(W))
        return 1
    ww, hh = W[0][2] - W[0][0], W[0][3] - W[0][1]
    kx, ky = ww / float(BASE_W), hh / float(BASE_H)
    print("=" * 96)
    print("💊 물약 칸 고치기 — 이 컴퓨터 클라 창 **%dx%d** (메인 %dx%d 기준 → %.3f배 / %.3f배)"
          % (ww, hh, BASE_W, BASE_H, kx, ky))
    if abs(kx - 1) < 0.002 and abs(ky - 1) < 0.002:
        print("   창 크기가 메인과 같다 — 값을 그대로 넣는다 (좌표가 깨졌으면 복구된다)")
    print("=" * 96)

    chg = 0
    for key in keys:
        if key not in cfg:
            continue
        a, b = CELL[key]
        tbl = POTION_REL.get(key) or {}
        print()
        print("■ %s  칸%d·칸%d" % (key, a + 1, b + 1))
        for si, slot in enumerate(cfg[key][:16]):
            if not isinstance(slot, dict):
                continue
            nm = slot.get("name") or ""
            pk = potion_of(nm)
            if not pk or pk not in tbl:
                print("   #%02d %-22s — 이름에 물약이 없다 → 건드리지 않는다" % (si + 1, nm[:22]))
                continue
            L, T = W[si][0], W[si][1]
            r1, r2 = tbl[pk]
            new1 = [int(round(r1[0] * kx)) + L, int(round(r1[1] * ky)) + T]
            new2 = [int(round(r2[0] * kx)) + L, int(round(r2[1] * ky)) + T]
            cs = slot.setdefault("coords", [])
            while len(cs) <= max(a, b):
                cs.append(None)
            old1, old2 = cs[a], cs[b]
            d1 = "그대로" if old1 == new1 else "%s → %s" % (old1, new1)
            d2 = "그대로" if old2 == new2 else "%s → %s" % (old2, new2)
            print("   #%02d %-22s [%s]  칸%d %s · 칸%d %s"
                  % (si + 1, nm[:22], pk, a + 1, d1, b + 1, d2))
            if old1 != new1 or old2 != new2:
                chg += 1
            cs[a], cs[b] = new1, new2

        # 🧪 프리셋도 그 컴퓨터 기준으로 (다음에 눌러도 맞게)
        for p in (cfg.get("_presets") or {}).get(key) or []:
            pk = potion_of(p.get("name"))
            if not pk or pk not in tbl:
                continue
            it = p.setdefault("items", {})
            r1, r2 = tbl[pk]
            for cell, rel in ((a, r1), (b, r2)):
                e = it.setdefault(str(cell), {})
                e["act"] = "mov"
                e["rel"] = [int(round(rel[0] * kx)), int(round(rel[1] * ky))]
            p["bw"], p["bh"] = ww, hh      # 기준 창 크기 — 창을 바꿔도 따라가게
            p["abs"] = False

    if not go:
        print()
        print("=" * 96)
        print("  바꿀 슬롯 %d개 — 실제로 고치려면 **--go** 를 붙여 다시 돌려주세요" % chg)
        print("  py fix_potion_local.py --go")
        print("=" * 96)
        return 0

    os.makedirs(BK, exist_ok=True)
    bkp = os.path.join(BK, time.strftime("%Y%m%d_%H%M%S") + "_before_potion_island_coords.json")
    try:
        shutil.copy2(CFG, bkp)
    except Exception as e:
        print("🚫 백업을 못 떠서 멈춘다: %s" % e)
        return 1
    tmp = CFG + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CFG)
    print()
    print("=" * 96)
    print("  ✔ 슬롯 %d개를 고쳤다 · 프리셋도 이 컴퓨터 기준으로 맞췄다" % chg)
    print("  📦 백업 %s" % bkp)
    print("  → 런처를 다시 켜고 그 던전을 한 번 돌려 확인해주세요")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    sys.exit(main())
