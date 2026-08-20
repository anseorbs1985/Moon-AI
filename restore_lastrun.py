# -*- coding: utf-8 -*-
"""섬/던전 좌표를 '그 던전을 마지막으로 실행했던 때'로 되돌린다 (그 컴퓨터에서 직접 실행).

    py restore_lastrun.py            → 무엇을 찾았는지 보여주기만 한다 (아무것도 안 바꿈)
    py restore_lastrun.py go         → 실제로 되돌린다 (녹화는 지금 것 그대로)
    py restore_lastrun.py go 에카     → 이름에 '에카'가 들어간 던전만

되돌리는 것 : 좌표·이름·간격·방향·프리셋
그대로 두는 것: 녹화(⏺), 다른 던전, coords.json(메인런처 좌표) 전부
"""
import os
import re
import sys
import json
import glob
import shutil
import datetime
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DESK = os.path.join(os.path.expanduser("~"), "Desktop")
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI")
BACKUPS = os.path.join(LOCAL, "backups")
RUNSNAP = os.path.join(LOCAL, "runsnap")
ISLAND = os.path.join(DESK, "island_coords.json")
DUNGEON_HINT = ("섬", "탑", "에카", "주문서", "카매사")


def last_run_times():
    """repeat_log.txt 에서 던전별 '마지막으로 클릭이 돌아간 시각'."""
    p = os.path.join(LOCAL, "repeat_log.txt")
    if not os.path.exists(p):
        print(f"[!] 실행 기록이 없습니다: {p}")
        return {}, 0
    year = datetime.date.today().year
    out, hit = {}, 0
    for ln in open(p, encoding="utf-8", errors="replace"):
        m = re.match(r"\[(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\]\s+(?:\[클릭\]\s+)?(\S+)", ln)
        if not m:
            continue
        mm, dd, hh, mi, ss, key = m.groups()
        if not any(x in key for x in DUNGEON_HINT):
            continue
        try:
            t = datetime.datetime(year, int(mm), int(dd), int(hh), int(mi), int(ss))
        except ValueError:
            continue
        if t > datetime.datetime.now() + datetime.timedelta(days=1):
            t = t.replace(year=year - 1)
        hit += 1
        if key not in out or t > out[key]:
            out[key] = t
    return out, hit


def sources(key):
    """그 던전을 되돌릴 수 있는 자료 — (시각, 경로, 종류) 오래된 것부터."""
    rows = []
    for p in glob.glob(os.path.join(RUNSNAP, f"{key}_*.json")):
        rows.append((datetime.datetime.fromtimestamp(os.path.getmtime(p)), p, "실행직전"))
    for p in glob.glob(os.path.join(BACKUPS, "*island_coords.json")):
        rows.append((datetime.datetime.fromtimestamp(os.path.getmtime(p)), p, "백업"))
    rows.sort(key=lambda r: r[0])
    return rows


def slots_in(path, key):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    v = d.get(key)
    if not isinstance(v, list) or not v:
        return None
    if not any(isinstance(s, dict) and any(s.get("coords") or []) for s in v):
        return None
    return v


def pick_for(key, t):
    """마지막 실행 시각(t) 이전의 가장 최근 자료. 없으면 가장 오래된 것이라도."""
    rows = [r for r in sources(key) if slots_in(r[1], key)]
    if not rows:
        return None, []
    before = [r for r in rows if r[0] <= t + datetime.timedelta(seconds=90)]
    return (before[-1] if before else rows[0]), rows


def main():
    go = len(sys.argv) > 1 and sys.argv[1] == "go"
    only = sys.argv[2] if len(sys.argv) > 2 else None
    if not os.path.exists(ISLAND):
        print(f"[!] {ISLAND} 이(가) 없습니다."); return
    runs, hit = last_run_times()
    print(f"\n실행 기록에서 찾은 던전 줄: {hit}개")
    if not runs:
        print("[!] 던전 실행 기록을 못 찾았습니다 — 되돌릴 기준이 없습니다.")
        print("    (%LOCALAPPDATA%\\MoonAI\\repeat_log.txt 확인)")
        return
    with open(ISLAND, encoding="utf-8") as f:
        cur = json.load(f)
    plan = []
    for key, t in sorted(runs.items(), key=lambda x: x[1]):
        if only and only not in key:
            continue
        pick, rows = pick_for(key, t)
        now_n = sum(1 for s in (cur.get(key) or []) if any(s.get("coords") or []))
        if not pick:
            print(f"\n{key}\n   마지막 실행: {t:%m-%d %H:%M}\n   [!] 되돌릴 자료가 없습니다 "
                  f"(백업·스냅샷 {len(rows)}개)")
            continue
        bt, bp, kind = pick
        old = slots_in(bp, key)
        same = json.dumps(old, sort_keys=True) == json.dumps(cur.get(key), sort_keys=True)
        print(f"\n{key}")
        print(f"   마지막 실행 : {t:%m-%d %H:%M}")
        print(f"   되돌릴 자료 : {bt:%m-%d %H:%M}  [{kind}]  {os.path.basename(bp)}")
        print(f"   지금 {now_n}슬롯 → 되돌리면 "
              f"{sum(1 for s in old if any(s.get('coords') or []))}슬롯"
              + ("   (내용이 이미 같음 — 바뀌는 것 없음)" if same else ""))
        if not same:
            plan.append((key, old, bt, kind))
    if not plan:
        print("\n바꿀 것이 없습니다. (이미 그 시점과 같거나 되돌릴 자료가 없음)")
        return
    if not go:
        print(f"\n되돌리려면:  py restore_lastrun.py go     ({len(plan)}개 던전)\n")
        return
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUPS, exist_ok=True)
    shutil.copy2(ISLAND, os.path.join(BACKUPS, f"{now}_before_restore_island_coords.json"))
    for key, old, bt, kind in plan:
        new = json.loads(json.dumps(old))
        cs = cur.get(key)
        if isinstance(cs, list):                       # 녹화(⏺)는 지금 것 유지
            for i, sl in enumerate(new):
                if not isinstance(sl, dict) or i >= len(cs) or not isinstance(cs[i], dict):
                    continue
                for fld in ("recs", "recs_off"):
                    if fld in cs[i]:
                        sl[fld] = cs[i][fld]
                    else:
                        sl.pop(fld, None)
        cur[key] = new
    tmp = ISLAND + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ISLAND)
    print(f"\n[OK] 되돌렸습니다 — " + ", ".join(f"{k}({bt:%m-%d %H:%M} {kind})"
                                              for k, _o, bt, kind in plan))
    print(f"     녹화(⏺)는 지금 것 그대로, 되돌리기 직전 상태는 "
          f"backups\\{now}_before_restore_island_coords.json")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
        subprocess.run(["schtasks", "/Run", "/TN", "LineageM_Watchdog"], capture_output=True)
        print("     메인런처를 다시 실행했습니다.")
    except Exception:
        print("     [!] 런처는 직접 다시 켜주세요.")


if __name__ == "__main__":
    main()
