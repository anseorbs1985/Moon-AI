# -*- coding: utf-8 -*-
r"""🩹 **섬/던전 좌표를 그 던전만 되살린다** — 로컬 전용 (2026-11-09).

사용자: *"로컬에서 **잊섬 좌표가 날아갔고**, 좌표를 채워도 실행이 안 되는 버그가
        있는데 뭐 때문에 그런 거야?"*

### 🚨 원인 — 클로드가 `NEVER_ISLAND` 를 껐다
```
10-14  NEVER_ISLAND = True    ← 사용자 최우선 지시로 코드에 박았다
11-04 17:15  **False**        ← 클로드가 끄고 `share_island.json` 에 6개 던전을 적었다
11-04 22:41  True             ← 되돌렸다. **열려 있던 5시간 26분**
```
그 사이에 🔄 를 누른 로컬은 아래가 **메인 것으로 통째로** 갈렸다:
`월요일_잊혀진섬 · 토요일_악몽의섬 · 화요일_에카 · 수금_오만의탑 · 귀환주문서 ·
카매사오기` + **프리셋 정의**(`presets: True`).
메인 좌표는 **메인 클라 위치 기준**이라 로컬에서는 전부 어긋난다 = "좌표가 날아갔다".

### 쓰는 법
```
py fix_local_island.py              ← 무엇을 되살릴 수 있나 **보여만 준다**
py fix_local_island.py --go         ← 되살린다 (직전 상태는 자동 백업)
py fix_local_island.py 잊혀진섬 --go  ← 그 던전만
```
🚫 **메인에서는 거부한다** — 메인은 좌표 원본이다.
🛟 되살리기 전 상태는 `backups\<시각>_before_islfix_island_coords.json` 로 남긴다.
🧷 되살리는 것: 그 던전의 **슬롯 전체**(좌표·간격·방향·이름표·녹화·프리셋 설정) +
   `_presets` 의 그 던전 부분.
🚫 **다른 던전·다른 키는 건드리지 않는다.**
"""
import io, os, sys, json, glob, time, shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
BK = os.path.join(LOCAL, "backups")
F = os.path.join(BASE, "island_coords.json")

# 🚨 2026-11-04 17:15 에 배포가 열렸다. 그 **전** 백업이 '날아가기 전' 것이다.
BAD_FROM = time.mktime(time.strptime("2026-11-04 17:00", "%Y-%m-%d %H:%M"))
# 그때 배포된 던전 — 이것만 되살린다
HIT = ("월요일_잊혀진섬", "토요일_악몽의섬", "화요일_에카", "수금_오만의탑",
       "귀환주문서", "카매사오기")


def jload(p):
    try:
        with io.open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def is_main():
    d = jload(os.path.join(BASE, "local_config.json")) or {}
    return bool(d.get("is_main"))


def ncoord(sl):
    """그 슬롯에 등록된 좌표 개수."""
    if not isinstance(sl, dict):
        return 0
    return len([c for c in (sl.get("coords") or []) if c])


def dsum(d, key):
    """그 던전의 좌표 개수 합계 · 슬롯 수."""
    L = (d or {}).get(key) or []
    return sum(ncoord(s) for s in L), len(L)


