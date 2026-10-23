# -*- coding: utf-8 -*-
"""💧 물약감시가 왜 안 도는지 한 화면에 보여준다 (로컬 진단용).

    py check_potion.py

메인에서도 로컬에서도 그냥 돌리면 된다. **아무것도 클릭하지 않는다.**
2026-10-17 — 로컬에서 "물약이 없는데 다시 실행을 안 한다" 를 짚으려고 만들었다.
"""
import io, os, sys, json, glob, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI")


def line(t=""):
    print(t)


def head(t):
    line(); line("─" * 66); line(t); line("─" * 66)


try:
    import lineagem_island as isl
except Exception as e:
    line("✘ lineagem_island 를 못 읽었다: %s" % e)
    line("   이 파일을 **런처 폴더(바탕화면)** 에 두고 돌려야 한다.")
    sys.exit(1)

# ── ① 코드·그림이 왔나 ────────────────────────────────────────────────────
head("① 코드·그림이 로컬에 왔나")
for f in ("lineagem_launcher.py", "lineagem_island.py"):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        st = os.stat(p)
        line("   %-22s %9s B · %s" % (f, format(st.st_size, ","),
             time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))))
    else:
        line("   %-22s ✘ 없다" % f)

q = isl.potion0_img_path()
line("   물약 문구 그림  %s" % ("있다  " + q if os.path.exists(q) else "✘ 없다 → [💧 0개 그림 등록]"))
line("   기준(thr)       %.2f" % isl.potion0_thr())
try:
    mp = os.path.join(isl.IMG_DIR, "potion0_meta.json")
    mw = (json.load(open(mp, encoding="utf-8-sig")) or {}).get("w")
    line("   기준 창 가로    %s  (그림을 이 가로에 맞춰 보정한다)" % mw)
except Exception:
    line("   기준 창 가로    ✘ potion0_meta.json 없음 — 창 크기가 다르면 못 잡는다")
line("   PLACE_MAX %d · PLACE_MATCH %.2f · PLACE_RATIO %.2f"
     % (isl.PLACE_MAX, isl.PLACE_MATCH, isl.PLACE_RATIO))

# 🚨 **물약 재실행 전용 기준** — 이 두 값이 옛날 것이면 16/16 전부 막힌다.
#    2026-10-23: 1.45 로 올려둔 탓에 실측 배수 1.15~1.33 이 **하나도 못 넘어**
#    물약 0개가 떠도 사흘간 한 번도 안 돌았다 → 1.12 로 내렸다.
_pm = _pr = None
try:
    _lp = os.path.join(HERE, "lineagem_launcher.py")
    _s = io.open(_lp, encoding="utf-8").read() if os.path.exists(_lp) else ""
    for _ln in _s.splitlines():
        for _k in ("P0_PLACE_MATCH", "P0_PLACE_RATIO"):
            if _ln.startswith(_k):
                _v = float(_ln.split("=", 1)[1].split("#")[0].strip())
                if _k.endswith("MATCH"):
                    _pm = _v
                else:
                    _pr = _v
except Exception:
    pass
if _pr is None:
    line("   ✘ P0_PLACE_RATIO 를 못 읽었다 — 런처 코드가 아주 옛날 것이다")
else:
    line("   물약재실행 기준  P0_PLACE_MATCH %.2f · P0_PLACE_RATIO %.2f"
         % (_pm or 0, _pr))
    if _pr > 1.20:
        line("   🚨 **P0_PLACE_RATIO 가 %.2f — 옛 코드다. 물약감시가 통째로 막힌다.**"
             % _pr)
        line("      실측 배수는 1.15~1.33 이라 1.45 는 아무도 못 넘는다.")
        line("      → 런처의 [🔄 업데이트] 를 누른 뒤 다시 돌려주세요 (1.12 가 되어야 한다)")
    else:
        line("   ✔ 새 코드다 (배수 %.2f ≤ 1.20)" % _pr)

# ── ② 켜져 있나 ───────────────────────────────────────────────────────────
head("② 켜져 있나")
on = isl.potion0_on()
line("   💧 물약감시  %s" % ("켬 ✔" if on else "✘ 꺼짐 — 던전 창의 [💧 자동 ON/OFF] 를 켤 것"))

