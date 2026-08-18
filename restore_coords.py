# -*- coding: utf-8 -*-
"""좌표 되돌리기 — 업데이트로 좌표가 덮어써졌을 때 원래대로 복구한다.

쓰는 법 (그 컴퓨터에서):
    py restore_coords.py            → 되돌릴 수 있는 시점 목록만 보여준다 (아무것도 안 바꿈)
    py restore_coords.py 3          → 목록의 3번으로 되돌린다 (되돌리기 전 현재 상태도 백업)
    py restore_coords.py 3 coords   → coords.json 만 되돌린다 (island 는 그대로)

찾는 곳 (최근 것부터):
    %LOCALAPPDATA%\\MoonAI\\backups        — 업데이트 직전 자동 백업(_before_update_), 하루 1회 백업
    %LOCALAPPDATA%\\MoonAI\\usersave       — [💾 좌표저장] 으로 직접 저장해둔 것
"""
import os
import sys
import json
import glob
import shutil
import datetime
import subprocess

DESK = os.path.join(os.path.expanduser("~"), "Desktop")
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", DESK), "MoonAI")
BACKUPS = os.path.join(LOCAL, "backups")
USERSAVE = os.path.join(LOCAL, "usersave")
FILES = ("coords.json", "island_coords.json")


def count_coords(path):
    """그 파일에 등록된 좌표가 몇 개인지 — 백업이 멀쩡한지 판단용."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return -1
    n = 0

    def walk(v):
        nonlocal n
        if isinstance(v, list):
            if len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
                n += 1
            else:
                for x in v:
                    walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(d)
    return n


def candidates():
    """되돌릴 수 있는 시점 — (시각, 설명, {파일: 경로})"""
    out = {}
    for p in glob.glob(os.path.join(BACKUPS, "*")):
        b = os.path.basename(p)
        # island_coords.json 이 coords.json 으로도 끝나므로 island 를 먼저 본다
        if b.endswith("island_coords.json"):
            f, stamp = "island_coords.json", b[:-len("island_coords.json")]
        elif b.endswith("coords.json"):
            f, stamp = "coords.json", b[:-len("coords.json")]
        else:
            continue
        tag = "업데이트 직전" if "before_update" in b else "자동 백업"
        stamp = (stamp.replace("_before_update", "").replace("_before_restore", "")
                 .replace("_desk", "").replace("_repo", "").rstrip("_"))
        out.setdefault((stamp, tag), {})[f] = p
    for f in FILES:
        p2 = os.path.join(USERSAVE, f)
        if os.path.exists(p2):
            st = datetime.datetime.fromtimestamp(os.path.getmtime(p2)).strftime("%Y%m%d_%H%M%S")
            out.setdefault((st, "좌표저장 버튼"), {})[f] = p2
    rows = []
    for (stamp, tag), files in out.items():
        rows.append((stamp, tag, files))
    rows.sort(key=lambda r: r[0])
    return rows


def show(rows, limit=20):
    cur = {f: count_coords(os.path.join(DESK, f)) for f in FILES}
    print(f"\n지금 바탕화면: coords {cur['coords.json']}좌표 / "
          f"island {cur['island_coords.json']}좌표\n")
    print(" 번호  시각              종류            coords    island")
    print(" " + "-" * 62)
    _from = max(0, len(rows) - limit)
    if _from:
        print(f"   … 오래된 {_from}개 생략 (전부 보려면:  py restore_coords.py all)")
    for i, (stamp, tag, files) in enumerate(rows, 1):
        if i <= _from:
            continue
        c1 = count_coords(files["coords.json"]) if "coords.json" in files else None
        c2 = count_coords(files["island_coords.json"]) if "island_coords.json" in files else None
        print(f" {i:>3}   {stamp:<16}  {tag:<14}  "
              f"{(str(c1) + '좌표') if c1 is not None else '   -':>8}  "
              f"{(str(c2) + '좌표') if c2 is not None else '   -':>8}")
    print("\n되돌리려면:  py restore_coords.py <번호>        (예: py restore_coords.py "
          f"{len(rows)})")
    print("한 파일만:   py restore_coords.py <번호> coords   또는  island\n")


def restore(rows, idx, only=None):
    if not (1 <= idx <= len(rows)):
        print("그런 번호가 없습니다."); return
    stamp, tag, files = rows[idx - 1]
    want = FILES
    if only == "coords":
        want = ("coords.json",)
    elif only == "island":
        want = ("island_coords.json",)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUPS, exist_ok=True)
    done = []
    for f in want:
        src = files.get(f)
        if not src:
            print(f"  {f}: 이 시점엔 백업이 없습니다 — 건너뜀"); continue
        if count_coords(src) <= 0:
            print(f"  {f}: 백업이 비어 있어 건너뜁니다 (안전장치)"); continue
        dst = os.path.join(DESK, f)
        if os.path.exists(dst):      # 되돌리기 전 지금 상태도 백업
            shutil.copy2(dst, os.path.join(BACKUPS, f"{now}_before_restore_{f}"))
        shutil.copy2(src, dst)
        done.append(f"{f}({count_coords(dst)}좌표)")
    if not done:
        print("되돌린 것이 없습니다."); return
    print(f"\n✔ {stamp} ({tag}) 시점으로 되돌렸습니다 — {', '.join(done)}")
    print("   되돌리기 직전 상태는 backups\\%s_before_restore_* 에 백업해뒀습니다." % now)
    try:                              # 런처를 다시 띄워 새 좌표로 돌게
        subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
        subprocess.run(["schtasks", "/Run", "/TN", "LineageM_Watchdog"], capture_output=True)
        print("   메인런처를 다시 실행했습니다.")
    except Exception:
        print("   ⚠ 런처 재시작은 직접 해주세요.")


def main():
    rows = candidates()
    if not rows:
        print("되돌릴 백업이 없습니다. (%s)" % BACKUPS); return
    if len(sys.argv) < 2:
        show(rows); return
    if sys.argv[1] == "all":
        show(rows, limit=len(rows)); return
    try:
        idx = int(sys.argv[1])
    except ValueError:
        show(rows); return
    restore(rows, idx, sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