def main():
    if is_main():
        print()
        print("🚫 **여기는 메인 컴퓨터다** — 메인 좌표는 배포의 원본이라")
        print("   되살리면 안 된다. 이 도구는 **로컬에서만** 쓴다.")
        return 2

    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    go = "--go" in sys.argv

    cur = jload(F)
    if cur is None:
        print("🚫 island_coords.json 을 읽을 수 없다: %s" % F)
        return 1

    keys = [k for k in HIT if k in cur]
    if want:
        keys = [k for k in keys if any(w in k for w in want)]
    if not keys:
        print("되살릴 던전이 없다 (이름을 확인해주세요: %s)" % " · ".join(HIT))
        return 1

    # 📦 '날아가기 전' 백업을 최신부터 찾는다
    cands = []
    for p in glob.glob(os.path.join(BK, "*island_coords.json")):
        try:
            m = os.path.getmtime(p)
        except Exception:
            continue
        if m < BAD_FROM and os.path.getsize(p) > 2000:
            cands.append((m, p))
    cands.sort(reverse=True)

    print()
    print("=" * 94)
    print("🩹 섬/던전 좌표 되살리기 — 로컬 전용")
    print("=" * 94)
    print("   지금 파일 : %s" % F)
    print("              %d B · %s"
          % (os.path.getsize(F), time.strftime("%m-%d %H:%M",
                                               time.localtime(os.path.getmtime(F)))))
    print("   백업 폴더 : %s" % BK)
    print("   '날아가기 전'(11-04 17:00 이전) 백업 %d개" % len(cands))
    for m, p in cands[:6]:
        print("      %s  %9d B  %s" % (time.strftime("%m-%d %H:%M", time.localtime(m)),
                                       os.path.getsize(p), os.path.basename(p)))
    if not cands:
        print()
        print("🚫 **되살릴 백업이 없다.**")
        print("   좌표는 그 컴퓨터에서 다시 찍어야 한다. 한 슬롯만 찍고")
        print("   그 던전 창의 **[📋 전체붙임]** 을 누르면 16슬롯에 퍼진다")
        print("   (클라 창 위치가 자동 보정된다).")
        return 1

    # 가장 가까운 백업에서 그 던전을 꺼낸다
    src = None
    for m, p in cands:
        d = jload(p)
        if not d:
            continue
        if any((d.get(k) or []) for k in keys):
            src = (m, p, d)
            break
    if not src:
        print()
        print("🚫 백업에 그 던전 자료가 없다.")
        return 1
    sm, sp, sd = src

    print()
    print("   📦 쓸 백업 : %s  (%s)"
          % (os.path.basename(sp), time.strftime("%m-%d %H:%M", time.localtime(sm))))
    print()
    print("   던전                  지금 → 되살림      슬롯")
    print("   " + "-" * 62)
    plan = []
    for k in keys:
        c0, n0 = dsum(cur, k)
        c1, n1 = dsum(sd, k)
        if not c1:
            print("   %-20s 백업에 자료 없음 — 건너뜀" % k)
            continue
        same = json.dumps(cur.get(k), ensure_ascii=False, sort_keys=True) == \
            json.dumps(sd.get(k), ensure_ascii=False, sort_keys=True)
        mark = "이미 같음" if same else "되살린다"
        print("   %-20s 좌표 %4d → %4d     %2d → %2d   %s"
              % (k, c0, c1, n0, n1, mark))
        if not same:
            plan.append(k)

    # 프리셋도 같이 (presets: True 로 배포됐다)
    pr_cur = (cur.get("_presets") or {})
    pr_src = (sd.get("_presets") or {})
    pplan = []
    for k in plan:
        if k in pr_src and json.dumps(pr_cur.get(k), ensure_ascii=False,
                                      sort_keys=True) != \
                json.dumps(pr_src.get(k), ensure_ascii=False, sort_keys=True):
            pplan.append(k)
    if pplan:
        print()
        print("   🧪 프리셋도 되살린다 (11-04 배포가 presets:True 였다): %s"
              % " · ".join(pplan))

    if not plan and not pplan:
        print()
        print("✔ **되살릴 것이 없다** — 지금 좌표가 그 백업과 같다.")
        print("   그래도 실행이 안 되면 `py check_local.py` 의 ⑨ 섬/던전 을 보세요.")
        return 0

    if not go:
        print()
        print("=" * 94)
        print("  위 내용이 맞으면 **--go** 를 붙여 다시 실행하세요:")
        print("     py fix_local_island.py%s --go"
              % ("" if not want else " " + " ".join(want)))
        print("  ⚠ 먼저 **메인런처와 섬/던전 실행기를 꺼주세요** (켜져 있으면 저장이 엉킵니다)")
        print("=" * 94)
        return 0

    # 🛟 직전 상태 백업
    try:
        os.makedirs(BK, exist_ok=True)
        bkp = os.path.join(BK, time.strftime("%Y%m%d_%H%M%S")
                           + "_before_islfix_island_coords.json")
        shutil.copy2(F, bkp)
        print()
        print("   📦 직전 상태를 남겼다: %s" % os.path.basename(bkp))
    except Exception as e:
        print("🚫 백업을 못 만들어 중단한다: %s" % e)
        return 1

    for k in plan:
        cur[k] = sd[k]
    if pplan:
        pr = cur.get("_presets")
        if not isinstance(pr, dict):
            pr = {}
        for k in pplan:
            pr[k] = pr_src[k]
        cur["_presets"] = pr

    tmp = F + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    if os.path.getsize(tmp) < 2000:
        os.remove(tmp)
        print("🚫 쓴 파일이 너무 작다 — 중단한다 (원본은 그대로)")
        return 1
    os.replace(tmp, F)

    print()
    print("✅ **되살렸다** — 던전 %s%s"
          % (" · ".join(plan), (" · 프리셋 " + " · ".join(pplan)) if pplan else ""))
    for k in plan:
        c, n = dsum(cur, k)
        print("   %-20s 좌표 %d개 · 슬롯 %d개" % (k, c, n))
    print()
    print("   이제 **메인런처를 다시 켜고**, 그 던전 창을 **닫았다 다시 열어** 확인하세요")
    print("   (섬/던전 실행기는 별도 프로세스라 열려 있던 창은 옛 값을 들고 있습니다).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("🚫 오류: %s" % e)
        sys.exit(1)