# ── ③ 던전별 장소그림 (없으면 상시감시가 그 던전을 아예 안 본다) ──────────
head("③ 장소그림 — **없으면 상시감시가 그 던전을 건너뛴다**")
KEYS = [d["key"] for d in isl.DUNGEONS[:4]]
for k in KEYS:
    n = len(isl.place_list(k))
    line("   %-16s %2d장 %s" % (k, n, "✔" if n else "✘ [📍 던전이름 등록] 필요"))
line("   %-16s %2d장" % ("마을(_마을)", len(isl.place_list(isl.TOWN_KEY))))

# ── ④ 슬롯 ON/OFF·좌표 ────────────────────────────────────────────────────
head("④ 슬롯 — OFF 이거나 좌표가 없으면 돌리지 않는다")
try:
    ic = json.load(open(os.path.join(HERE, "island_coords.json"), encoding="utf-8-sig"))
except Exception as e:
    ic = {}
    line("   ✘ island_coords.json 을 못 읽었다: %s" % e)
ancs = {}
for k in KEYS:
    slots = ic.get(k) or []
    onn = [i + 1 for i, s in enumerate(slots)
           if isinstance(s, dict) and s.get("enabled", True)
           and isl.IslandApp._slot_anchor(s)]
    line("   %-16s 쓸 수 있는 슬롯 %2d개  %s" % (k, len(onn), onn if onn else "← 전부 OFF/좌표없음"))
    for i, s in enumerate(slots):
        if isinstance(s, dict) and isl.IslandApp._slot_anchor(s):
            ancs.setdefault(i, isl.IslandApp._slot_anchor(s))

# ── ⑤ 지금 화면 ───────────────────────────────────────────────────────────
head("⑤ 지금 16클라 — 물약 문구 · 어느 던전인가")
if not ancs:
    line("   ✘ 슬롯 좌표가 하나도 없어 볼 수 없다")
else:
    line("   슬롯  물약문구   장소(1등 / 2등)                    판정")
    hits = []
    for si in sorted(ancs):
        anc = ancs[si]
        try:
            seen, pv = isl.potion0_seen(anc)
        except Exception:
            seen, pv = False, -1.0
        sv = isl.place_scores([isl.TOWN_KEY] + KEYS, anc) or {}
        rank = sorted(sv.items(), key=lambda kv: -kv[1])
        t1 = rank[0] if rank else ("", 0.0)
        t2 = rank[1] if len(rank) > 1 else ("", 0.0)
        ratio = (t1[1] / t2[1]) if t2[1] > 0 else 99.0
        if t1[1] < isl.PLACE_MATCH:
            v = "모름(창이 가렸거나 미등록)"
        elif ratio < isl.PLACE_RATIO:
            v = "애매 — 그림을 한 장 더"
        else:
            v = t1[0]
        mark = " ← 0개!" if (seen and pv >= isl.potion0_thr()) else ""
        if mark:
            hits.append(si + 1)
        line("    %02d   %.2f%s  %-14s %.2f / %-12s %.2f  %s"
             % (si + 1, pv, " " * 3, t1[0][:14], t1[1], t2[0][:12], t2[1], v + mark))
    line()
    line("   → 물약 0개로 잡힌 슬롯: %s" % (hits if hits else "없음"))

# ── ⑥ 최근 기록 ───────────────────────────────────────────────────────────
head("⑥ 최근 [물약감시] 기록 12줄 — **안 도는 이유가 여기 적힌다**")
lg = os.path.join(LOCAL, "click_log.txt")
try:
    with open(lg, encoding="utf-8", errors="replace") as f:
        rows = [l.rstrip() for l in f if "[물약감시]" in l or "[마을감시]" in l]
    for r in rows[-12:]:
        line("   " + r[:160])
    if not rows:
        line("   ✘ 기록이 한 줄도 없다 — 런처가 옛 코드이거나 감시가 안 돌고 있다")
except Exception as e:
    line("   ✘ click_log.txt 를 못 읽었다: %s" % e)

head("무엇을 볼까")
line("   ③ 장소그림이 0장 → 그 던전은 상시감시가 **아예 안 본다**")
line("   ④ 슬롯이 OFF   → 그 슬롯은 어떤 경로로도 안 돈다")
line("   ⑤ '애매'       → 그 슬롯에서 [📍 던전이름 등록] 으로 한 장 더 받는다")
line("   ⑤ 물약문구 점수가 기준 바로 밑 → 그 화면에서 [💧 0개 그림 등록] 을 다시")
line("   ⑥ 기록이 없다  → 🔄 업데이트 후 런처 재시작")
