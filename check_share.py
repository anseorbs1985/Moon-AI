# -*- coding: utf-8 -*-
"""🔍 배포 점검 — 업데이트가 '로컬 좌표를 건드릴 수 있는 통로'를 전부 보여준다.

쓰는 법:  py check_share.py

왜 필요한가 (2026-09-30 사고):
  2026-09-22 '작위·접속 좌표 100% 배포' 를 하려고 `share_coords.json` 의 **force** 에
  12개 항목을 적었는데, **작업이 끝난 뒤 비우지 않았다.** `force` 는
  *'로컬이 이미 찍어둔 좌표도 덮어쓴다'* 는 뜻이라, 그때부터 로컬은
  🔄 업데이트를 누를 때마다 접속 좌표와 작위 16슬롯이 메인 것으로 되돌아갔다.
  사용자: "로컬에 업데이트하면 좌표가 전부 돌아가버리는데 어떻게 하라는 거냐."

  CLAUDE.md 에 *"쓰고 나면 반드시 비운다"* 규칙이 이미 있었지만 사람이(클로드가)
  잊었다. 그래서 **눈으로 바로 확인할 수 있는 도구**를 만들었다.

**좌표를 배포하는 작업을 끝낼 때마 이걸 돌려서 전부 ✔ 인지 확인할 것.**
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

BASE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception as e:
        return {"_읽기실패": str(e)}


def main():
    sc = load("share_coords.json") or {}
    si = load("share_island.json") or {}
    st = load("share_times.json") or {}
    sr = load("share_recs.json") or {}
    ro = load("restore_order.json") or {}
    sk = load("share_skip.json") or {}

    # (이름, 값, 설명, 0이어야 안전한가)
    rows = [
        ("share_coords.json  keys", len(sc.get("keys") or []),
         "coords.json 의 **빈 항목**을 채운다", True),
        ("share_coords.json  force", len(sc.get("force") or []),
         "★ 로컬이 찍어둔 좌표까지 **덮어쓴다**", True),
        ("share_island.json  keys", len(si.get("keys") or []),
         "그 던전을 통째로 덮어쓴다", True),
        ("share_island.json  presets_only", len(si.get("presets_only") or []),
         "그 던전 프리셋(좌표 포함)", True),
        ("share_island.json  presets", 1 if si.get("presets") else 0,
         "프리셋 동기화", True),
        ("share_times.json   keys", len(st.get("keys") or []),
         "그 던전 간격(gap_list) — 좌표는 아님", True),
        ("share_recs.json    keys", len(sr.get("keys") or {}),
         "녹화(⏺)만 — 좌표와 무관", False),
        ("restore_order.json id", 1 if str(ro.get("id") or "").strip() else 0,
         "★ 좌표를 옛 백업으로 되돌린다", True),
        ("restore_order.json keys", len(ro.get("keys") or []),
         "되돌릴 던전", True),
        ("share_skip.json    files", len(sk.get("files") or []),
         "복사 제외 목록 (많을수록 안전)", False),
    ]

    print("통로                                값   무엇을 하는가")
    print("-" * 78)
    warn = []
    for name, val, desc, must_zero in rows:
        ok = (val == 0) or not must_zero
        print(f"{'✔' if ok else '⚠'} {name:34s} {val:>3}   {desc}")
        if not ok:
            warn.append(name)
    print("-" * 78)

    rb = "?"
    try:
        up = io.open(os.path.join(BASE, "lineagem_update.py"),
                     encoding="utf-8").read()
        m = re.search(r'COORDS_ROLLBACK_ID\s*=\s*"([^"]*)"', up)
        rb = m.group(1) if m else "?"
    except Exception:
        pass
    print(f"{'✔' if not rb else '⚠'} COORDS_ROLLBACK_ID = {rb!r:<20} "
          + ("(꺼짐 — 좌표 되돌리기 안 함)" if not rb
             else "★ 켜져 있다! 로컬 좌표를 백업으로 갈아끼운다"))
    if rb:
        warn.append("COORDS_ROLLBACK_ID")

    print()
    if not warn:
        print("✅ 지금 상태로는 업데이트가 **로컬 좌표를 하나도 건드리지 않는다.**")
        print("   (유실 자동복구만 남음 — coords.json 이 없거나 2000바이트 이하일 때만)")
    else:
        print(f"⚠ 좌표를 건드릴 수 있는 통로 {len(warn)}개: {', '.join(warn)}")
        print("   일부러 배포하는 중이면 정상이다. **작업이 끝나면 반드시 비울 것.**")
    return 0 if not warn else 1


if __name__ == "__main__":
    raise SystemExit(main())
