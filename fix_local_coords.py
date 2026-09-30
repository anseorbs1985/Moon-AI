# -*- coding: utf-8 -*-
"""🩹 업데이트에 덮어써진 좌표만 골라 되살린다 (그 컴퓨터에서 실행).

쓰는 법:
    py fix_local_coords.py          → 무엇이 덮어써졌는지 **보여만** 준다 (아무것도 안 바꿈)
    py fix_local_coords.py --go     → 그 항목만 원래대로 되돌리고 런처를 재시작한다

왜 필요한가 (2026-09-30 사고):
  `share_coords.json` 의 **force** 를 작업 뒤 비우지 않아서, 로컬이 🔄 업데이트를
  누를 때마다 접속 흐름 좌표와 작위 16슬롯이 **메인 것으로 갈아끼워졌다.**

  `restore_coords.py` 로 통째로 되돌릴 수도 있지만, 그러면 **그 사이에 맞춰둔 다른
  좌표까지 과거로 돌아간다.** 이 도구는 **덮어써진 항목만** 골라 되살린다.

어떻게 '덮어써졌다' 고 판단하나:
  저장소의 `share_coords_data.json` 에는 **메인이 배포한 값**이 그대로 들어 있다.
  지금 내 좌표가 그 값과 **똑같으면** = 업데이트가 갈아끼운 것이다.
  그러면 백업들을 최신부터 훑어 **그 값과 다른(= 내가 찍었던)** 것을 찾아 되살린다.

찾는 곳 (최근 것부터):
  %LOCALAPPDATA%\\MoonAI\\backups · usersave\\history · usersave\\coords.json
"""
import datetime
import glob
import io
import json
import os
import shutil
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DESK = os.path.join(os.path.expanduser("~"), "Desktop")
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI")
CUR = os.path.join(DESK, "coords.json")


def jload(path):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return None


