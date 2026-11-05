# -*- coding: utf-8 -*-
u"""🏢 11-04 배포로 **갈아끼워진 오만의탑 '층'(칸23)** 을 자기 백업으로 되살린다.

사고 (2026-11-05 확인):
    11-04 17:15 `68a6522` 가 `share_island.json` 에 `keys=[수금_오만의탑, …]`
    `presets=true` 로 배포했다. 그때 `keep_cells` 에 **물약 칸(12·13)만** 적어두고
    **층 칸(23)을 빼먹어서**, 로컬 16슬롯의 칸23 좌표와 프리셋이
    **메인 것(15개가 5층)으로 통째로 갈렸다.**
    → 로컬에서 6·7·8층 프리셋을 골라도 칸23 이 5층 줄을 가리켜 **5층이 눌렸다.**

쓰는 법 (로컬에서):
    py fix_local_floor.py          ← 무엇이 갈렸는지 **보여만** 준다
    py fix_local_floor.py --go     ← 되살리고 런처·섬실행기 재시작 안내

🚫 메인에서는 거부한다 (메인 좌표가 배포의 원본이라 '지금 값 = 배포 값' 이 당연히 참).
"""
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KEY = u"수금_오만의탑"
FLOOR_IDX = 22                      # 칸23 (0부터) — 층을 고르는 자리
FLOOR_Y3 = 229.0                    # 3층 줄 (창 546x307 기준 창 안 y)
FLOOR_DY = 22.54                    # 한 층 간격
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI")
BK = os.path.join(LOCAL, "backups")


def jload(p):
    try:
        with io.open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def is_main():
    for p in (os.path.join(HERE, "local_config.json"),
              os.path.join(os.path.expanduser("~"), "Desktop",
                           "local_config.json")):
        d = jload(p)
        if isinstance(d, dict) and d.get("is_main"):
            return True
    return False


def island_path():
    """로컬 런처가 실제로 쓰는 island_coords.json."""
    for p in (os.path.join(os.path.expanduser("~"), "Desktop",
                           "island_coords.json"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop",
                           "island_coords.json"),
              os.path.join(HERE, "island_coords.json")):
        if os.path.exists(p) and os.path.getsize(p) > 2000:
            return p
    return None


def floor_of(c, row, tops):
    u"""절대좌표 칸23 → 몇 층인가 (모르면 None)."""
    if not c or len(c) < 2:
        return None
    try:
        return int(round(3 + (FLOOR_Y3 - (c[1] - tops[row])) / FLOOR_DY))
    except Exception:
        return None


def win_tops(slots):
    u"""슬롯 좌표들로 '4줄의 창 top' 을 되짚는다 — 줄마다 가장 작은 y.

    칸23 은 창 안 y 116~229 자리라, 같은 줄 슬롯 4개의 y 는 비슷하다.
    창 top 을 모르면 층을 못 구하므로, **그 줄 y 들의 최솟값 − 116** 쯤으로 잡는다.
    정확한 창 자리는 알 수 없으니 '같은 줄끼리 상대 비교' 만 쓴다.
    """
    rows = {}
    for i, s in enumerate(slots):
        cs = (s or {}).get("coords") or []
        c = cs[FLOOR_IDX] if len(cs) > FLOOR_IDX else None
        if c and len(c) > 1:
            rows.setdefault(i % 4, []).append(c[1])
    tops = []
    for r in range(4):
        ys = rows.get(r) or []
        tops.append((min(ys) - 116) if ys else 0)
    return tops


