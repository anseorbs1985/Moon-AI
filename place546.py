# -*- coding: utf-8 -*-
u"""📍 **지금 창 크기에서 장소 이름 그림을 다시 받는다** (2026-11-05).

왜 필요한가 — 2026-11-03 에 클라 창을 **491x276 → 546x307** 로 키웠는데,
장소 이름 그림은 **옛 창(494) 시절 것**이라 안 맞는다.
`place_crop` 이 이름칸을 **항상 75x12 로 맞추는데**, 546 창은 칸이 83x13 이라
**축소 보간**이 들어가 글자 모양이 달라진다.

    실측 2026-11-05 (16클라 전부 오만의탑 5층):
      494 그림만          0.534~0.540   16슬롯 전부 막힘 (1등이 악몽의섬 0.58)
      546 에서 6장 더함    0.979~1.000   16슬롯 전부 통과 (배수 1.67~1.73)

🚫 **배율 보정으로는 못 고친다** (실측): 축소된 컷에 대면 최고 0.73,
   축소 없는 원본 컷에 1.11배로 대도 최고 0.81 — 기준 0.85 에 못 미친다.
   **그 던전에 들어가 있을 때 다시 받는 수밖에 없다.**

쓰는 법 — **그 던전에 캐릭이 들어가 있을 때**:
    py place546.py                   지금 점수를 잰다 (안 바꾼다)
    py place546.py 악몽의섬           〃 (던전을 콕 집어)
    py place546.py 악몽의섬 --go      그 던전 그림을 지금 창에서 받는다
    py place546.py 마을 --go          🏘 마을 이름도 같은 방법

⚠ 받은 뒤 **반대쪽도 같이 본다** — 다른 던전 점수가 올라가면 안 된다.
   이 도구가 받기 전/후 표를 둘 다 보여주므로 눈으로 확인할 것.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.dirname(HERE) if os.path.basename(HERE).lower() == "moon-ai" else HERE
sys.path.insert(0, DESK)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import numpy as np
import cv2

SRC = os.path.join(DESK, "lineagem_island.py")
ICJ = os.path.join(DESK, "island_coords.json")
KEYS = [u"수금_오만의탑", u"토요일_악몽의섬", u"월요일_잊혀진섬", u"화요일_에카"]
TOWN = u"_마을"
ALIAS = {u"오만": KEYS[0], u"오만의탑": KEYS[0], u"악몽": KEYS[1], u"악몽의섬": KEYS[1],
         u"잊섬": KEYS[2], u"잊혀진섬": KEYS[2], u"에카": KEYS[3],
         u"마을": TOWN, u"_마을": TOWN}
MATCH, RATIO = 0.85, 1.12            # 물약 재실행 전용 기준 (P0_PLACE_*)
TAKE = 6                             # 한 번에 받을 장수


def load_engine():
    u"""런처가 켜져 있어도 되게, 소스에서 필요한 것만 떼어 온다."""
    s = io.open(SRC, encoding="utf-8").read()
    g = {"np": np, "cv2": cv2, "os": os, "json": json, "io": io,
         "re": re, "sys": sys, "BASE": DESK}
    for ln in s.split("\n"):
        if re.match(r"^[A-Z_][A-Z0-9_]*(\s*,\s*[A-Z_][A-Z0-9_]*)*\s*=\s*\S", ln):
            try:
                exec(compile(ln, "<h>", "exec"), g)
            except Exception:
                pass
    for nm in sorted(set(re.findall(r"^def (place_\w+|grab_window)\(", s, re.M))):
        i = s.find("\ndef %s(" % nm)
        if i >= 0:
            try:
                exec(compile(s[i:s.find("\ndef ", i + 5)], "<b>", "exec"), g)
            except Exception:
                pass
    return g


def main():
    args = [a for a in sys.argv[1:] if a != "--go"]
    go = "--go" in sys.argv
    want = None
    if args:
        want = ALIAS.get(args[0].strip())
        if not want:
            print(u"⚠ 모르는 던전: %s" % args[0])
            print(u"   쓸 수 있는 이름: " + u" · ".join(sorted(set(ALIAS))))
            return 1

    g = load_engine()
    if "place_list" not in g or "grab_window" not in g:
        print(u"⚠ lineagem_island.py 에서 함수를 못 떼어냈습니다.")
        return 1

    ic = json.load(io.open(ICJ, encoding="utf-8-sig"))
    # 기준 좌표는 **어느 던전 것이든** 같은 클라를 가리킨다 — 있는 것을 쓴다
    anchors = []
    for k in KEYS:
        sl = ic.get(k) or []
        got = []
        for i in range(16):
            cs = ((sl[i] if i < len(sl) else None) or {}).get("coords") or []
            got.append(next((c for c in cs if c), None))
        if sum(1 for c in got if c) >= 12:
            anchors = got
            break
    if not anchors:
        print(u"⚠ 좌표가 등록된 던전이 없어 어느 클라인지 모릅니다.")
        return 1

    def cut_of(i, raw=False):
        a = anchors[i]
        if not a:
            return None
        got = g["grab_window"](a)
        if not got:
            return None
        c = g["place_crop"](got[0])
        t = g["place_trim"](c, False)
        c = t if t is not None else c
        return c if raw else g["place_nogreen"](c)

    def score(cut, key):
        best = -1.0
        for p in g["place_list"](key):
            t = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
            if t is None or cut.shape[0] < t.shape[0] or cut.shape[1] < t.shape[1]:
                continue
            best = max(best, float(cv2.matchTemplate(
                cut, t, cv2.TM_CCOEFF_NORMED).max()))
        return best

    ALL = KEYS + [TOWN]

    def table(tag):
        print(u"\n=== %s ===" % tag)
        print(u"슬롯 |  오만   악몽   잊섬   에카   마을 | 1등 | 배수 | 판정(%.2f/%.2f)"
              % (MATCH, RATIO))
        rows, bad = [], []
        for i in range(16):
            cut = cut_of(i)
            if cut is None:
                print(u"  #%02d 창 못 찍음" % (i + 1))
                rows.append(None)
                continue
            v = [score(cut, k) for k in ALL]
            srt = sorted(v, reverse=True)
            r = (srt[0] / srt[1]) if srt[1] > 0 else 9.9
            top = ALL[v.index(srt[0])]
            ok = srt[0] >= MATCH and r >= RATIO
            if not ok:
                bad.append(i + 1)
            rows.append((v, top, r, ok))
            print(u"  #%02d | %.3f %.3f %.3f %.3f %.3f | %-8s | %.2f | %s"
                  % (i + 1, v[0], v[1], v[2], v[3], v[4],
                     top.replace(u"요일_", u"").replace(u"수금_", u""),
                     r, u"✔" if ok else u"✘ 막힘"))
        print(u"  → 막히는 슬롯: %s" % (bad if bad else u"없음"))
        return rows, bad

    rows, bad0 = table(u"지금")

    # 어느 던전을 받을지 — 인자가 없으면 '1등이 가장 많은 던전'
    if not want:
        tally = {}
        for r in rows:
            if r:
                tally[r[1]] = tally.get(r[1], 0) + 1
        want = max(tally, key=tally.get) if tally else KEYS[0]
        print(u"\n※ 던전을 안 적어서 **1등이 가장 많은 것**으로 봅니다: %s" % want)
        print(u"   틀렸으면:  py place546.py <던전이름> --go")

    now = len(g["place_list"](want))
    print(u"\n%s — 지금 그림 %d장" % (want, now))
    if not go:
        print(u"\n※ 아직 안 바꿨습니다. 지금 창에서 받으려면:")
        print(u"      py place546.py %s --go"
              % want.replace(u"요일_", u"").replace(u"수금_", u""))
        return 0

    # ── 받는다 — 막히는 슬롯 먼저, 그 다음 골고루 ───────────────────
    pick = list(dict.fromkeys((bad0 or []) + [1, 6, 11, 16]))[:TAKE]
    print(u"\n=== 지금 창에서 받을 슬롯: %s ===" % pick)
    added = []
    for sn in pick:
        cut = cut_of(sn - 1, raw=True)
        if cut is None:
            print(u"  #%02d 창 못 찍음 — 건너뜀" % sn)
            continue
        if float(cut.std()) < 3.0:
            print(u"  #%02d 글자가 없다 (무늬 %.1f) — 건너뜀" % (sn, cut.std()))
            continue
        n = len(g["place_list"](want))
        if n >= g["PLACE_MAX"]:
            print(u"  그림이 %d장 다 찼다 — 멈춥니다" % g["PLACE_MAX"])
            break
        p = g["place_img_path"](want, n)
        os.makedirs(g["IMG_DIR"], exist_ok=True)
        cv2.imencode(".png", cut)[1].tofile(p)
        added.append(os.path.basename(p))
        print(u"  #%02d → %s  (%dx%d · 무늬 %.1f)"
              % (sn, os.path.basename(p), cut.shape[1], cut.shape[0], cut.std()))

    if not added:
        print(u"\n⚠ 한 장도 못 받았습니다.")
        return 1
    print(u"\n받은 것 %d장" % len(added))
    _rows, bad1 = table(u"받은 뒤")
    print(u"\n막히는 슬롯: %s → %s" % (bad0 if bad0 else u"없음", bad1 if bad1 else u"없음"))
    print(u"\n⚠ **반대쪽 확인** — 위 표에서 다른 던전 열이 전보다 올라갔으면")
    print(u"   그 던전 판정이 흔들린다. 올랐으면 방금 받은 그림을 지우고 다시 자를 것:")
    print(u"      " + u" · ".join(added))
    print(u"\n📦 저장소에도 넣어 로컬이 받게 하려면 (메인에서):")
    print(u"      cd Moon-AI && cp ../click_templates/place_*.png click_templates/")
    print(u"      git add click_templates/place_*.png && git commit && git push")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