def repo_dir():
    """저장소(Moon-AI) 폴더 찾기 — share_coords_data.json 이 있는 곳."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (here, os.path.join(DESK, "Moon-AI"),
              os.path.join(os.path.expanduser("~"), "Moon-AI")):
        if os.path.exists(os.path.join(p, "share_coords_data.json")):
            return p
    return None


def n_coords(v):
    """그 항목에 등록된 좌표 개수 (대충 세어 표시용)."""
    s = json.dumps(v, ensure_ascii=False)
    return s.count("[") if isinstance(v, (list, dict)) else 0


def candidates():
    """되살릴 값을 찾을 백업 파일들 — **최신 것부터**."""
    out = []
    for p in glob.glob(os.path.join(LOCAL, "backups", "*coords.json")):
        if "island" in os.path.basename(p):
            continue
        out.append(p)
    out += glob.glob(os.path.join(LOCAL, "usersave", "history", "*coords.json"))
    us = os.path.join(LOCAL, "usersave", "coords.json")
    if os.path.exists(us):
        out.append(us)
    out = [p for p in out if os.path.exists(p)]
    out.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return out


def is_main():
    """메인 컴퓨터인가 — `local_config.json` 의 is_main."""
    for p in (os.path.join(DESK, "local_config.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "local_config.json")):
        d = jload(p)
        if isinstance(d, dict) and "is_main" in d:
            return bool(d.get("is_main"))
    return False


def main():
    go = "--go" in sys.argv

    # 🚨 메인에서는 절대 돌리지 않는다.
    # 메인의 좌표가 **배포의 원본**이므로, '지금 값 == 배포된 값' 은 당연히 참이다.
    # 그대로 --go 를 하면 옛 백업 값으로 **메인 좌표를 망친다.**
    # (실측 2026-09-30: 메인에서 돌려보니 5개 항목을 09-02 값으로 되돌리려 했다)
    if is_main():
        print("🚨 여기는 **메인 컴퓨터**다 — 이 도구는 돌리지 않는다.")
        print("   메인 좌표가 배포의 원본이라 '지금 값 = 배포된 값' 이 당연하고,")
        print("   그대로 되돌리면 **메인 좌표를 옛 백업으로 망친다.**")
        print("   이 도구는 **좌표가 돌아간 로컬 컴퓨터에서** 실행하세요.")
        return 2

    cur = jload(CUR)
    if not isinstance(cur, dict):
        print(f"✘ 내 좌표를 못 읽었다: {CUR}")
        return 1
    rd = repo_dir()
    if not rd:
        print("✘ 저장소(Moon-AI) 폴더에서 share_coords_data.json 을 못 찾았다.")
        print("  → 이 파일을 저장소 폴더에 두고 다시 실행하거나, 통째 되돌리기를 쓰세요:")
        print("     py restore_coords.py")
        return 1
    main_vals = jload(os.path.join(rd, "share_coords_data.json")) or {}
    main_vals = {k: v for k, v in main_vals.items() if not k.startswith("_")}
    if not main_vals:
        print("✘ share_coords_data.json 이 비어 있다 — 비교할 기준이 없다.")
        return 1

    # ① 지금 값이 '메인이 배포한 값' 과 똑같은 항목 = 갈아끼워진 것
    hit = [k for k, v in main_vals.items()
           if k in cur and json.dumps(cur[k], ensure_ascii=False, sort_keys=True)
           == json.dumps(v, ensure_ascii=False, sort_keys=True)]
    if not hit:
        print("✅ 메인이 배포한 값과 똑같은 항목이 없다 — 덮어써진 좌표가 없어 보인다.")
        print("   그래도 이상하면 통째 되돌리기 목록을 보세요:  py restore_coords.py")
        return 0

    print(f"⚠ 메인 값으로 갈아끼워진 것으로 보이는 항목 {len(hit)}개\n")
    cands = candidates()
    print(f"   백업 {len(cands)}개를 최신부터 훑는다\n")

    plan, miss = {}, []
    for k in hit:
        mv = json.dumps(main_vals[k], ensure_ascii=False, sort_keys=True)
        found = None
        for p in cands:
            d = jload(p)
            if not isinstance(d, dict) or k not in d:
                continue
            bv = json.dumps(d[k], ensure_ascii=False, sort_keys=True)
            if bv != mv:                       # 내가 찍었던 값이다
                found = (p, d[k])
                break
        if found:
            plan[k] = found
        else:
            miss.append(k)

    w = max(len(k) for k in hit) + 1
    print(f"   {'항목':<{w}} {'지금(메인값)':>12}   {'되살릴 값':>10}   어디서")
    print("   " + "-" * 74)
    for k in hit:
        now_n = n_coords(cur.get(k))
        if k in plan:
            p, v = plan[k]
            src = os.path.basename(p)
            if "usersave" in p and "history" not in p:
                src = "💾 좌표저장"
            t = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            print(f"   {k:<{w}} {now_n:>9}좌표 → {n_coords(v):>7}좌표   "
                  f"{src}  ({t:%m-%d %H:%M})")
        else:
            print(f"   {k:<{w}} {now_n:>9}좌표      "
                  f"✘ 되살릴 값을 백업에서 못 찾음")
    print()

    if not plan:
        print("✘ 되살릴 값을 하나도 못 찾았다. 통째 되돌리기를 써보세요:")
        print("   py restore_coords.py")
        return 1
    if miss:
        print(f"※ {len(miss)}개는 백업에 다른 값이 없어 그대로 둔다: {', '.join(miss)}")
    if not go:
        print("지금은 **보여주기만** 했다. 실제로 되살리려면:")
        print("   py fix_local_coords.py --go")
        return 0

    # ② 되돌리기 — 지금 상태를 먼저 백업하고, **그 항목만** 고쳐 쓴다
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(LOCAL, "backups")
    os.makedirs(bdir, exist_ok=True)
    bk = os.path.join(bdir, f"{now}_before_fixkeys_coords.json")
    shutil.copy2(CUR, bk)
    print(f"· 지금 상태 백업: {bk}")

    fresh = jload(CUR)                         # 쓰기 직전에 다시 읽는다 (통째 덮어쓰기 금지)
    if not isinstance(fresh, dict):
        print("✘ 쓰기 직전 다시 읽기 실패 — 중단")
        return 1
    for k, (p, v) in plan.items():
        fresh[k] = v
    tmp = CUR + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(fresh, f, ensure_ascii=False, indent=2)
    if os.path.getsize(tmp) < 2000:            # 깨진 파일로 갈아끼우지 않는다
        os.remove(tmp)
        print("✘ 새로 쓴 파일이 너무 작다 — 중단 (원본 그대로)")
        return 1
    os.replace(tmp, CUR)
    print(f"✔ {len(plan)}개 항목을 되살렸다: {', '.join(plan)}")

    # ③ 런처 재시작 (메모리의 옛 값이 다시 저장되는 것을 막으려면 필수)
    try:
        subprocess.run(["schtasks", "/run", "/tn", "LineageM_Watchdog"],
                       capture_output=True, timeout=30)
        print("✔ 워치독으로 런처를 재시작했다 — 잠시 뒤 좌표를 확인하세요")
    except Exception as e:
        print(f"※ 런처 재시작 실패({e}) — 런처를 직접 껐다 켜주세요")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