def main():
    go = "--go" in sys.argv

    if is_main():
        print(u"🚫 여기는 **메인 컴퓨터**입니다 — 이 도구는 로컬에서만 씁니다.")
        print(u"   메인 좌표가 배포의 원본이라 '지금 값 = 배포된 값' 이 당연히 참이고,")
        print(u"   그대로 되살리면 메인 층 설정을 옛 백업으로 망칩니다.")
        return 2

    dst_p = island_path()
    if not dst_p:
        print(u"⚠ island_coords.json 을 찾지 못했습니다.")
        return 1
    dst = jload(dst_p)
    if not isinstance(dst, dict):
        print(u"⚠ island_coords.json 을 읽지 못했습니다: " + dst_p)
        return 1

    sent = jload(os.path.join(HERE, "share_island_data.json")) or {}
    sent_sl = sent.get(KEY) or []
    cur_sl = dst.get(KEY) or []
    if not cur_sl:
        print(u"⚠ 이 컴퓨터에 '%s' 설정이 없습니다." % KEY)
        return 1

    tops = win_tops(cur_sl)
    print(u"=== 지금 이 컴퓨터의 오만의탑 '층'(칸23) ===")
    same = []
    for i in range(min(16, len(cur_sl))):
        cs = (cur_sl[i] or {}).get("coords") or []
        c = cs[FLOOR_IDX] if len(cs) > FLOOR_IDX else None
        sc = None
        if i < len(sent_sl):
            scs = (sent_sl[i] or {}).get("coords") or []
            sc = scs[FLOOR_IDX] if len(scs) > FLOOR_IDX else None
        n = floor_of(c, i % 4, tops)
        mark = u""
        if c and sc and list(c) == list(sc):
            same.append(i)
            mark = u"   ← 배포된 값과 **같다** (갈아끼워진 것)"
        print(u"  #%02d  %s  %s%s"
              % (i + 1, (u"%d층" % n) if n else u"  ? ",
                 (u"%s" % (c,)) if c else u"없음", mark))

    if not same:
        print()
        print(u"✔ 배포된 값과 같은 슬롯이 없습니다 — 이미 로컬 것으로 돌아와 있습니다.")
        print(u"   (그래도 층이 틀리게 눌리면 아래 '🏢 드롭다운' 쪽을 보세요)")
        return 0

    # ── 백업에서 '배포 값과 다른' 칸23 을 찾는다 ──────────────────
    cands = []
    if os.path.isdir(BK):
        for nm in sorted(os.listdir(BK), reverse=True):   # 최신부터
            if "island_coords" in nm and nm.endswith(".json"):
                cands.append(os.path.join(BK, nm))
    print()
    print(u"=== 백업에서 되살릴 값을 찾습니다 (최신부터 %d개) ===" % len(cands))

    found = {}          # 슬롯번호 -> (좌표, 백업파일)
    pres = None         # (프리셋목록, 백업파일)
    for p in cands:
        b = jload(p)
        if not isinstance(b, dict):
            continue
        bsl = b.get(KEY) or []
        hit = []
        for i in same:
            if i in found or i >= len(bsl):
                continue
            bcs = (bsl[i] or {}).get("coords") or []
            bc = bcs[FLOOR_IDX] if len(bcs) > FLOOR_IDX else None
            sc = None
            if i < len(sent_sl):
                scs = (sent_sl[i] or {}).get("coords") or []
                sc = scs[FLOOR_IDX] if len(scs) > FLOOR_IDX else None
            if bc and (not sc or list(bc) != list(sc)):
                found[i] = (bc, os.path.basename(p))
                hit.append(i + 1)
        if pres is None:
            bp = ((b.get("_presets") or {}).get(KEY)) or []
            sp = ((sent.get("_presets") or {}).get(KEY)) or []
            if bp and json.dumps(bp, sort_keys=True) != json.dumps(sp, sort_keys=True):
                pres = (bp, os.path.basename(p))
        if hit:
            print(u"  %-44s 슬롯 %s" % (os.path.basename(p), hit))
        if len(found) >= len(same) and pres is not None:
            break

    print()
    if not found and pres is None:
        print(u"⚠ 백업에서 **로컬 값을 찾지 못했습니다.**")
        print(u"   → 아래 '🏢 드롭다운' 으로 슬롯마다 층을 고르는 것이 가장 빠릅니다.")
        return 1

    print(u"=== 되살릴 내용 ===")
    for i in sorted(found):
        c, src = found[i]
        n = floor_of(c, i % 4, tops)
        cs = (cur_sl[i] or {}).get("coords") or []
        now = cs[FLOOR_IDX] if len(cs) > FLOOR_IDX else None
        n0 = floor_of(now, i % 4, tops)
        print(u"  #%02d  %s → **%s**   (%s)"
              % (i + 1, (u"%d층" % n0) if n0 else u"?",
                 (u"%d층" % n) if n else u"?", src))
    if pres:
        print(u"  프리셋 15개 → %s 의 것으로" % pres[1])

    if not go:
        print()
        print(u"※ 아직 아무것도 안 바꿨습니다. 되살리려면:")
        print(u"      py fix_local_floor.py --go")
        return 0

    # ── 되살리기 ──────────────────────────────────────────────────
    import time
    st = time.strftime("%Y%m%d_%H%M%S")
    try:
        os.makedirs(BK, exist_ok=True)
        with io.open(os.path.join(BK, st + "_before_floorfix_island_coords.json"),
                     "w", encoding="utf-8") as f:
            json.dump(dst, f, ensure_ascii=False, indent=2)
        print()
        print(u"📦 되살리기 직전 백업: backups\\%s_before_floorfix_island_coords.json" % st)
    except Exception as e:
        print(u"⚠ 백업 실패: %s — 그래도 계속합니다" % e)

    n_fix = 0
    for i in sorted(found):
        cs = (dst[KEY][i] or {}).setdefault("coords", [])
        while len(cs) <= FLOOR_IDX:
            cs.append(None)
        cs[FLOOR_IDX] = list(found[i][0])
        n_fix += 1
    if pres:
        dst.setdefault("_presets", {})[KEY] = pres[0]

    tmp = dst_p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(dst, f, ensure_ascii=False, indent=2)
    os.replace(tmp, dst_p)
    print(u"✔ 칸23 %d개%s 되살렸습니다 — %s"
          % (n_fix, u" + 프리셋" if pres else u"", dst_p))
    print()
    print(u"⚠ **섬/던전 실행기 창이 열려 있으면 닫았다 다시 열어주세요** "
          u"(별도 프로세스라 옛 값을 들고 있습니다).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
