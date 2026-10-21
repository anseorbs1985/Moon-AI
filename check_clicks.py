# -*- coding: utf-8 -*-
"""🔎 **누가 좌표를 눌렀나** — 로컬에서 한 줄로 본다 (2026-10-21 사용자 요청)

사용자: *"지금 상당히 너 마음대로 클릭을 하는데, 내가 변신쪽이나 합성쪽이나
제작쪽에 뭔가를 작업하려면 너 맘대로 좌표를 찍어버리는데… **확인하고 제대로
수정해주라.**"* → 로컬에서 일어난 일이라 **기록으로 짚어야** 한다.

    py check_clicks.py          최근 2시간
    py check_clicks.py 6        최근 6시간

아무것도 클릭하지 않는다. 읽기만 한다.
"""
import io
import os
import re
import sys
import time
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI", "click_log.txt")
BASE = os.path.dirname(os.path.abspath(__file__))

# 자동으로 좌표를 누를 수 있는 것들 — 켬/끔과 기본값
AUTO = [
    ("💧 물약감시 → 섬 실행기 재실행", "potion0.json", "on", True,
     "물약 0개 + 그 던전 안이면 그 슬롯을 다시 돌린다 (좌표 22~35개)"),
    ("🏘 마을감시 → 재실행", "potion0.json", "on", True,
     "물약 없이 마을에 4~5분 서 있으면 다시 돌린다"),
    ("😴 5분 쉬면 자동복구", "coords.json", "fix_idle_on", True,
     "사람이 5분 안 만지면 복구 좌표를 누른다"),
    ("🃏 변신확정 자동", "coords.json", "cardfix_auto", False,
     "카드교체 화면을 보면 좌표 5개를 누른다 (기본 꺼짐)"),
    ("📬 우편 자동받기", "coords.json", "mail_auto", False,
     "코드에서 끔 (MAIL_AUTO_ON=False)"),
    ("🗂 도감 보상받기", None, None, None, "버튼을 눌러야 돈다"),
    ("⏰ 섬/던전 반복", "island_repeat.json", None, None,
     "사용자가 실행했을 때만 걸린다 — 걸려 있으면 그 시각에 자동으로 돈다"),
]

# 기록 줄 → 누가 눌렀나
WHO = [
    (re.compile(r"^(\S+) .*좌표\d+ \([\d, ]+\) 클릭"), "런처 {0}"),
    (re.compile(r"\[클릭\].*실행"), "섬/던전 실행기"),
    (re.compile(r"\[변신확정\].*좌표 \d+개"), "🃏 변신확정"),
    (re.compile(r"\[아이템등록\].*키 .*누름"), "🏷 아이템등록"),
    (re.compile(r"\[도감\].*눌렀"), "🗂 도감"),
    (re.compile(r"\[우편\].*받"), "📬 우편"),
    (re.compile(r"\[물약감시\].*다시 실행"), "💧 물약감시 → 섬 실행기"),
    (re.compile(r"\[마을감시\].*다시 실행"), "🏘 마을감시 → 섬 실행기"),
    (re.compile(r"\[유휴복구\]|\[fix\].*좌표"), "😴 유휴 자동복구"),
    (re.compile(r"\[반복\].*돌기 시작"), "⏰ 반복"),
    (re.compile(r"\[절전해제\]"), "🔆 F11 절전해제"),
    (re.compile(r"\[경고확인\].*깨어남"), "🩹 십자가 스캔(깨우기)"),
]


def _jget(fname, key, default=None):
    """설정 파일에서 키 하나 — 없으면 default."""
    for d in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI"), BASE):
        p = os.path.join(d, fname)
        if os.path.exists(p):
            try:
                import json
                v = json.load(io.open(p, encoding="utf-8-sig")) or {}
                if key is None:
                    return v
                return v.get(key, default)
            except Exception:
                pass
    return default


def main():
    hours = 2.0
    if len(sys.argv) > 1:
        try:
            hours = float(sys.argv[1])
        except Exception:
            pass
    print("=" * 72)
    print(f" 🔎 누가 좌표를 눌렀나 — 최근 {hours:g}시간   (아무것도 클릭하지 않습니다)")
    print("=" * 72)

    # ── ① 자동 기능의 켬/끔
    print("\n① 지금 '자동으로 좌표를 누를 수 있는' 것들")
    for name, fname, key, dflt, note in AUTO:
        if fname and key:
            v = _jget(fname, key, dflt)
            on = bool(v) if v is not None else bool(dflt)
            mark = "🔴 켜짐" if on else "⚫ 꺼짐"
        elif fname == "island_repeat.json":
            d = _jget(fname, None, {}) or {}
            n = len([k for k in d if "|" in k])
            mark = f"🔴 {n}슬롯 걸림" if n else "⚫ 없음"
        else:
            mark = "— 버튼"
        print(f"   {mark:<12s} {name}")
        print(f"   {'':<12s}   {note}")

    # ── ② 기록에서 누가 눌렀나
    if not os.path.exists(LOG):
        print(f"\n⚠ 기록 파일이 없습니다: {LOG}")
        return 1
    cut = time.time() - hours * 3600
    now = time.localtime()
    lines = io.open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    cnt = Counter()
    first, last = {}, {}
    rows = []
    for ln in lines[-20000:]:
        m = re.match(r"^(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d) ", ln)
        if not m:
            continue
        try:
            t = time.mktime((now.tm_year, int(m.group(1)), int(m.group(2)),
                             int(m.group(3)), int(m.group(4)), int(m.group(5)),
                             0, 0, -1))
        except Exception:
            continue
        if t < cut:
            continue
        body = ln[15:]
        for rx, label in WHO:
            g = rx.search(body)
            if g:
                who = label.format(*g.groups()) if g.groups() else label
                cnt[who] += 1
                first.setdefault(who, ln[:14])
                last[who] = ln[:14]
                rows.append((ln[:14], who, body[:70]))
                break
    print(f"\n② 최근 {hours:g}시간 동안 **실제로 움직인 것** (기록 기준)")
    if not cnt:
        print("   아무것도 안 움직였습니다 ✔")
    else:
        print(f"   {'무엇이':<26s} {'횟수':>5s}  {'처음':>12s}  {'마지막':>12s}")
        for who, c in cnt.most_common():
            print(f"   {who:<26s} {c:5d}  {first[who]:>12s}  {last[who]:>12s}")

    # ── ③ 마지막 30줄
    print(f"\n③ 마지막 움직임 30줄 (시각 순)")
    for tm, who, body in rows[-30:]:
        print(f"   {tm}  {who:<22s} {body}")

    print("\n" + "=" * 72)
    print(" 📌 작업 중에 끼어든 것이 보이면 그 기능을 끄세요:")
    print("    💧 물약감시·🏘 마을감시 → 섬/던전 창의 [💧 자동 ON/OFF]")
    print("    😴 유휴 자동복구       → 메인런처 영웅 판 아래 [😴 5분 쉬면 자동복구]")
    print("    🃏 변신확정 자동       → 변신확정 창의 [들어가면 스스로 누른다]")
    print("    ⏰ 반복               → 섬/던전 창의 [⏰ 반복 끄기(전체)]")
    print(" ✋ 2026-10-21 판부터는 **마우스를 만진 뒤 10초간** 자동 작업이 미뤄집니다.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
