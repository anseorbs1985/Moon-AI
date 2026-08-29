import ctypes
_ocr_reader = None
def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import ctypes, sys, os
        # 콘솔 창 숨기기
        try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except: pass
        os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
        import warnings; warnings.filterwarnings("ignore")
        import easyocr
        _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
    return _ocr_reader

# 콘솔 창 숨기기
try: ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except: pass

# 단일 인스턴스 보장 — 이미 실행 중이면 기존 창 앞으로 띄우고 종료
_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "LineageMAutoLauncher_Mutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    import sys
    sys.exit(0)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass

import tkinter as tk
from tkinter import messagebox
import subprocess, time, threading, json, random, re
import pyautogui
import pygetwindow as gw
import os
import win32gui, win32con

def _find_purple_exe():
    import glob as _glob
    candidates = _glob.glob(r"C:\Program Files (x86)\NCSOFT\Purple\*\Purple.exe")
    if candidates:
        return sorted(candidates)[-1]          # 가장 최신 버전
    return r"C:\Program Files (x86)\NCSOFT\Purple\Purple.exe"
PURPLE_EXE    = _find_purple_exe()
BASE          = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR      = os.path.join(BASE, "lineagem_logs")
os.makedirs(LOGS_DIR, exist_ok=True)
CONFIG_FILE   = os.path.join(BASE, "coords.json")
# 다야 측정 데이터는 git/업데이트/파일복사가 절대 못 건드리는 로컬 앱데이터 폴더에 저장
LOCAL_DATA    = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
try:
    import shutil as _sh
    os.makedirs(os.path.join(LOCAL_DATA, "daya_crops"), exist_ok=True)
    for _f in ("daya_counts.json", "daya_history.json", "daya_regions.json"):  # 예전 위치에서 1회 이관
        _s, _d = os.path.join(BASE, _f), os.path.join(LOCAL_DATA, _f)
        if os.path.exists(_s) and not os.path.exists(_d):
            _sh.copy2(_s, _d)
    _cs = os.path.join(BASE, "daya_crops")
    if os.path.isdir(_cs):
        for _fn in os.listdir(_cs):
            _dd = os.path.join(LOCAL_DATA, "daya_crops", _fn)
            if not os.path.exists(_dd):
                _sh.copy2(os.path.join(_cs, _fn), _dd)
except Exception:
    pass
# 좌표 자동 백업: 하루 1회 — git pull/실수로 좌표가 날아가도 여기서 복구
try:
    import shutil as _sh2, datetime as _dt2
    _bdir = os.path.join(LOCAL_DATA, "backups")
    os.makedirs(_bdir, exist_ok=True)
    _stamp = _dt2.date.today().strftime("%Y%m%d")
    for _f in ("coords.json", "island_coords.json", "local_config.json"):
        _s = os.path.join(BASE, _f)
        _d = os.path.join(_bdir, f"{_stamp}_{_f}")
        if os.path.exists(_s) and not os.path.exists(_d):
            _sh2.copy2(_s, _d)
    _fns = sorted(os.listdir(_bdir))
    for _fn in _fns[:-90]:                     # 최근 90개(약 한 달치)만 보관
        try: os.remove(os.path.join(_bdir, _fn))
        except Exception: pass
except Exception:
    pass
LOCAL_FILE    = os.path.join(BASE, "local_config.json")   # 머신별 설정(깃 공유 안 함, *.json 자동 제외)
LOCAL_KEYS    = ("profile_target_id",)                    # coords.json이 아닌 이 컴퓨터에만 저장할 키
DOLL_ENABLED_KEY = "doll_enabled"   # 인형탐험 슬롯 ON/OFF — 좌표는 공유하되 켜짐 여부만 머신별
ACCOUNTS_FILE = os.path.join(BASE, "accounts.json")
REROLL_DIR    = os.path.join(BASE, "reroll_templates")   # 아이템 리롤 타깃 이미지 저장
pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0.05

# ── 정밀 클릭 (전역) ───────────────────────────────────────────────
# 사용자가 마우스를 움직여도 클릭이 항상 지정 좌표에 찍히도록 SendInput 기반으로
# pyautogui.click/moveTo/mouseDown/mouseUp 을 교체 (precise_click.py 공용 패치).
# SendInput 한 호출에 [이동+누름+뗌]을 묶으면 그 사이에 물리 마우스 입력이
# 끼어들지 않음을 OS가 보장한다. (기존 BlockInput 방식은 관리자 권한이 없으면
# 조용히 실패해서 마우스 이동과 클릭이 경합하는 문제가 남아 있었음)
try:
    from precise_click import install as _install_precise_click
    _install_precise_click(pyautogui)
    try:                       # 사람이 마우스를 쓰는 중인지 감시 (클릭 겹침 방지)
        import precise_click as _pc0
        _pc0.start_input_watch()
    except Exception:
        pass
except Exception:
    pass

CLICK_SLOTS    = 16
GROUP_SIZE     = 8
HUNT_SLOTS     = 16
HUNT_CLICKS    = 5
HUNT_INTERVAL  = 1.4   # 사냥 슬롯 내 클릭 간격(초) — 실제 0.8~1.0초 랜덤
HUNT_SLOT_INTERVAL = 3.5  # 사냥 슬롯 간 간격(초) — 실제로 2~4초 랜덤
CLICK_INNER_INTERVAL = 2.5   # 클릭 슬롯 내 클릭 간격(초, 클릭1→클릭2)
CLICK_SLOT_INTERVAL  = 3.5   # 클릭 슬롯 간 간격(초, #01→#02)
CLICK_INTERVAL = CLICK_SLOT_INTERVAL  # 하위 호환
MAIL_SLOTS     = 16
MAIL_CLICKS    = 6
MAIL_INTERVAL  = 1.12   # 우편함 클릭 간격(초)
DUNGEON_SLOTS  = 16
DUNGEON_CLICKS = 5
DUNGEON_HOVER  = 1.5
COUPON_CLICKS  = 9     # 쿠폰등록 — 슬롯당 좌표 9개 (클릭5에서 글 붙여넣기)
MARKET_CLICKS  = 9     # 거래소검색 — 쿠폰등록과 같은 방식 (좌표 9개, 글 붙여넣기)
EVENTSHOP_CLICKS = 3   # 이벤트상점 — 슬롯당 좌표 3개
COUPON_SLOT_GAP = 3.0  # 쿠폰등록 슬롯 간 기본 간격(초) — 슬롯마다 ×1.02~1.18 랜덤
PAST_SLOTS     = 16
PAST_CLICKS    = 3
PAST_INTERVAL  = 2.8   # 과거의말하는섬 클릭 간격(초)
SCHED_SLOTS        = 16
SCHED_CLICKS       = 3
DRAGON_CLICKS      = 10    # 용던고고!!! — 슬롯당 좌표 10개
DRAGON_BUDGET      = 144   # 전체 슬롯을 2분 24초 안에 (3분에서 20% 단축)
DRAGON_GAP_MIN     = 0.64  # 좌표 간격 최소 (0.8초에서 20% 단축)
DRAGON_GAP_MAX     = 1.84  # 좌표 간격 최대 (2.3초에서 20% 단축)
DRAGON_EXTRA       = {1: (2.0, 3.2)}   # 좌표2→3 추가 대기 (2.5~4.0초에서 20% 단축)

KNIGHT_CLICKS      = 8     # 던전끝! 흑기사!! — 슬롯당 좌표 8개 (2026-08-21 5→8)
KNIGHT_GAP_MIN     = 1.0   # 좌표 간격 최소
KNIGHT_GAP_MAX     = 2.5   # 좌표 간격 최대
KNIGHT_EXTRA       = {1: (9.1, 13.0)}   # 좌표2 뒤(2→3 사이)에 9.1~13초 더 쉰다 (7~10초에서 30% 늘림)

# 런처별 '그 좌표 뒤에 더 쉬는 시간'
# 클릭하지 않고 '마우스만 올려놓는' 좌표 (0부터 셈 — 2 = 좌표3)
HOVER_INDICES = {}      # 마우스만 올리는 자리 — 없앰 (2026-08-21 사용자 지시, 전부 클릭)

# 이 좌표와 '바로 다음 좌표'는 한 묶음으로 — 사이에 다른 슬롯이 끼지 못하게 한다
# (마우스를 올려둔 상태에서 다른 곳을 누르면 다음 클릭이 씹힌다)
ATOMIC_NEXT = {}        # (호버를 없애서 묶을 이유가 사라짐)
# 웨이브(번갈아 실행)를 '앞의 몇 좌표'까지만 하고, 그 뒤는 슬롯을 끝까지 밀어붙인다.
# 용던고고는 좌표4부터 이미지·확인창이 이어져서, 중간에 다른 슬롯이 끼어들면
# 그 창이 닫히거나 포커스가 바뀌어 클릭이 씹힌다 (2026-08-27 사용자 지시).
WAVE_UNTIL = {"dragon": 3}     # 좌표1~3만 교차, 좌표4부터는 그 슬롯 완주
# 슬롯을 섞지 않고 1번부터 순서대로 도는 런처들 (2026-08-28 사용자 지시)
KEEP_ORDER_FKEYS = ("dragon", "sched", "fix")   # 섞지 않고 1번부터 순서대로
EARLY_IN = 2      # 남은 좌표가 이만큼 이하면 '끝나간다'고 보고 다음 슬롯을 미리 넣는다
# 전체를 이 시간 안에 끝낸다 (초). 남은 시간과 남은 클릭 수를 보고 간격을 스스로 줄인다.
# 늘리지는 않는다 — 빨리 끝나면 그대로 끝난다. (2026-08-27 사용자 지시: 4분 10초)
RUN_BUDGET = {"dragon": 270}      # 4분 30초 (2026-08-27 사용자 지시 — 여유 있게)
# 간격을 이보다 더 줄이지 않는다. 너무 서두르면 게임 화면이 아직 안 떠서
# '그림 못 찾음'이 늘어난다 (2026-08-27 — 0.30 으로 뒀다가 인식률이 폭락했다).
PACE_FLOOR = 0.60
NLCH = chr(10)
# 실행이 끝나면 '진단만' 저장소 diag/ 로 올리는 런처 (2026-08-28 사용자 지시)
DIAG_SHARE = ("dragon",)

EXTRA_GAPS = {"dragon": DRAGON_EXTRA, "knight": KNIGHT_EXTRA}


def extra_gap(fkey, j):
    """그 좌표 뒤에 더 쉬는 시간 (범위면 랜덤)."""
    v = (EXTRA_GAPS.get(fkey) or {}).get(j)
    if not v:
        return 0.0
    return random.uniform(*v) if isinstance(v, (tuple, list)) else float(v)


def dragon_extra(j):
    """(예전 이름 유지) 용던고고의 추가 대기."""
    return extra_gap("dragon", j)
ITEM_SWIPE_DIST    = 250   # 아이템정리 클릭3: 누른 채 위로 쓸어올리는 거리(px) — 클라이언트 창 안에 있어야 함
FIX_CLICKS         = 8     # 🩹 복구 — 슬롯당 좌표 8개 (안 쓰는 칸은 비워두면 건너뜀)
FIX_SLOTS          = 16    # 🩹 복구 — 슬롯 16개
FIX_GAP_MIN        = 0.30  # 🩹 복구 — 좌표 간 간격(초). 손으로 3초 안에 하는 작업이라 빠르게
FIX_GAP_MAX        = 0.60
TJ_CLICKS          = 3     # TJ성공!! 슬롯당 좌표 수
TJ_MIN             = 0.81  # TJ성공!! 좌표 간 클릭 간격(초) — 10~20% 완화(0.7~1.2 → 0.77~1.44)
TJ_MAX             = 1.51
TJ_SLOT_MIN        = 0.7   # TJ성공!! 슬롯 간 간격(초) — 0.7~2.3 랜덤
TJ_SLOT_MAX        = 2.3
ITEM_SWIPE_COUNT   = 1     # 같은 자리에서 쓸어올리기 반복 횟수
SCHED_INTERVAL     = 2.5
PASS_SLOTS         = 16
PASS_CLICKS        = 9
PASS_INNER_MIN     = 2.9   # 패스권 좌표(클릭) 간 간격 — 씹힘 방지로 또 1초 더 늘림
PASS_INNER_MAX     = 3.2
PASS_SLOT_MIN      = 2.0
PASS_SLOT_MAX      = 8.0
PASS_LABELS        = [f"클릭{j+1}" for j in range(PASS_CLICKS)]
DUNGEON_INTERVAL = 2.0 # 클릭 사이 간격(초)
SEQ_SLOTS      = 16    # 연속 클릭 슬롯 수 (고정)
SEQ_MIN        = 0.37  # 절전해제·절전모드 슬롯간 최소 간격(초) — 30% 단축(0.53→0.37)
SEQ_MAX        = 0.81  # 절전해제·절전모드 슬롯간 최대 간격(초) — 30% 단축(1.15→0.81)
WDOFF_SLOTS    = 16    # 주말던전 끄기 슬롯 수 (연속클릭과 동일 구조)
WDOFF_MIN      = 0.48  # 주말던전 끄기 슬롯간 최소 간격(초)
WDOFF_MAX      = 0.96
DC_SLOTS       = 16    # 일반던전충전 슬롯 수 (고정)
DC_MIN         = 1.0   # 좌표(슬롯) 간 간격(초) — 1~16 슬롯 사이 랜덤
DC_MAX         = 2.5
DC_TAPS_MIN    = 7     # 한 좌표당 연속 클릭 횟수(최소)
DC_TAPS_MAX    = 9     # 한 좌표당 연속 클릭 횟수(최대)
DC_BURST_MIN   = 1.0   # 한 좌표의 7~9회 클릭을 이 시간(초) 안에 모두 실행
DC_BURST_MAX   = 2.0
FISH_SLOTS     = 16    # 낚시녹임 슬롯 수 (인형탐험과 동일 구조)
FISH_CLICKS    = 19    # 낚시녹임 좌표 수 (2026-08-19 맨 앞에 하나 추가)
CIRCUS_SLOTS   = 16    # 서커스이벤트 슬롯 수 (낚시녹임과 동일 구조)
CIRCUS_CLICKS  = 9     # 서커스이벤트 좌표 수 (9번은 8번을 따라감)
CIRCUS2_SLOTS  = 16    # 서커스 이벤트실행 슬롯 수
CIRCUS2_CLICKS = 4     # 서커스 이벤트실행 좌표 수
CIRCUS3_SLOTS  = 16    # 서커스 이벤트퀘스트 슬롯 수
CIRCUS3_CLICKS = 3     # 서커스 이벤트퀘스트 좌표 수
# 클릭 대신 '마우스 휠 올리기'를 할 자리 (던전키: {0부터 센 클릭번호})
WHEEL_UP_INDICES = {"circus": {4}}     # 서커스이벤트 클릭5 = 휠 위로
WHEEL_UP_NOTCH  = 3    # 한 번에 굴릴 칸 수
WHEEL_UP_TIMES  = 3    # 몇 번 굴릴지
DOLL_SLOTS     = 16    # 인형 탐험 슬롯 수
DOLL_CLICKS    = 18    # 각 슬롯 좌표(클릭) 수
DOLL_MIN       = 2.0   # 슬롯 안 좌표 간 클릭 간격(초) — 2~3초 (1·2·3번 모두)
DOLL_MAX       = 3.0
DOLL_LEAD_MIN  = 0.5   # 슬롯의 '첫 클릭 전' 여유(바로 클릭하지 않음) — 0.5~1초
DOLL_LEAD_MAX  = 1.0
DOLL_SLOT_MIN  = 2.0   # 슬롯 간 간격(초) — 2~4초 랜덤
DOLL_SLOT_MAX  = 4.0
# 씹힘 방지용 추가 좌표간 간격 (사냥·전체실행·인형탐험 제외 전 기능)
# 2026-08-05: 너무 빠른 느낌이라 전체 10~20% 완화 (0.9~1.6 → 0.99~1.92)
EXTRA_GAP_MIN  = 1.04
EXTRA_GAP_MAX  = 2.02

DEFAULT_CFG = {
    "lineagem":    None,
    "game_start":  None,
    "multiplay":   None,
    "profile_btn": None,
    "google_acc":  None,
    "confirm_btn": None,
    "profile_target_id": "",
    "potion_area_rel": None,
    "scroll_area_rel": None,
    "check_area_rel": None,             # F11 때 확인할 경고 영역 (01번 클라 기준 [x,y,w,h])            # 물약색 확인 영역 (01번 클라 기준 상대 [x,y,w,h])
    "profile_id_area": None,
    "profile_reveal_btn": None,
    "char_btns":   [],
    "click_slots": [[None, None]] * CLICK_SLOTS,
    "hunt_slots":  [{"name": "미등록", "coords": [None] * HUNT_CLICKS}
                    for _ in range(HUNT_SLOTS)],
    "mail_slots":  [{"name": "미등록", "coords": [None] * MAIL_CLICKS}
                    for _ in range(MAIL_SLOTS)],
    "window_positions": [],
    "dungeon_slots": [{"name": "미등록", "coords": [None] * DUNGEON_CLICKS}
                      for _ in range(DUNGEON_SLOTS)],
    "past_slots":   [{"name": "미등록", "coords": [None] * PAST_CLICKS}
                     for _ in range(PAST_SLOTS)],
    "sched_slots":  [{"name": "미등록", "coords": [None] * SCHED_CLICKS}
                     for _ in range(SCHED_SLOTS)],
    "item_slots":   None,               # 아이템정리 — 처음 로드 때 스케줄 슬롯을 복사해 생성
    "item_hotkey":  None,               # 아이템정리 실행 단축키 (가상키 코드)
    "item_on":      False,              # 아이템정리 단축키 활성화 상태 (재시작 유지)
    "dollchk_slots": None,              # 인형확인용 — 처음 로드 때 변신확인용 복사
    "relic_slots":   None,              # 성물확인용 — 처음 로드 때 변신확인용 복사
    "coupon_slots":  None,              # 쿠폰등록 — 16슬롯 × 좌표9 (변신확인용 방식)
    "coupon_text":   "",                # 쿠폰등록 클릭5에서 붙여넣을 글
    "market_slots":  None,              # 거래소검색 — 16슬롯 × 좌표9 (쿠폰등록 방식)
    "dragon_slots":  None,              # 용던고고!!! — 16슬롯 × 좌표10 (스케줄과 같은 구조)
    "knight_slots":  None,              # 던전끝! 흑기사!! — 16슬롯 × 좌표5
    "dark_ui":       True,              # 어두운 화면 (눈 보호)
    "market_text":   "",                # 거래소검색에서 붙여넣을 글
    "eventshop_slots": None,            # 이벤트상점 — 16슬롯 × 좌표3 (변신확인용 방식)
    "fix_slots":     [{"name": "미등록", "coords": [None] * FIX_CLICKS}
                      for _ in range(FIX_SLOTS)],   # 🩹 복구 (그림 확인 필수)
    "tj_slots":      None,              # TJ성공!! — 16슬롯 × 좌표3 (인형탐험식 실행)
    "pass_slots":   [{"name": "미등록", "coords": [None]*PASS_CLICKS} for _ in range(PASS_SLOTS)],
    "seq_slots":    [None]*SEQ_SLOTS,   # 연속 클릭 좌표 (각 [x,y] 또는 None)
    "seq_hotkey":   None,               # 연속 클릭 실행 단축키 (가상키 코드)
    "seq_on":       False,              # 연속 클릭 단축키 활성화 상태 (재시작 유지)
    "seq_min":      SEQ_MIN,
    "seq_max":      SEQ_MAX,
    "slp_slots":    [None]*SEQ_SLOTS,   # 절전모드 좌표 (연속클릭과 동일 구조)
    "slp_hotkey":   0x7B,               # 기본 F12
    "slp_on":       True,               # 기본 ON
    "slp_min":      SEQ_MIN,
    "slp_max":      SEQ_MAX,
    "wdoff_slots":  [None]*WDOFF_SLOTS, # 주말던전 끄기 좌표 (각 [x,y] 또는 None)
    "wdoff_hotkey": None,
    "wdoff_on":     False,
    "wdoff_min":    WDOFF_MIN,
    "wdoff_max":    WDOFF_MAX,
    "dc_slots":     [None]*DC_SLOTS,    # 일반던전충전 좌표 (각 [x,y] 또는 None)
    "dc_hotkey":    None,               # 일반던전충전 실행 단축키 (가상키 코드)
    "dc_on":        False,              # 일반던전충전 단축키 활성화 상태 (재시작 유지)
    "dc_min":       DC_MIN,
    "dc_max":       DC_MAX,
    "doll_slots":   [{"name": "미등록", "coords": [None]*DOLL_CLICKS}
                     for _ in range(DOLL_SLOTS)],   # 인형 탐험 (16슬롯 × 18좌표)
    "fish_slots":   [{"name": "미등록", "coords": [None]*FISH_CLICKS}
                     for _ in range(FISH_SLOTS)],   # 낚시녹임 (16슬롯 × 18좌표)
    "circus_slots": [{"name": "미등록", "coords": [None]*CIRCUS_CLICKS}
                     for _ in range(CIRCUS_SLOTS)], # 서커스이벤트 (16슬롯 × 8좌표)
    "circus2_slots": [{"name": "미등록", "coords": [None]*CIRCUS2_CLICKS}
                      for _ in range(CIRCUS2_SLOTS)],  # 서커스 이벤트실행 (16슬롯 × 4좌표)
    "circus3_slots": [{"name": "미등록", "coords": [None]*CIRCUS3_CLICKS}
                      for _ in range(CIRCUS3_SLOTS)],  # 서커스 이벤트퀘스트 (16슬롯 × 3좌표)
    # 아이템 리롤(새로고침 매크로)
    "reroll_refresh_btn": None,   # 새로고침 버튼 좌표 [x,y]
    "reroll_confirm_btn": None,   # 발견 시 자동으로 누를 확인 버튼 좌표 [x,y]
    "reroll_item_area":   None,   # 아이템 이미지 캡처 영역 {x,y,w,h}
    "reroll_threshold":   0.90,   # 일치 판정 유사도(0~1)
    "reroll_wait":        1.0,    # 새로고침 후 대기(초)
    "reroll_targets":     [],     # [{enabled: bool} × 4], 이미지는 reroll_templates/target_N.png
}

LABELS = {
    "lineagem":    "리니지M 버튼 (좌측)",
    "game_start":  "게임 실행 버튼",
    "multiplay":   "멀티플레이 버튼",
    "profile_btn":    "프로필 버튼 (우상단)",
    "google_acc":     "구글 계정 (프로필 클릭 후)",
    "confirm_btn":    "확인 버튼 (계정전환 팝업)",
    "profile_reveal_btn": "아이디 표시 클릭 (확인 전)",
}


def load_accounts():
    try:
        with open(ACCOUNTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return [{"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""} for _ in range(20)]


def load_local():
    """머신별 설정(local_config.json) 읽기 — 없으면 빈 dict."""
    try:
        with open(LOCAL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_local(data):
    try:
        with open(LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _apply_local(cfg):
    """머신별 키를 로컬 파일 값으로 덮어씀. 로컬에 없고 coords.json에 값이 있으면 로컬로 1회 이관."""
    local = load_local()
    changed = False
    for k in LOCAL_KEYS:
        if k in local:
            cfg[k] = local[k]                 # 이 컴퓨터 값 우선
        elif cfg.get(k):
            local[k] = cfg[k]; changed = True  # 기존 coords.json 값 → 로컬로 이관(최초 1회)
    # 인형탐험 슬롯 ON/OFF는 머신별 — 로컬 값이 있으면 덮어쓰고, 없으면 현재 값을 로컬로 이관(최초 1회)
    slots = cfg.get("doll_slots", [])
    de = local.get(DOLL_ENABLED_KEY)
    if isinstance(de, list):
        for i, h in enumerate(slots):
            if i < len(de):
                h["enabled"] = bool(de[i])
    elif slots:
        local[DOLL_ENABLED_KEY] = [bool(h.get("enabled", True)) for h in slots]; changed = True
    if changed:
        save_local(local)
    return cfg

def save_accounts(data):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_cfg():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CFG)
        cfg.update(data)
        # char_btns
        normalized = []
        for item in cfg.get("char_btns", []):
            if isinstance(item, dict) and item.get("btn"):
                normalized.append(item["btn"])
            elif isinstance(item, list):
                normalized.append(item)
        cfg["char_btns"] = normalized
        # click_slots (5번 슬롯=idx4 은 3개 좌표)
        slots, norm = cfg.get("click_slots", []), []
        for i, s in enumerate(slots):
            size = 3 if i == 4 else 2
            if isinstance(s, list) and len(s) >= 2 and isinstance(s[0], (list, type(None))):
                while len(s) < size: s.append(None)
                norm.append(s[:size])
            else:
                norm.append([None] * size)
        while len(norm) < CLICK_SLOTS:
            i = len(norm)
            norm.append([None, None, None] if i == 4 else [None, None])
        cfg["click_slots"] = norm[:CLICK_SLOTS]
        # hunt_slots
        hunt, nh = cfg.get("hunt_slots", []), []
        for h in hunt:
            if isinstance(h, dict):
                c = h.get("coords", [None] * HUNT_CLICKS)
                while len(c) < HUNT_CLICKS: c.append(None)
                entry = dict(h)  # 모든 키 보존 (assigned_window 등)
                entry["name"] = h.get("name", "미등록")
                entry["coords"] = c[:HUNT_CLICKS]
                nh.append(entry)
            else:
                nh.append({"name": "미등록", "coords": [None] * HUNT_CLICKS})
        while len(nh) < HUNT_SLOTS:
            nh.append({"name": "미등록", "coords": [None] * HUNT_CLICKS})
        cfg["hunt_slots"] = nh[:HUNT_SLOTS]
        # mail_slots (6 clicks: 기존 5개짜리는 끝에 None 추가)
        ml, nm = cfg.get("mail_slots", []), []
        for m in ml:
            if isinstance(m, dict):
                c = m.get("coords", [None] * MAIL_CLICKS)
                while len(c) < MAIL_CLICKS: c.append(None)
                nm.append({"name": m.get("name", "미등록"), "coords": c[:MAIL_CLICKS]})
            else:
                nm.append({"name": "미등록", "coords": [None] * MAIL_CLICKS})
        while len(nm) < MAIL_SLOTS:
            nm.append({"name": "미등록", "coords": [None] * MAIL_CLICKS})
        cfg["mail_slots"] = nm[:MAIL_SLOTS]
        # past_slots (3 clicks: 기존 2개짜리는 앞에 None 삽입)
        pl, np2 = cfg.get("past_slots", []), []
        for p in pl:
            if isinstance(p, dict):
                c = p.get("coords", [None] * PAST_CLICKS)
                if len(c) == 2:  # 구버전 → 앞에 None 삽입
                    c = [None] + c
                while len(c) < PAST_CLICKS: c.append(None)
                np2.append({"name": p.get("name", "미등록"), "coords": c[:PAST_CLICKS]})
            else:
                np2.append({"name": "미등록", "coords": [None] * PAST_CLICKS})
        while len(np2) < PAST_SLOTS:
            np2.append({"name": "미등록", "coords": [None] * PAST_CLICKS})
        cfg["past_slots"] = np2[:PAST_SLOTS]
        # sched_slots (3 clicks: 기존 2개짜리는 앞에 None 삽입)
        sl, ns = cfg.get("sched_slots", []), []
        for s in sl:
            if isinstance(s, dict):
                c = s.get("coords", [None] * SCHED_CLICKS)
                if len(c) == 2:  # 구버전 → 앞에 None 삽입
                    c = [None] + c
                while len(c) < SCHED_CLICKS: c.append(None)
                ns.append({"name": s.get("name", "미등록"), "coords": c[:SCHED_CLICKS]})
            else:
                ns.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
        while len(ns) < SCHED_SLOTS:
            ns.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
        cfg["sched_slots"] = ns[:SCHED_SLOTS]
        # item_slots (아이템정리) — 스케줄과 동일 구조. 처음 생기면 스케줄 슬롯을 그대로 복사
        import copy as _cp
        il = cfg.get("item_slots")
        if not il:
            cfg["item_slots"] = _cp.deepcopy(cfg["sched_slots"])
        else:
            ni = []
            for s in il:
                if isinstance(s, dict):
                    c = s.get("coords", [None] * SCHED_CLICKS)
                    while len(c) < SCHED_CLICKS: c.append(None)
                    ni.append({"name": s.get("name", "미등록"), "coords": c[:SCHED_CLICKS]})
                else:
                    ni.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
            while len(ni) < SCHED_SLOTS:
                ni.append({"name": "미등록", "coords": [None] * SCHED_CLICKS})
            cfg["item_slots"] = ni[:SCHED_SLOTS]
        ps = cfg.get("pass_slots", [])
        while len(ps) < PASS_SLOTS:
            ps.append({"name": "미등록", "coords": [None]*PASS_CLICKS})
        for s in ps:
            c = s.get("coords", [])
            while len(c) < PASS_CLICKS: c.append(None)
            s["coords"] = c[:PASS_CLICKS]
        cfg["pass_slots"] = ps[:PASS_SLOTS]
        # seq_slots (연속 클릭 좌표 16개 고정)
        sq = cfg.get("seq_slots", [])
        if not isinstance(sq, list):
            sq = []
        while len(sq) < SEQ_SLOTS:
            sq.append(None)
        cfg["seq_slots"] = sq[:SEQ_SLOTS]
        # slp_slots (절전모드 — 연속클릭과 동일 구조)
        sl = cfg.get("slp_slots", [])
        if not isinstance(sl, list):
            sl = []
        while len(sl) < SEQ_SLOTS:
            sl.append(None)
        cfg["slp_slots"] = sl[:SEQ_SLOTS]
        # dungeon_slots (변신확인용 — 좌표 5개로 패딩, 예전 3개짜리 호환)
        dgs = cfg.get("dungeon_slots", [])
        for s in dgs:
            if isinstance(s, dict):
                c = s.get("coords", [])
                while len(c) < DUNGEON_CLICKS:
                    c.append(None)
                s["coords"] = c[:DUNGEON_CLICKS]
        # 인형확인용/성물확인용 — 변신확인용과 동일 구조, 처음 생기면 그대로 복사
        import copy as _cp2
        for _k2 in ("dollchk_slots", "relic_slots"):
            l2 = cfg.get(_k2)
            if not l2:
                cfg[_k2] = _cp2.deepcopy(cfg.get("dungeon_slots", []))
            else:
                n2 = []
                for s in l2:
                    if isinstance(s, dict):
                        c = s.get("coords", [None] * DUNGEON_CLICKS)
                        while len(c) < DUNGEON_CLICKS: c.append(None)
                        n2.append({"name": s.get("name", "미등록"), "coords": c[:DUNGEON_CLICKS]})
                    else:
                        n2.append({"name": "미등록", "coords": [None] * DUNGEON_CLICKS})
                while len(n2) < 16:
                    n2.append({"name": "미등록", "coords": [None] * DUNGEON_CLICKS})
                cfg[_k2] = n2[:16]
        # coupon_slots(쿠폰등록 ×9)·eventshop_slots(이벤트상점 ×3) — 16슬롯 정규화
        # knight_slots (던전끝! 흑기사!! 16슬롯 × 5좌표, 슬롯별 ON/OFF)
        kl, nkl = cfg.get("knight_slots") or [], []
        for s_ in kl:
            if isinstance(s_, dict):
                c = s_.get("coords", [None] * KNIGHT_CLICKS)
                while len(c) < KNIGHT_CLICKS: c.append(None)
                nkl.append({"name": s_.get("name", "미등록"), "coords": c[:KNIGHT_CLICKS],
                            "enabled": s_.get("enabled", True)})
            else:
                nkl.append({"name": "미등록", "coords": [None] * KNIGHT_CLICKS, "enabled": True})
        while len(nkl) < 16:
            nkl.append({"name": "미등록", "coords": [None] * KNIGHT_CLICKS, "enabled": True})
        cfg["knight_slots"] = nkl[:16]
        # dragon_slots (용던고고!!! 16슬롯 × 10좌표, 슬롯별 ON/OFF)
        dl, ndl = cfg.get("dragon_slots") or [], []
        for s_ in dl:
            if isinstance(s_, dict):
                c = s_.get("coords", [None] * DRAGON_CLICKS)
                while len(c) < DRAGON_CLICKS: c.append(None)
                ndl.append({"name": s_.get("name", "미등록"), "coords": c[:DRAGON_CLICKS],
                            "enabled": s_.get("enabled", True)})
            else:
                ndl.append({"name": "미등록", "coords": [None] * DRAGON_CLICKS, "enabled": True})
        while len(ndl) < 16:
            ndl.append({"name": "미등록", "coords": [None] * DRAGON_CLICKS, "enabled": True})
        cfg["dragon_slots"] = ndl[:16]
        for _k3, _n3 in (("coupon_slots", COUPON_CLICKS), ("market_slots", MARKET_CLICKS),
                         ("eventshop_slots", EVENTSHOP_CLICKS)):
            nc = []
            for s in (cfg.get(_k3) or []):
                if isinstance(s, dict):
                    c = s.get("coords", [None] * _n3)
                    while len(c) < _n3: c.append(None)
                    # 칸별 간격(gap_list)·붙임 자리(paste_list)는 그대로 살려둔다
                    _e = {k: v for k, v in s.items() if k in ("gap_list", "paste_list")}
                    nc.append({"name": s.get("name", "미등록"), "coords": c[:_n3], **_e})
                else:
                    nc.append({"name": "미등록", "coords": [None] * _n3})
            while len(nc) < 16:
                nc.append({"name": "미등록", "coords": [None] * _n3})
            cfg[_k3] = nc[:16]
        # tj_slots (TJ성공!!) — 16슬롯 × 좌표 3
        nt = []
        for s in (cfg.get("tj_slots") or []):
            if isinstance(s, dict):
                c = s.get("coords", [None] * TJ_CLICKS)
                while len(c) < TJ_CLICKS: c.append(None)
                nt.append({"name": s.get("name", "미등록"), "coords": c[:TJ_CLICKS]})
            else:
                nt.append({"name": "미등록", "coords": [None] * TJ_CLICKS})
        while len(nt) < 16:
            nt.append({"name": "미등록", "coords": [None] * TJ_CLICKS})
        cfg["tj_slots"] = nt[:16]
        # wdoff_slots (주말던전 끄기 좌표 16개 고정)
        wq = cfg.get("wdoff_slots", [])
        if not isinstance(wq, list):
            wq = []
        while len(wq) < WDOFF_SLOTS:
            wq.append(None)
        cfg["wdoff_slots"] = wq[:WDOFF_SLOTS]
        # dc_slots (일반던전충전 좌표 16개 고정)
        dq = cfg.get("dc_slots", [])
        if not isinstance(dq, list):
            dq = []
        while len(dq) < DC_SLOTS:
            dq.append(None)
        cfg["dc_slots"] = dq[:DC_SLOTS]
        # fish_slots (낚시녹임 16슬롯 × 19좌표)
        # (2026-08-19) 맨 앞에 좌표 하나를 새로 넣는다 — 기존 좌표는 한 칸씩 밀려
        # 클릭1→클릭2 … 순서는 그대로. 컴퓨터마다 한 번만 밀도록 표시를 남긴다.
        if not cfg.get("_fish_front_v2"):
            for s_ in (cfg.get("fish_slots") or []):
                if not isinstance(s_, dict):
                    continue
                for fld in ("coords", "gap_list", "wheel_list", "paste_list"):
                    v = s_.get(fld)
                    if isinstance(v, list) and len(v) < FISH_CLICKS:
                        v.insert(0, None if fld != "wheel_list" else 0)
            cfg["_fish_front_v2"] = True
        fl, nfl = cfg.get("fish_slots", []), []
        for s_ in fl:
            c = s_.get("coords", [None]*FISH_CLICKS) if isinstance(s_, dict) else [None]*FISH_CLICKS
            while len(c) < FISH_CLICKS: c.append(None)
            _e = {k: v for k, v in (s_.items() if isinstance(s_, dict) else [])
                  if k in ("gap_list", "wheel_list", "paste_list")}
            nfl.append({"name": s_.get("name", "미등록") if isinstance(s_, dict) else "미등록",
                        "coords": c[:FISH_CLICKS],
                        "enabled": s_.get("enabled", True) if isinstance(s_, dict) else True,
                        **_e})
        while len(nfl) < FISH_SLOTS:
            nfl.append({"name": "미등록", "coords": [None]*FISH_CLICKS, "enabled": True})
        cfg["fish_slots"] = nfl[:FISH_SLOTS]
        # circus_slots (서커스이벤트 16슬롯 × 8좌표)
        cl, ncl = cfg.get("circus_slots", []), []
        for s_ in cl:
            c = s_.get("coords", [None]*CIRCUS_CLICKS) if isinstance(s_, dict) else [None]*CIRCUS_CLICKS
            while len(c) < CIRCUS_CLICKS: c.append(None)
            _g = (s_.get("gap_list") or []) if isinstance(s_, dict) else []
            _w = (s_.get("wheel_list") or []) if isinstance(s_, dict) else []
            while len(_g) < CIRCUS_CLICKS: _g.append(None)
            while len(_w) < CIRCUS_CLICKS: _w.append(0)
            c = c[:CIRCUS_CLICKS]
            if len(c) >= 9 and c[7]:
                c[8] = list(c[7])        # 9번은 8번과 같은 자리 (자동 동기화)
            ncl.append({"name": s_.get("name", "미등록") if isinstance(s_, dict) else "미등록",
                        "coords": c,
                        "gap_list": _g[:CIRCUS_CLICKS],      # 칸마다 다음 좌표까지 기다릴 초
                        "wheel_list": _w[:CIRCUS_CLICKS],    # 칸마다 휠 굴릴 칸수 (0=클릭)
                        "enabled": s_.get("enabled", True) if isinstance(s_, dict) else True})
        while len(ncl) < CIRCUS_SLOTS:
            ncl.append({"name": "미등록", "coords": [None]*CIRCUS_CLICKS,
                        "gap_list": [None]*CIRCUS_CLICKS,
                        "wheel_list": [0]*CIRCUS_CLICKS, "enabled": True})
        cfg["circus_slots"] = ncl[:CIRCUS_SLOTS]
        # circus3_slots (서커스 이벤트퀘스트 16슬롯 × 3좌표)
        c3l, nc3 = cfg.get("circus3_slots", []), []
        for s_ in c3l:
            c = s_.get("coords", [None]*CIRCUS3_CLICKS) if isinstance(s_, dict) else [None]*CIRCUS3_CLICKS
            while len(c) < CIRCUS3_CLICKS: c.append(None)
            _g = (s_.get("gap_list") or []) if isinstance(s_, dict) else []
            _w = (s_.get("wheel_list") or []) if isinstance(s_, dict) else []
            while len(_g) < CIRCUS3_CLICKS: _g.append(None)
            while len(_w) < CIRCUS3_CLICKS: _w.append(0)
            nc3.append({"name": s_.get("name", "미등록") if isinstance(s_, dict) else "미등록",
                        "coords": c[:CIRCUS3_CLICKS],
                        "gap_list": _g[:CIRCUS3_CLICKS],
                        "wheel_list": _w[:CIRCUS3_CLICKS],
                        "enabled": s_.get("enabled", True) if isinstance(s_, dict) else True})
        while len(nc3) < CIRCUS3_SLOTS:
            nc3.append({"name": "미등록", "coords": [None]*CIRCUS3_CLICKS,
                        "gap_list": [None]*CIRCUS3_CLICKS,
                        "wheel_list": [0]*CIRCUS3_CLICKS, "enabled": True})
        cfg["circus3_slots"] = nc3[:CIRCUS3_SLOTS]
        # circus2_slots (서커스 이벤트실행 16슬롯 × 4좌표)
        c2l, nc2 = cfg.get("circus2_slots", []), []
        for s_ in c2l:
            c = s_.get("coords", [None]*CIRCUS2_CLICKS) if isinstance(s_, dict) else [None]*CIRCUS2_CLICKS
            while len(c) < CIRCUS2_CLICKS: c.append(None)
            _g = (s_.get("gap_list") or []) if isinstance(s_, dict) else []
            _w = (s_.get("wheel_list") or []) if isinstance(s_, dict) else []
            while len(_g) < CIRCUS2_CLICKS: _g.append(None)
            while len(_w) < CIRCUS2_CLICKS: _w.append(0)
            nc2.append({"name": s_.get("name", "미등록") if isinstance(s_, dict) else "미등록",
                        "coords": c[:CIRCUS2_CLICKS],
                        "gap_list": _g[:CIRCUS2_CLICKS],
                        "wheel_list": _w[:CIRCUS2_CLICKS],
                        "enabled": s_.get("enabled", True) if isinstance(s_, dict) else True})
        while len(nc2) < CIRCUS2_SLOTS:
            nc2.append({"name": "미등록", "coords": [None]*CIRCUS2_CLICKS,
                        "gap_list": [None]*CIRCUS2_CLICKS,
                        "wheel_list": [0]*CIRCUS2_CLICKS, "enabled": True})
        cfg["circus2_slots"] = nc2[:CIRCUS2_SLOTS]
        # doll_slots (인형 탐험 16슬롯 × 18좌표)
        dl, ndl = cfg.get("doll_slots", []), []
        for s in dl:
            c = s.get("coords", [None]*DOLL_CLICKS) if isinstance(s, dict) else [None]*DOLL_CLICKS
            while len(c) < DOLL_CLICKS: c.append(None)
            ndl.append({"name": s.get("name", "미등록") if isinstance(s, dict) else "미등록",
                        "coords": c[:DOLL_CLICKS],
                        "enabled": s.get("enabled", True) if isinstance(s, dict) else True})
        while len(ndl) < DOLL_SLOTS:
            ndl.append({"name": "미등록", "coords": [None]*DOLL_CLICKS, "enabled": True})
        cfg["doll_slots"] = ndl[:DOLL_SLOTS]
        return _apply_local(cfg)
    return _apply_local(dict(DEFAULT_CFG))

def save_cfg(cfg):
    # 머신별 키는 로컬 파일에만 저장하고, 공유되는 coords.json에서는 제외
    local = load_local()
    for k in LOCAL_KEYS:
        if k in cfg:
            local[k] = cfg[k]
    slots = cfg.get("doll_slots", [])
    if slots:
        local[DOLL_ENABLED_KEY] = [bool(h.get("enabled", True)) for h in slots]
    save_local(local)
    shared = {k: v for k, v in cfg.items() if k not in LOCAL_KEYS}
    # 인형탐험 ON/OFF는 머신별 — 공유 파일에는 기존 값을 그대로 두어 이 PC 상태가 깃에 새지 않게 한다
    if slots:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                prev = json.load(f).get("doll_slots", [])
        except Exception:
            prev = []
        shared["doll_slots"] = [
            {**h, "enabled": prev[i].get("enabled", True)
                   if i < len(prev) and isinstance(prev[i], dict) else True}
            for i, h in enumerate(slots)]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(shared, f, ensure_ascii=False, indent=2)

def find_purple():
    for w in gw.getAllWindows():
        if "purple" in w.title.lower() or "lineage" in w.title.lower():
            return w
    return None


# 클릭은 '마우스 분리' 방식 하나만 쓴다 (2026-08-21 사용자 지시).
#   precise_click.install() 이 pyautogui.click 을 SendInput 으로 바꿔놨다 —
#   [이동+누름+뗌]이 한 번에 전송돼 사용자가 마우스를 움직여도 끼어들지 못하고
#   클릭은 항상 지정 좌표에 찍힌다. 게임도 진짜 입력으로 받는다.
#   (창에 메시지만 보내는 '가상 클릭'은 씹혀서 없앴다 — 다시 넣지 말 것)
NO_CURSOR_CLICK = False


CLICK_LOG = os.path.join(LOCAL_DATA, "click_log.txt")   # 클릭이 어느 창에 갔는지 기록

# ── 이미지로 찾아 클릭 (2026-08-26 사용자 요청) ────────────────────────
#   좌표 대신 '그림'을 찾아 누른다. 못 찾으면 그 슬롯은 거기서 끝낸다.
IMG_DIR   = os.path.join(BASE, "click_templates")
IMG_MATCH = 0.60          # 이 정도 닮으면 같은 그림으로 본다 (2026-08-27 사용자 지시)
IMG_TRIES = 3             # 못 찾으면 1~1.5초 간격으로 몇 번까지 다시 볼지.
                          # 6번은 너무 느렸다 (2026-08-28 사용자 지시로 3번)
PEAK_RATIO = 1.45         # '1등 ÷ 2등' 이 이만큼 크면 점수가 낮아도 찾은 것으로 본다
PEAK_MIN   = 0.40         # 다만 이 점수 밑이면 배수와 무관하게 안 본다
# 흑백(밝기 평준화) 대조 — 색이 달라 보여도 모양이 같으면 잡는다.
# 잡음도 같이 올라가므로(0.37~0.45) 점수·배수를 둘 다 넘어야만 인정한다.
GRAY_MIN   = 0.55
GRAY_RATIO = 1.35
RECLICK_TRIES = 2         # 눌렀는데 창이 안 뜰 때 다시 눌러보는 횟수 (2026-08-28 — 속도)
RECLICK_HOLD = [(0.18, 0.30), (0.35, 0.50), (0.50, 0.70), (0.70, 0.95)]  # 갈수록 길게
# 누른 뒤 '창이 떴나' 보기까지 기다리는 시간 — 점점 길게 준다.
# 마름모가 캐릭터에서 멀면 눌러도 바로 창이 안 뜨고 **걸어가는 시간**이 필요하다
# (2026-08-28 실측: 실패한 두 슬롯은 마름모가 창 왼쪽·위 끝에 있었다 = 먼 거리).
CHECK_TRIES = 2      # 👁 확인만 자리는 짧게 2번만 본다 (0.25~0.45초 간격)
ESC_TIMES   = 2      # 취소할 때 ESC 를 몇 번 누를지 (창이 두 겹이라 두 번, 2026-08-29)
RECLICK_WAIT = [2.0, 3.0]        # 확인까지 2초 → 3초 (전 28초는 너무 느렸다)
DRIFT_MAX  = 40           # 그림이 이만큼(px) 안에서 움직인 건 '같은 것'으로 본다.
                          # 더 멀면 다른 마름모라 겨냥을 옮기지 않는다 (엉뚱한 층 방지)


def grab_patch(fkey, j, coord):
    """그 자리에서 '템플릿과 같은 크기'로 화면을 잘라온다 (배우기용)."""
    try:
        import cv2, numpy as np
        from PIL import ImageGrab
        base = img_path(fkey, j)
        if not os.path.exists(base):
            return None
        t0 = cv2.imdecode(np.fromfile(base, dtype=np.uint8), cv2.IMREAD_COLOR)
        if t0 is None:
            return None
        h, w = t0.shape[:2]
        x, y = int(coord[0]) - w // 2, int(coord[1]) - h // 2
        im = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def check_path(fkey, j):
    """**확인만** 표시 — 그 자리는 누르지 않고 그림이 보이는지만 본다.

    예: 복구 창의 '무료' 글자. 그 자리에 숫자(재화)가 들어가면 그림이 안 맞으므로
    **다음 좌표를 누르지 않고 그 슬롯을 끝낸다** (2026-08-29 사용자 지시)."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}_check.json")


def is_check_only(fkey, j):
    try:
        return os.path.exists(check_path(fkey, j))
    except Exception:
        return False


def set_check_only(fkey, j, on):
    try:
        if on:
            os.makedirs(IMG_DIR, exist_ok=True)
            with open(check_path(fkey, j), "w", encoding="utf-8") as f:
                json.dump({"check_only": True}, f)
        else:
            os.remove(check_path(fkey, j))
    except Exception:
        pass

def no_path(fkey, j):
    """**금지 그림** — 이게 보이면 그 자리를 누르지 않고 ESC 로 취소하고 슬롯을 끝낸다.

    로지텍 매크로처럼 순서대로 누르다가, 재화를 쓰려는 화면이 뜨면 그냥 ESC 를 눌러
    빠져나오는 방식 (2026-08-29 사용자 지시)."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}_no.png")


def has_no_img(fkey, j):
    try:
        return os.path.exists(no_path(fkey, j))
    except Exception:
        return False


def find_no_img(fkey, j, coord):
    """금지 그림이 지금 보이나 — 보이면 (x, y, 점수), 아니면 (None, None, 최고점수)."""
    q = no_path(fkey, j)
    if not os.path.exists(q):
        return None, None, 0.0
    box = search_box(fkey, j, coord)
    return _find_one(fkey, j, coord, q, box)


def press_esc(times=1, gap=(0.18, 0.32)):
    """ESC 를 times 번 누른다 — 열려 있는 창을 닫고 원래 화면으로 빠져나온다.
    복구처럼 창이 두 겹으로 열리는 경우가 있어 기본 두 번을 쓴다 (2026-08-29)."""
    ok = False
    try:
        for i in range(max(1, int(times))):
            if i:
                time.sleep(random.uniform(*gap))
            pyautogui.press("esc")
            ok = True
    except Exception:
        pass
    return ok

def zone_path(fkey, j):
    """성공한 자리들이 모인 구역 (이 컴퓨터 전용 — 창 배치가 다를 수 있으므로)."""
    return os.path.join(IMG_DIR_MINE, f"{fkey}_{j+1:02d}_zone.json")


ZONE_MIN  = 5      # 이만큼 모여야 구역을 쓴다
ZONE_PAD  = 35     # 구역 사방으로 이만큼 여유 (px)
CONFIRM_MIN = 0.70  # 이 점수 밑으로 잡히면 한 번 더 보고 같은 자리인지 확인한다
CONFIRM_PX  = 10    # 그때 이 거리(px) 안이면 '같은 자리'로 본다
ZONE_BONUS = 0.18   # '늘 뜨던 자리' 가까이면 점수에 이만큼 얹어 고른다
ZONE_NEAR  = 60     # 중심에서 이 거리(px) 안이면 '가깝다'
ZONE_OUT_MIN = 0.75  # 구역 **밖**에서 찾을 때는 이 점수를 넘어야만 인정한다.
                     # 구역 밖은 엉뚱한 곳일 확률이 높아 느슨한 판정(배수·흑백)을 쓰지 않는다.
ZONE_KEEP = 40     # 최근 이만큼만 보관


def learn_zone(fkey, j, coord):
    """**창이 실제로 뜬** 자리를 창 왼쪽위 기준으로 모아둔다.

    마름모는 늘 화면의 비슷한 구역에 뜬다 (실측: 창내 x 143~290 · y 73~121).
    그런데 낮은 점수로 **엉뚱한 곳**(예: y=31 의 UI)을 마름모로 보고 눌러 실패한
    일이 있었다 (2026-08-28 망자로 슬롯). 그래서 성공한 자리를 모아 그 구역을
    **먼저** 훑는다. 거기서 못 찾으면 예전처럼 창 전체를 훑으므로 놓치지는 않는다."""
    try:
        rc = client_rect_at(coord[0], coord[1])
        if not rc:
            return
        dx, dy = int(coord[0]) - rc[0], int(coord[1]) - rc[1]
        pts = []
        try:
            with open(zone_path(fkey, j), encoding="utf-8") as f:
                pts = (json.load(f) or {}).get("pts") or []
        except Exception:
            pts = []
        pts.append([dx, dy])
        pts = pts[-ZONE_KEEP:]
        os.makedirs(IMG_DIR_MINE, exist_ok=True)
        with open(zone_path(fkey, j), "w", encoding="utf-8") as f:
            json.dump({"pts": pts}, f)
    except Exception:
        pass


def zone_box(fkey, j, coord):
    """모아둔 성공 자리로 만든 구역 (없거나 표본이 적으면 None)."""
    try:
        with open(zone_path(fkey, j), encoding="utf-8") as f:
            pts = (json.load(f) or {}).get("pts") or []
        if len(pts) < ZONE_MIN:
            return None
        rc = client_rect_at(coord[0], coord[1])
        if not rc:
            return None
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        x0 = max(rc[0], rc[0] + min(xs) - ZONE_PAD)
        y0 = max(rc[1], rc[1] + min(ys) - ZONE_PAD)
        x1 = min(rc[2], rc[0] + max(xs) + ZONE_PAD)
        y1 = min(rc[3], rc[1] + max(ys) + ZONE_PAD)
        if x1 - x0 < 40 or y1 - y0 < 40:
            return None
        return (x0, y0, x1, y1)
    except Exception:
        return None


def learn_img(fkey, j, patch, nm=""):
    """**성공이 확인된** 클릭 자리의 그림을 '이 컴퓨터 전용'으로 모아둔다.

    같은 아이콘도 배경(지형·몹·이펙트)과 날개 애니메이션에 따라 점수가
    0.60~0.96 으로 흔들려서, 한 장으로는 몇 슬롯을 놓친다. 그래서 **실제로 창이
    뜬 것이 확인된 자리**만 골라 여러 장 모아두면 그 컴퓨터에서 점점 잘 잡힌다.
    (2026-08-27 — 컴퓨터마다 화면이 달라 로컬에서 특히 효과가 크다)

    - 이미 비슷한 그림(0.90 이상)이 있으면 넣지 않는다 — 다양한 배경만 모은다.
    - 최대 `IMG_MAX`(4)장. 오른쪽 클릭으로 전부 지울 수 있다."""
    if patch is None:
        return
    try:
        import cv2, numpy as np
        for q in img_list(fkey, j):
            old = cv2.imdecode(np.fromfile(q, dtype=np.uint8), cv2.IMREAD_COLOR)
            if old is None or old.shape != patch.shape:
                continue
            r = cv2.matchTemplate(patch, old, cv2.TM_CCOEFF_NORMED)
            if float(r.max()) >= 0.90:
                return                      # 이미 있는 것과 비슷 — 안 모은다
        n = img_mine_free(fkey, j)
        os.makedirs(IMG_DIR_MINE, exist_ok=True)
        cv2.imencode(".png", patch)[1].tofile(img_mine_path(fkey, j, n))
        click_log(f"{fkey} [{nm}] 좌표{j+1} 성공한 그림을 배웠음 "
                  f"(이 컴퓨터 전용 {img_mine_count(fkey, j)}/{IMG_MAX}장)")
    except Exception:
        pass


def _left_clicks(fkey, slot, j0, nclk):
    """그 슬롯에서 **실제로 누를 좌표가 몇 개 남았나**.
    빈 칸까지 세면 남은 일을 부풀려 계산해 간격을 쓸데없이 줄인다
    (2026-08-27 — 16×10=160 으로 세는 바람에 처음부터 페이스가 걸렸다)."""
    try:
        cl = (slot or {}).get("coords") or []
        return sum(1 for j in range(max(0, j0), nclk)
                   if (j < len(cl) and cl[j]) or has_img(fkey, j))
    except Exception:
        return max(0, nclk - j0)


def find_repo_dir():
    """저장소(Moon-AI) 폴더 찾기 — 컴퓨터마다 위치가 달라도 되도록."""
    home = os.path.expanduser("~")
    cands = [os.path.join(BASE, "Moon-AI"), BASE,
             os.path.join(home, "Moon-AI"),
             os.path.join(home, "Desktop", "Moon-AI"),
             os.path.join(home, "OneDrive", "Desktop", "Moon-AI")]
    for c in cands:
        try:
            if os.path.isdir(os.path.join(c, ".git")):
                return c
        except Exception:
            pass
    return None


def share_diag(fkey, lines, shots=()):
    """**진단 내용만** 저장소 `diag/` 에 올린다 — 메인에서 실시간으로 로컬 상태를 본다.

    사용자 지시(2026-08-28)로 만든 예외 통로다. 올리는 것은 `diag/` 아래 파일뿐이고
    코드·좌표·계정은 **절대 건드리지 않는다** (`git add` 에 diag 경로만 준다).
    실패해도 조용히 넘어간다 — 실행에 영향을 주지 않는다."""
    repo = find_repo_dir()
    if not repo:
        return False
    try:
        import shutil as _sh, socket, subprocess as _sp
        who = "".join(ch for ch in socket.gethostname() if ch.isalnum())[:16] or "pc"
        dd = os.path.join(repo, "diag")
        os.makedirs(dd, exist_ok=True)
        rel = []
        tf = os.path.join(dd, who + "_" + fkey + ".txt")
        with open(tf, "w", encoding="utf-8") as f:
            f.write(NLCH.join(lines))
        rel.append("diag/" + os.path.basename(tf))
        for src, tag in shots:
            if not (src and os.path.exists(src)):
                continue
            dst = os.path.join(dd, who + "_" + fkey + "_" + tag + ".png")
            try:
                _sh.copy2(src, dst)
                rel.append("diag/" + os.path.basename(dst))
            except Exception:
                pass
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        def g(*args, t=60):
            return _sp.run(["git"] + list(args), cwd=repo, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=t, env=env)
        g("add", "--", *rel)
        if not g("diff", "--cached", "--quiet", "--", *rel).returncode:
            return True                     # 바뀐 게 없으면 그냥 끝
        g("commit", "-q", "-m", "진단 공유: " + who + " / " + fkey, "--", *rel)
        g("fetch", "-q", "origin")
        g("rebase", "--autostash", "-q", "origin/main")   # 남의 커밋 위로 얹는다
                                                          # (다른 수정은 잠깐 치웠다 되돌림)
        r = g("push", "-q", "origin", "HEAD:main", t=90)
        ok = (r.returncode == 0)
        click_log("[진단공유] " + ("올림 ✔ " if ok else "실패 ✘ ") +
                  ", ".join(os.path.basename(x) for x in rel) +
                  ("" if ok else " — " + (r.stderr or "")[:120]))
        return ok
    except Exception as e:
        try:
            click_log("[진단공유] 실패 ✘ " + str(e)[:120])
        except Exception:
            pass
        return False


def save_miss_shot(fkey, j, coord):
    """이미지를 못 찾았을 때 '그때 훑은 화면'을 사진으로 남긴다.
    click_templates/_못찾음_<런처>_<좌표>.png — 범위가 맞는지 눈으로 확인용."""
    try:
        from PIL import ImageGrab
        box = search_box(fkey, j, coord)
        os.makedirs(IMG_DIR, exist_ok=True)
        ImageGrab.grab(bbox=box, all_screens=True).save(
            os.path.join(IMG_DIR, f"_못찾음_{fkey}_{j+1:02d}.png"))
    except Exception:
        pass


def img_path(fkey, j):
    """그 런처 · 그 좌표번호에 지정해둔 그림 파일 (좌표번호는 1부터 보여준다).
    이것은 '공용(저장소) 그림' — 업데이트로 모든 컴퓨터에 배포된다."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}.png")


# 컴퓨터마다 해상도·클라 크기·그래픽 설정이 달라 같은 아이콘이 다르게 보인다.
# 그래서 '이 컴퓨터 전용 그림'을 따로 둔다 — 업데이트가 절대 덮어쓰지 않는다.
IMG_DIR_MINE = os.path.join(os.environ.get("LOCALAPPDATA", BASE),
                            "MoonAI", "click_templates")
IMG_MAX = 4            # 한 좌표에 그림 몇 장까지


def img_mine_path(fkey, j, n):
    """이 컴퓨터 전용 그림 (n = 0,1,2,3)."""
    return os.path.join(IMG_DIR_MINE, f"{fkey}_{j+1:02d}_mine{n+1}.png")


def img_list(fkey, j):
    """그 자리에서 찾아볼 그림 전부 — 공용 1장 + 이 컴퓨터 전용 최대 4장.
    실행할 때는 이 중 '가장 잘 맞는 것' 하나를 쓴다."""
    out = []
    try:
        if os.path.exists(img_path(fkey, j)):
            out.append(img_path(fkey, j))
    except Exception:
        pass
    for n in range(IMG_MAX):
        try:
            q = img_mine_path(fkey, j, n)
            if os.path.exists(q):
                out.append(q)
        except Exception:
            pass
    return out


def img_mine_count(fkey, j):
    return sum(1 for n in range(IMG_MAX)
               if os.path.exists(img_mine_path(fkey, j, n)))


def img_mine_free(fkey, j):
    """비어 있는 '이 컴퓨터 전용' 자리 번호 (없으면 마지막을 덮어쓴다)."""
    for n in range(IMG_MAX):
        if not os.path.exists(img_mine_path(fkey, j, n)):
            return n
    return IMG_MAX - 1


PICKS = ["best", "top", "bottom", "left", "right"]
PICK_TXT = {"best": "최고일치", "top": "맨위", "bottom": "맨아래",
            "left": "맨왼쪽", "right": "맨오른쪽"}


def stop_path(fkey):
    """그 런처의 '여기까지만 하고 끝' 좌표번호 (1부터). 없으면 끝까지 간다."""
    return os.path.join(IMG_DIR, f"{fkey}_stopat.json")


def stop_at(fkey):
    try:
        with open(stop_path(fkey), encoding="utf-8") as f:
            v = int((json.load(f) or {}).get("stop_at") or 0)
        return v if v > 0 else 0
    except Exception:
        return 0


def set_stop_at(fkey, v):
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(stop_path(fkey), "w", encoding="utf-8") as f:
        json.dump({"stop_at": int(v)}, f)


def pick_path(fkey, j):
    """같은 그림이 여러 개일 때 어느 것을 누를지 (위/아래 구분용)."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}_pick.json")


def img_pick(fkey, j):
    try:
        with open(pick_path(fkey, j), encoding="utf-8") as f:
            v = (json.load(f) or {}).get("pick")
        return v if v in PICKS else "best"
    except Exception:
        return "best"


def set_img_pick(fkey, j, v):
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(pick_path(fkey, j), "w", encoding="utf-8") as f:
        json.dump({"pick": v}, f)


def thr_path(fkey, j):
    """그 좌표의 '일치 기준' 파일 (작은 그림은 기준을 낮춰야 잡힌다)."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}_thr.json")


def img_thr(fkey, j):
    try:
        with open(thr_path(fkey, j), encoding="utf-8") as f:
            return float((json.load(f) or {}).get("thr") or IMG_MATCH)
    except Exception:
        return IMG_MATCH


def set_img_thr(fkey, j, v):
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(thr_path(fkey, j), "w", encoding="utf-8") as f:
        json.dump({"thr": round(float(v), 2)}, f)


def has_img(fkey, j):
    """그 자리에 찾을 그림을 (공용이든 이 컴퓨터 전용이든) 지정해뒀나."""
    try:
        return bool(img_list(fkey, j))
    except Exception:
        return False


def slot_anchor(slot):
    """그 슬롯이 '어느 클라'인지 알려주는 기준 좌표 — 등록된 첫 좌표.
    (그림만 지정한 자리는 좌표가 없으므로, 같은 슬롯의 다른 좌표로 창을 찾는다)"""
    for c in (slot or {}).get("coords") or []:
        if c:
            return c
    return None


def area_path(fkey, j):
    """그 좌표에서 '그림을 찾을 범위' — 클라 창 왼쪽위 기준으로 저장한다."""
    return os.path.join(IMG_DIR, f"{fkey}_{j+1:02d}_area.json")


def area_is_set(fkey, j):
    """'진짜' 범위가 잡혀 있나 — {"full": true} 는 범위 없음으로 본다."""
    try:
        with open(area_path(fkey, j), encoding="utf-8") as f:
            a = json.load(f) or {}
        if a.get("full") or int(a.get("w") or 0) <= 0 or int(a.get("h") or 0) <= 0:
            return False
        return True
    except Exception:
        return False


def client_rect_at(x, y):
    """그 좌표를 품은 리니지M 창 위치 (없으면 None)."""
    try:
        import precise_click as _pc
        import ctypes, ctypes.wintypes
        h = _pc.game_window_at(int(x), int(y))
        if not h:
            return None
        r = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def search_box(fkey, j, coord):
    """그림을 찾을 화면 영역.
    범위를 지정해뒀으면 그 클라 창 기준으로 같은 자리를 계산해 쓴다
    (16슬롯이 창만 다르고 화면 구성은 같으므로 한 번만 잡으면 전부 적용된다).
    범위가 없으면 그 클라 창 전체, 창도 못 찾으면 좌표 주변 500×500."""
    rc = client_rect_at(coord[0], coord[1])
    try:
        with open(area_path(fkey, j), encoding="utf-8") as f:
            a = json.load(f) or {}
        # {"full": true} = '범위를 쓰지 말고 창 전체' — 잘못 잡아둔 범위를 업데이트로
        # 되돌리기 위한 값이다 (2026-08-28). 크기가 0 이하인 것도 같게 본다.
        if a.get("full") or int(a.get("w") or 0) <= 0 or int(a.get("h") or 0) <= 0:
            return rc if rc else (int(coord[0]) - 250, int(coord[1]) - 250,
                                  int(coord[0]) + 250, int(coord[1]) + 250)
        if rc and all(k in a for k in ("dx", "dy", "w", "h")):
            x0 = rc[0] + int(a["dx"]); y0 = rc[1] + int(a["dy"])
            return (x0, y0, x0 + int(a["w"]), y0 + int(a["h"]))
        if all(k in a for k in ("x", "y", "w", "h")):      # 창을 못 찾으면 절대좌표
            return (int(a["x"]), int(a["y"]),
                    int(a["x"]) + int(a["w"]), int(a["y"]) + int(a["h"]))
    except Exception:
        pass
    if rc:
        return rc
    x, y = int(coord[0]), int(coord[1])
    return (x - 250, y - 250, x + 250, y + 250)


def find_image(fkey, j, coord):
    """지정한 범위 안에서 그림을 찾는다.
    등록된 그림이 여러 장이면 **하나라도 잡히면 잡힌 것**으로 본다
    (컴퓨터마다 아이콘이 달라 보이므로 — 2026-08-27).
    찾으면 (x, y, 일치도), 못 찾으면 (None, None, 최고 일치도)."""
    paths = img_list(fkey, j)
    if not paths:
        return None, None, 0.0
    # 훑을 곳: 지정한 범위 → (못 찾으면) 그 클라 창 전체
    # 범위를 좁게 잡아두면 그림이 그 밖에 떠 있을 때 영영 못 찾는다 —
    # 실제로 로컬에서 175×127 로 잡아둬 계속 놓쳤다 (2026-08-28).
    boxes = []
    # 순서: ① 내가 지정한 범위(📐)  ② 성공했던 자리들이 모인 구역  ③ 창 전체
    # 뒤로 갈수록 '엉뚱한 곳'일 확률이 높아 ②③ 은 엄격하게 본다.
    _ub = search_box(fkey, j, coord) if area_is_set(fkey, j) else None
    if _ub:
        boxes.append(tuple(_ub))
    _zb = zone_box(fkey, j, coord)
    if _zb and tuple(_zb) not in boxes:
        boxes.append(tuple(_zb))
    if not boxes:
        boxes.append(tuple(search_box(fkey, j, coord)))
    try:
        rc = client_rect_at(coord[0], coord[1])
        if rc and tuple(rc) not in boxes:
            boxes.append(tuple(rc))
    except Exception:
        pass
    best = 0.0
    for _bi, _box in enumerate(boxes):
        _strict = _bi > 0        # 첫 상자 밖으로 넓힐수록 엄격하게 (오클릭 방지)
        for _p in paths:
            x, y, sc = _find_one(fkey, j, coord, _p, _box, _strict)
            if x is not None:
                if _bi:
                    click_log(f"{fkey} 좌표{j+1} — 지정 범위 밖에서 찾음 "
                              f"(일치도 {sc:.2f} ≥ {ZONE_OUT_MIN}, 엄격 판정 통과) "
                              f"· 범위(📐)를 조금 넓혀두면 더 잘 잡힙니다")
                return x, y, sc
            best = max(best, sc)
    return None, None, best


def _pick_near_zone(fkey, j, res, thr, mx, ml, tw, th, box):
    """기준을 넘는 후보들 중 **늘 뜨던 자리에 가까운 것**을 고른다.

    점수 1등만 믿으면 배경 무늬를 누르는 사고가 난다. 성공했던 자리(`*_zone.json`)의
    중심에서 가까울수록 점수에 가산점을 준다 — 자료가 적으면 그냥 1등을 쓴다.
    (2026-08-28 사용자 신고: 7번·10번이 엉뚱한 곳을 눌렀다)"""
    try:
        import cv2, numpy as np
        with open(zone_path(fkey, j), encoding="utf-8") as f:
            pts = (json.load(f) or {}).get("pts") or []
        if len(pts) < 3:
            return None, None, None
        rc = client_rect_at(box[0] + tw, box[1] + th)
        if not rc:
            return None, None, None
        cx = sum(q[0] for q in pts) / len(pts)      # 늘 뜨던 자리의 중심 (창 기준)
        cy = sum(q[1] for q in pts) / len(pts)
        ys, xs = np.where(res >= min(thr, mx))
        if len(xs) == 0:
            return None, None, None
        cands = []
        for y0, x0 in zip(ys.tolist(), xs.tolist()):
            v = float(res[y0, x0])
            for c in cands:
                if abs(c[0] - x0) < tw and abs(c[1] - y0) < th:
                    if v > c[2]:
                        c[0], c[1], c[2] = x0, y0, v
                    break
            else:
                cands.append([x0, y0, v])
        if len(cands) < 2:
            return None, None, None
        best = None
        for x0, y0, v in cands:
            ax = box[0] + x0 + tw // 2 - rc[0]      # 창 기준 좌표
            ay = box[1] + y0 + th // 2 - rc[1]
            d = ((ax - cx) ** 2 + (ay - cy) ** 2) ** 0.5
            adj = v + (ZONE_BONUS if d <= ZONE_NEAR else 0.0)
            if best is None or adj > best[0]:
                best = (adj, x0, y0, v, d)
        _adj, x0, y0, v, d = best
        if (x0, y0) != (ml[0], ml[1]):
            click_log(f"{fkey} 좌표{j+1} — 점수 1등({mx:.2f}) 대신 "
                      f"늘 뜨던 자리에 가까운 것({v:.2f}, {d:.0f}px)을 고름")
        return (int(box[0] + x0 + tw // 2), int(box[1] + y0 + th // 2), float(v))
    except Exception:
        return None, None, None

def _find_one(fkey, j, coord, path, box=None, strict=False):
    """그림 한 장으로, 지정한 화면 영역에서 찾아본다.
    strict=True 면 '늘 뜨던 구역 밖'이라는 뜻 — 점수를 높게 요구하고
    느슨한 판정(배수·흑백·윤곽선)을 쓰지 않는다 (오클릭 방지, 2026-08-28)."""
    if not os.path.exists(path):
        return None, None, 0.0
    try:
        import cv2, numpy as np
        from PIL import ImageGrab
        if box is None:
            box = search_box(fkey, j, coord)
        shot = ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        big = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        # cv2.imread 는 한글이 든 경로를 못 읽는다 (윈도 사용자 이름이 한글이면 전부 실패) —
        # 바이트로 읽어 디코드한다 (2026-08-27).
        try:
            tpl = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            tpl = cv2.imread(path, cv2.IMREAD_COLOR)
        if tpl is None or big.shape[0] < tpl.shape[0] or big.shape[1] < tpl.shape[1]:
            return None, None, 0.0
        res = cv2.matchTemplate(big, tpl, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, ml = cv2.minMaxLoc(res)
        thr = img_thr(fkey, j)
        if strict:
            thr = max(thr, ZONE_OUT_MIN)
        th, tw = tpl.shape[0], tpl.shape[1]
        # ── 점수만 보지 않고 '나머지보다 얼마나 튀는가'도 본다 (2026-08-27 실측) ──
        # 같은 아이콘도 배경(지형·몹·이펙트)에 따라 0.60~0.96 으로 크게 흔들려서
        # 절대 점수만으로는 자를 수가 없다. 반면 '1등 ÷ 2등' 은 확실히 갈린다:
        #   아이콘 있을 때 2.23배 · 없을 때 1.00~1.20배 (16클라 실측)
        if (not strict) and mx < thr and mx >= PEAK_MIN:
            try:
                _r2 = res.copy()
                _y0, _x0 = max(0, ml[1] - th), max(0, ml[0] - tw)
                _r2[_y0:ml[1] + th, _x0:ml[0] + tw] = -1     # 1등 주변을 지우고
                _a2, _m2, _b2, _c2 = cv2.minMaxLoc(_r2)      # 2등을 본다
                if _m2 > 0 and (mx / _m2) >= PEAK_RATIO:
                    thr = mx        # 확실히 튀는 하나 — 찾은 것으로 인정
            except Exception:
                pass
        if mx < thr:
            # 컴퓨터마다 해상도·클라 크기가 달라 그림이 조금 크거나 작게 보인다.
            # 0.8~1.25배로 늘였다 줄였다 하며 다시 찾는다 (2026-08-27 — 로컬 성공률).
            for _f in (0.90, 1.10, 0.80, 1.20, 0.85, 1.05, 1.15, 0.95, 1.25):
                w2, h2 = int(round(tw * _f)), int(round(th * _f))
                if (w2 < 6 or h2 < 6 or big.shape[0] < h2 or big.shape[1] < w2):
                    continue
                t2 = cv2.resize(tpl, (w2, h2),
                                interpolation=(cv2.INTER_AREA if _f < 1
                                               else cv2.INTER_CUBIC))
                r2 = cv2.matchTemplate(big, t2, cv2.TM_CCOEFF_NORMED)
                _n3, m3, _l3, l3 = cv2.minMaxLoc(r2)
                if m3 > mx:
                    res, mx, ml, tw, th = r2, m3, l3, w2, h2
                if mx >= thr:
                    break
        if (not strict) and mx < thr:
            # 색으로 못 찾으면 '흑백(밝기 평준화)'으로 한 번 더 본다 (2026-08-27).
            # 배경이 밝거나 어두워 색 점수가 깎일 때 이쪽이 더 잘 잡힌다
            # (실측: 놓쳤던 화면 색 0.606 → 흑백 0.658).
            try:
                _ge = cv2.equalizeHist(cv2.cvtColor(big, cv2.COLOR_BGR2GRAY))
                _gt = cv2.equalizeHist(cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY))
                _rg = cv2.matchTemplate(_ge, _gt, cv2.TM_CCOEFF_NORMED)
                _ng, _mg, _lg, _pg = cv2.minMaxLoc(_rg)
                if _mg >= GRAY_MIN:
                    _r3 = _rg.copy()
                    _y3, _x3 = max(0, _pg[1] - th), max(0, _pg[0] - tw)
                    _r3[_y3:_pg[1] + th, _x3:_pg[0] + tw] = -1
                    _a3, _m3, _b3, _c3 = cv2.minMaxLoc(_r3)
                    if _m3 > 0 and (_mg / _m3) >= GRAY_RATIO:
                        res, mx, ml, thr = _rg, _mg, _pg, _mg   # 흑백 결과로 인정
            except Exception:
                pass
        if (not strict) and mx < thr:
            # 그래도 못 찾으면 '윤곽선(모양)'으로 마지막 한 번 (2026-08-27).
            # 아이콘은 같은데 배경(지형·몹·이펙트)이 달라 점수가 떨어지는 경우 대응.
            try:
                g1 = cv2.Canny(cv2.cvtColor(big, cv2.COLOR_BGR2GRAY), 60, 160)
                g2 = cv2.Canny(cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY), 60, 160)
                res2 = cv2.matchTemplate(g1, g2, cv2.TM_CCOEFF_NORMED)
                _n2, mx2, _l2, ml2 = cv2.minMaxLoc(res2)
                if mx2 >= thr:
                    res, mx, ml = res2, mx2, ml2      # 윤곽선 결과를 쓴다
                    th, tw = tpl.shape[0], tpl.shape[1]
                else:
                    return None, None, float(max(mx, mx2))
            except Exception:
                return None, None, float(mx)
        pick = img_pick(fkey, j)
        if pick == "best":
            # 점수가 가장 높은 것 하나만 믿으면, 배경 무늬가 진짜보다 높게 나올 때
            # 엉뚱한 곳을 누른다 (2026-08-28 주이 슬롯: 맨 땅을 0.61 로 눌렀는데
            # 같은 화면에 진짜 마름모가 0.77 로 있었다).
            # → 기준을 넘는 후보를 다 모아 **늘 뜨던 자리에 가까운 것**을 고른다.
            _bx, _by, _bs = _pick_near_zone(fkey, j, res, thr, mx, ml, tw, th, box)
            if _bx is not None:
                return _bx, _by, _bs
            return (int(box[0] + ml[0] + tw // 2),
                    int(box[1] + ml[1] + th // 2), float(mx))
        # 같은 그림이 여럿일 때 — 기준을 넘는 것을 다 모아 겹치는 것끼리 묶고
        # 위/아래/왼/오 중 원하는 것을 고른다 (위로 갔다가 다시 내려가는 것 방지)
        ys, xs = np.where(res >= thr)
        cands = []
        for y0, x0 in zip(ys.tolist(), xs.tolist()):
            v = float(res[y0, x0])
            for c in cands:                      # 가까운 것은 같은 대상으로 본다
                if abs(c[0] - x0) < tw // 2 and abs(c[1] - y0) < th // 2:
                    if v > c[2]:
                        c[0], c[1], c[2] = x0, y0, v
                    break
            else:
                cands.append([x0, y0, v])
        if not cands:
            return None, None, float(mx)
        if   pick == "top":    c = min(cands, key=lambda c: c[1])
        elif pick == "bottom": c = max(cands, key=lambda c: c[1])
        elif pick == "left":   c = min(cands, key=lambda c: c[0])
        else:                  c = max(cands, key=lambda c: c[0])
        return (int(box[0] + c[0] + tw // 2),
                int(box[1] + c[1] + th // 2), float(c[2]))
    except Exception:
        return None, None, 0.0



def click_target(x, y):
    """그 좌표를 받아줄 창 이름 — 리니지M 창이 없으면 ('', False)."""
    try:
        import precise_click as _pc
        h = _pc.game_window_at(x, y)
        if h:
            return _pc.window_title(h), True
        import ctypes, ctypes.wintypes
        pt = ctypes.wintypes.POINT(int(x), int(y))
        h2 = ctypes.windll.user32.WindowFromPoint(pt)
        return (_pc.window_title(h2) if h2 else ""), False
    except Exception:
        return "", False


def click_log(line):
    """클릭 기록 한 줄 남기기 (LOCALAPPDATA/MoonAI/click_log.txt)."""
    try:
        os.makedirs(LOCAL_DATA, exist_ok=True)
        with open(CLICK_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%m-%d %H:%M:%S ") + line + "\n")
    except Exception:
        pass


# ── 어두운 화면 (눈 보호) — 2026-08-22 사용자 지시 ────────────────────
DARK_BG   = "#23272e"      # 창 배경
DARK_BG2  = "#2b3038"      # 입력칸·리스트 배경
DARK_FG   = "#e6e6e6"      # 기본 글씨
DARK_DIM  = "#9aa4b0"      # 흐린 설명 글씨
DARK_LINE = "#d6dde5"      # 구분선·박스 테두리 (어두운 배경에서 보이게 밝은 회색)


def _lum(w, color):
    """색의 밝기(0~1). 실패하면 None."""
    try:
        r, g, b = w.winfo_rgb(color)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 65535.0
    except Exception:
        return None


def apply_dark(w, on=True):
    """창 하나를 어둡게(또는 원래대로) 바꾼다.
    색을 일부러 지정해둔 버튼(빨강·초록 등)은 건드리지 않고,
    흰 배경 / 어두운 글씨만 바꿔서 대비를 지킨다."""
    try:
        cls = w.winfo_class()
    except Exception:
        return
    try:
        if cls in ("Frame", "Labelframe", "Toplevel", "Tk", "Canvas", "Panedwindow"):
            bg = str(w.cget("bg")) if "bg" in w.keys() else ""
            l = _lum(w, bg) if bg else None
            # 얇은 띠(구분선)는 어둡게 만들지 말고 '밝게' 살려야 칸이 구분된다
            thin = False
            try:
                hh = int(w.cget("height") or 0); ww = int(w.cget("width") or 0)
                thin = cls == "Frame" and ((0 < hh <= 3) or (0 < ww <= 3))
            except Exception:
                pass
            if thin:
                w.configure(bg=DARK_LINE if on else "#ddd")
                return
            if on:
                if l is None or l > 0.55:          # 밝은 배경만 어둡게
                    w.configure(bg=DARK_BG)
            elif str(w.cget("bg")) in (DARK_BG, DARK_BG2):
                w.configure(bg="SystemButtonFace")
            if on:
                try:                       # 박스 테두리를 밝게 그려 칸을 구분한다
                    if cls == "Labelframe" or int(w.cget("bd") or 0) > 0:
                        w.configure(highlightbackground=DARK_LINE, highlightcolor=DARK_LINE,
                                    highlightthickness=1)
                except Exception:
                    pass
            else:
                try: w.configure(highlightthickness=0)
                except Exception: pass
            if cls == "Labelframe" and on:
                try: w.configure(fg=DARK_FG)
                except Exception: pass
        elif cls in ("Label", "Checkbutton", "Radiobutton", "Message"):
            bg = str(w.cget("bg")); fg = str(w.cget("fg"))
            lb, lf = _lum(w, bg), _lum(w, fg)
            if on:
                if lb is None or lb > 0.55:
                    w.configure(bg=DARK_BG)
                    if lf is not None and lf < 0.45:      # 어두운 글씨 → 밝게
                        w.configure(fg=DARK_DIM if lf > 0.25 else DARK_FG)
                if cls in ("Checkbutton", "Radiobutton"):
                    try: w.configure(selectcolor=DARK_BG2, activebackground=DARK_BG,
                                     activeforeground=DARK_FG)
                    except Exception: pass
        elif cls in ("Entry", "Text", "Listbox", "Spinbox"):
            if on:
                try: w.configure(bg=DARK_BG2, fg=DARK_FG, insertbackground=DARK_FG)
                except Exception: pass
        elif cls == "Button":
            bg = str(w.cget("bg")); lb = _lum(w, bg)
            if on and (lb is None or lb > 0.80):   # 색 없는(흰) 버튼만
                try: w.configure(bg="#3a4149", fg=DARK_FG, activebackground="#4a525b",
                                 activeforeground=DARK_FG)
                except Exception: pass
        elif cls == "Menubutton":
            if on:
                try: w.configure(bg="#3a4149", fg=DARK_FG,
                                 activebackground="#4a525b", activeforeground=DARK_FG)
                except Exception: pass
    except Exception:
        pass
    for c in w.winfo_children():
        apply_dark(c, on)


def move_at(x, y):
    """마우스를 '올려놓기'만 하는 자리 — 그 좌표로 커서를 옮긴다.
    (SendInput 이라 사용자가 마우스를 움직여도 이 이동이 밀리지 않는다)"""
    pyautogui.moveTo(x, y)
    return "cursor"


def click_hold(x, y, ms=None):
    """사람처럼 '꾹 눌렀다 떼는' 클릭 (기본 70~130ms).
    [누름+뗌]이 0초 간격으로 나가면 게임이 무시하는 경우가 있다 —
    게임 화면 안의 아이콘·오브젝트는 이 방식이라야 반응한다. (2026-08-27)"""
    hold = (ms if ms is not None else random.uniform(0.07, 0.13))
    try:
        pyautogui.moveTo(int(x), int(y))
        time.sleep(random.uniform(0.05, 0.12))
        pyautogui.mouseDown(int(x), int(y))
        time.sleep(hold)
        pyautogui.mouseUp(int(x), int(y))
        return "꾹클릭"
    except Exception:
        pyautogui.click(int(x), int(y))
        return "클릭"


def click_at(x, y):
    """좌표 클릭 — [이동+누름+뗌]을 SendInput 으로 한 번에 보낸다.
    실행 중 사용자가 마우스를 움직여도 그 사이에 끼어들지 못해
    클릭은 항상 지정 좌표에 찍힌다 (precise_click.install 이 걸어둔 것)."""
    pyautogui.click(x, y)
    return "cursor"


def close_purple_popup_if_visible(cfg, status_fn=None):
    """Purple 팝업 감지 후 체크박스 → X 버튼 클릭으로 닫기.
    감지: X버튼 좌표의 픽셀이 등록된 색상과 일치할 때만 클릭.
    """
    from PIL import ImageGrab
    chk  = cfg.get("purple_popup_checkbox")   # [x, y]
    cls  = cfg.get("purple_popup_close")       # [x, y]
    det  = cfg.get("purple_popup_detect")      # [x, y]
    col  = cfg.get("purple_popup_color")       # [r, g, b]
    tol  = 30  # 색상 허용 오차

    if not (cls and det and col):
        return  # 미등록

    try:
        shot = ImageGrab.grab(all_screens=False)
        px   = shot.getpixel((det[0], det[1]))
        r, g, b = px[0], px[1], px[2]
        if (abs(r - col[0]) > tol or
            abs(g - col[1]) > tol or
            abs(b - col[2]) > tol):
            return  # 팝업 없음
    except Exception:
        return

    if status_fn:
        status_fn("⚠ 퍼플 팝업 감지 — 자동으로 닫는 중...")
    if chk:
        pyautogui.click(*chk)
        time.sleep(0.4)
    pyautogui.click(*cls)
    time.sleep(0.3)
    if status_fn:
        status_fn("✔ 퍼플 팝업 닫기 완료")


class WindowSizeLock:
    """폴링으로 창 크기 고정. 최소화만 허용, 최대화/리사이즈 모두 차단."""
    SWP_NOZORDER   = 0x0004
    SWP_NOACTIVATE = 0x0010

    def __init__(self):
        self._locks   = {}   # hwnd -> (x, y, w, h)
        self._thread  = None
        self._running = False

    def lock_all(self, hwnds):
        self.unlock()
        for hwnd in hwnds:
            try:
                r = win32gui.GetWindowRect(hwnd)
                self._locks[hwnd] = (r[0], r[1], r[2]-r[0], r[3]-r[1])
            except Exception:
                pass
        if self._locks:
            self._running = True
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()
        return self._locks

    def unlock(self):
        self._running = False
        self._locks = {}

    def is_locked(self):
        return self._running and bool(self._locks)

    def pause(self, seconds):
        """일시 정지 후 자동 재개"""
        self._paused_until = time.time() + seconds

    def _watch(self):
        user32 = ctypes.windll.user32
        self._paused_until = 0
        while self._running:
            if time.time() < self._paused_until:
                time.sleep(0.3); continue
            for hwnd, rect in list(self._locks.items()):
                try:
                    if not win32gui.IsWindow(hwnd):
                        self._locks.pop(hwnd, None); continue
                    if user32.IsIconic(hwnd):
                        continue
                    cr = win32gui.GetWindowRect(hwnd)
                    cw, ch = cr[2]-cr[0], cr[3]-cr[1]
                    if cw != rect[2] or ch != rect[3]:
                        user32.SetWindowPos(hwnd, 0, rect[0], rect[1],
                                            rect[2], rect[3],
                                            self.SWP_NOZORDER | self.SWP_NOACTIVATE)
                except Exception:
                    pass
            time.sleep(0.3)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("리니지M 자동 실행")
        try:
            # Moon-AI 공통 아이콘 (default= → 모든 서브창에도 적용)
            self.iconbitmap(default=os.path.join(BASE, "moon.ico"))
        except Exception:
            pass
        sh = self.winfo_screenheight()
        self.geometry(f"2117x1010+76+75")   # 콘텐츠에 맞춘 높이 (작업표시줄 위로)
        self.resizable(True, True)
        self.bind("<Map>", self._on_main_map)
        self.bind("<Unmap>", self._on_main_unmap)   # 런처 최소화 시 클로드도 같이 내림
        # (FocusIn→앞으로 올리기 바인딩 제거 — 다른 창이 실행되며 최소화될 때
        #  윈도우가 포커스만 넘겨줘도 런처가 튀어나오던 문제. 직접 클릭 시에만 올라옴)
        self.after(150, self._fit_main_height)
        # 유휴(2분 무조작) 시 메인런처 자동 최소화 — 조작 감지용
        self._last_activity = time.time()
        self.bind_all("<Button>", self._mark_activity, add="+")
        self.bind_all("<Key>",    self._mark_activity, add="+")
        self.bind("<FocusIn>",    self._mark_activity, add="+")   # 작업표시줄로 올려도 유휴 리셋
        self.bind("<Button-1>",   self._raise_on_click, add="+")  # 런처 아무 곳이나 클릭 → 앞으로
        # 런처↔클로드 최소화 커플링은 시작 20초 후부터 (워치독 시작 최소화 제외)
        self._unmap_couple_ok = False
        self.after(20000, lambda: setattr(self, "_unmap_couple_ok", True))

        self.cfg = load_cfg()
        self._accounts = load_accounts()
        while len(self._accounts) < 20:
            self._accounts.append({"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""})
        self._acc_type_vars = [tk.StringVar(value=a.get("type", "구글")) for a in self._accounts]
        self._acc_vars = [
            [tk.StringVar(value=a.get(f"f{j+1}", "")) for j in range(5)]
            for a in self._accounts
        ]
        self._acc_type_btns = [None] * 16   # 계정 관리 창 OptionMenu 참조 (창 재오픈 대비)
        self._reg_target   = None
        self._busy_task      = None   # 현재 실행 중인 개별 작업 이름 (동시 실행 방지)
        self._stop_flag      = False
        self._running        = False  # 전체 자동실행 중 여부
        self._click_stop     = False
        self._hunt_stop      = False
        self._sched_any_stop = False
        self._mail_on      = bool(self.cfg.get("mail_on", False))   # 우편 스케줄 — 기본 꺼짐(사용자 요청), 토글로 켜면 유지
        self._mail_triggered_date = None
        # (2026-08-13) '오늘 이미 돌렸다'를 파일에 남긴다 —
        # 런처를 재시작해도 기억이 지워지지 않아 하루 두 번 도는 사고를 막는다
        self._past_triggered_date = self._past_ran_load()
        self._purple_triggered_date = None
        self._win_lock     = WindowSizeLock()
        self._hp_stop      = False
        self._seq_on       = bool(self.cfg.get("seq_on", False))
        self._slp_on       = bool(self.cfg.get("slp_on", True))
        self._slp_running  = False
        self._seq_running  = False
        self._wdoff_on     = bool(self.cfg.get("wdoff_on", False))
        self._wdoff_running = False
        self._dc_on        = bool(self.cfg.get("dc_on", False))
        self._dc_running   = False
        self._doll_stop    = False
        self._item_on      = bool(self.cfg.get("item_on", False))
        self._item_stop    = False
        self._dollchk_stop = False
        self._fish_stop = False
        self._circus_stop = False
        self._circus2_stop = False
        self._circus3_stop = False
        self._relic_stop   = False
        self._coupon_stop  = False
        self._market_stop  = False
        self._dragon_stop  = False
        self._knight_stop  = False
        self._eventshop_stop = False
        self._tj_stop      = False
        self._task_queue   = []   # 연속으로 누른 실행/재측정 순차 실행 대기열
        self._build_ui()
        # 메인런처 고정 위치 — 드래그해도 자동 저장하지 않음(모든 컴퓨터 동일 위치 유지).
        # 잠깐 옮겨 쓰다가 [📍 제자리] 버튼으로 복귀. 고정값 변경은 클로드에게 요청.
        _pos = self.cfg.get("main_win_fixed") or self.cfg.get("main_win_pos") or [80, 120]
        try:
            self.geometry(f"+{int(_pos[0])}+{int(_pos[1])}")
        except Exception:
            pass
        # 떠있는 클라 메모 4개 — 완전 분리 실행. 실패해도 런처엔 영향 없음.
        try:
            self._memo_wins = {}
            self.after(3000, self._memo_tick)
        except Exception:
            pass
        self.after(600, self._align_tj_to_dc)   # TJ성공!! 좌측 끝 = 일반던전충전 좌측 끝
        self._sync_sched_click1()   # 스케줄 클릭1 = 과거섬 클릭1 (시작 시 1회 동기화)
        self.after(4000, self._sync_prestart_tasks)   # 스케줄 10분 전 자동시작 작업 동기화
        self.after(1000, self._mail_scheduler_tick)
        self.after(1000, self._past_scheduler_tick)
        self.after(30000, self._subwin_autoclose_tick)   # 서브창 3분 무조작 자동닫기
        self.after(2000, self._queue_tick)               # 실행 대기열 순차 처리
        self.after(3000, self._auto_back_tick)           # 다른 창을 클릭하면 런처를 바로 맨 뒤로
        # 퍼플 광고창('소식')은 마우스 없이 창만 닫는다 (픽셀 감지 방식은 폐기)
        self.after(4000, self._purple_ad_tick)
        # 포커스를 잃는 순간에도 즉시 반응 (0.15초 확인보다 더 빠름)
        self.bind("<FocusOut>", self._auto_back_check, add="+")
        self.after(8000,  self._ensure_time_sync_task)   # 🕐 시계 맞춤 예약 (매주 수 05:00)
        self.after(20000, self._island_repeat_tick)      # 섬/던전 슬롯 반복(2h N회) 관리
        # (자동 업데이트는 사용자 요청으로 비활성 — 업데이트는 🔄 버튼으로 수동 실행)
        # (2026-08-07 사용자 지시) 새벽 4시 퍼플 자동 확인·전환 사용 안 함 — 틱 미실행
        threading.Thread(target=self._seq_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._slp_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._dc_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._wdoff_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._item_hotkey_loop, daemon=True).start()
        threading.Thread(target=self._popup_guard_loop, daemon=True).start()
        threading.Thread(target=self._claude_attention_loop, daemon=True).start()
        # 작업 중에는 클로드를 강제로 내리지 않는다(예전 시작 버스트 제거).
        # 대신 클로드 앱을 화면 가운데로 유지 (아이디 영역 등 안 가리게, 사용자가 옮기면 중단)
        self.after(2000, self._center_claude_tick)
        self.after(3000, self._claude_minimize_tick)
        self.after(20000, self._idle_minimize_tick)         # 2분 무조작 시 메인런처 자동 최소화
        self.after(30000, self._claude_idle_minimize_tick)  # 3분 무입력 시 클로드 앱 최소화
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._set_sleep_prevention(False)
        self.destroy()

    def _auto_update_tick(self):
        """5분마다 GitHub 확인 — 새 커밋이 있으면 한가할 때 자동으로 업데이트 실행."""
        def _check():
            try:
                repo = None
                for c in (os.path.join(BASE, "Moon-AI"), BASE):
                    if os.path.isdir(os.path.join(c, ".git")):
                        repo = c; break
                if not repo:
                    return
                import subprocess
                NOW = 0x08000000  # CREATE_NO_WINDOW
                subprocess.run(["git", "fetch", "origin"], cwd=repo, capture_output=True,
                               text=True, creationflags=NOW, timeout=60)
                a = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                                   text=True, creationflags=NOW).stdout.strip()
                b = subprocess.run(["git", "rev-parse", "origin/main"], cwd=repo, capture_output=True,
                                   text=True, creationflags=NOW).stdout.strip()
                if a and b and a != b:
                    if self._is_busy() or self._system_idle_ms() < 120000:
                        # 작업 중이거나 사용자가 쓰는 중 → 다음 체크 때 재시도
                        self.after(0, lambda: self.status.set(
                            "⬇ GitHub 새 버전 감지 — 한가해지면 자동 업데이트합니다"))
                    else:
                        self.after(0, lambda: self.status.set("⬇ GitHub 새 버전 감지 — 자동 업데이트 시작"))
                        self.after(0, self._run_updater)
            except Exception:
                pass
        threading.Thread(target=_check, daemon=True).start()
        self.after(300000, self._auto_update_tick)   # 5분 간격

    # ── 좌표 저장 / 복구 (이 컴퓨터 전용 스냅샷) ──────────────────────
    # 런처 폴더(BASE)에 있는 설정 파일들
    _COORD_FILES = ("coords.json", "island_coords.json", "local_config.json",
                    "accounts.json", "daya_regions.json")
    # %LOCALAPPDATA%\MoonAI 에 있는 설정 파일들 (다야 OCR 영역·프로필 인식영역)
    _LOCAL_SAVE_FILES = ("daya_regions.json", "profile_ref_region.json")
    # 좌표 개수 검증 대상 (나머지는 있으면 그대로 저장/복구)
    _COORD_CRITICAL = ("coords.json", "island_coords.json")

    @staticmethod
    def _local_data_dir():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def _coord_save_dir():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI", "usersave")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def _count_coords_in(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            n = 0
            for v in data.values():
                if not isinstance(v, list):
                    continue
                for s in v:
                    if isinstance(s, dict):
                        n += sum(1 for c in s.get("coords", []) if c)
                    elif isinstance(s, list) and any(s):
                        n += sum(1 for c in s if c)
            return n
        except Exception:
            return 0

    def _coord_save_info(self):
        """저장본 시각·좌표 수 — 없으면 None."""
        d = self._coord_save_dir()
        meta = os.path.join(d, "info.json")
        try:
            with open(meta, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _refresh_coord_save_lbl(self):
        lb = getattr(self, "_coord_save_lbl", None)
        if not lb or not lb.winfo_exists():
            return
        info = self._coord_save_info()
        lb.config(text=(f"저장 {info['time'][5:16]}" if info else "저장본 없음"))

    def _save_coord_snapshot(self):
        """지금 좌표를 이 컴퓨터에 저장 — 나중에 [♻ 좌표복구]로 이 시점으로 되돌림.
        빈/깨진 좌표는 저장하지 않는다 (복구본이 오염되면 복구 자체가 무의미)."""
        import datetime, shutil
        try:
            # 1) 저장 전 검증 — 좌표 파일은 실제로 좌표가 들어 있어야 함
            #    (설정 파일들: 다야 OCR 영역·계정·머신설정도 함께 저장)
            checked = []
            for f in self._COORD_FILES:
                src = os.path.join(BASE, f)
                if not os.path.exists(src):
                    continue
                cnt = self._count_coords_in(src)
                if f in self._COORD_CRITICAL and cnt <= 0:
                    messagebox.showwarning(
                        "좌표 저장", f"{f} 에 등록된 좌표가 없습니다.\n"
                        f"비어 있는 상태를 저장하면 복구가 무의미해져서 저장을 중단합니다.")
                    return
                checked.append((f, src, cnt))
            for f in self._LOCAL_SAVE_FILES:      # %LOCALAPPDATA%\MoonAI 쪽 설정
                src = os.path.join(self._local_data_dir(), f)
                if os.path.exists(src):
                    checked.append(("local__" + f, src, 0))
            if not checked:
                messagebox.showwarning("좌표 저장", "저장할 좌표 파일이 없습니다.")
                return
            d = self._coord_save_dir()
            total = 0
            # 2) 임시로 쓴 뒤 교체 — 저장 도중 꺼져도 기존 저장본이 깨지지 않게
            for f, src, cnt in checked:
                dst = os.path.join(d, f)
                tmp = dst + ".tmp"
                shutil.copy2(src, tmp)
                with open(tmp, "rb") as fa, open(src, "rb") as fb:
                    if fa.read() != fb.read():
                        raise IOError(f"{f} 저장 검증 실패")
                os.replace(tmp, dst)
                total += cnt
            # 3) 세대 보관 — 최근 20개까지 따로 남겨둠(저장본이 손상돼도 되살릴 수 있게)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            gdir = os.path.join(d, "history")
            os.makedirs(gdir, exist_ok=True)
            for f, src, cnt in checked:
                shutil.copy2(src, os.path.join(gdir, f"{stamp}_{f}"))
            gfns = sorted(os.listdir(gdir))
            for fn in gfns[:-40]:
                try: os.remove(os.path.join(gdir, fn))
                except Exception: pass
            info = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "coords": total, "files": [f for f, _, _ in checked],
                    "n_files": len(checked)}
            with open(os.path.join(d, "info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            self._refresh_coord_save_lbl()
            self.status.set(f"💾 저장 완료 — {info['time']} (좌표 {total}개 / 파일 {len(checked)}개: "
                            f"좌표·다야OCR영역·계정·머신설정). 문제 생기면 [♻ 좌표복구]")
        except Exception as e:
            messagebox.showerror("좌표 저장", f"저장 실패: {e}\n\n다시 시도해주세요.")

    def _restore_coord_snapshot(self):
        """마지막으로 저장한 좌표로 되돌리고 런처를 재시작한다."""
        import shutil, subprocess as _sp, datetime, sys
        info = self._coord_save_info()
        if not info:
            messagebox.showinfo("좌표 복구", "저장된 좌표가 없습니다.\n먼저 [💾 좌표저장]을 눌러주세요.")
            return
        if self._is_busy():
            self.status.set(f"⚠ '{self._busy_label()}' 실행 중 — 끝난 뒤 복구하세요"); return
        if not messagebox.askyesno(
                "좌표 복구",
                f"저장 시점: {info['time']}  (좌표 {info.get('coords', 0)}개 / "
                f"파일 {info.get('n_files', len(info.get('files', [])))}개)\n\n"
                f"좌표 + 다야 OCR 영역 + 계정·머신설정을 이 시점으로 되돌립니다.\n"
                f"(되돌리기 직전 현재 좌표도 자동 백업됩니다)\n\n진행할까요?", default="no"):
            return
        d = self._coord_save_dir()
        # 0) 저장본 유효성 확인 — 깨졌으면 history의 최근 정상본으로 자동 대체
        #    (좌표 파일만 개수 검증, 설정 파일은 있으면 그대로 복구)
        sources = {}
        gdir = os.path.join(d, "history")
        gfns = sorted(os.listdir(gdir), reverse=True) if os.path.isdir(gdir) else []
        _all = list(self._COORD_FILES) + ["local__" + f for f in self._LOCAL_SAVE_FILES]
        for f in _all:
            need_coords = f in self._COORD_CRITICAL
            cand = os.path.join(d, f)
            if os.path.exists(cand) and (not need_coords or self._count_coords_in(cand) > 0):
                sources[f] = cand
                continue
            for fn in gfns:                      # 세대 보관본에서 최근 정상본 찾기
                if fn.endswith(f"_{f}"):
                    p2 = os.path.join(gdir, fn)
                    if not need_coords or self._count_coords_in(p2) > 0:
                        sources[f] = p2
                        break
        if not sources:
            messagebox.showerror("좌표 복구",
                "저장본이 손상되어 복구할 수 없습니다.\n"
                "클로드에게 '좌표 복구해줘'라고 요청하세요\n"
                "(%LOCALAPPDATA%\\MoonAI\\backups 의 자동 백업으로 되살릴 수 있습니다).")
            return
        try:
            # 1) 되돌리기 직전 현재 상태도 백업 (복구를 취소하고 싶을 때 대비)
            bdir = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI", "backups")
            os.makedirs(bdir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            for f in self._COORD_FILES:
                cur = os.path.join(BASE, f)
                if os.path.exists(cur):
                    try: shutil.copy2(cur, os.path.join(bdir, f"{stamp}_before_restore_{f}"))
                    except Exception: pass
            for f in self._LOCAL_SAVE_FILES:
                cur = os.path.join(self._local_data_dir(), f)
                if os.path.exists(cur):
                    try: shutil.copy2(cur, os.path.join(bdir, f"{stamp}_before_restore_local_{f}"))
                    except Exception: pass
            # 2) 실행 중인 섬/던전·OCR 종료 (옛 좌표를 다시 저장해버리는 것 방지)
            try:
                _sp.Popen(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'lineagem_island|lineagem_ocr|lineagem_dungeon' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                    creationflags=0x08000000)
            except Exception:
                pass
            time.sleep(1.0)
            # 3) 복사 — 실패하면 최대 3번까지 재시도 (파일 점유 대비), 복사 후 검증
            done, failed = [], []
            for f, src in sources.items():
                # local__ 접두사가 붙은 것은 %LOCALAPPDATA%\MoonAI 로 되돌린다
                if f.startswith("local__"):
                    dst = os.path.join(self._local_data_dir(), f[len("local__"):])
                else:
                    dst = os.path.join(BASE, f)
                ok = False
                for _try in range(3):
                    try:
                        shutil.copy2(src, dst)
                        with open(src, "rb") as fa, open(dst, "rb") as fb:
                            ok = fa.read() == fb.read()
                    except Exception:
                        ok = False
                    if ok:
                        break
                    time.sleep(0.7)
                (done if ok else failed).append(f)
            if failed:
                messagebox.showerror("좌표 복구",
                    f"복구 실패: {', '.join(failed)}\n\n"
                    f"런처를 종료한 뒤 다시 시도하거나, 클로드에게 '좌표 복구해줘'라고 요청하세요.")
                if not done:
                    return
            self.status.set(f"♻ 좌표 복구 완료 ({len(done)}개 파일) — 런처를 다시 시작합니다...")
            # 4) 재시작 — 워치독 실행 후 살아나지 않으면 직접 실행까지 폴백
            _exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(_exe):
                _exe = sys.executable
            _lp = os.path.join(BASE, "lineagem_launcher.py")
            _sp.Popen(["powershell", "-NoProfile", "-Command",
                       "Start-Sleep -Seconds 2; Start-ScheduledTask 'LineageM_Watchdog'; "
                       "Start-Sleep -Seconds 8; "
                       "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                       "Where-Object { $_.CommandLine -match 'lineagem_launcher' }; "
                       f"if (-not $p) {{ Start-Process '{_exe}' -ArgumentList '{_lp}' }}"],
                      creationflags=0x08000000)
            self.after(600, lambda: os._exit(0))
        except Exception as e:
            messagebox.showerror("좌표 복구",
                f"복구 중 오류: {e}\n\n클로드에게 '좌표 복구해줘'라고 요청하세요.")

    def _run_updater(self):
        """🔄 업데이트 동그라미 — git pull + 파일 복사 + 런처 재시작을 별도 프로그램으로 실행."""
        if self._is_busy():
            self.status.set(f"⚠ '{self._busy_label()}' 실행 중 — 끝난 뒤 업데이트하세요"); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        for cand in (os.path.join(BASE, "lineagem_update.py"),
                     os.path.join(BASE, "Moon-AI", "lineagem_update.py")):
            if os.path.exists(cand):
                subprocess.Popen([exe, cand])
                self.status.set("🔄 업데이트 실행 — 잠시 후 런처가 자동 재시작됩니다")
                return
        self.status.set("⚠ lineagem_update.py 를 찾을 수 없습니다 (git pull 한 번 필요)")

    def _open_ocr(self):
        if self._is_busy(exclude="다야OCR"):
            self._enqueue("다야OCR 창", self._open_ocr); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self._ocr_proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py")])
        self._send_to_back()

    def _open_ocr_scan(self):
        """다야 전체 스캔 — OCR 창 없이 바로 실행, 끝나면 메인런처 복귀+숫자 갱신."""
        if self._is_busy(exclude="다야OCR"):
            self._enqueue("다야OCR 스캔", self._open_ocr_scan); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self.status.set("📊 다야 전체 스캔 시작... (OCR 로딩 포함 잠시)")
        self._minimize_all()
        proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py"), "--scan", "--close"])
        self._ocr_proc = proc
        def _watch():
            try: proc.wait()
            except Exception: pass
            def _done():
                self._restore_back()   # 앞으로 올리지 않고 맨 뒤로 복원 (클라 안 가림)
                self._refresh_count()
                self.status.set("✔ 다야 전체 스캔 완료")
            self.after(0, _done)
        threading.Thread(target=_watch, daemon=True).start()

    def _open_island(self):
        import subprocess
        self._send_to_back()
        self._minimize_claude()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py")])
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _watch_island(self, proc):
        proc.wait()
        # 그 사이 다른 실행이 시작됐으면 그 핸들을 지우지 않는다
        # (예전엔 무조건 None으로 지워서 '실행 중'인데도 한가한 줄 알고 겹쳐 실행됐다)
        if getattr(self, "_island_proc", None) is proc:
            self._island_proc = None
        # 대기열에 다음 작업이 남아 있으면 창 복원을 건너뛴다 —
        # 복원한 창이 다음 실행의 클릭을 가리는 문제 방지 (전부 끝난 뒤에만 복원)
        if getattr(self, "_task_queue", None):
            return
        if not (self._pass_win and self._pass_win.winfo_exists()):
            self.after(0, self._restore_back)
        # (2026-08-09) 작업이 끝나도 클로드를 앞으로 올리지 않는다 —
        # 사용자가 [💬 클로드] 버튼이나 작업표시줄로 직접 꺼낸다.

    def _restore_claude(self):
        try:
            import win32gui, win32con
            def _do(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Claude" in title and win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.EnumWindows(_do, None)
        except Exception:
            pass


    # ── UI 빌드 ────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── 상단 배너: 다크+골드 그라데이션 (리니지M 느낌) ──
        self._build_banner()

        # 업데이트 누적 횟수 (이 컴퓨터 기준) — 맨 왼쪽 위
        _uc = load_local()
        self._upd_count_var = tk.StringVar(
            value="🔄 업데이트 " + str(int(_uc.get("update_count", 0))) + "회"
                  + ("  (" + str(_uc.get("update_last")) + ")" if _uc.get("update_last") else ""))
        _ur = tk.Frame(self); _ur.pack(fill="x")
        tk.Label(_ur, textvariable=self._upd_count_var, font=("맑은 고딕", 8, "bold"),
                 fg="#8a6d2f").pack(side="left", padx=(14, 0), pady=(2, 0))

        # 혈레이드 · 제자리 (나란히) / 그 아래 맨뒤로 (두 버튼 폭만큼 길게)
        BTN, GAP, LEFT = 46, 6, 30
        WIDE = BTN * 2 + GAP                      # 맨뒤로 가로 길이 = 혈레이드~제자리 끝
        top_row = tk.Frame(self); top_row.pack(fill="x")
        self._boost_btn = tk.Canvas(top_row, width=BTN, height=BTN, highlightthickness=0,
                                    bg=self.cget("bg"), cursor="hand2")
        self._boost_btn.pack(side="left", padx=(LEFT, 0), pady=(2, 0))
        self._boost_btn.create_oval(2, 2, BTN - 2, BTN - 2, fill="#c0392b",
                                    outline="#7b241c", width=2)
        self._boost_btn.create_text(BTN // 2, BTN // 2, text="🔥 혈\n레이드", fill="white",
                                    font=("맑은 고딕", 7, "bold"), justify="center")
        self._boost_btn.bind("<Button-1>", lambda e: self._memo_boost())
        # 제자리 — 혈레이드 바로 옆
        home_c = tk.Canvas(top_row, width=BTN, height=BTN, highlightthickness=0,
                           bg=self.cget("bg"), cursor="hand2")
        home_c.pack(side="left", padx=(GAP, 0), pady=(2, 0))
        home_c.create_oval(2, 2, BTN - 2, BTN - 2, fill="#117864",
                           outline="#0b4f42", width=2)
        home_c.create_text(BTN // 2, BTN // 2, text="📍 제\n자리", fill="white",
                           font=("맑은 고딕", 7, "bold"), justify="center")
        home_c.bind("<Button-1>", lambda e: self._go_home())
        # 거래소검색 — 제자리 오른쪽 (쿠폰등록과 같은 방식: 좌표 클릭 + 글 붙여넣기)
        mk = tk.Frame(top_row); mk.pack(side="left", padx=(GAP, 0), pady=(2, 0))
        tk.Button(mk, text="🔎 거래소검색", font=("맑은 고딕", 8, "bold"),
                  bg="#2874a6", fg="white", width=11,
                  command=self._open_market_win).pack(side="top")
        tk.Button(mk, text="▶ 실행", font=("맑은 고딕", 8, "bold"),
                  bg="#27ae60", fg="white", activebackground="#1e8449", width=11,
                  command=lambda: self._start_dgn2("market")).pack(side="top", pady=(2, 0))
        # 맨뒤로 — 위 두 버튼 폭에 맞춘 긴 버튼 (좌·우 끝 정렬)
        back_row = tk.Frame(self); back_row.pack(fill="x")
        self._back_circle = tk.Canvas(back_row, width=WIDE, height=34, highlightthickness=0,
                                      bg=self.cget("bg"), cursor="hand2")
        self._back_circle.pack(side="left", padx=(LEFT, 0), pady=(3, 0))
        self._back_circle.create_rectangle(2, 2, WIDE - 2, 32, fill="#5d6d7e",
                                           outline="#34495e", width=2)
        self._back_circle.create_text(WIDE // 2, 17, text="⬇ 맨뒤로", fill="white",
                                      font=("맑은 고딕", 9, "bold"))
        # "break" 반환으로 '클릭=앞으로' 핸들러(_raise_on_click)가 도로 올리는 것 차단
        self._back_circle.bind("<Button-1>", lambda e: (self._back_and_claude() or "break"))

        # 계정 수
        row_acc = tk.Frame(self); row_acc.pack(fill="x", padx=16, pady=2)
        tk.Label(row_acc, text="전환할 계정 수:", font=("맑은 고딕", 9)).pack(side="left")
        self.acc_count = tk.IntVar(value=2)
        tk.Spinbox(row_acc, from_=1, to=16, textvariable=self.acc_count,
                   width=4, font=("맑은 고딕", 9), state="normal").pack(side="left", padx=4)

        # 실행 / 멈춤
        # 가운데정렬이면 창을 넓힐 때마다 버튼이 오른쪽으로 밀린다 → 왼쪽 고정
        btn_row = tk.Frame(self); btn_row.pack(pady=6, anchor="w", padx=(38, 0))
        # TJ성공!! (동그라미 버튼) + 실행 — 계정관리 왼쪽
        tjcol = tk.Frame(btn_row); tjcol.pack(side="left", padx=(0, 6), anchor="n")
        self._tjcol = tjcol
        tjc = tk.Canvas(tjcol, width=58, height=58, highlightthickness=0,
                        bg=self.cget("bg"), cursor="hand2")
        tjc.pack()
        tjc.create_oval(2, 2, 56, 56, fill="#ad1457", outline="#6d0f38", width=3)
        tjc.create_text(29, 29, text="TJ\n성공!!", fill="white",
                        font=("맑은 고딕", 8, "bold"), justify="center")
        tjc.bind("<Button-1>", lambda e: self._open_tj_win())
        tk.Button(tjcol, text="▶\n실행", font=("맑은 고딕", 8, "bold"),
                  bg="#27ae60", fg="white", activebackground="#1e8449",
                  width=4, height=2, command=self._start_tj).pack(pady=(2, 0))
        # 🩹 복구 — TJ성공!! 실행 바로 아래 (2026-08-29 사용자 요청)
        tk.Button(tjcol, text="🩹" + chr(10) + "복구", font=("맑은 고딕", 8, "bold"),
                  bg="#7d3c98", fg="white", activebackground="#5b2c6f",
                  width=4, height=2, command=self._open_fix_win).pack(pady=(2, 0))
        # 💬 클로드 앞으로 + 그 아래 🔄 런처재시작 — TJ성공!! 바로 오른편에 붙임
        cl_col = tk.Frame(btn_row); cl_col.pack(side="left", padx=(0, 41), anchor="n")
        tk.Button(cl_col, text="💬 클로드", font=("맑은 고딕", 8, "bold"),
                  bg="#c0392b", fg="white", activebackground="#7b241c",
                  width=6, height=2,
                  command=self._raise_claude).pack()
        tk.Button(cl_col, text="🔄 런처" + chr(10) + "재시작",
                  font=("맑은 고딕", 8, "bold"),
                  bg="#2c3e50", fg="white", activebackground="#1b2631",
                  width=6, height=2,
                  command=self._restart_launcher).pack(pady=(2, 0))
        tk.Button(btn_row, text="🔑 계정\n관리",
            font=("맑은 고딕", 9, "bold"), bg="#16a085", fg="white",
            activebackground="#0e6655", width=7, height=2,
            command=self._open_accounts_win).pack(side="left", padx=(0, 6))
        self.btn_start = tk.Button(btn_row, text="▶  전체 자동 실행",
            font=("맑은 고딕", 12, "bold"), bg="#c8a951", fg="white",
            activebackground="#a88930", width=15, height=2, command=self._start)
        self.btn_start.pack(side="left", padx=(0, 4))
        # 멈춤 버튼이 아래 줄로 옮겨간 자리 — 오른쪽 버튼들(업데이트·좌표저장)이
        # 예전 위치를 그대로 지키도록 같은 폭의 빈칸을 둔다
        tk.Frame(btn_row, width=99).pack(side="left")

        # 9시 클릭 스케줄러
        tk.Frame(btn_row, width=10).pack(side="left")
        self.btn_mail = tk.Button(btn_row,
            text="🕘 23:30~23:50 클릭  " + ("ON" if self._mail_on else "OFF"),
            font=("맑은 고딕", 9, "bold"),
            bg="#27ae60" if self._mail_on else "#7f8c8d", fg="white",
            activebackground="#5d6d7e", width=13, height=2,
            command=self._toggle_mail)
        self.btn_mail.pack(side="left")

        self._btn_layout_toggle = tk.Button(btn_row, text="🖼 배치보기",
            font=("맑은 고딕", 7), width=6, height=2,
            command=self._toggle_layout_preview)
        # layout toggle 참조 유지 (내부 사용)

        tk.Frame(btn_row, width=20).pack(side="left")
        _isl_col = tk.Frame(btn_row); _isl_col.pack(side="left")
        tk.Button(_isl_col, text="🏝 섬/던전 실행기",
            font=("맑은 고딕", 11, "bold"), bg="#2c3e50", fg="white",
            width=14, height=2,
            command=self._open_island).pack()
        # 그 아래 — 요약 런처(작은 창)를 띄운다. ✕ 로 닫아도 런처·작업은 그대로.
        tk.Button(_isl_col, text="📏 요약런처 (던전 4개)",
            font=("맑은 고딕", 8, "bold"), bg="#117a8b", fg="white",
            activebackground="#0e6270", pady=2,
            command=self._open_bar).pack(fill="x", pady=(2, 0))
        tk.Button(btn_row, text="🎫 패스권\n새로운 등록",
            font=("맑은 고딕", 10, "bold"), bg="#6c3483", fg="white",
            width=10, height=2,
            command=self._open_pass_win).pack(side="left", padx=(4,0))
        tk.Frame(btn_row, width=10).pack(side="left")
        popup_box = tk.Frame(btn_row, bd=1, relief="groove", padx=4, pady=2)
        popup_box.pack(side="left")
        tk.Label(popup_box, text="퍼플 팝업 자동닫기",
                 font=("맑은 고딕", 7, "bold"), fg="#8e44ad").pack()
        pb_row = tk.Frame(popup_box); pb_row.pack()
        tk.Button(pb_row, text="☑ 체크박스\n좌표 등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_checkbox).pack(side="left", padx=1)
        tk.Button(pb_row, text="✕ 닫기버튼\n좌표 등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_close).pack(side="left", padx=1)
        tk.Button(pb_row, text="🎨 감지픽셀\n등록", font=("맑은 고딕", 6),
                  width=8, command=self._reg_popup_detect).pack(side="left", padx=1)
        self._popup_status_var = tk.StringVar(value=self._popup_reg_label())
        tk.Label(popup_box, textvariable=self._popup_status_var,
                 font=("맑은 고딕", 6), fg="#7f8c8d").pack()

        # 퍼플 팝업 자동닫기 우측: 오림의 일기장(아이템 리롤) — 크게
        tk.Frame(btn_row, width=10).pack(side="left")
        tk.Button(btn_row, text="📖 오림의\n일기장", font=("맑은 고딕", 13, "bold"),
                  bg="#a04000", fg="white", activebackground="#7a3000",
                  width=11, height=3, command=self._open_reroll_win).pack(side="left")

        # 오림의 일기장 오른쪽: 🛒 이벤트상점 (위=창 열기, 아래=▶ 바로 실행)
        eg = tk.Frame(btn_row); eg.pack(side="left", padx=(6, 0))
        tk.Button(eg, text="🛒 이벤트\n상점", font=("맑은 고딕", 10, "bold"),
                  bg="#0e6655", fg="white", activebackground="#0b5345",
                  width=7, height=2, command=self._open_eventshop_win).pack(side="top")
        tk.Button(eg, text="▶ 실행", font=("맑은 고딕", 8, "bold"),
                  bg="#0b5345", fg="white", width=9, height=1, pady=2,
                  command=lambda: self._start_dgn2("eventshop")).pack(side="top", pady=(1, 0))

        # 🎟 쿠폰등록 (위=창 열기, 아래=▶ 바로 실행)
        cg = tk.Frame(btn_row); cg.pack(side="left", padx=(6, 0))
        tk.Button(cg, text="🎟 쿠폰\n등록", font=("맑은 고딕", 10, "bold"),
                  bg="#1f618d", fg="white", activebackground="#154360",
                  width=7, height=2, command=self._open_coupon_win).pack(side="top")
        tk.Button(cg, text="▶ 실행", font=("맑은 고딕", 8, "bold"),
                  bg="#154360", fg="white", width=9, height=1, pady=2,
                  command=lambda: self._start_dgn2("coupon")).pack(side="top", pady=(1, 0))

        # 쿠폰등록과 좌표저장 사이: 빨간 동그라미 업데이트 버튼 (git pull + 재시작)
        upd = tk.Canvas(btn_row, width=78, height=78, highlightthickness=0,
                        bg=self.cget("bg"), cursor="hand2")
        upd.pack(side="left", padx=(6, 0))
        upd.create_oval(3, 3, 75, 75, fill="#c0392b", outline="#7b241c", width=3)
        upd.create_text(39, 29, text="🔄", font=("맑은 고딕", 13))
        upd.create_text(39, 52, text="업데이트", fill="white", font=("맑은 고딕", 9, "bold"))
        upd.bind("<Button-1>", lambda e: self._run_updater())

        # 맨 오른쪽: 좌표 저장/복구 (이 컴퓨터 전용 — 내가 저장한 시점으로 되돌리기)
        sv = tk.Frame(btn_row); sv.pack(side="left", padx=(6, 0))
        tk.Button(sv, text="💾 좌표\n저장", font=("맑은 고딕", 9, "bold"),
                  bg="#1e8449", fg="white", activebackground="#145a32",
                  width=7, height=2, command=self._save_coord_snapshot).pack(side="top")
        self._coord_save_lbl = tk.Label(sv, font=("맑은 고딕", 6), fg="#666")
        self._coord_save_lbl.pack(side="top")
        tk.Button(sv, text="♻ 좌표복구", font=("맑은 고딕", 8, "bold"),
                  bg="#7d3c98", fg="white", activebackground="#5b2c6f",
                  width=9, height=1, pady=2,
                  command=self._restore_coord_snapshot).pack(side="top", pady=(1, 0))
        # 🔒 좌표 잠금 — 잠근 런처는 업데이트가 절대 못 건드린다
        self._lock_btn = tk.Button(sv, text="🔒 좌표잠금", font=("맑은 고딕", 8, "bold"),
                                   bg="#c0392b", fg="white", activebackground="#922b21",
                                   width=9, height=1, pady=2, command=self._open_lock_win)
        self._lock_btn.pack(side="top", pady=(1, 0))
        tk.Button(sv, text="↩ 되돌리기", font=("맑은 고딕", 8, "bold"),
                  bg="#7b241c", fg="white", activebackground="#5b1a15",
                  width=9, height=1, pady=2,
                  command=self._open_lastrun_win).pack(side="top", pady=(1, 0))
        # 🌙 어두운 화면 / ☀ 밝은 화면
        self._dark_btn = tk.Button(sv, font=("맑은 고딕", 8, "bold"), fg="white",
                                   width=9, height=1, pady=2,
                                   command=self._toggle_dark)
        self._dark_btn.pack(side="top", pady=(1, 0))
        self._refresh_coord_save_lbl()
        self.after(1500, self._refresh_lock_btn)
        self.after(300, self._apply_dark_all)     # 저장해둔 화면 밝기 적용
        # TJ성공!! 좌측 끝 정렬용 가변 여백 (행이 가운데 정렬이라 오른쪽을 늘려 왼쪽으로 밀기)
        self._btnrow_pad = tk.Frame(btn_row, width=0, height=1)
        self._btnrow_pad.pack(side="left")

        # 다야 카운트 데이터 변수 (UI는 별도 창)
        self._cnt_total_var = tk.StringVar(value="합계: 0")
        self._cnt_date_var  = tk.StringVar(value="")   # 마지막 확정 측정 일시
        self._cnt_diff_var  = tk.StringVar(value="")   # 직전 확정 대비 수량 차이
        self._cnt_cell_vars = [tk.StringVar(value="-") for _ in range(16)]
        self._cnt_load  = self._make_cnt_loader()
        self._cnt_today = self._make_today_fn()
        self._refresh_count()
        self._schedule_count_refresh()


        # 배치 스크린샷 미리보기 (기본 숨김)
        self._layout_img_label = None
        self._layout_preview_frame = tk.Frame(self)
        self._layout_preview_visible = False

        self.status = tk.StringVar(value="버튼을 눌러 시작하세요")
        self.status_label_widget = tk.Label(self, textvariable=self.status, font=("맑은 고딕", 8),
                 fg="#555", wraplength=600)
        self.status_label_widget.pack(pady=(0, 2))

        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=10, pady=3)

        # ── 섹션 버튼 행 (좌표등록·과거섬·스케줄·사냥 등 직접 표시) ──
        self._sec_row = tk.Frame(self); self._sec_row.pack(pady=4, anchor="w", padx=(38, 0))
        self._build_sec_row()

        # ── 배열창 재배치(슬롯별 그리드) + 다야 수량 ──
        tk.Frame(self, height=1, bg="#ccc").pack(fill="x", padx=10, pady=(4,2))
        front_row = tk.Frame(self); front_row.pack(pady=4, anchor="w", padx=(38, 0))
        self._front_row = front_row   # 정렬 보정용 (일반던전충전 열 ← TJ 좌측 라인)

        # 배열창 재배치 왼쪽: (1행) 일반던전충전+실행  (2행) 인형탐험+실행 — 각 버튼 옆에 실행
        dc_col = tk.Frame(front_row); dc_col.pack(side="left", padx=(4,8), anchor="n")
        # ── 매일 해야 하는 것 (네모 박스) : 용던고고!!! / 스케줄 ──
        daily = tk.LabelFrame(dc_col, text=" 매일 ", font=("맑은 고딕", 8, "bold"),
                              fg="#a04000", bd=2, relief="groove")
        daily.pack(anchor="n", pady=(0, 5), padx=1)
        d1 = tk.Frame(daily); d1.pack(anchor="n", padx=3, pady=(3, 0))
        tk.Button(d1, text="🐲 용던\n고고!!!",
            font=("맑은 고딕", 9, "bold"), bg="#a04000", fg="white",
            activebackground="#7b3000", width=7, height=2,
            command=self._open_dragon_win).pack(side="left")
        tk.Button(d1, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_dragon).pack(side="left", padx=(2, 0))
        d2 = tk.Frame(daily); d2.pack(anchor="n", padx=3, pady=(4, 4))
        tk.Button(d2, text="📅 스케줄",
            font=("맑은 고딕", 9, "bold"), bg="#16a085", fg="white",
            activebackground="#0e6655", width=7, height=2,
            command=self._open_sched_win).pack(side="left")
        tk.Button(d2, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_sched).pack(side="left", padx=(2, 0))
        # 던전끝! 흑기사!! — [매일] 박스 바로 아래
        kr = tk.Frame(dc_col); kr.pack(anchor="n", pady=(0, 5))
        tk.Button(kr, text="🖤 던전끝!\n흑기사!!",
            font=("맑은 고딕", 9, "bold"), bg="#212f3d", fg="white",
            activebackground="#17202a", width=7, height=2,
            command=self._open_knight_win).pack(side="left")
        tk.Button(kr, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=lambda: self._start_dgn2("knight")).pack(side="left", padx=(2, 0))
        r1 = tk.Frame(dc_col); r1.pack(anchor="n")
        self._dc_open_btn = tk.Button(r1, text="🎯 일반\n던전충전",
            font=("맑은 고딕", 9, "bold"), bg="#6c3483", fg="white",
            activebackground="#512e6f", width=7, height=2,
            command=self._open_dc_win)
        self._dc_open_btn.pack(side="left")
        tk.Button(r1, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_dc).pack(side="left", padx=(2,0))
        r2 = tk.Frame(dc_col); r2.pack(anchor="n", pady=(4,0))
        tk.Button(r2, text="🧸 인형\n탐험",
            font=("맑은 고딕", 9, "bold"), bg="#b9770e", fg="white",
            activebackground="#8a5809", width=7, height=2,
            command=self._open_doll_win).pack(side="left")
        tk.Button(r2, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_doll).pack(side="left", padx=(2,0))
        # 인형탐험 아래: 매일매일 스케줄 (자주 쓰는 기능이라 앞으로 이동)
        # 스케줄은 위쪽 [매일] 박스로 옮겼다 (2026-08-16)
        # 아이템정리 (스케줄과 동일 구조 + 단축키)
        r4 = tk.Frame(dc_col); r4.pack(anchor="n", pady=(4,0))
        tk.Button(r4, text="🧹 아이템\n정리",
            font=("맑은 고딕", 9, "bold"), bg="#7d6608", fg="white",
            activebackground="#5d4c06", width=7, height=2,
            command=self._open_item_win).pack(side="left")
        tk.Button(r4, text="▶\n실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=self._start_item).pack(side="left", padx=(2,0))
        # 아이템정리 아래(이 줄 끝): 🎣 낚시녹임 — 변신확인용과 동일 구조(dgn2)
        r5 = tk.Frame(dc_col); r5.pack(anchor="n", pady=(4,0))
        tk.Button(r5, text="🎣 낚시" + chr(10) + "녹임",
            font=("맑은 고딕", 9, "bold"), bg="#1a5276", fg="white",
            activebackground="#123c56", width=7, height=2,
            command=self._open_fish_win).pack(side="left")
        tk.Button(r5, text="▶" + chr(10) + "실행",
            font=("맑은 고딕", 8, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=4, height=2,
            command=lambda: self._start_dgn2("fish")).pack(side="left", padx=(2,0))

        # 작업이 끝나면 여기에 큰 빨간 글씨로 '완료'가 1분간 뜬다
        self._done_var = tk.StringVar(value="")
        self._done_lbl = tk.Label(dc_col, textvariable=self._done_var,
                                  font=("맑은 고딕", 16, "bold"), fg="#c0392b",
                                  bg=self.cget("bg"), width=11, height=2,
                                  anchor="center")
        self._done_lbl.pack(anchor="n", pady=(3, 0))

        # ⚠ 경고 목록 — F11 때 확인해서 뜬 것들. 내가 X를 누르기 전엔 안 사라진다
        self._warn_box = tk.Frame(dc_col)
        self._warn_box.pack(anchor="n", pady=(2, 0))
        self._warn_hdr = tk.Label(self._warn_box, text="", font=("맑은 고딕", 9, "bold"),
                                  fg="white", bg="#c0392b")
        self._warn_rows = tk.Frame(self._warn_box)
        self._warn_rows.pack(fill="x")
        self.after(900, self._warn_refresh)

        # 확인용 3종 묶음: 변신확인용 / 인형확인용 / 성물확인용 (세로로 한 곳에)
        chk_col = tk.Frame(front_row); chk_col.pack(side="left", padx=(4,8), anchor="n")
        for _t, _bg, _open, _run in (
                ("🏰 변신\n확인용", "#d35400", self._open_dungeon_win, self._start_dungeon),
                ("🧸 인형\n확인용", "#b9770e", self._open_dollchk_win, lambda: self._start_dgn2("dollchk")),
                ("🗿 성물\n확인용", "#117864", self._open_relic_win,   lambda: self._start_dgn2("relic")),
                ("🎪 서커스\n이벤트등록", "#7d3c98", self._open_circus_win, lambda: self._start_dgn2("circus")),
                ("🎪 서커스\n이벤트실행", "#5b2c6f", self._open_circus2_win, lambda: self._start_dgn2("circus2")),
                ("🎪 서커스\n이벤트퀘스트", "#4a235a", self._open_circus3_win, lambda: self._start_dgn2("circus3"))):
            rr = tk.Frame(chk_col); rr.pack(anchor="n", pady=(0,4))
            tk.Button(rr, text=_t, font=("맑은 고딕", 9, "bold"), bg=_bg, fg="white",
                      width=9, height=2, command=_open).pack(side="left")
            tk.Button(rr, text="▶\n실행", font=("맑은 고딕", 8, "bold"),
                      bg="#27ae60", fg="white", activebackground="#1e8449",
                      width=4, height=2, command=_run).pack(side="left", padx=(2,0))

        winmgmt = tk.Frame(front_row); winmgmt.pack(side="left", padx=(4,10), anchor="n")
        self._build_winmgmt(winmgmt)

        tk.Frame(front_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=(4,8))

        # 다야 수량 컨트롤 + 그리드
        daya_inner = tk.Frame(front_row); daya_inner.pack(side="left", anchor="n")
        ctrl = tk.Frame(daya_inner); ctrl.pack(side="left", padx=(4,8), anchor="n")
        tk.Label(ctrl, text="💰 다야 수량", font=("맑은 고딕", 9, "bold"), fg="#2c3e50").pack(anchor="w")
        tk.Button(ctrl, text="📊 OCR 실행", font=("맑은 고딕", 8, "bold"),
                  bg="#27ae60", fg="white", width=10,
                  command=self._open_ocr_scan).pack(fill="x", pady=1)
        tk.Button(ctrl, text="📋 복사", font=("맑은 고딕", 8, "bold"),
                  bg="#2471a3", fg="white", width=10,
                  command=self._copy_daya_counts).pack(fill="x", pady=1)
        tk.Label(ctrl, textvariable=self._cnt_date_var,
                 font=("맑은 고딕", 7), fg="#555").pack(anchor="w", pady=(4,0))
        tk.Label(ctrl, textvariable=self._cnt_total_var,
                 font=("맑은 고딕", 10, "bold"), fg="#c0392b").pack(anchor="w")
        tk.Label(ctrl, textvariable=self._cnt_diff_var,
                 font=("맑은 고딕", 9, "bold"), fg="#8e44ad").pack(anchor="w")

        self._cnt_img_labels = []
        self._cnt_thumbs = [None] * 16
        grid = tk.Frame(daya_inner); grid.pack(side="left", anchor="n")
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(grid, bd=1, relief="groove")
                cell.grid(row=r, column=c, padx=1, pady=1, sticky="n")
                head = tk.Frame(cell); head.pack()
                tk.Label(head, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")
                cntlbl = tk.Label(head, textvariable=self._cnt_cell_vars[idx],
                         font=("맑은 고딕", 11, "bold"), fg="#2980b9", cursor="hand2")
                cntlbl.pack(side="left", padx=(2,0))
                cntlbl.bind("<Button-1>", lambda e, x=idx: self._edit_daya_count(x))
                imbox = tk.Frame(cell, width=93, height=33, bg="#f4f4f4")
                imbox.pack()
                imbox.pack_propagate(False)
                imlbl = tk.Label(imbox, bg="#f4f4f4", fg="#ccc", font=("맑은 고딕", 7))
                imlbl.pack(fill="both", expand=True)
                self._cnt_img_labels.append(imlbl)
                tk.Button(cell, text="재측정", font=("맑은 고딕", 6, "bold"),
                          bg="#27ae60", fg="white", pady=0,
                          command=lambda x=idx: self._rescan_daya_slot(x)).pack(fill="x")
        self._load_daya_thumbs()

        # 다야 수량 우측: 귀환주문서 슬롯별 실행 그리드 (좌표는 섬/던전 실행기에서 관리)
        tk.Frame(front_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=(8,8))
        return_col = tk.Frame(front_row); return_col.pack(side="left", anchor="n")
        self._build_return_grid(return_col)

        # 귀환주문서 우측: 악몽의섬 슬롯별 실행 + 반복끄기
        tk.Frame(front_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=(8, 8))
        night_col = tk.Frame(front_row); night_col.pack(side="left", anchor="n")
        self._build_night_grid(night_col)

        # 서브창 핸들 초기화
        self._settings_win = None
        self._hunt_win     = None
        self._mail_win     = None
        self._past_win2    = None
        self._sched_win    = None
        self._dungeon_win  = None
        self._daya_win     = None
        self._pass_win     = None
        self._accounts_win = None
        self._reroll_win   = None
        self._reroll_running = False
        self._reroll_thumbs  = [None] * 4   # 타깃 미리보기 PhotoImage 참조 유지
        self._island_proc  = None
        self._pass_name_vars    = []
        self._pass_click_vars   = []
        self._pass_click_btns   = []
        self._pass_coord_sv     = []
        self._pass_detail_frames= []
        self._pass_row_frames   = []
        self._refresh_ui()

    # ── 섹션 창 열기 ────────────────────────────────────────────────────
    def _minimize_claude(self):
        # 승인 버튼(항상 허용/한 번 허용) 등 주의 요청 후 3분간은 최소화하지 않음
        if time.time() - getattr(self, "_claude_attention_ts", 0) < 180:
            return
        try:
            import win32gui, win32con
            def _do(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Claude" in title and win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            win32gui.EnumWindows(_do, None)
        except Exception:
            pass

    def _open_section_win(self, attr, title, build_fn, w=420, h=700, pinnable=False, fit=True):
        win = getattr(self, attr, None)
        if win and win.winfo_exists():
            # 같은 버튼을 다시 누르면 열려 있던 창을 닫고 새로 띄운다 (2026-08-15 사용자 지시)
            try: win.destroy()
            except Exception: pass
            setattr(self, attr, None)
        win = tk.Toplevel(self)
        win.title(title)
        win.attributes("-topmost", True)
        # 저장된 위치가 있으면 복원, 없으면 기본 크기
        pos_key = f"_win_pos_{attr}"
        saved = self.cfg.get(pos_key)
        if saved:
            win.geometry(f"{w}x{h}+{saved[0]}+{saved[1]}")
        else:
            win.geometry(f"{w}x{h}")
        win.resizable(True, True)
        setattr(self, attr, win)
        # 실행 시 _minimize_all이 빠뜨리지 않게 모든 섹션 창을 자동 등록
        if not hasattr(self, "_section_attrs"):
            self._section_attrs = set()
        self._section_attrs.add(attr)
        # 서브창: 3분간 조작 없으면 자동으로 닫고 메인런처 복원
        win._last_active = time.time()
        def _bump(e=None, w=win): w._last_active = time.time()
        for _seq in ("<Button>", "<Key>", "<Motion>"):
            win.bind(_seq, _bump, add="+")
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self._close_subwin(w))
        build_fn(win)
        if pinnable:
            self._add_drag_bar(win, attr, pos_key)
        self._refresh_ui()
        # 내용 크기에 맞게 창 가로+세로 자동 조정 (셀에 딱 맞춤). fit=False면 지정 크기 고정.
        if fit:
            def _fit():
                win.update_idletasks()
                nw = win.winfo_reqwidth() + 10
                nh = win.winfo_reqheight() + 6
                win.geometry(f"{nw}x{nh}")
            win.after(80, _fit)
        try:                    # 새 창도 지금 화면 밝기에 맞춘다
            if self._dark_on():
                apply_dark(win, True)
        except Exception:
            pass
        return win

    def _close_subwin(self, win):
        """서브창을 닫고 메인런처를 앞으로 띄운다."""
        try:
            if win and win.winfo_exists():
                win.destroy()
        except Exception:
            pass
        def _raise():
            try:
                self.deiconify(); self.lift(); self.focus_force()
            except Exception:
                pass
        self.after(60, _raise)

    def _subwin_autoclose_tick(self):
        """열려있는 서브창이 3분간 조작이 없으면 자동으로 닫는다(실행 중엔 유지)."""
        try:
            if not self._is_busy():   # 실행 중이면 창을 건드리지 않음
                now = time.time()
                for w in self._section_wins():
                    if now - getattr(w, "_last_active", now) >= 180:
                        self._close_subwin(w)
                        break   # 한 번에 하나씩(복원 충돌 방지)
        except Exception:
            pass
        self.after(20000, self._subwin_autoclose_tick)

    def _add_drag_bar(self, win, attr, pos_key):
        """창 하단에 드래그 이동바 추가. 이동 후 위치를 cfg에 저장."""
        bar = tk.Frame(win, bg="#555", height=18, cursor="fleur")
        bar.pack(side="bottom", fill="x")
        lbl = tk.Label(bar, text="⠿ 여기를 드래그해서 창 이동", bg="#555", fg="#ccc",
                       font=("맑은 고딕", 7), cursor="fleur")
        lbl.pack()

        _drag = {"x": 0, "y": 0}

        def _start(e):
            _drag["x"] = e.x_root - win.winfo_x()
            _drag["y"] = e.y_root - win.winfo_y()

        def _drag_move(e):
            nx = e.x_root - _drag["x"]
            ny = e.y_root - _drag["y"]
            win.geometry(f"+{nx}+{ny}")

        def _end(e):
            nx = win.winfo_x()
            ny = win.winfo_y()
            self.cfg[pos_key] = [nx, ny]
            self._save_cfg()

        for w in (bar, lbl):
            w.bind("<ButtonPress-1>", _start)
            w.bind("<B1-Motion>", _drag_move)
            w.bind("<ButtonRelease-1>", _end)

    def _open_settings_win(self):
        self._open_section_win("_settings_win", "⚙ 좌표 등록", self._build_left, w=320, h=680)

    def _open_hunt_win(self):
        self._open_section_win("_hunt_win", "🏹 사냥", self._build_right, w=470, h=620)

    def _open_accounts_win(self):
        self._open_section_win("_accounts_win", "🔑 계정 관리", self._build_accounts, w=560, h=560)

    def _open_reroll_win(self):
        self._open_section_win("_reroll_win", "📖 오림의 일기장", self._build_reroll, w=440, h=800)

    def _open_mail_win(self):
        self._open_section_win("_mail_win", "📬 우편함", self._build_mail, w=470, h=600)

    def _open_past_win(self):
        self._open_section_win("_past_win2", "🏝 과거의말하는섬", self._build_past, w=470, h=620, pinnable=True)

    def _open_past_slot(self, idx):
        """해당 던전 컬럼만 단독으로 섬/던전 실행기 열기."""
        self._send_to_back()
        self._minimize_claude()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py"), str(idx)])
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    # ── 섬/던전 슬롯 반복(2시간 N회) — 메인런처가 관리 (2026-08-09) ─────
    #    예전엔 섬/던전 실행기 창 안에서만 타이머가 돌아, 창을 닫으면 반복이
    #    통째로 죽었다. 이제 런처가 시각을 파일에 기록하며 관리하므로
    #    창을 껐다 켜도, 런처를 재시작해도 이어진다.
    ISLAND_KEYS = ("수금_오만의탑", "토요일_악몽의섬", "월요일_잊혀진섬",
                   "화요일_에카", "귀환주문서", "카매사오기")

    def _rep_path(self):
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "island_repeat.json")

    def _rep_load(self):
        try:
            with open(self._rep_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _rep_save(self, st):
        try:
            with open(self._rep_path(), "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _rep_log(self, msg):
        try:
            import datetime as _dt
            d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "repeat_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"[{_dt.datetime.now():%m-%d %H:%M:%S}] {msg}" + chr(10))
        except Exception:
            pass

    @staticmethod
    def _rep_delay(h):
        """반복 주기(초) — 섬/던전 실행기와 같은 규칙(2h면 2:02~2:07 랜덤)."""
        extra = {1: (1, 7), 2: (2, 7), 3: (2, 6), 4: (2, 7)}.get(h, (1, 7))
        return h * 3600 + random.uniform(extra[0], extra[1]) * 60

    def _island_cfg(self):
        try:
            with open(os.path.join(BASE, "island_coords.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # 정해진 횟수를 다 채워도 ⏰를 끄지 않고 다시 채워 넣는 던전 (2026-08-14 사용자 지시)
    #   — 악몽의섬은 2시간 6회를 계속 돌린다. [■ 전체멈춤]·[⏰ 반복]으로 끄는 것은 그대로 동작.
    REPEAT_FIXED = {"토요일_악몽의섬": (2, 6)}      # {던전: (몇시간, 몇회)}
    # 반복을 새로 걸 때 '첫 회차만' 이 시간으로 기다린다 (2026-08-22 사용자 지시)
    #   악몽의섬 6회 = 4시간 1회 + 2시간 5회
    REPEAT_FIRST = {"토요일_악몽의섬": 4}          # {던전: 첫 대기 시간(시간)}

    def _rep_first_h(self, key, h, idx=None):
        """그 던전의 '첫 대기 시간'.
        슬롯 번호를 주면 그 슬롯이 '첫 4시간' 모드일 때만 4시간을 쓴다
        (첫 4시간을 이미 돌았거나 팅긴 뒤엔 2시간부터 다시 돌리려고 — 2026-08-22)."""
        f = int(self.REPEAT_FIRST.get(key, h) or h)
        if f == h or idx is None:
            return f
        return f if self._rep_first_on(key, idx) else h

    def _rep_first_on(self, key, idx):
        """그 슬롯이 '4시간 → 2시간' 모드인가 (기본 켜짐)."""
        try:
            return bool(self._rep_load().get("_first", {}).get(f"{key}|{idx}", True))
        except Exception:
            return True

    def _rep_first_set(self, key, idx, on):
        st = self._rep_load()
        d = st.get("_first") or {}
        d[f"{key}|{idx}"] = bool(on)
        st["_first"] = d
        self._rep_save(st)

    def _rep_hn(self, key, slot=None):
        """그 던전의 (몇시간, 몇회).
        슬롯에 정해둔 값이 있으면 그것을 쓴다 — 창 위 '전체 일괄'로 바꾼 값이 이긴다.
        비어 있으면 고정 던전 기본값(악몽의섬 2시간 6회)."""
        h = n = 0
        try:
            h = int((slot or {}).get("repeat_h") or 0)
            n = int((slot or {}).get("repeat_n") or 0)
        except Exception:
            pass
        fx = self.REPEAT_FIXED.get(key)
        if fx:
            return (h or fx[0]), (n or fx[1])
        return (h or 2), (n or 8)

    def _rep_turn_off(self, key, idx):
        """정해진 횟수를 다 채웠으면 섬/던전 설정의 ⏰도 꺼준다.
        (고정 던전은 끄지 않는다 — 계속 돌아야 하므로)"""
        if key in self.REPEAT_FIXED:
            return
        try:
            path = os.path.join(BASE, "island_coords.json")
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg[key][idx]["repeat_h"] = 0
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            self._rep_log(f"⚠ {key} #{idx+1:02d} ⏰ 끄기 실패: {e!r}")

    # ── ↩ 마지막 실행 시점으로 되돌리기 (섬/던전 좌표) ───────────────
    DUNGEON_HINT = ("섬", "탑", "에카", "주문서", "카매사")

    def _lr_last_runs(self):
        """repeat_log.txt 에서 던전별 '마지막으로 클릭이 돌아간 시각'."""
        import re, datetime as _dt
        p = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI", "repeat_log.txt")
        out, hit = {}, 0
        if not os.path.exists(p):
            return out, hit
        year = _dt.date.today().year
        for ln in open(p, encoding="utf-8", errors="replace"):
            m = re.match(r"\[(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\]\s+(?:\[클릭\]\s+)?(\S+)", ln)
            if not m:
                continue
            mm, dd, hh, mi, ss, key = m.groups()
            if not any(x in key for x in self.DUNGEON_HINT):
                continue
            try:
                t = _dt.datetime(year, int(mm), int(dd), int(hh), int(mi), int(ss))
            except ValueError:
                continue
            if t > _dt.datetime.now() + _dt.timedelta(days=1):
                t = t.replace(year=year - 1)
            hit += 1
            if key not in out or t > out[key]:
                out[key] = t
        return out, hit

    @staticmethod
    def _lr_slots(path, key):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return None
        v = d.get(key)
        if not isinstance(v, list) or not v:
            return None
        if not any(isinstance(x, dict) and any(x.get("coords") or []) for x in v):
            return None
        return v

    def _lr_scan(self):
        """던전마다 '마지막 실행 시점'으로 되돌릴 자료를 찾는다 (바꾸지는 않음)."""
        import glob as _g, datetime as _dt
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        runs, hit = self._lr_last_runs()
        rows, cur = [], {}
        try:
            with open(os.path.join(BASE, "island_coords.json"), encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            return [], hit, {}
        for key, t in sorted(runs.items(), key=lambda x: x[1]):
            srcs = []
            for q in _g.glob(os.path.join(d, "runsnap", f"{key}_*.json")):
                srcs.append((_dt.datetime.fromtimestamp(os.path.getmtime(q)), q, "실행직전"))
            for q in _g.glob(os.path.join(d, "backups", "*island_coords.json")):
                srcs.append((_dt.datetime.fromtimestamp(os.path.getmtime(q)), q, "백업"))
            srcs = [x for x in sorted(srcs) if self._lr_slots(x[1], key)]
            if not srcs:
                rows.append({"key": key, "run": t, "why": "되돌릴 자료 없음"}); continue
            before = [x for x in srcs if x[0] <= t + _dt.timedelta(seconds=90)]
            bt, bp, kind = (before[-1] if before else srcs[0])
            old = self._lr_slots(bp, key)
            same = (json.dumps(old, sort_keys=True) == json.dumps(cur.get(key), sort_keys=True))
            rows.append({"key": key, "run": t, "src": bt, "path": bp, "kind": kind,
                         "old": old, "same": same,
                         "cur_n": sum(1 for x in (cur.get(key) or []) if any(x.get("coords") or [])),
                         "old_n": sum(1 for x in old if any(x.get("coords") or []))})
        return rows, hit, cur

    def _dark_on(self):
        return bool(self.cfg.get("dark_ui", True))

    def _refresh_dark_btn(self):
        b = getattr(self, "_dark_btn", None)
        if not b:
            return
        if self._dark_on():
            b.config(text="☀ 밝게", bg="#566573", activebackground="#41525e")
        else:
            b.config(text="🌙 어둡게", bg="#2c3e50", activebackground="#1b2631")

    def _apply_dark_all(self):
        """메인 창과 열려 있는 모든 서브창에 적용."""
        on = self._dark_on()
        try:
            apply_dark(self, on)
        except Exception:
            pass
        for w in list(self.winfo_children()):      # 열려 있는 서브창들
            try:
                if isinstance(w, tk.Toplevel) and w.winfo_exists():
                    apply_dark(w, on)
            except Exception:
                pass
        self._refresh_dark_btn()

    def _open_bar(self):
        """요약 런처(작은 창)를 띄운다 — 별도 프로세스라 메인런처·작업과 무관하다.
        이미 떠 있으면 새로 띄우지 않는다. 그 창의 ✕ 는 '창만' 닫는다."""
        try:
            d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
            pidf = os.path.join(d, "bar.json")
            pid = 0
            try:
                with open(pidf, encoding="utf-8") as f:
                    pid = int((json.load(f) or {}).get("pid") or 0)
            except Exception:
                pid = 0
            if pid:      # 그 번호의 프로세스가 아직 살아 있나
                try:
                    out = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True, text=True, timeout=5).stdout
                    if str(pid) in out:
                        # 떠 있으면 새로 띄우지 않고 '앞으로 올려라' 신호만 남긴다
                        try:
                            with open(pidf, encoding="utf-8") as f:
                                d2 = json.load(f) or {}
                            d2["raise"] = time.time()
                            tmp = pidf + ".tmp"
                            with open(tmp, "w", encoding="utf-8") as f:
                                json.dump(d2, f, ensure_ascii=False, indent=2)
                            os.replace(tmp, pidf)
                        except Exception:
                            pass
                        self.status.set("📏 요약런처를 앞으로 가져왔습니다")
                        return
                except Exception:
                    pass
            subprocess.Popen(["pythonw", os.path.join(BASE, "lineagem_bar.pyw")])
            self.status.set("📏 요약런처 — 화면 아래에 떴습니다 "
                            "(✕ 는 창만 닫고, 돌던 작업·반복은 그대로)")
        except Exception as e:
            self.status.set(f"요약런처 실행 실패: {e}")

    def _toggle_dark(self):
        self.cfg["dark_ui"] = not self._dark_on()
        save_cfg(self.cfg)
        self._apply_dark_all()
        self.status.set("🌙 어두운 화면으로 바꿨습니다 (눈 보호)"
                        if self._dark_on() else "☀ 밝은 화면으로 되돌렸습니다")

    def _open_lastrun_win(self):
        self._open_section_win("_lastrun_win", "↩ 마지막 실행 시점으로 되돌리기",
                               self._build_lastrun, w=620, h=460, pinnable=True)

    def _build_lastrun(self, parent):
        tk.Label(parent, text="↩ 섬/던전 좌표를 '그 던전을 마지막으로 실행했던 때'로 되돌립니다",
                 font=("맑은 고딕", 10, "bold"), fg="#7b241c").pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(parent, text="· 되돌리는 것: 좌표·이름·간격·방향·프리셋\n"
                              "· 그대로 두는 것: 녹화(⏺), 다른 던전, 메인런처 좌표(coords.json) 전부\n"
                              "· 되돌리기 직전 상태는 자동으로 백업됩니다",
                 font=("맑은 고딕", 8), fg="#555", justify="left").pack(anchor="w", padx=6)
        box = tk.Frame(parent, bd=1, relief="groove")
        box.pack(fill="both", expand=True, padx=6, pady=6)
        self._lr_rows = []
        rows, hit, _cur = self._lr_scan()
        tk.Label(box, text=f"실행 기록에서 찾은 던전 줄: {hit}개",
                 font=("맑은 고딕", 8), fg="#888").pack(anchor="w", padx=6, pady=(4, 2))
        if not rows:
            tk.Label(box, text="던전 실행 기록을 찾지 못했습니다 — 되돌릴 기준이 없습니다.",
                     font=("맑은 고딕", 9, "bold"), fg="#c0392b").pack(anchor="w", padx=6, pady=6)
        for r in rows:
            fr = tk.Frame(box); fr.pack(fill="x", padx=6, pady=2)
            v = tk.BooleanVar(value=not r.get("same") and "old" in r)
            if "old" in r:
                self._lr_rows.append((r, v))
                tk.Checkbutton(fr, variable=v).pack(side="left")
                txt = (f"{r['key']}   실행 {r['run']:%m-%d %H:%M}  →  "
                       f"{r['src']:%m-%d %H:%M} [{r['kind']}]   "
                       f"{r['cur_n']}슬롯 → {r['old_n']}슬롯")
                col = "#7f8c8d" if r["same"] else "#1a5276"
                if r["same"]:
                    txt += "   (이미 같음)"
                tk.Label(fr, text=txt, font=("맑은 고딕", 9), fg=col).pack(side="left")
            else:
                tk.Label(fr, text=f"{r['key']}   실행 {r['run']:%m-%d %H:%M}  →  ⚠ {r['why']}",
                         font=("맑은 고딕", 9), fg="#c0392b").pack(side="left", padx=(20, 0))
        br = tk.Frame(parent); br.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(br, text="↩ 체크한 던전 되돌리기", font=("맑은 고딕", 10, "bold"),
                  bg="#c0392b", fg="white", height=2,
                  command=self._lr_apply).pack(side="left")
        tk.Button(br, text="다시 확인", font=("맑은 고딕", 9),
                  bg="#7f8c8d", fg="white", height=2,
                  command=lambda: (self._close_subwin(self._lastrun_win),
                                   self._open_lastrun_win())).pack(side="left", padx=(6, 0))
        self._lr_msg = tk.Label(parent, text="", font=("맑은 고딕", 9, "bold"), fg="#1e8449",
                                wraplength=580, justify="left")
        self._lr_msg.pack(anchor="w", padx=6, pady=(0, 6))

    def _lr_apply(self):
        """체크한 던전을 그 시점으로 되돌린다 (녹화는 지금 것 유지)."""
        import datetime as _dt, shutil
        picks = [(r, v) for r, v in (getattr(self, "_lr_rows", None) or []) if v.get()]
        if not picks:
            self._lr_msg.config(text="체크한 던전이 없습니다.", fg="#c0392b"); return
        path = os.path.join(BASE, "island_coords.json")
        try:
            with open(path, encoding="utf-8") as f:
                cur = json.load(f)
        except Exception as e:
            self._lr_msg.config(text=f"실패: {e}", fg="#c0392b"); return
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI", "backups")
        os.makedirs(d, exist_ok=True)
        now = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            shutil.copy2(path, os.path.join(d, f"{now}_before_restore_island_coords.json"))
        except Exception:
            pass
        names = []
        for r, _v in picks:
            new = json.loads(json.dumps(r["old"]))
            cs = cur.get(r["key"])
            if isinstance(cs, list):                       # 녹화는 지금 것 유지
                for i, sl in enumerate(new):
                    if not isinstance(sl, dict) or i >= len(cs) or not isinstance(cs[i], dict):
                        continue
                    for fld in ("recs", "recs_off"):
                        if fld in cs[i]:
                            sl[fld] = cs[i][fld]
                        else:
                            sl.pop(fld, None)
            cur[r["key"]] = new
            names.append(f"{r['key']}({r['src']:%m-%d %H:%M})")
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            self._lr_msg.config(text=f"쓰기 실패: {e}", fg="#c0392b"); return
        self._lr_msg.config(text=f"✔ 되돌렸습니다 — {', '.join(names)}\n"
                                 f"   녹화는 그대로. 직전 상태는 backups\\{now}_before_restore_* "
                                 f"에 백업했습니다. 런처를 다시 시작합니다…", fg="#1e8449")
        self.status.set(f"↩ 되돌림 — {', '.join(names)}")
        self.after(1500, self._restart_launcher)

    # ── 🔒 좌표 잠금 — 잠근 런처는 업데이트(git pull)가 절대 못 건드린다 ──
    #    (%LOCALAPPDATA%\MoonAI\coord_lock.json — 이 컴퓨터만의 파일)
    LOCK_ITEMS = [
        ("dragon_slots",   "🐲 용던고고!!!"),
        ("sched_slots",    "📅 스케줄"),
        ("dc_slots",       "🎯 일반던전충전"),
        ("doll_slots",     "🧸 인형탐험"),
        ("dollchk_slots",  "🧸 인형확인용"),
        ("relic_slots",    "🗿 성물확인용"),
        ("dungeon_slots",  "🏰 변신확인용"),
        ("fish_slots",     "🎣 낚시녹임"),
        ("market_slots",   "🔎 거래소검색"),
        ("coupon_slots",   "🎟 쿠폰등록"),
        ("circus_slots",   "🎪 서커스 이벤트등록"),
        ("circus2_slots",  "🎪 서커스 이벤트실행"),
        ("circus3_slots",  "🎪 서커스 이벤트퀘스트"),
        ("hunt_slots",     "🏹 사냥"),
        ("mail_slots",     "📬 우편함"),
        ("past_slots",     "🏝 과거섬"),
        ("item_slots",     "🧹 아이템정리"),
        ("pass_slots",     "🎫 패스권"),
        ("seq_slots",      "🔆 절전해제"),
        ("slp_slots",      "🌙 절전모드"),
        ("potion_area_rel", "🧪 물약색 영역"),
        ("check_area_rel", "⚠ 경고확인 영역"),
        ("scroll_area_rel", "📜 주문서 영역"),
    ]

    @staticmethod
    def _lock_path():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "coord_lock.json")

    def _lock_load(self):
        try:
            with open(self._lock_path(), encoding="utf-8") as f:
                d = json.load(f) or {}
            return set(d.get("keys") or []), set(d.get("island") or [])
        except Exception:
            return set(), set()

    def _lock_save(self, keys, island):
        try:
            with open(self._lock_path(), "w", encoding="utf-8") as f:
                json.dump({"_설명": "🔒 잠근 항목은 업데이트가 덮어쓰지 않는다 (이 컴퓨터만)",
                           "keys": sorted(keys), "island": sorted(island)},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.status.set(f"⚠ 잠금 저장 실패: {e}")

    def _open_lock_win(self):
        self._open_section_win("_lock_win", "🔒 좌표 잠금",
                               self._build_lock, w=560, h=640, pinnable=True)

    def _build_lock(self, parent):
        tk.Label(parent, text="🔒 좌표 잠금 — 잠근 것은 업데이트(git pull)가 절대 안 건드립니다",
                 font=("맑은 고딕", 10, "bold"), fg="#7b241c").pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(parent, text="잠그면 그 런처의 좌표는 이 컴퓨터 것이 원본이 됩니다.\n"
                              "(잠금은 이 컴퓨터에만 저장되고 GitHub와 무관합니다)",
                 font=("맑은 고딕", 8), fg="#555", justify="left").pack(anchor="w", padx=6)
        kl, il = self._lock_load()
        self._lock_vars = {}
        bar = tk.Frame(parent); bar.pack(fill="x", padx=6, pady=4)
        tk.Button(bar, text="🔒 전부 잠그기", font=("맑은 고딕", 9, "bold"),
                  bg="#c0392b", fg="white",
                  command=lambda: self._lock_all(True)).pack(side="left")
        tk.Button(bar, text="🔓 전부 풀기", font=("맑은 고딕", 9, "bold"),
                  bg="#7f8c8d", fg="white",
                  command=lambda: self._lock_all(False)).pack(side="left", padx=(6, 0))

        box = tk.LabelFrame(parent, text=" 런처 (coords.json) ", font=("맑은 고딕", 9, "bold"),
                            fg="#2c3e50")
        box.pack(fill="x", padx=6, pady=(4, 2))
        for n, (k, label) in enumerate(self.LOCK_ITEMS):
            v = tk.BooleanVar(value=(k in kl))
            self._lock_vars[("k", k)] = v
            tk.Checkbutton(box, text=label, variable=v, font=("맑은 고딕", 9),
                           anchor="w", command=self._lock_apply).grid(
                               row=n % 12, column=n // 12, sticky="w", padx=6, pady=1)
        box2 = tk.LabelFrame(parent, text=" 섬/던전 (island_coords.json) ",
                             font=("맑은 고딕", 9, "bold"), fg="#2c3e50")
        box2.pack(fill="x", padx=6, pady=(6, 2))
        try:
            dungeons = [k for k in (self._island_cfg() or {}) if not k.startswith("_")]
        except Exception:
            dungeons = list(self.ISLAND_KEYS)
        for n, k in enumerate(dungeons):
            v = tk.BooleanVar(value=(k in il))
            self._lock_vars[("i", k)] = v
            tk.Checkbutton(box2, text="🏝 " + k, variable=v, font=("맑은 고딕", 9),
                           anchor="w", command=self._lock_apply).grid(
                               row=n % 6, column=n // 6, sticky="w", padx=6, pady=1)
        self._lock_lbl = tk.Label(parent, text="", font=("맑은 고딕", 9, "bold"), fg="#7b241c")
        self._lock_lbl.pack(anchor="w", padx=6, pady=(6, 0))
        self._lock_refresh_lbl()

    def _lock_apply(self):
        keys = {k for (t, k), v in self._lock_vars.items() if t == "k" and v.get()}
        isl  = {k for (t, k), v in self._lock_vars.items() if t == "i" and v.get()}
        self._lock_save(keys, isl)
        self._lock_refresh_lbl()
        self._refresh_lock_btn()
        self.status.set(f"🔒 잠금 {len(keys) + len(isl)}개 저장 — 업데이트가 이 좌표는 안 건드립니다")

    def _lock_all(self, on):
        for v in self._lock_vars.values():
            v.set(bool(on))
        self._lock_apply()

    def _refresh_lock_btn(self):
        """잠근 게 있으면 버튼에 개수를 보여준다."""
        try:
            kl, il = self._lock_load()
            n = len(kl) + len(il)
            b = getattr(self, "_lock_btn", None)
            if b and b.winfo_exists():
                b.config(text=(f"🔒 잠금 {n}개" if n else "🔒 좌표잠금"),
                         bg=("#7b241c" if n else "#c0392b"))
        except Exception:
            pass

    def _lock_refresh_lbl(self):
        kl, il = self._lock_load()
        lb = getattr(self, "_lock_lbl", None)
        if lb and lb.winfo_exists():
            lb.config(text=(f"지금 잠긴 것: {len(kl) + len(il)}개"
                            + (f"  —  {', '.join(sorted(kl) + sorted(il))}" if (kl or il) else "")))

    # ── 🕐 컴퓨터 시계 맞추기 — 매주 수요일 05:00 한 번 ────────────────
    TIMESYNC_TASK = "LineageM_TimeSync"

    def _ensure_time_sync_task(self):
        """매주 수요일 새벽 5시에 시계를 인터넷 시각에 맞추는 예약 작업을 등록한다.
        (컴퓨터마다 시간이 달라 스케줄·2시간 반복이 어긋나는 것을 막는다)
        이미 있으면 아무것도 하지 않는다. 런처가 꺼져 있어도 예약이 돌아간다."""
        import subprocess
        try:
            q = subprocess.run(["schtasks", "/Query", "/TN", self.TIMESYNC_TASK],
                               capture_output=True, creationflags=0x08000000)
            if q.returncode == 0:
                return
            cmd = ["schtasks", "/Create", "/F", "/TN", self.TIMESYNC_TASK,
                   "/SC", "WEEKLY", "/D", "WED", "/ST", "05:00",
                   "/TR", "cmd /c w32tm /resync"]
            r = subprocess.run(cmd + ["/RL", "HIGHEST"], capture_output=True,
                               text=True, encoding="cp949", errors="replace",
                               creationflags=0x08000000)
            if r.returncode != 0:            # 권한이 없으면 일반 권한으로라도
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="cp949", errors="replace",
                                   creationflags=0x08000000)
            if r.returncode == 0:
                self.after(0, lambda: self.status.set(
                    "🕐 시계 맞춤 예약 등록 — 매주 수요일 05:00"))
            else:
                _m = ((r.stderr or "") + (r.stdout or "")).strip()[:80]
                self.after(0, lambda m=_m: self.status.set(f"⚠ 시계 맞춤 예약 등록 실패: {m}"))
        except Exception:
            pass

    def _rep_full_n(self, key, idx):
        """그 슬롯에 정해둔 반복 횟수 (없으면 6회)."""
        try:
            slot = self._island_cfg()[key][idx]
            return self._rep_hn(key, slot)[1]             # 슬롯 값 우선, 없으면 고정값
        except Exception:
            return 6

    def _rep_count(self):
        return sum(1 for k in self._rep_load() if not k.startswith("_"))

    def _rep_stop_all(self, quiet=False):
        """⏰ 2시간 N회 반복을 전부 끈다 — 멈췄다 재개하는 개념은 없다.
        예약 자체가 사라지므로 다시 하려면 섬/던전 실행기에서 ⏰를 다시 켜야 한다."""
        n = self._rep_count()
        if not n:
            return 0
        try:
            path = os.path.join(BASE, "island_coords.json")
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            for key in self.ISLAND_KEYS:
                for slot in cfg.get(key, []):
                    if isinstance(slot, dict) and slot.get("repeat_h"):
                        slot["repeat_h"] = 0
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            self._rep_log(f"⚠ 반복 종료 중 오류: {e!r}")
        # 사용자가 직접 껐다는 표시 — 런처를 다시 켜도 자동으로 되살리지 않는다
        self._rep_save({"_off": True})
        self._rep_log(f"반복 종료 — {n}개 슬롯의 ⏰ 전부 꺼짐"
                      + ("" if quiet else " (사용자)"))
        self._refresh_rep_btn()
        return n

    def _rep_stop_click(self):
        """[⏰ 반복] 버튼 — 묻지 않고 바로 끈다 (사용자 지시)."""
        n = self._rep_count()
        if not n:
            self.status.set("⏰ 켜져 있는 반복이 없습니다")
            return
        self._rep_stop_all()
        self.status.set(f"⏰ 반복 종료 — {n}개 슬롯 전부 꺼짐")

    def _refresh_stop_btn(self):
        """실행 중이면 빨강, 멈출 게 없으면 회색 (⏰ 반복 버튼과 같은 규칙)."""
        b = getattr(self, "btn_stop", None)
        if not b or not b.winfo_exists():
            return
        try:
            busy = self._is_busy()
        except Exception:
            busy = False
        if busy:
            b.config(bg="#c0392b", activebackground="#922b21")
        else:
            b.config(bg="#7f8c8d", activebackground="#5d6d7e")

    def _refresh_rep_btn(self):
        b = getattr(self, "btn_rep", None)
        if not b or not b.winfo_exists():
            return
        n = self._rep_count()
        if n:
            b.config(text="⏰ 반복" + chr(10) + f"종료 {n}",
                     bg="#c0392b", activebackground="#922b21")
        else:
            b.config(text="⏰ 반복" + chr(10) + "없음",
                     bg="#7f8c8d", activebackground="#5d6d7e")

    def _island_repeat_tick(self):
        try:
            self._island_repeat_check()
        except Exception as e:
            self._rep_log(f"⚠ 반복 관리 오류: {e!r}")
        self.after(60000, self._island_repeat_tick)

    def _island_repeat_check(self):
        self._refresh_rep_btn()
        cfg = self._island_cfg()
        st  = self._rep_load()
        now = time.time()
        changed = False
        due = []
        for di, key in enumerate(self.ISLAND_KEYS):
            for i, slot in enumerate(cfg.get(key, [])):
                if not isinstance(slot, dict):
                    continue
                h = slot.get("repeat_h") or 0
                k = f"{key}|{i}"
                if not h:
                    if k in st:
                        st.pop(k, None); changed = True
                    continue
                e = st.get(k)
                if not e:
                    # 설정만 있고 예약이 없으면 '꺼진 것'이다 — 여기서 켜지 않는다.
                    # 반복은 사용자가 실행했을 때만 걸린다 (2026-08-23 사용자 지시, 절대 규칙)
                    continue
                if e.get("h") != h:
                    e["h"] = h            # 주기만 맞춰준다 (시각·횟수는 그대로)
                    st[k] = e
                    changed = True
                elif now >= e.get("next", 0):
                    due.append((e["next"], di, key, i, h))
        if changed:
            self._rep_save(st)
        if not due:
            return
        if self._is_busy():          # 다른 작업 중이면 시각을 그대로 두고 다음 분에 재시도
            self.status.set(f"⏰ 반복 {len(due)}개 대기 — '{self._busy_label()}' 끝난 뒤 실행")
            self._rep_log(f"대기 — '{self._busy_label()}' 실행 중 (밀린 {len(due)}개)")
            return
        # 앞 실행이 끝난 지 얼마 안 됐으면 조금 더 기다린다 (겹침 방지 안전장치)
        _last = getattr(self, "_rep_last_start", 0)
        if time.time() - _last < 150:
            self._rep_log(f"대기 — 직전 실행 후 {int(time.time()-_last)}초 (밀린 {len(due)}개)")
            return
        self._rep_last_start = time.time()
        due.sort()                    # 가장 오래 밀린 것부터
        _, di, key, _i0, _h0 = due[0]
        # 같은 던전에서 '이미 차례 + 10분 안에 차례가 되는' 슬롯을 한 묶음으로 —
        # 하나씩 돌리면 16슬롯에 40분 넘게 걸리지만, 웨이브(번갈아)면 5~6분이면 끝난다.
        WINDOW = 600
        batch = []
        for kk, ee in st.items():
            if kk.startswith("_"):
                continue
            bkey, bi = kk.rsplit("|", 1)
            if bkey != key:
                continue
            if ee.get("next", 0) <= now + WINDOW:
                batch.append((int(bi), ee, int(ee.get("h") or 2)))
        batch.sort()
        names = []
        for bi, e, h in batch:
            kk = f"{key}|{bi}"
            e["left"] = int(e.get("left", 1)) - 1
            e["run"]  = int(e.get("run", 0)) + 1      # 이번이 몇 회차인지 (물약 교체용)
            if e["left"] <= 0 and key in self.REPEAT_FIXED:
                # 고정 던전 — 횟수를 다 채우면 끄지 않고 처음부터 다시
                e["left"] = self._rep_full_n(key, bi)
                e["run"]  = 0                          # 다음 실행이 다시 1회차
                e["next"] = now + self._rep_delay(h)
                st[kk] = e
                self._rep_log(f"{key} #{bi+1:02d} 마지막 회차 실행 — 고정이라 "
                              f"{e['left']}회로 다시 채움")
            elif e["left"] <= 0:
                st.pop(kk, None)
                self._rep_turn_off(key, bi)
                self._rep_log(f"{key} #{bi+1:02d} 마지막 회차 실행 (반복 종료)")
            else:
                e["next"] = now + self._rep_delay(h)
                st[kk] = e
                self._rep_log(f"{key} #{bi+1:02d} 실행 (남은 {e['left']}회)")
            names.append(bi)
        self._rep_save(st)
        if len(names) > 1:
            self._rep_log(f"{key} — {len(names)}슬롯 웨이브(번갈아) 묶음 실행: "
                          + ",".join(str(x + 1) for x in names))
            self.status.set(f"⏰ {key} {len(names)}슬롯 반복 자동 실행 (번갈아)")
        else:
            self.status.set(f"⏰ {key} #{names[0]+1:02d} 반복 자동 실행")
        self._run_island_repeat(di, names)

    def _run_island_repeat(self, didx, sidxs):
        """반복 차례가 된 슬롯들을 섬/던전 실행기로 돌린다.
        여러 개면 --slots 로 넘겨 웨이브(번갈아)로 한 번에 처리한다."""
        self._island_step_back()
        cmd = [r"pythonw", os.path.join(BASE, "lineagem_island.py"), str(didx), "--run"]
        if len(sidxs) > 1:
            # 반복은 슬롯 번호 순서 그대로 '2개씩' — 동시에 도는 창을 줄여 더 안전하게
            cmd += ["--slots", ",".join(str(i + 1) for i in sorted(sidxs)), "--lanes", "2"]
        else:
            cmd += ["--slot", str(sidxs[0] + 1)]
        proc = subprocess.Popen(cmd)
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _island_step_back(self):
        """섬/던전 실행 시작 — 최소화하지 말고 '맨 뒤'로만 물러난다 (2026-08-09 사용자 지시).
        최소화하면 다시 꺼내기가 번거로워서, 메인런처도 섬 실행기도 맨 뒤로만 간다."""
        for w in self._section_wins():
            try: w.iconify()
            except Exception: pass
        self._send_to_back()
        self._minimize_claude()

    def _run_island_slot(self, idx):
        """해당 던전 단독창 열고 자동 실행."""
        if self._is_busy():
            self._enqueue(f"섬/던전 #{idx+1:02d}", lambda: self._run_island_slot(idx)); return
        self._island_step_back()
        proc = subprocess.Popen([r"pythonw", os.path.join(BASE, "lineagem_island.py"), str(idx), "--run"])
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()

    def _open_sched_win(self):
        self._open_section_win("_sched_win", "📅 매일매일 스케줄", self._build_sched, w=470, h=620)

    def _open_dungeon_win(self):
        self._open_section_win("_dungeon_win", "🏰 변신확인용", self._build_dungeon, w=470, h=600, pinnable=True)

    def _open_daya_win(self):
        self._open_section_win("_daya_win", "💰 다야 카운트", self._build_daya_panel, w=500, h=260)

    def _build_daya_panel(self, parent):
        cnt_box = tk.Frame(parent); cnt_box.pack(padx=8, pady=8, fill="both", expand=True)
        tk.Label(cnt_box, text="현재 다야 수량",
                 font=("맑은 고딕", 14, "bold"), fg="#2c3e50").grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        tk.Button(cnt_box, text="📊 OCR", font=("맑은 고딕", 7, "bold"), bg="#27ae60", fg="white",
                  width=8, command=self._open_ocr).grid(row=0, column=2, columnspan=2, sticky="w", padx=2)
        tk.Button(cnt_box, text="📋 복사", font=("맑은 고딕", 7, "bold"), bg="#2471a3", fg="white",
                  width=8, command=self._copy_daya_counts).grid(row=0, column=4, columnspan=2, sticky="w", padx=2)
        tk.Label(cnt_box, textvariable=self._cnt_total_var,
                 font=("맑은 고딕", 14, "bold"), fg="#c0392b").grid(row=0, column=6, columnspan=4, sticky="e", padx=4)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(cnt_box, bd=1, relief="flat", width=70, height=44)
                cell.grid(row=r+1, column=c, padx=2, pady=2)
                cell.pack_propagate(False)
                tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 10), fg="#aaa").pack()
                tk.Label(cell, textvariable=self._cnt_cell_vars[idx],
                         font=("맑은 고딕", 14, "bold"), fg="#2980b9").pack()

    def _make_cnt_loader(self):
        import datetime as _dt
        count_file = os.path.join(LOCAL_DATA, "daya_counts.json")
        def load():
            try:
                with open(count_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return load

    def _make_today_fn(self):
        import datetime as _dt
        return lambda: _dt.date.today().isoformat()

    def _copy_daya_counts(self):
        values = [v.get().replace(",", "").replace("-", "0") for v in self._cnt_cell_vars]
        rows = ["\t".join(values[r*4:(r+1)*4]) for r in range(4)]
        text = "\n".join(rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("✔ 다야 수량 클립보드 복사 완료 — 엑셀에 붙여넣기 하세요")

    def _refresh_count(self):
        data = self._cnt_load()
        # 가장 최근 날짜 데이터를 항상 표시 (OCR 실행 시만 갱신됨)
        if not data:
            day_data = {}
        else:
            latest_day = max(data.keys())
            day_data = data.get(latest_day, {})
        total = 0
        for i in range(16):
            v = day_data.get(str(i), 0)
            self._cnt_cell_vars[i].set(f"{v:,}" if v else "-")
            total += v
        self._cnt_total_var.set(f"합계: {total:,}")
        self._daya_track_total(total)
        self._load_daya_thumbs()

    def _daya_track_total(self, total):
        """합계 변경 감지 → 30분 뒤 시점의 합계를 '확정' 기록 (그 사이 수동 수정 반영).
        확정 기록으로 [측정일시 / 합계 / 직전 대비 차이]를 표시한다."""
        import datetime as _dt
        hp = os.path.join(LOCAL_DATA, "daya_history.json")
        if not hasattr(self, "_daya_hist"):
            try:
                with open(hp, encoding="utf-8") as f:
                    self._daya_hist = json.load(f)
            except Exception:
                self._daya_hist = {"entries": []}
            self._daya_pending = None
            self._daya_seen_total = total   # 시작 시점 합계 (변경 감지 기준)
        # 합계 변경 감지 → 확정 대기 시작 (이미 대기 중이면 시작시각 유지)
        if total != self._daya_seen_total:
            self._daya_seen_total = total
            if self._daya_pending is None:
                self._daya_pending = {"start": time.time()}
        # 10분 경과 → 현재 합계로 확정 (그 사이 수동 수정 반영)
        if self._daya_pending and time.time() - self._daya_pending["start"] >= 600:
            ents = self._daya_hist["entries"]
            start_ts = self._daya_pending["start"]
            if ents and start_ts - ents[-1]["ts"] < 3600:
                ents[-1]["total"] = total          # 1시간 내 재변경은 같은 측정의 수정으로 봄
            else:
                ents.append({"ts": start_ts, "total": total})
            self._daya_hist["entries"] = ents[-30:]   # 최근 30개만 보관
            try:
                with open(hp, "w", encoding="utf-8") as f:
                    json.dump(self._daya_hist, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            self._daya_pending = None
        # 표시 갱신: 📅 측정일시(즉시 표기) / 차이(직전 확정 대비 — 새 측정 시 바로 잠정 표기)
        ents = self._daya_hist["entries"]
        pend = self._daya_pending
        if pend:
            when = _dt.datetime.fromtimestamp(pend["start"]).strftime("%m/%d %H:%M")
            self._cnt_date_var.set(f"📅 {when} 측정 ⏳")
            base = None
            if ents:
                merging = pend["start"] - ents[-1]["ts"] < 3600   # 직전 측정의 수정으로 병합될 건
                if merging:
                    base = ents[-2] if len(ents) >= 2 else None
                else:
                    base = ents[-1]
            self._cnt_diff_var.set(f"차이: {total - base['total']:+,}" if base else "")
        elif ents:
            when = _dt.datetime.fromtimestamp(ents[-1]["ts"]).strftime("%m/%d %H:%M")
            self._cnt_date_var.set(f"📅 {when} 측정")
            if len(ents) >= 2:
                diff = ents[-1]["total"] - ents[-2]["total"]
                self._cnt_diff_var.set(f"차이: {diff:+,}")
            else:
                self._cnt_diff_var.set("")
        else:
            self._cnt_date_var.set("📅 측정 기록 없음")
            self._cnt_diff_var.set("")

    def _load_daya_thumbs(self):
        """daya_crops/slot_i.png (OCR가 캡처한 숫자 이미지)을 각 셀에 표시."""
        labels = getattr(self, "_cnt_img_labels", None)
        if not labels:
            return
        try:
            from PIL import Image, ImageTk
        except Exception:
            return
        crop_dir = os.path.join(LOCAL_DATA, "daya_crops")
        for i, lbl in enumerate(labels):
            p = os.path.join(crop_dir, f"slot_{i}.png")
            try:
                if os.path.exists(p):
                    with Image.open(p) as _im0:
                        im = _im0.copy()
                    scale = 30.0 / max(im.height, 1)          # 기존 20px → 1.5배(30px)
                    w = max(1, min(180, int(im.width * scale)))
                    im = im.resize((w, 30), Image.LANCZOS)
                    ph = ImageTk.PhotoImage(im)
                    self._cnt_thumbs[i] = ph            # 참조 유지
                    lbl.config(image=ph, text="")
                else:
                    lbl.config(image="", text="-")
            except Exception:
                pass

    def _rescan_daya_slot(self, idx):
        """해당 슬롯 하나만 다야 OCR 재측정 (별도 프로세스 --slot)."""
        if self._is_busy():
            self._enqueue(f"다야 재측정 #{idx+1:02d}", lambda: self._rescan_daya_slot(idx)); return
        import subprocess, sys
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        self.status.set(f"🔎 #{idx+1:02d} 다야 재측정 중... (OCR 로딩 포함 잠시)")
        # 런처/클로드가 게임(숫자 영역)을 가리지 않게 최소화하고 실행
        self._minimize_all()
        try:
            proc = subprocess.Popen([exe, os.path.join(BASE, "lineagem_ocr.py"), "--slot", str(idx)])
        except Exception as e:
            self.deiconify()
            self.status.set(f"재측정 실행 오류: {e}"); return
        self._ocr_proc = proc   # busy 락이 인식 → 다른 작업과 겹침 방지
        threading.Thread(target=self._watch_rescan, args=(proc, idx), daemon=True).start()

    def _watch_rescan(self, proc, idx):
        try:
            proc.wait()
        except Exception:
            pass
        def _done():
            self._restore_back()            # 앞으로 올리지 않고 맨 뒤로 복원 (클라 안 가림)
            self._refresh_count()           # 숫자 + 캡처 사진(썸네일) 갱신
            self.status.set(f"✔ #{idx+1:02d} 다야 재측정 완료")
        self.after(0, _done)

    def _edit_daya_count(self, idx):
        """다야 수량 숫자를 클릭 → 손으로 수정 (OCR 오표기 보정)."""
        from tkinter import simpledialog
        cur_txt = self._cnt_cell_vars[idx].get().replace(",", "")
        try:
            cur = int(cur_txt) if cur_txt not in ("", "-", "?") else 0
        except Exception:
            cur = 0
        val = simpledialog.askinteger(
            "다야 수량 수정", f"#{idx+1:02d} 다야 수량을 입력하세요\n(캡처 이미지를 보고 맞는 숫자로)",
            initialvalue=cur, minvalue=0, parent=self)
        if val is None:
            return   # 취소
        self._save_daya_count_manual(idx, val)
        self._refresh_count()
        self.status.set(f"✔ #{idx+1:02d} 다야 수량 수동 수정: {val:,}")

    def _save_daya_count_manual(self, idx, val):
        """daya_counts.json의 최신 날짜 데이터에 수정값을 기록(표시와 동일한 날짜)."""
        p = os.path.join(LOCAL_DATA, "daya_counts.json")
        try:
            with open(p, encoding="utf-8") as f:
                counts = json.load(f)
        except Exception:
            counts = {}
        import datetime as _dt
        day = max(counts.keys()) if counts else _dt.date.today().isoformat()
        counts.setdefault(day, {})[str(idx)] = val
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(counts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.status.set(f"저장 오류: {e}")

    def _schedule_count_refresh(self):
        self._refresh_count()
        self.after(30000, self._schedule_count_refresh)  # 30초마다 자동갱신

    def _preview_coord(self, x, y):
        """마우스를 해당 좌표로 이동해서 위치 미리보기"""
        import threading as _th
        def _move():
            try:
                pyautogui.moveTo(x, y, duration=0.25)
            except Exception:
                pass
        self.status.set(f"미리보기: ({x},{y}) — 마우스가 해당 위치로 이동합니다")
        _th.Thread(target=_move, daemon=True).start()

    def _build_left(self, parent):
        # 좌표 등록
        tk.Label(parent, text="좌표 등록  (버튼 → 3초 후 해당 위치 클릭)",
                 font=("맑은 고딕", 8), fg="#888").pack(anchor="w", padx=4)
        self._coord_vars = {}
        for key, label in LABELS.items():
            row = tk.Frame(parent); row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=label, font=("맑은 고딕", 8),
                     width=18, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._coord_vars[key] = var
            tk.Label(row, textvariable=var, font=("맑은 고딕", 7),
                     fg="gray", width=12).pack(side="left")
            tk.Button(row, text="등록", font=("맑은 고딕", 7),
                      command=lambda k=key: self._reg_coord(k)).pack(side="right")
            tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                      command=lambda k=key: self._preview_label_coord(k)).pack(side="right", padx=1)

        # 프로필 아이디 OCR 설정
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)
        area_row = tk.Frame(parent); area_row.pack(fill="x", padx=4, pady=2)
        tk.Label(area_row, text="아이디 표시 영역", font=("맑은 고딕", 8), width=18, anchor="w").pack(side="left")
        self._profile_area_var = tk.StringVar(value="등록됨" if self.cfg.get("profile_id_area") else "미등록")
        tk.Label(area_row, textvariable=self._profile_area_var, font=("맑은 고딕", 7), fg="gray", width=12).pack(side="left")
        tk.Button(area_row, text="등록", font=("맑은 고딕", 7),
                  command=self._reg_profile_id_area).pack(side="right")
        tk.Button(area_row, text="테스트", font=("맑은 고딕", 7), bg="#7d3c98", fg="white",
                  command=self._test_profile_ocr).pack(side="right", padx=2)
        tk.Button(area_row, text="🖼기준등록", font=("맑은 고딕", 7), bg="#1e8449", fg="white",
                  command=self._reg_profile_ref).pack(side="right", padx=2)

        pid_row = tk.Frame(parent); pid_row.pack(fill="x", padx=4, pady=2)
        tk.Label(pid_row, text="사용할 아이디", font=("맑은 고딕", 8), width=18, anchor="w").pack(side="left")
        self._profile_target_var = tk.StringVar(value=self.cfg.get("profile_target_id", ""))
        tk.Entry(pid_row, textvariable=self._profile_target_var, font=("맑은 고딕", 8),
                 fg="#2471a3", width=14).pack(side="left")
        def _save_pid():
            self.cfg["profile_target_id"] = self._profile_target_var.get().strip()
            save_cfg(self.cfg)
            self.status.set(f"✔ 아이디 저장: '{self.cfg['profile_target_id']}'")
        tk.Button(pid_row, text="저장", font=("맑은 고딕", 7), bg="#2471a3", fg="white",
                  command=_save_pid).pack(side="left", padx=2)

        # 🔍 퍼플 확인 테스트 — 새벽 4시 자동 전환+최소화 로직을 지금 수동으로 1회 실행
        test_row = tk.Frame(parent); test_row.pack(fill="x", padx=4, pady=(0, 2))
        tk.Button(test_row, text="🔍 퍼플 확인 테스트 (4시 로직 지금 실행)",
                  font=("맑은 고딕", 8), bg="#7d3c98", fg="white",
                  command=lambda: threading.Thread(
                      target=self._purple_check_worker, daemon=True).start()
                  ).pack(fill="x")

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)

        # 캐릭터 접속 버튼
        char_hdr = tk.Frame(parent); char_hdr.pack(fill="x", padx=4, pady=1)
        self._char_count_var = tk.StringVar()
        tk.Label(char_hdr, text="캐릭터 접속 버튼", font=("맑은 고딕", 9, "bold")).pack(side="left")
        tk.Label(char_hdr, textvariable=self._char_count_var,
                 font=("맑은 고딕", 8), fg="#c8a951").pack(side="left", padx=4)
        tk.Button(char_hdr, text="+ 추가", font=("맑은 고딕", 7),
                  command=self._reg_char_btn).pack(side="right")
        tk.Button(char_hdr, text="전체삭제", font=("맑은 고딕", 7), fg="red",
                  command=self._clear_char_btns).pack(side="right", padx=2)
        # 캐릭터 버튼 목록 (동적)
        self._char_rows_frame = tk.Frame(parent)
        self._char_rows_frame.pack(fill="x", padx=4)

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=3)

        # 클릭 슬롯
        tk.Label(parent, text="클릭 등록  (슬롯당 2번 클릭 등록 / 3초 간격)",
                 font=("맑은 고딕", 8), fg="#888").pack(anchor="w", padx=4)

        self._slot_vars = []
        for g in range(CLICK_SLOTS // GROUP_SIZE):
            grp = tk.LabelFrame(parent,
                                text=f"그룹 {g+1}  ({g*GROUP_SIZE+1}~{(g+1)*GROUP_SIZE}번)",
                                font=("맑은 고딕", 7), padx=2, pady=1)
            grp.pack(fill="x", padx=4, pady=1)
            for i in range(GROUP_SIZE):
                idx = g * GROUP_SIZE + i
                row = tk.Frame(grp); row.pack(fill="x", pady=2)
                tk.Label(row, text=f"#{idx+1:02d}", font=("맑은 고딕", 8, "bold"),
                         width=4).pack(side="left", padx=(2,0))
                var = tk.StringVar()
                self._slot_vars.append(var)
                tk.Label(row, textvariable=var, font=("맑은 고딕", 7),
                         fg="gray", width=16).pack(side="left", padx=(2,4))
                # 왼쪽부터: ①②(개별등록) — 오른쪽부터: 등록 삭제 👁 ↑복사
                if idx > 0:
                    tk.Button(row, text="↑그룹복사", font=("맑은 고딕", 7), width=6,
                              command=lambda x=idx: self._group_copy_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="👁", font=("맑은 고딕", 7), width=2,
                          command=lambda x=idx: self._preview_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="삭제", font=("맑은 고딕", 7), fg="#c0392b",
                          command=lambda x=idx: self._del_slot(x)).pack(side="right", padx=(0,2))
                tk.Button(row, text="전체등록", font=("맑은 고딕", 7),
                          command=lambda x=idx: self._reg_slot(x)).pack(side="right", padx=(0,4))
                tk.Button(row, text="②등록", font=("맑은 고딕", 7), width=5,
                          command=lambda x=idx: self._reg_slot_step(x, 1)).pack(side="left", padx=(0,2))
                tk.Button(row, text="①등록", font=("맑은 고딕", 7), width=5,
                          command=lambda x=idx: self._reg_slot_step(x, 0)).pack(side="left", padx=(0,2))
                if idx == 4:
                    tk.Button(row, text="③등록", font=("맑은 고딕", 7), width=5,
                              command=lambda x=idx: self._reg_slot_step(x, 2)).pack(side="left", padx=(0,2))

        # 클릭 실행 버튼
        cr = tk.Frame(parent); cr.pack(pady=4)
        self.btn_click_run = tk.Button(cr, text="▶  클릭 실행 (32번)",
            font=("맑은 고딕", 9, "bold"), bg="#2980b9", fg="white",
            activebackground="#1a5e8a", width=16, height=2, command=self._start_click)
        self.btn_click_run.pack(side="left", padx=(0, 3))
        self.btn_click_stop = tk.Button(cr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_click_stop", True) or
                            self.status.set("클릭 멈추는 중..."),
            state="disabled")
        self.btn_click_stop.pack(side="left")

    def _build_winmgmt(self, parent):
        """배열창 재배치 — 좌측 전체 관리 버튼 열 + 슬롯별(01~16) 개별 재배치 그리드.
        그리드는 세로(열 우선) 번호: 01~04가 첫 열, 05~08이 둘째 열…"""
        # 좌측: 전체 창 관리 버튼 열 (다야 수량 컨트롤 열과 동일 형식)
        ctrl = tk.Frame(parent); ctrl.pack(side="left", padx=(4,8), anchor="n")
        tk.Label(ctrl, text="🪟 배열창 재배치", font=("맑은 고딕", 9, "bold"),
                 fg="#2c3e50").pack(anchor="w")
        for text, color, cmd in [
            ("📍 위치 전체저장", "#5d6d7e", self._save_all_window_pos),
            ("📐 창 전체복원",   "#1a5276", self._restore_all_windows),
            ("🔢 번호 재지정",   "#7d3c98", self._renumber_windows),
            ("📷 이름 영역등록", "#b7770d", self._reg_name_area),
            ("🔍 이름 자동인식", "#1e8449", self._ocr_all_names),
        ]:
            tk.Button(ctrl, text=text, font=("맑은 고딕", 7, "bold"),
                      bg=color, fg="white", width=12,
                      command=cmd).pack(fill="x", pady=1)

        # 우측: 슬롯별 재배치 그리드 (세로 번호 배치)
        wg = tk.Frame(parent); wg.pack(side="left", anchor="n")
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg); cell.grid(row=r, column=c, padx=6, pady=5)
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#888").pack()
            tk.Button(cell, text="재배치", font=("맑은 고딕", 7, "bold"),
                      bg="#1a5276", fg="white", width=6,
                      command=lambda x=idx: self._restore_single_window(x)).pack()

    def _build_return_grid(self, parent):
        """귀환주문서 슬롯별 실행 그리드 (좌표는 섬/던전 실행기에서 관리, 여기선 실행만).
        배열창 재배치와 동일한 세로(열 우선) 번호 배치."""
        hd = tk.Frame(parent); hd.pack(anchor="w", pady=(0, 2))
        tk.Label(hd, text="📜 귀환주문서", font=("맑은 고딕", 9, "bold"),
                 fg="#2c3e50").pack(side="left")
        tk.Button(hd, text="▶ 선택실행", font=("맑은 고딕", 8, "bold"),
                  bg="#1e8449", fg="white",
                  command=self._run_return_sel).pack(side="left", padx=(6, 0))
        tk.Button(hd, text="선택해제", font=("맑은 고딕", 8),
                  bg="#95a5a6", fg="white",
                  command=self._return_sel_clear).pack(side="left", padx=(4, 0))
        wg = tk.Frame(parent); wg.pack(anchor="w")
        self._return_plus = []
        self._return_sel = set()
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg); cell.grid(row=r, column=c, padx=6, pady=4)
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#888").pack()
            tk.Button(cell, text="실행", font=("맑은 고딕", 7, "bold"),
                      bg="#c0392b", fg="white", width=6,
                      command=lambda x=idx: self._run_return_slot(x)).pack()
            pb = tk.Button(cell, text="+", font=("맑은 고딕", 7, "bold"), width=6,
                           bg="#dfe3e6", fg="#e67e22",
                           command=lambda x=idx: self._return_sel_toggle(x))
            pb.pack(pady=(1, 0))
            self._return_plus.append(pb)

    def _return_sel_toggle(self, idx):
        sel = getattr(self, "_return_sel", None)
        if sel is None:
            sel = self._return_sel = set()
        sel.discard(idx) if idx in sel else sel.add(idx)
        self._refresh_return_plus()

    def _return_sel_clear(self):
        self._return_sel = set()
        self._refresh_return_plus()
        self.status.set("선택 해제")

    def _refresh_return_plus(self):
        sel = getattr(self, "_return_sel", set())
        for i, b in enumerate(getattr(self, "_return_plus", []) or []):
            try:
                on = i in sel
                b.config(text="✔" if on else "+",
                         bg="#e67e22" if on else "#dfe3e6",
                         fg="white" if on else "#e67e22")
            except Exception:
                pass
        self.status.set(f"귀환주문서 선택 {sorted(i+1 for i in sel)}" if sel else "선택 없음")

    def _run_return_sel(self):
        """+ 로 고른 슬롯들만 차례로 — 고른 게 없으면 좌표가 있는 전체."""
        if getattr(self, "_return_running", False):
            self.status.set("귀환주문서 실행 중입니다"); return
        try:
            slots = self._island_cfg().get("귀환주문서", [])
        except Exception:
            self.status.set("island_coords.json 을 찾을 수 없습니다"); return
        sel = sorted(getattr(self, "_return_sel", set()))
        if not sel:                      # 아무것도 안 골랐으면 실행하지 않는다
            self.status.set("📜 귀환주문서 — 슬롯을 고르세요 ([+] 를 눌러 선택)"); return
        todo = [(i, slots[i]) for i in sel
                if i < len(slots) and any(slots[i].get("coords") or [])]
        if not todo:
            self.status.set("귀환주문서 — 고른 슬롯에 등록된 좌표가 없습니다"); return
        if not self._try_busy_or_queue("귀환주문서", self._run_return_sel,
                                       label=f"귀환주문서 {len(todo)}칸"): return
        self._return_running = True
        self._return_stop    = False
        self.status.set(f"2초 후 귀환주문서 {[i+1 for i, _ in todo]}번 실행...")
        self._minimize_all()
        threading.Thread(target=self._run_task,
                         args=("귀환주문서", self._run_return_many, todo), daemon=True).start()

    def _run_return_many(self, todo):
        """고른 슬롯들을 차례로 실행 (슬롯 사이 2~4초)."""
        self._return_batch = True
        try:
            for n, (i, slot) in enumerate(todo):
                if getattr(self, "_return_stop", False):
                    break
                self._return_running = True
                self._run_return_worker(slot.get("name", f"#{i+1}"),
                                        slot.get("coords", []))
                if n < len(todo) - 1:
                    time.sleep(random.uniform(2.0, 4.0))
        finally:
            self._return_batch = False
            self._return_running = False
            self.after(0, self._raise_main)

    NIGHT_KEY = "토요일_악몽의섬"      # 메인런처에서 슬롯별로 다루는 던전 (탭으로 바뀐다)
    NIGHT_DIDX = 1                     # 섬/던전 실행기의 던전 번호 (0오만 1악몽 2잊섬 3에카)
    # 슬롯별 실행판에서 다루는 던전들 (2026-08-24 — 악몽의섬처럼 넷 다 개별 실행)
    DUN_TABS = [(1, "악몽의섬", "토요일_악몽의섬", "#8e44ad"),
                (3, "에카",     "화요일_에카",     "#27ae60"),
                (2, "잊혀진섬", "월요일_잊혀진섬", "#2980b9"),
                (0, "오만의탑", "수금_오만의탑",   "#e67e22")]

    def _dun_switch(self, tab_i):
        """슬롯판에서 다룰 던전을 바꾼다 (좌표·설정은 각 던전 창 그대로)."""
        didx, label, key, col = self.DUN_TABS[tab_i]
        self.NIGHT_DIDX, self.NIGHT_KEY = didx, key
        self.cfg["night_tab"] = tab_i
        try: save_cfg(self.cfg)
        except Exception: pass
        for i, b_ in enumerate(getattr(self, "_dun_tabs", []) or []):
            on = (i == tab_i)
            try:
                b_.config(bg=self.DUN_TABS[i][3] if on else "#3a4149",
                          fg="white" if on else "#9aa4b0")
            except Exception:
                pass
        try:
            self._night_title.config(text=f"🏝 {label}", fg=col)
        except Exception:
            pass
        self._night_sel = set()
        self._night_queue = []
        self._refresh_night_plus()
        self._refresh_night_btns()
        self._refresh_night_queue()
        self.status.set(f"슬롯판 — {label} (좌표·설정은 그 던전 창에서)")

    def _build_night_grid(self, parent):
        """악몽의섬 슬롯별 [실행] + [⏰끄기] + [+선택] — 좌표·반복은 섬/던전 실행기에서 관리."""
        hd = tk.Frame(parent); hd.pack(anchor="w", pady=(0, 2))
        self._night_title = tk.Label(hd, text="🏝 악몽의섬",
                                     font=("맑은 고딕", 9, "bold"), fg="#8e44ad")
        self._night_title.pack(side="left")
        tk.Button(hd, text="✔ 전체선택", font=("맑은 고딕", 8, "bold"),
                  bg="#e67e22", fg="white", activebackground="#ca6f1e",
                  command=self._night_sel_all).pack(side="left", padx=(6, 0))
        tk.Button(hd, text="▶ 선택실행", font=("맑은 고딕", 8, "bold"),
                  bg="#1e8449", fg="white",
                  command=self._run_night_sel).pack(side="left", padx=(4, 0))
        tk.Button(hd, text="선택해제", font=("맑은 고딕", 8),
                  bg="#95a5a6", fg="white",
                  command=lambda: self._night_sel_clear()).pack(side="left", padx=(4, 0))
        # 던전 고르기 탭 — 넷 다 슬롯별로 실행할 수 있다 (2026-08-24)
        tb = tk.Frame(parent); tb.pack(anchor="w", pady=(0, 2))
        self._dun_tabs = []
        for i, (didx, label, key, col) in enumerate(self.DUN_TABS):
            b_ = tk.Button(tb, text=label, font=("맑은 고딕", 8, "bold"),
                           bg="#3a4149", fg="#9aa4b0", bd=0, padx=6, pady=2,
                           command=lambda k=i: self._dun_switch(k))
            b_.pack(side="left", padx=(0, 3))
            self._dun_tabs.append(b_)

        # 반복을 16슬롯 전부 '지금부터' 다시 건다 (실행은 하지 않는다) — 제목 아랫줄
        rr2 = tk.Frame(parent); rr2.pack(anchor="w", pady=(0, 3))
        tk.Button(rr2, text="🔄 초기화 (4h→2h 6회)", font=("맑은 고딕", 8, "bold"),
                  bg="#196f3d", fg="white", activebackground="#145a32",
                  command=lambda: self._night_rearm_all(True)).pack(side="left")
        tk.Button(rr2, text="⏰ 2h 6회", font=("맑은 고딕", 8, "bold"),
                  bg="#1f618d", fg="white", activebackground="#154360",
                  command=lambda: self._night_rearm_all(False)).pack(side="left", padx=(3, 0))
        tk.Label(parent, text="16슬롯 전부 기본값으로 (토요일 지나면 자동으로도) · "
                              "슬롯 하나만은 아래 칸 클릭",
                 font=("맑은 고딕", 7), fg="#888").pack(anchor="w", pady=(0, 3))
        wg = tk.Frame(parent); wg.pack(anchor="w")
        self._night_btns = []; self._night_plus = []; self._night_runbtns = []
        self._night_firstbtns = []      # 첫 회차 4시간/2시간 선택
        self._night_sel = set()
        self._night_queue = []          # 눌러둔 슬롯을 쌓아두고 하나씩 실행
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg); cell.grid(row=r, column=c, padx=5, pady=3)
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 7), fg="#888").pack()
            xb = tk.Button(cell, text="실행", font=("맑은 고딕", 7, "bold"),
                           bg="#2471a3", fg="white", width=6,
                           command=lambda x=idx: self._run_night_slot(x))
            xb.pack()
            self._night_runbtns.append(xb)
            rr = tk.Frame(cell); rr.pack(pady=(1, 0))
            rb = tk.Button(rr, text="⏰", font=("맑은 고딕", 7, "bold"),
                           bg="#7f8c8d", fg="white", width=4,
                           command=lambda x=idx: self._night_rep_off(x))
            rb.pack(side="left")
            self._night_btns.append(rb)
            # ✕ — 이 슬롯의 반복만 취소 (다시 켜지 않는다)
            cb = tk.Button(rr, text="✕", font=("맑은 고딕", 8, "bold"),
                           bg="#c0392b", fg="white", activebackground="#922b21",
                           width=1, command=lambda x=idx: self._night_rep_cancel(x))
            cb.pack(side="left", padx=(1, 0))
            # 첫 회차 시간 고르기 — [4h→2h] ↔ [2h만]
            fb = tk.Button(cell, font=("맑은 고딕", 7, "bold"), width=6,
                           command=lambda x=idx: self._night_first_toggle(x))
            fb.pack(pady=(1, 0))
            self._night_firstbtns.append(fb)
            pb = tk.Button(cell, text="+", font=("맑은 고딕", 7, "bold"), width=6,
                           bg="#dfe3e6", fg="#e67e22",
                           command=lambda x=idx: self._night_sel_toggle(x))
            pb.pack(pady=(1, 0))
            self._night_plus.append(pb)
        self.after(300, lambda: self._dun_switch(int(self.cfg.get("night_tab", 0) or 0)))
        self.after(1200, self._refresh_night_btns)
        self._night_week_start()      # 토요일 00시 자동 초기화 감시

    def _night_sel_toggle(self, idx):
        """+ 로 고른 슬롯만 [선택실행]으로 한 번에 돌린다."""
        sel = getattr(self, "_night_sel", None)
        if sel is None:
            sel = self._night_sel = set()
        if idx in sel:
            sel.discard(idx)
        else:
            sel.add(idx)
        self._refresh_night_plus()

    def _night_sel_all(self):
        """좌표가 등록된 슬롯을 전부 선택한다 (실행은 [▶ 선택실행] 을 눌러야 시작).
        이미 전부 선택돼 있으면 해제 — 한 버튼으로 켜고 끈다."""
        try:
            slots = self._island_cfg().get(self.NIGHT_KEY) or []
        except Exception:
            slots = []
        able = {i for i, s_ in enumerate(slots)
                if isinstance(s_, dict) and any(s_.get("coords") or [])}
        if not able:
            self.status.set("악몽의섬 — 좌표가 등록된 슬롯이 없습니다"); return
        cur = getattr(self, "_night_sel", set()) or set()
        self._night_sel = set() if cur >= able else set(able)
        self._refresh_night_plus()
        if self._night_sel:
            self.status.set(f"악몽의섬 {len(able)}개 슬롯 전체선택 — "
                            f"[▶ 선택실행] 을 누르면 시작합니다")

    def _night_sel_clear(self):
        self._night_sel = set()
        self._refresh_night_plus()
        self.status.set("선택 해제")

    def _refresh_night_plus(self):
        sel = getattr(self, "_night_sel", set())
        for i, b in enumerate(getattr(self, "_night_plus", []) or []):
            try:
                on = i in sel
                b.config(text="✔" if on else "+",
                         bg="#e67e22" if on else "#dfe3e6",
                         fg="white" if on else "#e67e22")
            except Exception:
                pass
        self.status.set(f"악몽의섬 선택 {sorted(i+1 for i in sel)}" if sel else "선택 없음")

    def _run_night_sel(self):
        """+ 로 고른 슬롯들만 웨이브(번갈아)로 한 번에 — 고른 게 없으면 전체."""
        sel = sorted(getattr(self, "_night_sel", set()))
        if not sel:                      # 아무것도 안 골랐으면 실행하지 않는다
            self.status.set("🌑 악몽의섬 — 슬롯을 고르세요 ([+] 를 눌러 선택)"); return
        if self._is_busy():
            self._enqueue("악몽의섬 선택실행", self._run_night_sel); return
        self._island_step_back()
        cmd = [r"pythonw", os.path.join(BASE, "lineagem_island.py"),
               str(self.NIGHT_DIDX), "--run",
               "--slots", ",".join(str(i + 1) for i in sel), "--lanes", "2"]
        proc = subprocess.Popen(cmd)
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()
        for i in sel:
            self._night_rep_restart(i)
        self._night_sel = set()          # 실행했으면 + 선택은 풀어준다
        self._refresh_night_plus()
        self.status.set(f"🌑 악몽의섬 실행 — {[i+1 for i in sel]}번 "
                        f"(지금부터 2시간 다시 셈 / 선택 해제됨)")

    # 남은 횟수별 색 — 많이 남았으면 초록, 줄어들수록 파랑→보라→빨강
    REP_LEFT_COLORS = {6: "#1e8449", 5: "#27ae60", 4: "#16a085",
                       3: "#2980b9", 2: "#8e44ad", 1: "#c0392b"}

    def _refresh_night_btns(self):
        """반복이 걸린 슬롯은 남은 횟수에 따라 색이 다르다 (꺼졌으면 회색)."""
        try:
            st = self._rep_load()
            for i, b in enumerate(self._night_btns or []):
                if not b.winfo_exists():
                    continue
                e = st.get(f"{self.NIGHT_KEY}|{i}")
                if e:
                    n = int(e.get("left", 0))
                    _h = int(e.get("h", 2) or 2)
                    # 시간까지 같이 보여준다 — 예: '2h 5회' (2026-08-23 사용자 요청)
                    b.config(text=f"{_h}h {n}회",
                             bg=self.REP_LEFT_COLORS.get(n, "#34495e"))
                else:
                    # 예약은 없지만 **설정은 있다** — 그걸 보여준다.
                    # 초기화만 하고 아직 실행 전인 상태가 '⏰꺼짐' 으로 보여
                    # 설정이 안 들어간 줄 알았다는 지적 (2026-08-28).
                    try:
                        _sl = (self._island_cfg().get(self.NIGHT_KEY) or [])[i]
                        _h2, _n2 = self._rep_hn(self.NIGHT_KEY, _sl)
                        _f2 = (int(self.REPEAT_FIRST.get(self.NIGHT_KEY, _h2) or _h2)
                               if self._night_mode(i) == "first" else _h2)
                        _t2 = (f"{_f2}h→{_h2}h" if _f2 != _h2 else f"{_h2}h")
                        b.config(text=f"대기 {_t2} {_n2}회", bg="#5d6d7e")
                    except Exception:
                        b.config(text="⏰꺼짐", bg="#7f8c8d")
            for i, b in enumerate(getattr(self, "_night_firstbtns", []) or []):
                if not b.winfo_exists():
                    continue
                txt, col = self.NIGHT_MODE_TXT[self._night_mode(i)]
                b.config(text=txt, bg=col, fg="white")
        except Exception:
            pass
        self.after(20000, self._refresh_night_btns)

    def _night_week_start(self):
        """런처가 켜지면 주간 자동 초기화 감시를 시작한다 (한 번만)."""
        if getattr(self, "_night_week_on", False):
            return
        self._night_week_on = True
        self.after(15000, self._night_week_reset)

    def _run_night_slot(self, slot_idx):
        """[실행]은 '대기열에 쌓기' — 누른 순서대로 하나씩 자동으로 돈다.
        (여러 개를 눌러두고 잊어도 되게. 대기 중인 것을 다시 누르면 취소)"""
        if not hasattr(self, "_night_queue"):
            self._night_queue = []
        try:
            slots = self._island_cfg().get(self.NIGHT_KEY, [])
            if slot_idx >= len(slots) or not any(slots[slot_idx].get("coords") or []):
                self.status.set(f"악몽의섬 #{slot_idx+1:02d} — 등록된 좌표 없음"); return
        except Exception:
            pass
        if slot_idx in self._night_queue:
            self._night_queue.remove(slot_idx)
            self._refresh_night_queue()
            self.status.set(f"🌑 악몽의섬 #{slot_idx+1:02d} 대기 취소 "
                            f"(대기 {len(self._night_queue)}개)"); return
        self._night_queue.append(slot_idx)
        self._refresh_night_queue()
        self.status.set(f"🌑 악몽의섬 #{slot_idx+1:02d} 대기에 넣음 — "
                        f"{[i+1 for i in self._night_queue]} 순서로 하나씩 실행")
        self._night_queue_tick()

    def _night_queue_tick(self):
        """앞 작업이 끝나면 대기열에서 하나 꺼내 실행한다."""
        q = getattr(self, "_night_queue", None)
        if not q:
            return
        if self._is_busy():
            self.after(3000, self._night_queue_tick); return
        idx = q.pop(0)
        self._refresh_night_queue()
        self._night_launch(idx)
        self.after(6000, self._night_queue_tick)   # 다음 것은 이 실행이 끝난 뒤

    def _night_launch(self, slot_idx):
        """실제 실행 — 누른 때부터 2시간 N회를 다시 센다."""
        self._island_step_back()
        cmd = [r"pythonw", os.path.join(BASE, "lineagem_island.py"),
               str(self.NIGHT_DIDX), "--run", "--slot", str(slot_idx + 1)]
        proc = subprocess.Popen(cmd)
        self._island_proc = proc
        threading.Thread(target=self._watch_island, args=(proc,), daemon=True).start()
        self._night_rep_restart(slot_idx)
        left = len(getattr(self, "_night_queue", []) or [])
        self.status.set(f"🌑 악몽의섬 #{slot_idx+1:02d} 실행 — 지금부터 2시간 다시 셈"
                        + (f" (대기 {left}개 남음)" if left else ""))

    def _refresh_night_queue(self):
        """대기 중인 슬롯은 [실행] 버튼에 순번을 보여준다."""
        q = getattr(self, "_night_queue", []) or []
        for i, b in enumerate(getattr(self, "_night_runbtns", []) or []):
            try:
                if not b.winfo_exists():
                    continue
                if i in q:
                    b.config(text=f"대기{q.index(i)+1}", bg="#e67e22")
                else:
                    b.config(text="실행", bg="#2471a3")
            except Exception:
                pass

    def _night_rep_restart(self, slot_idx):
        """그 슬롯의 반복을 '지금부터' 다시 시작 (2시간 N회)."""
        try:
            slot = (self._island_cfg().get(self.NIGHT_KEY) or [])[slot_idx]
            if (self.NIGHT_KEY != "토요일_악몽의섬"
                    and not (slot.get("repeat_h") or 0)):
                # 다른 던전은 사용자가 ⏰ 를 켜둔 슬롯만 반복이 걸린다 (그냥 실행만)
                return
            h, n = self._rep_hn(self.NIGHT_KEY, slot)     # 악몽의섬 = 2시간 6회
            # 실행(선택실행·개별실행)은 **항상 2시간 6회** — 사용자 지시(2026-08-23).
            # 누른 그 실행이 1회차이므로 남은 5회, 다음은 2시간 뒤.
            f = h
            st = self._rep_load()
            st.pop("_off", None)          # 다시 켰으니 '꺼둠' 표시 해제
            # 사용자가 직접 누른 실행도 '1회차'로 센다 (2026-08-16 사용자 지시)
            st[f"{self.NIGHT_KEY}|{slot_idx}"] = {"h": h, "left": max(0, n - 1), "run": 1,
                                                  "next": time.time() + self._rep_delay(f)}
            md = st.get("_mode") or {}          # 표시도 '2h마다' 로 맞춘다
            md[f"{self.NIGHT_KEY}|{slot_idx}"] = "h2"
            st["_mode"] = md
            fd = st.get("_first") or {}
            fd[f"{self.NIGHT_KEY}|{slot_idx}"] = False
            st["_first"] = fd
            self._rep_save(st)
            # ★ 설정에도 주기를 되살린다 — [반복 종료]로 repeat_h 가 0이면
            #   반복 관리자가 방금 건 예약을 '꺼진 것'으로 보고 지워버린다
            #   (그래서 한 번만 돌고 끝났다 — 2026-08-23)
            try:
                path = os.path.join(BASE, "island_coords.json")
                with open(path, encoding="utf-8") as fp:
                    _cfg = json.load(fp)
                _cfg[self.NIGHT_KEY][slot_idx]["repeat_h"] = h
                _cfg[self.NIGHT_KEY][slot_idx]["repeat_n"] = n
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(_cfg, fp, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception as _e:
                self._rep_log(f"⚠ 악몽의섬 #{slot_idx+1:02d} 주기 저장 실패: {_e!r}")
            self._rep_log(f"{self.NIGHT_KEY} #{slot_idx+1:02d} 메인런처 실행 — "
                          f"1회차 (남은 {max(0, n-1)}회, 다음 {f}시간 뒤"
                          f"{', 그 다음부터 %d시간' % h if f != h else ''})")
            self._refresh_night_btns()
        except Exception as e:
            self._rep_log(f"⚠ 악몽의섬 #{slot_idx+1:02d} 반복 재시작 실패: {e!r}")

    def _night_week_reset(self):
        """**토요일 00시가 되면 악몽의섬 설정을 자동으로 초기화**한다
        (4시간 → 2시간 6회). 2026-08-28 사용자 지시.

        - **값만 되돌린다.** 예약(⏰)을 걸지 않고, 아무것도 실행하지 않는다.
          반복은 예전처럼 **사용자가 [실행] 을 눌렀을 때만** 걸린다.
        - 한 주에 한 번만 — LOCALAPPDATA/MoonAI/night_week.json 에 기록.
        - 런처가 꺼져 있었으면 켜진 뒤 처음 확인할 때 그 주 몫을 한 번 한다."""
        try:
            import datetime as _dt
            now = _dt.datetime.now()
            # 그 주의 '토요일 00시' — 토요일 이후면 이번 주, 아니면 지난 주 토요일
            days = (now.weekday() - 5) % 7          # 월=0 … 토=5
            sat = (now - _dt.timedelta(days=days)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            if now < sat:
                sat -= _dt.timedelta(days=7)
            tag = sat.strftime("%Y-%m-%d")
            fp = os.path.join(LOCAL_DATA, "night_week.json")
            try:
                with open(fp, encoding="utf-8") as f:
                    done = str((json.load(f) or {}).get("done") or "")
            except Exception:
                done = ""
            if done != tag:
                self._night_rearm_all_impl(True)     # 값만 — 예약 안 검
                os.makedirs(LOCAL_DATA, exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump({"done": tag}, f)
                self._rep_log(f"{self.NIGHT_KEY} — 토요일({tag}) 자동 초기화: "
                              f"4시간 → 2시간 6회 (값만, 예약·실행 없음)")
        except Exception as e:
            try: self._rep_log(f"⚠ 악몽의섬 주간 초기화 실패: {e!r}")
            except Exception: pass
        finally:
            self.after(600000, self._night_week_reset)   # 10분마다 확인

    def _night_rearm_all(self, first_4h):
        if self.NIGHT_KEY != "토요일_악몽의섬":
            self.status.set("이 버튼은 악몽의섬에서만 씁니다 (탭을 악몽의섬으로)")
            return
        return self._night_rearm_all_impl(first_4h)

    def _night_rearm_all_impl(self, first_4h):
        """악몽의섬 16슬롯의 '설정만' 기본값으로 되돌린다.
        first_4h=True  → 4시간 → 2시간 6회 (기본값)
        first_4h=False → 처음부터 2시간 6회
        **반복(⏰)을 켜지는 않는다** — 반복은 사용자가 실행했을 때만 걸린다
        (2026-08-23 사용자 지시, 절대 규칙)."""
        try:
            h, n = self._rep_hn(self.NIGHT_KEY)          # 코드 기본값 2시간 6회
            f = int(self.REPEAT_FIRST.get(self.NIGHT_KEY, h) or h) if first_4h else h
            cfg = self._island_cfg()
            slots = cfg.get(self.NIGHT_KEY) or []
            st = self._rep_load()
            md = st.get("_mode") or {}
            fd = st.get("_first") or {}
            cnt = 0
            for i, sl in enumerate(slots):
                if not (isinstance(sl, dict) and any(sl.get("coords") or [])):
                    continue
                sl["repeat_h"] = h; sl["repeat_n"] = n     # 주기는 항상 2시간
                md[f"{self.NIGHT_KEY}|{i}"] = "first" if first_4h else "h2"
                fd[f"{self.NIGHT_KEY}|{i}"] = bool(first_4h)
                st.pop(f"{self.NIGHT_KEY}|{i}", None)      # 걸려 있던 예약은 지운다
                cnt += 1
            st["_mode"] = md
            st["_first"] = fd
            self._rep_save(st)
            try:                                   # 섬/던전 설정에도 2시간 6회로 남긴다
                path = os.path.join(BASE, "island_coords.json")
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception as e:
                self._rep_log(f"⚠ 악몽의섬 설정 저장 실패: {e!r}")
            _t = f"{f}시간 → {h}시간" if f != h else f"{h}시간"
            self._rep_log(f"{self.NIGHT_KEY} — {cnt}개 슬롯 설정 초기화 "
                          f"({_t} {n}회). 반복은 켜지 않음 (사용자)")
            self.status.set(f"🔄 악몽의섬 {cnt}개 슬롯 설정 초기화 — {_t} {n}회. "
                            f"반복은 [실행] 을 눌렀을 때 걸립니다")
            self._refresh_night_btns(); self._refresh_rep_btn()
        except Exception as e:
            self.status.set(f"초기화 실패: {e}")

    def _night_mode(self, slot_idx):
        """그 슬롯의 지금 모드."""
        try:
            st = self._rep_load()
            k = f"{self.NIGHT_KEY}|{slot_idx}"
            m = (st.get("_mode") or {}).get(k)
            if m == "h4":                 # 없앤 모드 — 2h마다로 본다
                return "h2"
            if m in self.NIGHT_MODES:
                return m
            # 예전 방식(_first)만 있으면 그걸로 본다
            return "first" if (st.get("_first") or {}).get(k, True) else "h2"
        except Exception:
            return "first"

    def _night_first_toggle(self, slot_idx):
        """버튼을 누를 때마다 4h→2h / 2h마다 / 4h마다 로 돌려가며 고른다.
        **그 슬롯만** 바뀌고, 이미 돈 횟수(남은 회)는 그대로 이어간다."""
        cur = self._night_mode(slot_idx)
        try:
            nxt = self.NIGHT_MODES[(self.NIGHT_MODES.index(cur) + 1) % len(self.NIGHT_MODES)]
        except ValueError:
            nxt = "first"
        self._night_mode_set(slot_idx, nxt)

    def _night_mode_set(self, slot_idx, mode):
        """그 슬롯의 주기를 바꾸고, 다음 실행 시각만 다시 잡는다 (횟수는 유지)."""
        try:
            h = 2                                     # 평소 주기는 항상 2시간
            first = 4 if mode == "first" else 2        # 첫 회차만 4시간 or 2시간
            st = self._rep_load()
            k = f"{self.NIGHT_KEY}|{slot_idx}"
            md = st.get("_mode") or {}; md[k] = mode; st["_mode"] = md
            fd = st.get("_first") or {}; fd[k] = (mode == "first"); st["_first"] = fd
            e = st.get(k)
            _h0, n0 = self._rep_hn(self.NIGHT_KEY)
            if e:                       # 이미 걸려 있으면 남은 횟수를 그대로 이어간다
                run = int(e.get("run", 0) or 0)
                e["h"] = h
                e["next"] = time.time() + self._rep_delay(first if not run else h)
                st[k] = e
                left_txt = f"남은 {e.get('left', n0)}회 그대로"
            else:
                # 반복이 꺼져 있으면 '설정만' 바꾼다 — 여기서 켜지 않는다.
                # 반복은 사용자가 실행했을 때만 걸린다 (2026-08-23 사용자 지시, 절대 규칙)
                left_txt = "반복은 꺼진 상태 — [실행] 하면 이 설정으로 걸립니다"
            self._rep_save(st)
            try:                        # 섬/던전 설정에도 그 슬롯만 주기를 남긴다
                path = os.path.join(BASE, "island_coords.json")
                with open(path, encoding="utf-8") as fp:
                    cfg = json.load(fp)
                cfg[self.NIGHT_KEY][slot_idx]["repeat_h"] = h
                cfg[self.NIGHT_KEY][slot_idx]["repeat_n"] = n0
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception as ex:
                self._rep_log(f"⚠ 악몽의섬 #{slot_idx+1:02d} 주기 저장 실패: {ex!r}")
            txt = self.NIGHT_MODE_TXT[mode][0]
            when = (time.strftime("%H:%M", time.localtime(st[k]["next"]))
                    if k in st else "-")
            self._rep_log(f"{self.NIGHT_KEY} #{slot_idx+1:02d} {txt} 로 변경 "
                          f"(다음 {when}, {left_txt}) (사용자)")
            self.status.set(f"악몽의섬 #{slot_idx+1:02d} — {txt} "
                            f"(다음 실행 {when}, {left_txt})")
            self._refresh_night_btns()
        except Exception as e:
            self.status.set(f"악몽의섬 #{slot_idx+1:02d} 변경 실패: {e}")

    def _night_rep_cancel(self, slot_idx):
        """✕ — 그 슬롯의 ⏰ 반복만 취소한다 (토글 아님, 끄기만).
        다른 슬롯·실행 중인 작업은 건드리지 않는다."""
        try:
            st = self._rep_load()
            k = f"{self.NIGHT_KEY}|{slot_idx}"
            had = k in st
            st.pop(k, None)
            self._rep_save(st)
            try:                       # 섬/던전 설정의 ⏰ 도 꺼둔다
                path = os.path.join(BASE, "island_coords.json")
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg[self.NIGHT_KEY][slot_idx]["repeat_h"] = 0
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception:
                pass
            self._rep_log(f"{self.NIGHT_KEY} #{slot_idx+1:02d} 반복 취소 ✕ (사용자)")
            self.status.set(f"✕ 악몽의섬 #{slot_idx+1:02d} 반복 취소"
                            + ("" if had else " (이미 꺼져 있었습니다)"))
            self._refresh_night_btns(); self._refresh_rep_btn()
        except Exception as e:
            self.status.set(f"반복 취소 실패: {e}")

    def _night_rep_off(self, slot_idx):
        """그 슬롯의 ⏰ 반복만 끈다 (다른 슬롯은 그대로). 꺼진 것을 누르면 다시 시작."""
        try:
            st = self._rep_load()
            k = f"{self.NIGHT_KEY}|{slot_idx}"
            if k not in st:                      # 이미 꺼져 있으면 → 다시 시작
                self._night_rep_restart(slot_idx)
                self.status.set(f"⏰ 악몽의섬 #{slot_idx+1:02d} 반복 다시 시작 (2시간)")
                return
            st.pop(k, None)
            self._rep_save(st)
            path = os.path.join(BASE, "island_coords.json")
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg[self.NIGHT_KEY][slot_idx]["repeat_h"] = 0
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            self._rep_log(f"{self.NIGHT_KEY} #{slot_idx+1:02d} 반복 끔 (사용자)")
            self._refresh_night_btns(); self._refresh_rep_btn()
            self.status.set(f"⏰ 악몽의섬 #{slot_idx+1:02d} 반복 껐습니다")
        except Exception as e:
            self.status.set(f"⚠ 반복 끄기 실패: {e}")

    def _run_return_slot(self, slot_idx):
        """귀환주문서(섬/던전 실행기의 컬럼) 슬롯 하나만 메인 런처에서 단독 실행."""
        if getattr(self, "_return_running", False):
            self.status.set("귀환주문서 실행 중입니다"); return
        ipath = os.path.join(BASE, "island_coords.json")
        try:
            with open(ipath, encoding="utf-8") as f:
                icfg = json.load(f)
        except Exception:
            self.status.set("island_coords.json 을 찾을 수 없습니다"); return
        slots = icfg.get("귀환주문서", [])
        if slot_idx >= len(slots) or not any(c for c in slots[slot_idx].get("coords", [])):
            self.status.set(f"귀환주문서 #{slot_idx+1:02d} — 등록된 좌표 없음 (섬/던전 실행기에서 등록)")
            return
        name   = slots[slot_idx].get("name", f"#{slot_idx+1}")
        coords = slots[slot_idx].get("coords", [])
        if not self._try_busy_or_queue("귀환주문서", lambda: self._run_return_slot(slot_idx),
                                       label=f"귀환주문서 #{slot_idx+1:02d}"): return
        self._return_running = True
        self._return_stop    = False
        self.status.set(f"2초 후 귀환주문서 [{name}] 실행...")
        self._minimize_all()
        threading.Thread(target=self._run_task,
                         args=("귀환주문서", self._run_return_worker, name, coords), daemon=True).start()

    def _run_return_worker(self, name, coords):
        self._start_pause()
        CLICK_INTERVAL = 2.0   # island 실행 간격과 동일 (클릭 사이 대기)
        SETTLE_DELAY   = 0.7   # 좌표 이동 후 클릭 전 대기 (씹힘 방지)
        try:
            time.sleep(2)
            for j, c in enumerate(coords):
                if getattr(self, "_return_stop", False):
                    break
                if not c:
                    continue
                self.after(0, lambda n=name, j=j: self.status.set(f"🌀 귀환주문서 [{n}] 클릭{j+1}..."))
                pyautogui.moveTo(*c)
                time.sleep(SETTLE_DELAY)     # 커서 안착 후 클릭 → 씹힘 방지
                pyautogui.click()
                time.sleep(CLICK_INTERVAL + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.after(0, lambda n=name: self.status.set(f"✔ 귀환주문서 [{n}] 완료"))
        except Exception as e:
            self.after(0, lambda e=e: self.status.set(f"귀환주문서 오류: {e}"))
        finally:
            self._return_running = False
            # 여러 칸을 이어서 돌 때는 중간에 런처를 앞으로 올리지 않는다
            if not getattr(self, "_return_batch", False):
                self.after(0, self._raise_main)

    ACC_TYPES  = ["구글",    "NC",      "전번",    "페이스북"]
    ACC_COLORS = ["#DB4437", "#e67e22", "#27ae60", "#6c3483"]

    def _acc_color_for(self, idx, val):
        """계정 유형 OptionMenu 배경색 갱신 (창이 열려 있을 때만)."""
        if idx >= len(self._acc_type_btns):
            return
        om = self._acc_type_btns[idx]
        if om is None:
            return
        try:
            om.config(bg=self.ACC_COLORS[self.ACC_TYPES.index(val)
                                         if val in self.ACC_TYPES else 0])
        except Exception:
            pass

    def _build_accounts(self, parent):
        """🔑 계정 관리 — 16칸 그리드 (별도 창). 유형 색상은 생성자 command로 갱신(누적 없음)."""
        acc_title = tk.Frame(parent); acc_title.pack(fill="x", padx=4, pady=(4,0))
        tk.Label(acc_title, text="🔑 계정 관리", font=("맑은 고딕", 9, "bold"), fg="#2c3e50").pack(side="left")
        tk.Button(acc_title, text="초기화", font=("맑은 고딕", 7), bg="#c0392b", fg="white",
                  command=self._clear_accounts).pack(side="right", padx=(2,0))
        tk.Button(acc_title, text="전체저장", font=("맑은 고딕", 7), bg="#27ae60", fg="white",
                  command=self._save_accounts).pack(side="right")
        tk.Button(acc_title, text="🔐 본인확인", font=("맑은 고딕", 7), bg="#7d3c98", fg="white",
                  command=self._open_verify_win).pack(side="right", padx=(0,4))

        TYPES, TYPE_COLORS = self.ACC_TYPES, self.ACC_COLORS
        # 창을 다시 열 때 이전 창의 폰트맞춤 trace 제거 (중복 누적 방지)
        for (v, tid) in getattr(self, "_acc_fit_traces", {}).values():
            try: v.trace_remove("write", tid)
            except Exception: pass
        self._acc_fit_traces = {}
        acc_grid = tk.Frame(parent); acc_grid.pack(pady=(2,4), padx=4)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                cell = tk.Frame(acc_grid, bd=1, relief="groove", padx=2, pady=1)
                cell.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                top = tk.Frame(cell); top.pack(anchor="w")
                tk.Label(top, text=f"{idx+1:02d}", font=("맑은 고딕", 7, "bold"), fg="#888").pack(side="left")
                t = self._acc_type_vars[idx].get()
                om = tk.OptionMenu(top, self._acc_type_vars[idx], *TYPES,
                                   command=lambda val, i=idx: (self._acc_color_for(i, val),
                                                               self._schedule_acc_autosave()))
                om.config(font=("맑은 고딕", 7, "bold"), fg="white", width=6,
                          bg=TYPE_COLORS[TYPES.index(t) if t in TYPES else 0],
                          activebackground="#555", pady=0, relief="raised",
                          highlightthickness=0)
                for ti, (tn, tc) in enumerate(zip(TYPES, TYPE_COLORS)):
                    om["menu"].entryconfig(ti, background=tc, foreground="white",
                                          activebackground=tc, activeforeground="white",
                                          font=("맑은 고딕", 9, "bold"))
                om.pack(side="left", padx=(2,0))
                self._acc_type_btns[idx] = om
                for j in range(5):
                    fr = tk.Frame(cell); fr.pack(fill="x")
                    var = self._acc_vars[idx][j]
                    ent = tk.Entry(fr, textvariable=var,
                                   font=("맑은 고딕", 8), width=12)
                    ent.pack(side="left", fill="x", expand=True)
                    # 글자 수에 맞춰 폰트 축소 — 긴 내용도 칸 안에 보이게
                    tid = var.trace_add("write",
                        lambda *a, e=ent, v=var: (self._fit_acc_entry(e, v),
                                                  self._schedule_acc_autosave()))
                    self._acc_fit_traces[(idx, j)] = (var, tid)
                    self._fit_acc_entry(ent, var)
                    tk.Button(fr, text="📋", font=("맑은 고딕", 6), width=2, pady=0,
                              command=lambda i=idx, jj=j: self._copy_acc_field(i, jj)
                              ).pack(side="left", padx=(1, 0))

    def _fit_acc_entry(self, ent, var):
        """계정 칸 글자 수에 맞춰 폰트 크기 자동 축소 (칸 밖으로 안 벗어나게)."""
        try:
            n = len(var.get())
            size = 8 if n <= 13 else (7 if n <= 17 else 6)
            ent.config(font=("맑은 고딕", size))
        except Exception:
            pass

    def _copy_acc_field(self, idx, j):
        """계정 칸 하나를 클립보드로 복사."""
        val = self._acc_vars[idx][j].get().strip()
        if not val:
            self.status.set(f"#{idx+1:02d} {j+1}번 칸이 비어 있습니다"); return
        self.clipboard_clear(); self.clipboard_append(val)
        self.status.set(f"📋 #{idx+1:02d} {j+1}번 칸 복사됨: {val[:20]}")

    # ── 아이템 리롤(새로고침 매크로) ─────────────────────────────────
    def _reroll_targets_cfg(self):
        """reroll_targets 를 4칸으로 보정해 반환 (없으면 생성)."""
        t = list(self.cfg.get("reroll_targets") or [])
        while len(t) < 4:
            t.append({"enabled": False})
        self.cfg["reroll_targets"] = t
        return t

    def _reroll_reg_label(self):
        def mk(k): return "✔" if self.cfg.get(k) else "✕"
        return (f"새로고침 {mk('reroll_refresh_btn')}   확인 {mk('reroll_confirm_btn')}   "
                f"영역 {mk('reroll_item_area')}")

    def _build_reroll(self, parent):
        """🔨 아이템 리롤 — 새로고침 반복 → 타깃 아이템 발견 시 정지 + 확인 자동클릭."""
        targets = self._reroll_targets_cfg()

        self._reroll_status_var = tk.StringVar(value="상태: 대기 중")
        self._reroll_status_lbl = tk.Label(parent, textvariable=self._reroll_status_var,
            font=("맑은 고딕", 12, "bold"), fg="#c0392b", wraplength=400, justify="center")
        self._reroll_status_lbl.pack(pady=(8, 4))

        reg = tk.LabelFrame(parent, text="등록", font=("맑은 고딕", 8, "bold"))
        reg.pack(fill="x", padx=8, pady=4)
        r1 = tk.Frame(reg); r1.pack(fill="x", pady=2)
        tk.Button(r1, text="🖱 새로고침 버튼", font=("맑은 고딕", 8), width=13,
                  command=lambda: self._reg_reroll_point("reroll_refresh_btn", "새로고침 버튼")).pack(side="left", padx=2)
        tk.Button(r1, text="🖱 확인 버튼", font=("맑은 고딕", 8), width=11,
                  command=lambda: self._reg_reroll_point("reroll_confirm_btn", "확인(획득) 버튼")).pack(side="left", padx=2)
        tk.Button(r1, text="📷 아이템 영역", font=("맑은 고딕", 8), width=11,
                  command=self._reg_reroll_area).pack(side="left", padx=2)
        self._reroll_reg_var = tk.StringVar(value=self._reroll_reg_label())
        tk.Label(reg, textvariable=self._reroll_reg_var, font=("맑은 고딕", 8), fg="#555").pack(anchor="w", padx=4, pady=(2,2))

        tgt = tk.LabelFrame(parent, text="노릴 아이템 (체크=감시 / 📷=드래그로 아이콘 지정해 저장)",
                            font=("맑은 고딕", 8, "bold"))
        tgt.pack(fill="x", padx=8, pady=4)
        self._reroll_enable_vars = []
        self._reroll_thumb_lbls  = [None] * 4
        _changed = False
        for i in range(4):
            row = tk.Frame(tgt); row.pack(fill="x", pady=2)
            img_exists = os.path.exists(os.path.join(REROLL_DIR, f"target_{i+1}.png"))
            ev = tk.BooleanVar(value=img_exists)   # 이미지가 있으면 기본 감시 ON
            if targets[i].get("enabled") != img_exists:
                targets[i]["enabled"] = img_exists; _changed = True
            self._reroll_enable_vars.append(ev)
            tk.Checkbutton(row, text=f"{i+1}번", variable=ev, font=("맑은 고딕", 9, "bold"),
                           command=lambda x=i: self._toggle_reroll_target(x)).pack(side="left")
            tk.Button(row, text="📷 캡처", font=("맑은 고딕", 8), width=6,
                      command=lambda x=i: self._capture_reroll_target(x)).pack(side="left", padx=4)
            thumb = tk.Label(row, bd=1, relief="groove", width=9, height=2, text="없음",
                             font=("맑은 고딕", 7), fg="#aaa")
            thumb.pack(side="left", padx=4)
            self._reroll_thumb_lbls[i] = thumb
        self._reroll_load_thumbs()
        if _changed:
            save_cfg(self.cfg)

        cf = tk.Frame(parent); cf.pack(fill="x", padx=8, pady=4)
        tk.Label(cf, text="유사도(0~1):", font=("맑은 고딕", 8)).pack(side="left")
        self._reroll_thr_var = tk.StringVar(value=str(self.cfg.get("reroll_threshold", 0.90)))
        tk.Entry(cf, textvariable=self._reroll_thr_var, width=5, font=("맑은 고딕", 8)).pack(side="left", padx=(2,10))
        tk.Label(cf, text="새로고침 후 대기(초):", font=("맑은 고딕", 8)).pack(side="left")
        self._reroll_wait_var = tk.StringVar(value=str(self.cfg.get("reroll_wait", 1.0)))
        tk.Entry(cf, textvariable=self._reroll_wait_var, width=5, font=("맑은 고딕", 8)).pack(side="left", padx=2)
        tk.Button(cf, text="설정 저장", font=("맑은 고딕", 8), command=self._save_reroll_cfg).pack(side="left", padx=6)

        run = tk.Frame(parent); run.pack(pady=10)
        tk.Button(run, text="▶ 매크로 시작", font=("맑은 고딕", 11, "bold"),
                  bg="#27ae60", fg="white", width=12, height=2,
                  command=self._start_reroll).pack(side="left", padx=4)
        tk.Button(run, text="■ 매크로 종료", font=("맑은 고딕", 11, "bold"),
                  bg="#c0392b", fg="white", width=12, height=2,
                  command=self._stop_reroll).pack(side="left", padx=4)

    def _reroll_load_thumbs(self):
        from PIL import Image as _Img, ImageTk as _ITk
        for i in range(4):
            lbl = self._reroll_thumb_lbls[i] if hasattr(self, "_reroll_thumb_lbls") else None
            if lbl is None or not lbl.winfo_exists():
                continue
            p = os.path.join(REROLL_DIR, f"target_{i+1}.png")
            if os.path.exists(p):
                try:
                    im = _Img.open(p)
                    w0, h0 = im.size
                    # 작은 캡처는 2배 확대해 잘 보이게, 큰 건 상한(150×110)으로 축소
                    if max(w0, h0) < 90:
                        im = im.resize((w0 * 2, h0 * 2))
                    im.thumbnail((150, 110))
                    ph = _ITk.PhotoImage(im)
                    self._reroll_thumbs[i] = ph
                    # 이미지가 있으면 width/height 는 '픽셀'로 해석되므로 이미지 크기로 지정
                    lbl.config(image=ph, text="", width=im.width, height=im.height)
                except Exception:
                    lbl.config(image="", text="?", width=9, height=2)
            else:
                lbl.config(image="", text="없음", width=9, height=2)

    def _toggle_reroll_target(self, idx):
        t = self._reroll_targets_cfg()
        t[idx]["enabled"] = bool(self._reroll_enable_vars[idx].get())
        save_cfg(self.cfg)

    def _save_reroll_cfg(self):
        if not hasattr(self, "_reroll_thr_var"):
            return
        try:
            self.cfg["reroll_threshold"] = max(0.1, min(1.0, float(self._reroll_thr_var.get())))
        except Exception:
            self.cfg["reroll_threshold"] = 0.90
        try:
            self.cfg["reroll_wait"] = max(0.1, float(self._reroll_wait_var.get()))
        except Exception:
            self.cfg["reroll_wait"] = 1.0
        save_cfg(self.cfg)
        self.status.set(f"✔ 리롤 설정 저장 (유사도 {self.cfg['reroll_threshold']}, 대기 {self.cfg['reroll_wait']}초)")

    def _reg_reroll_point(self, key, label):
        self._reroll_reg_key = key
        self.status.set(f"3초 후 [{label}] 위치를 클릭하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollPointOverlay(self, label, self._on_reroll_point))])

    def _on_reroll_point(self, x, y):
        self.cfg[self._reroll_reg_key] = [x, y]
        save_cfg(self.cfg)
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if hasattr(self, "_reroll_reg_var"):
                self._reroll_reg_var.set(self._reroll_reg_label())
        self.status.set(f"✔ 좌표 등록 완료 ({x},{y})")

    def _reg_reroll_area(self):
        self.status.set("3초 후 아이템 이미지 영역을 드래그하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollAreaOverlay(self, self._on_reroll_area))])

    def _on_reroll_area(self, x, y, w, h):
        self.cfg["reroll_item_area"] = {"x": x, "y": y, "w": w, "h": h}
        save_cfg(self.cfg)
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if hasattr(self, "_reroll_reg_var"):
                self._reroll_reg_var.set(self._reroll_reg_label())
        self.status.set(f"✔ 아이템 영역 등록 ({x},{y} / {w}×{h})")

    def _capture_reroll_target(self, idx):
        """노릴 아이템 캡처 — 화면에서 직접 드래그로 아이콘 영역을 지정해 저장."""
        self.status.set(f"3초 후 {idx+1}번 타깃: 원하는 아이템 아이콘을 드래그하세요")
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.withdraw()
        self.after(3000, lambda: [self.withdraw(), self.after(200,
            lambda: _RerollAreaOverlay(
                self,
                lambda x, y, w, h: self._on_reroll_target_area(idx, x, y, w, h),
                label=f"{idx+1}번 타깃 — 원하는 아이템 아이콘을 드래그하세요"))])

    def _on_reroll_target_area(self, idx, x, y, w, h):
        if w < 3 or h < 3:
            self.deiconify()
            if self._reroll_win and self._reroll_win.winfo_exists():
                self._reroll_win.deiconify()
            self.status.set("영역이 너무 작습니다. 다시 시도하세요"); return
        time.sleep(0.2)   # 오버레이가 완전히 사라진 뒤 캡처
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
            os.makedirs(REROLL_DIR, exist_ok=True)
            img.save(os.path.join(REROLL_DIR, f"target_{idx+1}.png"))
            t = self._reroll_targets_cfg(); t[idx]["enabled"] = True
            save_cfg(self.cfg)
            msg = f"✔ {idx+1}번 타깃 캡처 완료 ({w}×{h})"
        except Exception as e:
            msg = f"{idx+1}번 캡처 오류: {e}"
        self.deiconify()
        if self._reroll_win and self._reroll_win.winfo_exists():
            self._reroll_win.deiconify()
            if idx < len(getattr(self, "_reroll_enable_vars", [])):
                self._reroll_enable_vars[idx].set(True)
            self._reroll_load_thumbs()
        self.status.set(msg)

    def _reroll_status(self, text, color="#c0392b"):
        if hasattr(self, "_reroll_status_var"):
            self._reroll_status_var.set(text)
        if hasattr(self, "_reroll_status_lbl") and self._reroll_status_lbl.winfo_exists():
            self._reroll_status_lbl.config(fg=color)
        self.status.set(text)

    def _start_reroll(self):
        if self._reroll_running:
            self.status.set("이미 리롤 실행 중입니다"); return
        self._save_reroll_cfg()
        if not self.cfg.get("reroll_refresh_btn"):
            self._reroll_status("새로고침 버튼을 먼저 등록하세요", "#c0392b"); return
        if not self.cfg.get("reroll_item_area"):
            self._reroll_status("아이템 영역을 먼저 등록하세요", "#c0392b"); return
        enabled = [i for i in range(4)
                   if self._reroll_targets_cfg()[i].get("enabled")
                   and os.path.exists(os.path.join(REROLL_DIR, f"target_{i+1}.png"))]
        if not enabled:
            self._reroll_status("노릴 아이템(타깃 이미지)을 1개 이상 캡처/체크하세요", "#c0392b"); return
        self._reroll_running = True
        self._reroll_status("리롤 시작...", "#2c3e50")
        threading.Thread(target=self._reroll_loop, daemon=True).start()

    def _stop_reroll(self):
        self._reroll_running = False
        self._reroll_status("리롤 정지", "#555")

    def _reroll_loop(self):
        try:
            import cv2, numpy as np
            from PIL import ImageGrab
        except Exception as e:
            self.after(0, lambda: self._reroll_status(f"라이브러리 오류: {e}", "#c0392b"))
            self._reroll_running = False; return
        area    = self.cfg.get("reroll_item_area")
        refresh = self.cfg.get("reroll_refresh_btn")
        confirm = self.cfg.get("reroll_confirm_btn")
        thr     = float(self.cfg.get("reroll_threshold", 0.90))
        wait    = float(self.cfg.get("reroll_wait", 1.0))
        templates = []
        for i in range(4):
            if not self._reroll_targets_cfg()[i].get("enabled"):
                continue
            p = os.path.join(REROLL_DIR, f"target_{i+1}.png")
            if os.path.exists(p):
                im = cv2.imread(p)
                if im is not None:
                    templates.append((i, im))
        if not templates:
            self.after(0, lambda: self._reroll_status("타깃 이미지 없음", "#c0392b"))
            self._reroll_running = False; return
        x, y, w, h = area["x"], area["y"], area["w"], area["h"]
        count = 0
        while self._reroll_running:
            try:
                pil = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True).convert("RGB")
                cur = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            except Exception as e:
                self.after(0, lambda e=e: self._reroll_status(f"캡처 오류: {e}", "#c0392b"))
                break
            best_i, best_s = -1, -1.0
            ch, cw = cur.shape[:2]
            for i, tmpl in templates:
                th, tw = tmpl.shape[:2]
                t = tmpl
                if th > ch or tw > cw:
                    # 템플릿이 검색영역보다 크면 맞게 축소 (matchTemplate 요구조건)
                    sc = min(ch / th, cw / tw)
                    t = cv2.resize(tmpl, (max(1, int(tw*sc)), max(1, int(th*sc))))
                try:
                    score = float(cv2.matchTemplate(cur, t, cv2.TM_CCOEFF_NORMED).max())
                except Exception:
                    score = -1.0
                if score > best_s:
                    best_s, best_i = score, i
            self.after(0, lambda c=count, s=best_s: self._reroll_status(
                f"검색 중…  {c}회  (최고 유사도 {s:.3f})", "#2c3e50"))
            if best_s >= thr:
                self.after(0, lambda i=best_i, s=best_s: self._reroll_status(
                    f"상태: {i+1}번 아이템 발견!!!  (유사도 {s:.3f})", "#c0392b"))
                self._reroll_found(confirm)
                self._reroll_running = False
                break
            if refresh:
                try: pyautogui.click(refresh[0], refresh[1])
                except Exception: pass
            count += 1
            t0 = time.time()
            while self._reroll_running and time.time() - t0 < wait:
                time.sleep(0.05)
        if not self._reroll_running:
            self.after(0, lambda: self._reroll_status("리롤 종료", "#555"))

    def _reroll_found(self, confirm):
        # 발견 시: 확인(획득) 버튼 자동 클릭 → 소리 알림 → 런처 앞으로
        if confirm:
            time.sleep(0.3)
            try: pyautogui.click(confirm[0], confirm[1])
            except Exception: pass
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 180); time.sleep(0.06)
        except Exception:
            pass
        self.after(0, self._keep_launcher_front)
        if self._reroll_win and self._reroll_win.winfo_exists():
            self.after(0, lambda: (self._reroll_win.deiconify(), self._reroll_win.lift()))

    def _build_right(self, parent):
        tk.Label(parent, text=f"사냥  (슬롯당 {HUNT_CLICKS}번 클릭 / {HUNT_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#27ae60").pack(anchor="w", padx=4, pady=(4,2))

        hr = tk.Frame(parent); hr.pack(pady=3)
        self.btn_hunt_run = tk.Button(hr, text="▶  사냥 실행",
            font=("맑은 고딕", 9, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=13, height=2, command=self._start_hunt)
        self.btn_hunt_run.pack(side="left", padx=(0, 3))
        self.btn_hunt_stop = tk.Button(hr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_hunt_stop", True) or
                            self.status.set("사냥 멈추는 중..."),
            state="disabled")
        self.btn_hunt_stop.pack(side="left")
        tk.Button(hr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#8e44ad", fg="white", width=18,
            command=self._group_copy_hunt).pack(side="left", padx=(8,0))
        # 전체 창 관리 버튼(위치저장/창복원/번호재지정/이름영역/이름인식)은
        # 메인 앞쪽 "🪟 배열창 재배치" 좌측 열(_build_winmgmt)로 이동됨

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "hunt")   # 4×4 그리드 (화면 배치와 동일)

    def _lock_lineagem_window(self):
        candidates = []
        def enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return
            t = win32gui.GetWindowText(hwnd)
            if not t: return
            tl = t.lower()
            if any(k in tl for k in ("lineagem", "리니지m", "lineage m", "ncsoft")):
                candidates.append(hwnd)
        win32gui.EnumWindows(enum_cb, None)

        if not candidates:
            # 창 제목 목록 팝업으로 보여주기
            self._pick_window_dialog()
            return

        self._win_lock.lock_all(candidates)
        self._lock_status_var.set(f"리사이즈 차단 ON — {len(candidates)}개 창")
        self._btn_lock.config(bg="#27ae60")

    def _pick_window_dialog(self):
        """창 목록을 팝업으로 보여주고 선택해서 고정."""
        wins = []
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if t: wins.append((hwnd, t))
        win32gui.EnumWindows(enum_cb, None)

        dlg = tk.Toplevel(self)
        dlg.title("창 선택"); dlg.geometry("500x400"); dlg.grab_set()
        tk.Label(dlg, text="리니지M 창이 자동으로 감지되지 않았습니다.\n고정할 창을 선택하세요 (Ctrl+클릭으로 다중 선택):",
                 font=("맑은 고딕", 9), justify="left").pack(padx=8, pady=(8,4), anchor="w")
        lb = tk.Listbox(dlg, selectmode="extended", font=("맑은 고딕", 8), height=16)
        lb.pack(fill="both", expand=True, padx=8, pady=4)
        for hwnd, title in wins:
            lb.insert("end", f"[{hwnd}] {title}")

        def _apply():
            sel = lb.curselection()
            if not sel: return
            chosen = [wins[i][0] for i in sel]
            self._win_lock.lock_all(chosen)
            self._lock_status_var.set(f"리사이즈 차단 ON — {len(chosen)}개 창")
            self._btn_lock.config(bg="#27ae60")
            dlg.destroy()

        tk.Button(dlg, text="선택 고정", font=("맑은 고딕", 9, "bold"),
                  bg="#2980b9", fg="white", command=_apply).pack(pady=6)

    def _unlock_lineagem_window(self):
        self._win_lock.unlock()
        self._lock_status_var.set("고정 꺼짐")
        self._btn_lock.config(bg="#2980b9")

    def _pause_lock(self):
        if not self._win_lock.is_locked():
            return
        self._win_lock.pause(600)
        self._lock_status_var.set("⏸ 임시 해제 중 (10분)...")
        self.after(600000, lambda: self._lock_status_var.set(
            f"리사이즈 차단 ON — {len(self._win_lock._locks)}개 창") if self._win_lock.is_locked() else None)

    def _build_mail(self, parent):
        tk.Label(parent, text=f"우편함  (슬롯당 {MAIL_CLICKS}번 클릭 / {MAIL_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#8e44ad").pack(anchor="w", padx=4, pady=(4,2))

        mr = tk.Frame(parent); mr.pack(pady=3)
        self._mail_stop = False
        self.btn_mail_run = tk.Button(mr, text="▶  우편함 실행",
            font=("맑은 고딕", 9, "bold"), bg="#8e44ad", fg="white",
            activebackground="#6c3483", width=13, height=2,
            command=self._start_mail)
        self.btn_mail_run.pack(side="left", padx=(0,3))
        self.btn_mail_stop = tk.Button(mr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2, state="disabled",
            command=self._stop_mail)
        self.btn_mail_stop.pack(side="left", padx=(0,6))
        tk.Button(mr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#6c3483", fg="white", width=18,
            command=self._group_copy_mail).pack(side="left", padx=(4,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "mail")   # 4×4 그리드 (화면 배치와 동일)

    def _build_dungeon(self, parent):
        tk.Label(parent, text="변신확인용  (슬롯 순서 랜덤 / 클릭1~5 순서대로, 간격 랜덤)",
                 font=("맑은 고딕", 9, "bold"), fg="#e67e22").pack(anchor="w", padx=4, pady=(4,2))

        dr = tk.Frame(parent); dr.pack(pady=3)
        self._dungeon_stop = False
        self.btn_dungeon_run = tk.Button(dr, text="▶  던전 실행",
            font=("맑은 고딕", 9, "bold"), bg="#e67e22", fg="white",
            activebackground="#b35400", width=13, height=2,
            command=self._start_dungeon)
        self.btn_dungeon_run.pack(side="left", padx=(0,3))
        self.btn_dungeon_stop = tk.Button(dr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_dungeon_stop", True) or
                            self.status.set("던전 멈추는 중..."),
            state="disabled")
        self.btn_dungeon_stop.pack(side="left")

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "dungeon")   # 4×4 그리드 (화면 배치와 동일)

    # ── 🩹 복구 (그림으로 확인하고 누른다 — 2026-08-29 사용자 요청) ───────
    def _open_fix_win(self):
        """🩹 복구 창 — 용던고고와 같은 틀 (좌표 + 🖼그림 + 📐범위 + 🔍기준).

        **다른 재화로 복구되는 것을 막는 방법**: 확인 버튼 자리에 좌표를 등록하고,
        그 자리에 '맞는 재화일 때의 화면'을 🖼 으로 등록해둔다. 그러면 그림이 보일 때만
        그 좌표를 누르고, 다른 재화가 떠 있으면 그림이 안 맞아 **그 슬롯은 아무것도
        누르지 않고 중단**한다 (용던고고에서 검증된 규칙)."""
        self._open_section_win("_fix_win", "🩹 복구", self._build_fix, w=980, h=720)

    def _build_fix(self, parent):
        self._build_dgn2("fix", parent)
    # ── TJ성공!! (인형탐험식 실행 — 슬롯당 좌표 3개) ─────────────────────
    def _open_tj_win(self):
        self._open_section_win("_tj_win", "⭕ TJ성공!!", self._build_tj, w=470, h=600)

    def _build_tj(self, parent):
        tk.Label(parent, text="TJ성공!!  (슬롯 순서 랜덤 / 좌표1~3 순서대로, 인형탐험식 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#ad1457").pack(anchor="w", padx=4, pady=(4,2))
        pr = tk.Frame(parent); pr.pack(pady=3)
        self._tj_stop = False
        self.btn_tj_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#ad1457", fg="white",
            activebackground="#6d0f38", width=13, height=2,
            command=self._start_tj)
        self.btn_tj_run.pack(side="left", padx=(0,3))
        self.btn_tj_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_tj_stop", True) or
                            self.status.set("TJ성공!! 멈추는 중..."),
            state="disabled")
        self.btn_tj_stop.pack(side="left")
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "tj")   # 4×4 그리드 (화면 배치와 동일)

    def _reg_tj_click(self, slot_idx, click_idx):
        self._reg_tj_slot_idx  = slot_idx
        self._reg_tj_click_idx = click_idx
        self.status.set(f"3초 후 TJ성공!! #{slot_idx+1} [좌표{click_idx+1}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="tj")])

    def on_tj_coord(self, x, y):
        si = self._reg_tj_slot_idx
        ci = self._reg_tj_click_idx
        self.cfg["tj_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ TJ성공!! #{si+1} 좌표{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _test_tj(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_tj, args=(idx,), daemon=True).start()

    def _del_tj(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"TJ성공!! #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["tj_slots"][idx] = {"name": "미등록", "coords": [None]*TJ_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_tj(self, idx):
        coords = self.cfg["tj_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"TJ성공!! #{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg["tj_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_tj_slot_idx  = idx
            self._reg_tj_click_idx = dot_idx if dot_idx is not None else 0
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="tj"))

        def _save(dot_idx, nx, ny):
            self.cfg["tj_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ TJ성공!! #{idx+1:02d} 좌표{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"TJ성공!! #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _start_tj(self):
        if not self._try_busy_or_queue("TJ성공", self._start_tj): return
        self._tj_stop = False
        self._set_btn("btn_tj_run", state="disabled")
        self._set_btn("btn_tj_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(
            target=self._run_task, args=("TJ성공", self._run_tj), daemon=True).start())

    def _run_tj(self, slot_idx=None):
        self._start_pause()
        try:
            slots = self.cfg.get("tj_slots", [])
            if slot_idx is not None:
                # 단일 슬롯 테스트 — 좌표 1→2→3 순서대로
                s = slots[slot_idx] if slot_idx < len(slots) else None
                if s and any(s.get("coords", [])):
                    name = s.get("name", f"#{slot_idx+1}")
                    time.sleep(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX))
                    for j, c in enumerate(s.get("coords", [])):
                        if not c: continue
                        if getattr(self, "_tj_stop", False): break
                        self.status.set(f"⭕ [{name}] 좌표{j+1}...")
                        pyautogui.click(*c)
                        time.sleep(random.uniform(TJ_MIN, TJ_MAX))
                return
            # 전체 실행 — 웨이브 방식: 좌표1을 전 슬롯에 쫙 → 좌표2 웨이브는 30% 앞당겨
            # → 좌표3은 더 빠르게 (점점 몰아치는 템포, 웨이브마다 슬롯 순서 랜덤)
            targets = [(i, s) for i, s in enumerate(slots)
                       if any(s.get("coords", []))]
            if not targets:
                self.status.set("TJ성공!!: 등록된 좌표가 없습니다"); return
            time.sleep(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX))
            speed = 1.0
            for phase in range(TJ_CLICKS):
                if getattr(self, "_tj_stop", False): break
                if phase == TJ_CLICKS - 1:
                    # 좌표3(닫기)은 좌표2 웨이브를 전부 누른 뒤 40초~1분 후에
                    wait_end = time.time() + random.uniform(40, 60)
                    while time.time() < wait_end:
                        if getattr(self, "_tj_stop", False): break
                        self.status.set(f"⭕ 닫기(좌표3)까지 {int(wait_end - time.time())}초 대기...")
                        time.sleep(0.5)
                    if getattr(self, "_tj_stop", False): break
                wave = [(i, s) for i, s in targets
                        if s.get("coords", [None]*TJ_CLICKS)[phase]]
                random.shuffle(wave)   # 웨이브마다 슬롯 순서 랜덤
                for k, (si, s) in enumerate(wave):
                    if getattr(self, "_tj_stop", False): break
                    name = s.get("name", f"#{si+1}")
                    self.status.set(f"⭕ 좌표{phase+1} 웨이브 [{name}] ({k+1}/{len(wave)})...")
                    pyautogui.click(*s["coords"][phase])
                    time.sleep(random.uniform(TJ_MIN, TJ_MAX) * speed)
                speed *= 0.7   # 다음 웨이브는 30% 앞당김
            self.status.set("✔ TJ성공!! 완료!" if not getattr(self, "_tj_stop", False) else "TJ성공!! 멈춤")
        except Exception as e:
            self.status.set(f"TJ성공!! 오류: {e}")
        finally:
            self._set_btn("btn_tj_run", state="normal")
            self._set_btn("btn_tj_stop", state="disabled")
            self.after(0, self._restore_back)

    # ── 인형확인용/성물확인용 (변신확인용 복제 — 동일 실행 로직) ────────
    def _dgn2_info(self, fkey):
        return {"fix":     ("fix_slots",     "복구",       "🩹"),
                "dollchk": ("dollchk_slots", "인형확인용", "🧸"),
                "relic":   ("relic_slots",   "성물확인용", "🗿"),
                "coupon":  ("coupon_slots",  "쿠폰등록",   "🎟"),
                "market":  ("market_slots",  "거래소검색", "🔎"),
                "dragon":  ("dragon_slots",  "용던고고!!!", "🐲"),
                "knight":  ("knight_slots",  "던전끝! 흑기사!!", "🖤"),
                "eventshop": ("eventshop_slots", "이벤트상점", "🛒"),
                "fish":    ("fish_slots",    "낚시녹임",   "🎣"),
                "circus":  ("circus_slots",  "서커스 이벤트등록", "🎪"),
                "circus2": ("circus2_slots", "서커스 이벤트실행", "🎪"),
                "circus3": ("circus3_slots", "서커스 이벤트퀘스트", "🎪")}[fkey]

    def _open_coupon_win(self):
        self._open_section_win("_coupon_win", "🎟 쿠폰등록",
                               lambda p: self._build_dgn2("coupon", p), w=470, h=640, pinnable=True)

    def _open_knight_win(self):
        self._open_section_win("_knight_win", "🖤 던전끝! 흑기사!!",
                               lambda p: self._build_dgn2("knight", p), w=470, h=620, pinnable=True)

    def _open_dragon_win(self):
        self._open_section_win("_dragon_win", "🐲 용던고고!!!",
                               lambda p: self._build_dgn2("dragon", p), w=470, h=620, pinnable=True)

    def _start_dragon(self):
        """[실행] — 절전해제(F11) 전체를 '끝까지' 돌린 뒤 이어서 용던고고를 시작한다."""
        if self._is_busy():
            self.status.set(f"⚠ '{self._busy_label()}' 실행 중 — 끝난 뒤 다시 눌러주세요")
            return
        self.status.set("🐲 용던고고!!! — 먼저 절전해제(F11) 전체 실행…")
        threading.Thread(target=self._dragon_seq_then_run, daemon=True).start()

    def _dragon_seq_then_run(self):
        """절전해제를 이 스레드에서 통째로 돌린다(끝날 때까지 대기) → 그 다음 용던고고.
        (예전엔 절전해제를 띄워놓고 1.5초 뒤 상태만 봤더니, 아직 시작 전이라
         용던고고가 먼저 잠금을 채가서 절전해제가 통째로 건너뛰어졌다)"""
        try:
            self._run_seq()
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"⚠ 절전해제 실패: {err}"))
        time.sleep(1.0)                      # 마지막 클릭이 먹을 시간
        self._dragon_deadline = time.time() + DRAGON_BUDGET   # 여기서부터 시간을 잰다
        self.after(0, lambda: self.status.set(
            f"🐲 용던고고!!! 시작 — {DRAGON_BUDGET}초 안에 끝냅니다"))
        self.after(0, lambda: self._start_dgn2("dragon"))

    def _open_market_win(self):
        self._open_section_win("_market_win", "🔎 거래소검색",
                               lambda p: self._build_dgn2("market", p), w=470, h=640, pinnable=True)

    def _open_eventshop_win(self):
        self._open_section_win("_eventshop_win", "🛒 이벤트상점",
                               lambda p: self._build_dgn2("eventshop", p), w=470, h=600, pinnable=True)

    def _open_dollchk_win(self):
        self._open_section_win("_dollchk_win", "🧸 인형확인용",
                               lambda p: self._build_dgn2("dollchk", p), w=470, h=600, pinnable=True)

    def _open_circus_win(self):
        self._open_section_win("_circus_win", "🎪 서커스 이벤트등록",
                               lambda p: self._build_dgn2("circus", p), w=470, h=560, pinnable=True)

    def _open_circus2_win(self):
        self._open_section_win("_circus2_win", "🎪 서커스 이벤트실행",
                               lambda p: self._build_dgn2("circus2", p), w=470, h=460, pinnable=True)

    def _open_circus3_win(self):
        self._open_section_win("_circus3_win", "🎪 서커스 이벤트퀘스트",
                               lambda p: self._build_dgn2("circus3", p), w=470, h=430, pinnable=True)

    def _open_fish_win(self):
        self._open_section_win("_fish_win", "🎣 낚시녹임",
                               lambda p: self._build_dgn2("fish", p), w=470, h=600, pinnable=True)

    def _open_relic_win(self):
        self._open_section_win("_relic_win", "🗿 성물확인용",
                               lambda p: self._build_dgn2("relic", p), w=470, h=600, pinnable=True)

    # 좌표를 누른 뒤 '적어둔 글'을 붙여넣는 런처들 (쿠폰등록·거래소검색)
    PASTE_FKEYS = ("coupon", "market")

    def _build_dgn2(self, fkey, parent):
        key, title, icon = self._dgn2_info(fkey)
        sp = self._grid_spec(fkey)
        color = sp["color"]
        sub = "클릭5에서 글 붙여넣기" if fkey in self.PASTE_FKEYS else "간격 랜덤"
        tk.Label(parent, text=f"{title}  (슬롯 순서 랜덤 / 클릭1~{sp['clicks']} 순서대로, {sub})",
                 font=("맑은 고딕", 9, "bold"), fg=color).pack(anchor="w", padx=4, pady=(4,2))
        if fkey in self.PASTE_FKEYS:
            # 클릭5에서 붙여넣을 글 — 여기 적으면 자동 저장, 모든 슬롯 공통
            tr = tk.Frame(parent); tr.pack(fill="x", padx=6, pady=(0, 3))
            tk.Label(tr, text="붙여넣을 글", font=("맑은 고딕", 9, "bold"),
                     fg=color).pack(side="left")
            tv = tk.StringVar(value=str(self.cfg.get(f"{fkey}_text", "") or ""))
            ent = tk.Entry(tr, textvariable=tv, font=("맑은 고딕", 10))
            ent.pack(side="left", fill="x", expand=True, padx=6)
            def _save_txt(e=None, f=fkey, v=tv):
                self.cfg[f"{f}_text"] = v.get()
                save_cfg(self.cfg)
            ent.bind("<FocusOut>", _save_txt); ent.bind("<Return>", _save_txt)
            def _clr_txt(f=fkey, v=tv, e=ent):      # ✖ — 적어둔 글을 한 번에 지운다
                v.set("")
                self.cfg[f"{f}_text"] = ""
                save_cfg(self.cfg)
                try: e.focus_set()
                except Exception: pass
                self.status.set("붙여넣을 글을 지웠습니다")
            tk.Button(tr, text="✖", font=("맑은 고딕", 9, "bold"), width=3,
                      bg="#c0392b", fg="white", command=_clr_txt).pack(side="left")
        dr = tk.Frame(parent); dr.pack(pady=3)
        setattr(self, f"_{fkey}_stop", False)
        run = tk.Button(dr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg=color, fg="white",
            width=13, height=2, command=lambda: self._start_dgn2(fkey))
        run.pack(side="left", padx=(0,3))
        if sp.get("sel"):
            tk.Button(dr, text="▶ 선택실행", font=("맑은 고딕", 9, "bold"),
                      bg="#1e8449", fg="white", width=10, height=2,
                      command=lambda: self._start_dgn2_sel(fkey)).pack(side="left", padx=(0, 3))
            tk.Button(dr, text="선택해제", font=("맑은 고딕", 8),
                      bg="#95a5a6", fg="white", width=8, height=2,
                      command=lambda: self._grid_sel_clear(fkey)).pack(side="left", padx=(0, 3))
        setattr(self, f"btn_{fkey}_run", run)
        stopb = tk.Button(dr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, f"_{fkey}_stop", True) or
                            self.status.set(f"{title} 멈추는 중..."),
            state="disabled")
        stopb.pack(side="left")
        setattr(self, f"btn_{fkey}_stop", stopb)
        if fkey in self.LOG_FKEYS:
            # 클릭이 어느 창에 갔는지 남긴 기록 — 씹히는 자리를 찾을 때 본다
            tk.Button(dr, text="📋 클릭기록", font=("맑은 고딕", 8),
                      bg="#34495e", fg="white", width=9, height=2,
                      command=self._open_click_log).pack(side="left", padx=(3, 0))
            tk.Button(dr, text="비우기", font=("맑은 고딕", 8),
                      bg="#95a5a6", fg="white", width=6, height=2,
                      command=self._clear_click_log).pack(side="left", padx=(2, 0))
        if any(has_img(fkey, _j) for _j in range(sp["clicks"])):
            # 🩺 — 지금 16클라를 전부 훑어 '그림이 잡히는지'를 슬롯별로 보여준다.
            #      컴퓨터마다 결과가 달라서, 로컬에서 문제를 찾을 때 이걸 먼저 누른다.
            tk.Button(dr, text="🩺 이미지진단", font=("맑은 고딕", 8, "bold"),
                      bg="#6c3483", fg="white", width=10, height=2,
                      command=lambda f=fkey: self._diag_images(f)).pack(side="left",
                                                                        padx=(3, 0))
            # 📁 — 그림·'못찾음' 사진이 들어 있는 폴더를 연다 (원인 확인용)
            tk.Button(dr, text="📁 그림폴더", font=("맑은 고딕", 8),
                      bg="#34495e", fg="white", width=9, height=2,
                      command=self._open_img_dir).pack(side="left", padx=(3, 0))
            # 📤 — 원인 확인에 필요한 것(기록 + 사진 + 그림)을 바탕화면 한 폴더에 모은다.
            #      원격으로 로컬을 봐줄 때 이 폴더만 통째로 보내면 된다.
            tk.Button(dr, text="📤 진단모으기", font=("맑은 고딕", 8, "bold"),
                      bg="#b9770e", fg="white", width=10, height=2,
                      command=lambda f=fkey: self._collect_diag(f)).pack(side="left",
                                                                        padx=(3, 0))
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, fkey)   # 4×4 그리드 (화면 배치와 동일)

    def _open_img_dir(self):
        """그림 폴더 열기 — 공용과 '이 컴퓨터 전용' 둘 다.
        못 찾았을 때 저장된 `_못찾음_*.png` 가 여기 있다 (원인 확인용)."""
        try:
            os.makedirs(IMG_DIR, exist_ok=True)
            subprocess.Popen(["explorer", IMG_DIR])
            if os.path.isdir(IMG_DIR_MINE):
                subprocess.Popen(["explorer", IMG_DIR_MINE])
            self.status.set("📁 그림 폴더를 열었습니다 — "
                            "_못찾음_*.png 가 '그때 훑은 화면'입니다")
        except Exception as e:
            self.status.set(f"📁 열기 실패: {e}")

    def _collect_diag(self, fkey):
        """원인 확인에 필요한 것을 바탕화면 `진단_<런처>` 폴더 하나에 모은다 —
        클릭기록, 못찾음·창안뜸·누른자리 사진, 지금 쓰는 그림과 기준.
        원격으로 로컬을 봐줄 때 이 폴더만 통째로 보내면 된다 (2026-08-27)."""
        import glob, shutil as _sh
        try:
            out = os.path.join(os.path.expanduser("~"), "Desktop", "진단_" + fkey)
            os.makedirs(out, exist_ok=True)
            n = 0
            try:
                if os.path.exists(CLICK_LOG):
                    _sh.copy2(CLICK_LOG, os.path.join(out, "click_log.txt")); n += 1
            except Exception:
                pass
            for d in (IMG_DIR, IMG_DIR_MINE):
                if not os.path.isdir(d):
                    continue
                for q in glob.glob(os.path.join(d, "*")):
                    bn = os.path.basename(q)
                    if not (bn.startswith(("_못찾음_", "_창안뜸_", "_누른자리_"))
                            or bn.startswith(fkey)):
                        continue
                    try:
                        tag = "" if d == IMG_DIR else "전용_"
                        _sh.copy2(q, os.path.join(out, tag + bn)); n += 1
                    except Exception:
                        pass
            try:
                nclk = self._grid_spec(fkey)["clicks"]
                L = []
                L.append("런처: " + fkey)
                L.append(f"IMG_TRIES={IMG_TRIES} RECLICK_TRIES={RECLICK_TRIES}")
                L.append(f"PEAK_MIN={PEAK_MIN} PEAK_RATIO={PEAK_RATIO} "
                         f"GRAY_MIN={GRAY_MIN} GRAY_RATIO={GRAY_RATIO}")
                L.append(f"RUN_BUDGET={RUN_BUDGET.get(fkey)} PACE_FLOOR={PACE_FLOOR}")
                L.append("")
                for j2 in range(nclk):
                    if not has_img(fkey, j2):
                        continue
                    L.append(f"좌표{j2+1}: 기준 {img_thr(fkey, j2):.2f} · "
                             f"그림 {len(img_list(fkey, j2))}장"
                             f"(전용 {img_mine_count(fkey, j2)}) · "
                             f"고르기 {img_pick(fkey, j2)} · "
                             f"범위 {'있음' if area_is_set(fkey, j2) else '없음'}")
                try:
                    import ctypes as _c
                    L.append("")
                    L.append(f"화면 배율 {_c.windll.user32.GetDpiForSystem()*100//96}%")
                except Exception:
                    pass
                with open(os.path.join(out, "설정.txt"), "w", encoding="utf-8") as f:
                    f.write(chr(10).join(L))
                n += 1
            except Exception:
                pass
            subprocess.Popen(["explorer", out])
            self.status.set(f"📤 바탕화면 '진단_{fkey}' 폴더에 {n}개 모았습니다 — "
                            f"이 폴더를 통째로 보내주세요")
        except Exception as e:
            self.status.set(f"📤 모으기 실패: {e}")

    def _note(self, fkey, nm, msg):
        """실행 중 '잘 안 된 것'을 슬롯별로 모아둔다 — 끝나고 요약으로 보여준다.
        실행이 너무 빨라 화면으로는 못 보기 때문 (2026-08-27 사용자 요청)."""
        try:
            if not hasattr(self, "_run_note"):
                self._run_note = []
            self._run_note.append((str(nm), str(msg)))
        except Exception:
            pass

    def _run_summary(self, fkey, title):
        """실행이 끝나면 무엇이 안 됐는지 기록에 남기고, 진단을 저장소에 올린다.
        **창은 띄우지 않는다** (2026-08-27 사용자 지시 — 매번 닫아야 해서 불편)."""
        notes = getattr(self, "_run_note", None) or []
        try:
            byslot = {}
            for nm, msg in notes:
                byslot.setdefault(nm, []).append(msg)
            if byslot:
                click_log("[결과] " + fkey + " 문제 있던 슬롯 " + str(len(byslot)) +
                          "개 · " + " / ".join(k + ": " + "; ".join(v)
                                               for k, v in byslot.items()))
                self.status.set("⚠ " + title + " — 잘 안 된 슬롯 " +
                                str(len(byslot)) + "개 (자세한 내용은 [📋 클릭기록])")
        except Exception:
            pass
        # 메인 컴퓨터는 '읽는 쪽'이라 올리지 않는다 (로컬만 올린다)
        if fkey in DIAG_SHARE and not load_local().get("is_main"):
            threading.Thread(target=self._share_diag_now, args=(fkey,),
                             daemon=True).start()

    def _share_diag_now(self, fkey):
        """이번 실행의 진단만 저장소 diag/ 로 올린다 (메인에서 바로 본다)."""
        try:
            import socket, datetime as _dt
            nclk = self._grid_spec(fkey)["clicks"]
            L = ["=== 진단 " + fkey + " ===",
                 "컴퓨터: " + socket.gethostname(),
                 "시각: " + _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]
            L.append("[설정]")
            L.append("IMG_TRIES=" + str(IMG_TRIES) +
                     " RECLICK_TRIES=" + str(RECLICK_TRIES) +
                     " PEAK_MIN=" + str(PEAK_MIN) + " PEAK_RATIO=" + str(PEAK_RATIO) +
                     " GRAY_MIN=" + str(GRAY_MIN) + " GRAY_RATIO=" + str(GRAY_RATIO))
            L.append("RUN_BUDGET=" + str(RUN_BUDGET.get(fkey)) +
                     " PACE_FLOOR=" + str(PACE_FLOOR))
            try:
                import ctypes as _c
                L.append("화면 배율 " +
                         str(_c.windll.user32.GetDpiForSystem() * 100 // 96) + "%")
            except Exception:
                pass
            for j2 in range(nclk):
                if not has_img(fkey, j2):
                    continue
                L.append("좌표" + str(j2 + 1) + ": 기준 " +
                         format(img_thr(fkey, j2), ".2f") + " · 그림 " +
                         str(len(img_list(fkey, j2))) + "장(전용 " +
                         str(img_mine_count(fkey, j2)) + ") · 범위 " +
                         ("있음" if area_is_set(fkey, j2) else "없음"))
            # 클라 창 크기 (그림이 안 맞는 가장 흔한 원인)
            try:
                key = self._dgn2_info(fkey)[0]
                sz = {}
                for sl in (self.cfg.get(key) or []):
                    anc = slot_anchor(sl)
                    rc = client_rect_at(*anc) if anc else None
                    k = (str(rc[2] - rc[0]) + "x" + str(rc[3] - rc[1])) if rc else "창없음"
                    sz[k] = sz.get(k, 0) + 1
                L.append("클라 창 크기: " +
                         " · ".join(k + "(" + str(v) + ")" for k, v in sz.items()))
            except Exception:
                pass
            L.append("")
            L.append("[이번 실행 기록]")
            try:
                with open(CLICK_LOG, encoding="utf-8", errors="replace") as f:
                    all_lines = [x.rstrip() for x in f]
                L += [x for x in all_lines if fkey in x or "[결과]" in x
                      or "[시간]" in x][-200:]
            except Exception:
                pass
            shots = []
            for j2 in range(nclk):
                q = os.path.join(IMG_DIR, "_못찾음_" + fkey + "_" +
                                 format(j2 + 1, "02d") + ".png")
                if os.path.exists(q):
                    shots.append((q, "못찾음" + format(j2 + 1, "02d")))
            share_diag(fkey, L, shots[:3])
        except Exception:
            pass

    def _collect_diag(self, fkey):
        """원인 확인에 필요한 것을 바탕화면 `진단_<런처>` 폴더 하나에 모은다 —
        클릭기록, 못찾음·창안뜸·누른자리 사진, 지금 쓰는 그림과 기준.
        원격으로 로컬을 봐줄 때 이 폴더만 통째로 보내면 된다 (2026-08-27)."""
        import glob, shutil as _sh
        try:
            out = os.path.join(os.path.expanduser("~"), "Desktop", "진단_" + fkey)
            os.makedirs(out, exist_ok=True)
            n = 0
            try:
                if os.path.exists(CLICK_LOG):
                    _sh.copy2(CLICK_LOG, os.path.join(out, "click_log.txt")); n += 1
            except Exception:
                pass
            for d in (IMG_DIR, IMG_DIR_MINE):
                if not os.path.isdir(d):
                    continue
                for q in glob.glob(os.path.join(d, "*")):
                    bn = os.path.basename(q)
                    if not (bn.startswith(("_못찾음_", "_창안뜸_", "_누른자리_"))
                            or bn.startswith(fkey)):
                        continue
                    try:
                        tag = "" if d == IMG_DIR else "전용_"
                        _sh.copy2(q, os.path.join(out, tag + bn)); n += 1
                    except Exception:
                        pass
            try:
                nclk = self._grid_spec(fkey)["clicks"]
                L = []
                L.append("런처: " + fkey)
                L.append(f"IMG_TRIES={IMG_TRIES} RECLICK_TRIES={RECLICK_TRIES}")
                L.append(f"PEAK_MIN={PEAK_MIN} PEAK_RATIO={PEAK_RATIO} "
                         f"GRAY_MIN={GRAY_MIN} GRAY_RATIO={GRAY_RATIO}")
                L.append(f"RUN_BUDGET={RUN_BUDGET.get(fkey)} PACE_FLOOR={PACE_FLOOR}")
                L.append("")
                for j2 in range(nclk):
                    if not has_img(fkey, j2):
                        continue
                    L.append(f"좌표{j2+1}: 기준 {img_thr(fkey, j2):.2f} · "
                             f"그림 {len(img_list(fkey, j2))}장"
                             f"(전용 {img_mine_count(fkey, j2)}) · "
                             f"고르기 {img_pick(fkey, j2)} · "
                             f"범위 {'있음' if os.path.exists(area_path(fkey, j2)) else '없음'}")
                try:
                    import ctypes as _c
                    L.append("")
                    L.append(f"화면 배율 {_c.windll.user32.GetDpiForSystem()*100//96}%")
                except Exception:
                    pass
                with open(os.path.join(out, "설정.txt"), "w", encoding="utf-8") as f:
                    f.write(chr(10).join(L))
                n += 1
            except Exception:
                pass
            subprocess.Popen(["explorer", out])
            self.status.set(f"📤 바탕화면 '진단_{fkey}' 폴더에 {n}개 모았습니다 — "
                            f"이 폴더를 통째로 보내주세요")
        except Exception as e:
            self.status.set(f"📤 모으기 실패: {e}")

    def _note(self, fkey, nm, msg):
        """실행 중 '잘 안 된 것'을 슬롯별로 모아둔다 — 끝나고 요약으로 보여준다.
        실행이 너무 빨라 화면으로는 못 보기 때문 (2026-08-27 사용자 요청)."""
        try:
            if not hasattr(self, "_run_note"):
                self._run_note = []
            self._run_note.append((str(nm), str(msg)))
        except Exception:
            pass

    def _run_summary(self, fkey, title):
        """실행이 끝나면 '무엇이 안 됐는지'를 기록에 남긴다.
        **창은 띄우지 않는다** (2026-08-27 사용자 지시 — 매번 닫아야 해서 불편).
        상태줄에 한 줄로만 알리고, 자세한 내용은 [📋 클릭기록] 에서 본다."""
        notes = getattr(self, "_run_note", None) or []
        if not notes:
            return
        try:
            byslot = {}
            for nm, msg in notes:
                byslot.setdefault(nm, []).append(msg)
            click_log(f"[결과] {fkey} 문제 있던 슬롯 {len(byslot)}개 · "
                      + " / ".join(f"{k}: {'; '.join(v)}" for k, v in byslot.items()))
            self.status.set(f"⚠ {title} — 잘 안 된 슬롯 {len(byslot)}개 "
                            f"(자세한 내용은 [📋 클릭기록])")
        except Exception:
            pass

    def _diag_images(self, fkey):
        """지금 16슬롯(클라)을 전부 훑어 그림이 잡히는지 슬롯별로 보여준다.
        컴퓨터마다 해상도·클라 크기가 달라 결과가 다르므로, 로컬에서 '가끔 안 된다'는
        문제를 찾을 때 이것부터 누른다. 결과는 클릭기록에도 남는다 (2026-08-27)."""
        key, title, icon = self._dgn2_info(fkey)
        nclk = self._grid_spec(fkey)["clicks"]
        js = [j for j in range(nclk) if has_img(fkey, j)]
        if not js:
            self.status.set("🩺 이 런처에는 지정한 그림이 없습니다"); return
        slots = self.cfg.get(key) or []
        rows = []
        self.status.set("🩺 진단 중… (16클라를 훑는 중)")
        self.update_idletasks()
        for i, sl in enumerate(slots):
            anc = slot_anchor(sl)
            if not anc:
                continue
            nm = (sl.get("name") or f"#{i+1}").strip()
            rc = client_rect_at(anc[0], anc[1])
            got = []
            for j in js:
                x, y, sc = find_image(fkey, j, anc)
                got.append((j + 1, sc, x is not None, img_thr(fkey, j)))
            rows.append((i + 1, nm, rc, got))
        if not rows:
            self.status.set("🩺 좌표가 등록된 슬롯이 없습니다"); return

        w = tk.Toplevel(self); w.title(f"🩺 {title} 이미지 진단")
        w.attributes("-topmost", True)
        tk.Label(w, text=f"{title} — 지금 화면에서 그림이 잡히는지",
                 font=("맑은 고딕", 13, "bold")).pack(padx=14, pady=(12, 2))
        # 클라 창 크기가 다르면 그림이 안 맞는다 — 제일 흔한 원인이라 먼저 보여준다
        sizes = {}
        for _i, _n, rc, _g in rows:
            if rc:
                sizes[(rc[2] - rc[0], rc[3] - rc[1])] = sizes.get(
                    (rc[2] - rc[0], rc[3] - rc[1]), 0) + 1
        szt = " · ".join(f"{a}×{b} ({c}개)" for (a, b), c in
                         sorted(sizes.items(), key=lambda kv: -kv[1]))
        try:
            import ctypes as _c
            _aw = _c.c_int(0)
            _c.windll.shcore.GetProcessDpiAwareness(None, _c.byref(_aw))
            _dpi = _c.windll.user32.GetDpiForSystem()
            tk.Label(w, text=f"화면 배율 {_dpi*100//96}%  ·  DPI 인식 {_aw.value} "
                             f"(2 = 모니터별, 이 값이 메인과 같아야 좌표가 맞는다)",
                     font=("맑은 고딕", 9), fg="#888").pack()
        except Exception:
            pass
        tk.Label(w, text=f"클라 창 크기: {szt or '알 수 없음'}",
                 font=("맑은 고딕", 10),
                 fg=("#c0392b" if len(sizes) > 1 else "#888")).pack()
        if len(sizes) > 1:
            tk.Label(w, text="⚠ 클라 창 크기가 서로 다릅니다 — 그림이 안 잡히는 원인입니다",
                     font=("맑은 고딕", 10, "bold"), fg="#c0392b").pack()
        _nowin = sum(1 for _i, _n, rc, _g in rows if not rc)
        if _nowin:
            tk.Label(w, text=f"⚠ {_nowin}개 슬롯은 그 좌표에 리니지M 창이 없습니다 — "
                             f"좌표가 이 컴퓨터와 안 맞는 것입니다",
                     font=("맑은 고딕", 11, "bold"), fg="#c0392b").pack()
        tk.Label(w, text=f"등록된 그림: "
                         + " · ".join(f"좌표{j+1} {len(img_list(fkey, j))}장" for j in js),
                 font=("맑은 고딕", 9), fg="#888").pack()
        bd = tk.Frame(w); bd.pack(padx=14, pady=8)
        hdr = ["슬롯"] + [f"좌표{j+1}" for j in js]
        for c, t in enumerate(hdr):
            tk.Label(bd, text=t, font=("맑은 고딕", 9, "bold"),
                     width=(16 if c == 0 else 9)).grid(row=0, column=c)
        okn = 0
        for r, (idx, nm, rc, got) in enumerate(rows, start=1):
            tk.Label(bd, text=f"{idx:02d} {nm[:12]}", font=("맑은 고딕", 9),
                     width=16, anchor="w").grid(row=r, column=0, sticky="w")
            for c, (jn, sc, ok, thr) in enumerate(got, start=1):
                if ok: okn += 1
                tk.Label(bd, text=f"{sc:.2f}", font=("맑은 고딕", 9, "bold"),
                         width=9, fg=("#196f3d" if ok else "#c0392b")).grid(row=r, column=c)
        tot = len(rows) * len(js)
        tk.Label(w, text=f"잡힘 {okn} / {tot}  (기준 "
                         + " · ".join(f"좌표{j+1} {img_thr(fkey, j):.2f}" for j in js) + ")",
                 font=("맑은 고딕", 12, "bold")).pack(pady=(2, 0))
        tk.Label(w, text="초록 = 기준을 넘어 잡힘 · 빨강 = 못 잡음",
                 font=("맑은 고딕", 9), fg="#888").pack()
        tk.Label(w, text="지금 그 창에 그 그림이 실제로 떠 있어야 초록입니다",
                 font=("맑은 고딕", 9), fg="#888").pack()
        tk.Button(w, text="닫기", font=("맑은 고딕", 10),
                  command=w.destroy).pack(pady=10)
        try:
            click_log(f"[진단] {fkey} 잡힘 {okn}/{tot} · 창크기 {szt} · "
                      + " / ".join(f"{idx:02d}:" + ",".join(f"{sc:.2f}" for _j, sc, _o, _t in got)
                                   for idx, _n, _rc, got in rows))
        except Exception:
            pass
        try:
            apply_dark(w, self._dark_on())
        except Exception:
            pass
        self.status.set(f"🩺 진단 끝 — 잡힘 {okn}/{tot}")

    def _reg_dgn2_click(self, fkey, slot_idx, click_idx):
        key, title, _ = self._dgn2_info(fkey)
        self._reg_dgn2 = (fkey, slot_idx, click_idx)
        self.status.set(f"3초 후 {title} #{slot_idx+1} [클릭{click_idx+1}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="dgn2")])

    def on_dgn2_coord(self, x, y):
        fkey, si, ci = self._reg_dgn2
        key, title, _ = self._dgn2_info(fkey)
        self.cfg[key][si]["coords"][ci] = [x, y]
        if fkey == "circus" and ci == 7:      # 9번은 8번을 따라간다
            cs = self.cfg[key][si]["coords"]
            while len(cs) < CIRCUS_CLICKS: cs.append(None)
            cs[8] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ {title} #{si+1} [클릭{ci+1}] 등록: ({x},{y})")
        self.deiconify()

    def _test_dgn2(self, fkey, idx):
        self._minimize_all()
        threading.Thread(target=self._run_dgn2, args=(fkey, idx), daemon=True).start()

    def _del_dgn2(self, fkey, idx):
        key, title, _ = self._dgn2_info(fkey)
        if not messagebox.askyesno("슬롯 삭제", f"{title} #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg[key][idx] = {"name": "미등록", "coords": [None]*self._grid_spec(fkey)["clicks"]}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_dgn2(self, fkey, idx):
        key, title, _ = self._dgn2_info(fkey)
        coords = self.cfg[key][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"{title} #{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg[key][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_dgn2 = (fkey, idx, dot_idx if dot_idx is not None else 0)
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="dgn2"))

        def _save(dot_idx, nx, ny):
            self.cfg[key][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ {title} #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"{title} #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    @staticmethod
    def _send_key_input_cp(scan, flags):
        # 게임 클라이언트가 못 씹는 저수준 SendInput 키 전송 (스캔코드/유니코드 공용)
        import ctypes
        PUL = ctypes.c_void_p
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", PUL)]
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
        class _IN(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("u", _IN)]
        inp = INPUT(type=1)
        inp.u.ki = KEYBDINPUT(0, scan, flags, 0, None)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _focus_client_at(self, coord):
        """그 좌표에 있는 리니지M 창을 앞으로 가져온다.
        커서 없는 클릭(메시지 전달)은 창을 활성화하지 않아서, 그대로 Ctrl+V를 보내면
        엉뚱한 창(또는 아무 데도)에 붙는다 → 붙여넣기 직전에 이 창을 활성화한다."""
        try:
            import win32gui, win32con, win32process, ctypes
            hwnd = win32gui.WindowFromPoint((int(coord[0]), int(coord[1])))
            root = ctypes.windll.user32.GetAncestor(hwnd, 2)      # GA_ROOT
            if not root:
                return False
            title = win32gui.GetWindowText(root)
            if not title.startswith("리니지M"):
                return False
            if win32gui.GetForegroundWindow() == root:
                return True
            try:                     # 다른 스레드 창은 그냥은 못 올려서 입력 큐를 붙였다 뗀다
                cur = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
                tgt = win32process.GetWindowThreadProcessId(root)[0]
                ctypes.windll.user32.AttachThreadInput(cur, tgt, True)
                try:
                    win32gui.SetForegroundWindow(root)
                finally:
                    ctypes.windll.user32.AttachThreadInput(cur, tgt, False)
            except Exception:
                pass
            if win32gui.GetForegroundWindow() != root:
                # 윈도우가 창 올리기를 막을 때 — ALT를 한 번 눌렀다 떼면 잠금이 풀린다
                try:
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                    win32gui.SetForegroundWindow(root)
                except Exception:
                    pass
            time.sleep(0.25)
            return win32gui.GetForegroundWindow() == root
        except Exception:
            return False

    def _paste_at(self, coord, txt, label=""):
        """붙여넣기 자리 — 진짜 커서로 눌러 그 창을 앞으로 세운 뒤 Ctrl+V, Enter.
        (커서 없는 클릭은 창을 활성화하지 못해 Ctrl+V가 엉뚱한 곳으로 간다)"""
        pyautogui.moveTo(*coord); time.sleep(0.15)
        pyautogui.click()
        try:
            time.sleep(random.uniform(1.3, 1.7))
            _fw = self._focus_client_at(coord)
            self._coupon_log(f"{label} 창 활성화 {'성공' if _fw else '실패/불필요'} {tuple(coord)}")
            ok = self._set_clipboard_text(txt)
            self._coupon_log(f"{label} 클립보드 복사 {'성공' if ok else '실패'}: {txt!r}")
            time.sleep(0.15)
            self._paste_ctrl_v()
            self._coupon_log(f"{label} Ctrl+V 전송 완료")
            time.sleep(random.uniform(0.6, 0.9))
            # 입력칸이 살아 있으면 다음 클릭을 게임이 씹으므로 Enter로 입력 확정
            self._send_key_input_cp(0x1C, 0x0008)
            time.sleep(0.08)
            self._send_key_input_cp(0x1C, 0x0008 | 0x0002)
            self._coupon_log(f"{label} Enter(입력 확정) 전송 완료")
            time.sleep(random.uniform(0.5, 0.8))
            return True
        except Exception as e:
            self._coupon_log(f"{label} 붙여넣기 오류: {e!r}")
            return False

    def _paste_ctrl_v(self):
        # Ctrl(0x1D)+V(0x2F) 스캔코드 순서대로 누르고 떼기 — 게임 프레임이 놓치지 않게 여유 있게
        self._send_key_input_cp(0x1D, 0x0008);          time.sleep(0.12)
        self._send_key_input_cp(0x2F, 0x0008);          time.sleep(0.12)
        self._send_key_input_cp(0x2F, 0x0008 | 0x0002); time.sleep(0.08)
        self._send_key_input_cp(0x1D, 0x0008 | 0x0002)

    def _type_text_cp(self, text, stop_attr=None):
        # 유니코드 SendInput으로 글자를 한 자씩 직접 입력 — 클립보드/키배열 무관, 게임에서도 확실
        import struct
        data = str(text).encode("utf-16-le")
        units = struct.unpack(f"<{len(data)//2}H", data)
        for u in units:
            if stop_attr and getattr(self, stop_attr, False):
                return
            self._send_key_input_cp(u, 0x0004)              # KEYEVENTF_UNICODE down
            time.sleep(0.03)
            self._send_key_input_cp(u, 0x0004 | 0x0002)     # up
            time.sleep(random.uniform(0.04, 0.09))

    @staticmethod
    def _coupon_log(msg):
        # 쿠폰등록 진단 로그 — %LOCALAPPDATA%\MoonAI\coupon_debug.log
        try:
            import datetime
            d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MoonAI")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "coupon_debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%H:%M:%S.%f}] {msg}\n")
        except Exception:
            pass

    @staticmethod
    def _set_clipboard_text(text):
        # 실행 스레드에서도 안전한 Win32 클립보드 쓰기 (tk 클립보드는 메인스레드 전용)
        import ctypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        for _ in range(5):
            if u32.OpenClipboard(0): break
            time.sleep(0.05)
        else:
            return False
        try:
            u32.EmptyClipboard()
            data = str(text).encode("utf-16-le") + b"\x00\x00"
            h = k32.GlobalAlloc(0x0042, len(data))   # GMEM_MOVEABLE | GMEM_ZEROINIT
            if not h:
                return False
            p = k32.GlobalLock(h)
            if not p:
                return False
            ctypes.memmove(p, data, len(data))
            k32.GlobalUnlock(h)
            u32.SetClipboardData(13, h)              # CF_UNICODETEXT
        finally:
            u32.CloseClipboard()
        return True

    def _start_dgn2(self, fkey, sel_list=None):
        key, title, _ = self._dgn2_info(fkey)
        if not self._try_busy_or_queue(title, lambda: self._start_dgn2(fkey, sel_list)): return
        setattr(self, f"_{fkey}_stop", False)
        self._set_btn(f"btn_{fkey}_run", state="disabled")
        self._set_btn(f"btn_{fkey}_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(
            target=self._run_task,
            args=(title, lambda: self._run_dgn2(fkey, sel_list=sel_list)), daemon=True).start())

    def _start_dgn2_sel(self, fkey):
        """+ 로 고른 슬롯만 실행 — 고른 게 없으면 전체."""
        sel = sorted((getattr(self, "_grid_sel", None) or {}).get(fkey) or [])
        title = self._dgn2_info(fkey)[1]
        if not sel:                      # 아무것도 안 골랐으면 실행하지 않는다
            self.status.set(f"{title} — 슬롯을 고르세요 ([+] 를 눌러 선택)"); return
        self._start_dgn2(fkey, sel)
        self.status.set(f"{title} — {[i+1 for i in sel]}번 실행")

    def _grid_sel_toggle(self, fkey, idx):
        sel = (getattr(self, "_grid_sel", None) or {}).setdefault(fkey, set())
        sel.discard(idx) if idx in sel else sel.add(idx)
        self._refresh_grid_sel(fkey)

    def _grid_sel_clear(self, fkey):
        (getattr(self, "_grid_sel", None) or {})[fkey] = set()
        self._refresh_grid_sel(fkey)

    def _refresh_grid_sel(self, fkey):
        sel = (getattr(self, "_grid_sel", None) or {}).get(fkey) or set()
        for i, b in enumerate((getattr(self, "_grid_selbtns", None) or {}).get(fkey) or []):
            try:
                on = i in sel
                b.config(text="✔" if on else "+",
                         bg="#e67e22" if on else "#dfe3e6",
                         fg="white" if on else "#e67e22")
            except Exception:
                pass
        self.status.set(f"{self._dgn2_info(fkey)[1]} 선택 {sorted(i+1 for i in sel)}"
                        if sel else "선택 없음")

    @staticmethod
    def _slot_wheel(slot, j):
        """이 칸에 지정된 휠 칸수 (0이면 그냥 클릭)."""
        try:
            wl = slot.get("wheel_list") or []
            return int(wl[j]) if j < len(wl) and wl[j] else 0
        except Exception:
            return 0

    @staticmethod
    def _slot_gap(slot, j, default=None):
        """이 칸에 지정된 '다음 좌표까지 기다릴 초' — 없으면 None."""
        try:
            gl = slot.get("gap_list") or []
            v = gl[j] if j < len(gl) else None
            if v in (None, ""):
                return default
            t = str(v).strip()
            if "~" in t:                      # '2~4' 처럼 범위도 허용
                a_, b_ = t.split("~")
                return random.uniform(float(a_), float(b_))
            return float(t)
        except Exception:
            return default

    LOG_FKEYS = ("knight", "dragon")      # 클릭이 어느 창에 갔는지 기록해두는 런처
    FOCUS_FIRST = ()                      # 슬롯이 바뀌면 그 클라를 먼저 앞으로 올릴 런처
    # 좌표 하나하나 누르기 직전에 '사람이 마우스를 놓았는지' 확인하는 런처
    # (사용자가 제일 중요하게 보는 것 — 겹치면 팅긴다)
    CLICK_GUARD = ("dragon", "knight", "sched")

    def _click_log(self, fkey, j, coord, slot, act):
        """이 클릭이 '리니지M 창'에 제대로 갔는지 기록한다 (씹힘 찾기용)."""
        if fkey not in self.LOG_FKEYS:
            return
        nm = (slot or {}).get("name", "?")
        tt, ok = click_target(coord[0], coord[1])
        if ok:
            click_log(f"{fkey} [{nm}] 좌표{j+1} ({coord[0]},{coord[1]}) {act} → {tt}")
        else:
            click_log(f"{fkey} [{nm}] 좌표{j+1} ({coord[0]},{coord[1]}) {act} "
                      f"→ ⚠ 그 자리에 리니지M 창이 없음"
                      + (f" (덮은 창: {tt})" if tt else ""))
            try:
                self.status.set(f"⚠ [{nm}] 좌표{j+1} — 그 자리에 리니지M 창이 없습니다 "
                                f"(클릭이 씹히는 자리)")
            except Exception:
                pass

    def _wait_gap(self, stop, name, j, secs):
        """좌표 사이 대기 — 남은 초를 계속 보여준다 (멈춘 것처럼 보이지 않게)."""
        t_end = time.time() + secs
        while True:
            left = t_end - time.time()
            if left <= 0 or getattr(self, stop, False):
                return
            if secs >= 3.0:
                self.status.set(f"⏳ [{name}] 좌표{j+1} 다음까지 {left:.0f}초 "
                                f"(이번 대기 {secs:.1f}초)")
            time.sleep(min(0.4, max(0.05, left)))

    def _open_click_log(self):
        """클릭 기록 파일을 연다 — 어느 클릭이 리니지M 창에 안 갔는지 볼 수 있다."""
        try:
            os.makedirs(LOCAL_DATA, exist_ok=True)
            if not os.path.exists(CLICK_LOG):
                click_log("(기록 시작)")
            os.startfile(CLICK_LOG)
            self.status.set("클릭 기록을 열었습니다 — ⚠ 표시가 씹힌 자리입니다")
        except Exception as e:
            self.status.set(f"기록 열기 실패: {e}")

    def _clear_click_log(self):
        try:
            open(CLICK_LOG, "w", encoding="utf-8").close()
            self.status.set("클릭 기록을 비웠습니다")
        except Exception as e:
            self.status.set(f"기록 비우기 실패: {e}")

    def _user_focus_snap(self):
        """사용자가 방금까지 조작하던 게임 창과 커서 위치를 기억한다.
        자동 클릭은 그 창을 앞으로 끌어올려(포커스를 뺏어) 캐릭터 이동을 끊는다 —
        클릭 직후 원래 창으로 돌려주기 위한 것. 한동안 안 만졌으면 None."""
        try:
            import precise_click as _pc
            if _pc.idle_seconds() > 8.0:       # 안 만지고 있으면 되돌릴 이유가 없다
                return None
            import win32gui
            h = win32gui.GetForegroundWindow()
            if not h or not _pc.is_game_window(h):
                return None                    # 게임 창을 보고 있을 때만
            return (h, pyautogui.position())
        except Exception:
            return None

    def _user_focus_back(self, snap, move_cursor=True):
        """기억해둔 창을 다시 앞으로, 커서도 원래 자리로 (이동이 안 끊기게)."""
        if not snap:
            return
        h, pos = snap
        try:
            import win32gui, win32process, ctypes
            fg = win32gui.GetForegroundWindow()
            if fg != h and win32gui.IsWindow(h):
                try:      # 다른 스레드 창은 그냥은 못 올려서 입력 큐를 붙였다 뗀다
                    cur = win32process.GetWindowThreadProcessId(fg)[0]
                    tgt = win32process.GetWindowThreadProcessId(h)[0]
                    ctypes.windll.user32.AttachThreadInput(cur, tgt, True)
                    try:
                        win32gui.SetForegroundWindow(h)
                    finally:
                        ctypes.windll.user32.AttachThreadInput(cur, tgt, False)
                except Exception:
                    pass
            if move_cursor and pos:
                pyautogui.moveTo(int(pos[0]), int(pos[1]))
        except Exception:
            pass

    def _grab_click_image(self, fkey, idx, j, btn=None):
        """그 좌표 자리에서 찾을 그림을 화면에서 드래그해 저장한다.
        저장하면 실행 때 좌표 대신 '그 그림'을 찾아 누르고,
        못 찾으면 그 슬롯은 거기서 끝낸다 (다른 슬롯은 계속)."""
        self._img_target = (fkey, idx, j, btn)
        self.status.set(f"🖼 {self._dgn2_info(fkey)[1]} 좌표{j+1} — "
                        f"찾을 그림을 화면에서 드래그하세요 (ESC 취소)")
        for w in self._section_wins():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(250, lambda: _PotionAreaOverlay(self, self._on_click_image))

    def _on_click_image(self, x, y, w, h):
        """드래그한 영역을 그림 파일로 저장."""
        self.deiconify()
        for wn in self._section_wins():
            try: wn.deiconify()
            except Exception: pass
        tgt = getattr(self, "_img_target", None)
        if not tgt:
            return
        fkey, idx, j, btn = tgt
        if w < 6 or h < 6:
            self.status.set("🖼 너무 작습니다 — 다시 드래그해주세요"); return
        try:
            from PIL import ImageGrab
            im = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
            if os.path.exists(img_path(fkey, j)):
                # 공용 그림이 이미 있으면 → '이 컴퓨터 전용'으로 한 장 더 추가한다.
                # 컴퓨터마다 아이콘이 달라 보이므로, 각자 자기 화면에서 찍어 쓴다.
                # 이 폴더는 업데이트가 절대 덮어쓰지 않는다 (2026-08-27).
                n = img_mine_free(fkey, j)
                os.makedirs(IMG_DIR_MINE, exist_ok=True)
                im.save(img_mine_path(fkey, j, n))
                _c = img_mine_count(fkey, j)
                msg = (f"🖼 좌표{j+1} — 이 컴퓨터 전용 그림 {_c}장째 추가 ({w}×{h}). "
                       f"공용 1장 + 전용 {_c}장 중 하나만 맞으면 찾은 것으로 봅니다")
            else:
                os.makedirs(IMG_DIR, exist_ok=True)
                im.save(img_path(fkey, j))
                msg = (f"🖼 좌표{j+1} 그림 저장 ({w}×{h}) — "
                       f"실행 때 이 그림을 찾아 누릅니다 (못 찾으면 그 슬롯 중단)")
            if btn and btn.winfo_exists():
                _n = len(img_list(fkey, j))
                btn.config(text=("🖼있음" if _n <= 1 else f"🖼{_n}장"), bg="#8e44ad")
            self.status.set(msg)
        except Exception as e:
            self.status.set(f"🖼 저장 실패: {e}")

    def _toggle_check_only(self, fkey, j, btn=None):
        """👁 확인만 켜기/끄기 — 그 자리는 누르지 않고 그림 확인만 한다.
        보이면 통과, 안 보이면 그 슬롯 중단 (예: 복구 창의 '무료' 글자)."""
        on = not is_check_only(fkey, j)
        set_check_only(fkey, j, on)
        if btn and btn.winfo_exists():
            btn.config(text=("👁확인만" if on else "👁"),
                       bg=("#117a65" if on else "#5d6d7e"))
        if on:
            self.status.set(f"👁 좌표{j+1} — 이 자리는 **누르지 않고** 그림 확인만 합니다. "
                            f"그림이 안 보이면 그 슬롯을 끝냅니다")
        else:
            self.status.set(f"👁 좌표{j+1} — 확인만 해제 (평소대로 누릅니다)")

    def _grab_no_image(self, fkey, idx, j, btn=None):
        """⛔ 금지 그림 지정 — 이게 보이면 누르지 않고 ESC 로 취소하고 슬롯을 끝낸다.
        (예: '다이아로 복구하시겠습니까?' 같은 재화 쓰는 창)"""
        self._no_target = (fkey, idx, j, btn)
        self.status.set(f"⛔ 좌표{j+1} — '이게 뜨면 취소할 그림'을 드래그하세요 "
                        f"(재화 쓰는 창 등 · ESC 취소)")
        for w in self._section_wins():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(250, lambda: _PotionAreaOverlay(self, self._on_no_image))

    def _on_no_image(self, x, y, w, h):
        self.deiconify()
        for wn in self._section_wins():
            try: wn.deiconify()
            except Exception: pass
        tgt = getattr(self, "_no_target", None)
        if not tgt:
            return
        fkey, idx, j, btn = tgt
        if w < 6 or h < 6:
            self.status.set("⛔ 너무 작습니다 — 다시 드래그해주세요"); return
        try:
            from PIL import ImageGrab
            os.makedirs(IMG_DIR, exist_ok=True)
            im = ImageGrab.grab(bbox=(x, y, x + w, y + h),
                                all_screens=True).convert("RGB")
            im.save(no_path(fkey, j))
            if btn and btn.winfo_exists():
                btn.config(text="⛔있음", bg="#c0392b")
            self.status.set(f"⛔ 좌표{j+1} 금지 그림 저장 ({w}×{h}) — "
                            f"이게 보이면 누르지 않고 ESC 로 취소합니다")
        except Exception as e:
            self.status.set(f"⛔ 저장 실패: {e}")

    def _del_no_image(self, fkey, j, btn=None):
        """금지 그림 지우기 (오른쪽 클릭)."""
        try:
            os.remove(no_path(fkey, j))
            if btn and btn.winfo_exists():
                btn.config(text="⛔", bg="#5d6d7e")
            self.status.set(f"⛔ 좌표{j+1} 금지 그림 삭제")
        except Exception as e:
            self.status.set(f"⛔ 삭제 실패: {e}")

    def _grab_click_area(self, fkey, idx, j, btn=None):
        """그 그림을 찾을 '범위'를 화면에서 드래그해 정한다.
        드래그한 자리가 어느 클라 창 안인지 보고, 그 창 기준 위치로 저장한다 →
        슬롯(클라)이 달라도 각 창의 같은 자리를 훑는다."""
        self._area_target = (fkey, idx, j, btn)
        self.status.set(f"📐 좌표{j+1} — 그림을 '찾을 범위'를 드래그하세요 "
                        f"(그 그림이 뜨는 자리를 넉넉히 감싸기 · ESC 취소)")
        for w in self._section_wins():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(250, lambda: _PotionAreaOverlay(self, self._on_click_area))

    def _on_click_area(self, x, y, w, h):
        self.deiconify()
        for wn in self._section_wins():
            try: wn.deiconify()
            except Exception: pass
        tgt = getattr(self, "_area_target", None)
        if not tgt:
            return
        fkey, idx, j, btn = tgt
        if w < 10 or h < 10:
            self.status.set("📐 너무 작습니다 — 다시 드래그해주세요"); return
        rc = client_rect_at(x + w // 2, y + h // 2)
        d = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        if rc:
            d.update(dx=int(x - rc[0]), dy=int(y - rc[1]))
        try:
            os.makedirs(IMG_DIR, exist_ok=True)
            with open(area_path(fkey, j), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            if btn and btn.winfo_exists():
                btn.config(text="📐범위", bg="#1a5276")
            # 실제로 마름모가 떴던 자리들이 이 안에 다 들어오는지 바로 확인해준다 —
            # 좁게 잡아서 못 찾는 사고를 막는다 (2026-08-28)
            msg = ("클라 창 기준이라 16슬롯 전부에 적용됩니다" if rc
                   else "⚠ 클라 창 밖이라 이 자리 그대로만 훑습니다")
            try:
                with open(zone_path(fkey, j), encoding="utf-8") as f:
                    pts = (json.load(f) or {}).get("pts") or []
            except Exception:
                pts = []
            if pts and rc:
                dx0, dy0 = int(x - rc[0]), int(y - rc[1])
                out = [q for q in pts
                       if not (dx0 <= q[0] <= dx0 + w and dy0 <= q[1] <= dy0 + h)]
                xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                if out:
                    msg = (f"⚠ 실제로 뜬 자리 {len(pts)}개 중 {len(out)}개가 이 범위 밖입니다 "
                           f"— 창 기준 x {min(xs)}~{max(xs)} · y {min(ys)}~{max(ys)} 를 "
                           f"덮도록 더 넓게 잡아주세요")
                else:
                    msg = (f"✔ 실제로 뜬 자리 {len(pts)}개가 모두 이 안에 들어옵니다 "
                           f"(x {min(xs)}~{max(xs)} · y {min(ys)}~{max(ys)})")
            self.status.set(f"📐 좌표{j+1} 범위 저장 ({w}×{h}) — " + msg)
        except Exception as e:
            self.status.set(f"📐 범위 저장 실패: {e}")

    def _auto_click_area(self, fkey, j, btn=None):
        """실제로 마름모가 떴던 자리들로 범위를 자동 계산해 저장한다 (가운데 클릭).
        손으로 그리는 것보다 정확하다 — 성공한 자리를 다 덮으면서 최소로 잡는다."""
        try:
            with open(zone_path(fkey, j), encoding="utf-8") as f:
                pts = (json.load(f) or {}).get("pts") or []
        except Exception:
            pts = []
        if len(pts) < ZONE_MIN:
            self.status.set(f"📐 아직 자료가 적습니다 ({len(pts)}/{ZONE_MIN}) — "
                            f"몇 번 더 돌린 뒤 눌러주세요")
            return
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        d = {"dx": min(xs) - ZONE_PAD, "dy": min(ys) - ZONE_PAD,
             "w": (max(xs) - min(xs)) + ZONE_PAD * 2,
             "h": (max(ys) - min(ys)) + ZONE_PAD * 2}
        try:
            os.makedirs(IMG_DIR, exist_ok=True)
            with open(area_path(fkey, j), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            if btn and btn.winfo_exists():
                btn.config(text="📐범위", bg="#1a5276")
            self.status.set(f"📐 좌표{j+1} 범위 자동 계산 완료 — "
                            f"{d['w']}×{d['h']} (실제로 뜬 {len(pts)}자리 + 여유 {ZONE_PAD}px)")
        except Exception as e:
            self.status.set(f"📐 자동 계산 실패: {e}")

    def _del_click_area(self, fkey, j, btn=None):
        """범위 지우기 — 그 클라 창 전체에서 찾는다."""
        try:
            os.remove(area_path(fkey, j))
            if btn and btn.winfo_exists():
                btn.config(text="📐", bg="#5d6d7e")
            self.status.set(f"📐 좌표{j+1} 범위 삭제 — 클라 창 전체에서 찾습니다")
        except Exception as e:
            self.status.set(f"📐 삭제 실패: {e}")

    def _cycle_img_thr(self, fkey, j, btn=None):
        """일치 기준 순환 0.90 → 0.85 → … → 0.55 → 0.50 → 0.90.
        용던고고 기본은 0.55 (2026-08-27 사용자 지시 — 뜨는 자리가 한 군데뿐이라
        낮춰도 오탐이 없다. 실측 잡음 0.27~0.30 이라 여유 0.25)."""
        opts = [0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]
        cur = img_thr(fkey, j)
        nxt = opts[(min(range(len(opts)), key=lambda i: abs(opts[i] - cur)) + 1) % len(opts)]
        try:
            set_img_thr(fkey, j, nxt)
            if btn and btn.winfo_exists():
                btn.config(text=f"🔍{nxt:.2f}")
            self.status.set(f"🔍 좌표{j+1} 일치 기준 {nxt:.2f} — "
                            f"작은 그림이 잘 안 잡히면 더 낮추세요 (오른쪽 클릭)")
        except Exception as e:
            self.status.set(f"기준 변경 실패: {e}")

    def _toggle_stop_at(self, fkey, j, btn=None):
        """'여기까지만 하고 끝' 켜기/끄기 — 그 좌표를 마치면 그 슬롯을 종료한다."""
        cur = stop_at(fkey)
        nxt = 0 if cur == j + 1 else j + 1
        set_stop_at(fkey, nxt)
        if btn and btn.winfo_exists():
            btn.config(text=("⏹여기끝" if nxt else "⏹"),
                       bg=("#c0392b" if nxt else "#5d6d7e"))
        if nxt:
            self.status.set(f"⏹ 좌표{nxt}까지만 하고 그 슬롯을 끝냅니다 "
                            f"(뒤 좌표는 실행 안 함)")
        else:
            self.status.set("⏹ 해제 — 끝까지 실행합니다")

    def _cycle_img_pick(self, fkey, j, btn=None):
        """같은 그림이 여럿일 때 고를 기준 — 최고일치 → 맨위 → 맨아래 → 맨왼쪽 → 맨오른쪽."""
        cur = img_pick(fkey, j)
        nxt = PICKS[(PICKS.index(cur) + 1) % len(PICKS)]
        set_img_pick(fkey, j, nxt)
        if btn and btn.winfo_exists():
            btn.config(text=PICK_TXT[nxt])
        self.status.set(f"🎯 좌표{j+1} — 같은 그림이 여러 개면 "
                        f"'{PICK_TXT[nxt]}' 것을 누릅니다")

    def _test_click_image(self, fkey, idx, j, btn=None):
        """지금 찾아본다 — 최고 일치도와 찾은 자리를 큰 창으로 보여준다.
        (셀이 작아 상태줄로는 확인이 어려워서 팝업으로 띄운다)"""
        try:
            slot = (self.cfg.get(self._dgn2_info(fkey)[0]) or [])[idx]
            coord = (slot.get("coords") or [None] * 30)[j]
        except Exception:
            coord = None
        if not coord:      # 그림만 지정한 자리 — 같은 슬롯의 다른 좌표로 창을 찾는다
            try:
                coord = slot_anchor(slot)
            except Exception:
                coord = None
        if not coord:
            self.status.set(f"🔍 슬롯{idx+1} — 이 슬롯에 좌표가 하나도 없습니다 "
                            f"(어느 클라인지 알 수 없어요)"); return
        if not has_img(fkey, j):
            self.status.set(f"🔍 좌표{j+1} — [🖼] 로 그림부터 지정해주세요"); return
        thr = img_thr(fkey, j)
        box = search_box(fkey, j, coord)
        ix, iy, sc = find_image(fkey, j, coord)
        w = tk.Toplevel(self); w.title("🔍 이미지 찾기 결과")
        w.attributes("-topmost", True)
        ok = ix is not None
        tk.Label(w, text=("찾음 ✔" if ok else "못 찾음 ✘"),
                 font=("맑은 고딕", 22, "bold"),
                 fg=("#196f3d" if ok else "#c0392b")).pack(padx=20, pady=(14, 4))
        tk.Label(w, text=f"일치도  {sc:.3f}   (기준 {thr:.2f} · "
                         f"{PICK_TXT[img_pick(fkey, j)]} 선택)",
                 font=("맑은 고딕", 16, "bold")).pack(padx=20)
        tk.Label(w, text=(f"찾은 자리: ({ix}, {iy})" if ok else
                          "기준보다 낮아서 이 자리는 건너뜁니다"),
                 font=("맑은 고딕", 11)).pack(pady=(2, 0))
        _n = len(img_list(fkey, j))
        tk.Label(w, text=f"등록된 그림 {_n}장 "
                         f"(공용 {1 if os.path.exists(img_path(fkey, j)) else 0} + "
                         f"이 컴퓨터 전용 {img_mine_count(fkey, j)})",
                 font=("맑은 고딕", 10)).pack()
        tk.Label(w, text=f"찾은 범위: {box[2]-box[0]}×{box[3]-box[1]} "
                         f"({box[0]},{box[1]})",
                 font=("맑은 고딕", 9), fg="#888").pack()
        if not ok and sc >= 0.50:
            def _apply(v=round(max(0.50, sc - 0.03), 2)):
                set_img_thr(fkey, j, v)
                if btn and btn.winfo_exists():
                    btn.config(text=f"🔍{v:.2f}")
                self.status.set(f"🔍 좌표{j+1} 일치 기준 {v:.2f} 로 낮췄습니다")
                w.destroy()
            tk.Button(w, text=f"기준을 {max(0.50, sc - 0.03):.2f} 로 낮추기",
                      font=("맑은 고딕", 10, "bold"), bg="#1a5276", fg="white",
                      command=_apply).pack(pady=(8, 0))
        tk.Button(w, text="닫기", font=("맑은 고딕", 10),
                  command=w.destroy).pack(pady=10)
        try:
            apply_dark(w, self._dark_on())
        except Exception:
            pass

    def _del_click_image(self, fkey, j, btn=None):
        """그림 지우기 (오른쪽 클릭). '이 컴퓨터 전용'이 있으면 그것부터 전부 지우고,
        없으면 공용 그림을 지운다 — 실수로 공용을 날리지 않게 한 단계 둔다."""
        try:
            n = img_mine_count(fkey, j)
            if n:
                for k in range(IMG_MAX):
                    try: os.remove(img_mine_path(fkey, j, k))
                    except Exception: pass
                msg = f"🖼 좌표{j+1} — 이 컴퓨터 전용 그림 {n}장 삭제 (공용은 그대로)"
            else:
                os.remove(img_path(fkey, j))
                msg = f"🖼 좌표{j+1} 그림 삭제 — 이제 좌표를 그냥 누릅니다"
            if btn and btn.winfo_exists():
                _c = len(img_list(fkey, j))
                btn.config(text=("🖼" if not _c else
                                 ("🖼있음" if _c == 1 else f"🖼{_c}장")),
                           bg=("#5d6d7e" if not _c else "#8e44ad"))
            self.status.set(msg)
        except Exception as e:
            self.status.set(f"🖼 삭제 실패: {e}")

    def _do_click_or_wheel(self, fkey, j, coord, slot=None):
        """휠 칸수가 지정된 자리면 클릭 대신 휠을 그만큼 위로 굴린다.
        HOVER_INDICES 에 적힌 자리는 클릭하지 않고 '마우스만 올려놓는다'."""
        if j in HOVER_INDICES.get(fkey, ()):
            self._click_log(fkey, j, coord, slot, "마우스올림")
            move_at(*coord)                   # 커서는 그대로, 그 자리에 올림 신호만
            return "마우스올림"
        # ⛔ 금지 그림 — 이게 보이면 **누르지 않고 ESC 로 취소**하고 이 슬롯을 끝낸다.
        # (재화를 쓰려는 창이 떴을 때 빠져나오는 안전장치, 2026-08-29 사용자 지시)
        if has_no_img(fkey, j) and coord:
            _nm0 = (slot or {}).get("name", "?")
            _nx, _ny, _ns = find_no_img(fkey, j, coord)
            if _nx is not None:
                press_esc(ESC_TIMES)
                click_log(f"{fkey} [{_nm0}] 좌표{j+1} ⛔ 금지 그림 보임 "
                          f"(일치도 {_ns:.2f}) → ESC {ESC_TIMES}번 누르고 이 슬롯 중단")
                self.status.set(f"⛔ [{_nm0}] 좌표{j+1} — 재화 쓰는 창이라 ESC 취소")
                self._note(fkey, _nm0, f"좌표{j+1} ⛔ 금지 그림 → ESC 취소")
                return "이미지없음"          # 이 슬롯만 끝, 다른 슬롯은 계속
        n = self._slot_wheel(slot, j) if slot else 0
        if not n and j in WHEEL_UP_INDICES.get(fkey, ()):
            n = WHEEL_UP_NOTCH                # 슬롯 설정이 없으면 기본값
        if n:
            # 휠도 커서를 옮기지 않고 그 자리에 메시지로 보낸다 (실패하면 예전 방식)
            import ctypes
            pyautogui.moveTo(*coord)
            time.sleep(0.08)
            if abs(int(n)) >= 10:
                # 많이 굴려야 하는 자리 (예: 맨 끝까지 내리기) — 적은 양을 여러 번
                # 나눠 보낸다. 한 번에 크게 보내면 게임이 무시하는 일이 있다.
                step = 3 if n > 0 else -3
                left = abs(int(n))
                while left > 0:
                    d = min(3, left)
                    try:
                        ctypes.windll.user32.mouse_event(
                            0x0800, 0, 0, (d if n > 0 else -d) * 120, 0)
                    except Exception:
                        pyautogui.scroll((d if n > 0 else -d) * 120)
                    left -= d
                    time.sleep(random.uniform(0.03, 0.07))
            else:
                for _ in range(WHEEL_UP_TIMES):
                    try:
                        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(n) * 120, 0)
                    except Exception:
                        pyautogui.scroll(int(n) * 120)
                    time.sleep(random.uniform(0.12, 0.25))
            return (f"휠▼{abs(n)}" if n < 0 else f"휠▲{n}")
        # 이 자리에 그림을 지정해뒀으면 그림을 찾아 그 자리를 누른다.
        # 못 찾으면 "이미지없음" 을 돌려줘서 그 슬롯을 여기서 끝낸다 (사용자 지시).
        _img_hit = False
        _win_fail = False        # 확인창이 끝내 안 떴나 (뜨면 다음 좌표를 안 누른다)
        # 이 슬롯에서 이미 이미지를 한 번 찾았으면 더 이상 찾지 않는다 —
        # 뒤 좌표에서 같은 그림을 또 찾아 눌러 되돌아가는 것을 막는다 (2026-08-27 사용자 지시)
        _done = getattr(self, "_img_done", None)
        if _done is None:
            _done = self._img_done = set()
        _slot_id = id(slot) if slot is not None else 0
        _cl0 = (slot or {}).get("coords") or []
        _own0 = bool(j < len(_cl0) and _cl0[j])
        # '그림을 눌러야 하는 자리(좌표 없음)'만 한 번으로 제한한다.
        # 좌표가 있는 자리의 그림은 '창이 떴는지 확인'용이라 매번 확인해야 한다
        # (안 그러면 창이 안 떴는데도 다음 좌표를 눌러버린다 — 2026-08-27 수정)
        if (not _own0) and (fkey, _slot_id) in _done:
            if coord:
                self._click_log(fkey, j, coord, slot, "클릭")
                click_at(*coord)
            return "클릭"
        if has_img(fkey, j):
            nm = (slot or {}).get("name", "?")
            try:      # 이 자리에 등록된 좌표가 따로 있나 (없으면 그림을 직접 누른다)
                _cl = (slot or {}).get("coords") or []
                _own_coord = bool(j < len(_cl) and _cl[j])
            except Exception:
                _own_coord = False
            # 앞 좌표를 누른 뒤 화면이 뜨는 데 시간이 걸린다 —
            # 못 찾으면 잠깐 기다렸다 다시 본다 (최대 IMG_TRIES 번, 2026-08-27)
            ix = iy = None
            sc = 0.0
            _chk_only = is_check_only(fkey, j)
            _tries = (CHECK_TRIES if _chk_only else IMG_TRIES)
            for _t in range(_tries):
                ix, iy, sc = find_image(fkey, j, coord)
                if ix is not None and sc < CONFIRM_MIN:
                    # 점수가 낮으면 **한 번 더 보고 같은 자리인지 확인**한다.
                    # 화면이 아직 다 안 그려졌을 때 배경 무늬를 집는 사고가 있었다
                    # (2026-08-28 주이 슬롯: 맨 땅을 0.61 로 눌렀다).
                    # 진짜 아이콘은 잠시 뒤에도 같은 자리에 있고 보통 점수가 오른다.
                    time.sleep(random.uniform(0.5, 0.8))
                    _cx, _cy, _cs = find_image(fkey, j, coord)
                    if (_cx is None or abs(_cx - ix) > CONFIRM_PX
                            or abs(_cy - iy) > CONFIRM_PX):
                        click_log(f"{fkey} [{nm}] 좌표{j+1} 낮은 점수({sc:.2f})가 "
                                  f"다시 보니 " +
                                  ("사라짐" if _cx is None else
                                   f"자리가 바뀜({_cx-ix:+d},{_cy-iy:+d})") +
                                  " → 배경으로 보고 다시 찾음")
                        ix = None
                    else:
                        ix, iy, sc = _cx, _cy, max(sc, _cs)
                if ix is not None:
                    break
                # 다음 자리의 그림(= 눌러서 뜨는 창)이 이미 보이면
                # 이 자리는 이미 처리된 것 — 재시도하지 않고 넘어간다 (2026-08-27 사용자 지시)
                if (not _own_coord) and has_img(fkey, j + 1):
                    _nx, _ny, _ns = find_image(fkey, j + 1, coord)
                    if _nx is not None:
                        click_log(f"{fkey} [{nm}] 좌표{j+1} — 다음 창이 이미 떠 있음 "
                                  f"(좌표{j+2} 그림 {_ns:.2f}) → 재시도 없이 넘어감")
                        self.status.set(f"🖼 [{nm}] 좌표{j+1} 창이 이미 떴음 — 넘어감")
                        _done.add((fkey, _slot_id))
                        return "이미열림"
                if _t < _tries - 1:
                    self.status.set(f"🖼 [{nm}] 좌표{j+1} "
                                    f"{'창이 뜨기를' if _own_coord else '그림을'} "
                                    f"기다리는 중… ({_t+1}/{_tries}, 지금 {sc:.2f})")
                    time.sleep(random.uniform(0.25, 0.45) if _chk_only
                               else random.uniform(1.0, 1.5))
            if ix is not None and is_check_only(fkey, j):
                # 👁 확인만 — 그림이 보였으니 **누르지 않고** 다음 좌표로 넘어간다
                click_log(f"{fkey} [{nm}] 좌표{j+1} 👁 확인만 — 그림 보임 "
                          f"(일치도 {sc:.2f}) → 누르지 않고 통과")
                self.status.set(f"👁 [{nm}] 좌표{j+1} 확인 통과 ({sc:.2f})")
                return "확인"
            if ix is None and _chk_only:
                # 👁 확인 실패(예: '무료'가 아니라 숫자) — 열린 창을 **ESC 두 번**으로
                # 닫고 빠져나온 뒤 이 슬롯을 끝낸다 (2026-08-29 사용자 지시).
                # 그냥 멈추면 복구 창이 열린 채로 남는다.
                save_miss_shot(fkey, j, coord)
                press_esc(ESC_TIMES)
                click_log(f"{fkey} [{nm}] 좌표{j+1} 👁 확인 실패 (최고 {sc:.2f}) "
                          f"→ ESC {ESC_TIMES}번 누르고 이 슬롯 중단")
                self.status.set(f"👁 [{nm}] 좌표{j+1} 다른 화면 ({sc:.2f}) — "
                                f"ESC {ESC_TIMES}번 누르고 중단")
                self._note(fkey, nm, f"좌표{j+1} 👁 확인 실패 — ESC 취소 (최고 {sc:.2f})")
                return "이미지없음"
            if ix is None:
                save_miss_shot(fkey, j, coord)      # 뭘 봤는지 사진으로 남긴다
                _bx = search_box(fkey, j, coord)
                _rc = client_rect_at(coord[0], coord[1])
                click_log(f"{fkey} [{nm}] 좌표{j+1} 이미지 못 찾음 "
                          f"(최고 일치도 {sc:.2f} / 기준 {img_thr(fkey, j):.2f}, "
                          f"{_tries}번 시도, 그림 {len(img_list(fkey, j))}장) "
                          f"· 훑은 범위 {_bx[2]-_bx[0]}×{_bx[3]-_bx[1]} @{_bx[0]},{_bx[1]} "
                          + ("" if _rc else "· ⚠ 리니지M 창을 못 찾아 좌표 주변만 훑음 ")
                          + f"→ 이 슬롯 여기서 중단 "
                          f"· 그때 본 화면: click_templates/_못찾음_{fkey}_{j+1:02d}.png")
                if not _rc:
                    self._note(fkey, nm, f"좌표{j+1} ⚠ 리니지M 창을 못 찾음 (좌표가 어긋남)")
                self.status.set(f"🖼 [{nm}] 좌표{j+1} 이미지 없음 — 이 슬롯 중단 "
                                f"(일치도 {sc:.2f})")
                self._note(fkey, nm,
                           (f"좌표{j+1} 👁 확인 실패 — 다른 화면 (최고 {sc:.2f})"
                            if is_check_only(fkey, j) else
                            (f"좌표{j+1} 창이 안 뜸 (최고 {sc:.2f})" if _own_coord
                             else f"좌표{j+1} 그림 못 찾음 (최고 {sc:.2f})")))
                return "이미지없음"
            # 좌표도 함께 등록돼 있으면 → 그림은 '창이 떴는지 확인'용.
            #   그림이 보일 때까지 기다렸다가 **등록한 좌표**를 누른다.
            # 좌표가 없으면 → 그림 가운데를 누른다. (2026-08-27 사용자 지시)
            if _own_coord:
                click_log(f"{fkey} [{nm}] 좌표{j+1} 그림 확인됨 (일치도 {sc:.2f}) "
                          f"→ 등록한 좌표 클릭")
                self.status.set(f"🖼 [{nm}] 좌표{j+1} 창 떴음 (일치도 {sc:.2f}) — 좌표 클릭")
            else:
                click_log(f"{fkey} [{nm}] 좌표{j+1} 이미지 찾음 ({ix},{iy}) "
                          f"일치도 {sc:.2f}")
                self.status.set(f"🖼 [{nm}] 좌표{j+1} 이미지 찾음 (일치도 {sc:.2f}) "
                                f"— 가운데 클릭")
                coord = (ix, iy)
                _img_hit = True
                _done.add((fkey, _slot_id))   # 그림 클릭은 이 슬롯에서 한 번만
        self._click_log(fkey, j, coord, slot, "클릭")
        snap = None
        if fkey in self.CLICK_GUARD:
            self._wait_user_free(f"_{fkey}_stop")   # 사람이 마우스 놓을 때까지
            if fkey != "sched":                     # 스케줄은 슬롯이 끝난 뒤에 되돌린다
                snap = self._user_focus_snap()      # 지금 사용자가 보던 창·커서
        if _img_hit:
            # 그림을 찾아 누를 때는 그 창을 먼저 앞으로 — 비활성 창의 첫 클릭은
            # '창 띄우기'로만 먹히고 사라진다 (좌표 클릭과 똑같이 들어가게, 2026-08-27)
            try:
                self._focus_client_at(coord)
                time.sleep(random.uniform(0.25, 0.45))
            except Exception:
                pass
            try:      # 그 자리에 지금 '어느 창'이 떠 있는지 기록 (가려져 있으면 여기서 드러난다)
                import win32gui, ctypes as _ct
                _h = win32gui.WindowFromPoint((int(coord[0]), int(coord[1])))
                _r = _ct.windll.user32.GetAncestor(_h, 2)
                click_log(f"{fkey} 좌표{j+1} 누르기 직전 맨 위 창 = "
                          f"[{win32gui.GetWindowText(_r)}]")
            except Exception:
                pass
        if _img_hit:
            # 게임 화면 안의 아이콘은 '커서를 올려 대상이 잡힌 뒤' 눌러야 반응한다 —
            # 그래서 먼저 그 자리에 커서를 올리고 잠깐 뒤에 누른다 (2026-08-27)
            try:
                move_at(*coord)
                time.sleep(random.uniform(0.35, 0.6))
            except Exception:
                pass
        if _img_hit:
            # 무엇을 눌렀는지 사진으로 남긴다 (오탐 확인용 — 2026-08-27)
            try:
                from PIL import ImageGrab, ImageDraw
                _sx, _sy = int(coord[0]), int(coord[1])
                _im = ImageGrab.grab(bbox=(_sx - 60, _sy - 50, _sx + 60, _sy + 50),
                                     all_screens=True).convert("RGB")
                _dr = ImageDraw.Draw(_im)
                _dr.ellipse([48, 38, 72, 62], outline=(255, 0, 0), width=2)
                os.makedirs(IMG_DIR, exist_ok=True)
                try:      # 슬롯 이름이 전부 '미등록'이라 창 이름으로 구분한다
                    import precise_click as _pc2
                    _h2 = _pc2.game_window_at(int(coord[0]), int(coord[1]))
                    _t2 = _pc2.window_title(_h2).replace("리니지M l ", "") if _h2 else ""
                except Exception:
                    _t2 = ""
                _nm2 = re.sub(r"[^\w가-힣]", "",
                              _t2 or str((slot or {}).get("name", "?")))[:10]
                _im.save(os.path.join(
                    IMG_DIR, f"_누른자리_{fkey}_{j+1:02d}_{_nm2}.png"))
            except Exception:
                pass
            # 찾은 뒤 [창 띄우기 → 커서 올리기] 로 1초쯤 지난다. 그 사이 화면이
            # 밀리거나(캐릭터 이동·카메라) 아이콘이 다시 그려질 수 있으므로
            # **누르기 직전에 위치를 한 번 더 확인**한다 — 어긋나 있으면 새 자리로.
            # (마름모 본체는 고정이고 옆 날개만 애니메이션이라 보통 0px 이다 —
            #  값이 크게 나오면 그건 화면이 밀린 것이다. 2026-08-27)
            try:
                _fx, _fy, _fs = find_image(fkey, j, coord)
                if _fx is not None:
                    _dx, _dy = _fx - coord[0], _fy - coord[1]
                    # 멀리 잡혔으면 '움직인 것'이 아니라 **다른 마름모**다 — 무시한다.
                    # (위·아래에 같은 아이콘이 있어 엉뚱한 층으로 가던 문제 방지)
                    if abs(_dx) > DRIFT_MAX or abs(_dy) > DRIFT_MAX:
                        _fx = None
                    elif abs(_dx) > 2 or abs(_dy) > 2:
                        click_log(f"{fkey} [{nm}] 좌표{j+1} 자리가 어긋나 있었음 "
                                  f"({_dx:+d},{_dy:+d}) → 새 자리로 다시 겨냥")
                        coord = (_fx, _fy)
                        move_at(*coord)
                        time.sleep(random.uniform(0.12, 0.22))
            except Exception:
                pass
            _learn = grab_patch(fkey, j, coord)   # 성공하면 배울 그림 (미리 떠 둔다)
            click_hold(*coord)          # 그림 자리는 꾹 눌렀다 뗀다 (게임이 확실히 받게)
        else:
            click_at(*coord)
        if _img_hit:
            time.sleep(random.uniform(0.35, 0.55))  # 게임이 클릭을 처리할 시간
            # 눌렀는데 '뜨기로 한 창'이 안 뜨면 = 게임이 그 클릭을 안 먹은 것.
            # 아이콘이 아닌 '창'을 보고 판단하므로 두 번 눌릴 염려가 없다
            # (2026-08-27 사용자 지시 — 씹혔을 때 스스로 회복하게).
            # 로컬에서 '창이 안 뜬다'가 잦아 2회까지, 갈수록 더 길게 누른다.
            if has_img(fkey, j + 1):
                for _try in range(RECLICK_TRIES):
                    _w = RECLICK_WAIT[min(_try, len(RECLICK_WAIT) - 1)]
                    time.sleep(_w * random.uniform(0.9, 1.15))
                    _wx, _wy, _ws = find_image(fkey, j + 1, coord)
                    if _wx is not None:
                        if _try:
                            click_log(f"{fkey} [{nm}] 좌표{j+1} 다시 눌러 창이 떴음 "
                                      f"(일치도 {_ws:.2f})")
                        # 창이 떴다 = 그 자리가 진짜였다는 증거 → 그 그림을 배워둔다
                        learn_img(fkey, j, _learn, nm)
                        learn_zone(fkey, j, coord)   # 성공한 '자리'도 모아둔다
                        break
                    _hold = RECLICK_HOLD[min(_try, len(RECLICK_HOLD) - 1)]
                    click_log(f"{fkey} [{nm}] 좌표{j+1} 눌렀는데 창이 안 뜸 "
                              f"(좌표{j+2} 최고 {_ws:.2f}) → 다시 누름 "
                              f"({_try+1}/{RECLICK_TRIES}, "
                              f"{_hold[0]:.2f}~{_hold[1]:.2f}초 꾹)")
                    self.status.set(f"🖼 [{nm}] 좌표{j+1} 창이 안 떠서 다시 누름 "
                                    f"({_try+1}/{RECLICK_TRIES})")
                    self._note(fkey, nm, f"좌표{j+1} 창이 안 떠서 다시 누름")
                    # 같은 자리를 또 눌러봐야 소용없다 — 그림이 움직였을 수 있으니
                    # **다시 찾아서** 누른다. 그림이 아예 없어졌으면 이미 눌린 것이므로
                    # 더 누르지 않고 빠진다 (2026-08-27).
                    _rx, _ry, _rs = find_image(fkey, j, coord)
                    if _rx is not None and (abs(_rx - coord[0]) > DRIFT_MAX
                                            or abs(_ry - coord[1]) > DRIFT_MAX):
                        _rx = None      # 멀리 있는 건 다른 마름모 — 그 자리를 그대로 다시
                        _rx, _ry = coord[0], coord[1]
                    if _rx is None:
                        # 그림이 사라졌다 — 그래도 **확인창을 못 봤으면 여기서 끝낸다.**
                        # 창이 안 떴는데 다음 좌표(오토 등)를 누르면 절대 안 된다
                        # (2026-08-28 사용자 지시 — 이 규칙을 어기지 말 것).
                        click_log(f"{fkey} [{nm}] 좌표{j+1} 그림이 사라졌으나 "
                                  f"확인창을 못 봄 (최고 {_rs:.2f}) → 이 슬롯 중단")
                        self._note(fkey, nm, f"좌표{j+1} 창을 못 봐서 중단")
                        break
                    if (_rx, _ry) != (coord[0], coord[1]):
                        click_log(f"{fkey} [{nm}] 좌표{j+1} 그림이 옮겨감 "
                                  f"({_rx-coord[0]:+d},{_ry-coord[1]:+d}) → 새 자리를 누름")
                    coord = (_rx, _ry)
                    try:
                        self._focus_client_at(coord)
                        time.sleep(random.uniform(0.35, 0.55))
                        move_at(*coord)
                        time.sleep(random.uniform(0.5, 0.8))
                    except Exception:
                        pass
                    click_hold(*coord, ms=random.uniform(*_hold))
                    time.sleep(random.uniform(0.35, 0.55))
                else:
                    self._note(fkey, nm, f"좌표{j+1} {RECLICK_TRIES}번 눌러도 창이 안 뜸")
                    _win_fail = True
                    try:    # 그 슬롯 화면을 통째로 남긴다 (덮어쓰지 않게 이름까지)
                        from PIL import ImageGrab as _IG
                        _bx = search_box(fkey, j, coord)
                        try:
                            import precise_click as _pc3
                            _h3 = _pc3.game_window_at(int(coord[0]), int(coord[1]))
                            _t3 = (_pc3.window_title(_h3).replace("리니지M l ", "")
                                   if _h3 else "")
                        except Exception:
                            _t3 = ""
                        _n3 = re.sub(r"[^\w가-힣]", "", _t3 or str(nm))[:10]
                        _IG.grab(bbox=_bx, all_screens=True).save(os.path.join(
                            IMG_DIR, f"_창안뜸_{fkey}_{j+1:02d}_{_n3}.png"))
                        click_log(f"{fkey} [{nm}] 좌표{j+1} 창이 끝내 안 뜸 — "
                                  f"그때 화면: click_templates/_창안뜸_{fkey}_{j+1:02d}_{_n3}.png")
                    except Exception:
                        pass
        self._user_focus_back(snap)                 # 곧바로 원래 창·커서로
        if _win_fail:
            # 확인창이 끝내 안 떴다 → **다음 좌표(오토 등)를 절대 누르지 않는다.**
            # 이 슬롯은 여기서 끝 (2026-08-28 사용자 지시).
            self.status.set(f"🖼 [{nm}] 좌표{j+1} 창이 안 떠서 이 슬롯 중단")
            return "이미지없음"
        return "클릭"

    def _pace(self, fkey, t0, left, gap, done=0):
        """목표 시간에 맞추려면 간격을 몇 배로 줄여야 하는지 (1.0 = 그대로).

        **'지금까지 클릭 하나에 실제로 몇 초 걸렸나'로 계산한다** — 간격만 보면
        그림 찾기·확인창 기다리기 같은 진짜 시간이 빠져서 페이스가 안 걸린다
        (실측: 간격은 클릭당 1.24초인데 실제는 2.29초, 2026-08-27).

        줄일 수 있는 건 '간격'뿐이므로, 초과분을 간격에서 빼는 식으로 계산한다.
        **1.0 을 넘지 않고**(늦추지 않는다) **0.30 밑으로도 안 내린다**(너무 조급하면 씹힌다)."""
        bud = RUN_BUDGET.get(fkey)
        if not bud or left <= 0:
            return 1.0
        try:
            el = time.time() - t0
            remain = bud - el
            avg = (gap[0] + gap[1]) / 2.0
            # 클릭 하나에 실제로 걸린 시간 (초반엔 표본이 없어 간격+1.0 으로 가정)
            per = (el / done) if done >= 5 else (avg + 1.0)
            need = left * per
            if need <= remain:
                return 1.0              # 여유 있음 — 원래 속도 그대로
            # 모자라는 시간을 간격에서 뺀다
            cut = need - remain
            room = left * avg           # 간격으로 줄일 수 있는 최대치
            if room <= 0.1:
                return PACE_FLOOR
            return max(PACE_FLOOR, min(1.0, 1.0 - cut / room))
        except Exception:
            return 1.0

    def _wave_tail(self, fkey, st, j0, nclk, icon, stop, name, gap, slow):
        """좌표 j0부터 그 슬롯을 '끊김 없이' 끝까지 민다 (웨이브 섞임 방지).
        이미지·확인창이 이어지는 구간에 다른 슬롯이 끼어들면 창이 닫히거나
        포커스가 바뀌어 클릭이 씹힌다 (2026-08-27 사용자 지시)."""
        slot   = st["slot"]
        coords = slot.get("coords", [])
        _anc   = slot_anchor(slot)
        done   = 0
        for j in range(j0, nclk):
            if getattr(self, stop, False):
                break
            _cd = coords[j] if (j < len(coords) and coords[j]) else None
            if _cd is None and has_img(fkey, j) and _anc:
                _cd = _anc                    # 그림만 지정한 자리
            if _cd is None:
                continue                      # 빈 자리는 통과
            if not self._wait_mouse_idle(stop, fkey=fkey):
                st["j"] = nclk
                return done
            _act = self._do_click_or_wheel(fkey, j, _cd, slot)
            done += 1
            if _act == "이미지없음":
                break                         # 이 슬롯만 끝
            self.status.set(f"{icon} [{name}] {_act}{j+1}/{nclk}  (이어서 완주)")
            _sa = stop_at(fkey)
            if _sa and (j + 1) >= _sa:
                break
            if j + 1 < nclk:
                _g = self._slot_gap(slot, j)
                _base = _g if _g is not None else random.uniform(*gap)
                _base *= getattr(self, "_pace_now", 1.0)   # 웨이브가 정한 페이스
                if fkey in EXTRA_GAPS:
                    _base += extra_gap(fkey, j)   # 기다림은 줄이지 않는다
                time.sleep(_base * random.uniform(*slow))
        st["j"] = nclk
        return done

    def _run_dgn2_wave(self, fkey, targets, nclk, icon, stop, lanes=4, gap=(2.0, 4.0),
                       slow=(1.0, 1.0), slot_gap=(0.5, 3.0), keep_order=False):
        """번갈아(웨이브) 실행 — 동시 lanes개 슬롯을 섞어가며 클릭 하나씩.
        각 좌표 사이 간격은 slot마다 따로 흐르고 gap 범위에서 랜덤."""
        _t_now = time.time()
        # 사람처럼 — 슬롯마다 **자기 속도**(tempo)를 다르게 주고, 시작도 어긋나게 한다.
        # 전부 같은 박자로 딱딱 움직이면 기계처럼 보인다 (2026-08-28 사용자 지시).
        state = {si: {"slot": sl, "j": 0,
                      "due": _t_now + (0.0 if keep_order else random.uniform(0, 6.0)),
                      "tempo": random.uniform(0.82, 1.28)}
                 for si, sl in targets}
        order = [si for si, _ in targets]
        if not keep_order:                 # 용던고고는 번호 순서대로 투입한다
            random.shuffle(order)
        active, waiting = order[:lanes], order[lanes:]
        for _k, _si in enumerate(active):      # 처음부터 나란히 출발하지 않게 흩는다
            state[_si]["due"] = _t_now + _k * random.uniform(0.7, 2.3)
        last_si, done = None, 0
        _t0 = time.time()
        _bud = RUN_BUDGET.get(fkey)
        self.status.set(f"{icon} 번갈아 실행 — 동시 {lanes}슬롯 (좌표 간격 "
                        f"{gap[0]:.0f}~{gap[1]:.0f}초"
                        + (f" · 목표 {_bud//60}분 {_bud%60}초 안에" if _bud else "") + ")")
        while not getattr(self, stop, False):
            for si in [x for x in active if state[x]["j"] >= nclk]:
                active.remove(si)
            # 끝나가는 슬롯이 있으면 **다음 슬롯을 미리 준비**해 겹쳐 들여보낸다.
            # 하나가 완전히 끝나야 다음이 들어오면 그 사이가 뚝 끊겨 기계 같다.
            _almost = sum(1 for x in active if state[x]["j"] >= nclk - EARLY_IN)
            _room = lanes + (1 if _almost else 0) - len(active)
            while waiting and _room > 0:
                nx = waiting.pop(0)
                state[nx]["due"] = (time.time() + random.uniform(*slot_gap)
                                    * random.uniform(*slow) * state[nx]["tempo"])
                active.append(nx)
                _room -= 1
            alive = [si for si in active if state[si]["j"] < nclk]
            if not alive:
                break
            now = time.time()
            ready = [si for si in alive if state[si]["due"] <= now]
            if not ready:
                nxt = min(state[si]["due"] for si in alive)
                time.sleep(max(0.05, min(nxt - now, 1.0)))
                continue
            si = random.choice(ready)
            st = state[si]
            j  = st["j"]
            coords = st["slot"].get("coords", [])
            st["j"] = j + 1
            _anc = slot_anchor(st["slot"])
            _cd = coords[j] if (j < len(coords) and coords[j]) else None
            if _cd is None and has_img(fkey, j) and _anc:
                _cd = _anc                        # 그림만 지정한 자리 — 창은 이 좌표로 찾는다
            if _cd is None:
                st["due"] = time.time()          # 빈 자리는 기다리지 않고 통과
                continue
            if si != last_si:
                time.sleep(random.uniform(0.6, 1.1))   # 다른 창으로 넘어갈 여유
                if fkey in self.FOCUS_FIRST:
                    # 비활성 창의 첫 클릭은 '창 띄우기'로만 먹히고 사라진다
                    try:
                        self._focus_client_at(coords[j])
                        time.sleep(random.uniform(0.25, 0.45))
                    except Exception:
                        pass
                last_si = si
            name = st["slot"].get("name", f"#{si+1}")
            _wu = WAVE_UNTIL.get(fkey, 0)
            if _wu and j >= _wu:
                self._pace_now = self._pace(
                    fkey, _t0,
                    sum(_left_clicks(fkey, state[x]["slot"], state[x]["j"], nclk)
                        for x in (active + waiting)), gap, done)
                # 여기서부터는 교차하지 않고 이 슬롯을 끝까지 (중간 끼어들기 방지)
                done += self._wave_tail(fkey, st, j, nclk, icon, stop,
                                        name, gap, slow)
                continue
            if not self._wait_mouse_idle(stop, fkey=fkey): return
            if getattr(self, stop, False): break
            if (fkey in self.PASTE_FKEYS
                    and j == self._paste_idx_or_default(fkey, st["slot"])
                    and (j < len(coords) and coords[j])):
                self._paste_at(coords[j], str(self.cfg.get(f"{fkey}_text", "") or ""),
                               f"[{name}]")
                _act = "붙임"
            else:
                _act = self._do_click_or_wheel(fkey, j, _cd, st["slot"])
            if _act == "이미지없음":
                st["j"] = nclk          # 이 슬롯만 끝 — 다른 슬롯은 그대로 계속
                continue
            _sa = stop_at(fkey)
            if _sa and (j + 1) >= _sa:
                st["j"] = nclk          # '여기까지만' 좌표를 마쳤다 → 이 슬롯 끝
                self.status.set(f"{icon} [{name}] 좌표{_sa}까지 끝 — 이 슬롯 종료")
                continue
            self.status.set(f"{icon} [{name}] {_act}{j+1}/{nclk}  (남은 슬롯 {len(alive)})")
            done += 1
            # 묶음 자리 — 다음 좌표를 '바로 이어서' 처리한다 (다른 슬롯이 끼어들지 못하게)
            while (j in ATOMIC_NEXT.get(fkey, ()) and j + 1 < nclk
                   and j + 1 < len(coords) and coords[j + 1]
                   and not getattr(self, stop, False)):
                time.sleep(random.uniform(0.35, 0.8))   # 올려둔 채 잠깐 뒤 바로
                _a2 = self._do_click_or_wheel(fkey, j + 1, coords[j + 1], st["slot"])
                self.status.set(f"{icon} [{name}] {_a2}{j+2}/{nclk}  (앞 좌표와 묶음)")
                done += 1
                j += 1
                st["j"] = j + 1
            _g = self._slot_gap(st["slot"], j)          # 칸에 적어둔 초가 있으면 그걸로
            _base = _g if _g is not None else random.uniform(*gap)
            # '더 쉬어야 하는 자리'(좌표2→3)는 화면이 뜨기를 기다리는 시간이라
            # **페이스로 줄이지 않는다** — 줄였더니 그림을 못 찾았다 (2026-08-27)
            _fix = extra_gap(fkey, j) if fkey in EXTRA_GAPS else 0.0
            # 목표 시간(RUN_BUDGET) 안에 끝내도록 남은 클릭 수를 보고 간격을 줄인다
            _left = sum(_left_clicks(fkey, state[x]["slot"], state[x]["j"], nclk)
                        for x in (active + waiting))
            _pc = self._pace(fkey, _t0, _left, gap, done)
            self._pace_now = _pc
            _base = _base * _pc + _fix        # 기다림(_fix)은 그대로 더한다
            # 사람처럼 — 한 슬롯에서 2~3번 이어 누르고 다른 슬롯으로 넘어간다
            if st.get("burst", 0) <= 0:
                st["burst"] = random.choice([1, 2, 2, 3])
            st["burst"] -= 1
            if st["burst"] > 0 and _g is None:
                _base = random.uniform(0.7, 1.4)        # 이어 누를 땐 짧게
            _base *= st.get("tempo", 1.0)          # 슬롯마다 자기 속도
            if random.random() < 0.10:             # 가끔 한 번씩 더 쉰다 (사람처럼)
                _base += random.uniform(0.5, 1.6)
            st["due"] = time.time() + _base * random.uniform(*slow)   # 10~20% 할증
            time.sleep(random.uniform(0.35, 0.7))      # 클릭끼리 최소 간격
        _el = int(time.time() - _t0)
        _bud2 = RUN_BUDGET.get(fkey)
        self.status.set(f"{icon} 번갈아 실행 완료 — 클릭 {done}회, "
                        f"{_el//60}분 {_el%60}초 걸림"
                        + (f" (목표 {_bud2//60}분 {_bud2%60}초)" if _bud2 else ""))
        if _bud2:
            click_log(f"[시간] {fkey} {_el}초 / 목표 {_bud2}초 "
                      + ("✔ 안에 끝남" if _el <= _bud2 else f"⚠ {_el-_bud2}초 초과"))
        if fkey in self.LOG_FKEYS:
            try:      # 슬롯별로 끝까지 갔는지 남긴다 (누락 확인용)
                short = [f"#{si+1:02d} {state[si]['j']}/{nclk}"
                         for si, _s in targets if state[si]["j"] < nclk]
                click_log(f"[웨이브끝] {fkey} {len(targets)}슬롯 · 클릭 {done}회 · "
                          + (f"⚠ 덜 돈 슬롯: {', '.join(short)}" if short
                             else "전 슬롯 끝까지 완료"))
                if short:
                    self.status.set(f"{icon} 완료 — ⚠ 덜 돈 슬롯 {len(short)}개 "
                                    f"(클릭기록 확인)")
            except Exception:
                pass

    def _run_dgn2(self, fkey, slot_idx=None, sel_list=None):
        self._start_pause()
        self._img_done = set()      # 실행할 때마다 '이미지 찾음' 표시를 비운다
        self._run_note = []         # 이번 실행에서 잘 안 된 것 (끝나고 요약)
        self._pace_now = 1.0        # 목표 시간에 맞추는 간격 배수 (1.0 = 그대로)
        key, title, icon = self._dgn2_info(fkey)
        nclk = self._grid_spec(fkey)["clicks"]
        stop = f"_{fkey}_stop"
        try:
            slots = self.cfg.get(key, [])
            if fkey in self.PASTE_FKEYS:
                txt = str(self.cfg.get(f"{fkey}_text", "") or "")
                if not txt.strip():
                    self.status.set(f"{icon} {title}: 붙여넣을 글이 비어 있습니다 — 창에서 글을 먼저 적어주세요")
                    return
                self._set_clipboard_text(txt)
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                _pick = sel_list if sel_list else range(len(slots))
                _en = self._grid_spec(fkey).get("enable")
                targets = [(i, slots[i]) for i in _pick
                           if i < len(slots) and any(slots[i].get("coords", []))
                           and (not _en or slots[i].get("enabled", True))]
                # 용던고고·매일매일 스케줄은 **1번부터 번호 순서대로** 돈다
                # (2026-08-28 사용자 지시 — 스케줄도 섞지 않는다)
                if fkey not in KEEP_ORDER_FKEYS:
                    random.shuffle(targets)   # 그 밖의 런처는 슬롯 순서 랜덤
            if fkey == "circus" and slot_idx is None and len(targets) > 1:
                # 서커스 이벤트등록: 동시 2슬롯, 간격·슬롯투입 모두 10~20% 할증
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=2,
                                    slow=(1.10, 1.20), slot_gap=(3.0, 5.0))
                return
            if fkey == "market" and slot_idx is None and len(targets) > 1:
                # 거래소검색: 동시 2슬롯 번갈아 (간격은 칸에 적어둔 값 우선)
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=2,
                                    gap=(2.0, 4.0), slot_gap=(3.0, 5.0))
                return
            if fkey == "circus3" and slot_idx is None and len(targets) > 1:
                # 서커스 이벤트퀘스트: 서커스와 같은 시간 + 10~20% 할증
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=2,
                                    gap=(2.0, 4.0), slow=(1.10, 1.20), slot_gap=(3.0, 5.0))
                return
            if fkey == "circus2" and slot_idx is None and len(targets) > 1:
                # 서커스 이벤트실행: 동시 2슬롯, 좌표 2~4초 / 슬롯 3~5초 랜덤
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=2,
                                    gap=(2.0, 4.0), slot_gap=(3.0, 5.0))
                return
            if fkey in ("fish",) and slot_idx is None and len(targets) > 1:
                # 낚시녹임은 번갈아(웨이브) 실행 — 동시 4슬롯, 좌표 간격 2~4초 랜덤
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop)
                return
            if fkey == "knight" and slot_idx is None and len(targets) > 1:
                # 흑기사 — 2슬롯씩 번갈아(웨이브), 슬롯 순서는 랜덤.
                # 좌표 간격은 정해둔 범위에서 랜덤, 좌표2→3만 더 쉰다.
                _cl = sum(1 for _si, _sl in targets
                          for _c in (_sl.get("coords") or [])[:nclk] if _c)
                _avg = (KNIGHT_GAP_MIN + KNIGHT_GAP_MAX) / 2 + 0.15
                _ex = sum((sum(v) / 2 if isinstance(v, (tuple, list)) else v)
                          for v in KNIGHT_EXTRA.values())
                _per = _cl / max(len(targets), 1)
                _est = int(len(targets) / 2 * (_per * _avg + _ex + 1.75))
                self.status.set(f"🖤 던전끝! 흑기사!! — {len(targets)}슬롯 / 클릭 {_cl}회, "
                                f"2슬롯 번갈아 (간격 {KNIGHT_GAP_MIN:.1f}~{KNIGHT_GAP_MAX:.1f}초, "
                                f"좌표2→3은 +{KNIGHT_EXTRA[1][0]:.1f}~{KNIGHT_EXTRA[1][1]:.1f}초, "
                                f"약 {_est//60}분 {_est%60}초 예상)")
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=2,
                                    gap=(KNIGHT_GAP_MIN, KNIGHT_GAP_MAX),
                                    slot_gap=(1.0, 2.5))
                return
            if fkey == "dragon" and slot_idx is None and len(targets) > 1:
                # 용던고고 — 2슬롯씩 번갈아(웨이브), 슬롯 순서는 번호대로.
                # 시간을 억지로 맞추지 않는다 — 정해둔 범위에서 랜덤으로 쉬고,
                # 좌표는 하나도 빠짐없이 다 누른다. 슬롯이 적으면 그만큼 빨리 끝난다.
                _cl = sum(1 for _si, _sl in targets
                          for _c in (_sl.get("coords") or [])[:nclk] if _c)
                _avg = (DRAGON_GAP_MIN + DRAGON_GAP_MAX) / 2 + 0.15
                _ex = sum((sum(v) / 2 if isinstance(v, (tuple, list)) else v)
                          for v in DRAGON_EXTRA.values())      # 2→3 같은 추가 대기
                _est = int(len(targets) / 3 * (nclk * _avg + _ex + 1.15))
                self.status.set(f"🐲 용던고고!!! — {len(targets)}슬롯 / 클릭 {_cl}회, "
                                f"좌표1~3만 3슬롯 번갈아 · 좌표4부터 슬롯 완주 "
                                f"(간격 {DRAGON_GAP_MIN:.1f}~{DRAGON_GAP_MAX:.1f}초, "
                                f"좌표2→3은 +{DRAGON_EXTRA[1][0]:.1f}~{DRAGON_EXTRA[1][1]:.1f}초, "
                                f"약 {_est//60}분 {_est%60}초 예상)")
                # 동시 3슬롯 · 슬롯 간격 1~2초 랜덤 (2026-08-28 사용자 지시)
                self._run_dgn2_wave(fkey, targets, nclk, icon, stop, lanes=3,
                                    gap=(DRAGON_GAP_MIN, DRAGON_GAP_MAX),
                                    slot_gap=(1.0, 2.0), keep_order=True)
                return
            if fkey in ("dragon", "knight"):
                # F11(절전해제)이 끝난 시각부터 정해둔 시간 안에 전부 끝낸다.
                # 남은 시간 ÷ 남은 클릭 수로 간격을 매번 다시 계산해 스스로 맞춘다.
                _left = sum(1 for _si, _sl in targets
                            for _c in (_sl.get("coords") or [])[:nclk] if _c)
                _tt = "🖤 던전끝! 흑기사!!" if fkey == "knight" else "🐲 용던고고!!!"
                _mn, _mx = ((KNIGHT_GAP_MIN, KNIGHT_GAP_MAX) if fkey == "knight"
                            else (DRAGON_GAP_MIN, DRAGON_GAP_MAX))
                self.status.set(f"{_tt} — {len(targets)}슬롯 / 클릭 {_left}회, "
                                f"한 슬롯씩 차례로 (간격 {_mn:.1f}~{_mx:.1f}초)")
            for tn, (si, slot) in enumerate(targets):
                if getattr(self, stop, False): break
                name = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [])
                while len(coords) < nclk:
                    coords.append(None)
                if not self._wait_mouse_idle(stop, fkey=fkey): return
                # 쿠폰: 슬롯마다 클릭 간격 배수를 새로 뽑음 (기본의 -5%~+20%)
                c_mult = random.uniform(0.95, 1.20) if fkey in self.PASTE_FKEYS else 1.0
                # 클릭1~N을 순서대로, 클릭 사이 간격만 랜덤
                # 좌표가 없어도 '그림'을 지정해뒀으면 그 자리도 실행한다 (2026-08-27)
                _anchor = slot_anchor(slot)
                order = [j for j in range(nclk)
                         if coords[j] or (has_img(fkey, j) and _anchor)]
                # 쿠폰: 클릭5(입력칸)가 등록돼 있으면 그 직후, 없으면 클릭4 직후에 붙여넣기
                paste_after = (self._paste_idx_or_default(fkey, slot)
                               if fkey in self.PASTE_FKEYS else None)
                if fkey == "coupon":
                    self._coupon_log(f"슬롯 [{name}] 시작 — 등록클릭 {[x+1 for x in order]}, 붙여넣기는 클릭{(paste_after or 0)+1} 직후")
                for n, j in enumerate(order):
                    if getattr(self, stop, False):
                        if fkey == "coupon": self._coupon_log(f"멈춤 플래그로 중단 (클릭{j+1} 직전)")
                        break
                    if fkey in self.PASTE_FKEYS and j == paste_after and coords[j]:
                        self._paste_at(coords[j], txt, f"[{name}]")
                        self.status.set(f"{icon} [{name}] 붙여넣기 완료 (클릭{j+1} 다음)")
                    else:
                        _act = self._do_click_or_wheel(
                            fkey, j, coords[j] or _anchor, slot)
                        if _act == "이미지없음":
                            break        # 이 슬롯만 끝 — 다음 슬롯으로 넘어간다
                    _sa = stop_at(fkey)
                    if _sa and (j + 1) >= _sa:
                        # '여기까지만' 으로 정해둔 좌표를 마쳤다 → 이 슬롯 끝
                        # (뒤 좌표가 같은 아이콘을 또 눌러 되돌아가는 것 방지)
                        self.status.set(f"{icon} [{name}] 좌표{_sa}까지 끝 — 이 슬롯 종료")
                        break
                        self.status.set(f"{icon} [{name}] {_act}{j+1}...")
                        if fkey == "coupon":
                            self._coupon_log(f"클릭{j+1} 완료 {tuple(coords[j])}")
                    if fkey == "fix":
                        # 🩹 복구는 **빠르게** — 사용자가 손으로 3초 안에 끝내는 작업이라
                        # 느리면 쓸모가 없다 (2026-08-29 사용자 지시)
                        self._wait_gap(stop, name, j,
                                       random.uniform(FIX_GAP_MIN, FIX_GAP_MAX))
                    elif fkey in ("dragon", "knight"):
                        # 정해둔 범위에서 랜덤 (좌표2→3은 더 쉬어준다)
                        _left -= 1
                        _mn, _mx = ((KNIGHT_GAP_MIN, KNIGHT_GAP_MAX) if fkey == "knight"
                                    else (DRAGON_GAP_MIN, DRAGON_GAP_MAX))
                        self._wait_gap(stop, name, j,
                                       random.uniform(_mn, _mx) + extra_gap(fkey, j))
                    if n < len(order) - 1:
                        if fkey == "eventshop" and j == 0:
                            # 이벤트상점: 클릭1 → 4초 × 1.15~1.30 랜덤 증가 후 클릭2
                            time.sleep(4.0 * random.uniform(1.15, 1.30))
                        elif fkey in ("dragon", "knight", "fix"):
                            pass                 # 위에서 이미 쉬었다
                        else:
                            _cg = self._slot_gap(slot, j)    # 칸에 적어둔 초가 있으면 그걸로
                            if _cg is not None:
                                time.sleep(_cg * random.uniform(1.0, 1.10))
                            else:
                                gap = random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX)
                                if fkey == "eventshop":
                                    gap *= random.uniform(1.15, 1.25)   # 좌표별 15~25% 추가 증가
                                time.sleep(gap * c_mult)
                if fkey in self.PASTE_FKEYS:
                    self._coupon_log(f"[{fkey}] 슬롯 [{name}] 끝 (클릭간격 배수 {c_mult:.2f})")
                    # 슬롯 간 간격 — 기본 3초의 +2%~18% 랜덤 (마지막 슬롯 뒤엔 생략)
                    if slot_idx is None and tn < len(targets) - 1:
                        g = COUPON_SLOT_GAP * random.uniform(1.02, 1.18)
                        self._coupon_log(f"슬롯 간격 {g:.2f}초 대기")
                        time.sleep(g)
            if fkey == "dragon":
                _el = int(time.time() - (getattr(self, "_dragon_deadline", 0) - DRAGON_BUDGET))
                self.status.set(f"✔ {title} 완료 — {_el//60}분 {_el%60}초 걸림 "
                                f"(목표 {DRAGON_BUDGET//60}분 {DRAGON_BUDGET%60}초)")
            else:
                self.status.set(f"✔ {title} 실행 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self._set_btn(f"btn_{fkey}_run", state="normal")
            self._set_btn(f"btn_{fkey}_stop", state="disabled")
            self.after(0, lambda f=fkey, t=title: self._run_summary(f, t))
            self.after(0, self._restore_back)

    def _build_past(self, parent):
        tk.Label(parent, text=f"과거의말하는섬  (3번 클릭 / {PAST_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#c0392b").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._past_stop = False
        self.btn_past_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=13, height=2,
            command=self._start_past)
        self.btn_past_run.pack(side="left", padx=(0,3))
        self.btn_past_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_past_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_past_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#922b21", fg="white", width=18,
            command=self._group_copy_past).pack(side="left", padx=(8,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "past")   # 4×4 그리드 (화면 배치와 동일)

    def deiconify(self):
        if getattr(self, "_running", False):
            return  # 자동실행 중에는 복원 차단
        super().deiconify()

    def _restart_launcher(self):
        """[🔄 런처재시작] — 런처를 확실히 껐다가 다시 켠다.
        (버튼 위치가 틀어지거나 반응이 이상할 때 한 번 눌러 초기화)"""
        self.status.set("🔄 런처를 다시 시작합니다...")
        try:
            import sys          # 이 파일은 sys 를 전역으로 import 하지 않는다
            pyw = sys.executable
            if pyw.lower().endswith("python.exe"):
                pyw = pyw[:-10] + "pythonw.exe"
            me = os.path.join(BASE, "lineagem_launcher.py")
            # 이 프로세스가 죽은 뒤 확실히 다시 띄운다 —
            # 20초 동안 지켜보며 안 떠 있으면 직접 실행 (워치독 실패해도 살아남)
            ps = ("Start-Sleep -Milliseconds 1200; "
                  "schtasks /Run /TN 'LineageM_Watchdog' | Out-Null; "
                  "for ($i=0; $i -lt 20; $i++) { "
                  "  Start-Sleep -Seconds 1; "
                  "  $p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                  "       Where-Object { $_.CommandLine -like '*lineagem_launcher*' }; "
                  "  if ($p) { break } "
                  "}; "
                  "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                  "     Where-Object { $_.CommandLine -like '*lineagem_launcher*' }; "
                  f"if (-not $p) {{ Start-Process -FilePath '{pyw}' -ArgumentList '{me}' }}")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                              "-Command", ps], creationflags=0x08000000)
        except Exception as e:
            self.status.set(f"재시작 준비 실패: {e}")
            return

        def _bye():
            try:
                self.destroy()
            except Exception:
                pass
            os._exit(0)          # tkinter 정리에서 막히지 않게 확실히 종료
        self.after(600, _bye)

    def _raise_claude(self):
        import win32gui, win32con
        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return True
            title = win32gui.GetWindowText(hwnd)
            if "claude" in title.lower():
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                # 잠깐 맨 위로 올렸다가 곧바로 '항상 위'를 푼다 —
                # 계속 TOPMOST로 두면 메인런처가 그 위로 올라올 수 없다 (2026-08-13)
                _f = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, _f)
                win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, _f)
                win32gui.SetForegroundWindow(hwnd)
            return True
        win32gui.EnumWindows(_cb, None)

    def _clear_accounts(self):
        from tkinter import messagebox
        if not messagebox.askyesno("초기화", "계정 정보를 전체 초기화하시겠습니까?", default="no"):
            return
        for i in range(16):
            self._acc_type_vars[i].set("구글")
            for j in range(5):
                self._acc_vars[i][j].set("")
        save_accounts([{"type": "구글", "f1": "", "f2": "", "f3": "", "f4": "", "f5": ""} for _ in range(20)])
        self.status.set("✔ 계정 정보 초기화 완료")

    def _save_accounts(self):
        for i in range(20):
            self._accounts[i]["type"] = self._acc_type_vars[i].get()
            for j in range(5):
                self._accounts[i][f"f{j+1}"] = self._acc_vars[i][j].get()
        save_accounts(self._accounts)
        self.status.set("✔ 계정 정보 저장 완료")

    def _schedule_acc_autosave(self):
        """계정 칸 수정 시 자동저장 예약 (0.8초 디바운스 — 저장 버튼 안 눌러도 안 날아감)."""
        job = getattr(self, "_acc_save_job", None)
        if job:
            try: self.after_cancel(job)
            except Exception: pass
        self._acc_save_job = self.after(800, self._autosave_accounts)

    def _autosave_accounts(self):
        self._acc_save_job = None
        try:
            for i in range(20):
                self._accounts[i]["type"] = self._acc_type_vars[i].get()
                for j in range(5):
                    self._accounts[i][f"f{j+1}"] = self._acc_vars[i][j].get()
            save_accounts(self._accounts)
            self.status.set("💾 계정 자동저장됨")
        except Exception:
            pass

    # ── ⚠ 경고 확인 (F11 때 지정 영역을 보고 '떠 있으면' 경고를 남긴다) ──────
    @staticmethod
    def _warn_dir():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return d

    def _warn_load(self):
        try:
            with open(os.path.join(self._warn_dir(), "warns.json"), encoding="utf-8") as f:
                return sorted({int(x) for x in (json.load(f) or {}).get("slots", [])})
        except Exception:
            return []

    def _warn_save(self, slots):
        try:
            with open(os.path.join(self._warn_dir(), "warns.json"), "w", encoding="utf-8") as f:
                json.dump({"slots": sorted(set(int(x) for x in slots))}, f)
        except Exception:
            pass

    def _warn_add(self, slots):
        cur = set(self._warn_load()) | set(slots)
        self._warn_save(cur)
        self._warn_refresh()

    def _warn_remove(self, slot):
        """경고 ✕ — 지우기만 하고 런처를 앞으로 올리지 않는다 (맨 뒤 유지)."""
        cur = set(self._warn_load()) - {int(slot)}
        self._warn_save(cur)
        self._warn_refresh()
        # 클릭 때문에 창이 앞으로 나오지 않게 잠깐 '조용히' 상태로 두고 맨 뒤 유지
        self._quiet_restore = True
        try:
            self._send_to_back()
        except Exception:
            pass
        self.after(800, lambda: setattr(self, "_quiet_restore", False))

    def _fix_paid_path(self):
        """'이 슬롯은 다야(재화)를 써야 복구된다' 표시 — 이 컴퓨터에만 저장."""
        return os.path.join(LOCAL_DATA, "fix_paid.json")

    def _fix_paid_load(self):
        try:
            with open(self._fix_paid_path(), encoding="utf-8") as f:
                return set(int(x) for x in (json.load(f) or {}).get("slots") or [])
        except Exception:
            return set()

    def _fix_paid_save(self, sl):
        try:
            os.makedirs(LOCAL_DATA, exist_ok=True)
            with open(self._fix_paid_path(), "w", encoding="utf-8") as f:
                json.dump({"slots": sorted(int(x) for x in sl)}, f)
        except Exception:
            pass

    def _fix_paid_mark(self, si, on=True):
        """다야를 써야 하는 슬롯으로 표시(초록)하거나 해제한다."""
        cur = self._fix_paid_load()
        cur.add(int(si)) if on else cur.discard(int(si))
        self._fix_paid_save(cur)
        self._warn_refresh()

    def _warn_refresh(self):
        box = getattr(self, "_warn_rows", None)
        if not box or not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        slots = self._warn_load()
        _paidset = self._fix_paid_load() & set(slots)   # 목록에 없는 표시는 버린다
        if _paidset != self._fix_paid_load():
            self._fix_paid_save(_paidset)
        hdr = getattr(self, "_warn_hdr", None)   # 개수 표시는 쓰지 않는다 (사용자 지시)
        if hdr and hdr.winfo_exists():
            hdr.pack_forget()
        for si in slots:
            row = tk.Frame(box); row.pack(fill="x", pady=1)
            # 누르면 그 슬롯만 복구를 돌린다 (2026-08-29 사용자 요청).
            # 좌표4 의 '무료' 확인을 통과할 때만 진행되므로 재화는 쓰이지 않는다.
            # 다야(재화)를 써야 하는 슬롯은 **초록** — 무료로 안 되는 것을 한눈에
            # (2026-08-29 사용자 요청). 무료로 되는 것은 빨강 그대로.
            _paid = si in _paidset
            tk.Button(row,
                      text=(f"💎 다야!! {si:02d}" if _paid
                            else f"복구해야함 {si:02d} ▶"),
                      font=("맑은 고딕", 11 if _paid else 9, "bold"),
                      fg=("#fff9c4" if _paid else "white"),      # 초록 위 노란 글씨 = 잘 보임
                      bg=("#1e8449" if _paid else "#c0392b"),
                      activebackground=("#186a3b" if _paid else "#922b21"),
                      width=(11 if _paid else 13), anchor="w", padx=3, pady=0,
                      cursor="hand2",
                      command=lambda x=si: self._run_fix_slot(x)).pack(side="left")
            tk.Button(row, text="✕", font=("맑은 고딕", 8, "bold"), width=2, pady=0,
                      bg="#7f8c8d", fg="white",
                      command=lambda x=si: self._warn_remove(x)).pack(side="left", padx=(2, 0))

    def _run_fix_slot(self, si):
        """'복구해야함 03' 을 누르면 **그 슬롯만** 복구를 돌린다 (2026-08-29 사용자 요청).

        좌표4 의 👁 '무료' 확인을 통과할 때만 뒤 좌표를 누르므로,
        재화가 드는 상태면 그 자리에서 멈춘다 — 눌러도 안전하다."""
        idx = int(si) - 1
        try:
            slots = self.cfg.get("fix_slots") or []
            if idx < 0 or idx >= len(slots) or not any(slots[idx].get("coords") or []):
                self.status.set(f"🩹 복구 #{si:02d} — 좌표가 등록돼 있지 않습니다. "
                                f"[🩹복구] 창에서 먼저 좌표를 넣어주세요")
                return
        except Exception:
            pass
        # ── 누르기 전에 **십자가가 아직 있는지** 확인한다 (2026-08-29 사용자 지시) ──
        # 없으면 이미 복구된 것이므로 **아무것도 누르지 않고** 목록에서 지운다.
        # (예전엔 십자가가 없는데도 좌표1부터 눌러 엉뚱한 곳을 찍었다)
        try:
            hit = self._check_hits()
            if hit is not None and int(si) not in set(hit):
                self._fix_paid_mark(int(si), False)
                self._warn_remove(int(si))
                click_log(f"fix #{si:02d} 십자가가 없어 실행 취소 — 이미 복구된 것으로 보고 지움")
                self.status.set(f"✖ 복구 #{si:02d} — 십자가가 없어 실행하지 않았습니다 "
                                f"(이미 복구됨 · 목록에서 지웠습니다)")
                return
        except Exception:
            pass
        self.status.set(f"🩹 복구 #{si:02d} 실행 — '무료'가 아니면 그 자리에서 멈춥니다")
        self._start_dgn2("fix", sel_list=[idx])
        # 끝난 뒤 **화면을 다시 봐서** 경고가 사라졌는지 확인하고 지운다
        self.after(3000, lambda x=si: self._fix_verify(x, 12))

    def _fix_verify(self, si, tries):
        """복구를 돌린 뒤 **정말 없어졌는지 화면으로 확인**하고 목록에서 지운다.

        경고영역(`check_area_rel`)을 다시 훑어 그 슬롯의 마크가 사라졌으면 자동 삭제.
        **화면으로 확인될 때만 지운다** — 실행했다는 이유만으로 지우지 않는다
        (2026-08-29 사용자 요청)."""
        try:
            if tries <= 0:
                self.status.set(f"🩹 복구 #{si:02d} — 아직 경고가 남아 있습니다 "
                                f"(재화가 들어서 멈췄거나 실패). 목록은 그대로 둡니다")
                return
            if self._is_busy():                       # 아직 돌고 있으면 기다린다
                self.after(2000, lambda: self._fix_verify(si, tries)); return
            hit = self._check_hits()
            if hit is None:                           # 경고영역 미지정 등 — 확인 불가
                self.status.set(f"🩹 복구 #{si:02d} 끝 — 경고영역이 없어 자동 확인은 못 합니다 "
                                f"([🔆 절전해제] → [📷 경고영역 지정])")
                return
            if int(si) not in set(hit):
                self._fix_paid_mark(int(si), False)     # 무료로 됐으니 표시 해제
                self._warn_remove(int(si))
                click_log(f"fix #{si:02d} 복구 확인됨 — 화면에서 경고가 사라져 목록에서 지움")
                self.status.set(f"✅ 복구 #{si:02d} 확인 — 경고가 사라져 목록에서 지웠습니다")
                return
            # 아직 남아 있다 — '무료' 확인에서 멈춘 것이면 **다야를 써야 하는 슬롯**이다
            try:
                _nt = getattr(self, "_run_note", None) or []
                if any("👁 확인" in m for _n, m in _nt):
                    self._fix_paid_mark(int(si), True)
                    click_log(f"fix #{si:02d} '무료'가 아니라 취소 — 다야 필요로 표시(초록)")
                    self.status.set(f"💎 복구 #{si:02d} — 무료가 아니라 취소했습니다. "
                                    f"다야를 써야 하는 슬롯으로 초록 표시했습니다")
                    return
            except Exception:
                pass
            self.after(2000, lambda: self._fix_verify(si, tries - 1))
        except Exception as e:
            self.status.set(f"🩹 복구 #{si:02d} 확인 실패: {e}")

    @staticmethod
    def _rect_owner(rects, x, y):
        """드래그한 지점이 몇 번 클라 안인지 찾는다 (없으면 0번).
        (2026-08-10) 예전엔 무조건 01번 기준으로 계산해서, 다른 클라에서 드래그하면
        영역이 화면 밖으로 나가 전부 오판정됐다."""
        for i, (l, t, r, b) in enumerate(rects):
            if l <= x <= r and t <= y <= b:
                return i
        return 0

    def _reg_check_area(self):
        """경고가 '떠 있는 상태'의 01번 클라 화면에서 그 자리를 드래그해 등록."""
        rects = self._client_rects_by_slot()
        if not rects:
            self.status.set("⚠ 리니지M 클라이언트 16개가 보이지 않습니다"); return
        self._check_rects = rects
        w = getattr(self, "_seq_win", None)
        if w and w.winfo_exists():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(200, lambda: _PotionAreaOverlay(self, self._on_check_area))

    def _on_check_area(self, x, y, w, h):
        self.deiconify()
        sw = getattr(self, "_seq_win", None)
        if sw and sw.winfo_exists():
            try: sw.deiconify(); sw.lift()
            except Exception: pass
        if w < 5 or h < 5:
            self.status.set("영역이 너무 작습니다 — 다시 드래그해주세요"); return
        rects = getattr(self, "_check_rects", None) or self._client_rects_by_slot()
        hw = self._client_hwnds_by_slot()
        if not rects or not hw:
            self.status.set("⚠ 클라이언트 16개 감지 실패"); return
        oi = self._rect_owner(rects, x, y)      # 어느 클라에서 찍었는지 자동 인식
        base = rects[oi]
        rel = [x - base[0], y - base[1], w, h]
        self.cfg["check_area_rel"] = rel
        save_cfg(self.cfg)
        try:      # 지금 화면(=경고가 떠 있는 상태)을 '기준 그림'으로 저장
            l, t, r, b, hwnd = hw[oi]
            im = self._grab_client(hwnd, r - l, b - t).crop(
                (rel[0], rel[1], rel[0] + w, rel[1] + h))
            im.save(os.path.join(self._warn_dir(), "check_ref.png"))
            self.status.set(f"✔ 경고영역 등록 — #{oi+1:02d} 클라 기준 "
                            f"({rel[0]},{rel[1]}) {w}x{h} (지금 화면을 기준으로 저장)")
        except Exception as e:
            self.status.set(f"⚠ 기준 그림 저장 실패: {e}")

    @staticmethod
    def _img_match(im, ref):
        """넓게 잘라온 그림(im) 안에서 기준 그림(ref)을 찾은 최고 점수(0~1).
        클라마다 표시 위치가 몇 픽셀 다르기 때문에 '그 안에서 찾기'로 해야 잡힌다."""
        try:
            import cv2, numpy as np
            a = np.asarray(im, dtype="uint8")
            b = np.asarray(ref, dtype="uint8")
            if a.shape[0] < b.shape[0] or a.shape[1] < b.shape[1]:
                a = cv2.resize(a, (max(a.shape[1], b.shape[1]), max(a.shape[0], b.shape[0])))
            return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED).max())
        except Exception:
            return 0.0

    def _check_hits(self):
        """지금 그 영역에 '기준 그림'이 보이는 슬롯 번호들 (없으면 None = 확인 불가)."""
        rel = self.cfg.get("check_area_rel")
        ref_p = os.path.join(self._warn_dir(), "check_ref.png")
        if not os.path.exists(ref_p):
            # 기준 그림이 없으면 저장소·런처 폴더에서 찾아 가져온다 (2026-08-29).
            # 업데이트가 이 파일을 %LOCALAPPDATA% 로 옮기는데, 그 기능이 들어간
            # 판을 받기 전에는 비어 있어서 '십자가가 떠 있는데 인식 못 함'이 났다.
            for _c in (os.path.join(BASE, "check_ref.png"),
                       os.path.join(find_repo_dir() or "", "check_ref.png")):
                try:
                    if _c and os.path.exists(_c):
                        import shutil as _sh
                        _sh.copy2(_c, ref_p)
                        click_log(f"[경고확인] 기준 그림을 {_c} 에서 가져왔습니다")
                        break
                except Exception:
                    pass
        if not rel or not os.path.exists(ref_p):
            return None
        hw = self._client_hwnds_by_slot()
        if not hw:
            return None
        try:
            from PIL import Image
            ref = Image.open(ref_p).convert("L")
        except Exception:
            return None
        dx, dy, w, h = rel
        M = 20        # 클라마다 몇 픽셀씩 어긋나므로 주변까지 넓게 훑는다
        hit = []
        for i, (l, t, r, b, hwnd) in enumerate(hw):
            try:
                W, H = r - l, b - t
                x0, y0 = max(0, dx - M), max(0, dy - M)
                x1, y1 = min(W, dx + w + M), min(H, dy + h + M)
                im = self._grab_client(hwnd, W, H).crop((x0, y0, x1, y1)).convert("L")
                if self._img_match(im, ref) >= 0.60:   # 기준 그림이 그 안에 있다 = 떠 있다
                    hit.append(i + 1)
            except Exception:
                pass
        return hit

    def _check_scan(self, quiet=False):
        """지정 영역에 마크가 보이면 경고를 남기고, 이후 5분간 지켜본다 (F11 때 자동).
        지켜보는 동안 마크가 사라진 슬롯은 경고를 자동으로 지운다 —
        내가 ✕로 지우는 것도 그대로 쓸 수 있다."""
        hit = self._check_hits()
        if hit is None:
            if not quiet:
                _rp = os.path.join(self._warn_dir(), "check_ref.png")
                _why = []
                if not self.cfg.get("check_area_rel"):
                    _why.append("경고영역(check_area_rel) 없음")
                if not os.path.exists(_rp):
                    _why.append("십자가 기준 그림(check_ref.png) 없음")
                if not self._client_hwnds_by_slot():
                    _why.append("리니지M 클라 16개가 안 보임")
                self.status.set("⚠ 경고 확인 불가 — " + (" · ".join(_why) or "원인 불명")
                                + " · [🔆 절전해제] 창에서 [📷 경고영역 지정]을 해주세요")
            return
        # 마크가 있는 곳은 그대로 두고, 사라진 곳은 자동으로 지운다
        # (내가 ✕ 로 지우지 않아도 다음 F11 때 알아서 정리됨)
        before = set(self._warn_load())
        gone = sorted(before - set(hit))
        self._warn_save(hit)
        self._warn_refresh()
        _msg = f"⚠ 경고 확인 — 뜬 곳 {len(hit)}개 {hit or ''}"
        if gone:
            _msg += f" · 사라진 {gone} 자동 삭제"
        self.status.set(_msg + " · 5분간 지켜봅니다")
        self._check_watch_start()

    def _check_watch_start(self, minutes=5):
        """5분 동안 15초마다 다시 봐서, 마크가 사라진 슬롯의 경고를 지운다."""
        self._check_watch_until = time.time() + minutes * 60
        if getattr(self, "_check_watch_on", False):
            return                     # 이미 지켜보는 중이면 시간만 연장
        self._check_watch_on = True
        self.after(15000, self._check_watch_tick)

    def _check_watch_tick(self):
        """15초마다 다시 봐서 목록을 화면과 맞춘다.
        · 마크가 사라진 슬롯 → 경고 삭제
        · 새로 뜬 슬롯      → 경고 추가 (F11 직후엔 없다가 뒤늦게 뜨는 것도 잡는다)"""
        try:
            if time.time() > getattr(self, "_check_watch_until", 0):
                self._check_watch_on = False
                self.status.set("⚠ 5분 확인 끝 — 남은 경고 "
                                f"{len(self._warn_load())}개")
                return
            now_hit = self._check_hits()
            if now_hit is not None:
                before = set(self._warn_load())
                gone = sorted(before - set(now_hit))
                new_ = sorted(set(now_hit) - before)
                if gone or new_:
                    self._warn_save(now_hit)
                    self._warn_refresh()
                    msg = []
                    if new_:
                        msg.append(f"새로 뜸 {new_}")
                    if gone:
                        msg.append(f"복구됨 {gone} 삭제")
                    self.status.set("⚠ 확인 중 — " + " · ".join(msg) +
                                    f" (남은 경고 {len(now_hit)}개)")
        except Exception:
            pass
        self.after(15000, self._check_watch_tick)

    # ── 🧪 물약색 확인 — 16개 클라의 같은 자리 색을 한 번에 보고 빨강/주황 판정 ──
    def _open_potion_win(self):
        self._open_section_win("_potion_win", "🧪 물약색 확인",
                               self._build_potion, w=470, h=430, pinnable=True)

    def _build_potion(self, parent):
        tk.Label(parent, text="🧪 물약색 확인  (16개 클라를 한 번에)",
                 font=("맑은 고딕", 10, "bold"), fg="#6c3483").pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(parent, text="① [영역 지정]으로 01번 클라의 물약 자리를 드래그해서 한 번만 등록\n"
                              "② [확인]을 누르면 16개 클라의 같은 자리 색을 읽어 빨강/주황을 알려줍니다",
                 font=("맑은 고딕", 8), fg="#555", justify="left").pack(anchor="w", padx=6)
        row = tk.Frame(parent); row.pack(fill="x", padx=6, pady=6)
        tk.Button(row, text="📷 영역 지정 (01번 기준)", font=("맑은 고딕", 9, "bold"),
                  bg="#8e44ad", fg="white", command=self._reg_potion_area).pack(side="left")
        tk.Button(row, text="🔍 확인", font=("맑은 고딕", 9, "bold"),
                  bg="#6c3483", fg="white", width=8,
                  command=self._potion_check).pack(side="left", padx=(6, 0))
        self._potion_area_lbl = tk.Label(parent, text="", font=("맑은 고딕", 8), fg="#888")
        self._potion_area_lbl.pack(anchor="w", padx=6)
        self._refresh_potion_area_lbl()

        grid = tk.Frame(parent); grid.pack(padx=6, pady=6)
        self._potion_cells = []
        for i in range(16):
            r, c = i % 4, i // 4
            cell = tk.Frame(grid, bd=1, relief="groove", padx=4, pady=3, width=96)
            cell.grid(row=r, column=c, padx=4, pady=4, sticky="we")
            tk.Label(cell, text=f"{i+1:02d}", font=("맑은 고딕", 8, "bold"), fg="#555").pack()
            lb = tk.Label(cell, text="—", font=("맑은 고딕", 12, "bold"),
                          fg="white", bg="#bdc3c7", width=6)
            lb.pack()
            self._potion_cells.append(lb)

    def _refresh_potion_area_lbl(self):
        lb = getattr(self, "_potion_area_lbl", None)
        if not lb or not lb.winfo_exists():
            return
        a = self.cfg.get("potion_area_rel")
        lb.config(text=(f"등록된 영역: 01번 클라 기준 ({a[0]},{a[1]}) 크기 {a[2]}x{a[3]}"
                        if a else "등록된 영역 없음 — [영역 지정]을 먼저 눌러주세요"))

    def _reg_potion_area(self):
        rects = self._client_rects_by_slot()
        if not rects:
            self.status.set("⚠ 리니지M 클라이언트 16개가 보이지 않습니다 (창을 모두 띄운 뒤 다시)")
            return
        self._potion_rects = rects
        w = getattr(self, "_potion_win", None)
        if w and w.winfo_exists():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(200, lambda: _PotionAreaOverlay(self, self._on_potion_area))

    def _on_potion_area(self, x, y, w, h):
        self.deiconify()
        pw = getattr(self, "_potion_win", None)
        if pw and pw.winfo_exists():
            try: pw.deiconify(); pw.lift()
            except Exception: pass
        if w < 3 or h < 3:
            self.status.set("영역이 너무 작습니다 — 다시 드래그해주세요"); return
        rects = getattr(self, "_potion_rects", None) or self._client_rects_by_slot()
        if not rects:
            self.status.set("⚠ 클라이언트 16개 감지 실패"); return
        oi = self._rect_owner(rects, x, y)      # 어느 클라에서 찍었는지 자동 인식
        base = rects[oi]
        self.cfg["potion_area_rel"] = [x - base[0], y - base[1], w, h]
        save_cfg(self.cfg)
        self._refresh_potion_area_lbl()
        self.status.set(f"✔ 물약 영역 등록 — #{oi+1:02d} 클라 기준 "
                        f"({x-base[0]},{y-base[1]}) {w}x{h}")

    @staticmethod
    def _potion_name(px):
        """영역 픽셀들 → 빨강/주황 판정.
        빨강 물약은 '순수 빨강(345~10°)' 픽셀이 뭉쳐 있고, 주황 물약은 그게 거의 없다.
        (주황 물약도 20~35° 픽셀이 많아서 '중앙값'으로는 구분이 안 됐다 —
         빨강 픽셀이 얼마나 있는지로 판정한다)"""
        import colorsys
        red = orange = strong = 0
        for r, g, b in px:
            h, sv, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if sv < 0.35 or v < 0.25:
                continue
            strong += 1
            deg = h * 360
            if deg >= 345 or deg <= 10:
                red += 1
            elif 11 <= deg <= 50:
                orange += 1
        if strong < 8:
            return "어두움", "#7f8c8d"
        if red >= max(5, strong * 0.08):
            return "빨강", "#c0392b"
        if orange >= max(5, strong * 0.08):
            return "주황", "#e67e22"
        return "기타", "#34495e"

    @staticmethod
    def _grab_client(hwnd, w, h):
        """클라이언트 창을 직접 캡처 — 다른 창에 가려져 있어도 제대로 찍힌다."""
        import win32gui, win32ui
        from ctypes import windll
        from PIL import Image
        hdc = win32gui.GetWindowDC(hwnd)
        mfc = win32ui.CreateDCFromHandle(hdc)
        save = mfc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc, w, h)
        save.SelectObject(bmp)
        windll.user32.PrintWindow(hwnd, save.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                              bits, "raw", "BGRX", 0, 1)
        try:
            win32gui.DeleteObject(bmp.GetHandle()); save.DeleteDC()
            mfc.DeleteDC(); win32gui.ReleaseDC(hwnd, hdc)
        except Exception:
            pass
        return im

    def _client_hwnds_by_slot(self):
        """슬롯 순서(01~16)로 (창핸들, 위치) — 화면 배치 세로 열우선."""
        try:
            import win32gui
            wins = []
            def cb(h, _):
                if win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h):
                    t = win32gui.GetWindowText(h)
                    if t.startswith("리니지M l"):
                        l, tp, r, b = win32gui.GetWindowRect(h)
                        if r - l > 100 and b - tp > 100:
                            wins.append((l, tp, r, b, h))
                return True
            win32gui.EnumWindows(cb, None)
            if len(wins) != 16:
                return None
            wins.sort(key=lambda w: w[0])
            cols = [sorted(wins[i*4:(i+1)*4], key=lambda w: w[1]) for i in range(4)]
            return [w for col in cols for w in col]
        except Exception:
            return None

    def _potion_check(self):
        area = self.cfg.get("potion_area_rel")
        if not area:
            self.status.set("먼저 [🧪 물약색] 창에서 [영역 지정]을 해주세요")
            self._open_potion_win(); return
        rects = self._client_rects_by_slot()
        if not rects:
            self.status.set("⚠ 리니지M 클라이언트 16개가 보이지 않습니다"); return
        try:
            from PIL import ImageGrab
        except Exception as e:
            self.status.set(f"⚠ 이미지 라이브러리 없음: {e}"); return
        if not (getattr(self, "_potion_win", None) and self._potion_win.winfo_exists()):
            self._open_potion_win()
            self.after(400, self._potion_check); return
        dx, dy, w, h = area
        hw = self._client_hwnds_by_slot()
        reds, oranges = [], []
        for i, rc in enumerate(rects):
            try:
                if hw:      # 창을 직접 캡처 — 다른 창에 가려져도 제대로 읽는다
                    l, t, r, b, hwnd = hw[i]
                    im = self._grab_client(hwnd, r - l, b - t).crop((dx, dy, dx + w, dy + h))
                else:
                    im = ImageGrab.grab(bbox=(rc[0] + dx, rc[1] + dy,
                                              rc[0] + dx + w, rc[1] + dy + h)).convert("RGB")
                name, col = self._potion_name(list(im.getdata()))
            except Exception:
                name, col = "실패", "#7f8c8d"
            if name == "빨강": reds.append(i + 1)
            elif name == "주황": oranges.append(i + 1)
            try:
                self._potion_cells[i].config(text=name, bg=col)
            except Exception:
                pass
        # 결과를 파일로 남긴다 — 섬/던전 실행기 슬롯에 그대로 표시되고,
        # 다시 측정하기 전까지 계속 유지된다
        try:
            import datetime as _dt
            res = {"time": f"{_dt.datetime.now():%m-%d %H:%M}",
                   "slots": {str(i + 1): ("빨강" if (i + 1) in reds else
                                          "주황" if (i + 1) in oranges else "")
                             for i in range(len(rects))}}
            d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "potion_result.json"), "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:                       # 결과 창을 앞으로 올려 바로 보이게
            w = getattr(self, "_potion_win", None)
            if w and w.winfo_exists():
                w.deiconify(); w.lift()
        except Exception:
            pass
        self.status.set(f"🧪 빨강 {len(reds)}개 {reds or ''} / 주황 {len(oranges)}개 {oranges or ''}")

    # ── 📜 주문서 층수 확인 ──────────────────────────────────────────────
    #   숫자가 5x8픽셀밖에 안 돼서 글자인식(OCR)으로는 못 읽는다.
    #   → 한 번만 사람이 숫자를 적어주면 그 그림을 기억해뒀다가(scroll_digits)
    #     다음부터는 그림을 맞대보고 같은 숫자를 찾아낸다. (경고확인과 같은 방식)
    SCROLL_PAD = 3          # 잘라올 때 상하좌우로 더 두는 여유 (px)

    @staticmethod
    def _scroll_dir():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI", "scroll_digits")
        os.makedirs(d, exist_ok=True)
        return d

    def _open_scroll_win(self):
        self._open_section_win("_scroll_win", "\U0001F4DC 주문서 층수",
                               self._build_scroll, w=520, h=560, pinnable=True)

    def _build_scroll(self, parent):
        tk.Label(parent, text="\U0001F4DC 주문서 층수 확인  (16개 클라를 한 번에)",
                 font=("맑은 고딕", 10, "bold"), fg="#1a5276").pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(parent, text="① [영역 지정]으로 주문서의 '층수 숫자' 자리만 드래그해서 한 번 등록\n"
                              "② [확인] → 16개 클라의 같은 자리를 잘라와 아래에 보여줍니다\n"
                              "③ 빈 칸은 '그림을 직접 보고' 숫자를 적은 뒤 [숫자 가르치기]\n"
                              "   → 칸은 확인할 때마다 비워집니다 — 이번에 읽은 것만 적힙니다\n"
                              "   ※ 슬롯마다 따로 기억합니다 (클라마다 화면이 미세하게 다름)\n"
                              "   ※ 빨간 테두리 칸 = 클라 화면이 꺼져 있어 못 읽은 칸",
                 font=("맑은 고딕", 8), fg="#555", justify="left").pack(anchor="w", padx=6)
        row = tk.Frame(parent); row.pack(fill="x", padx=6, pady=6)
        tk.Button(row, text="\U0001F4F7 영역 지정", font=("맑은 고딕", 9, "bold"),
                  bg="#2471a3", fg="white", command=self._reg_scroll_area).pack(side="left")
        tk.Button(row, text="\U0001F50D 확인", font=("맑은 고딕", 9, "bold"),
                  bg="#1a5276", fg="white", width=7,
                  command=self._scroll_check).pack(side="left", padx=(6, 0))
        tk.Button(row, text="\U0001F4DD 숫자 가르치기", font=("맑은 고딕", 9, "bold"),
                  bg="#117864", fg="white",
                  command=self._scroll_teach).pack(side="left", padx=(6, 0))
        tk.Button(row, text="\U0001F5D1 기억 지우기", font=("맑은 고딕", 9, "bold"),
                  bg="#7f8c8d", fg="white",
                  command=self._scroll_forget).pack(side="left", padx=(6, 0))
        self._scroll_area_lbl = tk.Label(parent, text="", font=("맑은 고딕", 8), fg="#888")
        self._scroll_area_lbl.pack(anchor="w", padx=6)
        self._refresh_scroll_area_lbl()

        grid = tk.Frame(parent); grid.pack(padx=6, pady=6)
        self._scroll_imgs  = []          # 잘라온 그림을 보여주는 라벨
        self._scroll_vars  = []          # 칸마다 숫자 입력
        self._scroll_photos = []         # PhotoImage 보관 (안 하면 그림이 사라짐)
        for i in range(16):
            r, c = i % 4, i // 4
            cell = tk.Frame(grid, bd=1, relief="groove", padx=3, pady=2)
            cell.grid(row=r, column=c, padx=4, pady=4, sticky="we")
            tk.Label(cell, text=f"{i+1:02d}", font=("맑은 고딕", 8, "bold"), fg="#555").pack()
            il = tk.Label(cell, bg="#222", width=8, height=3)
            il.pack()
            self._scroll_imgs.append(il)
            self._scroll_photos.append(None)
            v = tk.StringVar()
            self._scroll_vars.append(v)
            tk.Entry(cell, textvariable=v, font=("맑은 고딕", 10, "bold"), width=5,
                     justify="center").pack(pady=(2, 1))

    def _refresh_scroll_area_lbl(self):
        lb = getattr(self, "_scroll_area_lbl", None)
        if not lb or not lb.winfo_exists():
            return
        a = self.cfg.get("scroll_area_rel")
        n = len([f for f in os.listdir(self._scroll_dir()) if f.endswith(".png")])
        lb.config(text=((f"등록된 영역: ({a[0]},{a[1]}) 크기 {a[2]}x{a[3]}  /  기억한 숫자 {n}개"
                         if a else "등록된 영역 없음 — [영역 지정]을 먼저 눌러주세요")))

    def _reg_scroll_area(self):
        rects = self._client_rects_by_slot()
        if not rects:
            self.status.set("\u26a0 리니지M 클라이언트 16개가 보이지 않습니다 (창을 모두 띄운 뒤 다시)")
            return
        self._scroll_rects = rects
        w = getattr(self, "_scroll_win", None)
        if w and w.winfo_exists():
            try: w.withdraw()
            except Exception: pass
        self.withdraw()
        self.after(200, lambda: _PotionAreaOverlay(self, self._on_scroll_area))

    def _on_scroll_area(self, x, y, w, h):
        self.deiconify()
        pw = getattr(self, "_scroll_win", None)
        if pw and pw.winfo_exists():
            try: pw.deiconify(); pw.lift()
            except Exception: pass
        if w < 3 or h < 3:
            self.status.set("영역이 너무 작습니다 — 다시 드래그해주세요"); return
        rects = getattr(self, "_scroll_rects", None) or self._client_rects_by_slot()
        if not rects:
            self.status.set("\u26a0 클라이언트 16개 감지 실패"); return
        oi = self._rect_owner(rects, x, y)      # 어느 클라에서 찍었는지 자동 인식
        base = rects[oi]
        old = self.cfg.get("scroll_area_rel")
        # 기준 클라의 창 크기도 함께 저장 — 클라마다 창이 몇 px씩 달라서
        # 다른 클라에서는 그 비율만큼 자리를 옮겨 잘라야 같은 곳이 나온다
        self.cfg["scroll_area_rel"] = [x - base[0], y - base[1], w, h,
                                       base[2] - base[0], base[3] - base[1]]
        save_cfg(self.cfg)
        if old and (old[2], old[3]) != (w, h):
            # 영역 크기가 바뀌면 기억해둔 그림을 못 쓴다 — 다시 가르쳐야 한다
            try:
                for f in os.listdir(self._scroll_dir()):
                    if f.endswith(".png"):
                        os.remove(os.path.join(self._scroll_dir(), f))
            except Exception:
                pass
        self._refresh_scroll_area_lbl()
        self.status.set(f"\u2714 주문서 층수 영역 등록 — #{oi+1:02d} 클라 기준 "
                        f"({x-base[0]},{y-base[1]}) {w}x{h} — 이제 [확인]을 눌러주세요")

    def _scroll_grab(self):
        """16개 클라의 등록 영역을 잘라온다 (가려져 있어도 창을 직접 캡처)."""
        area = self.cfg.get("scroll_area_rel")
        if not area:
            self.status.set("먼저 [\U0001F4DC 주문서] 창에서 [영역 지정]을 해주세요")
            self._open_scroll_win(); return None
        rects = self._client_rects_by_slot()
        if not rects:
            self.status.set("\u26a0 리니지M 클라이언트 16개가 보이지 않습니다"); return None
        from PIL import ImageGrab
        dx, dy, w, h = area[:4]
        rw, rh = (area[4], area[5]) if len(area) >= 6 else (None, None)
        P = self.SCROLL_PAD                 # 창이 몇 px 어긋나도 찾아내도록 여유를 둔다
        hw = self._client_hwnds_by_slot()
        out = []
        for i, rc in enumerate(rects):
            try:
                cw, ch = rc[2] - rc[0], rc[3] - rc[1]
                ox = int(round(dx * cw / rw)) if rw else dx      # 창 크기 비율만큼 자리 보정
                oy = int(round(dy * ch / rh)) if rh else dy
                if hw:
                    l, t, r, b, hwnd = hw[i]
                    im = self._grab_client(hwnd, r - l, b - t).crop(
                        (ox - P, oy - P, ox + w + P, oy + h + P))
                else:
                    im = ImageGrab.grab(bbox=(rc[0] + ox - P, rc[1] + oy - P,
                                              rc[0] + ox + w + P,
                                              rc[1] + oy + h + P)).convert("RGB")
            except Exception:
                im = None
            out.append(im)
        return out

    def _scroll_match(self, im, idx):
        """그 슬롯에서 기억해둔 그림들과만 맞대본다 → 숫자 (헷갈리면 빈 값).

        클라마다 창 크기가 몇 px씩 달라 화면이 미세하게 다르게 그려진다.
        그래서 '다른 클라의 그림'과 비교하면 숫자 차이보다 그 차이가 더 커서
        틀리게 읽는다. 슬롯마다 따로 기억해두고 자기 것과만 비교한다."""
        try:
            import cv2, numpy as np
        except Exception:
            return ""
        a = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        sc = []
        for num, t in self._scroll_tpls(idx).items():
            if t.shape[0] > a.shape[0] or t.shape[1] > a.shape[1]:
                continue
            try:
                sc.append((float(cv2.matchTemplate(a, t, cv2.TM_CCOEFF_NORMED).max()), num))
            except Exception:
                pass
        if not sc:
            return ""
        sc.sort(reverse=True)
        if sc[0][0] < 0.97:
            return ""                                   # 기억한 것과 충분히 닮지 않음
        if len(sc) > 1 and (sc[0][0] - sc[1][0]) < 0.02:
            return ""                                   # 1등과 2등이 비슷하면 헷갈림
        return sc[0][1]

    def _scroll_tpls(self, idx):
        """그 슬롯에서 기억해둔 {숫자: 그림}."""
        try:
            import cv2
        except Exception:
            return {}
        out, d, pre = {}, self._scroll_dir(), f"s{idx+1:02d}_"
        for f in sorted(os.listdir(d)):
            if not (f.startswith(pre) and f.endswith(".png")):
                continue
            t = cv2.imread(os.path.join(d, f), cv2.IMREAD_GRAYSCALE)
            if t is not None:
                out[f[len(pre):-4]] = t
        return out

    @staticmethod
    def _scroll_is_dark(im):
        """클라가 절전(화면 꺼짐)이면 잘라온 그림이 온통 어둡다."""
        try:
            return max(im.convert("L").getdata()) < 80
        except Exception:
            return False

    def _scroll_show(self, i, im):
        """잘라온 그림을 칸에 크게 보여준다."""
        try:
            from PIL import ImageTk, Image
            big = im.resize((im.width * 5, im.height * 5), Image.LANCZOS)
            ph = ImageTk.PhotoImage(big)
            self._scroll_photos[i] = ph                     # 참조 유지
            self._scroll_imgs[i].config(image=ph, width=big.width, height=big.height)
        except Exception:
            pass

    def _scroll_check(self):
        if not (getattr(self, "_scroll_win", None) and self._scroll_win.winfo_exists()):
            self._open_scroll_win()
            self.after(400, self._scroll_check); return
        crops = self._scroll_grab()
        if crops is None:
            return
        self._scroll_crops = crops
        for v in self._scroll_vars:      # 이번에 읽은 것만 적는다
            v.set("")
        # 게임 배경(캐릭터·풍경)이 움직이는 순간엔 잘 안 맞을 수 있어서
        # 못 읽은 칸만 잠깐 뒤에 다시 찍어본다 (최대 3번)
        res = {}
        for tries in range(3):
            if tries:
                time.sleep(0.7)
                nc = self._scroll_grab()
                if nc:
                    for i in range(len(crops)):
                        if i not in res and nc[i] is not None:
                            crops[i] = nc[i]
                    self._scroll_crops = crops
            for i, im in enumerate(crops):
                if i in res or im is None or self._scroll_is_dark(im):
                    continue
                n = self._scroll_match(im, i)
                if n:
                    res[i] = n
            if len(res) == len(crops):
                break
        got, unknown, dark = 0, [], []
        for i, im in enumerate(crops):
            if im is None:
                unknown.append(i + 1); continue
            self._scroll_show(i, im)
            if self._scroll_is_dark(im):
                # 화면이 꺼져 있으면 주문서가 안 보인다 — 예전 값을 그대로 둔다
                dark.append(i + 1)
                try: self._scroll_imgs[i].config(bg="#c0392b")
                except Exception: pass
                continue
            try: self._scroll_imgs[i].config(bg="#222")
            except Exception: pass
            if i in res:
                self._scroll_vars[i].set(res[i]); got += 1
            else:
                unknown.append(i + 1)
        self._scroll_save_result()
        self._refresh_scroll_area_lbl()
        self._scroll_fit()
        self._scroll_raise()
        if dark and len(dark) == len(crops):
            self.status.set(f"\U0001F4DC 클라 화면이 꺼져 있어 주문서가 안 보입니다 "
                            f"— 절전을 풀고 다시 [확인]을 눌러주세요")
        elif got == 0:
            self.status.set("\U0001F4DC 아직 기억한 숫자가 없습니다 — 그림을 보고 칸에 숫자를 적은 뒤 "
                            "[\U0001F4DD 숫자 가르치기]를 눌러주세요"
                            + (f"  (화면 꺼짐 {dark})" if dark else ""))
        else:
            self.status.set(f"\U0001F4DC 주문서 층수 {got}/16 인식"
                            + (f" — 못 읽음 {unknown}" if unknown else "")
                            + (f" — 화면 꺼짐 {dark}" if dark else ""))

    def _scroll_teach(self):
        """칸에 적힌 숫자를 그 그림의 정답으로 기억한다.
        이미 다른 숫자로 기억해둔 그림과 똑같으면 거부한다 —
        한 번 잘못 기억하면 그 뒤로 계속 그 숫자로 읽히기 때문."""
        crops = getattr(self, "_scroll_crops", None)
        if not crops:
            self.status.set("먼저 [\U0001F50D 확인]을 눌러 그림을 가져와주세요"); return
        n, bad, dark = 0, [], []
        for i, v in enumerate(self._scroll_vars):
            num = (v.get() or "").strip()
            if not num.isdigit() or i >= len(crops) or crops[i] is None:
                continue
            if self._scroll_is_dark(crops[i]):
                dark.append(i + 1); continue    # 꺼진 화면은 기억해봐야 소용없다
            same = self._scroll_same_as(crops[i], i)   # 이 슬롯에서 이미 기억한 그림과 같은가
            if same and same != num:
                bad.append(f"{i+1}번({num}\u2260{same})")
                continue
            try:
                im = crops[i]
                P = self.SCROLL_PAD
                if im.width > 2 * P and im.height > 2 * P:
                    im = im.crop((P, P, im.width - P, im.height - P))
                im.save(os.path.join(self._scroll_dir(), f"s{i+1:02d}_{num}.png"))
                n += 1
            except Exception:
                pass
        self._scroll_save_result()
        self._refresh_scroll_area_lbl()
        msg = f"\U0001F4DD 숫자 {n}칸 기억했습니다"
        if bad:
            msg += (f"  \u26a0 {', '.join(bad)} 는 이미 다른 숫자로 기억한 그림과 똑같아서 "
                    f"넘겼습니다 — 숫자를 다시 확인해주세요")
        if dark:
            msg += f"  (화면 꺼짐 {dark} 은 제외)"
        self.status.set(msg)

    def _scroll_same_as(self, im, idx):
        """이 그림이 그 슬롯에서 이미 기억한 어떤 숫자와 사실상 같은가? → 그 숫자."""
        try:
            import cv2, numpy as np
        except Exception:
            return ""
        a = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        for num, t in self._scroll_tpls(idx).items():
            if t.shape[0] > a.shape[0] or t.shape[1] > a.shape[1]:
                continue
            try:
                if float(cv2.matchTemplate(a, t, cv2.TM_CCOEFF_NORMED).max()) > 0.99:
                    return num                                # 거의 똑같은 그림
            except Exception:
                pass
        return ""

    def _scroll_forget(self):
        """기억한 숫자 그림을 전부 지운다 (잘못 가르쳤을 때)."""
        d = self._scroll_dir()
        n = 0
        for f in os.listdir(d):
            if f.endswith(".png"):
                try:
                    os.remove(os.path.join(d, f)); n += 1
                except Exception:
                    pass
        self._refresh_scroll_area_lbl()
        self.status.set(f"\U0001F5D1 기억한 숫자 {n}개를 지웠습니다 — 다시 가르쳐주세요")

    def _scroll_save_result(self):
        """칸에 적힌 값을 결과로 저장 — 오만의탑 실행기에 그대로 표시된다."""
        try:
            import datetime as _dt
            res = {"time": f"{_dt.datetime.now():%m-%d %H:%M}",
                   "slots": {str(i + 1): (v.get() or "").strip()
                             for i, v in enumerate(self._scroll_vars)}}
            d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "scroll_result.json"), "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _scroll_fit(self):
        """그림이 들어오면 잘리지 않게 창을 내용 크기에 맞춘다."""
        try:
            w = getattr(self, "_scroll_win", None)
            if not (w and w.winfo_exists()):
                return
            w.update_idletasks()
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            w.geometry(f"{min(w.winfo_reqwidth() + 12, sw - 40)}x"
                       f"{min(w.winfo_reqheight() + 8, sh - 80)}")
        except Exception:
            pass

    def _scroll_raise(self):
        try:
            w = getattr(self, "_scroll_win", None)
            if w and w.winfo_exists():
                w.deiconify(); w.lift()
        except Exception:
            pass

    # ── 🔐 본인확인 도우미 (임시제한 해제 시 전화·이메일 붙여넣기 보조) ──────
    #    감지+계정확인+전화/이메일 클립보드 복사까지만. 붙여넣기·확인은 사람이.
    @staticmethod
    def _vf_is_phone(v):
        import re
        v = str(v).strip()
        return bool(re.search(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}", v)) or \
               bool(re.match(r"^\d[\d\-\s]{8,}$", v))

    def _vf_id_of(self, fields):
        """계정 5칸 중 표시할 아이디 하나 — 한글 아이디 우선 (전화·이메일·영어 제외)."""
        names = [f for f in fields if f and not self._vf_is_phone(f) and "@" not in f]
        if not names:
            return ""
        return next((f for f in names
                     if any('가' <= ch <= '힣' for ch in f)), names[0])

    def _open_verify_win(self):
        self._open_section_win("_verify_win", "🔐 본인확인 도우미", self._build_verify, w=601, h=576, fit=False)

    def _build_verify(self, parent):
        tk.Label(parent, text="🔐 본인확인 도우미", font=("맑은 고딕", 10, "bold"),
                 fg="#2c3e50").pack(anchor="w", padx=6, pady=(6, 0))
        tk.Label(parent, text="계정 클릭 → 전화·이메일 복사 → Ctrl+V   |   칸 우클릭 = 색 지정 (8개씩 그룹 구분)",
                 font=("맑은 고딕", 8), fg="#666").pack(anchor="w", padx=6, pady=(0, 4))

        tk.Button(parent, text="🔍 영역 확대해서 보기 (아이디가 가려/쪼개질 때)",
                  font=("맑은 고딕", 10, "bold"), bg="#16a085", fg="white",
                  command=self._vf_zoom_region).pack(fill="x", padx=6, pady=(0, 6))

        # 계정 4열 4행 그리드 — 아이디(클릭 선택) + 그 밑에 메모 입력 (셀 세로 1.4배)
        grid = tk.Frame(parent); grid.pack(fill="x", padx=6, pady=2)
        for cc in range(4):
            grid.columnconfigure(cc, weight=1)
        self._vf_cells = []
        self._vf_cell_lbls = []
        colors = self.cfg.get("verify_colors") or {}
        for i in range(16):
            r, c = divmod(i, 4)
            x = self._accounts[i] if i < len(self._accounts) else {}
            fields = [str(x.get(f"f{j+1}", "")).strip() for j in range(5)]
            disp = self._vf_id_of(fields) or "(빈칸)"
            bg = colors.get(str(i)) or "#ecf0f1"
            cell = tk.Frame(grid, bg=bg, relief="raised", bd=1)
            cell.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            lbl = tk.Label(cell, text=disp, font=("맑은 고딕", 12, "bold"),
                           bg=bg, wraplength=120, justify="center", height=2)
            lbl.pack(fill="both", expand=True, padx=4, pady=8)
            for wdg in (cell, lbl):
                wdg.bind("<Button-1>", lambda e, ii=i: self._vf_pick_cell(ii))
                wdg.bind("<Button-3>", lambda e, ii=i: self._vf_color_menu(e, ii))
            self._vf_cells.append(cell)
            self._vf_cell_lbls.append(lbl)

        self._vf_result = tk.StringVar(value="— 위 표에서 계정을 선택하세요 —")
        tk.Label(parent, textvariable=self._vf_result, font=("맑은 고딕", 10), fg="#1a5276",
                 justify="left", anchor="w", wraplength=440).pack(fill="x", padx=6, pady=6)

        br = tk.Frame(parent); br.pack(fill="x", padx=6, pady=4)
        tk.Button(br, text="📋 전화 복사", font=("맑은 고딕", 11, "bold"), bg="#27ae60", fg="white",
                  height=2, command=lambda: self._vf_copy("phone")).pack(side="left", expand=True, fill="x", padx=(0, 3))
        tk.Button(br, text="📋 이메일 복사", font=("맑은 고딕", 11, "bold"), bg="#e67e22", fg="white",
                  height=2, command=lambda: self._vf_copy("email")).pack(side="left", expand=True, fill="x", padx=(3, 0))
        self._vf_match = None

        # 📝 떠있는 클라 메모 4개 — 각각 체크로 켜고, 직접 입력, Ctrl+드래그로 이동
        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=6, pady=(6, 2))
        mrow = tk.Frame(parent); mrow.pack(fill="x", padx=6, pady=(0, 2))
        tk.Label(mrow, text="📝 클라 위 메모:", font=("맑은 고딕", 8, "bold")).pack(side="left")
        self._memo_on_vars = []
        ons, _t, _p = self._memo_lists()
        for i in range(4):
            v = tk.BooleanVar(value=ons[i])
            self._memo_on_vars.append(v)
            tk.Checkbutton(mrow, text=f"{i+1}", variable=v,
                           command=lambda ii=i: self._memo_toggle(ii),
                           font=("맑은 고딕", 8)).pack(side="left")
        # 지금 상태(글·위치)는 그대로 두고 화면에서만 전부 끄기/켜기
        self._memo_all_btn = tk.Button(mrow, text="전부 끄기", font=("맑은 고딕", 8, "bold"),
                                       bg="#c0392b", fg="white", width=8,
                                       command=self._memo_toggle_all)
        self._memo_all_btn.pack(side="left", padx=(8, 0))
        self._refresh_memo_all_btn()
        tk.Label(parent, text="(체크하면 노란 메모가 뜸 · 직접 입력 · Ctrl+드래그로 이동 · 리니지M이 앞에 있을 때만 그 위에 보임/항상위 아님)",
                 font=("맑은 고딕", 7), fg="#888").pack(anchor="w", padx=6)

    def _refresh_memo_all_btn(self):
        b = getattr(self, "_memo_all_btn", None)
        if not b or not b.winfo_exists():
            return
        ons, _t, _p = self._memo_lists()
        if any(ons):
            b.config(text="전부 끄기", bg="#c0392b", activebackground="#922b21")
        else:
            b.config(text="전부 켜기", bg="#27ae60", activebackground="#1e8449")

    def _memo_toggle_all(self):
        """클라 위 메모를 지금 상태 그대로 두고 화면에서만 전부 끈다/켠다.
        (글·위치는 저장돼 있으므로 다시 켜면 그대로 돌아온다)"""
        ons, _t, _p = self._memo_lists()
        turn_on = not any(ons)
        if turn_on:
            prev = list(self.cfg.get("float_memo_ons_bak") or [])
            while len(prev) < 4: prev.append(True)
            ons = [bool(x) for x in prev[:4]]
            if not any(ons):
                ons = [True] * 4
        else:
            self.cfg["float_memo_ons_bak"] = list(ons)   # 어떤 게 켜져 있었는지 기억
            ons = [False] * 4
        self.cfg["float_memo_ons"] = ons
        save_cfg(self.cfg)
        for i, v in enumerate(getattr(self, "_memo_on_vars", [])):
            try: v.set(ons[i])
            except Exception: pass
        self._refresh_memo_all_btn()
        self.status.set("📝 클라 위 메모 " + ("전부 켬 (이전 상태로)" if turn_on else "전부 끔 (글·위치는 그대로)"))

    def _memo_toggle(self, i):
        ons = list(self.cfg.get("float_memo_ons") or [])
        while len(ons) < 4:
            ons.append(False)
        ons[i] = bool(self._memo_on_vars[i].get())
        self.cfg["float_memo_ons"] = ons; save_cfg(self.cfg)
        self._refresh_memo_all_btn()
        self.status.set(f"📝 메모{i+1} " + ("켬" if ons[i] else "끔"))

    def _vf_pick_cell(self, idx):
        """4x4 그리드에서 계정 클릭 → 선택 확정 + 전화·이메일 표시."""
        x = self._accounts[idx] if idx < len(self._accounts) else {}
        fields = [str(x.get(f"f{j+1}", "")).strip() for j in range(5)]
        phone = next((f for f in fields if self._vf_is_phone(f)), "")
        email = next((f for f in fields if "@" in f), "")
        disp = self._vf_id_of(fields) or f"#{idx+1:02d}"
        self._vf_match = {"idx": idx, "disp": disp, "phone": phone, "email": email}
        # 색은 유지, 선택 표시는 테두리로
        for k, cell in enumerate(self._vf_cells):
            cell.config(relief=("solid" if k == idx else "raised"),
                        bd=(3 if k == idx else 1))
        self._vf_result.set(f"✔ {disp}\n전화: {phone or '(없음)'}\n이메일: {email or '(없음)'}")

    _VF_PALETTE = [("🟡 노랑", "#f9e79f"), ("🟢 초록", "#abebc6"), ("🔵 파랑", "#aed6f1"),
                   ("🟣 보라", "#d7bde2"), ("🩷 분홍", "#f5b7b1"), ("🟠 주황", "#fad7a0"),
                   ("⬜ 기본색(지우기)", "")]

    def _vf_color_menu(self, event, idx):
        """칸 우클릭 → 색 선택 메뉴 (8개씩 그룹 구분용)."""
        m = tk.Menu(self, tearoff=0)
        for name, col in self._VF_PALETTE:
            m.add_command(label=name, command=lambda c=col, i=idx: self._vf_set_color(i, c))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _vf_set_color(self, idx, color):
        colors = dict(self.cfg.get("verify_colors") or {})
        if color:
            colors[str(idx)] = color
        else:
            colors.pop(str(idx), None)
        self.cfg["verify_colors"] = colors
        save_cfg(self.cfg)
        try:
            bg = color or "#ecf0f1"
            self._vf_cells[idx].config(bg=bg)
            self._vf_cell_lbls[idx].config(bg=bg)
        except Exception:
            pass
        self.status.set(f"🎨 #{idx+1:02d} 색 {'지움' if not color else '변경됨 (저장됨)'}")

    def _vf_copy(self, which):
        r = self._vf_match
        if not r:
            self.status.set("먼저 계정을 조회하거나 선택하세요."); return
        val = r.get(which, "")
        label = "전화" if which == "phone" else "이메일"
        if not val:
            self.status.set(f"{label}가 없습니다."); return
        self.clipboard_clear(); self.clipboard_append(val)
        self.status.set(f"📋 #{r['idx']+1:02d} {label} 복사됨 — 칸 클릭 후 Ctrl+V")

    # ── 📝 떠있는 클라 메모 4개 (각각 체크로 켬 · 리니지M 앞일 때만 그 위에 보임/항상위 아님) ──
    _MEMO_N = 4

    def _memo_lists(self):
        ons = list(self.cfg.get("float_memo_ons") or [])
        txts = list(self.cfg.get("float_memo_texts") or [])
        poss = list(self.cfg.get("float_memo_positions") or [])
        dft = [[500, 40], [660, 40], [500, 90], [660, 90]]
        while len(ons) < self._MEMO_N: ons.append(False)
        while len(txts) < self._MEMO_N: txts.append("")
        while len(poss) < self._MEMO_N: poss.append(dft[len(poss) % 4])
        return ons[:self._MEMO_N], txts[:self._MEMO_N], poss[:self._MEMO_N]

    def _memo_tick(self):
        try:
            ons, txts, poss = self._memo_lists()
            if getattr(self, "_memo_wins", None) is None:
                self._memo_wins = {}
            # 매크로/작업 실행 중엔 메모를 아예 숨김 — 자동 클릭을 가로채지 않게
            busy = self._is_busy() or getattr(self, "_running", False)
            for i in range(self._MEMO_N):
                if ons[i] and not busy:
                    self._memo_show_one(i, txts[i], poss[i])
                else:
                    self._memo_hide_one(i)
            if not busy:
                self._memo_raise_over_lineage()
        except Exception:
            pass
        # 클라를 클릭해 앞으로 나와도 곧바로 메모가 다시 위로 오도록 자주 확인
        self.after(300, self._memo_tick)

    def _memo_show_one(self, i, txt, pos):
        store = self._memo_wins
        w = store.get(i)
        if w and w[0].winfo_exists():
            return
        try:
            win = tk.Toplevel(self)
            win.overrideredirect(True)          # 항상위 아님
            var = tk.StringVar(value=txt)
            ent = tk.Entry(win, textvariable=var, font=("맑은 고딕", 12, "bold"),
                           fg="#000000", bg="#fff59d", width=14, justify="center",
                           relief="solid", bd=2)
            ent.pack(ipady=5)   # 세로 약 1.3배 (내부 여백)
            # 오른쪽 클릭 → [종료] 메뉴가 뜨고, 그걸 눌러야 꺼진다 (실수 방지)
            for _w in (ent, win):
                _w.bind("<Button-3>", lambda e, ii=i: self._memo_menu(ii, e))
            win.geometry(f"+{int(pos[0])}+{int(pos[1])}")
            var.trace_add("write", lambda *a: self._memo_save_texts())
            ent.bind("<Control-Button-1>", lambda e, ww=win: setattr(ww, "_d", (e.x, e.y)))
            ent.bind("<Control-B1-Motion>", lambda e, ww=win: ww.geometry(
                f"+{ww.winfo_x()+e.x-getattr(ww,'_d',(0,0))[0]}+{ww.winfo_y()+e.y-getattr(ww,'_d',(0,0))[1]}"))
            # 위치 저장 — Ctrl을 먼저 떼도 저장되게 두 경우 모두 잡는다
            # (예전엔 Ctrl+뗌 조합에서만 저장돼, Ctrl을 먼저 놓으면 위치가 안 남았다)
            ent.bind("<Control-ButtonRelease-1>", lambda e: self._memo_save_positions())
            ent.bind("<ButtonRelease-1>", lambda e: self._memo_save_positions())
            store[i] = (win, var)
        except Exception:
            pass

    def _memo_menu(self, i, ev):
        """메모 오른쪽 클릭 — [종료] 메뉴를 띄운다. 눌러야 실제로 꺼진다."""
        try:
            m = tk.Menu(self, tearoff=0, font=("맑은 고딕", 10))
            m.add_command(label="✕  종료", command=lambda ii=i: self._memo_off_one(ii))
            m.add_separator()
            m.add_command(label="닫기")          # 아무것도 안 함 (취소용)
            try:
                m.tk_popup(ev.x_root, ev.y_root)
            finally:
                m.grab_release()
        except Exception:
            pass

    def _memo_off_one(self, i):
        """메모 위의 ✕(또는 오른쪽 클릭) — 그 메모만 끈다. 글·위치는 그대로 남는다."""
        ons = list(self.cfg.get("float_memo_ons") or [])
        while len(ons) < 4:
            ons.append(False)
        ons[i] = False
        self.cfg["float_memo_ons"] = ons
        save_cfg(self.cfg)
        try:
            self._memo_on_vars[i].set(False)
        except Exception:
            pass
        self._refresh_memo_all_btn()
        self._memo_hide_one(i)
        self.status.set(f"📝 메모{i+1} 끔 — 글·위치는 그대로, [🔐 본인확인 도우미]에서 다시 켤 수 있어요")

    def _memo_hide_one(self, i):
        store = getattr(self, "_memo_wins", {}) or {}
        w = store.pop(i, None)
        if w:
            # 숨기기 전에 지금 위치를 남긴다 — 다시 띄울 때 그 자리에 뜨게
            try:
                if w[0].winfo_exists():
                    _o, _t, poss = self._memo_lists()
                    poss[i] = [w[0].winfo_x(), w[0].winfo_y()]
                    self.cfg["float_memo_positions"] = poss
                    save_cfg(self.cfg)
            except Exception:
                pass
            try: w[0].destroy()
            except Exception: pass

    def _memo_save_texts(self):
        try:
            _o, txts, _p = self._memo_lists()
            for i, (win, var) in self._memo_wins.items():
                txts[i] = var.get()
            self.cfg["float_memo_texts"] = txts; save_cfg(self.cfg)
        except Exception:
            pass

    def _memo_save_positions(self):
        try:
            _o, _t, poss = self._memo_lists()
            for i, (win, var) in self._memo_wins.items():
                if win.winfo_exists():
                    poss[i] = [win.winfo_x(), win.winfo_y()]
            self.cfg["float_memo_positions"] = poss; save_cfg(self.cfg)
        except Exception:
            pass

    def _memo_fg_is_lineage(self):
        """맨 앞 창이 리니지M 클라이고 '지금 상태(확대 아님)'이면 True.
        판단: 다른 타일 클라들보다 눈에 띄게 크거나 최대화면 확대로 보고 False."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            h = u.GetForegroundWindow()
            b = ctypes.create_unicode_buffer(300); u.GetWindowTextW(h, b, 300)
            t = b.value
            if ("리니지" not in t) or t == "리니지M 자동 실행":
                return False
            if u.IsZoomed(h):                       # 완전 최대화 → 확대
                return False
            r = wintypes.RECT(); u.GetWindowRect(h, ctypes.byref(r))
            fw = r.right - r.left; fh = r.bottom - r.top
            # 다른 리니지M 클라들의 가로·세로 수집 (타일 상태 기준)
            ws, hs = [], []
            def cb(hh, _):
                if hh != h and u.IsWindowVisible(hh) and not u.IsIconic(hh):
                    bb = ctypes.create_unicode_buffer(300); u.GetWindowTextW(hh, bb, 300)
                    tt = bb.value
                    if ("리니지" in tt) and tt != "리니지M 자동 실행":
                        rr = wintypes.RECT(); u.GetWindowRect(hh, ctypes.byref(rr))
                        w = rr.right - rr.left; ht = rr.bottom - rr.top
                        if w > 100 and ht > 100:
                            ws.append(w); hs.append(ht)
                return True
            WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            u.EnumWindows(WN(cb), 0)
            if ws:
                # 가장 작은(타일) 클라 기준 — 여러 개 확대해도 흔들리지 않음
                if fw > min(ws) * 1.25 or fh > min(hs) * 1.25:
                    return False                          # 확대 → 안 띄움
                return True
            # 비교할 다른 클라 없으면 화면폭 60% 미만이면 지금상태로 봄
            return fw < u.GetSystemMetrics(0) * 0.6
        except Exception:
            return False

    def _memo_boost(self):
        """[🔥 혈레이드] — 클라 위 메모를 5분 동안만 맨 위로 표시, 이후 자동으로 뒤로."""
        self._memo_boost_until = time.time() + 300
        self.status.set("🔥 혈레이드 — 메모를 5분 동안 맨 위로 띄웁니다")

    def _memo_raise_over_lineage(self):
        """평소엔 메모를 위로 올리지 않는다 (거슬리지 않게).
        [🔥 혈레이드]를 누르면 5분 동안만 항상 위로 표시."""
        boost = time.time() < getattr(self, "_memo_boost_until", 0)
        for i, (win, var) in list(getattr(self, "_memo_wins", {}).items()):
            try:
                if not win.winfo_exists():
                    continue
                if boost:
                    win.attributes("-topmost", True)
                    win.lift()
                else:
                    win.attributes("-topmost", False)   # 항상위만 해제 — 나머지는 그대로 둠
            except Exception:
                pass

    def _vf_zoom_region(self):
        """영역을 드래그하면 그 부분을 크게 확대해 보여준다 — 가려/쪼개진 아이디를 눈으로 읽기."""
        self.status.set("1초 후 확대해서 볼 영역(아이디 부분)을 드래그하세요!")
        self.after(1000, lambda: [self.withdraw(), self.after(150, lambda: _ZoomCaptureOverlay(self))])

    def _vf_show_zoom(self, bbox):
        try:
            from PIL import ImageGrab, Image, ImageTk
            x0, y0, x1, y1 = bbox
            bx0, by0, bx1, by1 = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
            if (bx1 - bx0) < 4 or (by1 - by0) < 4:
                self.deiconify(); self.status.set("영역이 너무 작습니다. 다시 드래그하세요."); return
            img = ImageGrab.grab(bbox=(bx0, by0, bx1, by1), all_screens=True)
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            maxw, maxh = int(sw * 0.85), int(sh * 0.7)
            scale = min(6.0, maxw / max(img.width, 1), maxh / max(img.height, 1))
            scale = max(1.0, scale)
            big = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
            win = tk.Toplevel(self)
            win.title("🔍 아이디 확대 — 읽고 4×4 표에서 계정 선택 (4초 후 자동 닫힘)")
            win.attributes("-topmost", True)
            self._vf_zoom_imgtk = ImageTk.PhotoImage(big)   # GC 방지용 참조 유지
            tk.Label(win, text="↓ 이 아이디를 도우미 창의 4×4 표에서 고르세요  (4초 후 자동 닫힘)",
                     font=("맑은 고딕", 9), fg="#16a085").pack(pady=(6, 0))
            tk.Label(win, image=self._vf_zoom_imgtk, bd=1, relief="solid").pack(padx=8, pady=8)
            tk.Button(win, text="닫기", command=win.destroy).pack(pady=(0, 8))
            # 4초 후 자동으로 닫힘 (확대 창만) — 미리 닫혀 있으면 무시
            win.after(4000, lambda w=win: w.winfo_exists() and w.destroy())
            self.deiconify()
        except Exception as e:
            self.deiconify(); self.status.set(f"확대 오류: {e}")

    def _target_geometry(self):
        """콘텐츠에 맞는 목표 창 크기/위치 (폭=섹션행, 높이=콘텐츠+1cm, 작업표시줄 위로)."""
        self.update_idletasks()
        needed = self.winfo_reqheight() + 38   # 슬롯 끝에서 약 1cm 여유
        pos = self.cfg.get("main_win_fixed") or self.cfg.get("main_win_pos")   # 고정 위치 우선
        x, y = (int(pos[0]), int(pos[1])) if pos else (76, 75)
        work_bottom = self.winfo_screenheight() - 48   # fallback
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
            work_bottom = rect.bottom
        except Exception:
            pass
        # 창 하단이 작업표시줄 아래로 잘리지 않도록 위로 올리고, 그래도 넘치면 높이 축소
        if y + needed > work_bottom:
            y = max(0, work_bottom - needed)
            if y + needed > work_bottom:
                needed = work_bottom - y
        try:
            w = max(self._sec_row.winfo_reqwidth() + 20, self.winfo_reqwidth())
        except Exception:
            w = self.winfo_width() or 1047
        w += 76   # 좌우 약 1cm씩(≈38px) 여유 — 내용이 가운데 정렬이라 양옆에 균등 여백
        return w, needed, x, y

    def _fit_main_height(self):
        # 최소화(iconic) 상태에선 geometry 변경이 복원 크기에 안 먹으므로 normal일 때만 조정
        try:
            if self.state() != "normal":
                return
        except Exception:
            pass
        w, h, x, y = self._target_geometry()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._did_initial_fit = True   # normal 상태에서 실제로 맞췄을 때만 완료 표시

    def _align_tj_to_dc(self, _tries=0):
        """TJ성공!! 좌측 라인이 기준 — 일반던전충전 열·맨뒤로·혈레이드·★과거섬패스를
        전부 TJ 좌측에 맞춤. (여백을 조절하며 맞을 때까지 반복 보정.)
        최소화 상태에선 좌표가 쓰레기값이라 절대 계산하지 않는다."""
        try:
            if self.state() != "normal":
                if _tries < 30:   # 창이 보일 때까지 기다렸다가 계산
                    self.after(1000, lambda: self._align_tj_to_dc(_tries + 1))
                return
            self.update_idletasks()
            need_more = False
            # 1) 일반던전충전 열(front_row) ← TJ성공!! 좌측 라인
            #    (TJ가 기준 — 실행 버튼들이 클라이언트에 가리지 않게 왼쪽으로 당김)
            try:
                tj_bx = self._tjcol.winfo_rootx() - self.winfo_rootx()
                dxf = self._dc_open_btn.winfo_rootx() - self._tjcol.winfo_rootx()
                if getattr(self, "_frontrow_padx", None) is None:
                    if 0 <= tj_bx < 800:
                        self._frontrow_padx = max(0, tj_bx)
                        self._front_row.pack_configure(anchor="w", padx=(self._frontrow_padx, 0))
                        need_more = True
                elif 2 < abs(dxf) < 900:
                    self._frontrow_padx = max(0, self._frontrow_padx - dxf)
                    self._front_row.pack_configure(padx=(self._frontrow_padx, 0))
                    need_more = True
            except Exception:
                pass
            # 2) 맨뒤로/혈레이드/제자리 ← TJ성공!! 좌측 라인에 일렬로
            try:
                bx = self._tjcol.winfo_rootx() - self.winfo_rootx()
                if 0 <= bx < 800:
                    self._back_circle.pack_configure(padx=(bx, 0))
                    self._boost_btn.pack_configure(padx=(bx, 0))
            except Exception:
                pass
            # 3) ★ 과거섬 패스 ← 일반던전충전 좌측 라인 (맞을 때까지 반복)
            try:
                _left = getattr(self, "_stop_col", None) or self._past_skip_btn
                dx2 = self._dc_open_btn.winfo_rootx() - _left.winfo_rootx()
                if 2 < abs(dx2) < 900:
                    if dx2 > 0:
                        # 오른쪽으로 이동 — 별 버튼 왼쪽 여백 증가
                        pad = min(600, getattr(self, "_star_pad", 0) + dx2)
                        self._star_pad = pad
                        _left.pack_configure(padx=(pad, 6))
                    else:
                        # 왼쪽으로 이동 — 행 오른쪽 여백을 늘려 행 전체를 왼쪽으로
                        cur_p = getattr(self, "_star_pad", 0)
                        if cur_p > 0:
                            take = min(cur_p, -dx2)
                            self._star_pad = cur_p - take
                            _left.pack_configure(padx=(self._star_pad, 6))
                            dx2 += take
                        if dx2 < -2:
                            w2 = min(1200, getattr(self, "_secrow_pad_w", 0) + 2 * (-dx2))
                            self._secrow_pad_w = w2
                            self._secrow_pad.config(width=w2)
                    need_more = True
            except Exception:
                pass
            if need_more and _tries < 40:
                self.after(150, lambda: self._align_tj_to_dc(_tries + 1))
        except Exception:
            pass

    def _purple_popup_tick(self):
        """(2026-08-11) 퍼플을 켜면 아래에 뜨는 팝업을 상시 감시해서 바로 닫는다.
        · 다른 작업이 돌고 있으면 건드리지 않는다 (클릭 충돌 방지)
        · 사용자가 마우스를 쓰는 중이면 다음 기회에 (커서를 뺏지 않게)"""
        try:
            det = self.cfg.get("purple_popup_detect")
            col = self.cfg.get("purple_popup_color")
            cls = self.cfg.get("purple_popup_close")
            if det and col and cls and not self._is_busy():
                from PIL import ImageGrab
                x, y = int(det[0]), int(det[1])
                px = ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).convert("RGB").getpixel((0, 0))
                if (abs(px[0] - col[0]) <= 30 and abs(px[1] - col[1]) <= 30
                        and abs(px[2] - col[2]) <= 30):
                    p0 = pyautogui.position()
                    time.sleep(0.15)
                    if pyautogui.position() == p0:      # 마우스가 멈춰 있을 때만
                        back = pyautogui.position()
                        chk = self.cfg.get("purple_popup_checkbox")
                        if chk:
                            pyautogui.click(*chk); time.sleep(0.35)
                        pyautogui.click(*cls); time.sleep(0.2)
                        try: pyautogui.moveTo(*back)    # 커서 원위치
                        except Exception: pass
                        self.status.set("✔ 퍼플 팝업 자동으로 닫음")
        except Exception:
            pass
        self.after(2000, self._purple_popup_tick)

    def _purple_ad_tick(self):
        """(2026-08-13) 퍼플 광고창('소식')이 뜨면 마우스를 전혀 쓰지 않고 그 창만 닫는다.
        창을 직접 닫는 방식이라 게임 조작이나 커서에 아무 영향이 없다."""
        try:
            import win32gui, win32con
            targets = []

            def _cb(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                cls = win32gui.GetClassName(hwnd) or ""
                if not cls.startswith("HwndWrapper[Purple.exe"):
                    return True
                t = (win32gui.GetWindowText(hwnd) or "").strip()
                if t in ("소식", "공지", "이벤트", "알림"):
                    l, tp, r, b = win32gui.GetWindowRect(hwnd)
                    if r - l > 200 and b - tp > 150:      # 작은 보조창은 제외
                        targets.append((hwnd, t))
                return True

            win32gui.EnumWindows(_cb, None)
            for hwnd, t in targets:
                try:
                    win32gui.SendMessageTimeout(hwnd, win32con.WM_CLOSE, 0, 0,
                                                win32con.SMTO_ABORTIFHUNG, 1500)
                    self.status.set(f"✔ 퍼플 광고창 '{t}' 자동으로 닫음")
                except Exception:
                    pass
        except Exception:
            pass
        self.after(3000, self._purple_ad_tick)   # 3초마다 (부하 절반)

    def _auto_back_check(self, _e=None):
        """(2026-08-11) 메인런처 말고 다른 창(리니지M 클라·바탕화면 등)이 앞으로 오면
        기다리지 않고 곧바로 '맨 뒤'로 보낸다 — 클라를 가리지 않게."""
        try:
            import ctypes
            u = ctypes.windll.user32
            fg = u.GetForegroundWindow()
            pid = ctypes.c_ulong()
            u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if pid.value == os.getpid():
                self._auto_back_done = 0        # 내 창을 보고 있으면 그대로 둔다
                return
            # 클로드 창을 보고 있으면 건드리지 않는다 (사용자가 쓰는 중)
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(fg, buf, 256)
            if "claude" in buf.value.lower():
                self._auto_back_done = 0
                return
            if fg and fg != getattr(self, "_auto_back_done", 0):
                self._auto_back_done = fg       # 같은 창에 대해 한 번만
                if self.state() == "normal":
                    self._send_to_back()        # 메인런처는 맨 뒤로
                self._minimize_claude()         # 클로드 창은 최소화 (2026-08-13)
        except Exception:
            pass

    def _auto_back_tick(self):
        self._auto_back_check()
        self.after(80, self._auto_back_tick)    # 0.08초마다 — 즉시 반응

    def _raise_on_click(self, e=None):
        """메인런처 안 아무 곳(빈 곳 포함)이나 클릭하면 창을 앞으로 올린다."""
        try:
            if self.state() != "normal" or getattr(self, "_quiet_restore", False):
                return
            self.lift()
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, "리니지M 자동 실행")
            if hwnd:
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
        except Exception:
            pass

    def _bring_to_front(self, e=None):
        if getattr(self, "_quiet_restore", False):   # 맨뒤 복원 중엔 올리지 않음
            return
        self.lift()

    def _raise_main(self):
        """최소화된 메인런처를 복원하고 앞으로 올림 (항상 위 고정은 안 함)"""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _on_main_unmap(self, e=None):
        """메인런처가 최소화되면 클로드 앱도 같이 최소화.
        (복원은 클로드를 직접 클릭해서 따로 열 수 있음 — 자동 복원 안 함)
        단, 시작 직후 워치독이 런처를 최소화하는 건 제외(배포/시작 시 클로드 안 내리게)."""
        if not getattr(self, "_unmap_couple_ok", False):
            return
        def _chk():
            try:
                if self.state() == "iconic":   # 실제 최소화일 때만 (withdraw/등록오버레이 제외)
                    self._minimize_claude()
            except Exception:
                pass
        self.after(120, _chk)

    def _on_main_map(self, e):
        """패스권 창이 켜져 있으면 메인 런처 최소화 유지 (섬/던전은 사용자가 직접 복원 가능)"""
        pass_open = self._pass_win and self._pass_win.winfo_exists()
        if pass_open:
            self.after(50, self._send_to_back)
            return
        self._last_activity = time.time()   # 다시 올라오면 유휴 타이머 리셋
        # 작업 완료 후 '맨 뒤로 복원'(_restore_back) 중에는 앞으로 올리지 않는다
        if not getattr(self, "_quiet_restore", False):
            self._bring_to_front()
        # 워치독이 최소화 상태로 띄우면 시작 시 크기맞춤이 걸리지 않으므로,
        # 최초로 창이 보여질 때 딱 한 번만 콘텐츠 크기에 맞춘다(맵 이벤트 폭주 방지: 1회성).
        if not getattr(self, "_did_initial_fit", False):
            self.after(60, self._fit_main_height)

    def _open_pass_win(self):
        if self._pass_win and self._pass_win.winfo_exists():
            self._pass_win.lift(); return
        self._send_to_back()
        win = tk.Toplevel(self)
        win.title("🎫 패스권 새로운 등록")
        win.geometry("480x720")
        win.resizable(True, True)
        def _on_pass_close():
            win.destroy()
            if not (hasattr(self, "_island_proc") and self._island_proc and self._island_proc.poll() is None):
                self.deiconify()
        win.protocol("WM_DELETE_WINDOW", _on_pass_close)
        self._pass_win = win
        self._build_pass(win)
        self._refresh_ui()

    def _build_pass(self, parent):
        tk.Label(parent, text=f"패스권 새로운 등록  ({PASS_CLICKS}번 클릭)",
                 font=("맑은 고딕", 9, "bold"), fg="#6c3483").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._pass_stop = False
        self.btn_pass_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#6c3483", fg="white",
            activebackground="#4a235a", width=13, height=2,
            command=self._start_pass)
        self.btn_pass_run.pack(side="left", padx=(0,3))
        self.btn_pass_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_pass_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_pass_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#4a235a", fg="white", width=18,
            command=self._group_copy_pass).pack(side="left", padx=(8,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "pass")   # 4×4 그리드 (화면 배치와 동일)

    def _start_pass(self):
        if not self._try_busy_or_queue("패스권", self._start_pass): return
        self._pass_stop = False
        self.btn_pass_run.config(state="disabled", bg="#f39c12", text="⏳ 실행중...")
        self.btn_pass_stop.config(state="normal")
        self._minimize_all()
        threading.Thread(target=self._run_task, args=("패스권", self._run_pass), daemon=True).start()

    def _minimize_pass_ui(self):
        """패스권 실행 시 — 메인은 맨 뒤로, 패스권 창·클로드는 최소화 (클릭이 게임에 닿도록)."""
        self._send_to_back()
        try:
            if self._pass_win and self._pass_win.winfo_exists():
                self._pass_win.iconify()
        except Exception:
            pass
        self._minimize_claude()

    def _restore_pass_ui(self):
        """패스권 실행 종료 후 창 복원 — 패스권 창이 있으면 그걸, 없으면 메인을 올림."""
        try:
            if self._pass_win and self._pass_win.winfo_exists():
                self._pass_win.deiconify(); self._pass_win.lift()
                return
        except Exception:
            pass
        self.deiconify()

    def _run_pass(self, slot_idx=None):
        self._start_pause()
        try:
            self.status.set("2초 후 패스권 실행...")
            self.after(0, self._minimize_all)
            time.sleep(2)
            slots = self.cfg.get("pass_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots) if any(s.get("coords", []))]
            for si, slot in targets:
                if self._pass_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*PASS_CLICKS)
                if not self._wait_mouse_idle("_pass_stop"): return
                for ci, coord in enumerate(coords):
                    if self._pass_stop: break
                    if not coord: continue
                    self.status.set(f"🎫 [{name}] {PASS_LABELS[ci]}...")
                    pyautogui.click(*coord)
                    if ci < len(coords) - 1:
                        time.sleep(random.uniform(PASS_INNER_MIN, PASS_INNER_MAX) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._pass_stop: break
                time.sleep(random.uniform(PASS_SLOT_MIN, PASS_SLOT_MAX))
            self.status.set("✔ 패스권 등록 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_pass_ui)
            try:
                if self.btn_pass_run.winfo_exists():
                    self.btn_pass_run.config(state="normal", bg="#6c3483", text="▶  실행")
                if self.btn_pass_stop.winfo_exists():
                    self.btn_pass_stop.config(state="disabled")
            except Exception:
                pass

    def _reg_pass_click(self, slot_idx, click_idx):
        self._reg_pass_slot_idx  = slot_idx
        self._reg_pass_click_idx = click_idx
        self.status.set(f"3초 후 패스권 #{slot_idx+1} [{PASS_LABELS[click_idx]}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="pass")])

    def on_pass_coord(self, x, y):
        si = self._reg_pass_slot_idx
        ci = self._reg_pass_click_idx
        self.cfg["pass_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 패스권 #{si+1} {PASS_LABELS[ci]} 등록: ({x},{y})")
        self.deiconify()

    def _save_pass_name(self, idx):
        name = self._pass_name_vars[idx].get().strip() or "미등록"
        self.cfg["pass_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_pass(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_pass, args=(idx,), daemon=True).start()

    def _del_pass(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"패스권 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["pass_slots"][idx] = {"name": "미등록", "coords": [None]*PASS_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _pass_scroll_to_group(self, g):
        PASS_GROUP = 4
        total = PASS_SLOTS
        frac = (g * PASS_GROUP) / total
        self._pass_canvas.yview_moveto(frac)

    def _preview_pass(self, idx):
        coords = self.cfg["pass_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg["pass_slots"][idx].get("name", f"#{idx+1:02d}")
        total = PASS_SLOTS

        def rereg(dot_idx):
            self._reg_pass_slot_idx  = idx
            self._reg_pass_click_idx = dot_idx if dot_idx is not None else 0
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="pass"))

        def _save(dot_idx, nx, ny):
            self.cfg["pass_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 패스권 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        def _prev():
            prev_idx = (idx - 1) % total
            self._open_dot_preview_pass(prev_idx)

        def _next():
            next_idx = (idx + 1) % total
            self._open_dot_preview_pass(next_idx)

        self._open_dot_preview_with_nav(
            f"패스권 #{idx+1:02d} {name}  ({idx+1}/{total})",
            dots, rereg_fn=rereg, save_fn=_save,
            prev_fn=_prev, next_fn=_next)

    def _open_dot_preview_pass(self, idx):
        self.after(200, lambda: self._preview_pass(idx))

    def _open_dot_preview_with_nav(self, title, dots, rereg_fn, save_fn, prev_fn, next_fn):
        self.withdraw()
        if self._pass_win and self._pass_win.winfo_exists():
            self._pass_win.withdraw()
        self.after(1000, lambda: _DotPreviewOverlayNav(
            self, title, dots, rereg_fn, save_fn, prev_fn, next_fn))

    def _group_copy_pass_slot(self, idx):
        import copy
        src = self.cfg["pass_slots"][0].get("coords", [])
        dst = self.cfg["pass_slots"][idx]["coords"]
        for j in range(PASS_CLICKS):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 → #{idx+1:02d} 복사 완료")

    def _group_copy_pass(self):
        import copy
        src = self.cfg["pass_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다"); return
        for i in range(1, PASS_SLOTS):
            self.cfg["pass_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{PASS_SLOTS:02d} 전체 복사 완료")

    def _build_sched(self, parent):
        self._sync_sched_click1()   # 창 열 때 과거섬 클릭1을 그대로 반영
        tk.Label(parent, text=f"매일매일 스케줄  ({SCHED_INTERVAL}초 간격)",
                 font=("맑은 고딕", 9, "bold"), fg="#16a085").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._sched_stop = False
        self.btn_sched_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#16a085", fg="white",
            activebackground="#0e6655", width=13, height=2,
            command=self._start_sched)
        self.btn_sched_run.pack(side="left", padx=(0,3))
        self.btn_sched_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_sched_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_sched_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#0e6655", fg="white", width=18,
            command=self._group_copy_sched).pack(side="left", padx=(8,0))
        tk.Button(pr, text="🔒 클릭1=과거섬",
            font=("맑은 고딕", 8), bg="#95a5a6", fg="white", width=14,
            state="disabled").pack(side="left", padx=(4,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "sched")   # 4×4 그리드 (화면 배치와 동일)

    # ── 아이템정리 (스케줄과 동일 구조 + 단축키) ─────────────────────────
    def _open_item_win(self):
        self._open_section_win("_item_win", "🧹 아이템정리", self._build_item, w=470, h=620)

    def _build_item(self, parent):
        tk.Label(parent, text="아이템정리",
                 font=("맑은 고딕", 9, "bold"), fg="#7d6608").pack(anchor="w", padx=4, pady=(4,2))

        pr = tk.Frame(parent); pr.pack(pady=3)
        self._item_stop = False
        self.btn_item_run = tk.Button(pr, text="▶  실행",
            font=("맑은 고딕", 9, "bold"), bg="#7d6608", fg="white",
            activebackground="#5d4c06", width=13, height=2,
            command=self._start_item)
        self.btn_item_run.pack(side="left", padx=(0,3))
        self.btn_item_stop = tk.Button(pr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#7f8c8d", fg="white",
            width=6, height=2,
            command=lambda: setattr(self, "_item_stop", True) or
                            self.status.set("멈추는 중..."),
            state="disabled")
        self.btn_item_stop.pack(side="left")
        tk.Button(pr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#5d4c06", fg="white", width=18,
            command=self._group_copy_item).pack(side="left", padx=(8,0))

        # 단축키 (연속클릭과 동일 방식 — ON/OFF + 키 지정)
        hk = tk.Frame(parent); hk.pack(pady=2)
        self._item_toggle_btn = tk.Button(hk, text="ON" if self._item_on else "OFF",
            font=("맑은 고딕", 9, "bold"),
            bg="#27ae60" if self._item_on else "#7f8c8d", fg="white", width=6,
            command=self._toggle_item)
        self._item_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(hk, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_item_hotkey).pack(side="left", padx=3)
        self._item_hotkey_var = tk.StringVar(value=self._item_hotkey_label())
        tk.Label(hk, textvariable=self._item_hotkey_var,
                 font=("맑은 고딕", 8), fg="#34495e").pack(side="left", padx=(6,0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=4, pady=2)
        self._build_slot_grid(parent, "item")   # 4×4 그리드 (화면 배치와 동일)

    def _item_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('item_hotkey'))}"

    def _toggle_item(self):
        self._item_on = not getattr(self, "_item_on", False)
        self.cfg["item_on"] = self._item_on
        save_cfg(self.cfg)
        if hasattr(self, "_item_toggle_btn"):
            try:
                self._item_toggle_btn.config(text="ON" if self._item_on else "OFF",
                                             bg="#27ae60" if self._item_on else "#7f8c8d")
            except Exception:
                pass
        if self._item_on:
            self.status.set(f"아이템정리 ON — {self._vk_name(self.cfg.get('item_hotkey'))} 누르면 실행")
        else:
            self.status.set("아이템정리 OFF")

    def _assign_item_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["item_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_item_hotkey_var"):
                    self._item_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _item_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 아이템정리 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("item_hotkey")
            if not getattr(self, "_item_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev:
                self.after(0, self._start_item)
            prev = down

    def _reg_item_click(self, slot_idx, click_idx):
        # 클릭1·클릭2 = 일반 클릭, 클릭3 = 쓸어올리기 시작점 — 전부 클릭으로 등록
        self._reg_item_slot_idx  = slot_idx
        self._reg_item_click_idx = click_idx
        what = "쓸어올리기 시작점" if click_idx == 2 else f"클릭{click_idx+1}"
        self.status.set(f"3초 후 아이템정리 #{slot_idx+1} [{what}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="item")])

    def on_item_coord(self, x, y):
        si = self._reg_item_slot_idx
        ci = self._reg_item_click_idx
        self.cfg["item_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 아이템정리 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_item(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"아이템정리 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["item_slots"][idx] = {"name": "미등록", "coords": [None]*SCHED_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_item(self, idx):
        coords = self.cfg["item_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["item_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_item_slot_idx  = idx
            self._reg_item_click_idx = dot_idx if dot_idx is not None else 0
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="item"))

        def _save(dot_idx, nx, ny):
            self.cfg["item_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 아이템정리 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"아이템정리 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _group_copy_item(self):
        import copy
        src = self.cfg["item_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다"); return
        for i in range(1, SCHED_SLOTS):
            self.cfg["item_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set("✔ #01 좌표를 전체 슬롯에 복사 완료")

    def _test_item(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_item, args=(idx,), daemon=True).start()

    def _start_item(self):
        if not self._try_busy_or_queue("아이템정리", self._start_item): return
        self._item_stop = False
        self._set_btn("btn_item_run", state="disabled", bg="#f39c12", text="⏳ 실행중...")
        self._set_btn("btn_item_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("아이템정리", self._run_item), daemon=True).start())

    def _run_item(self, slot_idx=None):
        self._start_pause()
        try:
            self.status.set("2초 후 아이템정리 실행...")
            self.after(0, self._send_to_back)
            time.sleep(2)
            slots = self.cfg.get("item_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
                # 1번부터 번호 순서대로 (2026-08-28 사용자 지시 — 섞지 않는다)
            for si, slot in targets:
                if self._item_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*SCHED_CLICKS)
                if not self._wait_mouse_idle("_item_stop"): return
                if coords[0]:
                    self.status.set(f"🧹 [{name}] 클릭1...")
                    click_at(*coords[0])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._item_stop: break
                if coords[1]:
                    self.status.set(f"🧹 [{name}] 클릭2...")
                    click_at(*coords[1])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._item_stop: break
                if len(coords) > 2 and coords[2]:
                    # 클릭3 = 누른 채 위로 쓸어올리기 (같은 자리에서 2회 반복)
                    sx, sy = coords[2]
                    for rep in range(ITEM_SWIPE_COUNT):
                        if self._item_stop: break
                        self.status.set(f"🧹 [{name}] 위로 쓸어올리기 "
                                        f"{rep+1}/{ITEM_SWIPE_COUNT}... (이때만 커서를 씁니다)")
                        pyautogui.mouseDown(sx, sy)
                        time.sleep(0.09)              # 드래그로 인식될 시간
                        steps = 6                     # 빠른 플릭 — 속도가 높을수록 관성 스크롤이 세짐
                        for st in range(1, steps + 1):
                            pyautogui.moveTo(sx, sy - int(ITEM_SWIPE_DIST * st / steps))
                            time.sleep(0.005)
                        pyautogui.mouseUp(sx, sy - ITEM_SWIPE_DIST)   # 끝에서 바로 놓기 → 관성 스크롤
                        if rep < ITEM_SWIPE_COUNT - 1:
                            time.sleep(random.uniform(0.4, 0.7))   # 다음 쓸어올리기 전 잠깐 대기
                if self._item_stop: break
                time.sleep(4)
            self.status.set("✔ 아이템정리 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_back)
            self._set_btn("btn_item_run", state="normal", bg="#7d6608", text="▶  실행")
            self._set_btn("btn_item_stop", state="disabled")

    def _popup_reg_label(self):
        chk = "✔" if self.cfg.get("purple_popup_checkbox") else "✗"
        cls = "✔" if self.cfg.get("purple_popup_close")    else "✗"
        det = "✔" if self.cfg.get("purple_popup_detect")   else "✗"
        return f"체크박스:{chk}  닫기:{cls}  감지:{det}"

    def _reg_popup_checkbox(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [체크박스] 위에 올려두세요 — 자동 캡처")
        self.after(3000, self._capture_popup_checkbox)

    def _capture_popup_checkbox(self):
        x, y = pyautogui.position()
        self.cfg["purple_popup_checkbox"] = [x, y]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 팝업 체크박스 등록: ({x},{y})")

    def _reg_popup_close(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [✕ 닫기버튼] 위에 올려두세요 — 자동 캡처")
        self.after(3000, self._capture_popup_close)

    def _capture_popup_close(self):
        x, y = pyautogui.position()
        self.cfg["purple_popup_close"] = [x, y]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 팝업 닫기버튼 등록: ({x},{y})")

    def _reg_popup_detect(self):
        self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
        self.status.set("3초 후 마우스를 [팝업 X버튼 주변 빈 배경] 위에 올려두세요 — 픽셀 색상 저장")
        self.after(3000, self._capture_popup_detect)

    def _capture_popup_detect(self):
        from PIL import ImageGrab
        x, y = pyautogui.position()
        shot = ImageGrab.grab(all_screens=False)
        px   = shot.getpixel((x, y))
        self.cfg["purple_popup_detect"] = [x, y]
        self.cfg["purple_popup_color"]  = [px[0], px[1], px[2]]
        save_cfg(self.cfg)
        self._popup_status_var.set(self._popup_reg_label())
        self.status.set(f"✔ 감지 픽셀 등록: ({x},{y}) RGB=({px[0]},{px[1]},{px[2]})")

    def _maximize_purple(self):
        win = find_purple()
        if win:
            try: win.activate(); win.maximize()
            except: pass

    def _open_dot_preview(self, title, dots, rereg_fn, save_fn=None, dot_r=3):
        self.withdraw()
        self.after(1000, lambda: _DotPreviewOverlay(self, title, dots, rereg_fn, save_fn, dot_r))

    def _preview_label_coord(self, key):
        c = self.cfg.get(key)
        dots = [(c[0], c[1], "1")] if c else []
        self._open_dot_preview(LABELS[key], dots, lambda _: self._reg_coord(key))

    def _preview_slot(self, idx):
        pair = self.cfg["click_slots"][idx]
        c1 = pair[0] if len(pair) > 0 else None
        c2 = pair[1] if len(pair) > 1 else None
        c3 = pair[2] if idx == 4 and len(pair) > 2 else None
        dots = []
        if c1: dots.append((c1[0], c1[1], "1"))
        if c2: dots.append((c2[0], c2[1], "2"))
        if c3: dots.append((c3[0], c3[1], "3"))

        def _save(dot_idx, nx, ny):
            self.cfg["click_slots"][idx][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        def _rereg(dot_idx):
            if dot_idx is None:
                self._reg_slot(idx)
            else:
                self._reg_slot_step(idx, dot_idx)

        self._open_dot_preview(f"#{idx+1:02d} 클릭슬롯", dots,
                               rereg_fn=_rereg, save_fn=_save)

    def _preview_char(self, idx):
        btns = self.cfg.get("char_btns", [])
        c = btns[idx] if idx < len(btns) else None
        dots = [(c[0], c[1], str(idx+1))] if c else []
        def _rereg():
            self._char_rereg_idx = idx
            self.status.set(f"3초 후 캐릭터 #{idx+1} 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                      CoordOverlay(self, mode="char_rereg")])
        self._open_dot_preview(f"캐릭터 #{idx+1:02d}", dots, _rereg)

    def on_char_rereg_coord(self, x, y):
        idx = self._char_rereg_idx
        btns = self.cfg.get("char_btns", [])
        if idx < len(btns):
            btns[idx] = [x, y]
            self.cfg["char_btns"] = btns
            save_cfg(self.cfg)
            self._refresh_ui()
            self.status.set(f"✔ 캐릭터 #{idx+1} 재등록: ({x},{y})")
        self.deiconify()

    def _del_char_btn(self, idx):
        btns = self.cfg.get("char_btns", [])
        if idx < len(btns):
            btns.pop(idx)
            self.cfg["char_btns"] = btns
            save_cfg(self.cfg)
            self._refresh_ui()

    def _sync_sched_click1(self):
        """매일매일 스케줄 클릭1 = 과거의말하는섬 클릭1 (항상 동기화)"""
        changed = False
        for i in range(min(PAST_SLOTS, SCHED_SLOTS)):
            src = self.cfg["past_slots"][i]["coords"][0]
            if self.cfg["sched_slots"][i]["coords"][0] != src:
                self.cfg["sched_slots"][i]["coords"][0] = src
                changed = True
        if changed:
            save_cfg(self.cfg)

    def _build_sec_row(self):
        """섹션 버튼 행 전체 재빌드 (고정 섹션 + 과거섬/던전 슬롯)."""
        for w in self._sec_row.winfo_children():
            w.destroy()

        # ■ 전체멈춤 / ⏰ 반복 — 이 행의 맨 왼쪽 (일반던전충전 좌측 라인에 맞춤)
        self._stop_col = tk.Frame(self._sec_row)
        self._stop_col.pack(side="left", padx=(getattr(self, "_star_pad", 0), 6))
        self.btn_stop = tk.Button(self._stop_col, text="■ 전체" + chr(10) + "멈춤",
            font=("맑은 고딕", 9, "bold"), bg="#7f8c8d", fg="white",
            activebackground="#5d6d7e", width=6, height=2, command=self._stop)
        self.btn_stop.pack(side="left")
        self.btn_rep = tk.Button(self._stop_col, text="⏰ 반복" + chr(10) + "ON",
            font=("맑은 고딕", 9, "bold"), bg="#27ae60", fg="white",
            activebackground="#1e8449", width=6, height=2,
            command=self._rep_stop_click)
        self.btn_rep.pack(side="left", padx=(3, 0))
        self.after(300, self._refresh_rep_btn)

        # ★ 과거섬 하루 패스 버튼 — 누르면 다음 새벽 실행 건너뜀, 다시 누르면 취소, 다음날 자동 재개
        self._past_skip_btn = tk.Button(self._sec_row, text="★ 과거섬\n패스!",
            font=("맑은 고딕", 9, "bold"), width=7, height=2,
            command=self._toggle_past_skip)
        self._past_skip_btn.pack(side="left", padx=(0, 4))
        self._refresh_past_skip_btn()

        fixed = [
            ("⚙ 좌표 등록", "#2c3e50", self._open_settings_win,                         None,      None),
            ("귀환주문서",   "#c0392b", lambda: self._open_past_slot(4),                 "#922b21", lambda: self._run_island_slot(4)),
            ("카매사오기",   "#1a5276", lambda: self._open_past_slot(5),                 "#154360", lambda: self._run_island_slot(5)),
            ("📬 우편함",    "#2471a3", self._open_mail_win,     "#1a5276", self._start_mail),
            ("🏝 과거섬",    "#c0392b", self._open_past_win,     "#922b21", self._start_past),
            ("주말던전끄기", "#5d6d7e", self._open_wdoff_win,    "#34495e", self._start_wdoff),
            ("🏹 사냥",      "#27ae60", self._open_hunt_win,     "#1e8449", self._start_hunt),
            ("💰 다야OCR",   "#27ae60", self._open_ocr,          "#1e8449", self._open_ocr_scan),
            ("🔆 절전해제",  "#7d3c98", self._open_seq_win,      "#5b2c6f", self._start_seq),
            ("🌙 절전모드",  "#1f618d", self._open_slp_win,      "#154360", self._start_slp),
            ("🧪 물약색",   "#8e44ad", self._open_potion_win,   "#6c3483", self._potion_check),
            ("📜 주문서",    "#2471a3", self._open_scroll_win,   "#1a5276", self._scroll_check),
        ]
        for text, color, cmd, run_color, run_cmd in fixed:
            grp = tk.Frame(self._sec_row); grp.pack(side="left", padx=2)
            tk.Button(grp, text=text, font=("맑은 고딕", 9, "bold"),
                      bg=color, fg="white", width=9, height=2,
                      command=cmd).pack(side="top")
            if run_cmd:
                tk.Button(grp, text="▶ 실행", font=("맑은 고딕", 8, "bold"),
                          bg=run_color, fg="white", width=9, height=1, pady=5,
                          command=run_cmd).pack(side="top", pady=(1, 0))
            else:
                tk.Frame(grp, height=30).pack(side="top")

        # 구분선
        tk.Frame(self._sec_row, width=2, bg="#bbb").pack(side="left", fill="y", padx=4)

        # 과거섬 슬롯 4개 고정 (이름 하드코딩) — 위=창 열기, 아래=▶ 실행
        _ISLAND_NAMES  = ["오만의탑", "악몽의섬", "잊혀진섬", "에카"]
        _ISLAND_COLORS = ["#8e44ad", "#2471a3", "#16a085", "#d35400"]
        for i, label in enumerate(_ISLAND_NAMES):
            grp = tk.Frame(self._sec_row); grp.pack(side="left", padx=2)
            tk.Button(grp, text=label, font=("맑은 고딕", 9, "bold"),
                      bg=_ISLAND_COLORS[i], fg="white", width=9, height=2,
                      command=lambda x=i: self._open_past_slot(x)).pack(side="top")
            tk.Button(grp, text="▶ 실행", font=("맑은 고딕", 8, "bold"),
                      bg=_ISLAND_COLORS[i], fg="white", width=9, height=1, pady=5,
                      command=lambda x=i: self._run_island_slot(x)
                      ).pack(side="top", pady=(1, 0))

        # ★ 정렬용 가변 여백 (오른쪽을 늘려 행 전체를 왼쪽으로 밀기)
        self._secrow_pad = tk.Frame(self._sec_row, width=getattr(self, "_secrow_pad_w", 0), height=1)
        self._secrow_pad.pack(side="left")
        # 버튼 행 너비에 맞게 창 자동 조정
        self.after(50, self._fit_width_to_sec_row)

    def _fit_width_to_sec_row(self):
        self._fit_main_height()

    def _build_banner(self):
        """상단 배너 — 다크 + 골드 (리니지M 느낌). 위젯 기반이라 항상 표시된다."""
        DARK, GOLD, GOLD2 = "#141210", "#e6c66a", "#8a6d2f"
        wrap = tk.Frame(self, bg=DARK)
        wrap.pack(fill="x", pady=(0, 3))
        tk.Frame(wrap, height=2, bg=GOLD).pack(fill="x")          # 위 골드 라인
        body = tk.Frame(wrap, bg=DARK); body.pack(fill="x", pady=3)
        # 좌측 문양
        tk.Label(body, text="◆", font=("맑은 고딕", 10), bg=DARK, fg=GOLD2).pack(side="left", padx=(14, 2))
        tk.Label(body, text="🌙", font=("맑은 고딕", 15), bg=DARK, fg=GOLD).pack(side="left")
        tk.Label(body, text="◆", font=("맑은 고딕", 10), bg=DARK, fg=GOLD2).pack(side="left", padx=2)
        # 우측 문양
        tk.Label(body, text="◆", font=("맑은 고딕", 10), bg=DARK, fg=GOLD2).pack(side="right", padx=(2, 14))
        tk.Label(body, text="🌙", font=("맑은 고딕", 15), bg=DARK, fg=GOLD).pack(side="right")
        tk.Label(body, text="◆", font=("맑은 고딕", 10), bg=DARK, fg=GOLD2).pack(side="right", padx=2)
        # 가운데 제목
        center = tk.Frame(body, bg=DARK); center.pack(expand=True)
        tk.Label(center, text="⚔", font=("맑은 고딕", 15), bg=DARK, fg=GOLD2).pack(side="left", padx=(0, 8))
        tk.Label(center, text="대균아!!  열심히 살자!!  화이팅!", font=("맑은 고딕", 18, "bold"),
                 bg=DARK, fg=GOLD).pack(side="left")
        tk.Label(center, text="⚔", font=("맑은 고딕", 15), bg=DARK, fg=GOLD2).pack(side="left", padx=(8, 0))
        tk.Frame(wrap, height=2, bg=GOLD2).pack(fill="x")         # 아래 골드 라인
        # 상태 표시줄 색도 배너와 어울리게 (아래에서 만들어지므로 여기선 색만 기억)
        self._theme = {"dark": DARK, "gold": GOLD, "gold2": GOLD2}

    def _build_slot_quick_btns(self):
        """메인 런처 다야 옆 섬/던전 슬롯 빠른 실행 버튼 (재호출로 갱신)."""
        for w in self._slot_inner.winfo_children():
            w.destroy()
        self._slot_quick_btns = []

        past_slots    = self.cfg.get("past_slots",    [])
        dungeon_slots = self.cfg.get("dungeon_slots", [])

        # 과거섬 슬롯 — 행으로 배치
        for i, slot in enumerate(past_slots):
            name      = slot.get("name", "").strip() or f"섬#{i+1}"
            coords    = slot.get("coords", [])
            has_coord = any(c for c in coords)
            btn = tk.Button(
                self._slot_inner,
                text=name,
                font=("맑은 고딕", 8, "bold"),
                bg="#c0392b" if has_coord else "#95a5a6",
                fg="white", width=9, height=1,
                state="normal" if has_coord else "disabled",
                command=lambda x=i: threading.Thread(
                    target=self._run_past, args=(x,), daemon=True).start()
            )
            btn.pack(fill="x", pady=1)
            self._slot_quick_btns.append(btn)

        # 던전 슬롯
        for i, slot in enumerate(dungeon_slots):
            name      = slot.get("name", "").strip() or f"던전#{i+1}"
            coords    = slot.get("coords", [])
            has_coord = any(c for c in coords)
            btn = tk.Button(
                self._slot_inner,
                text=name,
                font=("맑은 고딕", 8, "bold"),
                bg="#e67e22" if has_coord else "#95a5a6",
                fg="white", width=9, height=1,
                state="normal" if has_coord else "disabled",
                command=lambda x=i: threading.Thread(
                    target=self._run_dungeon, args=(x,), daemon=True).start()
            )
            btn.pack(fill="x", pady=1)
            self._slot_quick_btns.append(btn)

    def _refresh_ui(self):
        # 스케줄 클릭1 = 과거섬 클릭1 : 표시 갱신 전에 항상 미러링(과거섬 편집이 그대로 반영됨)
        self._sync_sched_click1()
        # debounce: 100ms 내 중복 호출 무시
        now = time.time()
        if hasattr(self, "_last_refresh") and now - self._last_refresh < 0.1:
            return
        self._last_refresh = now
        # 4×4 그리드·인형탐험은 항상 즉시 갱신 (좌표등록 창이 안 열려 있어도!)
        try:
            self._refresh_slot_grids()
        except Exception:
            pass
        try:
            self._refresh_doll_display()
        except Exception:
            pass
        if not hasattr(self, "_coord_vars"):
            return
        for key, var in self._coord_vars.items():
            c = self.cfg.get(key)
            var.set(f"({c[0]},{c[1]})" if c else "미등록")
        # 캐릭터 버튼 동적 목록 갱신
        for w in self._char_rows_frame.winfo_children():
            w.destroy()
        btns = self.cfg.get("char_btns", [])
        for i, c in enumerate(btns):
            r = tk.Frame(self._char_rows_frame); r.pack(fill="x", pady=0)
            tk.Label(r, text=f"#{i+1:02d}", font=("맑은 고딕", 7), width=3).pack(side="left")
            coord_txt = f"({c[0]},{c[1]})" if c else "미등록"
            tk.Label(r, text=coord_txt, font=("맑은 고딕", 7), fg="gray", width=14).pack(side="left")
            tk.Button(r, text="👁", font=("맑은 고딕", 6), width=2,
                      command=lambda x=i: self._preview_char(x)).pack(side="right", padx=1)
            tk.Button(r, text="×", font=("맑은 고딕", 6), fg="red", width=2,
                      command=lambda x=i: self._del_char_btn(x)).pack(side="right", padx=1)
        n = len(btns)
        self._char_count_var.set(f"({n}개)" if n else "(미등록)")
        for i, var in enumerate(self._slot_vars):
            pair = self.cfg["click_slots"][i]
            c1 = pair[0] if len(pair) > 0 else None
            c2 = pair[1] if len(pair) > 1 else None
            c3 = pair[2] if i == 4 and len(pair) > 2 else None
            if i == 4:
                if c1 and c2 and c3:
                    var.set(f"✔ {c1} / {c2} / {c3}")
                elif c1 and c2:
                    var.set("클릭1✔ 클릭2✔ 클릭3 미등록")
                elif c1:
                    var.set("클릭1✔  클릭2 미등록")
                else:
                    var.set("미등록")
            else:
                if c1 and c2:
                    var.set(f"✔ {c1} / {c2}")
                elif c1:
                    var.set("클릭1✔  클릭2 미등록")
                else:
                    var.set("미등록")
        if hasattr(self, "_hunt_name_vars") and self._hunt_name_vars:
            for i in range(HUNT_SLOTS):
                h = self.cfg["hunt_slots"][i]
                self._hunt_name_vars[i].set(h.get("name", "미등록"))
                coords = h.get("coords", [None] * HUNT_CLICKS)
                for j in range(HUNT_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._hunt_click_vars[i][j].set("✔" if c else "✗")
                    self._hunt_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._hunt_assign_btns):
                    aw = h.get("assigned_window")
                    self._hunt_assign_btns[i].config(
                        text="✔지정" if aw else "지정",
                        bg="#27ae60" if aw else "#8e44ad"
                    )
                if hasattr(self, "_hunt_enable_btns") and i < len(self._hunt_enable_btns):
                    en = h.get("enabled", True)
                    self._hunt_enable_btns[i].config(text="ON" if en else "OFF",
                                                     bg="#27ae60" if en else "#95a5a6")
                if i < len(self._hunt_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._hunt_detail_frames) and self._hunt_detail_frames[i].winfo_ismapped()) else "▾"
                    self._hunt_coord_sv[i].set(f"좌표 {reg}/{HUNT_CLICKS} {arrow}")
        # mail 슬롯
        if hasattr(self, "_mail_name_vars") and self._mail_name_vars:
            for i in range(MAIL_SLOTS):
                m = self.cfg["mail_slots"][i]
                self._mail_name_vars[i].set(m.get("name", "미등록"))
                coords = m.get("coords", [None]*MAIL_CLICKS)
                for j in range(MAIL_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._mail_click_vars[i][j].set("✔" if c else "✗")
                    self._mail_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._mail_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._mail_detail_frames) and self._mail_detail_frames[i].winfo_ismapped()) else "▾"
                    self._mail_coord_sv[i].set(f"좌표 {reg}/{MAIL_CLICKS} {arrow}")
        # past 슬롯
        if hasattr(self, "_past_name_vars") and self._past_name_vars:
            for i in range(PAST_SLOTS):
                p = self.cfg["past_slots"][i]
                self._past_name_vars[i].set(p.get("name", "미등록"))
                coords = p.get("coords", [None]*PAST_CLICKS)
                for j in range(PAST_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._past_click_vars[i][j].set("✔" if c else "✗")
                    self._past_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._past_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._past_detail_frames) and self._past_detail_frames[i].winfo_ismapped()) else "▾"
                    self._past_coord_sv[i].set(f"좌표 {reg}/{PAST_CLICKS} {arrow}")
        # pass 슬롯
        if hasattr(self, "_pass_name_vars") and self._pass_name_vars:
            for i in range(PASS_SLOTS):
                p = self.cfg["pass_slots"][i]
                self._pass_name_vars[i].set(p.get("name", "미등록"))
                coords = p.get("coords", [None]*PASS_CLICKS)
                for j in range(PASS_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._pass_click_vars[i][j].set("✔" if c else "✗")
                    self._pass_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )
                if i < len(self._pass_coord_sv):
                    reg = sum(1 for c in coords if c)
                    arrow = "▴" if (i < len(self._pass_detail_frames) and self._pass_detail_frames[i].winfo_ismapped()) else "▾"
                    self._pass_coord_sv[i].set(f"좌표 {reg}/{PASS_CLICKS} {arrow}")
        # 섹션 버튼 행 슬롯 갱신
        if hasattr(self, "_sec_row") and self._sec_row.winfo_exists():
            self._build_sec_row()
        # 4×4 슬롯 그리드 갱신 (과거섬·우편함·던전·스케줄·사냥·패스권)
        try:
            self._refresh_slot_grids()
        except Exception:
            pass
        # sched 슬롯 (창이 열려있을 때만)
        if hasattr(self, "_sched_name_vars") and self._sched_name_vars:
            for i in range(SCHED_SLOTS):
                s = self.cfg["sched_slots"][i]
                self._sched_name_vars[i].set(s.get("name", "미등록"))
                coords = s.get("coords", [None]*SCHED_CLICKS)
                for j in range(SCHED_CLICKS):
                    c = coords[j] if j < len(coords) else None
                    self._sched_click_vars[i][j].set("✔" if c else "✗")
                    self._sched_click_btns[i][j].config(
                        fg="white" if c else "#aaa",
                        bg="#27ae60" if c else "#7f8c8d"
                    )

    def _wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._stop_flag: return False
            time.sleep(0.1)
        return True

    # 커서를 쓰지 않는(메시지로 클릭하는) 런처 — 사용자가 마우스를 써도 안 기다린다
    # 커서를 쓰지 않는(메시지로 클릭하는) 런처 — 사용자가 마우스를 써도 기다리지 않는다
    NO_WAIT_MOUSE = ("dragon", "knight", "sched", "item", "dc", "doll", "dungeon",
                     "dollchk", "relic", "fish")

    def _user_busy(self, sec=0.8):
        """사람이 방금 마우스를 만졌는가 (움직임뿐 아니라 '클릭'까지 본다).
        저수준 훅으로 물리 입력만 골라 보므로, 우리가 보낸 클릭은 세지 않는다."""
        try:
            import precise_click as _pc
            if not _pc.start_input_watch():
                return None                     # 감시를 못 켜면 예전 방식으로
            return _pc.button_down() or _pc.idle_seconds() < sec
        except Exception:
            return None

    def _wait_user_free(self, stop_flag_name, sec=0.8, limit=30.0):
        """사람이 마우스를 놓을 때까지 잠깐 기다린다 (클릭 겹침 = 팅김 방지).
        감시를 못 켜면 아무것도 하지 않고 통과한다."""
        t0 = time.time()
        shown = False
        while True:
            if getattr(self, stop_flag_name, False):
                return False
            b = self._user_busy(sec)
            if b is None:
                return True                     # 훅 실패 — 기존 로직에 맡긴다
            if not b:
                if shown:
                    self.after(0, lambda: self.status.set("▶ 마우스 놓음 — 이어서 진행"))
                return True
            if not shown:
                self.after(0, lambda: self.status.set(
                    "⏸ 마우스 쓰는 중 — 손 떼면 바로 이어서 클릭합니다"))
                shown = True
            if time.time() - t0 > limit:        # 너무 오래 붙잡고 있지 않게
                return True
            time.sleep(0.06)

    def _wait_mouse_idle(self, stop_flag_name, idle_sec=1.5, fkey=None):
        """마우스를 쓰는 중이면 대기. 안 쓰면 즉시 True.
        훅이 켜지면 '클릭까지' 감지하고, 안 되면 예전(위치 비교) 방식으로."""
        b = self._user_busy(idle_sec)
        if b is not None:
            return self._wait_user_free(stop_flag_name, idle_sec)
        CHECK = 0.1
        prev = pyautogui.position()
        # 움직임이 없으면 즉시 통과
        time.sleep(CHECK)
        cur = pyautogui.position()
        if cur == prev:
            return not getattr(self, stop_flag_name, False)
        # 움직임 감지됨 → idle_sec초 동안 안 움직일 때까지 대기
        self.after(0, lambda: self.status.set(f"⏸ 마우스 움직임 감지 — {int(idle_sec)}초 정지 후 재개..."))
        last_move = time.time()
        prev = cur
        while True:
            if getattr(self, stop_flag_name, False):
                return False
            time.sleep(CHECK)
            cur = pyautogui.position()
            if cur != prev:
                last_move = time.time()
                prev = cur
            elif time.time() - last_move >= idle_sec:
                return True

    def _click_wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._click_stop: return False
            time.sleep(0.1)
        return True

    def _hunt_wait(self, sec):
        for _ in range(int(sec * 10)):
            if self._hunt_stop: return False
            time.sleep(0.1)
        return True

    # ── 좌표 등록 ─────────────────────────────────────────────────────
    def _preprocess_ocr_img(self, img):
        """OCR용 이미지 전처리 — 단순 확대만"""
        from PIL import Image, ImageOps
        img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
        img = ImageOps.expand(img, border=20, fill=(0, 0, 0))
        return img.convert("RGB")

    def _save_ocr_as_target_id(self):
        """테스트 OCR 결과를 사용할 아이디로 저장"""
        area = self.cfg.get("profile_id_area")
        if not area:
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        def _do():
            try:
                if self.cfg.get("profile_reveal_btn"):
                    pyautogui.click(*self.cfg["profile_reveal_btn"])
                    time.sleep(1)
                ocr_id = self._ocr_profile_id()
                if ocr_id:
                    self.cfg["profile_target_id"] = ocr_id
                    save_cfg(self.cfg)
                    self.after(0, lambda: [self._profile_target_var.set(ocr_id),
                                           self.status.set(f"✔ 아이디 저장 완료: '{ocr_id}'")])
                else:
                    self.after(0, lambda: self.status.set("OCR 결과가 없습니다. 영역을 다시 확인하세요."))
            except Exception as e:
                self.after(0, lambda err=e: self.status.set(f"오류: {err}"))
        self.status.set("OCR로 아이디 읽는 중...")
        threading.Thread(target=_do, daemon=True).start()

    def _test_profile_ocr(self):
        """profile_reveal_btn 클릭 후 영역 캡처해서 이미지 열기"""
        area = self.cfg.get("profile_id_area")
        # 기준이미지(드래그 영역) 모드는 아이디 표시영역이 없어도 동작
        if not area and not os.path.exists(self._profile_ref_path()):
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        def _do():
            try:
                # 기준이미지 모드면 이미지 대조 결과를 표시 (실제 판별과 동일 경로)
                if os.path.exists(self._profile_ref_path()):
                    matched, label, sim = self._is_target_account()
                    self.after(0, self._raise_main)
                    self.after(0, lambda m=matched, l=label: self.status.set(
                        f"{l} → {'✔ 지정계정 일치' if m else '✘ 불일치'} (기준: 90% 이상)"))
                    return
                # 캡처는 런처가 최소화된 상태에서 먼저 (런처 창이 영역을 가리지 않도록)
                # 실제 4시 판별과 동일한 창 위치 보정 경로 사용
                img = self._grab_profile_img()
                # 캡처 후 메인런처를 복원·앞으로 올려 상태바 결과를 볼 수 있게 함
                self.after(0, self._raise_main)
                self.after(0, lambda: self.status.set("OCR 분석 중..."))
                ocr_id = self._ocr_img_text(img)
                target = (self.cfg.get("profile_target_id") or "").strip()
                if target and ocr_id:
                    ratio = int(self._profile_match_ratio(ocr_id) * 100)
                    self.after(0, lambda o=ocr_id, r=ratio: self.status.set(
                        f"OCR: '{o}' / 목표: '{target}' → 일치율 {r}%"))
                else:
                    self.after(0, lambda o=ocr_id: self.status.set(
                        f"OCR 결과: '{o}' (저장된 아이디 없음)"))
            except Exception as e:
                import traceback
                try:
                    with open(os.path.join(LOGS_DIR, "ocr_error.txt"), "w", encoding="utf-8") as f:
                        f.write(traceback.format_exc())
                except Exception:
                    pass
                self.after(0, lambda err=e: self.status.set(f"오류: {err} (ocr_error.txt 확인)"))
        self.status.set("캡처 중... (첫 실행 시 30초 소요)")
        threading.Thread(target=_do, daemon=True).start()

    def _reg_profile_id_area(self):
        self.status.set("3초 후 퍼플 아이디가 표시되는 영역을 드래그하세요!")
        self.after(3000, lambda: [self.withdraw(), self.after(200, self._open_profile_area_overlay)])

    def _open_profile_area_overlay(self):
        _ProfileAreaOverlay(self)

    def _save_profile_ref_pixel(self):
        """난봉꾼 계정 화면에서 아이디 영역 픽셀 기준값 저장"""
        area = self.cfg.get("profile_id_area")
        if not area:
            self.status.set("아이디 표시 영역을 먼저 등록하세요."); return
        from PIL import ImageGrab
        import numpy as np
        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
        arr = np.array(img).flatten().tolist()
        self.cfg["profile_ref_pixel"] = arr
        save_cfg(self.cfg)
        self._profile_pix_var.set("저장됨")
        self.status.set("✔ 난봉꾼 계정 기준 픽셀 저장 완료")

    def _test_profile_pixel(self):
        """현재 화면과 기준 픽셀 비교 테스트"""
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            self.status.set("기준 픽셀 또는 영역이 미등록입니다."); return
        from PIL import ImageGrab
        import numpy as np
        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
        arr = np.array(img).flatten().tolist()
        n = min(len(ref), len(arr))
        diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
        matched = diff < 30
        self.status.set(f"픽셀 차이: {diff:.1f} → {'✔ 난봉꾼 계정 일치' if matched else '✗ 다른 계정'}")

    def _is_scroll_account_at(self, hwnd):
        """hwnd 창 위치 기준으로 profile_id_area 좌표 보정 후 픽셀 비교"""
        import win32gui
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            return False
        try:
            from PIL import ImageGrab
            import numpy as np
            wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
            ax = area["x"] + wx
            ay = area["y"] + wy
            img = ImageGrab.grab(bbox=(ax, ay, ax+area["w"], ay+area["h"]), all_screens=True)
            arr = np.array(img).flatten().tolist()
            n = min(len(ref), len(arr))
            diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
            return diff < 30
        except:
            return False

    def _is_scroll_account(self):
        """현재 화면이 난봉꾼 계정인지 픽셀 비교로 확인"""
        ref = self.cfg.get("profile_ref_pixel")
        area = self.cfg.get("profile_id_area")
        if not ref or not area:
            return False
        try:
            from PIL import ImageGrab
            import numpy as np
            ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            arr = np.array(img).flatten().tolist()
            n = min(len(ref), len(arr))
            diff = sum(abs(ref[i] - arr[i]) for i in range(n)) / n
            return diff < 30
        except:
            return False

    # ── 아이디 OCR 기반 계정 판별 (창 위치 보정 → 다른 컴퓨터에서도 동작) ──
    def _profile_area_bbox(self, hwnd=None):
        """아이디 영역의 실제 캡처 bbox 계산.
        등록 시 퍼플 창 위치(profile_id_area_win)가 저장돼 있으면 현재 퍼플 창
        위치와의 차이만큼 보정한다 → 창이 어디 떠 있든/다른 컴퓨터에서도 정확.
        저장된 창위치가 없으면 기존 절대좌표를 그대로 사용(하위호환)."""
        area = self.cfg.get("profile_id_area")
        if not area:
            return None
        ax, ay = area["x"], area["y"]
        reg_win = self.cfg.get("profile_id_area_win")
        if reg_win:
            cur = None
            if hwnd:
                try:
                    import win32gui
                    wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
                    cur = (wx, wy)
                except Exception:
                    cur = None
            if cur is None:
                try:
                    w = find_purple()
                    if w:
                        cur = (w.left, w.top)
                except Exception:
                    cur = None
            if cur:
                ax += cur[0] - reg_win[0]
                ay += cur[1] - reg_win[1]
        return (ax, ay, area["w"], area["h"])

    def _grab_profile_img(self, hwnd=None):
        """아이디 영역 캡처 + 전처리 후 이미지 반환(실패 시 None). 디버그 이미지 저장."""
        bbox = self._profile_area_bbox(hwnd)
        if not bbox:
            return None
        try:
            from PIL import ImageGrab
            ax, ay, aw, ah = bbox
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            try:
                img.save(os.path.join(LOGS_DIR, "profile_ocr_debug.png"))
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _ocr_img_text(self, img):
        if img is None:
            return ""
        try:
            import numpy as np
            results = _get_ocr_reader().readtext(np.array(img), detail=0, paragraph=False)
            return "".join(results).strip()
        except Exception:
            return ""

    def _ocr_profile_id(self, hwnd=None):
        """아이디 영역을 OCR로 읽어 문자열 반환."""
        return self._ocr_img_text(self._grab_profile_img(hwnd))

    def _profile_match_ratio(self, ocr_id):
        target = (self.cfg.get("profile_target_id") or "").strip()
        if not target or not ocr_id:
            return 0.0
        match = sum(1 for a, b in zip(ocr_id, target) if a == b)
        return match / max(len(target), 1)

    def _profile_ref_path(self):
        return os.path.join(LOCAL_DATA, "profile_ref.png")

    def _profile_ref_region_path(self):
        return os.path.join(LOCAL_DATA, "profile_ref_region.json")

    def _grab_ref_img(self, hwnd=None):
        """기준 대조용 캡처 — 드래그로 등록한 전용 영역이 있으면 그 영역을,
        없으면 기존 아이디 영역(_grab_profile_img)을 사용."""
        p = self._profile_ref_region_path()
        if not os.path.exists(p):
            return self._grab_profile_img(hwnd)
        try:
            with open(p, encoding="utf-8") as f:
                reg = json.load(f)
            ax, ay = reg["x"], reg["y"]
            # 등록 당시 퍼플 창 위치 대비 현재 위치 차이만큼 보정
            if reg.get("win"):
                cur = None
                if hwnd:
                    try:
                        import win32gui
                        wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
                        cur = (wx, wy)
                    except Exception:
                        cur = None
                if cur is None:
                    try:
                        w = find_purple()
                        if w:
                            cur = (w.left, w.top)
                    except Exception:
                        cur = None
                if cur:
                    ax += cur[0] - reg["win"][0]
                    ay += cur[1] - reg["win"][1]
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(ax, ay, ax+reg["w"], ay+reg["h"]), all_screens=True)
            try:
                img.save(os.path.join(LOGS_DIR, "profile_ref_debug.png"))
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _finish_ref_capture(self, region):
        """드래그 영역 확정 후 — 오버레이가 사라진 다음 그 영역을 캡처해 기준으로 저장."""
        def _do():
            try:
                time.sleep(0.4)   # 오버레이(반투명) 잔상이 사라진 뒤 캡처
                from PIL import ImageGrab
                x, y, w, h = region["x"], region["y"], region["w"], region["h"]
                img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
                with open(self._profile_ref_region_path(), "w", encoding="utf-8") as f:
                    json.dump(region, f)
                img.save(self._profile_ref_path())
                self.after(0, self._raise_main)
                self.after(0, lambda: self.status.set(
                    "✔ 기준 영역·이미지 등록 완료 — 이 영역으로 이미지 대조합니다 (지정계정 상태에서 등록했는지 확인!)"))
            except Exception as e:
                self.after(0, lambda err=e: self.status.set(f"기준이미지 등록 오류: {err}"))
        threading.Thread(target=_do, daemon=True).start()

    def _reg_profile_ref(self):
        """기준이미지 등록 — 캡처 영역을 직접 드래그로 지정하고, 그 영역을 기준으로 저장.
        계정마다 확실히 다르게 보이는 부분(아이디 글자·프로필 사진 등)을 지정할수록 정확.
        (지정계정으로 로그인된 상태에서 누를 것)"""
        def _do():
            try:
                if self.cfg.get("profile_reveal_btn"):
                    pyautogui.click(*self.cfg["profile_reveal_btn"])
                    time.sleep(2)
            except Exception:
                pass
            self.after(0, lambda: _ProfileRefOverlay(self))
        self._send_to_back()   # 게임 화면이 보이게 런처를 맨 뒤로
        self.status.set("기준으로 쓸 영역을 드래그하세요...")
        threading.Thread(target=_do, daemon=True).start()

    def _img_similarity(self, cur_img):
        """현재 캡처와 기준이미지의 유사도(0~1). 몇 픽셀 어긋나도 견디게 템플릿 매칭."""
        try:
            import numpy as np, cv2
            from PIL import Image
            ref = Image.open(self._profile_ref_path()).convert("L")
            cur = cur_img.convert("L")
            r = np.array(ref); c = np.array(cur)
            # 기준을 안쪽으로 잘라 템플릿으로 사용 → 창 위치 미세 오차 흡수
            m = 12
            if r.shape[0] > m*2+8 and r.shape[1] > m*2+8:
                r = r[m:-m, m:-m]
            if c.shape[0] < r.shape[0] or c.shape[1] < r.shape[1]:
                return 0.0
            # 공통 배경(UI)이 유사도를 부풀리므로 이진화 후, 템플릿매칭으로 위치만 맞추고
            # '글자 픽셀'의 실제 일치율을 점수로 사용 — 다른 계정이면 크게 떨어진다
            # (같은계정 0.99+, 3글자만 달라도 ~0.56, 전부 다르면 ~0.28 검증됨)
            _, rb = cv2.threshold(r, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, cb = cv2.threshold(c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            res = cv2.matchTemplate(cb, rb, cv2.TM_CCOEFF_NORMED)
            _, _, _, loc = cv2.minMaxLoc(res)
            x, y = loc
            crop = cb[y:y+rb.shape[0], x:x+rb.shape[1]]
            fg = 0 if (rb == 0).mean() < 0.5 else 255      # 글자(소수) 픽셀 값
            mask = (rb == fg) | (crop == fg)               # 글자 픽셀 합집합
            if not mask.any():
                return float(res.max())
            return float(1.0 - (crop != rb)[mask].mean())  # 글자 픽셀 일치율
        except Exception:
            return 0.0

    def _is_target_account(self, hwnd=None):
        """현재 퍼플 계정이 지정 계정인지 판별 → (matched, 표시문자열, 점수).
        기준이미지가 등록돼 있으면 이미지 대조(권장), 없으면 기존 OCR 문자 비교."""
        # 이미지 대조 모드 (기준이미지 등록 시)
        if os.path.exists(self._profile_ref_path()):
            cur = self._grab_ref_img(hwnd)
            if cur is None:
                return (False, "[이미지] 캡처실패", 0.0)
            sim = self._img_similarity(cur)
            return (sim >= 0.90, f"[이미지대조] 유사도 {int(sim*100)}%", sim)
        # OCR 문자 비교 모드 (기존)
        target = (self.cfg.get("profile_target_id") or "").strip()
        if not target:
            return (True, "", 0.0)
        ocr_id = self._ocr_profile_id(hwnd)
        ratio = self._profile_match_ratio(ocr_id)
        return (ratio >= 1.0, ocr_id, ratio)

    def _check_profile_and_switch(self):
        """아이디 영역 OCR → 100% 일치하면 지정 계정으로 판단"""
        area = self.cfg.get("profile_id_area")
        target = self.cfg.get("profile_target_id", "난봉꾼").strip()
        if not area or not target:
            return True
        try:
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(1)
            from PIL import ImageGrab
            ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            img.save(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"))
            results = _get_ocr_reader().readtext(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"),
                detail=0, paragraph=False)
            ocr_id = "".join(results).strip()
            # 100% 글자 일치 여부 확인
            match = sum(1 for a, b in zip(ocr_id, target) if a == b)
            ratio = match / max(len(target), 1)
            self.status.set(f"아이디 인식: '{ocr_id}' ({int(ratio*100)}% 일치)")
            return ratio >= 1.0
        except Exception as e:
            self.status.set(f"아이디 확인 오류: {e}")
            return True

    def _check_profile_and_switch_at(self, hwnd):
        """hwnd 창 위치를 기준으로 profile_id_area 절대좌표를 계산해서 OCR"""
        import win32gui
        area = self.cfg.get("profile_id_area")
        target = self.cfg.get("profile_target_id", "난봉꾼").strip()
        if not area or not target:
            return True
        try:
            # 창이 (0,0)에 있을 때 기준으로 등록된 좌표 → 현재 창 위치로 보정
            wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
            ax = area["x"] + wx
            ay = area["y"] + wy
            aw, ah = area["w"], area["h"]
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
            img = self._preprocess_ocr_img(img)
            img.save(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"))
            results = _get_ocr_reader().readtext(os.path.join(LOGS_DIR, "profile_ocr_tmp.png"),
                detail=0, paragraph=False)
            ocr_id = "".join(results).strip()
            match = sum(1 for a, b in zip(ocr_id, target) if a == b)
            ratio = match / max(len(target), 1)
            self.status.set(f"아이디 인식: '{ocr_id}' ({int(ratio*100)}% 일치)")
            return ratio >= 1.0
        except Exception as e:
            self.status.set(f"아이디 확인 오류: {e}")
            return True

    # ── 연속 클릭 (별도 기능): 단축키/버튼으로 16개 좌표를 순서대로 1회씩 클릭 ──
    def _open_seq_win(self):
        self._open_section_win("_seq_win", "🔆 절전해제", self._build_seq, w=500, h=580)

    def _vk_name(self, vk):
        if not vk:
            return "미지정"
        names = {0x1B: "ESC", 0x20: "Space", 0x0D: "Enter", 0x09: "Tab",
                 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
                 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
                 0x21: "PageUp", 0x22: "PageDown"}
        if vk in names:
            return names[vk]
        if 0x70 <= vk <= 0x87:
            return f"F{vk - 0x6F}"      # F1~F24
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return chr(vk)              # 0-9, A-Z
        if 0x60 <= vk <= 0x69:
            return f"Num{vk - 0x60}"    # 넘패드 0-9
        return f"VK 0x{vk:02X}"

    def _seq_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('seq_hotkey'))}"

    def _build_seq(self, parent):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS

        _wr = tk.Frame(parent); _wr.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(_wr, text="⚠ F11 때 확인할 경고영역:", font=("맑은 고딕", 8, "bold"),
                 fg="#c0392b").pack(side="left")
        tk.Button(_wr, text="📷 경고영역 지정", font=("맑은 고딕", 8, "bold"),
                  bg="#c0392b", fg="white",
                  command=self._reg_check_area).pack(side="left", padx=(4, 0))
        tk.Button(_wr, text="🔍 지금 확인", font=("맑은 고딕", 8, "bold"),
                  bg="#922b21", fg="white",
                  command=self._check_scan).pack(side="left", padx=(4, 0))
        tk.Label(parent, text="(경고가 떠 있는 01번 클라 화면에서 그 자리를 드래그해 등록 · "
                              "F11을 누를 때마다 16개를 확인합니다)",
                 font=("맑은 고딕", 7), fg="#888").pack(anchor="w", padx=6)
        tk.Label(parent, text="절전해제 — 단축키를 누르면 순서대로 1회씩",
                 font=("맑은 고딕", 9, "bold"), fg="#5b2c6f").pack(pady=(6, 2))

        top = tk.Frame(parent); top.pack(pady=2)
        self._seq_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                         bg="#7f8c8d", fg="white", width=6,
                                         command=self._toggle_seq)
        self._seq_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_seq).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_seq_hotkey).pack(side="left", padx=3)
        tk.Button(top, text="👁 전체보기", font=("맑은 고딕", 8),
                  bg="#566573", fg="white",
                  command=lambda: self._flat_preview_all("seq")).pack(side="left", padx=3)

        self._seq_hotkey_var = tk.StringVar(value=self._seq_hotkey_label())
        tk.Label(parent, textvariable=self._seq_hotkey_var,
                 font=("맑은 고딕", 8), fg="#5b2c6f").pack()

        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._seq_min_var = tk.StringVar(value=str(self.cfg.get("seq_min", SEQ_MIN)))
        self._seq_max_var = tk.StringVar(value=str(self.cfg.get("seq_max", SEQ_MAX)))
        tk.Entry(int_row, textvariable=self._seq_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._seq_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_seq_interval).pack(side="left", padx=3)

        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)
        self._build_flat_grid(parent, "seq")   # 4×4 그리드 (화면 배치와 동일)

    def _refresh_seq_toggle(self):
        if hasattr(self, "_seq_toggle_btn") and self._seq_toggle_btn.winfo_exists():
            on = getattr(self, "_seq_on", False)
            self._seq_toggle_btn.config(text="ON" if on else "OFF",
                                        bg="#27ae60" if on else "#7f8c8d")

    def _toggle_seq(self):
        self._seq_on = not getattr(self, "_seq_on", False)
        self.cfg["seq_on"] = self._seq_on   # 재시작해도 유지되게 저장
        save_cfg(self.cfg)
        self._refresh_seq_toggle()
        if self._seq_on:
            self.status.set(f"절전해제 ON — {self._vk_name(self.cfg.get('seq_hotkey'))} 누르면 실행")
        else:
            self.status.set("절전해제 OFF")

    def _save_seq_interval(self):
        try:
            mn = float(self._seq_min_var.get())
            mx = float(self._seq_max_var.get())
            if mx < mn:
                mn, mx = mx, mn
            self.cfg["seq_min"] = mn
            self.cfg["seq_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_seq_coord(self, idx):
        self._seq_reg_idx = idx
        self.status.set(f"3초 후 절전해제 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="seq")])

    def on_seq_coord(self, x, y):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS
        while len(seq) < SEQ_SLOTS:
            seq.append(None)
        seq[self._seq_reg_idx] = [x, y]
        self.cfg["seq_slots"] = seq
        save_cfg(self.cfg)
        if hasattr(self, "_seq_slot_vars") and self._seq_reg_idx < len(self._seq_slot_vars):
            self._seq_slot_vars[self._seq_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 절전해제 #{self._seq_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_seq_coord(self, idx):
        seq = self.cfg.get("seq_slots") or [None] * SEQ_SLOTS
        if idx < len(seq):
            seq[idx] = None
            self.cfg["seq_slots"] = seq
            save_cfg(self.cfg)
        if hasattr(self, "_seq_slot_vars") and idx < len(self._seq_slot_vars):
            self._seq_slot_vars[idx].set("미등록")
        self.status.set(f"절전해제 #{idx+1} 삭제")

    def _seq_hide(self):
        """단축키 실행 전 창 정리 — 메인런처를 '즉시' 맨 뒤로 보낸 뒤 서브창을 정리한다.
        (서브창을 먼저 최소화하면 포커스가 메인런처로 넘어와 잠깐 앞으로 튀어나온다)"""
        self._quiet_restore = True          # 이 동안엔 어떤 이유로도 앞으로 올리지 않음
        self._send_to_back()                # ① 먼저 뒤로
        try:
            for w in self._section_wins():  # ② 서브창 정리
                try: w.iconify()
                except Exception: pass
            self._minimize_claude()
        except Exception:
            pass
        self._send_to_back()                # ③ 다시 뒤로 (포커스 이동 상쇄)
        try:
            self.iconify()                  # ④ 실행 중엔 아예 최소화
        except Exception:
            pass
        # 늦게 도착하는 포커스 이벤트까지 눌러두기
        self.after(120, self._send_to_back)
        self.after(350, self._send_to_back)
        self.after(600, lambda: (self._send_to_back(),
                                 setattr(self, "_quiet_restore", False)))

    def _start_seq(self):
        threading.Thread(target=self._run_seq, daemon=True).start()

    def _run_seq(self):
        self._start_pause()
        if getattr(self, "_seq_running", False):
            return
        seq = self.cfg.get("seq_slots") or []
        coords = [c for c in seq if c]
        if not coords:
            self.after(0, lambda: self.status.set("절전해제: 등록된 좌표가 없습니다"))
            return
        # 단축키 실행은 대기열에 넣지 않는다 (나중에 저절로 이어서 도는 것 방지)
        if not self._try_busy("절전해제"):
            return
        self._seq_running = True
        try:
            # 클릭 좌표를 런처/연속클릭 창이 가리지 않도록 확실히 최소화 후 실행
            self.after(0, self._seq_hide)
            time.sleep(0.15)
            mn = float(self.cfg.get("seq_min", SEQ_MIN))
            mx = float(self.cfg.get("seq_max", SEQ_MAX))
            if mx < mn:
                mn, mx = mx, mn
            random.shuffle(coords)   # 매 실행마다 클릭 순서 무작위
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                self.after(0, lambda a=i: self.status.set(f"🔆 절전해제 {a+1}/{n} (랜덤 순서)..."))
                pyautogui.click(x, y)
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx))   # 슬롯간 간격 (설정값 그대로, 추가 간격 없음)
            self.after(0, lambda: self.status.set(f"✔ 절전해제 완료 ({n}개)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"절전해제 오류: {err}"))
        finally:
            self._seq_running = False
            self._clear_busy("절전해제")
            self.after(0, self._restore_back_quiet)   # 앞으로 띄우지 않고 바로 맨 뒤로
        # (2026-08-10) F11(절전해제) 끝나면 경고영역을 확인한다
        try:
            self.after(1200, lambda: self._check_scan(quiet=True))
        except Exception:
            pass

    def _assign_seq_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)  # 이전 클릭이 떼질 시간
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):  # 마우스 버튼 제외
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:  # ESC
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["seq_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_seq_hotkey_var"):
                    self._seq_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    # ── 🌙 절전모드 (절전해제와 동일 구조 — 별도 좌표/단축키/ON·OFF, 기본 Shift·ON) ──
    def _open_slp_win(self):
        self._open_section_win("_slp_win", "🌙 절전모드", self._build_slp, w=500, h=580)

    def _slp_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('slp_hotkey'))}"

    def _build_slp(self, parent):
        tk.Label(parent, text="절전모드 — 단축키를 누르면 순서대로 1회씩",
                 font=("맑은 고딕", 9, "bold"), fg="#154360").pack(pady=(6, 2))
        top = tk.Frame(parent); top.pack(pady=2)
        self._slp_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                         bg="#7f8c8d", fg="white", width=6,
                                         command=self._toggle_slp)
        self._slp_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_slp).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_slp_hotkey).pack(side="left", padx=3)
        tk.Button(top, text="👁 전체보기", font=("맑은 고딕", 8),
                  bg="#566573", fg="white",
                  command=lambda: self._flat_preview_all("slp")).pack(side="left", padx=3)
        self._slp_hotkey_var = tk.StringVar(value=self._slp_hotkey_label())
        tk.Label(parent, textvariable=self._slp_hotkey_var,
                 font=("맑은 고딕", 8), fg="#154360").pack()
        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._slp_min_var = tk.StringVar(value=str(self.cfg.get("slp_min", SEQ_MIN)))
        self._slp_max_var = tk.StringVar(value=str(self.cfg.get("slp_max", SEQ_MAX)))
        tk.Entry(int_row, textvariable=self._slp_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._slp_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_slp_interval).pack(side="left", padx=3)
        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)
        self._build_flat_grid(parent, "slp")
        self._refresh_slp_toggle()

    def _refresh_slp_toggle(self):
        if hasattr(self, "_slp_toggle_btn") and self._slp_toggle_btn.winfo_exists():
            on = getattr(self, "_slp_on", False)
            self._slp_toggle_btn.config(text="ON" if on else "OFF",
                                        bg="#27ae60" if on else "#7f8c8d")

    def _toggle_slp(self):
        self._slp_on = not getattr(self, "_slp_on", False)
        self.cfg["slp_on"] = self._slp_on
        save_cfg(self.cfg)
        self._refresh_slp_toggle()
        self.status.set(f"절전모드 ON — {self._vk_name(self.cfg.get('slp_hotkey'))} 누르면 실행"
                        if self._slp_on else "절전모드 OFF")

    def _save_slp_interval(self):
        try:
            mn = float(self._slp_min_var.get()); mx = float(self._slp_max_var.get())
            if mx < mn: mn, mx = mx, mn
            self.cfg["slp_min"] = mn; self.cfg["slp_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 절전모드 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_slp_coord(self, idx):
        self._slp_reg_idx = idx
        self.status.set(f"3초 후 절전모드 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="slp")])

    def on_slp_coord(self, x, y):
        slp = self.cfg.get("slp_slots") or [None] * SEQ_SLOTS
        while len(slp) < SEQ_SLOTS:
            slp.append(None)
        slp[self._slp_reg_idx] = [x, y]
        self.cfg["slp_slots"] = slp
        save_cfg(self.cfg)
        if hasattr(self, "_slp_slot_vars") and self._slp_reg_idx < len(self._slp_slot_vars):
            self._slp_slot_vars[self._slp_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 절전모드 #{self._slp_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_slp_coord(self, idx):
        slp = self.cfg.get("slp_slots") or [None] * SEQ_SLOTS
        if idx < len(slp):
            slp[idx] = None
            self.cfg["slp_slots"] = slp
            save_cfg(self.cfg)
        if hasattr(self, "_slp_slot_vars") and idx < len(self._slp_slot_vars):
            self._slp_slot_vars[idx].set("미등록")
        self.status.set(f"절전모드 #{idx+1} 삭제")

    def _start_slp(self):
        threading.Thread(target=self._run_slp, daemon=True).start()

    def _run_slp(self):
        self._start_pause()
        if getattr(self, "_slp_running", False):
            return
        coords = [c for c in (self.cfg.get("slp_slots") or []) if c]
        if not coords:
            self.after(0, lambda: self.status.set("절전모드: 등록된 좌표가 없습니다"))
            return
        if not self._try_busy("절전모드"):
            return
        self._slp_running = True
        try:
            self.after(0, self._seq_hide)
            time.sleep(0.15)
            mn = float(self.cfg.get("slp_min", SEQ_MIN))
            mx = float(self.cfg.get("slp_max", SEQ_MAX))
            if mx < mn: mn, mx = mx, mn
            random.shuffle(coords)
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                self.after(0, lambda a=i: self.status.set(f"🌙 절전모드 {a+1}/{n} (랜덤 순서)..."))
                pyautogui.click(x, y)
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx))
            self.after(0, lambda: self.status.set(f"✔ 절전모드 완료 ({n}개)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"절전모드 오류: {err}"))
        finally:
            self._slp_running = False
            self._clear_busy("절전모드")
            self.after(0, self._restore_back_quiet)   # 앞으로 띄우지 않고 바로 맨 뒤로

    def _assign_slp_hotkey(self):
        self.status.set("절전모드에 쓸 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk; break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None or captured == 0x1B:
                self.after(0, lambda: self.status.set("절전모드 단축키 지정 취소"))
                return
            self.cfg["slp_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_slp_hotkey_var"):
                    self._slp_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 절전모드 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _slp_hotkey_loop(self):
        """전역 단축키 감시 — 절전모드 ON 상태에서 지정키(기본 Shift)가 눌리면 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("slp_hotkey") or 0x7B
            if not getattr(self, "_slp_on", False):
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_slp_running", False):
                threading.Thread(target=self._run_slp, daemon=True).start()
            prev = down

    def _seq_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 연속 클릭 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("seq_hotkey")
            if not getattr(self, "_seq_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_seq_running", False):
                threading.Thread(target=self._run_seq, daemon=True).start()
            prev = down

    @staticmethod
    def _open_wdoff_win(self):
        self._open_section_win("_wdoff_win", "🚪 주말던전 끄기", self._build_wdoff, w=500, h=580)

    def _wdoff_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('wdoff_hotkey'))}"

    def _build_wdoff(self, parent):
        wd = self.cfg.get("wdoff_slots") or [None] * WDOFF_SLOTS

        tk.Label(parent, text="주말던전 끄기 — 등록 좌표를 순서 랜덤으로 1회씩",
                 font=("맑은 고딕", 9, "bold"), fg="#34495e").pack(pady=(6, 2))

        top = tk.Frame(parent); top.pack(pady=2)
        self._wdoff_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                           bg="#7f8c8d", fg="white", width=6,
                                           command=self._toggle_wdoff)
        self._wdoff_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_wdoff).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_wdoff_hotkey).pack(side="left", padx=3)
        tk.Button(top, text="👁 전체보기", font=("맑은 고딕", 8),
                  bg="#566573", fg="white",
                  command=self._preview_wdoff_all).pack(side="left", padx=3)

        self._wdoff_hotkey_var = tk.StringVar(value=self._wdoff_hotkey_label())
        tk.Label(parent, textvariable=self._wdoff_hotkey_var,
                 font=("맑은 고딕", 8), fg="#34495e").pack()

        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._wdoff_min_var = tk.StringVar(value=str(self.cfg.get("wdoff_min", WDOFF_MIN)))
        self._wdoff_max_var = tk.StringVar(value=str(self.cfg.get("wdoff_max", WDOFF_MAX)))
        tk.Entry(int_row, textvariable=self._wdoff_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._wdoff_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_wdoff_interval).pack(side="left", padx=3)

        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)
        self._build_flat_grid(parent, "wdoff")   # 4×4 그리드 (화면 배치와 동일)

    def _refresh_wdoff_toggle(self):
        if hasattr(self, "_wdoff_toggle_btn") and self._wdoff_toggle_btn.winfo_exists():
            on = getattr(self, "_wdoff_on", False)
            self._wdoff_toggle_btn.config(text="ON" if on else "OFF",
                                          bg="#27ae60" if on else "#7f8c8d")

    def _toggle_wdoff(self):
        self._wdoff_on = not getattr(self, "_wdoff_on", False)
        self.cfg["wdoff_on"] = self._wdoff_on   # 재시작해도 유지
        save_cfg(self.cfg)
        self._refresh_wdoff_toggle()
        if self._wdoff_on:
            self.status.set(f"주말던전끄기 ON — {self._vk_name(self.cfg.get('wdoff_hotkey'))} 누르면 실행")
        else:
            self.status.set("주말던전끄기 OFF")

    def _save_wdoff_interval(self):
        try:
            mn = float(self._wdoff_min_var.get())
            mx = float(self._wdoff_max_var.get())
            if mx < mn:
                mn, mx = mx, mn
            self.cfg["wdoff_min"] = mn
            self.cfg["wdoff_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_wdoff_coord(self, idx):
        self._wdoff_reg_idx = idx
        self.status.set(f"3초 후 주말던전끄기 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="wdoff")])

    def on_wdoff_coord(self, x, y):
        wd = self.cfg.get("wdoff_slots") or [None] * WDOFF_SLOTS
        while len(wd) < WDOFF_SLOTS:
            wd.append(None)
        wd[self._wdoff_reg_idx] = [x, y]
        self.cfg["wdoff_slots"] = wd
        save_cfg(self.cfg)
        if hasattr(self, "_wdoff_slot_vars") and self._wdoff_reg_idx < len(self._wdoff_slot_vars):
            self._wdoff_slot_vars[self._wdoff_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 주말던전끄기 #{self._wdoff_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_wdoff_coord(self, idx):
        wd = self.cfg.get("wdoff_slots") or [None] * WDOFF_SLOTS
        if idx < len(wd):
            wd[idx] = None
            self.cfg["wdoff_slots"] = wd
            save_cfg(self.cfg)
        if hasattr(self, "_wdoff_slot_vars") and idx < len(self._wdoff_slot_vars):
            self._wdoff_slot_vars[idx].set("미등록")
        self.status.set(f"주말던전끄기 #{idx+1} 삭제")

    def _preview_wdoff_all(self):
        """전체 좌표 미리보기 — 점 드래그=개별 이동, 빈 곳 드래그=전체 이동, 점 클릭=재등록."""
        wd = self.cfg.get("wdoff_slots") or []
        reg = [(i, c) for i, c in enumerate(wd) if c]
        if not reg:
            self.status.set("주말던전끄기: 등록된 좌표가 없습니다"); return
        dots = [(c[0], c[1], si + 1) for si, c in reg]

        def rereg(dot_idx):
            self._reg_wdoff_coord(reg[dot_idx][0])

        def _save(dot_idx, nx, ny):
            si = reg[dot_idx][0]
            self.cfg["wdoff_slots"][si] = [nx, ny]
            save_cfg(self.cfg)
            if hasattr(self, "_wdoff_slot_vars") and si < len(self._wdoff_slot_vars):
                self._wdoff_slot_vars[si].set(f"({nx},{ny})")

        self._open_dot_preview("주말던전 끄기 — 전체 좌표", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _start_wdoff(self):
        threading.Thread(target=self._run_wdoff, daemon=True).start()

    def _run_wdoff(self):
        self._start_pause()
        if getattr(self, "_wdoff_running", False):
            return
        wd = self.cfg.get("wdoff_slots") or []
        coords = [c for c in wd if c]
        if not coords:
            self.after(0, lambda: self.status.set("주말던전끄기: 등록된 좌표가 없습니다"))
            return
        if not self._try_busy_or_queue("주말던전끄기", self._start_wdoff):
            return
        self._wdoff_running = True
        try:
            self.after(0, self._seq_hide)   # 런처/창 최소화 (연속클릭과 동일)
            time.sleep(0.5)
            mn = float(self.cfg.get("wdoff_min", WDOFF_MIN))
            mx = float(self.cfg.get("wdoff_max", WDOFF_MAX))
            if mx < mn:
                mn, mx = mx, mn
            random.shuffle(coords)   # 매 실행마다 클릭 순서 무작위 (연속클릭과 동일)
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                self.after(0, lambda a=i: self.status.set(f"🚪 주말던전끄기 {a+1}/{n} (랜덤 순서)..."))
                pyautogui.click(x, y)
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx))
            self.after(0, lambda: self.status.set(f"✔ 주말던전끄기 완료 ({n}개)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"주말던전끄기 오류: {err}"))
        finally:
            self._wdoff_running = False
            self._clear_busy("주말던전끄기")
            self.after(0, self._restore_back)

    def _assign_wdoff_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["wdoff_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_wdoff_hotkey_var"):
                    self._wdoff_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _wdoff_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 주말던전 끄기 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("wdoff_hotkey")
            if not getattr(self, "_wdoff_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_wdoff_running", False):
                threading.Thread(target=self._run_wdoff, daemon=True).start()
            prev = down

    # ── 일반던전충전 (연속클릭 복제 — 각 좌표를 7~9회 랜덤 연속 클릭) ──
    def _open_dc_win(self):
        self._open_section_win("_dc_win", "🎯 일반던전충전", self._build_dc, w=300, h=680)

    def _dc_hotkey_label(self):
        return f"단축키: {self._vk_name(self.cfg.get('dc_hotkey'))}"

    def _build_dc(self, parent):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS

        tk.Label(parent,
                 text=f"일반던전충전 — 각 좌표 {DC_BURST_MIN:.0f}~{DC_BURST_MAX:.0f}초 내 {DC_TAPS_MIN}~{DC_TAPS_MAX}회 연속 클릭",
                 font=("맑은 고딕", 9, "bold"), fg="#6c3483").pack(pady=(6, 2))

        top = tk.Frame(parent); top.pack(pady=2)
        self._dc_toggle_btn = tk.Button(top, text="OFF", font=("맑은 고딕", 9, "bold"),
                                        bg="#7f8c8d", fg="white", width=6,
                                        command=self._toggle_dc)
        self._dc_toggle_btn.pack(side="left", padx=(0, 3))
        tk.Button(top, text="▶ 실행", font=("맑은 고딕", 9, "bold"),
                  bg="#27ae60", fg="white", width=6,
                  command=self._start_dc).pack(side="left", padx=3)
        tk.Button(top, text="⌨ 단축키", font=("맑은 고딕", 8),
                  bg="#2c3e50", fg="white",
                  command=self._assign_dc_hotkey).pack(side="left", padx=3)

        self._dc_hotkey_var = tk.StringVar(value=self._dc_hotkey_label())
        tk.Label(parent, textvariable=self._dc_hotkey_var,
                 font=("맑은 고딕", 8), fg="#6c3483").pack()

        int_row = tk.Frame(parent); int_row.pack(pady=2)
        tk.Label(int_row, text="좌표간 간격(초)", font=("맑은 고딕", 8)).pack(side="left")
        self._dc_min_var = tk.StringVar(value=str(self.cfg.get("dc_min", DC_MIN)))
        self._dc_max_var = tk.StringVar(value=str(self.cfg.get("dc_max", DC_MAX)))
        tk.Entry(int_row, textvariable=self._dc_min_var, width=4).pack(side="left", padx=2)
        tk.Label(int_row, text="~").pack(side="left")
        tk.Entry(int_row, textvariable=self._dc_max_var, width=4).pack(side="left", padx=2)
        tk.Button(int_row, text="저장", font=("맑은 고딕", 7),
                  command=self._save_dc_interval).pack(side="left", padx=3)

        tk.Frame(parent, height=1, bg="#ccc").pack(fill="x", padx=8, pady=3)

        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        self._dc_slot_vars = []
        for i in range(DC_SLOTS):
            row = tk.Frame(inner, bd=1, relief="groove"); row.pack(fill="x", padx=3, pady=1)
            tk.Label(row, text=f"#{i+1:02d}", font=("맑은 고딕", 8, "bold"),
                     width=3, fg="#6c3483").pack(side="left", padx=2)
            sv = tk.StringVar()
            c = dc[i] if i < len(dc) else None
            sv.set(f"({c[0]},{c[1]})" if c else "미등록")
            self._dc_slot_vars.append(sv)
            tk.Label(row, textvariable=sv, font=("맑은 고딕", 8),
                     width=12, anchor="w").pack(side="left")
            tk.Button(row, text="등록", font=("맑은 고딕", 7), bg="#6c3483", fg="white",
                      command=lambda x=i: self._reg_dc_coord(x)).pack(side="right", padx=2)
            tk.Button(row, text="×", font=("맑은 고딕", 7), fg="red", width=2,
                      command=lambda x=i: self._del_dc_coord(x)).pack(side="right")
            row.bind("<MouseWheel>", _wheel)

        self._refresh_dc_toggle()

    def _refresh_dc_toggle(self):
        if hasattr(self, "_dc_toggle_btn") and self._dc_toggle_btn.winfo_exists():
            on = getattr(self, "_dc_on", False)
            self._dc_toggle_btn.config(text="ON" if on else "OFF",
                                       bg="#27ae60" if on else "#7f8c8d")

    def _toggle_dc(self):
        self._dc_on = not getattr(self, "_dc_on", False)
        self.cfg["dc_on"] = self._dc_on   # 재시작해도 유지되게 저장
        save_cfg(self.cfg)
        self._refresh_dc_toggle()
        if self._dc_on:
            self.status.set(f"일반던전충전 ON — {self._vk_name(self.cfg.get('dc_hotkey'))} 누르면 실행")
        else:
            self.status.set("일반던전충전 OFF")

    def _save_dc_interval(self):
        try:
            mn = float(self._dc_min_var.get())
            mx = float(self._dc_max_var.get())
            if mx < mn:
                mn, mx = mx, mn
            self.cfg["dc_min"] = mn
            self.cfg["dc_max"] = mx
            save_cfg(self.cfg)
            self.status.set(f"✔ 좌표간 간격 저장: {mn}~{mx}초")
        except ValueError:
            self.status.set("간격은 숫자로 입력하세요")

    def _reg_dc_coord(self, idx):
        self._dc_reg_idx = idx
        self.status.set(f"3초 후 일반던전충전 #{idx+1} 위치를 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="dc")])

    def on_dc_coord(self, x, y):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS
        while len(dc) < DC_SLOTS:
            dc.append(None)
        dc[self._dc_reg_idx] = [x, y]
        self.cfg["dc_slots"] = dc
        save_cfg(self.cfg)
        if hasattr(self, "_dc_slot_vars") and self._dc_reg_idx < len(self._dc_slot_vars):
            self._dc_slot_vars[self._dc_reg_idx].set(f"({x},{y})")
        self.status.set(f"✔ 일반던전충전 #{self._dc_reg_idx+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_dc_coord(self, idx):
        dc = self.cfg.get("dc_slots") or [None] * DC_SLOTS
        if idx < len(dc):
            dc[idx] = None
            self.cfg["dc_slots"] = dc
            save_cfg(self.cfg)
        if hasattr(self, "_dc_slot_vars") and idx < len(self._dc_slot_vars):
            self._dc_slot_vars[idx].set("미등록")
        self.status.set(f"일반던전충전 #{idx+1} 삭제")

    def _start_dc(self):
        threading.Thread(target=self._run_dc, daemon=True).start()

    def _run_dc(self):
        self._start_pause()
        if getattr(self, "_dc_running", False):
            return
        dc = self.cfg.get("dc_slots") or []
        coords = [c for c in dc if c]
        if not coords:
            self.after(0, lambda: self.status.set("일반던전충전: 등록된 좌표가 없습니다"))
            return
        if not self._try_busy_or_queue("일반던전충전", self._start_dc):
            return
        self._dc_running = True
        try:
            # 클릭 좌표를 런처/창이 가리지 않도록 최소화 후 실행(연속클릭과 동일)
            self.after(0, self._seq_hide)
            time.sleep(0.15)
            mn = float(self.cfg.get("dc_min", DC_MIN))
            mx = float(self.cfg.get("dc_max", DC_MAX))
            if mx < mn:
                mn, mx = mx, mn
            n = len(coords)
            for i, (x, y) in enumerate(coords):
                taps = random.randint(DC_TAPS_MIN, DC_TAPS_MAX)   # 좌표마다 7~9회 랜덤
                window = random.uniform(DC_BURST_MIN, DC_BURST_MAX)  # 1~2초 랜덤 구간
                # 7~9회 클릭을 window(초) 안에 랜덤 간격으로 모두 실행
                gaps = taps - 1
                if gaps > 0:
                    ws = [random.random() for _ in range(gaps)]
                    s = sum(ws) or 1.0
                    intervals = [window * w / s for w in ws]
                else:
                    intervals = []
                self.after(0, lambda a=i, t=taps, w=window: self.status.set(
                    f"🎯 일반던전충전 {a+1}/{n} — {t}회 연속({w:.1f}초 내)..."))
                for k in range(taps):
                    click_at(x, y)
                    if k < taps - 1:
                        time.sleep(intervals[k])
                if i < n - 1:
                    time.sleep(random.uniform(mn, mx) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.after(0, lambda: self.status.set(f"✔ 일반던전충전 완료 ({n}개 좌표)"))
        except Exception as e:
            self.after(0, lambda err=e: self.status.set(f"일반던전충전 오류: {err}"))
        finally:
            self._dc_running = False
            self._clear_busy("일반던전충전")
            self.after(0, self._restore_back)   # 완료 후 런처/서브창 복원

    def _assign_dc_hotkey(self):
        self.status.set("지정할 키를 누르세요... (5초 안에, ESC=취소)")
        def _cap():
            import ctypes
            time.sleep(0.3)  # 이전 클릭이 떼질 시간
            end = time.time() + 5
            captured = None
            while time.time() < end:
                for vk in range(0x08, 0xFF):
                    if vk in (0x01, 0x02, 0x04):  # 마우스 버튼 제외
                        continue
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        captured = vk
                        break
                if captured is not None:
                    break
                time.sleep(0.02)
            if captured is None:
                self.after(0, lambda: self.status.set("단축키 지정 취소 (시간초과)"))
                return
            if captured == 0x1B:  # ESC
                self.after(0, lambda: self.status.set("단축키 지정 취소"))
                return
            self.cfg["dc_hotkey"] = captured
            save_cfg(self.cfg)
            name = self._vk_name(captured)
            def _upd():
                if hasattr(self, "_dc_hotkey_var"):
                    self._dc_hotkey_var.set(f"단축키: {name}")
                self.status.set(f"✔ 단축키 지정: {name}")
            self.after(0, _upd)
        threading.Thread(target=_cap, daemon=True).start()

    def _dc_hotkey_loop(self):
        """전역 단축키 감시 — ON 상태에서 지정키가 눌리면 일반던전충전 실행."""
        import ctypes
        prev = False
        while True:
            time.sleep(0.03)
            vk = self.cfg.get("dc_hotkey")
            if not getattr(self, "_dc_on", False) or not vk:
                prev = False
                continue
            try:
                down = bool(ctypes.windll.user32.GetAsyncKeyState(int(vk)) & 0x8000)
            except Exception:
                prev = False
                continue
            if down and not prev and not getattr(self, "_dc_running", False):
                threading.Thread(target=self._run_dc, daemon=True).start()
            prev = down

    # ── 인형 탐험 (16슬롯 × 18좌표, 슬롯별 순차 클릭) ──
    def _open_doll_win(self):
        self._open_section_win("_doll_win", "🧸 인형 탐험", self._build_doll, w=440, h=440)

    def _build_doll(self, parent):
        tk.Label(parent, text=f"인형 탐험  (슬롯당 {DOLL_CLICKS}좌표 순차 클릭)",
                 font=("맑은 고딕", 9, "bold"), fg="#b9770e").pack(anchor="w", padx=4, pady=(4,2))

        hr = tk.Frame(parent); hr.pack(pady=3)
        self.btn_doll_run = tk.Button(hr, text="▶  인형탐험 실행",
            font=("맑은 고딕", 9, "bold"), bg="#b9770e", fg="white",
            activebackground="#8a5809", width=15, height=2, command=self._start_doll)
        self.btn_doll_run.pack(side="left", padx=(0, 3))
        self.btn_doll_stop = tk.Button(hr, text="■ 멈춤",
            font=("맑은 고딕", 8, "bold"), bg="#c0392b", fg="white",
            activebackground="#922b21", width=6, height=2,
            command=lambda: setattr(self, "_doll_stop", True) or self.status.set("인형탐험 멈추는 중..."),
            state="disabled")
        self.btn_doll_stop.pack(side="left")
        tk.Button(hr, text="🔀 그룹복사 (#01→전체)",
            font=("맑은 고딕", 8), bg="#8e44ad", fg="white", width=18,
            command=self._group_copy_doll).pack(side="left", padx=(8,0))
        tk.Button(hr, text="👁 전체보기", font=("맑은 고딕", 8),
                  bg="#566573", fg="white",
                  command=lambda: self._slots_preview_all(
                      "인형탐험", "doll_slots", self._preview_doll,
                      self._refresh_doll_display)).pack(side="left", padx=(6, 0))

        tk.Frame(parent, height=1, bg="#ddd").pack(fill="x", padx=6, pady=3)

        # 4×4 세로(열 우선) 그리드 — 01~04 첫 열, 05~08 둘째 열, …
        wg = tk.Frame(parent); wg.pack(padx=6, pady=4)
        self._doll_enable_btns = []
        self._doll_coord_sv    = []
        self._doll_name_vars   = []
        self._doll_name_ents   = []
        for idx in range(DOLL_SLOTS):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg, bd=1, relief="groove", padx=3, pady=2)
            cell.grid(row=r, column=c, padx=5, pady=4)
            # 슬롯 이름 — 프리셋을 적용하면 그 이름이 자동으로 들어온다
            _nm = (self.cfg["doll_slots"][idx].get("name") or "").strip()
            nvv = tk.StringVar(value="" if _nm == "미등록" else _nm)
            self._doll_name_vars.append(nvv)
            ne = tk.Entry(cell, textvariable=nvv, font=("맑은 고딕", 8, "bold"), width=10,
                          justify="center", relief="flat", bg="#f2f2f2",
                          fg=self._name_color(_nm))
            self._doll_name_ents.append(ne)
            ne.pack(pady=(1, 0), fill="x")
            def _sv_dname(*_a, x=idx, v=nvv):
                if time.time() - getattr(self, "_doll_preset_ts", 0) < 1.0:
                    return                       # 프리셋 적용 직후 덮어쓰기 방지
                self.cfg["doll_slots"][x]["name"] = v.get().strip() or "미등록"
                save_cfg(self.cfg)
            nvv.trace_add("write", _sv_dname)
            top = tk.Frame(cell); top.pack()
            tk.Label(top, text=f"{idx+1:02d}", font=("맑은 고딕", 9, "bold"), fg="#555").pack(side="left")
            en = self.cfg["doll_slots"][idx].get("enabled", True)
            eb = tk.Button(top, text="ON" if en else "OFF", font=("맑은 고딕", 7, "bold"), width=4,
                           bg="#27ae60" if en else "#95a5a6", fg="white", pady=0,
                           command=lambda x=idx: self._toggle_doll_enable(x))
            eb.pack(side="left", padx=(4,0))
            self._doll_enable_btns.append(eb)
            reg = sum(1 for cc in self.cfg["doll_slots"][idx].get("coords", []) if cc)
            sv = tk.StringVar(value=f"좌표 {reg}/{DOLL_CLICKS}")
            self._doll_coord_sv.append(sv)
            tk.Button(cell, textvariable=sv, font=("맑은 고딕", 8, "bold"),
                      bg="#b9770e", fg="white", width=10,
                      command=lambda x=idx: self._open_doll_slot(x)).pack(pady=(3,0))
            tk.Button(cell, text="▶ 테스트", font=("맑은 고딕", 7), bg="#27ae60", fg="white", width=10,
                      command=lambda x=idx: self._test_doll(x)).pack(pady=(2,1))
            cprow = tk.Frame(cell); cprow.pack(pady=(0,1))
            tk.Button(cprow, text="복사", font=("맑은 고딕", 6), bg="#2980b9", fg="white", width=3,
                      command=lambda x=idx: self._copy_doll_slot(x)).pack(side="left", padx=(0,2))
            tk.Button(cprow, text="붙임", font=("맑은 고딕", 6), bg="#8e44ad", fg="white", width=3,
                      command=lambda x=idx: self._paste_doll_slot(x)).pack(side="left", padx=(0,2))
            tk.Button(cprow, text="👁", font=("맑은 고딕", 6), bg="#566573", fg="white", width=2,
                      command=lambda x=idx: self._preview_doll(x)).pack(side="left")

        self._doll_pop_win = None
        self._refresh_doll_display()

    # ── 인형탐험 프리셋 P1~P4 — 번호별 [그대로/삭제/위치변경]을 저장해두고 슬롯에 적용 ──
    DOLL_PRESET_NAMES = ["전부다!!", "인형,성물!!", "인형!!", "성물!!"]

    @staticmethod
    def _name_color(name):
        """슬롯 이름(프리셋 이름)별 색 — 한눈에 구분되게."""
        nm = (name or "").strip()
        if not nm:
            return "#2c3e50"
        if "전부" in nm:
            return "#1e8449"          # 초록
        if "인형" in nm and "성물" in nm:
            return "#2471a3"          # 파랑
        if "인형" in nm:
            return "#b9770e"          # 주황
        if "성물" in nm:
            return "#7d3c98"          # 보라
        if "빨갱" in nm:
            return "#c0392b"
        if "주홍" in nm:
            return "#7d3c98"
        return "#2c3e50"

    def _doll_presets(self):
        lst = self.cfg.setdefault("_doll_presets", [])
        names = self.DOLL_PRESET_NAMES
        if len(lst) != len(names):
            new = []
            for i, nm in enumerate(names):
                old = lst[i] if i < len(lst) else {}
                new.append({"name": nm, "items": old.get("items", {}),
                            "src": old.get("src", 1), "abs": old.get("abs", False)})
            lst = new
            self.cfg["_doll_presets"] = lst
        return lst

    def _doll_preset_color(self, pi):
        return ("#1e8449", "#2471a3", "#b9770e", "#7d3c98")[pi % 4]

    def _apply_doll_preset(self, idx, pi):
        """이 슬롯의 지정 번호만 삭제/이동 (나머지 좌표는 그대로)."""
        pr = self._doll_presets()[pi]
        items = pr.get("items") or {}
        if not items:
            self.status.set(f"[{pr['name']}] 에 저장된 내용이 없습니다 — [⚙ 프리셋 설정]에서 만들어주세요")
            return
        slot = self.cfg["doll_slots"][idx]
        cs = slot.setdefault("coords", [])
        while len(cs) < DOLL_CLICKS: cs.append(None)
        rects = self._client_rects_by_slot()
        dels, movs = [], []
        for k2, it in items.items():
            j = int(k2)
            if j >= DOLL_CLICKS: continue
            if it.get("act") == "del":
                cs[j] = None; dels.append(j + 1)
            else:
                rel = it.get("rel") or [0, 0]
                if rects and not pr.get("abs"):
                    cs[j] = [rel[0] + rects[idx][0], rel[1] + rects[idx][1]]
                else:
                    cs[j] = [rel[0], rel[1]]
                movs.append(j + 1)
        slot["name"] = pr.get("name") or f"P{pi+1}"
        self._doll_preset_ts = time.time()      # 이름칸 자동저장이 덮어쓰지 않게
        try:
            self._doll_name_vars[idx].set(slot["name"])
        except Exception:
            pass
        save_cfg(self.cfg)
        self._refresh_doll_display()
        # (2026-08-10) 프리셋을 고르면 적용하고 좌표등록 팝업을 닫는다 (사용자 지시)
        if getattr(self, "_doll_pop_win", None) and self._doll_pop_win.winfo_exists()            and getattr(self, "_doll_pop_slot", None) == idx:
            try:
                self._doll_pop_win.destroy()
            except Exception:
                pass
            self._doll_pop_win = None
        self.status.set(f"✔ 인형탐험 #{idx+1:02d} [{slot['name']}] 적용 — "
                        f"삭제 {sorted(dels) or '없음'} / 이동 {sorted(movs) or '없음'}")

    def _build_doll_preset_row(self, parent, idx):
        """슬롯 팝업용 프리셋 버튼 줄."""
        box = tk.LabelFrame(parent, text="프리셋 (누르면 이 슬롯에 적용)",
                            font=("맑은 고딕", 8), fg="#7d6608", padx=4, pady=3)
        box.pack(fill="x", padx=10, pady=(4, 2))
        self._doll_preset_btns = []
        row = tk.Frame(box); row.pack(fill="x")
        for pi, pr in enumerate(self._doll_presets()):
            b = tk.Button(row, text=pr.get("name") or f"P{pi+1}",
                          font=("맑은 고딕", 9, "bold"), width=10, pady=2,
                          bg=self._doll_preset_color(pi), fg="white",
                          command=lambda x=idx, q=pi: self._apply_doll_preset(x, q))
            b.pack(side="left", padx=3)
            self._doll_preset_btns.append(b)
        tk.Button(box, text="⚙ 프리셋 설정", font=("맑은 고딕", 8, "bold"),
                  bg="#7d6608", fg="white",
                  command=self._open_doll_preset_win).pack(fill="x", pady=(3, 0))
        return box

    def _open_doll_preset_win(self):
        """인형탐험 프리셋 편집 — 좌표 1~18번을 보여주고 번호별로 그대로/삭제/위치변경."""
        old = getattr(self, "_doll_pw_win", None)
        if old and old.winfo_exists():
            try: old.destroy()
            except Exception: pass
        win = tk.Toplevel(self); self._doll_pw_win = win
        win.title("⚙ 인형탐험 프리셋 편집")
        win.attributes("-topmost", True)
        self._doll_pw = {"pi": 0, "items": {}, "cells": [], "name": tk.StringVar(),
                         "src": tk.StringVar(value="1")}
        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10, 4))
        self._doll_pw["tabs"] = []
        for pi, pr in enumerate(self._doll_presets()):
            b = tk.Button(top, text=pr.get("name") or f"P{pi+1}",
                          font=("맑은 고딕", 9, "bold"), width=10,
                          bg=self._doll_preset_color(pi), fg="white",
                          command=lambda x=pi: self._doll_preset_load(x))
            b.pack(side="left", padx=2)
            self._doll_pw["tabs"].append(b)
        tk.Label(top, text="이름", font=("맑은 고딕", 9, "bold")).pack(side="left", padx=(10, 2))
        tk.Entry(top, textvariable=self._doll_pw["name"], font=("맑은 고딕", 10),
                 width=14).pack(side="left")
        tk.Label(top, text="기준슬롯", font=("맑은 고딕", 9)).pack(side="left", padx=(8, 2))
        tk.Spinbox(top, from_=1, to=DOLL_SLOTS, textvariable=self._doll_pw["src"],
                   width=3, font=("맑은 고딕", 9)).pack(side="left")
        _h = ("번호칸을 누르면 [그대로 ↔ 삭제] 전환,  [위치찍기]를 누르면 그 번호를 바꿀 자리를 화면에서 찍습니다." +
              chr(10) + "저장 후 슬롯 좌표 팝업에서 프리셋 버튼을 누르면 그 번호들만 바뀝니다.")
        tk.Label(win, text=_h, font=("맑은 고딕", 8), fg="#555",
                 justify="left").pack(anchor="w", padx=10)
        lg = tk.Frame(win); lg.pack(anchor="w", padx=10, pady=(2, 0))
        tk.Label(lg, text=" 그대로 ", font=("맑은 고딕", 8), bg="#dfe3e6").pack(side="left")
        tk.Label(lg, text=" ✖ 삭제 ", font=("맑은 고딕", 8), bg="#c0392b", fg="white").pack(side="left", padx=4)
        tk.Label(lg, text=" 📍 위치변경 ", font=("맑은 고딕", 8), bg="#f39c12", fg="black").pack(side="left")
        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        for jx in range(DOLL_CLICKS):
            cell = tk.Frame(grid, bd=1, relief="groove", padx=2, pady=1)
            cell.grid(row=jx // 6, column=jx % 6, padx=3, pady=3, sticky="n")
            tk.Label(cell, text=str(jx + 1), font=("맑은 고딕", 8, "bold"), fg="#555").pack()
            srow = tk.Frame(cell); srow.pack(pady=(1, 0))
            sb = tk.Button(srow, text="그대로", font=("맑은 고딕", 8), width=8,
                           bg="#dfe3e6", command=lambda x=jx: self._doll_preset_toggle(x))
            sb.pack(side="left")
            tk.Button(srow, text="👁", font=("맑은 고딕", 8), width=2,
                      bg="#566573", fg="white",
                      command=lambda x=jx: self._doll_preset_preview(x)).pack(side="left", padx=(2, 0))
            pb = tk.Button(cell, text="위치찍기", font=("맑은 고딕", 8), width=8,
                           bg="#95a5a6", fg="white",
                           command=lambda x=jx: self._doll_preset_pick(x))
            pb.pack(pady=(1, 0))
            self._doll_pw["cells"].append({"state": sb, "pick": pb})
        bot = tk.Frame(win); bot.pack(pady=(2, 10))
        tk.Button(bot, text="💾 저장", font=("맑은 고딕", 10, "bold"), bg="#1e8449",
                  fg="white", width=10, command=self._doll_preset_store).pack(side="left", padx=4)
        tk.Button(bot, text="↺ 전부 그대로", font=("맑은 고딕", 9), bg="#7f8c8d", fg="white",
                  command=self._doll_preset_clear).pack(side="left", padx=4)
        tk.Button(bot, text="닫기", font=("맑은 고딕", 9), command=win.destroy).pack(side="left", padx=4)
        self._doll_preset_load(0)

    def _doll_preset_load(self, pi):
        pw = self._doll_pw
        pr = self._doll_presets()[pi]
        pw["pi"] = pi
        pw["items"] = {k: dict(v) for k, v in (pr.get("items") or {}).items()}
        pw["name"].set(pr.get("name", ""))
        pw["src"].set(str(pr.get("src", 1)))
        for x, b in enumerate(pw["tabs"]):
            b.config(relief="sunken" if x == pi else "raised", bd=4 if x == pi else 1)
        self._doll_preset_refresh()

    def _doll_preset_refresh(self):
        for jx, c in enumerate(self._doll_pw["cells"]):
            it = self._doll_pw["items"].get(str(jx))
            if not it:
                c["state"].config(text="그대로", bg="#dfe3e6", fg="black")
                c["pick"].config(text="위치찍기", bg="#95a5a6", fg="white", relief="raised", bd=1)
            elif it.get("act") == "del":
                c["state"].config(text="✖ 삭제", bg="#c0392b", fg="white")
                c["pick"].config(text="위치찍기", bg="#95a5a6", fg="white", relief="raised", bd=1)
            else:
                rel = it.get("rel") or [0, 0]
                c["state"].config(text="📍 위치변경", bg="#f39c12", fg="black")
                c["pick"].config(text="✔ " + str(rel[0]) + "," + str(rel[1]),
                                 bg="#f1c40f", fg="black", relief="sunken", bd=3)

    def _doll_preset_preview(self, jx):
        """이 번호가 어디를 클릭하는지 점으로 보여준다."""
        pw = self._doll_pw
        try:
            base = int(pw["src"].get()) - 1
        except Exception:
            base = 0
        it = pw["items"].get(str(jx))
        rects = self._client_rects_by_slot()
        if it and it.get("act") == "mov":
            rel = it.get("rel") or [0, 0]
            pos = ([rel[0] + rects[base][0], rel[1] + rects[base][1]]
                   if (rects and not pw.get("abs")) else list(rel))
            note = "프리셋 지정 위치"
        else:
            cs = self.cfg["doll_slots"][base].get("coords", [])
            pos = cs[jx] if jx < len(cs) else None
            note = "기준 슬롯 #" + str(base + 1) + " 현재 좌표"
        if not pos:
            self.status.set("클릭 " + str(jx + 1) + "번: 보여줄 좌표가 없습니다")
            return
        self.status.set("👁 클릭 " + str(jx + 1) + "번 — " + note +
                        " (" + str(pos[0]) + "," + str(pos[1]) + ")")
        _PresetDotOverlay(self, jx + 1, pos, note)

    def _doll_preset_toggle(self, jx):
        pw = self._doll_pw
        if not pw["items"].get(str(jx)):
            pw["items"][str(jx)] = {"act": "del"}
        else:
            pw["items"].pop(str(jx), None)
        self._doll_preset_refresh()

    def _doll_preset_pick(self, jx):
        try:
            base = int(self._doll_pw["src"].get()) - 1
        except Exception:
            base = 0
        self._doll_pick = {"jx": jx, "base": base}
        self.status.set(f"📍 클릭 {jx+1} 번을 바꿀 위치를 3초 후 화면에서 클릭하세요")
        self.after(1500, lambda: CoordOverlay(self, mode="dollpreset"))

    def on_dollpreset_coord(self, x, y):
        pm = getattr(self, "_doll_pick", None) or {}
        self._doll_pick = None
        jx, base = pm.get("jx", 0), pm.get("base", 0)
        rects = self._client_rects_by_slot()
        hit = None
        if rects:
            for si, (l, t, r, b_) in enumerate(rects):
                if l <= x <= r and t <= y <= b_:
                    hit = si; break
            if hit is not None:
                base = hit
                try: self._doll_pw["src"].set(str(base + 1))
                except Exception: pass
            rel = [x - rects[base][0], y - rects[base][1]]
            self._doll_pw["abs"] = False
        else:
            rel = [x, y]
            self._doll_pw["abs"] = True
        self._doll_pw["items"][str(jx)] = {"act": "mov", "rel": rel}
        self._doll_preset_refresh()
        try:
            w = getattr(self, "_doll_pw_win", None)
            if w and w.winfo_exists(): w.deiconify(); w.lift()
        except Exception:
            pass
        self.status.set(f"✔ 클릭 {jx+1} 번 위치 지정: ({x},{y})")

    def _doll_preset_clear(self):
        self._doll_pw["items"] = {}
        self._doll_preset_refresh()
        self.status.set("전부 그대로로 되돌림 — [💾 저장]을 눌러야 반영됩니다")

    def _doll_preset_store(self):
        pw = self._doll_pw; pi = pw["pi"]
        try: src = int(pw["src"].get())
        except Exception: src = 1
        pres = self._doll_presets()
        pres[pi] = {"name": pw["name"].get().strip() or self.DOLL_PRESET_NAMES[pi],
                    "src": src, "abs": bool(pw.get("abs")),
                    "items": {k: dict(v) for k, v in pw["items"].items()}}
        self.cfg["_doll_presets"] = pres
        save_cfg(self.cfg)
        for x, b in enumerate(pw["tabs"]):
            try: b.config(text=pres[x].get("name") or f"P{x+1}")
            except Exception: pass
        dels = sorted(int(k) + 1 for k, v in pw["items"].items() if v.get("act") == "del")
        movs = sorted(int(k) + 1 for k, v in pw["items"].items() if v.get("act") == "mov")
        self.status.set(f"💾 [{pres[pi]['name']}] 저장 — 삭제 {dels or '없음'} / 이동 {movs or '없음'}")

    def _open_doll_slot(self, idx):
        """슬롯 하나의 18좌표 등록 팝업 (셀의 '좌표 x/18' 클릭 시)."""
        if getattr(self, "_doll_pop_win", None) and self._doll_pop_win.winfo_exists():
            try: self._doll_pop_win.destroy()
            except Exception: pass
        win = tk.Toplevel(self); self._doll_pop_win = win; self._doll_pop_slot = idx
        win.title(f"🧸 인형탐험 #{idx+1:02d} 좌표 등록")
        win.attributes("-topmost", True)

        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        tk.Label(top, text=f"#{idx+1:02d}  이름", font=("맑은 고딕", 9, "bold")).pack(side="left")
        nv = tk.StringVar(value=self.cfg["doll_slots"][idx].get("name", "미등록"))
        self._doll_pop_name = nv
        ent = tk.Entry(top, textvariable=nv, font=("맑은 고딕", 9), width=14)
        ent.pack(side="left", padx=6)
        self._build_doll_preset_row(win, idx)   # 프리셋 P1~P4
        ent.bind("<FocusOut>", lambda e: self._save_doll_pop_name())
        ent.bind("<Return>",   lambda e: self._save_doll_pop_name())

        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        self._doll_pop_vars = []; self._doll_pop_btns = []
        coords = self.cfg["doll_slots"][idx].get("coords", [None]*DOLL_CLICKS)
        for j in range(DOLL_CLICKS):
            cc = tk.Frame(grid); cc.grid(row=j//6, column=j%6, padx=4, pady=4)
            tk.Label(cc, text=f"{j+1}", font=("맑은 고딕", 7), fg="#555").pack()
            on = j < len(coords) and coords[j]
            cv = tk.StringVar(value="✔" if on else "✗")
            self._doll_pop_vars.append(cv)
            b = tk.Button(cc, textvariable=cv, font=("맑은 고딕", 8), width=4, pady=2,
                          bg="#27ae60" if on else "#7f8c8d", fg="white",
                          command=lambda x=idx, c=j: self._reg_doll_click(x, c))
            b.pack(); self._doll_pop_btns.append(b)

        bot = tk.Frame(win); bot.pack(pady=(4,10))
        tk.Button(bot, text="👁 미리보기", font=("맑은 고딕", 8), bg="#566573", fg="white",
                  command=lambda: self._preview_doll(idx)).pack(side="left", padx=3)
        if idx > 0:
            tk.Button(bot, text="↑ 윗슬롯 복사", font=("맑은 고딕", 8), bg="#8e44ad", fg="white",
                      command=lambda: self._group_copy_doll_slot(idx)).pack(side="left", padx=3)
        tk.Button(bot, text="× 전체삭제", font=("맑은 고딕", 8), fg="white", bg="#c0392b",
                  command=lambda: self._del_doll(idx)).pack(side="left", padx=3)
        tk.Button(bot, text="닫기", font=("맑은 고딕", 8),
                  command=win.destroy).pack(side="left", padx=3)

    def _save_doll_pop_name(self):
        i = getattr(self, "_doll_pop_slot", None)
        if i is not None and getattr(self, "_doll_pop_name", None) is not None:
            self.cfg["doll_slots"][i]["name"] = self._doll_pop_name.get().strip() or "미등록"
            save_cfg(self.cfg)

    def _toggle_doll_enable(self, idx):
        cur = self.cfg["doll_slots"][idx].get("enabled", True)
        self.cfg["doll_slots"][idx]["enabled"] = not cur
        save_cfg(self.cfg)
        self._refresh_doll_display()

    def _refresh_doll_display(self):
        # 그리드 셀 (ON/OFF + 좌표 개수)
        if getattr(self, "_doll_enable_btns", None):
            for i in range(DOLL_SLOTS):
                s = self.cfg["doll_slots"][i]
                en = s.get("enabled", True)
                self._doll_enable_btns[i].config(text="ON" if en else "OFF",
                                                 bg="#27ae60" if en else "#95a5a6")
                reg = sum(1 for c in s.get("coords", []) if c)
                self._doll_coord_sv[i].set(f"좌표 {reg}/{DOLL_CLICKS}")
                try:
                    nm = (s.get("name") or "").strip()
                    nm = "" if nm == "미등록" else nm
                    if i < len(getattr(self, "_doll_name_vars", [])) \
                       and self._doll_name_vars[i].get() != nm:
                        self._doll_name_vars[i].set(nm)
                    _es = getattr(self, "_doll_name_ents", [])
                    if i < len(_es) and _es[i].winfo_exists():
                        _es[i].config(fg=self._name_color(nm))
                except Exception:
                    pass
        # 열린 좌표 등록 팝업의 18버튼 갱신
        pw = getattr(self, "_doll_pop_win", None)
        if pw and pw.winfo_exists():
            i = self._doll_pop_slot
            coords = self.cfg["doll_slots"][i].get("coords", [None]*DOLL_CLICKS)
            for j in range(DOLL_CLICKS):
                on = j < len(coords) and coords[j]
                self._doll_pop_vars[j].set("✔" if on else "✗")
                self._doll_pop_btns[j].config(bg="#27ae60" if on else "#7f8c8d")

    def _reg_doll_click(self, slot_idx, click_idx):
        self._save_doll_pop_name()
        self._doll_reg_idx  = slot_idx
        self._doll_reg_step = click_idx
        name = self.cfg["doll_slots"][slot_idx].get("name", f"#{slot_idx+1}")
        self.status.set(f"3초 후 [{name}] 좌표{click_idx+1} 위치 클릭하세요!")
        def _go():
            pw = getattr(self, "_doll_pop_win", None)
            if pw and pw.winfo_exists():
                try: pw.withdraw()   # 팝업이 타깃 가리지 않게 잠시 숨김
                except Exception: pass
            self.withdraw(); time.sleep(0.2); CoordOverlay(self, mode="doll")
        self.after(3000, _go)

    def on_doll_coord(self, x, y):
        idx, step = self._doll_reg_idx, self._doll_reg_step
        coords = self.cfg["doll_slots"][idx].get("coords", [None]*DOLL_CLICKS)
        while len(coords) < DOLL_CLICKS: coords.append(None)
        coords[step] = [x, y]
        self.cfg["doll_slots"][idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ 인형탐험 #{idx+1} 좌표{step+1} 등록: ({x},{y})")
        self.deiconify()
        pw = getattr(self, "_doll_pop_win", None)   # 등록 팝업 다시 보이기
        if pw and pw.winfo_exists():
            try: pw.deiconify(); pw.lift()
            except Exception: pass

    def _del_doll(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"인형탐험 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["doll_slots"][idx]["coords"] = [None]*DOLL_CLICKS
        save_cfg(self.cfg); self._refresh_doll_display()

    def _test_doll(self, idx):
        h = self.cfg["doll_slots"][idx]
        coords = [c for c in h.get("coords", []) if c]
        if not coords:
            messagebox.showwarning("등록 필요", f"#{idx+1} 슬롯에 등록된 좌표가 없습니다."); return
        # 슬롯별 실행도 잠금+대기열 — 연속으로 눌러두면 한 슬롯 완료 후 다음 슬롯 실행
        busy_name = f"인형탐험 #{idx+1:02d}"
        if not self._try_busy_or_queue(busy_name, lambda: self._test_doll(idx)): return
        self._doll_stop = False
        name = h.get("name", f"#{idx+1}")
        self._minimize_all()
        def run():
            try:
                _clicked = 0
                for j, c in enumerate(h.get("coords", [])):
                    if not c: continue
                    if getattr(self, "_doll_stop", False): break
                    if _clicked == 0:
                        time.sleep(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX))  # 첫 클릭 전 여유
                    self.status.set(f"[{name}] 좌표{j+1} 실행...")
                    click_at(*c)
                    _clicked += 1
                    time.sleep(random.uniform(DOLL_MIN, DOLL_MAX))  # 좌표 간 간격
                self.status.set(f"✔ [{name}] 슬롯 완료!")
            except Exception as e:
                self.status.set(f"오류: {e}")
            finally:
                self._clear_busy(busy_name)   # 잠금 해제 → 대기열의 다음 슬롯이 이어서 실행
                self.deiconify()
        threading.Thread(target=run, daemon=True).start()

    def _preview_doll(self, idx):
        coords = self.cfg["doll_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다"); return
        name = self.cfg["doll_slots"][idx].get("name", f"#{idx+1:02d}")
        def rereg(dot_idx):
            self._doll_reg_idx  = idx
            self._doll_reg_step = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="doll"))
        def _save(dot_idx, nx, ny):
            self.cfg["doll_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_doll_display()
            self.status.set(f"✔ 인형탐험 #{idx+1:02d} 좌표{dot_idx+1} 이동 저장: ({nx},{ny})")
        self._open_dot_preview(f"인형탐험 #{idx+1:02d} {name}", dots, rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _group_copy_doll_slot(self, idx):
        import copy
        src = self.cfg["doll_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다"); return
        self.cfg["doll_slots"][idx]["coords"] = copy.deepcopy(src)
        _pn = (self.cfg["doll_slots"][idx-1].get("name") or "").strip()
        if _pn and _pn != "미등록":
            self.cfg["doll_slots"][idx]["name"] = _pn
            self._doll_preset_ts = time.time()
            try: self._doll_name_vars[idx].set(_pn)
            except Exception: pass
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ #{idx:02d} → #{idx+1:02d} 좌표·이름 복사 완료")

    def _group_copy_doll(self):
        import copy
        src = self.cfg["doll_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다"); return
        for i in range(1, DOLL_SLOTS):
            self.cfg["doll_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_doll_display()
        self.status.set(f"✔ #01 좌표 → #02~#{DOLL_SLOTS:02d} 전체 복사 완료")

    # ── 공용 4×4 슬롯 그리드 (인형탐험 스타일 — 세로 열우선, 팝업 등록, 복사/붙임/미리보기) ──
    def _grid_spec(self, fkey):
        S = {
            "past":    dict(title="과거섬",   key="past_slots",    clicks=PAST_CLICKS,    color="#c0392b",
                            reg=self._reg_past_click,    test=self._test_past,    prev=self._preview_past,    delete=self._del_past),
            "mail":    dict(title="우편함",   key="mail_slots",    clicks=MAIL_CLICKS,    color="#2471a3",
                            reg=self._reg_mail_click,    test=self._test_mail,    prev=self._preview_mail,    delete=self._del_mail),
            "dungeon": dict(title="변신확인용", key="dungeon_slots", clicks=DUNGEON_CLICKS, color="#d35400",
                            reg=self._reg_dungeon_click, test=self._test_dungeon, prev=self._preview_dungeon, delete=self._del_dungeon),
            "sched":   dict(title="스케줄",   key="sched_slots",   clicks=SCHED_CLICKS,   color="#16a085",
                            reg=self._reg_sched_click,   test=self._test_sched,   prev=self._preview_sched,   delete=self._del_sched,
                            locked=(0,)),
            "hunt":    dict(title="사냥",     key="hunt_slots",    clicks=HUNT_CLICKS,    color="#27ae60",
                            reg=self._reg_hunt_click,    test=self._test_hunt,    prev=self._preview_hunt,    delete=self._del_hunt,
                            enable=True, assign=True),
            "pass":    dict(title="패스권",   key="pass_slots",    clicks=PASS_CLICKS,    color="#6c3483",
                            reg=self._reg_pass_click,    test=self._test_pass,    prev=self._preview_pass,    delete=self._del_pass),
            "item":    dict(title="아이템정리", key="item_slots",   clicks=SCHED_CLICKS,   color="#7d6608",
                            reg=self._reg_item_click,    test=self._test_item,    prev=self._preview_item,    delete=self._del_item),
            "dollchk": dict(title="인형확인용", key="dollchk_slots", clicks=DUNGEON_CLICKS, color="#b9770e",
                            reg=lambda s, c: self._reg_dgn2_click("dollchk", s, c),
                            test=lambda i: self._test_dgn2("dollchk", i),
                            prev=lambda i: self._preview_dgn2("dollchk", i),
                            delete=lambda i: self._del_dgn2("dollchk", i)),
            "relic":   dict(title="성물확인용", key="relic_slots",   clicks=DUNGEON_CLICKS, color="#117864",
                            reg=lambda s, c: self._reg_dgn2_click("relic", s, c),
                            test=lambda i: self._test_dgn2("relic", i),
                            prev=lambda i: self._preview_dgn2("relic", i),
                            delete=lambda i: self._del_dgn2("relic", i)),
            "knight":  dict(title="던전끝! 흑기사!!", key="knight_slots",
                            clicks=KNIGHT_CLICKS, color="#212f3d", enable=True, sel=True,
                            reg=lambda s, c: self._reg_dgn2_click("knight", s, c),
                            test=lambda i: self._test_dgn2("knight", i),
                            prev=lambda i: self._preview_dgn2("knight", i),
                            delete=lambda i: self._del_dgn2("knight", i)),
            "dragon":  dict(title="용던고고!!!", key="dragon_slots", clicks=DRAGON_CLICKS,
                            color="#a04000", enable=True, sel=True, img=True,
                            reg=lambda s, c: self._reg_dgn2_click("dragon", s, c),
                            test=lambda i: self._test_dgn2("dragon", i),
                            prev=lambda i: self._preview_dgn2("dragon", i),
                            delete=lambda i: self._del_dgn2("dragon", i)),
            "fix":     dict(title="🩹 복구", key="fix_slots", clicks=FIX_CLICKS,
                            color="#7d3c98", enable=True, sel=True, img=True,
                            reg=lambda s, c: self._reg_dgn2_click("fix", s, c),
                            test=lambda i: self._test_dgn2("fix", i),
                            prev=lambda i: self._preview_dgn2("fix", i),
                            delete=lambda i: self._del_dgn2("fix", i)),
            "market":  dict(title="거래소검색", key="market_slots", clicks=MARKET_CLICKS,
                            color="#2874a6", opts=True, paste=True, sel=True,
                            reg=lambda s, c: self._reg_dgn2_click("market", s, c),
                            test=lambda i: self._test_dgn2("market", i),
                            prev=lambda i: self._preview_dgn2("market", i),
                            delete=lambda i: self._del_dgn2("market", i)),
            "coupon":  dict(title="쿠폰등록",  key="coupon_slots",  clicks=COUPON_CLICKS,  color="#1f618d",
                            reg=lambda s, c: self._reg_dgn2_click("coupon", s, c),
                            test=lambda i: self._test_dgn2("coupon", i),
                            prev=lambda i: self._preview_dgn2("coupon", i),
                            delete=lambda i: self._del_dgn2("coupon", i)),
            "eventshop": dict(title="이벤트상점", key="eventshop_slots", clicks=EVENTSHOP_CLICKS, color="#0e6655",
                            reg=lambda s, c: self._reg_dgn2_click("eventshop", s, c),
                            test=lambda i: self._test_dgn2("eventshop", i),
                            prev=lambda i: self._preview_dgn2("eventshop", i),
                            delete=lambda i: self._del_dgn2("eventshop", i)),
            "circus3": dict(title="서커스 이벤트퀘스트", key="circus3_slots",
                            clicks=CIRCUS3_CLICKS, color="#4a235a", opts=True,
                            reg=lambda s, c: self._reg_dgn2_click("circus3", s, c),
                            test=lambda i: self._test_dgn2("circus3", i),
                            prev=lambda i: self._preview_dgn2("circus3", i),
                            delete=lambda i: self._del_dgn2("circus3", i)),
            "circus2": dict(title="서커스 이벤트실행", key="circus2_slots",
                            clicks=CIRCUS2_CLICKS, color="#5b2c6f", opts=True,
                            reg=lambda s, c: self._reg_dgn2_click("circus2", s, c),
                            test=lambda i: self._test_dgn2("circus2", i),
                            prev=lambda i: self._preview_dgn2("circus2", i),
                            delete=lambda i: self._del_dgn2("circus2", i)),
            "circus":  dict(title="서커스 이벤트등록", key="circus_slots", clicks=CIRCUS_CLICKS, color="#7d3c98",
                            opts=True,        # 칸마다 간격(초)·휠칸수 직접 지정
                            reg=lambda s, c: self._reg_dgn2_click("circus", s, c),
                            test=lambda i: self._test_dgn2("circus", i),
                            prev=lambda i: self._preview_dgn2("circus", i),
                            delete=lambda i: self._del_dgn2("circus", i)),
            "fish":    dict(title="낚시녹임",  key="fish_slots",    clicks=FISH_CLICKS,    color="#1a5276",
                            reg=lambda s, c: self._reg_dgn2_click("fish", s, c),
                            test=lambda i: self._test_dgn2("fish", i),
                            prev=lambda i: self._preview_dgn2("fish", i),
                            delete=lambda i: self._del_dgn2("fish", i)),
            "tj":      dict(title="TJ성공!!", key="tj_slots",       clicks=TJ_CLICKS,      color="#ad1457",
                            reg=self._reg_tj_click,      test=self._test_tj,      prev=self._preview_tj,      delete=self._del_tj),
        }
        return S[fkey]

    def _build_slot_grid(self, parent, fkey):
        """16슬롯을 화면 배치와 같은 4×4(세로 열우선)로 표시. 셀=[번호(+ON)] [좌표 x/N] [▶실행] [복사|붙임|👁]."""
        sp = self._grid_spec(fkey)
        if not hasattr(self, "_grid_state"):
            self._grid_state = {}
        st = self._grid_state.setdefault(fkey, {})
        st["cnt_vars"] = []; st["enable_btns"] = []
        if not hasattr(self, "_grid_selbtns"):
            self._grid_sel = {}; self._grid_selbtns = {}
        self._grid_selbtns[fkey] = []
        st["pop"] = None; st["pop_slot"] = None
        _top = tk.Frame(parent); _top.pack(pady=(4, 0))
        tk.Button(_top, text="👁 전체 좌표 보기", font=("맑은 고딕", 8),
                  bg="#566573", fg="white",
                  command=lambda f=fkey: self._grid_preview_all(f)).pack(side="left")
        # 📋 전체붙임 — 복사한 슬롯을 16슬롯 전부에 붙인다 (2026-08-29 사용자 요청).
        # 붙일 때 클라이언트 창 위치를 슬롯마다 자동보정하므로 좌표가 맞는다.
        tk.Button(_top, text="📋 전체붙임", font=("맑은 고딕", 8, "bold"),
                  bg="#1a5276", fg="white", activebackground="#154360",
                  command=lambda f=fkey: self._grid_paste_all(f)).pack(side="left", padx=(4, 0))
        wg = tk.Frame(parent); wg.pack(padx=6, pady=4)
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg, bd=1, relief="groove", padx=3, pady=2)
            cell.grid(row=r, column=c, padx=4, pady=3, sticky="n")
            top = tk.Frame(cell); top.pack()
            tk.Label(top, text=f"{idx+1:02d}", font=("맑은 고딕", 9, "bold"), fg="#555").pack(side="left")
            if sp.get("enable"):
                eb = tk.Button(top, text="ON", font=("맑은 고딕", 7, "bold"), width=4,
                               bg="#27ae60", fg="white", pady=0,
                               command=lambda x=idx, f=fkey: self._toggle_slot_enable(f, x))
                eb.pack(side="left", padx=(4, 0))
                st["enable_btns"].append(eb)
            sv = tk.StringVar(value="좌표 0/%d" % sp["clicks"])
            st["cnt_vars"].append(sv)
            tk.Button(cell, textvariable=sv, font=("맑은 고딕", 8, "bold"),
                      bg=sp["color"], fg="white", width=10,
                      command=lambda x=idx, f=fkey: self._open_grid_slot(f, x)).pack(pady=(3, 0))
            tk.Button(cell, text="▶ 실행", font=("맑은 고딕", 7), bg="#1e8449", fg="white", width=10,
                      command=lambda x=idx, f=fkey: self._grid_spec(f)["test"](x)).pack(pady=(2, 1))
            row3 = tk.Frame(cell); row3.pack(pady=(0, 1))
            tk.Button(row3, text="복사", font=("맑은 고딕", 6), bg="#2980b9", fg="white", width=3,
                      command=lambda x=idx, f=fkey: self._grid_copy(f, x)).pack(side="left", padx=(0, 2))
            tk.Button(row3, text="붙임", font=("맑은 고딕", 6), bg="#8e44ad", fg="white", width=3,
                      command=lambda x=idx, f=fkey: self._grid_paste(f, x)).pack(side="left", padx=(0, 2))
            tk.Button(row3, text="👁", font=("맑은 고딕", 6), bg="#566573", fg="white", width=2,
                      command=lambda x=idx, f=fkey: self._grid_spec(f)["prev"](x)).pack(side="left")
            if sp.get("sel"):
                if not hasattr(self, "_grid_sel"):
                    self._grid_sel = {}; self._grid_selbtns = {}
                self._grid_sel.setdefault(fkey, set())
                pb = tk.Button(cell, text="+", font=("맑은 고딕", 7, "bold"), width=10,
                               bg="#dfe3e6", fg="#e67e22",
                               command=lambda x=idx, f=fkey: self._grid_sel_toggle(f, x))
                pb.pack(pady=(1, 0))
                self._grid_selbtns.setdefault(fkey, []).append(pb)
        self._refresh_slot_grids(fkey)

    def _open_grid_slot(self, fkey, idx):
        """슬롯 좌표 등록 팝업 — 클릭N 버튼(✔/✗), 이름, 전체삭제."""
        sp = self._grid_spec(fkey)
        st = self._grid_state[fkey]
        old = st.get("pop")
        if old and old.winfo_exists():
            try: old.destroy()
            except Exception: pass
        win = tk.Toplevel(self); st["pop"] = win; st["pop_slot"] = idx
        win.title(f"{sp['title']} #{idx+1:02d} 좌표 등록")
        win.attributes("-topmost", True)
        slot = self.cfg[sp["key"]][idx]
        top = tk.Frame(win); top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text=f"#{idx+1:02d}  이름", font=("맑은 고딕", 9, "bold")).pack(side="left")
        nv = tk.StringVar(value=slot.get("name", "미등록"))
        ent = tk.Entry(top, textvariable=nv, font=("맑은 고딕", 9), width=14)
        ent.pack(side="left", padx=6)
        def _save_name(e=None):
            self.cfg[sp["key"]][idx]["name"] = nv.get().strip() or "미등록"
            save_cfg(self.cfg)
        ent.bind("<FocusOut>", _save_name); ent.bind("<Return>", _save_name)
        grid = tk.Frame(win); grid.pack(padx=10, pady=6)
        st["pop_vars"] = []; st["pop_btns"] = []; st["pop_pvars"] = []
        locked = sp.get("locked", ())
        coords = slot.get("coords", [None] * sp["clicks"])
        for j in range(sp["clicks"]):
            cc = tk.Frame(grid); cc.grid(row=j // 6, column=j % 6, padx=4, pady=4)
            lk = j in locked
            tk.Label(cc, text=(f"{j+1}🔒" if lk else f"{j+1}"), font=("맑은 고딕", 7),
                     fg="#c0392b" if lk else "#555").pack()
            on = j < len(coords) and coords[j]
            cv = tk.StringVar(value="✔" if on else "✗")
            st["pop_vars"].append(cv)
            if lk:
                cmd = (lambda: self.status.set("🔒 이 좌표는 과거섬 클릭1과 동기화됩니다 — 과거섬에서 수정하세요"))
            else:
                cmd = (lambda x=idx, c=j, f=fkey: self._grid_spec(f)["reg"](x, c))
            b = tk.Button(cc, textvariable=cv, font=("맑은 고딕", 8), width=4, pady=2,
                          bg="#27ae60" if on else "#7f8c8d", fg="white", command=cmd)
            b.pack(); st["pop_btns"].append(b)
            # 좌표마다 ▶ — 그 좌표 하나만 눌러본다 (휠로 지정했으면 휠을 굴린다)
            tk.Button(cc, text="▶", font=("맑은 고딕", 7), width=4, pady=0,
                      bg="#1e8449", fg="white",
                      command=lambda x=idx, c=j, f=fkey:
                      self._test_grid_click(f, x, c)).pack(pady=(1, 0))
            if sp.get("img"):
                # 🖼 — 이 자리에서 찾을 '그림'을 드래그로 잘라 저장한다.
                #      그림이 있으면 실행 때 그림을 찾아 누르고, 못 찾으면 그 슬롯은 끝.
                _cnt = len(img_list(fkey, j))
                _has = _cnt > 0
                ib = tk.Button(cc, text=("🖼" if not _cnt else
                                         ("🖼있음" if _cnt == 1 else f"🖼{_cnt}장")),
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg=("#8e44ad" if _has else "#5d6d7e"), fg="white")
                ib.config(command=lambda x=idx, c=j, f=fkey, b_=ib:
                          self._grab_click_image(f, x, c, b_))
                ib.pack(pady=(1, 0))
                if _has:      # 오른쪽 클릭 = 그 그림 지우기
                    ib.bind("<Button-3>", lambda _e, c=j, f=fkey, b_=ib:
                            self._del_click_image(f, c, b_))
                # 👁 — '확인만' : 그 자리를 누르지 않고 그림이 보이는지만 본다.
                #      보이면 통과, 안 보이면 그 슬롯 중단 (예: '무료' 글자 확인)
                _chk = is_check_only(fkey, j)
                kb = tk.Button(cc, text=("👁확인만" if _chk else "👁"),
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg=("#117a65" if _chk else "#5d6d7e"), fg="white")
                kb.config(command=lambda c=j, f=fkey, b_=kb:
                          self._toggle_check_only(f, c, b_))
                kb.pack(pady=(1, 0))
                # ⛔ — 이 그림이 보이면 누르지 않고 ESC 로 취소하고 그 슬롯을 끝낸다
                #      (재화를 쓰려는 창을 만났을 때 빠져나오는 안전장치)
                _hasn = has_no_img(fkey, j)
                nb = tk.Button(cc, text=("⛔있음" if _hasn else "⛔"),
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg=("#c0392b" if _hasn else "#5d6d7e"), fg="white")
                nb.config(command=lambda x=idx, c=j, f=fkey, b_=nb:
                          self._grab_no_image(f, x, c, b_))
                nb.pack(pady=(1, 0))
                if _hasn:     # 오른쪽 클릭 = 금지 그림 지우기
                    nb.bind("<Button-3>", lambda _e, c=j, f=fkey, b_=nb:
                            self._del_no_image(f, c, b_))
                # 📐 — 그 그림을 '어디에서 찾을지' 범위를 드래그로 정한다.
                #      클라 창 기준으로 저장돼 16슬롯 전부에 그대로 적용된다.
                _hasa = area_is_set(fkey, j)
                ab = tk.Button(cc, text=("📐범위" if _hasa else "📐"),
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg=("#1a5276" if _hasa else "#5d6d7e"), fg="white")
                ab.config(command=lambda x=idx, c=j, f=fkey, b_=ab:
                          self._grab_click_area(f, x, c, b_))
                ab.pack(pady=(1, 0))
                if _hasa:     # 오른쪽 클릭 = 범위 지우기 (창 전체에서 찾는다)
                    ab.bind("<Button-3>", lambda _e, c=j, f=fkey, b_=ab:
                            self._del_click_area(f, c, b_))
                # 가운데(휠) 클릭 = 실제로 뜬 자리들로 범위를 자동 계산해 저장
                ab.bind("<Button-2>", lambda _e, c=j, f=fkey, b_=ab:
                        self._auto_click_area(f, c, b_))
                # 🔍 — 지금 찾아본다. 최고 일치도와 결과를 팝업으로 크게 보여준다.
                #      오른쪽 클릭 = 일치 기준 낮추기/올리기 (작은 그림은 낮춰야 잡힌다)
                tb = tk.Button(cc, text=f"🔍{img_thr(fkey, j):.2f}",
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg="#7d6608", fg="white")
                tb.config(command=lambda x=idx, c=j, f=fkey, b_=tb:
                          self._test_click_image(f, x, c, b_))
                tb.pack(pady=(1, 0))
                tb.bind("<Button-3>", lambda _e, c=j, f=fkey, b_=tb:
                        self._cycle_img_thr(f, c, b_))
                # 🎯 — 같은 그림이 여러 개일 때 어느 것을 누를지 (맨위/맨아래…)
                pb = tk.Button(cc, text=PICK_TXT[img_pick(fkey, j)],
                               font=("맑은 고딕", 7), width=4, pady=0,
                               bg="#117864", fg="white")
                pb.config(command=lambda c=j, f=fkey, b_=pb:
                          self._cycle_img_pick(f, c, b_))
                pb.pack(pady=(1, 0))
            if sp.get("opts"):
                # ㅡ 칸: 다음 좌표까지 기다릴 초 (비우면 기본), 아래는 휠 굴릴 칸수(0=클릭)
                gl = slot.get("gap_list") or []
                gv = tk.StringVar(value=(str(gl[j]) if j < len(gl) and gl[j] not in (None, "") else ""))
                ge = tk.Entry(cc, textvariable=gv, font=("맑은 고딕", 7), width=4,
                              justify="center", relief="solid", bd=1)
                ge.pack(pady=(1, 0))
                def _sv_gap(*_a, x=idx, c=j, v=gv, f=fkey):
                    self._grid_set_list(f, x, "gap_list", c, v.get().strip())
                gv.trace_add("write", _sv_gap)
                if sp.get("paste"):
                    # 간격 아래에 '붙임' — 체크한 좌표 '다음'에 적어둔 글을 붙여넣는다
                    pl = slot.get("paste_list") or []
                    pv = tk.BooleanVar(value=bool(pl[j]) if j < len(pl) else False)
                    st["pop_pvars"].append(pv)
                    tk.Checkbutton(cc, text="붙임", font=("맑은 고딕", 7), variable=pv,
                                   command=lambda x=idx, c=j, f=fkey:
                                   self._pick_paste(f, x, c)).pack(pady=(1, 0))
                else:
                    # 휠 — 칸수를 직접 적고(0=그냥 클릭), ▲/▼ 로 방향을 고른다
                    # (예: 100 + ▼ = 아래로 100칸. 저장은 부호로: 아래는 음수)
                    wl = slot.get("wheel_list") or []
                    raw = int(wl[j]) if (j < len(wl) and wl[j]) else 0
                    wf = tk.Frame(cc); wf.pack(pady=(1, 0))
                    wv = tk.StringVar(value=str(abs(raw)))
                    dv = tk.StringVar(value=("▼" if raw < 0 else "▲"))
                    we = tk.Entry(wf, textvariable=wv, font=("맑은 고딕", 7), width=3,
                                  justify="center", relief="solid", bd=1)
                    we.pack(side="left")
                    db = tk.Button(wf, textvariable=dv, font=("맑은 고딕", 7, "bold"),
                                   width=1, pady=0,
                                   bg=("#7b241c" if raw < 0 else "#1a5276"), fg="white")
                    db.pack(side="left", padx=(1, 0))

                    def _sv_wheel(*_a, x=idx, c=j, v=wv, d=dv, f=fkey):
                        try:
                            n = abs(int(str(v.get()).strip() or 0))
                        except Exception:
                            n = 0
                        if d.get() == "▼":
                            n = -n
                        self._grid_set_list(f, x, "wheel_list", c, n)

                    def _flip(x=idx, c=j, v=wv, d=dv, f=fkey, btn=db):
                        d.set("▲" if d.get() == "▼" else "▼")
                        btn.config(bg=("#7b241c" if d.get() == "▼" else "#1a5276"))
                        _sv_wheel(x=x, c=c, v=v, d=d, f=f)

                    db.config(command=_flip)
                    wv.trace_add("write", _sv_wheel)
        bot = tk.Frame(win); bot.pack(pady=(4, 10))
        if sp.get("assign"):
            tk.Button(bot, text="🖥 창 지정", font=("맑은 고딕", 8), bg="#8e44ad", fg="white",
                      command=lambda: self._assign_window(idx)).pack(side="left", padx=3)
        tk.Button(bot, text="👁 미리보기", font=("맑은 고딕", 8), bg="#566573", fg="white",
                  command=lambda: sp["prev"](idx)).pack(side="left", padx=3)
        tk.Button(bot, text="× 전체삭제", font=("맑은 고딕", 8), fg="white", bg="#c0392b",
                  command=lambda: sp["delete"](idx)).pack(side="left", padx=3)
        tk.Button(bot, text="닫기", font=("맑은 고딕", 8), command=win.destroy).pack(side="left", padx=3)

    def _pick_paste(self, fkey, idx, j):
        """붙여넣기 자리는 슬롯마다 한 곳만 — 체크하면 나머지는 자동으로 풀린다."""
        try:
            sp = self._grid_spec(fkey)
            st = self._grid_state[fkey]
            vars_ = st.get("pop_pvars") or []
            on = bool(vars_[j].get()) if j < len(vars_) else False
            for i, v in enumerate(vars_):
                if i != j:
                    v.set(False)
            self.cfg[sp["key"]][idx]["paste_list"] = [(i == j and on)
                                                      for i in range(sp["clicks"])]
            save_cfg(self.cfg)
            self.status.set(f"{sp['title']} #{idx+1:02d} 붙여넣기 자리 — "
                            + (f"클릭{j+1} 다음" if on else "없음"))
        except Exception:
            pass

    def _paste_idx_or_default(self, fkey, slot):
        """칸에 체크한 붙여넣기 자리 (없으면 예전 규칙 = 클릭5, 없으면 클릭4)."""
        j = self._paste_idx(slot)
        if j is not None:
            return j
        cs = slot.get("coords") or []
        return 4 if (len(cs) > 4 and cs[4]) else 3

    @staticmethod
    def _paste_idx(slot):
        """그 슬롯에서 체크해둔 붙여넣기 자리 (없으면 None)."""
        try:
            for i, v in enumerate(slot.get("paste_list") or []):
                if v:
                    return i
        except Exception:
            pass
        return None

    def _test_grid_click(self, fkey, idx, j):
        """좌표 하나만 눌러보기 — 등록한 자리가 맞는지 확인용."""
        try:
            sp = self._grid_spec(fkey)
            slot = self.cfg[sp["key"]][idx]
            coords = slot.get("coords") or []
            c = coords[j] if j < len(coords) else None
        except Exception:
            c = None
        if not c and has_img(fkey, j):
            # 그림만 지정한 자리 — 같은 슬롯의 다른 좌표로 어느 클라인지 찾는다
            c = slot_anchor(slot)
        if not c:
            self.status.set("그 자리에 등록된 좌표도, 그림도 없습니다"); return
        title = self._grid_spec(fkey)["title"]
        _im = " (그림을 찾아 그 자리를 클릭합니다)" if has_img(fkey, j) else ""
        self.status.set(f"{title} #{idx+1:02d} 좌표{j+1} — 0.8초 뒤 실행{_im}")
        # 실행 중에는 런처를 내려둔다 — 창이 클릭 자리를 가리면 안 먹는다
        try:
            self._minimize_all()
        except Exception:
            pass
        def _go():
            time.sleep(0.8)
            try:
                act = self._do_click_or_wheel(fkey, j, c, slot)
            except Exception as e:
                act = f"오류 {e}"
            self.after(0, lambda: self.status.set(
                f"{title} #{idx+1:02d} 좌표{j+1} {act} {tuple(c)}"))
        threading.Thread(target=_go, daemon=True).start()

    def _grid_set_list(self, fkey, idx, field, j, val):
        """슬롯의 gap_list / wheel_list 같은 '칸별 값'을 저장한다."""
        try:
            sp = self._grid_spec(fkey)
            slot = self.cfg[sp["key"]][idx]
            lst = list(slot.get(field) or [])
            while len(lst) < sp["clicks"]:
                lst.append(None if field == "gap_list" else 0)
            lst[j] = val
            slot[field] = lst
            save_cfg(self.cfg)
        except Exception:
            pass

    def _refresh_slot_grids(self, only=None):
        """그리드 셀(좌표 개수·ON/OFF)과 열린 등록 팝업(✔/✗) 갱신."""
        for fkey, st in getattr(self, "_grid_state", {}).items():
            if only and fkey != only:
                continue
            try:
                sp = self._grid_spec(fkey)
            except Exception:
                continue
            slots = self.cfg.get(sp["key"], [])
            for i, sv in enumerate(st.get("cnt_vars", [])):
                if i >= len(slots): break
                coords = slots[i].get("coords", [])
                sv.set(f"좌표 {sum(1 for c in coords if c)}/{sp['clicks']}")
            if sp.get("enable"):
                for i, eb in enumerate(st.get("enable_btns", [])):
                    try:
                        en = slots[i].get("enabled", True)
                        eb.config(text="ON" if en else "OFF", bg="#27ae60" if en else "#95a5a6")
                    except Exception:
                        pass
            pop = st.get("pop")
            if pop and pop.winfo_exists() and st.get("pop_slot") is not None:
                i = st["pop_slot"]
                if i < len(slots):
                    coords = slots[i].get("coords", [])
                    for j, cv in enumerate(st.get("pop_vars", [])):
                        on = j < len(coords) and coords[j]
                        cv.set("✔" if on else "✗")
                        try:
                            st["pop_btns"][j].config(bg="#27ae60" if on else "#7f8c8d")
                        except Exception:
                            pass

    def _grid_copy(self, fkey, idx):
        import copy
        sp = self._grid_spec(fkey)
        coords = self.cfg[sp["key"]][idx].get("coords", [])
        if not any(coords):
            self.status.set(f"{sp['title']} #{idx+1:02d} 복사할 좌표가 없습니다"); return
        slot = self.cfg[sp["key"]][idx]
        # 좌표뿐 아니라 칸별 간격·휠·붙임 자리도 같이 복사한다
        # (예전엔 좌표만 복사돼서 2번 슬롯부터 붙여넣기 자리가 기본값으로 돌아갔다)
        self._grid_clip = {"f": fkey, "src": idx, "coords": copy.deepcopy(coords),
                           "gap_list":   copy.deepcopy(slot.get("gap_list")),
                           "wheel_list": copy.deepcopy(slot.get("wheel_list")),
                           "paste_list": copy.deepcopy(slot.get("paste_list"))}
        self.status.set(f"📋 {sp['title']} #{idx+1:02d} 좌표 {sum(1 for c in coords if c)}개 "
                        f"+ 간격·붙임 자리 복사됨 — [붙임]을 누르세요")

    def _grid_paste(self, fkey, idx):
        """복사한 좌표를 붙여넣기 — 클라이언트 창 위치 자동보정 (인형탐험과 동일)."""
        import copy
        sp = self._grid_spec(fkey)
        clip = getattr(self, "_grid_clip", None)
        if not clip or clip.get("f") != fkey:
            self.status.set(f"먼저 {sp['title']} 슬롯에서 [복사]를 누르세요"); return
        shifted = copy.deepcopy(clip["coords"])
        src = clip["src"]; note = ""
        if src != idx:
            rects = self._client_rects_by_slot()
            if rects:
                dx = rects[idx][0] - rects[src][0]
                dy = rects[idx][1] - rects[src][1]
                for c in shifted:
                    if c:
                        c[0] += dx; c[1] += dy
                note = f" — 클라이언트 위치 자동보정 ({dx:+},{dy:+})"
            else:
                note = " — ⚠ 클라이언트 16개 감지 실패, 원본 위치 그대로"
        self.cfg[sp["key"]][idx]["coords"] = shifted
        for _f in ("gap_list", "wheel_list", "paste_list"):     # 설정도 함께
            if clip.get(_f) is not None:
                self.cfg[sp["key"]][idx][_f] = copy.deepcopy(clip[_f])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ {sp['title']} #{idx+1:02d} 붙여넣기 완료 (간격·붙임 자리 포함){note}")

    def _grid_paste_all(self, fkey):
        """📋 전체붙임 — 복사한 슬롯을 **16슬롯 전부**에 붙인다 (2026-08-29 사용자 요청).

        슬롯마다 클라이언트 창 위치를 자동보정하므로 좌표가 그 클라에 맞게 들어간다.
        복사한 원본 슬롯은 건드리지 않는다. 되돌릴 수 없으니 한 번 물어본다."""
        import copy
        sp = self._grid_spec(fkey)
        clip = getattr(self, "_grid_clip", None)
        if not clip or clip.get("f") != fkey:
            self.status.set(f"먼저 {sp['title']} 슬롯에서 [복사]를 누르세요"); return
        src = clip["src"]
        rects = self._client_rects_by_slot()
        if not rects:
            if not messagebox.askyesno(
                    "전체붙임",
                    "리니지M 클라이언트 16개를 못 찾았습니다. 위치 보정 없이 원본 좌표 그대로 전부 붙일까요? (좌표가 전부 같은 자리가 됩니다)"):
                return
        else:
            if not messagebox.askyesno(
                    "전체붙임",
                    f"#{src+1:02d} 의 좌표를 16슬롯 전부에 붙입니다. 슬롯마다 클라 위치로 자동보정됩니다. 기존 좌표는 덮어써집니다. 계속할까요?"):
                return
        slots = self.cfg.get(sp["key"]) or []
        cnt = 0
        for idx in range(min(16, len(slots))):
            if idx == src:
                continue                     # 원본은 그대로
            shifted = copy.deepcopy(clip["coords"])
            if rects:
                dx = rects[idx][0] - rects[src][0]
                dy = rects[idx][1] - rects[src][1]
                for c in shifted:
                    if c:
                        c[0] += dx; c[1] += dy
            slots[idx]["coords"] = shifted
            for _f in ("gap_list", "wheel_list", "paste_list"):
                if clip.get(_f) is not None:
                    slots[idx][_f] = copy.deepcopy(clip[_f])
            cnt += 1
        self.cfg[sp["key"]] = slots
        save_cfg(self.cfg); self._refresh_ui()
        _n = sum(1 for c in clip["coords"] if c)
        self.status.set(f"✔ {sp['title']} 전체붙임 완료 — #{src+1:02d} 의 좌표 {_n}개를 "
                        f"{cnt}개 슬롯에 붙였습니다"
                        + ("" if rects else " (⚠ 클라 감지 실패 — 위치 보정 없음)"))

    # ── 공용 그리드 (연속클릭/주말던전끄기 — 슬롯당 좌표 1개) ──
    def _build_flat_grid(self, parent, fkey):
        """좌표 1개짜리 기능용 4×4 그리드. 셀=[번호][좌표버튼=등록] [×|복사|붙임|👁]."""
        cfgs = {
            "seq":   dict(key="seq_slots",   color="#7d3c98", reg=self._reg_seq_coord,   dele=self._del_seq_coord,   vars_attr="_seq_slot_vars"),
            "slp":   dict(key="slp_slots",   color="#1f618d", reg=self._reg_slp_coord,   dele=self._del_slp_coord,   vars_attr="_slp_slot_vars"),
            "wdoff": dict(key="wdoff_slots", color="#5d6d7e", reg=self._reg_wdoff_coord, dele=self._del_wdoff_coord, vars_attr="_wdoff_slot_vars"),
        }
        sp = cfgs[fkey]
        slots = self.cfg.get(sp["key"]) or [None] * 16
        svlist = []
        setattr(self, sp["vars_attr"], svlist)
        wg = tk.Frame(parent); wg.pack(padx=6, pady=4)
        for idx in range(16):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(wg, bd=1, relief="groove", padx=3, pady=2)
            cell.grid(row=r, column=c, padx=4, pady=3, sticky="n")
            tk.Label(cell, text=f"{idx+1:02d}", font=("맑은 고딕", 9, "bold"), fg="#555").pack()
            sv = tk.StringVar()
            cc = slots[idx] if idx < len(slots) else None
            sv.set(f"({cc[0]},{cc[1]})" if cc else "미등록")
            svlist.append(sv)
            tk.Button(cell, textvariable=sv, font=("맑은 고딕", 7, "bold"),
                      bg=sp["color"], fg="white", width=11,
                      command=lambda x=idx, f=fkey: self._flat_spec(f)["reg"](x)).pack(pady=(2, 1))
            row3 = tk.Frame(cell); row3.pack(pady=(0, 1))
            tk.Button(row3, text="×", font=("맑은 고딕", 6), fg="red", width=2,
                      command=lambda x=idx, f=fkey: self._flat_del(f, x)).pack(side="left", padx=(0, 2))
            tk.Button(row3, text="복사", font=("맑은 고딕", 6), bg="#2980b9", fg="white", width=3,
                      command=lambda x=idx, f=fkey: self._flat_copy(f, x)).pack(side="left", padx=(0, 2))
            tk.Button(row3, text="붙임", font=("맑은 고딕", 6), bg="#8e44ad", fg="white", width=3,
                      command=lambda x=idx, f=fkey: self._flat_paste(f, x)).pack(side="left", padx=(0, 2))
            tk.Button(row3, text="👁", font=("맑은 고딕", 6), bg="#566573", fg="white", width=2,
                      command=lambda x=idx, f=fkey: self._flat_preview(f, x)).pack(side="left")
    def _slots_preview_all(self, title, key, prev_fn, refresh_fn=None):
        """섹션 전체 슬롯 좌표 미리보기 — 점 드래그/WASD=수정 저장, 점 클릭=해당 슬롯 미리보기."""
        slots = self.cfg.get(key) or []
        items, dots = [], []
        for si, s in enumerate(slots):
            for ci, c in enumerate(s.get("coords", [])):
                if c and len(c) >= 2:
                    items.append((si, ci))
                    dots.append((c[0], c[1], f"{si+1}-{ci+1}"))
        if not dots:
            self.status.set(f"{title}: 등록된 좌표가 없습니다"); return

        def rereg(dot_idx):
            if dot_idx is None:
                self.deiconify(); return
            prev_fn(items[dot_idx][0])   # 해당 슬롯 미리보기(점 클릭=재등록)로 이동

        def _flush():
            self._pa_save_job = None
            save_cfg(self.cfg)
            (refresh_fn or self._refresh_ui)()

        def _save(dot_idx, nx, ny):
            si, ci = items[dot_idx]
            self.cfg[key][si]["coords"][ci] = [nx, ny]
            # 그룹 이동은 점 수만큼 연속 호출됨 → 파일 저장/화면 갱신은 모아서 1회
            job = getattr(self, "_pa_save_job", None)
            if job:
                try: self.after_cancel(job)
                except Exception: pass
            self._pa_save_job = self.after(300, _flush)

        self._open_dot_preview(f"{title} — 전체 좌표", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _grid_preview_all(self, fkey):
        sp = self._grid_spec(fkey)
        self._slots_preview_all(sp["title"], sp["key"], sp["prev"])

    def _flat_preview_all(self, fkey):
        """연속클릭 등 1좌표 슬롯 섹션의 전체 좌표 미리보기 — 점 드래그=이동, 점 클릭=재등록."""
        sp = self._flat_spec(fkey)
        slots = self.cfg.get(sp["key"]) or []
        reg = [(i, c) for i, c in enumerate(slots) if c]
        if not reg:
            self.status.set(f"{sp['title']}: 등록된 좌표가 없습니다"); return
        dots = [(c[0], c[1], i + 1) for i, c in reg]

        def rereg(di):
            if di is None:
                self.deiconify(); return
            sp["reg"](reg[di][0])

        def _save(di, nx, ny):
            i = reg[di][0]
            slots[i] = [nx, ny]
            self.cfg[sp["key"]] = slots
            save_cfg(self.cfg)
            vl = getattr(self, sp["vars_attr"], None)
            if vl and i < len(vl): vl[i].set(f"({nx},{ny})")

        self._open_dot_preview(f"{sp['title']} — 전체 좌표", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _flat_spec(self, fkey):
        return {
            "seq":   dict(title="절전해제",     key="seq_slots",   reg=self._reg_seq_coord,   dele=self._del_seq_coord,   vars_attr="_seq_slot_vars"),
            "slp":   dict(title="절전모드",     key="slp_slots",   reg=self._reg_slp_coord,   dele=self._del_slp_coord,   vars_attr="_slp_slot_vars"),
            "wdoff": dict(title="주말던전끄기", key="wdoff_slots", reg=self._reg_wdoff_coord, dele=self._del_wdoff_coord, vars_attr="_wdoff_slot_vars"),
        }[fkey]

    def _flat_del(self, fkey, idx):
        self._flat_spec(fkey)["dele"](idx)

    def _flat_copy(self, fkey, idx):
        sp = self._flat_spec(fkey)
        slots = self.cfg.get(sp["key"]) or []
        c = slots[idx] if idx < len(slots) else None
        if not c:
            self.status.set(f"{sp['title']} #{idx+1:02d} 복사할 좌표가 없습니다"); return
        self._flat_clip = {"f": fkey, "src": idx, "coord": list(c)}
        self.status.set(f"📋 {sp['title']} #{idx+1:02d} ({c[0]},{c[1]}) 복사됨 — [붙임]을 누르세요")

    def _flat_paste(self, fkey, idx):
        sp = self._flat_spec(fkey)
        clip = getattr(self, "_flat_clip", None)
        if not clip or clip.get("f") != fkey:
            self.status.set(f"먼저 {sp['title']} 슬롯에서 [복사]를 누르세요"); return
        x, y = clip["coord"]; src = clip["src"]; note = ""
        if src != idx:
            rects = self._client_rects_by_slot()
            if rects:
                x += rects[idx][0] - rects[src][0]
                y += rects[idx][1] - rects[src][1]
                note = " — 클라이언트 위치 자동보정"
            else:
                note = " — ⚠ 클라이언트 감지 실패, 원본 그대로"
        slots = self.cfg.get(sp["key"]) or [None] * 16
        while len(slots) < 16: slots.append(None)
        slots[idx] = [int(x), int(y)]
        self.cfg[sp["key"]] = slots
        save_cfg(self.cfg)
        vl = getattr(self, sp["vars_attr"], None)
        if vl and idx < len(vl): vl[idx].set(f"({int(x)},{int(y)})")
        self.status.set(f"✔ {sp['title']} #{idx+1:02d} 붙여넣기 완료{note}")

    def _flat_preview(self, fkey, idx):
        sp = self._flat_spec(fkey)
        slots = self.cfg.get(sp["key"]) or []
        c = slots[idx] if idx < len(slots) else None
        if not c:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다"); return
        def rereg(_):
            sp["reg"](idx)
        def _save(_, nx, ny):
            slots[idx] = [nx, ny]
            self.cfg[sp["key"]] = slots
            save_cfg(self.cfg)
            vl = getattr(self, sp["vars_attr"], None)
            if vl and idx < len(vl): vl[idx].set(f"({nx},{ny})")
        self._open_dot_preview(f"{sp['title']} #{idx+1:02d}", [(c[0], c[1], idx + 1)],
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _client_rects_by_slot(self):
        """리니지M 클라이언트 창 16개를 화면 배치(세로 열우선 01~16) 순서로 반환.
        16개가 정확히 안 보이면 None (보정 불가)."""
        try:
            import win32gui
            wins = []
            def cb(h, _):
                if win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h):
                    t = win32gui.GetWindowText(h)
                    if t.startswith("리니지M l"):
                        l, tp, r, b = win32gui.GetWindowRect(h)
                        if r - l > 100 and b - tp > 100:
                            wins.append((l, tp, r, b))
                return True
            win32gui.EnumWindows(cb, None)
            if len(wins) != 16:
                return None
            wins.sort(key=lambda w: w[0])                     # x(열) 정렬
            cols = [sorted(wins[i*4:(i+1)*4], key=lambda w: w[1]) for i in range(4)]
            return [w for col in cols for w in col]           # 01~16 (열 우선)
        except Exception:
            return None

    def _copy_doll_slot(self, idx):
        """슬롯 좌표를 클립보드에 복사 — 원하는 슬롯에서 [붙임]으로 붙여넣기."""
        import copy
        coords = self.cfg["doll_slots"][idx].get("coords", [])
        if not any(coords):
            self.status.set(f"#{idx+1:02d} 복사할 좌표가 없습니다"); return
        self._doll_clipboard = copy.deepcopy(coords)
        self._doll_clip_src  = idx   # 붙여넣기 때 클라이언트 위치 자동보정 기준
        self._doll_clip_name = (self.cfg["doll_slots"][idx].get("name") or "").strip()
        reg = sum(1 for c in coords if c)
        self.status.set(f"📋 #{idx+1:02d} 좌표 {reg}개 복사됨 — 원하는 슬롯의 [붙임]을 누르세요")

    def _paste_doll_slot(self, idx):
        """클립보드 좌표를 이 슬롯에 붙여넣기 — 클라이언트 창 위치를 감지해
        원본 슬롯→대상 슬롯 위치 차이만큼 좌표를 자동 이동시킨다."""
        import copy
        clip = getattr(self, "_doll_clipboard", None)
        if not clip:
            self.status.set("먼저 [복사]로 슬롯 좌표를 복사하세요"); return
        shifted = copy.deepcopy(clip)
        src = getattr(self, "_doll_clip_src", None)
        note = ""
        if src is not None and src != idx:
            rects = self._client_rects_by_slot()
            if rects:
                dx = rects[idx][0] - rects[src][0]
                dy = rects[idx][1] - rects[src][1]
                for c in shifted:
                    if c:
                        c[0] += dx; c[1] += dy
                note = f" — 클라이언트 위치 자동보정 ({dx:+},{dy:+})"
            else:
                note = " — ⚠ 클라이언트 16개 감지 실패, 원본 위치 그대로"
        self.cfg["doll_slots"][idx]["coords"] = shifted
        # 슬롯 이름(제목)도 함께 붙여넣기
        _nm = getattr(self, "_doll_clip_name", "")
        if _nm and _nm != "미등록":
            self.cfg["doll_slots"][idx]["name"] = _nm
            self._doll_preset_ts = time.time()      # 이름칸 자동저장이 되돌리지 않게
            try:
                self._doll_name_vars[idx].set(_nm)
            except Exception:
                pass
        save_cfg(self.cfg); self._refresh_doll_display()
        reg = sum(1 for c in shifted if c)
        self.status.set(f"✔ #{idx+1:02d}에 붙여넣기 완료 ({reg}/{DOLL_CLICKS})"
                        + (f" · 이름 '{_nm}'" if _nm and _nm != "미등록" else "") + note)

    def _doll_wait(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if getattr(self, "_doll_stop", False): return False
            time.sleep(0.05)
        return True

    def _start_doll(self):
        active = [h for h in self.cfg.get("doll_slots", [])
                  if h.get("enabled", True) and any(c for c in h.get("coords", []))]
        if not active:
            messagebox.showwarning("등록 필요", "실행할(ON) 인형 탐험 좌표가 없습니다."); return
        if not self._try_busy_or_queue("인형탐험", self._start_doll): return
        self._doll_stop = False
        self._set_btn("btn_doll_run", state="disabled")
        self._set_btn("btn_doll_stop", state="normal")
        self._minimize_all()
        threading.Thread(target=self._run_task, args=("인형탐험", self._run_doll_standalone), daemon=True).start()

    def _run_doll_standalone(self):
        self._run_doll()
        self._set_btn("btn_doll_run", state="normal", bg="#b9770e", text="▶  인형탐험 실행")
        self._set_btn("btn_doll_stop", state="disabled")
        self._doll_stop = False
        self.after(0, self._restore_back)

    def _run_doll_wave(self, active, lanes=3):
        """인형탐험 번갈아(웨이브) 실행 — 동시 3슬롯을 섞어가며 클릭 하나씩.
        마우스가 하나라 '동시 클릭'은 애초에 불가능하고, 아래 두 가지로 겹침을 막는다.
          · 클릭과 클릭 사이 최소 간격(0.35~0.7초)
          · 다른 클라이언트로 넘어갈 때 창이 올라올 여유(0.6~1.1초)
        각 슬롯의 좌표 간 간격(2~3초)은 그대로 지켜진다."""
        state = {}
        for i, h in active:
            state[i] = {"slot": h, "j": 0,
                        "coords": [c for c in h.get("coords", [])],
                        "due": time.time() + random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX)
                               + random.uniform(0, 3.0)}
        order = [i for i, _h in active]
        act, waiting = order[:lanes], order[lanes:]
        last_si, done = None, 0
        self.status.set(f"🧸 인형탐험 번갈아 실행 — 동시 {lanes}슬롯 ({len(active)}개)")
        while not getattr(self, "_doll_stop", False):
            for si in [x for x in act if state[x]["j"] >= len(state[x]["coords"])]:
                act.remove(si)
                if waiting:
                    nx = waiting.pop(0)
                    state[nx]["due"] = time.time() + random.uniform(DOLL_SLOT_MIN, DOLL_SLOT_MAX)
                    act.append(nx)
            alive = [x for x in act if state[x]["j"] < len(state[x]["coords"])]
            if not alive:
                break
            now = time.time()
            ready = [x for x in alive if state[x]["due"] <= now]
            if not ready:
                nxt = min(state[x]["due"] for x in alive)
                time.sleep(max(0.05, min(nxt - now, 1.0)))
                continue
            si = random.choice(ready)
            st = state[si]
            j = st["j"]; st["j"] = j + 1
            coord = st["coords"][j] if j < len(st["coords"]) else None
            if not coord:
                st["due"] = time.time()          # 빈 자리는 기다리지 않고 통과
                continue
            if si != last_si:
                time.sleep(random.uniform(0.6, 1.1))   # 다른 창으로 넘어갈 여유
                last_si = si
            if getattr(self, "_doll_stop", False):
                break
            name = st["slot"].get("name", f"#{si+1}")
            self.status.set(f"🧸 [{name}] 좌표 {j+1}/{len(st['coords'])} (남은 슬롯 {len(alive)})")
            click_at(*coord)
            done += 1
            st["due"] = time.time() + random.uniform(DOLL_MIN, DOLL_MAX)
            time.sleep(random.uniform(0.35, 0.7))      # 클릭끼리 최소 간격
        if getattr(self, "_doll_stop", False):
            self.status.set("인형탐험 멈춤")
        else:
            self.status.set(f"✔ 인형 탐험 완료! ({len(active)}개 슬롯 / 클릭 {done}회)")

    def _run_doll(self):
        self._start_pause()
        try:
            slots = list(enumerate(self.cfg.get("doll_slots", [])))
            active = [(i, h) for i, h in slots
                      if h.get("enabled", True) and any(c for c in h.get("coords", []))]
            random.shuffle(active)   # 슬롯 실행 순서 매번 랜덤
            if len(active) > 1:
                # (2026-08-10) 3슬롯씩 번갈아(웨이브) — 마우스는 하나뿐이라
                # 동시에 눌리는 일은 없고, 클릭끼리 최소 간격을 둬서 겹침도 막는다
                self._run_doll_wave(active); return
            for si, (i, h) in enumerate(active):
                if getattr(self, "_doll_stop", False): self.status.set("인형탐험 멈춤"); return
                name = h.get("name", f"#{i+1}")
                coords = h.get("coords", [])
                _clicked = 0   # 이 슬롯에서 실제로 클릭한 횟수
                for j, coord in enumerate(coords):
                    if not coord: continue
                    if getattr(self, "_doll_stop", False): self.status.set("인형탐험 멈춤"); return
                    if _clicked == 0:
                        # 첫 클릭 '전' 여유 — 바로 클릭하지 않음 (0.5~1초)
                        if not self._doll_wait(random.uniform(DOLL_LEAD_MIN, DOLL_LEAD_MAX)):
                            self.status.set("인형탐험 멈춤"); return
                    self.status.set(f"🧸 [{name}] 좌표 {j+1}/{DOLL_CLICKS}...")
                    click_at(*coord)
                    _clicked += 1
                    if j < len(coords) - 1:
                        if not self._doll_wait(random.uniform(DOLL_MIN, DOLL_MAX)):
                            self.status.set("인형탐험 멈춤"); return
                if si < len(active) - 1:
                    if not self._doll_wait(random.uniform(DOLL_SLOT_MIN, DOLL_SLOT_MAX)):
                        self.status.set("인형탐험 멈춤"); return
            self.status.set(f"✔ 인형 탐험 완료! ({len(active)}개 슬롯)")
        except Exception as e:
            self.status.set(f"인형탐험 오류: {e}")

    # ── 클로드 앱 최소화 (좌표 겹침 방지 + 야간 자동 최소화) ──
    def _minimize_claude_windows(self, only_background=False):
        """제목에 'claude'가 들어간 창을 최소화한다.
        only_background=True면 사용자가 보고 있는(포그라운드) 창은 건드리지 않는다."""
        if time.time() - getattr(self, "_claude_attention_ts", 0) < 180:
            return   # 승인 대기 중일 수 있음 — 내리지 않음
        import ctypes
        SW_MINIMIZE = 6
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow() if only_background else None
        def _cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if "claude" in buf.value.lower():
                    if only_background and hwnd == fg:
                        return True  # 사용자가 열어둔 창은 그대로 둠
                    if not user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try:
            user32.EnumWindows(WNDENUMPROC(_cb), 0)
        except Exception:
            pass

    def _claude_ui_state(self):
        """(보임여부, 포그라운드여부) — 클로드 창이 화면에 떠 있나 / 사용자가 앞에 두고 있나."""
        import ctypes
        u = ctypes.windll.user32
        fg = u.GetForegroundWindow()
        st = {"vis": False, "fg": False}
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" in b.value.lower() and not u.IsIconic(hwnd):
                    st["vis"] = True
                    if hwnd == fg:
                        st["fg"] = True
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass
        return st["vis"], st["fg"]

    def _center_claude(self):
        """클로드 앱 창을 고정 위치(claude_win_pos)로 유지 — 없으면 화면 가운데.
        크기는 그대로, 위치만. 최소화 상태면 건드리지 않음.
        사용자가 옮기면 그 자리가 새 고정 위치로 저장된다(_center_claude_tick)."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        sw = u.GetSystemMetrics(0); sh = u.GetSystemMetrics(1)
        target = self.cfg.get("claude_win_pos")   # 사용자가 정한 고정 위치
        SWP_NOSIZE = 0x0001; SWP_NOZORDER = 0x0004; SWP_NOACTIVATE = 0x0010
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" not in b.value.lower():
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left; h = r.bottom - r.top
                if w > 200 and h > 200:   # 실제 앱 창만 (작은 부속 창 제외)
                    if target:
                        x, y = int(target[0]), int(target[1])
                    else:
                        x = max(0, (sw - w) // 2)
                        y = max(0, (sh - h) // 2)
                    self._claude_center_pos = (x, y)
                    if abs(r.left - x) > 3 or abs(r.top - y) > 3:   # 이미 제자리면 안 건드림
                        u.SetWindowPos(hwnd, 0, x, y, 0, 0,
                                       SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass

    def _claude_pos(self):
        """현재 클로드 앱 창의 (x, y) 반환. 없으면 None."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        res = {"p": None}
        def cb(hwnd, _):
            try:
                if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                if "claude" not in b.value.lower():
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) > 200 and (r.bottom - r.top) > 200:
                    res["p"] = (r.left, r.top)
            except Exception:
                pass
            return True
        WN = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try: u.EnumWindows(WN(cb), 0)
        except Exception: pass
        return res["p"]

    def _center_claude_tick(self):
        """클로드를 고정 위치에 유지. 사용자가 옮기면 그 자리를 새 고정 위치로 저장."""
        try:
            cur = self._claude_pos()
            cp  = getattr(self, "_claude_center_pos", None)
            if cur and cp and (abs(cur[0] - cp[0]) > 20 or abs(cur[1] - cp[1]) > 20):
                # 사용자가 클로드를 옮김 → 그 자리가 새 고정 위치
                self.cfg["claude_win_pos"] = [cur[0], cur[1]]
                save_cfg(self.cfg)
            self._center_claude()
        except Exception:
            pass
        self.after(8000, self._center_claude_tick)

    def _claude_minimize_tick(self):
        """밤 11시~새벽 6시엔 클로드 앱을 최소화 유지.
        단, 사용자가 직접 클로드를 열면(포그라운드로) 자동 최소화를 멈추고,
        사용자가 다시 최소화하면 재개한다 — 사용자가 클릭해서 연 걸 계속 내리지 않도록."""
        import datetime
        vis, fg = self._claude_ui_state()
        if fg:
            self._claude_user_open = True    # 사용자가 열어둠 → 자동 최소화 중지
        elif not vis:
            self._claude_user_open = False   # 클로드가 안 보임(최소화됨) → 재개
        h = datetime.datetime.now().hour
        if (h >= 23 or h < 6) and not getattr(self, "_claude_user_open", False):
            self._minimize_claude_windows(only_background=True)
        self.after(30000, self._claude_minimize_tick)

    def _system_idle_ms(self):
        """시스템 전체 마지막 입력(마우스·키보드) 이후 경과 시간(ms)."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO(); lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return ctypes.windll.kernel32.GetTickCount() - lii.dwTime

    def _claude_idle_minimize_tick(self):
        """사용자가 5분간 아무 작업(입력)도 안 하면 클로드 앱도 최소화.
        (매크로 실행 중엔 pyautogui가 입력을 내서 유휴가 아니므로 발동 안 함)"""
        try:
            if self._system_idle_ms() >= 300000:   # 5분
                self._minimize_claude_windows(only_background=False)
        except Exception:
            pass
        self.after(20000, self._claude_idle_minimize_tick)

    def _claude_attention_loop(self):
        """클로드 앱이 주의를 요청(작업표시줄 플래시)하면 자동으로 복원해서 앞으로.
        승인(항상 허용/한번 허용) 등 클릭이 필요할 때, 최소화돼 있어도 스스로 올라오게 한다.
        사용자가 그냥 최소화한 경우와 구분하려고, 짧은 시간에 '반복되는' 상태변화(=플래시)만 복원한다."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        EVENT_OBJECT_STATECHANGE = 0x800A
        WINEVENT_OUTOFCONTEXT = 0x0000
        OBJID_WINDOW = 0
        hits = {}   # hwnd -> [최근 상태변화 시각들]

        def _is_claude(hwnd):
            try:
                b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, b, 256)
                return "claude" in b.value.lower()
            except Exception:
                return False

        WEP = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                 wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _cb(hHook, event, hwnd, idObject, idChild, dwThread, dwMs):
            try:
                if not hwnd or idObject != OBJID_WINDOW:
                    return
                if not _is_claude(hwnd):
                    return
                # 승인 버튼(항상 허용/한 번 허용) 등 주의 요청 감지 시각 기록
                # → 이후 3분간은 클로드를 최소화하지 않는다
                self._claude_attention_ts = time.time()
                if not u.IsIconic(hwnd):     # 이미 보이면 복원 불필요
                    return
                now = time.time()
                ts = [t for t in hits.get(hwnd, []) if now - t < 2.0] + [now]
                hits[hwnd] = ts
                # 2초 안에 상태변화 3번 이상 = 플래시(주의 요청) → 복원
                if len(ts) >= 3:
                    hits[hwnd] = []
                    u.ShowWindow(hwnd, 9)    # SW_RESTORE
                    try: u.SetForegroundWindow(hwnd)
                    except Exception: pass
                    try: self._center_claude()   # 복원 시 가운데로
                    except Exception: pass
            except Exception:
                pass

        cb = WEP(_cb)
        self._claude_wineventproc = cb   # 콜백 GC 방지 (참조 유지)
        try:
            u.SetWinEventHook(EVENT_OBJECT_STATECHANGE, EVENT_OBJECT_STATECHANGE,
                              0, cb, 0, 0, WINEVENT_OUTOFCONTEXT)
        except Exception:
            return
        msg = wintypes.MSG()
        while True:
            try:
                r = u.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if r == 0 or r == -1:
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                time.sleep(0.5)

    def _mark_activity(self, e=None):
        """메인런처(및 서브창) 조작 감지 — 유휴 최소화 타이머 리셋."""
        self._last_activity = time.time()

    def _idle_minimize_tick(self):
        """5분간 아무 조작이 없으면 메인런처를 최소화 대신 '맨 뒤'로 보낸다
        (제자리에 남아 있어 스케줄 실행에 지장 없음). 클릭/포커스 주면 타이머 리셋."""
        try:
            idle = time.time() - getattr(self, "_last_activity", time.time())
            running = getattr(self, "_running", False)  # 전체 자동실행 중이면 관여 안 함
            showing = getattr(self, "_back_after_id", None)  # 완료 후 1분 표시 중이면 대기
            if not running and not showing and idle >= 300:
                try: normal = (self.state() == "normal")
                except Exception: normal = False
                if normal:
                    self._send_to_back()
        except Exception:
            pass
        self.after(15000, self._idle_minimize_tick)

    def _popup_guard_loop(self):
        """실행 방해 팝업 감시·정리.
        - 우하단 윈도우 알림 토스트: 항상 숨김(안전).
        - 항상 위(topmost) 낯선 팝업(업데이트 나그 등): 실행 중(런처 최소화 상태)일 때만 최소화.
        우리 런처/서브창(같은 PID)·게임(Purple/리니지M)·바탕화면/작업표시줄은 건드리지 않음."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        SW_HIDE = 0
        SW_MINIMIZE = 6
        my_pid = os.getpid()

        def _glog(msg):
            """가드가 창을 건드릴 때마다 기록 — 오작동 추적용."""
            try:
                import datetime as _dt
                with open(os.path.join(LOGS_DIR, "popup_guard.txt"), "a", encoding="utf-8") as f:
                    f.write(f"[{_dt.datetime.now():%m-%d %H:%M:%S}] {msg}\n")
            except Exception:
                pass
        SKIP_CLASSES = {
            "progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
            "button", "trayclockwclass", "notifyiconoverflowwindow",
            "tooltips_class32", "windows.ui.input.inputsite.windowclass",
        }
        sw = u.GetSystemMetrics(0)
        sh = u.GetSystemMetrics(1)
        k = ctypes.windll.kernel32
        # 게임/퍼플/NCSoft 계열 프로세스 — 이 창들은 절대 건드리지 않음
        # (계정 전환·구글 계정 선택 팝업이 이 CEF/웹뷰 창으로 뜸)
        SKIP_PROCS = {
            "purple.exe", "purplebox.exe", "purpleon.exe", "purpleonp.exe",
            "purple-agent.exe", "ncoverlaycefweb32.exe", "lineagem.exe",
            "msedgewebview2.exe",
            # 원격제어 프로그램 — 파일전송 창 포함 절대 건드리지 않음
            "remotet.exe", "remoteview.exe", "rvagent.exe", "rvagtray.exe",
            "anydesk.exe", "teamviewer.exe",
        }

        def _pid_of(hwnd):
            p = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            return p.value

        def _pname_of(pid):
            try:
                h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if not h:
                    return ""
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                k.CloseHandle(h)
                return os.path.basename(buf.value).lower() if ok else ""
            except Exception:
                return ""

        def _is_game_proc(pid):
            return _pname_of(pid) in SKIP_PROCS

        def _cb(hwnd, running):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                pid = _pid_of(hwnd)
                if pid == my_pid:                    # 우리 런처/서브창
                    return True
                tb = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, tb, 256)
                title = tb.value
                cbn = ctypes.create_unicode_buffer(256); u.GetClassNameW(hwnd, cbn, 256)
                cls = cbn.value.lower()
                if cls in SKIP_CLASSES:
                    return True
                tl = title.lower()
                # 퍼플 로고 전체화면 스플래시(계정 전환 시 화면을 검게 덮음) — 항상 숨김
                if tl.startswith("ngp_purplelogo"):
                    r0 = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r0))
                    if (r0.right - r0.left) >= sw - 10 and (r0.bottom - r0.top) >= sh - 10:
                        u.ShowWindow(hwnd, SW_HIDE)
                        _glog(f"퍼플 로고 스플래시 숨김: '{title}'")
                        return True
                # 게임/런처/클로드 + 원격제어·파일전송 창은 절대 건드리지 않음
                if any(kk in tl for kk in (
                        "purple", "리니지m", "claude",
                        "파일전송", "파일 전송", "file transfer",
                        "리모트", "remote",   # RemoteT·RemoteView 등 원격제어 전반
                        "anydesk", "teamviewer", "원격")):
                    return True
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left; h = r.bottom - r.top
                if w <= 0 or h <= 0:
                    return True
                # 1) 알림 토스트: 우하단 코너의 작은 CoreWindow → 숨김
                if (cls == "windows.ui.core.corewindow"
                        and r.right >= sw - 60 and r.bottom >= sh - 160
                        and w < 640 and h < 520):
                    if _is_game_proc(pid):           # 게임/퍼플/NCSoft/원격 창 보호
                        return True
                    u.ShowWindow(hwnd, SW_HIDE)
                    _glog(f"토스트 숨김: '{title}' cls={cls} proc={_pname_of(pid)}")
                    return True
                # 2) 실행 중일 때만: 항상 위(topmost) 낯선 창 → 최소화
                if running and title:
                    ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    if ex & WS_EX_TOPMOST:
                        if _is_game_proc(pid):       # 게임/퍼플/NCSoft/원격 창 보호
                            return True
                        u.ShowWindow(hwnd, SW_MINIMIZE)
                        _glog(f"topmost 최소화: '{title}' cls={cls} proc={_pname_of(pid)} "
                              f"busy={getattr(self, '_busy_task', None)}")
            except Exception:
                pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        while True:
            try:
                # 실제 작업이 돌고 있을 때만 낯선 topmost 창을 정리한다.
                # (예전: 런처 최소화 = 실행 중 간주 → 유휴 자동최소화 때문에 사실상 항상
                #  작동해서, 원격 파일전송 등 무관한 항상위 창까지 내려버리는 문제)
                running = bool(getattr(self, "_busy_task", None)
                               or getattr(self, "_running", False))
                cb_ptr = WNDENUMPROC(lambda h, l, rn=running: _cb(h, rn))
                u.EnumWindows(cb_ptr, 0)
            except Exception:
                pass
            time.sleep(0.5)

    def _reg_coord(self, key):
        self._reg_target = key
        self.status.set(f"3초 후 [{LABELS[key]}] 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="single")])

    def on_coord(self, x, y):
        if isinstance(self._reg_target, str) and self._reg_target.startswith("__pass_"):
            ci = int(self._reg_target.split("_")[3])
            pc = self.cfg.setdefault("pass_coords", [None]*PASS_CLICKS)
            while len(pc) < PASS_CLICKS: pc.append(None)
            pc[ci] = [x, y]
            if hasattr(self, "_pass_reg_sv") and self._pass_reg_sv:
                self._pass_reg_sv.set(f"({x},{y})")
        else:
            self.cfg[self._reg_target] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 등록: ({x},{y})")
        self.deiconify()

    def _reg_char_btn(self):
        n = len(self.cfg.get("char_btns", []))
        self.status.set(f"3초 후 캐릭터 #{n+1} 접속 버튼 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="char")])

    def on_char_coord(self, x, y):
        self.cfg.setdefault("char_btns", []).append([x, y])
        n = len(self.cfg["char_btns"])
        # 대응하는 사냥 슬롯 이름이 미등록이면 자동 설정
        hunt_slots = self.cfg.get("hunt_slots", [])
        if n - 1 < len(hunt_slots):
            if hunt_slots[n-1].get("name", "미등록") == "미등록":
                hunt_slots[n-1]["name"] = f"캐릭터{n}"
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 캐릭터 #{n} 등록: ({x},{y})  →  사냥 슬롯 #{n} 연동됨")
        self.deiconify()

    def _clear_char_btns(self):
        self.cfg["char_btns"] = []
        save_cfg(self.cfg); self._refresh_ui()

    # ── 클릭 슬롯 ─────────────────────────────────────────────────────
    def _reg_slot(self, idx):
        self._slot_target = idx
        self._slot_step   = 0
        self.cfg["click_slots"][idx] = [None, None]
        self._do_slot_step()

    def _do_slot_step(self):
        step = self._slot_step
        self.status.set(f"3초 후 #{self._slot_target+1}번 클릭{step+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="slot")])

    def on_slot_coord(self, x, y):
        idx, step = self._slot_target, self._slot_step
        slot = self.cfg["click_slots"][idx]
        while len(slot) <= step:
            slot.append(None)
        slot[step] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #{idx+1}번 클릭{step+1} 등록: ({x},{y})")
        self.deiconify()
        self._slot_step += 1
        max_steps = 3 if idx == 4 else 2
        if self._slot_step < max_steps:
            self.after(500, self._do_slot_step)
        else:
            self.status.set(f"✔ #{idx+1}번 슬롯 완료!")

    def _reg_slot_step(self, idx, step):
        """클릭1 또는 클릭2만 개별 등록"""
        if self.cfg["click_slots"][idx] is None:
            self.cfg["click_slots"][idx] = [None, None]
        self._slot_target = idx
        self._slot_step   = step
        self.status.set(f"3초 후 #{idx+1}번 클릭{step+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="slot")])

    def _group_copy_slot(self, idx):
        import copy
        src = self.cfg["click_slots"][idx-1]
        if not src or not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["click_slots"][idx] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        pair = self.cfg["click_slots"][idx]
        dots = []
        if pair[0]: dots.append((pair[0][0], pair[0][1], "1"))
        if pair[1]: dots.append((pair[1][0], pair[1][1], "2"))
        if dots:
            self.withdraw()
            self.after(300, lambda: _SlotGroupMoveOverlay(self, idx, dots))

    def _del_slot(self, idx):
        self.cfg["click_slots"][idx] = [None, None]
        save_cfg(self.cfg); self._refresh_ui()

    def _clear_click_slots(self):
        self.cfg["click_slots"] = [[None, None]] * CLICK_SLOTS
        save_cfg(self.cfg); self._refresh_ui()

    # ── 사냥 슬롯 ─────────────────────────────────────────────────────
    def _save_hunt_name(self, idx):
        name = self._hunt_name_vars[idx].get().strip() or "미등록"
        self._hunt_name_vars[idx].set(name)
        self.cfg["hunt_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _reg_hunt_click(self, slot_idx, click_idx):
        self._hunt_reg_idx  = slot_idx
        self._hunt_reg_step = click_idx
        name = self.cfg["hunt_slots"][slot_idx].get("name", f"#{slot_idx+1}")
        self.status.set(f"3초 후 [{name}] 클릭{click_idx+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="hunt")])

    def on_hunt_coord(self, x, y):
        idx, step = self._hunt_reg_idx, self._hunt_reg_step
        coords = self.cfg["hunt_slots"][idx].get("coords", [None] * HUNT_CLICKS)
        while len(coords) < HUNT_CLICKS:
            coords.append(None)
        coords[step] = [x, y]
        self.cfg["hunt_slots"][idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_ui()
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1}")
        self.status.set(f"✔ [{name}] 클릭{step+1} 등록: ({x},{y})")
        self.deiconify()

    def _del_hunt_click(self, slot_idx, click_idx):
        if not messagebox.askyesno("좌표 삭제", f"사냥 #{slot_idx+1} 클릭{click_idx+1} 좌표를 삭제하시겠습니까?", default="no"):
            return
        coords = self.cfg["hunt_slots"][slot_idx].get("coords", [None] * HUNT_CLICKS)
        while len(coords) < HUNT_CLICKS:
            coords.append(None)
        coords[click_idx] = None
        self.cfg["hunt_slots"][slot_idx]["coords"] = coords
        save_cfg(self.cfg); self._refresh_ui()

    def _test_hunt(self, idx):
        h = self.cfg["hunt_slots"][idx]
        coords = [c for c in h.get("coords", []) if c]
        if not coords:
            messagebox.showwarning("등록 필요", f"#{idx+1} 슬롯에 등록된 좌표가 없습니다."); return
        name = h.get("name", f"#{idx+1}")
        self.status.set(f"[{name}] 테스트 실행 중...")
        self._minimize_all()
        def run():
            try:
                for j, coord in enumerate(h.get("coords", [])):
                    if not coord: continue
                    self.status.set(f"[{name}] 클릭{j+1} 테스트...")
                    pyautogui.click(*coord)
                    if j < len(h["coords"]) - 1:
                        time.sleep(random.uniform(0.1, 0.6))
                self.status.set(f"✔ [{name}] 테스트 완료!")
            except Exception as e:
                self.status.set(f"오류: {e}")
            finally:
                self.deiconify()
        threading.Thread(target=run, daemon=True).start()

    def _toggle_slot_enable(self, fkey, idx):
        """슬롯 ON/OFF — 꺼둔 슬롯은 실행에서 빠진다."""
        if fkey == "hunt":
            return self._toggle_hunt_enable(idx)
        try:
            sp = self._grid_spec(fkey)
            slot = self.cfg[sp["key"]][idx]
            slot["enabled"] = not slot.get("enabled", True)
            save_cfg(self.cfg); self._refresh_slot_grids(fkey)
            self.status.set(f"{sp['title']} #{idx+1:02d} "
                            + ("ON" if slot["enabled"] else "OFF (실행에서 제외)"))
        except Exception:
            pass

    def _toggle_hunt_enable(self, idx):
        cur = self.cfg["hunt_slots"][idx].get("enabled", True)
        self.cfg["hunt_slots"][idx]["enabled"] = not cur
        save_cfg(self.cfg); self._refresh_ui()

    def _del_hunt(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"사냥 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["hunt_slots"][idx]["coords"] = [None] * HUNT_CLICKS
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_hunt(self, idx):
        coords = self.cfg["hunt_slots"][idx].get("coords", [])
        dots = [(x, y, n+1) for n, c in enumerate(coords)
                if c and len(c) >= 2 for x, y in [c[:2]]]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._hunt_reg_idx  = idx
            self._hunt_reg_step = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="hunt"))

        def _save(dot_idx, nx, ny):
            self.cfg["hunt_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 사냥 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"사냥 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _group_copy_hunt_slot(self, idx):
        """위 슬롯 좌표 복사 후 그룹 드래그로 위치 조정"""
        import copy
        src = self.cfg["hunt_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["hunt_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()

        # 그룹 드래그 미리보기 열기
        coords = self.cfg["hunt_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            return
        name = self.cfg["hunt_slots"][idx].get("name", f"#{idx+1:02d}")

        def _save_group(_, nx, ny):
            pass  # 개별 저장은 아래 group_save에서 처리

        self.withdraw()
        self.after(300, lambda: _HuntGroupMoveOverlay(self, idx, dots))

    def _group_copy_hunt(self):
        import copy
        src = self.cfg["hunt_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, HUNT_SLOTS):
            self.cfg["hunt_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{HUNT_SLOTS:02d} 전체 복사 완료")

    # ── 멈춤 ──────────────────────────────────────────────────────────
    # ── 9시 클릭 스케줄러 ─────────────────────────────────────────────
    def _set_sleep_prevention(self, prevent: bool):
        ES_CONTINUOUS       = 0x80000000
        ES_SYSTEM_REQUIRED  = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        if prevent:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    def _toggle_mail(self):
        has = any(any(s.get("coords", [])) for s in self.cfg.get("mail_slots", []))
        if not has:
            messagebox.showwarning("등록 필요", "먼저 우편함 좌표를 등록해주세요."); return
        self._mail_on = not self._mail_on
        self.cfg["mail_on"] = self._mail_on   # 재시작해도 상태 유지
        save_cfg(self.cfg)
        if self._mail_on:
            self._mail_triggered_date = None
            self.btn_mail.config(text="🕘 23:30~23:50 클릭  ON", bg="#27ae60")
            self.status.set("우편 클릭 ON — 밤 23:30~23:50 랜덤 실행")
        else:
            self.btn_mail.config(text="🕘 23:30~23:50 클릭  OFF", bg="#7f8c8d")
            self.status.set("우편 클릭 OFF")
        self._sync_prestart_tasks()      # 스케줄 켜짐/꺼짐에 맞춰 자동시작 작업 갱신

    # ── 스케줄 10분 전 런처 자동 시작 (윈도우 예약 작업으로 등록) ──
    #    켜져 있으면 워치독이 아무 일도 안 하므로 중복 실행 걱정 없음.
    SCHED_TIMES = [("past", 5, 3, True),      # 과거섬 5:03 (항상)
                   ("mail", 23, 30, "mail")]  # 우편함 23:30 (mail_on 일 때만)

    def _sync_prestart_tasks(self):
        """켜져 있는 스케줄마다 '시작 10분 전' 자동 시작 작업을 등록/해제한다."""
        def _work():
            import subprocess as _sp, sys as _sys
            try:
                exe = _sys.executable.replace("python.exe", "pythonw.exe")
                wd = os.path.join(BASE, "lineagem_watchdog.py")
                for tag, hh, mm, cond in self.SCHED_TIMES:
                    on = bool(self.cfg.get("mail_on")) if cond == "mail" else bool(cond)
                    name = "LineageM_Pre_" + tag
                    tot = hh * 60 + mm - 10          # 10분 전
                    if tot < 0:
                        tot += 24 * 60
                    tstr = "%02d:%02d" % (tot // 60, tot % 60)
                    if not on:
                        _sp.run(["schtasks", "/Delete", "/F", "/TN", name],
                                capture_output=True, creationflags=0x08000000)
                        continue
                    q = _sp.run(["schtasks", "/Query", "/TN", name],
                                capture_output=True, text=True, creationflags=0x08000000)
                    if q.returncode == 0 and tstr in (q.stdout or ""):
                        continue                      # 이미 같은 시각으로 등록됨
                    _sp.run(["schtasks", "/Create", "/F", "/TN", name,
                             "/SC", "DAILY", "/ST", tstr,
                             "/TR", '"%s" "%s"' % (exe, wd)],
                            capture_output=True, creationflags=0x08000000)
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()

    def _mail_scheduler_tick(self):
        import datetime
        if self._mail_on:
            now = datetime.datetime.now()
            today = now.date()
            # 23:30~23:50 사이에 한 번만 트리거
            in_window = (now.hour == 23 and 30 <= now.minute < 50)
            if in_window and self._mail_triggered_date != today:
                if self._is_busy():
                    self.status.set("🕘 우편 스케줄 대기 — 다른 작업 실행 중")
                else:
                    self._mail_triggered_date = today
                    self._busy_task = "우편함(스케줄)"
                    threading.Thread(target=self._run_task,
                        args=("우편함(스케줄)", self._run_mail_scheduled), daemon=True).start()
            elif self._mail_triggered_date != today:
                target = now.replace(hour=23, minute=30, second=0, microsecond=0)
                if now >= target:
                    target += datetime.timedelta(days=1)
                diff = target - now
                h, m = divmod(int(diff.total_seconds()) // 60, 60)
                self.status.set(f"🕘 우편 클릭 대기 중... (약 {h}시간 {m}분 후 23:30~23:50 실행)")
        self.after(10000, self._mail_scheduler_tick)

    def _next_past_run_date(self):
        """다음 과거섬 스케줄 실행 날짜 — 오늘 5:25 전이면 오늘, 지났으면 내일."""
        import datetime
        now = datetime.datetime.now()
        d = now.date()
        if now.hour > 5 or (now.hour == 5 and now.minute > 25):
            d += datetime.timedelta(days=1)
        return d

    def _toggle_past_skip(self):
        """★ 버튼 — 다음 과거섬 새벽 실행을 하루 건너뜀 (다시 누르면 취소, 다음날 자동 재개)."""
        target = self._next_past_run_date()
        tstr = target.strftime("%Y-%m-%d")
        if str(self.cfg.get("past_skip_date") or "") == tstr:
            self.cfg["past_skip_date"] = ""
            save_cfg(self.cfg)
            self.status.set("★ 과거섬 패스 취소 — 예정대로 실행합니다")
        else:
            self.cfg["past_skip_date"] = tstr
            save_cfg(self.cfg)
            self.status.set(f"★ 과거섬 {target.month}/{target.day} 새벽 실행 건너뜀 — 그 다음날 자동 재개")
        self._refresh_past_skip_btn()

    def _refresh_past_skip_btn(self):
        btn = getattr(self, "_past_skip_btn", None)
        if not btn:
            return
        try:
            armed = (str(self.cfg.get("past_skip_date") or "")
                     == self._next_past_run_date().strftime("%Y-%m-%d"))
            if armed:
                btn.config(text="★ 패스중!", bg="#c0392b", fg="white",
                           activebackground="#922b21")
            else:
                btn.config(text="★ 과거섬\n패스!", bg="#dfe3e6", fg="#c0392b",
                           activebackground="#cfd4d8")
        except Exception:
            pass

    @staticmethod
    def _past_ran_path():
        d = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "past_ran.json")

    def _past_ran_load(self):
        """마지막으로 과거섬 스케줄을 실행한 날짜 (없으면 None)."""
        try:
            import datetime
            with open(self._past_ran_path(), encoding="utf-8") as f:
                v = (json.load(f) or {}).get("date")
            return datetime.date.fromisoformat(v) if v else None
        except Exception:
            return None

    def _past_ran_save(self, day):
        try:
            with open(self._past_ran_path(), "w", encoding="utf-8") as f:
                json.dump({"date": day.isoformat()}, f)
        except Exception:
            pass

    def _past_scheduler_tick(self):
        import datetime
        now = datetime.datetime.now()
        today = now.date()
        is_skip_day = now.weekday() in (2, 5)   # 월=0 … 수=2, 토=5 : 수·토요일엔 과거섬 스케줄 건너뜀
        # 사용자가 특정 날짜 하루 건너뛰기를 지정한 경우 (cfg past_skip_date = "YYYY-MM-DD")
        user_skip = (str(self.cfg.get("past_skip_date") or "") == now.strftime("%Y-%m-%d"))
        if is_skip_day or user_skip:
            if user_skip:
                self.status.set("🏝 과거섬: 오늘은 사용자 지시로 건너뜀")
            else:
                _dname = "수요일" if now.weekday() == 2 else "토요일"
                self.status.set(f"🏝 과거섬: {_dname}은 스케줄 실행 안 함 (건너뜀)")
        elif now.hour == 5 and 3 <= now.minute <= 25 and self._past_triggered_date != today:
            if self._is_busy():
                # 최우선: 대기열 맨 앞에 넣어 현재 작업이 끝나는 즉시 실행 (창이 지나도 실행)
                self._enqueue_front("과거섬(스케줄)", self._start_past_scheduled)
                self.status.set("🏝 과거섬 스케줄 — 현재 작업 끝나는 즉시 최우선 실행")
            else:
                self._start_past_scheduled()
        elif self._past_triggered_date != today:
            target = now.replace(hour=5, minute=3, second=0, microsecond=0)
            if now >= target:
                target += datetime.timedelta(days=1)
            diff = target - now
            h, m = divmod(int(diff.total_seconds()) // 60, 60)
            self.status.set(f"🏝 과거섬 대기 중... (약 {h}시간 {m}분 후 5:03~5:25 실행)")
        self.after(30000, self._past_scheduler_tick)

    def _purple_check_tick(self):
        """(사용 안 함) 새벽 4시 퍼플 자동 확인·전환 — 2026-08-07 사용자 지시로 비활성.
        되살리려면 __init__의 after(1000, self._purple_check_tick) 등록을 복원할 것."""
        return
        import threading, datetime
        now = datetime.datetime.now()
        today = now.date()
        if now.hour == 4 and self._purple_triggered_date != today:
            if self._is_busy():
                self.status.set("🔍 4시 퍼플 확인 대기 — 다른 작업 실행 중")
            else:
                self._purple_triggered_date = today
                self._busy_task = "퍼플확인(4시)"
                threading.Thread(target=self._run_task,
                    args=("퍼플확인(4시)", self._purple_check_worker), daemon=True).start()
        self.after(60000, self._purple_check_tick)

    def _plog(self, msg):
        """4시 퍼플 체크 파일 로그 — 다음날 무슨 일이 있었는지 추적용."""
        try:
            import datetime as _dt
            with open(os.path.join(LOGS_DIR, "purple_check.txt"), "a", encoding="utf-8") as f:
                f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except Exception:
            pass

    def _purple_check_worker(self):
        import win32gui, win32con, ctypes
        self._plog(f"=== 시작 (타깃='{(self.cfg.get('profile_target_id') or '').strip()}') ===")
        self._minimize_claude()          # 클로드(항상위)가 클릭을 가리지 않게 먼저 내림
        self.after(0, self._send_to_back)      # 메인런처도 내림
        win = find_purple()
        if not win:
            self._plog("퍼플 창 없음 — 종료")
            self.after(0, lambda: self.status.set("🔍 퍼플 확인: 퍼플 창 없음"))
            return
        hwnd = win32gui.FindWindow(None, win.title)
        orig_placement = None
        try:
            if hwnd:
                orig_placement = win32gui.GetWindowPlacement(hwnd)
                # 퍼플을 맨 앞 + '최대화' — 아이디 표시 영역/버튼 좌표가 최대화 상태 기준이라
                # 반드시 최대화해야 OCR 캡처가 올바른 위치에서 찍힌다. (축소/복원 상태면 오인식)
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                time.sleep(0.6)
                try:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                try:
                    win32gui.BringWindowToTop(hwnd)
                except Exception:
                    pass
                time.sleep(1.2)
            self.after(0, lambda: self.status.set("🔍 퍼플 확인 중..."))

            # 1단계: 리니지M 좌측버튼(profile_reveal_btn) 클릭 → 아이디 표시 → 확인
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(2)

            matched, ocr_id, ratio = self._is_target_account(hwnd)
            self._plog(f"1차 확인: OCR='{ocr_id}' 일치율 {int(ratio*100)}% → matched={matched}")
            self.after(0, lambda o=ocr_id, r=ratio: self.status.set(
                f"🔍 퍼플 아이디 '{o}' (일치율 {int(r*100)}%)"))

            # 2단계: 지정 아이디 아니면 전환 → 전환 후 재검증, 아직 다르면 최대 2회 재전환
            MAX_SWITCH_TRIES = 2
            attempt = 0
            while not matched and attempt < MAX_SWITCH_TRIES:
                attempt += 1
                self._plog(f"전환 시도 {attempt}/{MAX_SWITCH_TRIES} (profile→google→confirm)")
                self.after(0, lambda a=attempt: self.status.set(
                    f"🔍 지정 아이디 아님 → 전환 시도 {a}/{MAX_SWITCH_TRIES}..."))
                if self.cfg.get("profile_btn"):
                    pyautogui.click(*self.cfg["profile_btn"]); time.sleep(2)
                if self.cfg.get("google_acc"):
                    pyautogui.click(*self.cfg["google_acc"]); time.sleep(2)
                if self.cfg.get("confirm_btn"):
                    pyautogui.click(*self.cfg["confirm_btn"])
                    time.sleep(10)  # 계정 전환 후 로딩(약 8~10초) 대기
                # 전환 후 재검증 — 퍼플 hwnd가 새로 생기므로 다시 찾아 앞으로 + 아이디 재표시
                _re = win32gui.FindWindow(None, "PURPLE")
                if _re:
                    hwnd = _re
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE); time.sleep(0.5)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        win32gui.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    time.sleep(1.0)
                if self.cfg.get("profile_reveal_btn"):
                    pyautogui.click(*self.cfg["profile_reveal_btn"]); time.sleep(2)
                matched, ocr_id, ratio = self._is_target_account(hwnd)
                self._plog(f"전환 {attempt}회 후 확인: OCR='{ocr_id}' 일치율 {int(ratio*100)}% → matched={matched}")
                self.after(0, lambda o=ocr_id, r=ratio, a=attempt: self.status.set(
                    f"🔍 전환 {a}회 후 아이디 '{o}' (일치율 {int(r*100)}%)"))
                # 느슨일치 기준 — 이미지 대조는 다른 계정도 어느 정도 점수가 나오므로 더 높게
                loose = 0.75 if os.path.exists(self._profile_ref_path()) else 0.5
                if not matched and ratio >= loose:
                    # 판독이 흔들려 기준 미달이지만 사실상 지정계정일 가능성 —
                    # 재전환하면 (목록에 현재계정이 없어서) 다른 계정으로 이탈하므로 중단
                    self._plog(f"느슨일치(≥{int(loose*100)}%) — 재전환 시 이탈 위험 → 여기서 중단")
                    break

            if matched:
                self._plog("✔ 완료 — 지정계정 확인됨")
                self.after(0, lambda: self.status.set("✔ 퍼플 지정계정 확인/전환 완료"))
            else:
                self._plog(f"⚠ 실패 — {MAX_SWITCH_TRIES}회 재시도에도 미일치 (마지막 OCR='{ocr_id}')")
                self.after(0, lambda: self.status.set(
                    f"⚠ 퍼플 전환 실패 — {MAX_SWITCH_TRIES}회 재시도했으나 지정 아이디로 못 바꿈"))
        except Exception as e:
            import traceback as _tb
            self._plog(f"오류: {e}\n{_tb.format_exc()}")
            self.after(0, lambda err=e: self.status.set(f"🔍 퍼플 확인 오류: {err}"))
        finally:
            # 계정 전환하면 퍼플 창이 새로 생겨 hwnd가 바뀌므로, 여기서 다시 찾아 최소화.
            # (확인/전환 중 오류가 나도 반드시 최소화 — 안 되면 다음 작업이 퍼플 위에서 막힘)
            try:
                _ph = win32gui.FindWindow(None, "PURPLE")
                if not _ph:
                    _w2 = find_purple()
                    _ph = win32gui.FindWindow(None, _w2.title) if _w2 else None
                if _ph:
                    win32gui.ShowWindow(_ph, win32con.SW_MINIMIZE)
                elif win:
                    win.minimize()
            except Exception:
                try: win.minimize()
                except Exception: pass

    def _purple_ensure_scroll(self):
        """퍼플을 지정 계정으로 전환하고 최소화."""
        try:
            import win32gui, win32con, ctypes
            hwnd = win32gui.FindWindow(None, "PURPLE")
            if not hwnd:
                self.status.set("⚠ 퍼플 창 없음 — 지정계정 확인 건너뜀")
                return

            orig_placement = win32gui.GetWindowPlacement(hwnd)

            # 캡처 전에 퍼플을 '최대화 + 앞으로' — 아이디 표시 영역 좌표가 최대화 기준이라
            # 최대화 상태에서 찍어야 OCR 인식이 맞다.
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.6)
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            try:
                win32gui.BringWindowToTop(hwnd)
            except Exception:
                pass
            time.sleep(0.6)

            # 1단계: 리니지M 좌측버튼(profile_reveal_btn) 클릭 → 계정 확인
            if self.cfg.get("profile_reveal_btn"):
                pyautogui.click(*self.cfg["profile_reveal_btn"])
                time.sleep(1)

            matched, ocr_id, ratio = self._is_target_account(hwnd)
            self.status.set(f"{'✔ 아이디 확인됨' if matched else '🔄 아이디 다름 → 퍼플 전환 중...'} ('{ocr_id}' {int(ratio*100)}%)")

            if not matched:
                # 2단계: Purple 포그라운드로 가져와서 프로필 전환 (이미 최대화 상태)
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                time.sleep(0.3)
                try:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(1.0)
                if self.cfg.get("profile_btn"):
                    pyautogui.click(*self.cfg["profile_btn"]); time.sleep(2)
                if self.cfg.get("google_acc"):
                    pyautogui.click(*self.cfg["google_acc"]); time.sleep(2)
                if self.cfg.get("confirm_btn"):
                    pyautogui.click(*self.cfg["confirm_btn"]); time.sleep(3)
                self.status.set("✔ 퍼플 지정계정 전환 완료")

            # 원래 상태로 복원 후 최소화
            win32gui.SetWindowPlacement(hwnd, orig_placement)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception as e:
            self.status.set(f"⚠ 퍼플 전환 오류: {e}")

    def _system_idle_seconds(self):
        """Windows 마지막 입력(마우스+키보드) 이후 경과 초"""
        import ctypes
        class _LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0

    def _wait_system_idle(self, minutes=15, deadline=None):
        """시스템이 minutes분 이상 유휴 상태가 될 때까지 대기. 멈춤 시 즉시 반환.
        deadline(datetime)이 지나면 False 반환(대기 포기). 성공/중단은 True."""
        import datetime as _dt
        required = minutes * 60
        while True:
            if getattr(self, "_sched_any_stop", False):
                return True
            if deadline and _dt.datetime.now() >= deadline:
                return False
            idle = self._system_idle_seconds()
            if idle >= required:
                return True
            remaining = int((required - idle) / 60)
            self.after(0, lambda r=remaining: self.status.set(
                f"⏸ 컴퓨터 사용 중 — {r}분 더 대기 후 스케줄 실행..."))
            for _ in range(60):  # 30초를 0.5초씩 나눠 stop 즉시 감지
                if getattr(self, "_sched_any_stop", False):
                    return True
                if deadline and _dt.datetime.now() >= deadline:
                    return False
                time.sleep(0.5)

    def _wait_mouse_idle_sched(self, idle_sec=5.0):
        """스케줄 작업용 마우스 idle 대기 — stop flag 없이 단순 대기"""
        import pyautogui as _pg
        prev = _pg.position()
        time.sleep(0.1)
        cur = _pg.position()
        if cur == prev:
            return
        self.after(0, lambda: self.status.set(f"⏸ 마우스 움직임 감지 — {idle_sec}초 정지 후 재개..."))
        last_move = time.time()
        prev = cur
        while True:
            time.sleep(0.1)
            cur = _pg.position()
            if cur != prev:
                last_move = time.time()
                prev = cur
            elif time.time() - last_move >= idle_sec:
                return

    def _run_past_scheduled(self):
        import random, datetime
        self._sched_any_stop = False
        self._past_stop = False
        self._minimize_claude()          # 클로드(항상위)가 클릭 가리지 않게 먼저 내림
        self.after(0, self._send_to_back)
        slots = self.cfg.get("past_slots", [])
        active = [(i, s) for i, s in enumerate(slots)
                  if any(s.get("coords", []))]
        if not active:
            return

        # 각 슬롯마다 5:03~5:25 사이 무작위 시각 배정
        base = datetime.datetime.now().replace(hour=5, minute=3, second=0, microsecond=0)
        window = 22 * 60  # 22분
        schedule = sorted([(random.uniform(0, window), i, s) for i, s in active])

        self.status.set(f"🏝 과거섬 {len(active)}개 슬롯 랜덤 실행 대기...")
        elapsed = (datetime.datetime.now() - base).total_seconds()

        for delay, si, slot in schedule:
            wait = delay - elapsed
            if wait > 0:
                mins = int(wait // 60); secs = int(wait % 60)
                name = slot.get("name", f"#{si+1}")
                self.status.set(f"🏝 [{name}] {mins}분 {secs}초 후 실행...")
                waited = 0
                while waited < wait:
                    if getattr(self, "_sched_any_stop", False): return
                    time.sleep(0.5); waited += 0.5
            if getattr(self, "_sched_any_stop", False): return
            elapsed = (datetime.datetime.now() - base).total_seconds()
            self._run_past(slot_idx=si)

        self.status.set("✔ 과거섬 전체 슬롯 완료!")

    def _run_mail_scheduled(self):
        import random, datetime
        self._minimize_claude()          # 클로드(항상위)가 클릭 가리지 않게 먼저 내림
        self.after(0, self._send_to_back)
        slots = self.cfg.get("mail_slots", [])
        active = [(i, s) for i, s in enumerate(slots)
                  if any(c for c in s.get("coords", []))]
        if not active:
            return

        # 각 클라이언트마다 23:30~23:50 사이 무작위 시각 배정
        base = datetime.datetime.now().replace(hour=23, minute=30, second=0, microsecond=0)
        window = 20 * 60  # 20분(1200초)
        schedule = sorted([(random.uniform(0, window), i, s) for i, s in active])

        self.status.set(f"🕘 23:30~23:50 우편함 {len(active)}개 랜덤 실행 대기...")
        elapsed = (datetime.datetime.now() - base).total_seconds()
        # 시간대(23:50)를 넘기면 남은 슬롯은 포기하고 잠금을 놓는다 — 새벽 스케줄을 막지 않게
        end_t = base + datetime.timedelta(seconds=window)

        for delay, si, slot in schedule:
            if datetime.datetime.now() >= end_t:
                self.status.set("🕘 우편함 — 23:50 지남, 남은 슬롯 포기 (내일 재시도)")
                return
            wait = delay - elapsed
            if wait > 0:
                mins = int(wait // 60); secs = int(wait % 60)
                name = slot.get("name", f"#{si+1}")
                self.status.set(f"🕘 [{name}] {mins}분 {secs}초 후 실행...")
                waited = 0
                while waited < wait:
                    if getattr(self, "_sched_any_stop", False): return
                    time.sleep(0.5); waited += 0.5
            if getattr(self, "_sched_any_stop", False): return
            elapsed = (datetime.datetime.now() - base).total_seconds()
            name = slot.get("name", f"#{si+1}")
            if not self._wait_system_idle(15, deadline=end_t):
                self.status.set("🕘 우편함 — 23:50까지 유휴시간 못 확보, 포기 (내일 재시도)")
                return
            if getattr(self, "_sched_any_stop", False): return
            self.status.set(f"🕘 [{name}] 우편함 클릭 중...")
            self._run_mail(slot_idx=si)

        self.status.set("✔ 전체 우편함 클릭 완료!")

    def _start_mail(self):
        if not self._try_busy_or_queue("우편함", self._start_mail): return
        self._mail_stop = False
        self._sched_any_stop = False
        self._set_btn("btn_mail_run", state="disabled")
        self._set_btn("btn_mail_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("우편함", self._run_mail_standalone), daemon=True).start())

    def _stop_mail(self):
        self._mail_stop = True
        self.status.set("우편함 멈추는 중...")

    def _run_mail_standalone(self):
        self._run_mail()
        self.after(0, lambda: self._set_btn("btn_mail_run", state="normal"))
        self.after(0, lambda: self._set_btn("btn_mail_stop", state="disabled"))
        self._mail_stop = False
        self.after(0, self._restore_back)

    def _run_mail(self, slot_idx=None):
        """slot_idx 지정 시 해당 슬롯만, None이면 전체 16개 랜덤 순서 실행"""
        self._start_pause()
        try:
            slots = self.cfg.get("mail_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(c for c in s.get("coords", []) if c)]
                random.shuffle(targets)
            for si, slot in targets:
                if self._mail_stop: break
                name = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [])
                valid = [(j, c) for j, c in enumerate(coords) if c and len(c) >= 2]
                if not valid: continue
                for k, (j, coord) in enumerate(valid):
                    if self._mail_stop: break
                    if not self._wait_mouse_idle("_mail_stop"): break
                    if j == 1:
                        # 좌표2는 연속 7번 딱딱딱 (짧은 간격)
                        for t in range(7):
                            if self._mail_stop: break
                            self.status.set(f"🕘 [{name}] 클릭2 연속 {t+1}/7...")
                            pyautogui.click(*coord)
                            if t < 6:
                                time.sleep(random.uniform(0.12, 0.25))
                    else:
                        self.status.set(f"🕘 [{name}] 우편함 클릭 {j+1}...")
                        pyautogui.click(*coord)
                    if k < len(valid) - 1:
                        time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if not self._mail_stop:
                    slot_wait = random.uniform(2.0, 4.0)
                    self.status.set(f"🕘 다음 슬롯 대기 {slot_wait:.1f}초...")
                    time.sleep(slot_wait)
            self.status.set("✔ 우편함 클릭 완료!" if not self._mail_stop else "우편함 멈춤")
        except Exception as e:
            self.status.set(f"오류: {e}")

    def _reg_mail_click(self, slot_idx, click_idx):
        self._reg_mail_slot_idx  = slot_idx
        self._reg_mail_click_idx = click_idx
        self.status.set(f"3초 후 우편함 #{slot_idx+1} 클릭{click_idx+1} 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="mail")])

    def on_mail_coord(self, x, y):
        si = self._reg_mail_slot_idx
        ci = self._reg_mail_click_idx
        self.cfg["mail_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 우편함 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_mail_name(self, idx):
        name = self._mail_name_vars[idx].get().strip() or "미등록"
        self.cfg["mail_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_mail(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_mail, args=(idx,), daemon=True).start()

    def _del_mail(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"우편함 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["mail_slots"][idx] = {"name": "미등록", "coords": [None]*MAIL_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_mail(self, idx):
        coords = self.cfg["mail_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["mail_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_mail_slot_idx  = idx
            self._reg_mail_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="mail"))

        def _save(dot_idx, nx, ny):
            self.cfg["mail_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 우편함 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"우편함 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _group_copy_mail_slot(self, idx):
        import copy
        src = self.cfg["mail_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["mail_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["mail_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if dots:
            self.withdraw()
            self.after(300, lambda: _MailGroupMoveOverlay(self, idx, dots))

    def _group_copy_mail(self):
        import copy
        src = self.cfg["mail_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, MAIL_SLOTS):
            self.cfg["mail_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{MAIL_SLOTS:02d} 전체 복사 완료")

    # ── 주말던전 ──────────────────────────────────────────────────────
    def _start_dungeon(self):
        if not self._try_busy_or_queue("주말던전", self._start_dungeon): return
        self._dungeon_stop = False
        self._set_btn("btn_dungeon_run", state="disabled")
        self._set_btn("btn_dungeon_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("주말던전", self._run_dungeon), daemon=True).start())

    def _run_dungeon(self, slot_idx=None):
        self._start_pause()
        try:
            slots = self.cfg.get("dungeon_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
                random.shuffle(targets)   # 슬롯 클릭 순서 매번 랜덤
            for si, slot in targets:
                if self._dungeon_stop: break
                name = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [])
                while len(coords) < DUNGEON_CLICKS:   # 예전 3개짜리 데이터 호환
                    coords.append(None)
                if not self._wait_mouse_idle("_dungeon_stop"): return
                # 클릭1~5를 순서대로, 클릭 사이 간격만 랜덤
                order = [j for j in range(DUNGEON_CLICKS) if coords[j]]
                for n, j in enumerate(order):
                    if self._dungeon_stop: break
                    self.status.set(f"🏰 [{name}] 클릭{j+1}...")
                    click_at(*coords[j])
                    if n < len(order) - 1:
                        time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
            self.status.set("✔ 던전 실행 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self._set_btn("btn_dungeon_run", state="normal")
            self._set_btn("btn_dungeon_stop", state="disabled")

    def _reg_dungeon_click(self, slot_idx, click_idx):
        self._reg_dungeon_slot_idx  = slot_idx
        self._reg_dungeon_click_idx = click_idx
        label = ["클릭1", "클릭2", "클릭3", "클릭4", "클릭5"][click_idx]
        self.status.set(f"3초 후 던전 #{slot_idx+1} [{label}] 위치 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                   CoordOverlay(self, mode="dungeon")])

    def on_dungeon_coord(self, x, y):
        si = self._reg_dungeon_slot_idx
        ci = self._reg_dungeon_click_idx
        self.cfg["dungeon_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        label = ["클릭1", "클릭2", "클릭3", "클릭4", "클릭5"][ci]
        self.status.set(f"✔ 던전 #{si+1} [{label}] 등록: ({x},{y})")
        self.deiconify()

    def _save_dungeon_name(self, idx):
        name = self._dungeon_name_vars[idx].get().strip() or "미등록"
        self.cfg["dungeon_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_dungeon(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_dungeon, args=(idx,), daemon=True).start()

    def _del_dungeon(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"던전 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["dungeon_slots"][idx] = {"name": "미등록", "coords": [None]*DUNGEON_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_dungeon(self, idx):
        coords = self.cfg["dungeon_slots"][idx].get("coords", [])
        LABELS_D = ["클릭1", "클릭2", "클릭3", "클릭4", "클릭5"]
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"던전 #{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["dungeon_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_dungeon_slot_idx  = idx
            self._reg_dungeon_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="dungeon"))

        def _save(dot_idx, nx, ny):
            self.cfg["dungeon_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 던전 #{idx+1:02d} {LABELS_D[dot_idx]} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"던전 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save, dot_r=4)

    def _group_copy_dungeon_slot(self, idx):
        import copy
        src = self.cfg["dungeon_slots"][idx-1].get("coords", [])
        if not any(src):
            self.status.set(f"던전 #{idx:02d} 위에 복사할 좌표가 없습니다")
            return
        self.cfg["dungeon_slots"][idx]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["dungeon_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            return
        self.withdraw()
        self.after(300, lambda: _DungeonGroupMoveOverlay(self, idx, dots))

    # ── 과거의말하는섬 ────────────────────────────────────────────────
    def _start_past(self):
        if not self._try_busy_or_queue("과거섬", self._start_past): return
        self._past_stop = False
        self._sched_any_stop = False
        self._set_btn("btn_past_run", state="disabled", bg="#f39c12", text="⏳ 실행중...")
        self._set_btn("btn_past_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("과거섬", self._run_past), daemon=True).start())

    def _run_past(self, slot_idx=None):
        self._start_pause()
        try:
            self.status.set("2초 후 과거의말하는섬 실행...")
            self.after(0, self._send_to_back)
            time.sleep(2)
            slots = self.cfg.get("past_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
                random.shuffle(targets)   # 슬롯 실행 순서 매번 랜덤
            for si, slot in targets:
                if self._past_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*PAST_CLICKS)
                # 슬롯별 랜덤 딜레이
                slot_delay = random.uniform(3.0, 15.0)
                self.status.set(f"🏝 [{name}] {slot_delay:.0f}초 후 실행...")
                elapsed = 0
                while elapsed < slot_delay:
                    if self._past_stop: break
                    time.sleep(0.5); elapsed += 0.5
                if self._past_stop: break
                # 0: 클릭1(신규) → 1: 마우스이동(hover) → 2: 클릭
                if coords[0]:
                    self.status.set(f"🏝 [{name}] 클릭1...")
                    pyautogui.click(*coords[0])
                    time.sleep(random.uniform(3.0, 6.0) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._past_stop: break
                if coords[1]:
                    self.status.set(f"🏝 [{name}] 마우스 이동...")
                    pyautogui.moveTo(*coords[1])
                    time.sleep(random.uniform(3.0, 5.0) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._past_stop: break
                if len(coords) > 2 and coords[2]:
                    self.status.set(f"🏝 [{name}] 클릭2...")
                    pyautogui.click(*coords[2])
                if self._past_stop: break
                # 슬롯 간 대기 (가끔 긴 휴식)
                pause = random.uniform(4.0, 8.0)
                if random.random() < 0.25:
                    pause += random.uniform(3.0, 7.0)
                time.sleep(pause)
            self.status.set("✔ 과거의말하는섬 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_back)
            self._set_btn("btn_past_run", state="normal", bg="#c0392b", text="▶  실행")
            self._set_btn("btn_past_stop", state="disabled")

    def _reg_past_click(self, slot_idx, click_idx):
        self._reg_past_slot_idx  = slot_idx
        self._reg_past_click_idx = click_idx
        if click_idx == 1:
            # 이동 좌표는 카운트다운 후 현재 마우스 위치 자동 캡처
            self._past_hover_countdown(slot_idx, 3)
        else:
            self.status.set(f"3초 후 과거의말하는섬 #{slot_idx+1} [클릭{click_idx+1}] 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                       CoordOverlay(self, mode="past")])

    def _past_hover_countdown(self, slot_idx, remaining):
        if remaining > 0:
            self.status.set(f"⏱ {remaining}초 안에 마우스를 이동해두세요 — 자동 저장됩니다")
            self.after(1000, lambda: self._past_hover_countdown(slot_idx, remaining - 1))
        else:
            x, y = pyautogui.position()
            self.on_past_coord(x, y)

    def on_past_coord(self, x, y):
        si = self._reg_past_slot_idx
        ci = self._reg_past_click_idx
        self.cfg["past_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 과거의말하는섬 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_past_name(self, idx):
        name = self._past_name_vars[idx].get().strip() or "미등록"
        self.cfg["past_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_past(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_past, args=(idx,), daemon=True).start()

    def _del_past(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"과거의섬 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["past_slots"][idx] = {"name": "미등록", "coords": [None]*PAST_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_past(self, idx):
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["past_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_past_slot_idx  = idx
            self._reg_past_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="past"))

        def _save(dot_idx, nx, ny):
            self.cfg["past_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 과거섬 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"과거섬 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _group_copy_past_slot(self, idx):
        import copy
        src = self.cfg["past_slots"][idx-1].get("coords", [])
        if not any(src[1:]):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표(2,3번)가 없습니다")
            return
        dst = self.cfg["past_slots"][idx]["coords"]
        for j in (1, 2):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1, n) for n, c in enumerate(coords)
                if n > 0 and c and len(c) >= 2]
        if dots:
            self.withdraw()
            def _open_past(i=idx, d=dots):
                try:
                    _PastGroupMoveOverlay(self, i, d)
                except Exception as e:
                    self.deiconify()
                    self.status.set(f"오류: {e}")
            self.after(300, _open_past)

    def _group_copy_past_1to4(self):
        import copy
        src = self.cfg["past_slots"][0].get("coords", [])
        if not any(src):
            self.status.set("#01 슬롯에 복사할 좌표가 없습니다")
            return
        for i in range(1, 4):
            self.cfg["past_slots"][i]["coords"] = copy.deepcopy(src)
        save_cfg(self.cfg); self._refresh_ui()
        # #02~#04 순서대로 그룹 이동 오버레이 열기
        self._past_chain_move(1, end=4)

    def _past_chain_move(self, idx, end):
        coords = self.cfg["past_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            if idx + 1 < end:
                self.after(300, lambda: self._past_chain_move(idx+1, end))
            return
        self.withdraw()
        self.after(300, lambda: _PastChainMoveOverlay(self, idx, dots, idx+1, end))

    def _group_copy_past(self):
        import copy
        src = self.cfg["past_slots"][0].get("coords", [])
        if not any(src[1:]):
            self.status.set("#01 슬롯에 복사할 좌표(2,3번)가 없습니다")
            return
        for i in range(1, PAST_SLOTS):
            dst = self.cfg["past_slots"][i]["coords"]
            for j in (1, 2):
                if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{PAST_SLOTS:02d} 전체 복사 완료")

    def _start_sched(self):
        if not self._try_busy_or_queue("스케줄", self._start_sched): return
        self._sched_stop = False
        self._sched_any_stop = False
        self._set_btn("btn_sched_run", state="disabled", bg="#f39c12", text="⏳ 실행중...")
        self._set_btn("btn_sched_stop", state="normal")
        self._minimize_all()
        self.after(300, lambda: threading.Thread(target=self._run_task, args=("스케줄", self._run_sched), daemon=True).start())

    def _run_sched(self, slot_idx=None):
        self._start_pause()
        try:
            self._sync_sched_click1()   # 실행 직전 과거섬 클릭1 반영(항상 최신값으로 실행)
            self.status.set("2초 후 매일매일 스케줄 실행...")
            self.after(0, self._send_to_back)
            time.sleep(2)
            slots = self.cfg.get("sched_slots", [])
            if slot_idx is not None:
                targets = [(slot_idx, slots[slot_idx])] if slot_idx < len(slots) else []
            else:
                targets = [(i, s) for i, s in enumerate(slots)
                           if any(s.get("coords", []))]
                random.shuffle(targets)   # 슬롯 실행 순서 매번 랜덤
            if slot_idx is None and len(targets) > 1:
                # 2슬롯씩 번갈아(웨이브). '마우스 이동(좌표2) → 클릭2(좌표3)'는
                # 한 묶음으로 처리해 사이에 다른 슬롯이 끼지 못하게 한다.
                self._run_sched_wave(targets)
                self.status.set("✔ 매일매일 스케줄 완료!")
                return
            for si, slot in targets:
                if self._sched_stop: break
                name   = slot.get("name", f"#{si+1}")
                coords = slot.get("coords", [None]*SCHED_CLICKS)
                if not self._wait_mouse_idle("_sched_stop"): return
                _snap = self._user_focus_snap()   # 사용자가 보던 창 (슬롯 끝나면 복귀)
                if coords[0]:
                    self.status.set(f"📅 [{name}] 클릭1...")
                    self._wait_user_free("_sched_stop")
                    click_at(*coords[0])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._sched_stop: break
                if coords[1]:
                    self.status.set(f"📅 [{name}] 마우스 이동...")
                    self._wait_user_free("_sched_stop")
                    move_at(*coords[1])
                    time.sleep(random.uniform(0.1, 0.6) + random.uniform(EXTRA_GAP_MIN, EXTRA_GAP_MAX))
                if self._sched_stop: break
                if len(coords) > 2 and coords[2]:
                    self.status.set(f"📅 [{name}] 클릭2...")
                    self._wait_user_free("_sched_stop")
                    click_at(*coords[2])
                self._user_focus_back(_snap)      # 이 슬롯 끝 — 사용자 창으로 복귀
                if self._sched_stop: break
                time.sleep(random.uniform(1.38, 1.80))   # 슬롯 사이 (2.3~3.0초에서 40% 줄임)
            self.status.set("✔ 매일매일 스케줄 완료!")
        except Exception as e:
            self.status.set(f"오류: {e}")
        finally:
            self.after(0, self._restore_back)
            self._set_btn("btn_sched_run", state="normal", bg="#16a085", text="▶  실행")
            self._set_btn("btn_sched_stop", state="disabled")

    def _run_sched_wave(self, targets):
        """스케줄 3슬롯 번갈아 — 한 슬롯이 기다리는 동안 다른 슬롯을 진행한다.
        '마우스 이동 → 클릭2'는 반드시 붙여서 한 묶음으로 처리한다
        (사이에 다른 클릭이 끼면 이동해둔 자리가 풀린다)."""
        LANES = 3        # 동시 3슬롯 (2026-08-28 사용자 지시 — 시간이 촉박해서)
        state = {si: {"slot": sl, "u": 0, "due": time.time()} for si, sl in targets}
        order = [si for si, _ in targets]
        active, waiting = order[:LANES], order[LANES:]
        last, done = None, 0
        self.status.set(f"📅 스케줄 번갈아 실행 — 동시 {LANES}슬롯 · 1번부터 순서대로 ({len(targets)}슬롯)")
        while not self._sched_stop:
            for si in [x for x in active if state[x]["u"] >= 2]:
                active.remove(si)
                if waiting:
                    nx = waiting.pop(0)
                    state[nx]["due"] = time.time() + random.uniform(0.5, 1.2)
                    active.append(nx)
            alive = [si for si in active if state[si]["u"] < 2]
            if not alive:
                break
            now = time.time()
            ready = [si for si in alive if state[si]["due"] <= now]
            if not ready:
                nxt = min(state[si]["due"] for si in alive)
                time.sleep(max(0.05, min(nxt - now, 0.5)))
                continue
            # 준비된 것 중 **번호가 앞선 슬롯부터** (섞지 않는다, 2026-08-28)
            si = min(ready)
            st = state[si]
            slot = st["slot"]
            name = slot.get("name", f"#{si+1}")
            coords = slot.get("coords", [None] * SCHED_CLICKS)
            if si != last:
                time.sleep(random.uniform(0.4, 0.9))     # 다른 창으로 넘어갈 여유
                last = si
            if not self._wait_mouse_idle("_sched_stop"):
                return
            if self._sched_stop:
                break
            if st["u"] == 0:
                if coords[0]:
                    self.status.set(f"📅 [{name}] 클릭1...  (남은 슬롯 {len(alive)})")
                    self._wait_user_free("_sched_stop")
                    _snap = self._user_focus_snap()
                    click_at(*coords[0])
                    self._user_focus_back(_snap)
                    done += 1
                st["due"] = time.time() + random.uniform(1.8, 3.0)   # 클릭1 뒤 여유
            else:
                # ── 좌표2 → 좌표3 은 여기서 '한 번에' 끝낸다 ──
                # 사이에 다른 슬롯이 끼면 올려둔 자리가 풀려 클릭2가 씹힌다.
                _snap = self._user_focus_snap()   # 묶음 끝나면 사용자 창으로 복귀
                if coords[1]:
                    self.status.set(f"📅 [{name}] 마우스 이동...")
                    self._wait_user_free("_sched_stop")
                    move_at(*coords[1])
                    time.sleep(random.uniform(1.8, 3.0))     # 이동 뒤 여유
                if len(coords) > 2 and coords[2]:
                    self.status.set(f"📅 [{name}] 클릭2...  (좌표2와 한 묶음)")
                    self._wait_user_free("_sched_stop")
                    click_at(*coords[2])
                    done += 1
                self._user_focus_back(_snap)
                st["due"] = time.time() + random.uniform(1.9, 2.5)   # 슬롯 끝 대기 (40% 단축)
            st["u"] += 1
            time.sleep(random.uniform(0.25, 0.5))        # 클릭끼리 최소 간격

    def _reg_sched_click(self, slot_idx, click_idx):
        self._reg_sched_slot_idx  = slot_idx
        self._reg_sched_click_idx = click_idx
        if click_idx == 1:
            # 이동 좌표는 카운트다운 후 현재 마우스 위치 자동 캡처
            self._minimize_claude()   # 클로드가 타깃을 가리지 않게 (런처는 안내 위해 유지)
            self._sched_hover_countdown(slot_idx, 3)
        else:
            self.status.set(f"3초 후 스케줄 #{slot_idx+1} [클릭{click_idx+1}] 위치 클릭하세요!")
            self.after(3000, lambda: [self.withdraw(), time.sleep(0.2),
                                       CoordOverlay(self, mode="sched")])

    def _sched_hover_countdown(self, slot_idx, remaining):
        if remaining > 0:
            self.status.set(f"⏱ {remaining}초 안에 마우스를 이동해두세요 — 자동 저장됩니다")
            self.after(1000, lambda: self._sched_hover_countdown(slot_idx, remaining - 1))
        else:
            x, y = pyautogui.position()
            self.on_sched_coord(x, y)

    def on_sched_coord(self, x, y):
        si = self._reg_sched_slot_idx
        ci = self._reg_sched_click_idx
        self.cfg["sched_slots"][si]["coords"][ci] = [x, y]
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ 스케줄 #{si+1} 클릭{ci+1} 등록: ({x},{y})")
        self.deiconify()

    def _save_sched_name(self, idx):
        name = self._sched_name_vars[idx].get().strip() or "미등록"
        self.cfg["sched_slots"][idx]["name"] = name
        save_cfg(self.cfg)

    def _test_sched(self, idx):
        self._minimize_all()
        threading.Thread(target=self._run_sched, args=(idx,), daemon=True).start()

    def _del_sched(self, idx):
        if not messagebox.askyesno("슬롯 삭제", f"스케줄 #{idx+1} 슬롯 전체 좌표를 삭제하시겠습니까?", default="no"):
            return
        self.cfg["sched_slots"][idx] = {"name": "미등록", "coords": [None]*SCHED_CLICKS}
        save_cfg(self.cfg); self._refresh_ui()

    def _preview_sched(self, idx):
        coords = self.cfg["sched_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1) for n, c in enumerate(coords) if c and len(c) >= 2]
        if not dots:
            self.status.set(f"#{idx+1:02d} 등록된 좌표가 없습니다")
            return
        name = self.cfg["sched_slots"][idx].get("name", f"#{idx+1:02d}")

        def rereg(dot_idx):
            self._reg_sched_slot_idx  = idx
            self._reg_sched_click_idx = dot_idx
            self.deiconify()
            self.after(200, lambda: CoordOverlay(self, mode="sched"))

        def _save(dot_idx, nx, ny):
            self.cfg["sched_slots"][idx]["coords"][dot_idx] = [nx, ny]
            save_cfg(self.cfg); self._refresh_ui()
            self.status.set(f"✔ 스케줄 #{idx+1:02d} 클릭{dot_idx+1} 이동 저장: ({nx},{ny})")

        self._open_dot_preview(f"스케줄 #{idx+1:02d} {name}", dots,
                               rereg_fn=rereg, save_fn=_save)

    def _group_copy_sched_slot(self, idx):
        import copy
        src = self.cfg["sched_slots"][idx-1].get("coords", [])
        if not any(src[1:]):
            self.status.set(f"#{idx:02d} 위에 복사할 좌표(2,3번)가 없습니다")
            return
        dst = self.cfg["sched_slots"][idx]["coords"]
        for j in (1, 2):
            if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        coords = self.cfg["sched_slots"][idx].get("coords", [])
        dots = [(c[0], c[1], n+1, n) for n, c in enumerate(coords)
                if n > 0 and c and len(c) >= 2]
        if dots:
            self.withdraw()
            def _open_sched(i=idx, d=dots):
                try:
                    _SchedGroupMoveOverlay(self, i, d)
                except Exception as e:
                    self.deiconify()
                    self.status.set(f"오류: {e}")
            self.after(300, _open_sched)

    def _group_copy_sched(self):
        import copy
        src = self.cfg["sched_slots"][0].get("coords", [])
        if not any(src[1:]):
            self.status.set("#01 슬롯에 복사할 좌표(2,3번)가 없습니다")
            return
        for i in range(1, SCHED_SLOTS):
            dst = self.cfg["sched_slots"][i]["coords"]
            for j in (1, 2):
                if j < len(src): dst[j] = copy.deepcopy(src[j])
        save_cfg(self.cfg); self._refresh_ui()
        self.status.set(f"✔ #01 좌표 → #02~#{SCHED_SLOTS:02d} 전체 복사 완료")

    def _reg_sched_click1_all(self):
        ref = self.cfg["sched_slots"][0]["coords"][0]
        if not ref:
            self.status.set("슬롯#01 클릭1 좌표가 없습니다. 먼저 등록해주세요.")
            return
        self._sched_click1_ref = list(ref)
        self.status.set(f"기준: 슬롯#01 클릭1 ({ref[0]},{ref[1]}) → 3초 후 새 위치에 마우스를 올려두세요")
        self.after(3000, self._capture_sched_click1_all)

    def _capture_sched_click1_all(self):
        nx, ny = pyautogui.position()
        ox, oy = self._sched_click1_ref
        dx, dy = nx - ox, ny - oy
        for i in range(SCHED_SLOTS):
            c = self.cfg["sched_slots"][i]["coords"][0]
            if c:
                self.cfg["sched_slots"][i]["coords"][0] = [c[0] + dx, c[1] + dy]
        save_cfg(self.cfg)
        self._refresh_ui()
        self.status.set(f"✔ 클릭1 전체 이동 완료 (dx={dx:+d}, dy={dy:+d})")

    def _take_layout_screenshot(self, count):
        import time
        time.sleep(0.4)
        try:
            from PIL import ImageGrab, ImageDraw, ImageFont
            shot = ImageGrab.grab(all_screens=True)
            draw = ImageDraw.Draw(shot)
            positions = self.cfg.get("window_positions", [])
            for idx, p in enumerate(positions):
                x, y, w, h = p["x"], p["y"], p["w"], p["h"]
                # 창 테두리
                draw.rectangle([x, y, x+w, y+h], outline=(255, 80, 80), width=3)
                # 번호 배경 박스
                pad = 6
                num_text = f"#{idx+1:02d}"
                box_w, box_h = 60, 36
                draw.rectangle([x+4, y+4, x+4+box_w, y+4+box_h], fill=(255, 80, 80))
                draw.text((x+8, y+8), num_text, fill=(255, 255, 255))
            path = os.path.join(BASE, "lineagem_logs", "window_layout.png")
            shot.save(path)
        except Exception:
            pass
        self.deiconify()
        self.lift()
        self.status.set(f"✔ 창 배치 {count}개 저장 완료")
        # 캡처 후 잠깐 보여주다 5초 후 자동 숨김
        self._show_layout_preview()
        self.after(5000, self._hide_layout_preview)

    def _section_wins(self):
        # 고정 목록 + 열릴 때 자동 등록된 창 전부 (새 기능 창이 빠지지 않게)
        attrs = {"_settings_win","_hunt_win","_mail_win","_past_win2",
                 "_sched_win","_dungeon_win","_daya_win","_pass_win","_seq_win",
                 "_dc_win","_accounts_win","_doll_win","_wdoff_win","_item_win",
                 "_lastrun_win","_lock_win","_scroll_win","_dollchk_win","_relic_win","_tj_win","_coupon_win","_market_win","_dragon_win","_knight_win","_fish_win","_circus_win","_circus2_win","_circus3_win",
                 "_eventshop_win","_reroll_win","_verify_win"}
        attrs |= getattr(self, "_section_attrs", set())
        wins = [getattr(self, a) for a in attrs
                if getattr(self, a, None) and getattr(self, a).winfo_exists()]
        # 슬롯 좌표 등록 팝업(항상위 Toplevel)도 실행 중엔 최소화 대상
        for st in getattr(self, "_grid_state", {}).values():
            p = st.get("pop")
            if p and p.winfo_exists():
                wins.append(p)
        return wins

    def _minimize_all(self):
        # 실행 중에는 메인런처도 최소화한다 (2026-08-07 사용자 지시 — 화면에 남아 있으면
        # 실수로 클릭할 수 있어서). 완료 후엔 _restore_back이 '맨 뒤'로만 되살린다.
        for w in self._section_wins():
            w.iconify()
        self._send_to_back()
        try:
            self.iconify()
        except Exception:
            pass
        self._minimize_claude()

    def _go_home(self):
        """[📍 제자리] — 런처를 고정 위치로 되돌린다."""
        pos = self.cfg.get("main_win_fixed") or self.cfg.get("main_win_pos")
        if not pos:
            self.status.set("고정 위치가 없습니다"); return
        try:
            self.deiconify()
            self.geometry(f"+{int(pos[0])}+{int(pos[1])}")
        except Exception:
            pass

    def _back_and_claude(self):
        """[⬇ 맨뒤로] 버튼 — 런처는 맨 뒤로, 섬/던전 실행기는 그 바로 앞,
        클로드 창은 최소화. (실행기는 최소화하지 않아 바로 쓸 수 있다)"""
        self._send_to_back()
        self._islands_behind_front()
        self._minimize_claude()

    def _islands_behind_front(self):
        """섬/던전 실행기 창들을 '메인런처 바로 앞(클라이언트 뒤)'에 배치.
        창 제목으로 즉시 찾는다 — 프로세스 조회(PowerShell)는 2초씩 걸려 쓰지 않는다."""
        try:
            import win32gui, win32con
            main = win32gui.FindWindow(None, "리니지M 자동 실행")
            if not main:
                return
            flags = (win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    t = win32gui.GetWindowText(hwnd)
                    if t.startswith("🏝") or "섬/던전 실행기" in t:
                        l, tp, r, b = win32gui.GetWindowRect(hwnd)
                        if r - l > 200 and b - tp > 200:      # 실제 실행기 창만
                            win32gui.SetWindowPos(hwnd, main, 0, 0, 0, 0, flags)
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(_cb, None)
        except Exception:
            pass

    def _send_to_back(self):
        """창을 최소화하지 않고 z순서 맨 뒤로 (리니지M 클라이언트 뒤)."""
        try:
            self.lower()
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, "리니지M 자동 실행")
            if hwnd:
                win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                                      win32con.SWP_NOACTIVATE)
        except Exception:
            pass

    def _restore_back_quiet(self):
        """완료 후 복원 — 앞으로 띄우지 않고 곧바로 맨 뒤로 되살린다 (모든 실행 공통)."""
        try:
            if getattr(self, "_back_after_id", None):
                self.after_cancel(self._back_after_id)
                self._back_after_id = None
        except Exception:
            pass
        self._quiet_restore = True          # <Map>/포커스 핸들러의 '앞으로 올리기' 억제
        try:
            self.deiconify()
        except Exception:
            pass
        self._send_to_back()
        self.after(200, self._send_to_back)
        self.after(600, self._send_to_back)
        self.after(1500, lambda: setattr(self, "_quiet_restore", False))

    def _show_done(self, text="완료"):
        """작업이 끝났음을 왼쪽 아래에 큰 빨간 글씨로 1시간 동안 알린다."""
        try:
            if not hasattr(self, "_done_var"):
                return
            import datetime as _dt
            self._done_var.set(text + chr(10) + f"{_dt.datetime.now():%H:%M}")
            old = getattr(self, "_done_after", None)
            if old:
                try: self.after_cancel(old)
                except Exception: pass
            self._done_after = self.after(3600000, lambda: self._done_var.set(""))   # 1시간 유지
        except Exception:
            pass

    def _restore_back(self):
        """모든 작업 완료 후 복원 — 앞으로 띄우지 않고 곧바로 '맨 뒤'로 되살린다.
        (2026-08-07 사용자 지시: 완료 후 창이 앞으로 나오지 않게 통일.
         결과는 나중에 런처를 직접 열어 상태줄에서 확인)
        (2026-08-09) 마지막 좌표를 누르자마자 끝내지 않고 2초 뒤에 마무리한다."""
        self.after(2000, self._restore_back_quiet)
        self.after(2000, self._show_done)          # 왼쪽 아래에 '완료' 1분 표시

    def _restore_all(self):
        self.deiconify()
        for w in self._section_wins():
            w.deiconify()

    def _show_layout_preview(self):
        # 메인+서브창 전부 최소화
        for w in self._section_wins():
            w.iconify()
        self._load_layout_preview()
        self._layout_preview_visible = True
        self.iconify()

    def _hide_layout_preview(self):
        self._layout_preview_frame.pack_forget()
        self._layout_preview_visible = False
        self._btn_layout_toggle.config(text="🖼 배치보기")
        self.deiconify()
        for w in self._section_wins():
            w.deiconify()

    def _toggle_layout_preview(self):
        if self._layout_preview_visible:
            self._hide_layout_preview()
        else:
            self._show_layout_preview()

    def _load_layout_preview(self):
        path = os.path.join(BASE, "lineagem_logs", "window_layout.png")
        frame = self._layout_preview_frame
        for w in frame.winfo_children():
            w.destroy()
        if not os.path.exists(path):
            tk.Label(frame, text="(배치 캡처 없음)", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            # 가로 폭을 프레임에 맞게 축소
            max_w = 900
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(frame, image=photo, cursor="hand2")
            lbl.image = photo
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e: __import__("subprocess").Popen(["explorer", path]))
        except Exception:
            tk.Label(frame, text="(미리보기 오류)", font=("맑은 고딕", 7), fg="#aaa").pack(side="left")

    # ── 창 배치 ───────────────────────────────────────────────────────
    def _get_purple_hwnds(self):
        """Purple/리니지 창의 (hwnd, left, top, width, height) 목록 반환"""
        import ctypes
        result = []
        def cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if ("Purple" in title or "리니지" in title) and ctypes.windll.user32.IsWindowVisible(hwnd):
                r = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                w = r.right - r.left
                h = r.bottom - r.top
                if w > 100 and h > 100:
                    result.append((hwnd, r.left, r.top, w, h))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
        return result

    def _capture_window_layout(self):
        wins = self._get_purple_hwnds()
        if not wins:
            messagebox.showwarning("창 없음", "퍼플/리니지 창을 찾을 수 없습니다."); return
        # 위치(위→아래, 왼→오른) 순으로 정렬해서 패턴만 저장
        wins_sorted = sorted(wins, key=lambda e: (e[2], e[1]))  # y, x 순
        positions = [{"x": x, "y": y, "w": w, "h": h}
                     for _, x, y, w, h in wins_sorted]
        self.cfg["window_positions"] = positions
        save_cfg(self.cfg)
        # 런처 최소화 후 스크린샷 → 복구
        self.iconify()
        self.after(600, lambda: self._take_layout_screenshot(len(positions)))

    def _clear_window_layout(self):
        self.cfg["window_positions"] = []
        save_cfg(self.cfg)
        self.status.set("창 배치 초기화 완료")

    def _apply_window_layout(self):
        positions = self.cfg.get("window_positions", [])
        if not positions:
            self.status.set("저장된 배치가 없습니다. 먼저 '현재 배치 캡처'를 눌러주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("퍼플/리니지 창을 찾을 수 없습니다."); return
        # 현재 창도 같은 기준(y, x)으로 정렬
        wins_sorted = sorted(wins, key=lambda e: (e[2], e[1]))
        applied, failed = 0, 0
        for i, (hwnd, *_) in enumerate(wins_sorted):
            if i >= len(positions): break
            p = positions[i]
            try:
                ok, _reason = self._apply_window_pos(hwnd, p)
            except Exception:
                ok = False
            applied += 1 if ok else 0
            failed  += 0 if ok else 1
        if failed:
            self.status.set(f"창 배치 복구: 성공 {applied}개 / 실패 {failed}개")
        else:
            self.status.set(f"✔ 창 배치 복구 완료 ({applied}개)")

    def _toggle_detail(self, detail, sv, row_frame, padx=14):
        if detail.winfo_ismapped():
            detail.pack_forget()
            sv.set(sv.get().replace("▴", "▾"))
        else:
            detail.pack(fill="x", padx=padx, pady=(0,4), after=row_frame)
            sv.set(sv.get().replace("▾", "▴"))

    def _toggle_hunt_detail(self, slot_idx):
        self._toggle_detail(self._hunt_detail_frames[slot_idx],
                            self._hunt_coord_sv[slot_idx],
                            self._hunt_row_frames[slot_idx])

    def _toggle_mail_detail(self, slot_idx):
        self._toggle_detail(self._mail_detail_frames[slot_idx],
                            self._mail_coord_sv[slot_idx],
                            self._mail_row_frames[slot_idx])

    def _toggle_dungeon_detail(self, slot_idx):
        self._toggle_detail(self._dungeon_detail_frames[slot_idx],
                            self._dungeon_coord_sv[slot_idx],
                            self._dungeon_row_frames[slot_idx])

    def _toggle_past_detail(self, slot_idx):
        self._toggle_detail(self._past_detail_frames[slot_idx],
                            self._past_coord_sv[slot_idx],
                            self._past_row_frames[slot_idx])

    def _toggle_pass_detail(self, slot_idx):
        self._toggle_detail(self._pass_detail_frames[slot_idx],
                            self._pass_coord_sv[slot_idx],
                            self._pass_row_frames[slot_idx])

    def _minimize_claude(self):
        """Claude 창 최소화"""
        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return True
            t = win32gui.GetWindowText(hwnd)
            if "claude" in t.lower():
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        win32gui.EnumWindows(_cb, None)

    def _assign_window(self, slot_idx):
        """카운트다운 후 클릭한 창을 슬롯에 지정"""
        def _countdown(n):
            if n > 0:
                self.status.set(f"#{slot_idx+1:02d} 창 지정 — {n}초 후 지정할 창을 클릭하세요!")
                self.after(1000, lambda: _countdown(n - 1))
            else:
                self.status.set(f"#{slot_idx+1:02d} 창 지정 — 지금 지정할 창을 클릭하세요! (클릭 대기 중...)")
                self._minimize_claude()
                self.withdraw()
                self.after(100, _wait_click)

        def _wait_click():
            _AssignWindowOverlay(self, slot_idx, self._on_assign_done)

        _countdown(1)

    def _on_assign_done(self, slot_idx, title):
        """지정 완료 후 버튼 초록으로 변경"""
        if slot_idx < len(self._hunt_assign_btns):
            self._hunt_assign_btns[slot_idx].config(text="✔지정", bg="#27ae60")
        self.status.set(f"✔ #{slot_idx+1:02d} 지정 완료 — [{title[:30]}]")

    def _preview_assigned_window(self, slot_idx):
        """지정된 창을 잠깐 맨 앞으로 띄워서 어떤 창인지 확인"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1:02d} — 지정된 창이 없습니다."); return
        wins = self._get_purple_hwnds()
        if not wins: return
        tx, ty = aw["cx"], aw["cy"]
        best = min(wins, key=lambda e: ((e[1]+e[3]//2-tx)**2 + (e[2]+e[4]//2-ty)**2))
        hwnd = best[0]
        HWND_TOP = 0
        SWP_NOSIZE = 0x0001; SWP_NOMOVE = 0x0002
        def _flash():
            for _ in range(3):
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                                                   SWP_NOSIZE | SWP_NOMOVE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.4)
        threading.Thread(target=_flash, daemon=True).start()
        title = aw.get("title", "")
        self.status.set(f"#{slot_idx+1:02d} 지정 창: [{title[:30]}]  {aw['w']}x{aw['h']}  @{aw['x']},{aw['y']}")

    _FIXED_W = 491
    _FIXED_H = 276

    def _find_hwnd_for_slot(self, aw, wins):
        """1) HWND  2) 창 제목 번호  3) 가장 가까운 위치 순으로 찾기"""
        # 1) HWND
        saved_hwnd = aw.get("hwnd")
        if saved_hwnd and win32gui.IsWindow(saved_hwnd):
            for e in wins:
                if e[0] == saved_hwnd:
                    return saved_hwnd
        # 2) 창 제목 (지정 시 번호 붙여놓은 경우)
        title = aw.get("title", "")
        if title:
            for e in wins:
                if win32gui.GetWindowText(e[0]) == title:
                    return e[0]
        # 3) 저장된 x,y 기준 가장 가까운 창
        sx, sy = aw.get("x"), aw.get("y")
        if sx is not None and sy is not None:
            best = min(wins, key=lambda e: (e[1]-sx)**2+(e[2]-sy)**2)
            return best[0]
        return None

    def _reg_name_area(self):
        """창 최대화 후 이름 영역 두 점 드래그로 등록"""
        self.status.set("3초 후 캐릭터 이름 영역의 좌상단을 클릭하세요!")
        self.after(3000, lambda: [self.withdraw(), self.after(200, self._open_name_area_overlay)])

    def _open_name_area_overlay(self):
        _NameAreaOverlay(self)

    def _ocr_all_names(self):
        area = self.cfg.get("name_ocr_area")
        if not area:
            self.status.set("먼저 📷 이름 영역등록 버튼으로 영역을 등록해주세요."); return
        self._send_to_back()
        threading.Thread(target=self._do_ocr_all_names, daemon=True).start()

    def _do_ocr_all_names(self):
        try:
            import easyocr
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: self.status.set(f"easyocr 오류: {e}")); return

        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: self.status.set("리니지M 창을 찾을 수 없습니다.")); return

        area = self.cfg.get("name_ocr_area")
        ox, oy, aw, ah = area["ox"], area["oy"], area["w"], area["h"]
        slots = self.cfg.get("hunt_slots", [])
        updated = 0

        # 열린 창 각각을 OCR 스캔 후 가장 가까운 슬롯에 이름 업데이트
        for hwnd, wx, wy in wins:
            self.after(0, lambda h=hwnd: self.status.set(f"OCR 인식 중..."))
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.6)
                import ctypes
                pt = ctypes.wintypes.POINT(0, 0)
                ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                x, y = pt.x + ox, pt.y + oy
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x, y, x+aw, y+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                name = " ".join(results).strip()
                self.after(0, lambda n=name: self.status.set(f"OCR 결과: '{n}'"))
                time.sleep(1.0)
                if not name: continue

                # 가장 가까운 슬롯 찾기 (assigned_window 위치 기준, 없으면 순서대로)
                best_si = None
                best_dist = float('inf')
                for si, slot in enumerate(slots):
                    aw_data = slot.get("assigned_window")
                    if aw_data:
                        sx, sy = aw_data.get("x", 0), aw_data.get("y", 0)
                        dist = (wx-sx)**2 + (wy-sy)**2
                        if dist < best_dist:
                            best_dist = dist
                            best_si = si
                    elif best_si is None:
                        best_si = si

                if best_si is not None:
                    self.cfg["hunt_slots"][best_si]["name"] = name
                    if best_si < len(self._hunt_name_vars):
                        self.after(0, lambda n=name, i=best_si: self._hunt_name_vars[i].set(n))
                    updated += 1
            except Exception as e:
                self.after(0, lambda e=e: self.status.set(f"OCR 오류: {e}"))

        save_cfg(self.cfg)
        self.after(0, lambda: [self.deiconify(), self.status.set(f"✔ {updated}개 슬롯 이름 자동 업데이트 완료")])

    def _renumber_windows(self):
        """지정된 슬롯의 창 제목을 번호로 다시 붙이기"""
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        count = 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw: continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            new_title = f"리니지M #{i+1:02d}"
            try:
                win32gui.SetWindowText(hwnd, new_title)
                aw["title"] = new_title
                aw["hwnd"] = hwnd
                count += 1
            except: pass
        save_cfg(self.cfg)
        self.status.set(f"✔ {count}개 창 번호 재지정 완료")

    def _save_window_pos(self, slot_idx):
        """현재 지정된 창의 위치를 저장 (크기는 491×276 고정)"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1} 슬롯 없음"); return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1} — 먼저 '지정' 버튼으로 창을 지정해주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        hwnd = self._find_hwnd_for_slot(aw, wins)
        if not hwnd:
            self.status.set(f"#{slot_idx+1} — 창을 찾을 수 없습니다. '지정' 버튼을 다시 눌러주세요."); return
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]
            w, h = self._FIXED_W, self._FIXED_H
            aw["x"], aw["y"], aw["w"], aw["h"] = x, y, w, h
            aw["cx"], aw["cy"] = x + w // 2, y + h // 2
            save_cfg(self.cfg)
            self.status.set(f"✔ #{slot_idx+1:02d} 위치 저장: {w}×{h} @{x},{y}")
        except Exception as e:
            self.status.set(f"#{slot_idx+1} 저장 오류: {e}")

    def _save_all_window_pos(self):
        """지정된 모든 슬롯의 현재 창 위치를 저장 (크기 491×276 고정)"""
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        count = 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw: continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            try:
                rect = win32gui.GetWindowRect(hwnd)
                x, y = rect[0], rect[1]
                w, h = self._FIXED_W, self._FIXED_H
                aw["x"], aw["y"], aw["w"], aw["h"] = x, y, w, h
                aw["cx"], aw["cy"] = x + w // 2, y + h // 2
                count += 1
            except: pass
        save_cfg(self.cfg)
        self.status.set(f"✔ {count}개 창 위치 저장 완료 (491×276 고정)")

    def _restore_all_windows(self):
        self._restore_by_position()

    def _apply_window_pos(self, hwnd, aw):
        """창을 지정 위치/크기로 이동. (성공여부, 실패사유) 반환.
        SetWindowPos는 예외가 아니라 0(실패)을 돌려주고, 최대화/최소화된 창은
        위치가 바뀌지 않으므로 먼저 일반 상태로 되돌린 뒤 적용하고 결과를 검증한다."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        SWP_NOZORDER, SW_RESTORE = 0x0004, 9
        if u.IsIconic(hwnd) or u.IsZoomed(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.25)
        if not u.SetWindowPos(hwnd, 0, aw["x"], aw["y"], aw["w"], aw["h"], SWP_NOZORDER):
            return False, f"SetWindowPos 실패(오류 {ctypes.windll.kernel32.GetLastError()})"
        r = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        if abs(r.left - aw["x"]) > 4 or abs(r.top - aw["y"]) > 4:
            return False, f"이동 안 됨(현재 @{r.left},{r.top})"
        return True, ""

    def _restore_by_position(self):
        slots = self.cfg.get("hunt_slots", [])
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        count, failed = 0, 0
        for i, slot in enumerate(slots):
            aw = slot.get("assigned_window")
            if not aw or not all(k in aw for k in ("x","y","w","h")): continue
            hwnd = self._find_hwnd_for_slot(aw, wins)
            if not hwnd: continue
            try:
                ok, _reason = self._apply_window_pos(hwnd, aw)
            except Exception:
                ok = False
            count  += 1 if ok else 0
            failed += 0 if ok else 1
        if failed:
            self.status.set(f"창 위치 복원: 성공 {count}개 / 실패 {failed}개")
        else:
            self.status.set(f"✔ {count}개 창 위치 복원 완료")

    def _restore_by_ocr(self):
        """OCR로 각 창의 캐릭터명을 읽어 슬롯 이름과 매칭 후 복원"""
        try:
            import easyocr
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: [self.deiconify(), self.status.set(f"easyocr 오류: {e}")]); return

        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: [self.deiconify(), self.status.set("리니지M 창을 찾을 수 없습니다.")]); return

        area = self.cfg.get("name_ocr_area")
        ox, oy, aw, ah = area["ox"], area["oy"], area["w"], area["h"]
        slots = self.cfg.get("hunt_slots", [])
        SWP_NOZORDER = 0x0004
        count = 0

        for hwnd, wx, wy in wins:
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.6)
                pt = ctypes.wintypes.POINT(0, 0)
                ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                x, y = pt.x + ox, pt.y + oy
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(x, y, x+aw, y+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                ocr_name = " ".join(results).strip()
                self.after(0, lambda n=ocr_name: self.status.set(f"OCR: '{n}' 매칭 중..."))

                # 슬롯 이름과 매칭
                matched_si = None
                for si, slot in enumerate(slots):
                    slot_name = slot.get("name", "").strip()
                    if slot_name and slot_name != "미등록" and slot_name in ocr_name:
                        matched_si = si
                        break

                if matched_si is not None:
                    aw_data = slots[matched_si].get("assigned_window")
                    if aw_data and all(k in aw_data for k in ("x","y","w","h")):
                        ctypes.windll.user32.SetWindowPos(hwnd, 0,
                            aw_data["x"], aw_data["y"], aw_data["w"], aw_data["h"], SWP_NOZORDER)
                        self.after(0, lambda n=ocr_name, s=matched_si: self.status.set(f"✔ '{n}' → #{s+1:02d} 복원"))
                        count += 1
                        time.sleep(0.3)
            except Exception as e:
                self.after(0, lambda e=e: self.status.set(f"오류: {e}"))

        save_cfg(self.cfg)
        self.after(0, lambda: [self.deiconify(), self.status.set(f"✔ {count}개 창 이름 매칭 복원 완료")])

    def _restore_single_by_ocr(self, slot_idx):
        """고정 영역 OCR → 현재 앞에 있는 창을 해당 슬롯 위치로 복원"""
        area = self.cfg.get("name_ocr_area")
        if not area:
            self.status.set("먼저 📷 이름 영역등록을 해주세요."); return
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1:02d} 슬롯 없음"); return
        aw_data = slots[slot_idx].get("assigned_window")
        if not aw_data or not all(k in aw_data for k in ("x","y","w","h")):
            self.status.set(f"#{slot_idx+1:02d} 저장된 위치가 없습니다. 📍 저장 먼저 해주세요."); return
        # 버튼 클릭 전 포그라운드 창 미리 기억
        prev_hwnd = win32gui.GetForegroundWindow()
        threading.Thread(target=self._do_ocr_snap, args=(slot_idx, area, aw_data, prev_hwnd), daemon=True).start()

    def _do_ocr_snap(self, slot_idx, area, aw_data, prev_hwnd):
        try:
            import easyocr
            from PIL import ImageGrab
            reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        except Exception as e:
            self.after(0, lambda: self.status.set(f"easyocr 오류: {e}")); return

        slots = self.cfg.get("hunt_slots", [])
        slot_name = slots[slot_idx].get("name", "").strip()
        wins = self._get_purple_hwnds()
        if not wins:
            self.after(0, lambda: self.status.set("리니지M 창을 찾을 수 없습니다.")); return

        ax, ay, aw, ah = area["x"], area["y"], area["w"], area["h"]
        SWP_NOZORDER = 0x0004

        for hwnd, wx, wy in wins:
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                img = ImageGrab.grab(bbox=(ax, ay, ax+aw, ay+ah), all_screens=True)
                results = reader.readtext(img, detail=0)
                ocr_name = " ".join(results).strip()
                self.after(0, lambda n=ocr_name: self.status.set(f"OCR: '{n}' 확인 중..."))
                if slot_name and (slot_name in ocr_name or ocr_name in slot_name):
                    ctypes.windll.user32.SetWindowPos(hwnd, 0,
                        aw_data["x"], aw_data["y"], aw_data["w"], aw_data["h"], SWP_NOZORDER)
                    self.after(0, lambda: self.status.set(f"✔ '{slot_name}' → #{slot_idx+1:02d} 복원 완료"))
                    return
            except: pass

        self.after(0, lambda: self.status.set(f"'{slot_name}' 이름의 창을 찾지 못했습니다."))

    def _restore_single_window(self, slot_idx):
        """지정된 창을 저장된 위치/크기로 복구"""
        slots = self.cfg.get("hunt_slots", [])
        if slot_idx >= len(slots):
            self.status.set(f"#{slot_idx+1} 슬롯 없음"); return
        aw = slots[slot_idx].get("assigned_window")
        if not aw:
            self.status.set(f"#{slot_idx+1} — 먼저 '지정' 버튼으로 창을 지정해주세요."); return
        wins = self._get_purple_hwnds()
        if not wins:
            self.status.set("리니지M 창을 찾을 수 없습니다."); return
        hwnd = self._find_hwnd_for_slot(aw, wins)
        if not hwnd:
            self.status.set(f"#{slot_idx+1} — 창을 찾을 수 없습니다. '지정' 버튼을 다시 눌러주세요."); return
        try:
            ok, reason = self._apply_window_pos(hwnd, aw)
            if ok:
                self.status.set(f"✔ #{slot_idx+1:02d} 창 복구 완료  ({aw['w']}x{aw['h']}  @{aw['x']},{aw['y']})")
            else:
                self.status.set(f"⚠ #{slot_idx+1:02d} 창 복구 실패 — {reason}")
        except Exception as e:
            self.status.set(f"#{slot_idx+1} 복구 오류: {e}")
        # 개별 재배치 후 메인런처가 뒤로 밀리지 않도록 항상 앞으로 유지
        self._keep_launcher_front()

    def _keep_launcher_front(self):
        """메인런처를 잠깐 topmost로 올려 앞으로 유지 (고정은 하지 않음)."""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    # ── 동시 실행 방지 (전역 잠금) ──────────────────────────────────
    def _set_btn(self, name, **kw):
        """서브창이 닫히면(3분 자동닫힘 포함) 버튼 위젯이 파괴된다.
        파괴된 위젯에 config()하면 TclError가 나서 작업 시작이 통째로 취소되고,
        직전에 잡은 _busy_task 잠금도 안 풀리므로 반드시 생존 확인 후 설정한다."""
        b = getattr(self, name, None)
        try:
            if b is not None and b.winfo_exists():
                b.config(**kw)
        except Exception:
            pass

    def _is_busy(self, exclude=None):
        """개별 작업 / 다야 OCR / 섬·던전 실행기가 돌고 있으면 True. exclude 이름은 무시."""
        bt = getattr(self, "_busy_task", None)
        if bt and bt != exclude:
            return True
        if exclude != "다야OCR":
            proc = getattr(self, "_ocr_proc", None)
            if proc is not None and proc.poll() is None:
                return True
        ip = getattr(self, "_island_proc", None)
        if ip is not None and ip.poll() is None:
            return True
        if self._island_lock_alive():
            return True
        return False

    @staticmethod
    def _island_lock_alive():
        """섬/던전 실행기가 남기는 잠금 파일이 3초 안에 갱신됐으면 아직 돌고 있다."""
        try:
            p = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI",
                             "island_running.lock")
            with open(p, encoding="utf-8") as f:
                _pid, ts = f.read().split()
            return (time.time() - float(ts)) < 3.0
        except Exception:
            return False

    def _busy_label(self):
        bt = getattr(self, "_busy_task", None)
        if bt:
            return bt
        proc = getattr(self, "_ocr_proc", None)
        if proc is not None and proc.poll() is None:
            return "다야OCR"
        return "다른 작업"

    def _try_busy(self, name):
        """작업 시작 시도 — 다른 작업이 실행 중이면 안내 후 False."""
        if self._is_busy(exclude=name):
            self.status.set(f"⚠ '{self._busy_label()}' 실행 중 — '{name}'은(는) 실행 안 함 (동시 실행 방지)")
            return False
        self._busy_task = name
        return True

    # ── 작업 대기열: 실행 중에 누른 실행/재측정은 쌓아뒀다가 순차 실행 ──
    def _start_past_scheduled(self):
        """과거섬 스케줄 시작 — 대기열(최우선)에서 불려도 안전하게 잠금·중복 처리."""
        import datetime
        today = datetime.date.today()
        if self._past_triggered_date == today:
            return
        if self._is_busy():
            self._enqueue_front("과거섬(스케줄)", self._start_past_scheduled)
            return
        self._past_triggered_date = today
        self._past_ran_save(today)          # 재시작해도 오늘 또 돌지 않게 기록
        self._busy_task = "과거섬(스케줄)"
        threading.Thread(target=self._run_task,
            args=("과거섬(스케줄)", self._run_past_scheduled), daemon=True).start()

    def _enqueue_front(self, label, fn):
        """최우선 작업 — 대기열 맨 앞에 넣는다 (이미 있으면 맨 앞으로 이동)."""
        self._task_queue = [(l, f) for l, f in self._task_queue if l != label]
        self._task_queue.insert(0, (label, fn))

    def _enqueue(self, label, fn):
        """대기열 폐지(2026-08-07) — 다른 작업 중이면 쌓아두지 않고 안내만 한다.
        끝난 뒤 사용자가 직접 다시 누르는 방식."""
        self.after(0, lambda: self.status.set(
            f"⚠ '{self._busy_label()}' 실행 중 — '{label}'은(는) 실행 안 함 (끝난 뒤 다시 눌러주세요)"))

    def _queue_tick(self):
        """1.5초마다 확인 — 스케줄(과거섬 등 자동 예약)만 한가해질 때 이어서 실행한다.
        사용자가 누른 실행은 대기열에 쌓지 않으므로 여기서 처리할 것이 없다.
        (겸사겸사 [■ 전체멈춤]·[⏰ 반복] 버튼 색도 여기서 갱신한다)"""
        try:
            self._refresh_stop_btn()
            self._refresh_rep_btn()
        except Exception:
            pass
        try:
            if self._task_queue and not self._is_busy():
                label, fn = self._task_queue.pop(0)
                self.status.set(f"▶ 예약 작업 실행: {label}")
                fn()
        except Exception:
            pass
        self.after(1500, self._queue_tick)

    def _try_busy_or_queue(self, name, retry_fn, label=None):
        """busy면 안내만 하고 False (대기열 폐지 — 끝난 뒤 직접 다시 누르기)."""
        if self._is_busy(exclude=name):
            self._enqueue(label or name, retry_fn)
            return False
        self._busy_task = name
        return True

    def _clear_busy(self, name):
        if getattr(self, "_busy_task", None) == name:
            self._busy_task = None

    def _start_pause(self):
        """(2026-08-09) 실행 버튼을 눌러도 곧바로 클릭하지 않고 1~2초 뜸을 들인다.
        바로 눌리면 어색하고, 창이 아직 정리되기 전에 클릭이 들어갈 수도 있어서.
        + 스케줄·반복으로 저절로 시작될 때 클로드나 런처가 앞에 떠 있으면 클릭을
          가리므로, 무엇이 됐든 먼저 내리고(최소화·맨뒤로) 나서 시작한다."""
        try:
            self.after(0, self._minimize_all)   # 런처·서브창·클로드 전부 내림
        except Exception:
            pass
        now = time.time()
        if now - getattr(self, "_last_start_pause", 0) < 5:
            return                      # 단독실행→본체처럼 겹쳐 불릴 땐 한 번만 쉰다
        self._last_start_pause = now
        _d = random.uniform(1.0, 2.0)
        _t0 = now
        while time.time() - _t0 < _d:
            if getattr(self, "_stop_flag", False):
                return
            time.sleep(0.05)

    def _run_task(self, name, fn, *args):
        """작업 스레드 래퍼 — 끝나면 잠금 해제."""
        try:
            fn(*args)
        finally:
            self._clear_busy(name)

    def _stop(self):
        self._stop_flag      = True
        self._past_stop      = True
        self._sched_stop     = True
        self._hunt_stop      = True
        self._click_stop     = True
        self._mail_stop      = True
        self._sched_any_stop = True
        self._return_stop    = True
        self._doll_stop      = True
        self._dungeon_stop   = True
        self._pass_stop      = True
        self._item_stop      = True
        self._dollchk_stop   = True
        self._relic_stop     = True
        self._coupon_stop    = True
        self._market_stop    = True
        self._dragon_stop    = True
        self._knight_stop    = True
        self._eventshop_stop = True
        self._fish_stop      = True
        self._circus_stop    = True
        self._circus2_stop   = True
        self._circus3_stop   = True
        self._tj_stop        = True
        self._reroll_running = False  # 오림의일기장도 정지
        self._busy_task      = None   # 잠금 해제
        self._task_queue.clear()      # 멈춤 시 대기열도 비움
        # 별도 프로세스(섬/던전 실행기·다야 OCR·던전) 전부 강제 종료 — 재개 없이 완전히 끔
        # (추적 안 된 단독 창(잊혀진섬 등)까지 명령줄 기준으로 모두 종료)
        try:
            import subprocess as _sp
            _sp.Popen(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'lineagem_island|lineagem_ocr|lineagem_dungeon' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                creationflags=0x08000000)
        except Exception:
            pass
        self._ocr_proc = None
        self._island_proc = None
        # (2026-08-15 사용자 지시) ⏰ 2시간 N회 반복은 여기서 끄지 않는다 —
        # [■ 전체멈춤]은 '지금 돌고 있는 것'만, 반복을 끄려면 [⏰] 버튼을 쓴다.
        _n = self._rep_count()
        self._night_queue = []          # 눌러둔 대기열은 함께 비운다
        try:
            self._refresh_night_queue()
        except Exception:
            pass
        self.status.set("전체 종료 중..."
                        + (f" (⏰ 반복 {_n}개는 그대로 — 끄려면 ⏰ 버튼)" if _n else ""))

    # ── 클릭 실행 ─────────────────────────────────────────────────────
    def _start_click(self):
        slots = [s for s in self.cfg.get("click_slots", []) if s[0] and s[1]]
        if not slots:
            messagebox.showwarning("등록 필요", "클릭 좌표를 먼저 등록해주세요."); return
        if not self._try_busy_or_queue("클릭실행", self._start_click): return
        self._click_stop = False
        self.btn_click_run.config(state="disabled")
        self.btn_click_stop.config(state="normal")
        self._minimize_all()
        threading.Thread(target=self._run_task, args=("클릭실행", self._run_click_standalone), daemon=True).start()

    def _run_click_standalone(self):
        self._run_click()
        self.btn_click_run.config(state="normal")
        self.btn_click_stop.config(state="disabled")
        self._click_stop = False
        self.deiconify()

    def _run_click(self):
        self._start_pause()
        try:
            active = [(i, s) for i, s in enumerate(self.cfg.get("click_slots", []))
                      if s[0] and s[1]]
            for done, (i, pair) in enumerate(active):
                if self._click_stop: self.status.set("클릭 멈춤"); return
                if not self._wait_mouse_idle("_click_stop"):
                    self.status.set("클릭 멈춤"); return
                grp = (i // GROUP_SIZE) + 1
                self.status.set(f"그룹{grp} #{i+1}번 클릭1...")
                pyautogui.click(*pair[0])
                # 좌표1 → 좌표2 사이 0.8~1.1초 (너무 빠르면 클릭 씹힘) — 16슬롯 모두
                if not self._click_wait(random.uniform(0.8, 1.1)): self.status.set("클릭 멈춤"); return
                if not self._wait_mouse_idle("_click_stop"):
                    self.status.set("클릭 멈춤"); return
                self.status.set(f"그룹{grp} #{i+1}번 클릭2...")
                pyautogui.click(*pair[1])
                if done < len(active) - 1:
                    if not self._click_wait(random.uniform(0.1, 0.5)): self.status.set("클릭 멈춤"); return
            self.status.set(f"✔ 클릭 완료! (총 {len(active)*2}번)")
        except Exception as e:
            self.status.set(f"오류: {e}")

    # ── 사냥 실행 ─────────────────────────────────────────────────────
    def _start_hunt(self):
        active = [h for h in self.cfg.get("hunt_slots", [])
                  if h.get("enabled", True) and any(c for c in h.get("coords", []))]
        if not active:
            messagebox.showwarning("등록 필요", "실행할(ON) 사냥 좌표가 없습니다."); return
        if not self._try_busy_or_queue("사냥", self._start_hunt): return
        self._hunt_stop = False
        self._set_btn("btn_hunt_run", state="disabled")
        self._set_btn("btn_hunt_stop", state="normal")
        self._minimize_all()
        threading.Thread(target=self._run_task, args=("사냥", self._run_hunt_standalone), daemon=True).start()

    def _run_hunt_standalone(self):
        self._run_hunt()
        self._set_btn("btn_hunt_run", state="normal")
        self._set_btn("btn_hunt_stop", state="disabled")
        self._hunt_stop = False
        self.deiconify()

    def _run_hunt(self, limit=None):
        self._start_pause()
        try:
            all_slots = list(enumerate(self.cfg.get("hunt_slots", [])))
            if limit is not None:
                all_slots = all_slots[:limit]
            active = [(i, h) for i, h in all_slots
                      if h.get("enabled", True) and any(c for c in h.get("coords", []))]
            _hunt_t0 = time.time()   # 사냥 전체 소요시간 측정 (3분=180초 목표)
            for slot_done, (i, h) in enumerate(active):
                if self._hunt_stop: self.status.set("사냥 멈춤"); return
                # 슬롯 전 대기 — 전체 3분(180초) 안에 들도록 축소: 2~12 → 1~4
                slot_delay = random.uniform(1.0, 4.0)
                name = h.get("name", f"#{i+1}")
                self.status.set(f"[{name}] {slot_delay:.0f}초 후 실행...")
                if not self._hunt_wait(slot_delay): self.status.set("사냥 멈춤"); return
                for j, coord in enumerate(h["coords"]):
                    if not coord: continue
                    if self._hunt_stop: self.status.set("사냥 멈춤"); return
                    if not self._wait_mouse_idle("_hunt_stop"):
                        self.status.set("사냥 멈춤"); return
                    self.status.set(f"[{name}] 클릭 {j+1}/{HUNT_CLICKS}...")
                    pyautogui.moveTo(*coord)
                    time.sleep(random.uniform(0.1, 0.3))
                    pyautogui.mouseDown(*coord)
                    time.sleep(random.uniform(0.1, 0.25))
                    pyautogui.mouseUp(*coord)
                    time.sleep(random.uniform(0.05, 0.15))
                    if j < HUNT_CLICKS - 1:
                        # 슬롯 안 좌표간 클릭 간격 (랜덤)
                        interval = random.uniform(0.15, 0.5)
                        if not self._hunt_wait(interval):
                            self.status.set("사냥 멈춤"); return
                # 다음 슬롯 대기
                if slot_done < len(active) - 1:
                    slot_interval = random.uniform(0.6, 1.6)
                    if random.random() < 0.2:  # 20% 확률로 짧은 추가 휴식
                        slot_interval += random.uniform(0.5, 1.2)
                    if not self._hunt_wait(slot_interval):
                        self.status.set("사냥 멈춤"); return
            # 사냥 전체 소요시간 기록 (180초 목표 확인)
            _he = time.time() - _hunt_t0
            _hmark = "✔180초이내" if _he <= 180 else "⚠180초초과!"
            _hmsg = f"✔ 사냥 완료! ({len(active)}개)  [소요 {_he:.1f}초 {_hmark}]"
            try:
                with open(os.path.join(LOGS_DIR, "run_timing.txt"), "a", encoding="utf-8") as _f:
                    import datetime as _dt
                    _f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  [사냥] {_he:.1f}초 ({_hmark})\n")
            except Exception:
                pass
            self.status.set(_hmsg)
        except Exception as e:
            import traceback
            self.status.set(f"사냥 오류: {type(e).__name__}: {e}")
            print(traceback.format_exc())

    # ── 전체 자동 실행 ────────────────────────────────────────────────
    def _start(self):
        optional = {"confirm_btn", "profile_reveal_btn"}
        missing = [LABELS[k] for k in LABELS if k not in optional and not self.cfg.get(k)]
        if not self.cfg.get("char_btns"):
            missing.append("캐릭터 접속 버튼 (1개 이상)")
        if missing:
            messagebox.showwarning("등록 필요", "먼저 등록해주세요:\n" +
                                   "\n".join(f"• {m}" for m in missing)); return
        if not self._try_busy_or_queue("전체자동실행", self._start):   # 실행 중이면 대기열로
            return
        self._stop_flag = False
        self._running   = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._minimize_all()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self._start_pause()
        total = self.acc_count.get()
        self.after(0, self._minimize_all)
        try:
            import traceback as _tb
            _dbg = open(os.path.join(LOGS_DIR, "run_debug.txt"), "w", encoding="utf-8")
            _dbg.write("_run started\n"); _dbg.flush()
            win = find_purple()
            if win is None:
                self.status.set("퍼플 실행 중...")
                subprocess.Popen(PURPLE_EXE)
                for _ in range(30):
                    if self._stop_flag: self.status.set("멈춤"); return
                    time.sleep(1)
                    win = find_purple()
                    if win: break
            if win is None:
                self.status.set("오류: 퍼플 창 없음"); return

            try:
                import win32gui, win32con, ctypes
                hwnd = win32gui.FindWindow(None, win.title)
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.5)
                    # 작업 표시줄 제외한 실제 작업 영역으로 크기 설정
                    rc = ctypes.wintypes.RECT()
                    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP,
                                         rc.left, rc.top,
                                         rc.right - rc.left, rc.bottom - rc.top,
                                         win32con.SWP_SHOWWINDOW)
                    time.sleep(0.5)
                win32gui.SetForegroundWindow(hwnd)
            except: pass
            if not self._wait(2): self.status.set("멈춤"); return

            # 팝업 감지 및 자동 닫기 (3초 대기 후)
            self.status.set("퍼플 팝업 확인 중...")
            time.sleep(3)
            close_purple_popup_if_visible(
                self.cfg,
                lambda msg: self.after(0, lambda m=msg: self.status.set(m)))
            if not self._wait(1): self.status.set("멈춤"); return

            # ── 현재 퍼플 아이디 그대로 접속 ────────────────────────────────
            try: win.activate()
            except: pass
            if not self._wait(1): self.status.set("멈춤"); return

            for acc_idx in range(total):
                if self._stop_flag: self.status.set("멈춤"); return
                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 리니지M 클릭...")
                pyautogui.click(*self.cfg["lineagem"])
                if not self._wait(3): self.status.set("멈춤"); return

                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return
                self.status.set(f"[{acc_idx+1}/{total}] 게임 실행 클릭...")
                pyautogui.click(*self.cfg["game_start"])
                if not self._wait(5): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 멀티플레이 클릭...")
                pyautogui.click(*self.cfg["multiplay"])
                if not self._wait(6): self.status.set("멈춤"); return

                # 캐릭터 버튼 클릭 전 퍼플을 항상 위로 고정
                try:
                    import win32gui, win32con
                    _hwnd = win32gui.FindWindow(None, win.title)
                    if _hwnd:
                        win32gui.SetWindowPos(_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                        win32gui.SetForegroundWindow(_hwnd)
                except: pass

                for i, (cx, cy) in enumerate(self.cfg.get("char_btns", [])):
                    if self._stop_flag: self.status.set("멈춤"); return
                    if acc_idx == 0 and i == 0:
                        self._run_char01_t = time.time()   # 캐릭터01 접속 시각 (4분30초 제한 측정)
                    self.status.set(f"[{acc_idx+1}/{total}] 캐릭터 #{i+1} 클릭...")
                    pyautogui.click(cx, cy)
                    if not self._wait(3): self.status.set("멈춤"); return

                # 캐릭터 버튼 완료 후 항상 위 해제
                try:
                    if _hwnd:
                        win32gui.SetWindowPos(_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                except: pass

                try: _dbg.write(f"[LOOP] acc_idx={acc_idx} total={total} 마지막여부={acc_idx == total - 1}\n"); _dbg.flush()
                except Exception: pass
                if acc_idx == total - 1:
                    # ── 마지막 캐릭터 접속 후 순서 ──
                    # ① 지정계정로 전환(프로필→구글계정→확인) ② 리니지M 좌측버튼으로 지정계정 확인
                    # ③ 지정계정이면 퍼플 최소화
                    if not self._wait(3): self.status.set("멈춤"); return

                    # ⓪ 먼저 현재 아이디 확인 — 이미 지정계정이면 전환 생략!
                    #    (계정 목록엔 '현재 계정 제외 나머지'만 떠서, 이미 지정계정일 때
                    #     고정 좌표를 클릭하면 다른 계정으로 이탈해버리는 사고 방지)
                    _pre_matched = False
                    try:
                        try: win.activate()
                        except Exception: pass
                        if not self._wait(1): self.status.set("멈춤"); return
                        if self.cfg.get("profile_reveal_btn"):
                            pyautogui.click(*self.cfg["profile_reveal_btn"])
                            if not self._wait(3): self.status.set("멈춤"); return
                        _pre_matched, _pre_id, _pre_r = self._is_target_account()
                        try: _dbg.write(f"[SWITCH] 사전확인: '{_pre_id}' 일치율 {int(_pre_r*100)}% matched={_pre_matched}\n"); _dbg.flush()
                        except Exception: pass
                    except Exception:
                        pass
                    if _pre_matched:
                        self.status.set("✔ 이미 지정계정 — 전환 생략, 퍼플 최소화")
                        try: _dbg.write("[SWITCH] 이미 지정계정 → 전환 생략\n"); _dbg.flush()
                        except Exception: pass
                        try:
                            import win32gui, win32con
                            _p_hwnd = win32gui.FindWindow(None, "PURPLE")
                            if _p_hwnd:
                                win32gui.ShowWindow(_p_hwnd, win32con.SW_MINIMIZE)
                            else:
                                win.minimize()
                        except Exception:
                            try: win.minimize()
                            except Exception: pass
                        break

                    # ①② (2026-08-09) 지정 계정으로 전환 → 아이디 확인 → 다르면 재전환
                    #     4시 퍼플 자동전환을 폐지했기 때문에, 전체 자동 실행 마지막에
                    #     "처음 로그인해 두었던 아이디(지정계정)"로 확실히 되돌려 놓는다.
                    #     예전엔 전환을 1번만 하고 실패해도 그냥 넘어갔다 → 최대 2번까지 재시도.
                    _matched3, _oid3, _r3 = False, "", 0.0
                    for _try in range(1, 3):
                        self.status.set(f"지정 계정으로 전환 중... ({_try}/2)")
                        try: _dbg.write(f"[SWITCH] 전환 {_try}/2 시작" + chr(10)); _dbg.flush()
                        except Exception: pass
                        if self.cfg.get("profile_btn"):
                            pyautogui.click(*self.cfg["profile_btn"])
                            if not self._wait(2): self.status.set("멈춤"); return
                        if self.cfg.get("google_acc"):
                            pyautogui.click(*self.cfg["google_acc"])
                            if not self._wait(2): self.status.set("멈춤"); return
                        if self.cfg.get("confirm_btn"):
                            pyautogui.click(*self.cfg["confirm_btn"])
                            self.status.set("계정 전환 로딩 대기 중... (약 10초)")
                            if not self._wait(10): self.status.set("멈춤"); return

                        # 게임 창 활성화 → 리니지M 좌측버튼으로 아이디 표시 → 지정계정 확인
                        self.status.set("지정계정 확인 중...")
                        try: win.activate()
                        except Exception: pass
                        if not self._wait(1): self.status.set("멈춤"); return
                        if self.cfg.get("profile_reveal_btn"):
                            pyautogui.click(*self.cfg["profile_reveal_btn"])
                            if not self._wait(3): self.status.set("멈춤"); return
                        _matched3, _oid3, _r3 = self._is_target_account()
                        self.status.set(f"아이디 '{_oid3}' (일치율 {int(_r3*100)}%)")
                        try: _dbg.write(f"[SWITCH] {_try}/2 아이디 확인: '{_oid3}' "
                                        f"일치율 {int(_r3*100)}% matched={_matched3}" + chr(10)); _dbg.flush()
                        except Exception: pass
                        if _matched3:
                            break
                        if self._stop_flag: self.status.set("멈춤"); return


                    # ③ 퍼플 최소화 — 확인 성공/실패와 무관하게 항상 최소화
                    #    (다음 좌표 클릭이 퍼플 위에서 눌리지 않도록 반드시 최소화)
                    if _matched3:
                        self.status.set("✔ 지정계정 확인 → 퍼플 최소화")
                    else:
                        self.status.set(f"⚠ 지정계정 확인 실패('{_oid3}') — 그래도 최소화 진행")
                    try:
                        import win32gui, win32con
                        # 계정 전환하면 퍼플 창이 새로 생겨 win 객체가 오래됨(죽은 창) →
                        # "PURPLE" 제목으로 현재 창을 다시 찾아서 최소화
                        _p_hwnd = win32gui.FindWindow(None, "PURPLE")
                        if not _p_hwnd:
                            try: _p_hwnd = win32gui.FindWindow(None, win.title)
                            except Exception: _p_hwnd = 0
                        if _p_hwnd:
                            win32gui.ShowWindow(_p_hwnd, win32con.SW_MINIMIZE)
                        else:
                            win.minimize()
                    except Exception:
                        try: win.minimize()
                        except Exception: pass
                    try: _dbg.write("[SWITCH] 퍼플 최소화 완료 → 그룹 클릭으로\n"); _dbg.flush()
                    except Exception: pass
                    break

                self.status.set(f"[{acc_idx+1}/{total}] 로딩 대기... (15초)")
                if not self._wait(15): self.status.set("멈춤"); return
                try: win.activate()
                except: pass
                if not self._wait(1): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 프로필 클릭...")
                pyautogui.click(*self.cfg["profile_btn"])
                if not self._wait(2): self.status.set("멈춤"); return

                self.status.set(f"[{acc_idx+1}/{total}] 구글 계정 클릭...")
                pyautogui.click(*self.cfg["google_acc"])
                if not self._wait(2): self.status.set("멈춤"); return

                if self.cfg.get("confirm_btn"):
                    self.status.set(f"[{acc_idx+1}/{total}] 확인 클릭...")
                    pyautogui.click(*self.cfg["confirm_btn"])

                self.status.set(f"[{acc_idx+1}/{total}] 새 계정 로딩... (15초)")
                if not self._wait(15): self.status.set("멈춤"); return

                for _ in range(10):
                    win = find_purple();
                    if win: break
                    time.sleep(1)
                if win is None:
                    self.status.set("오류: 퍼플 창 없음"); return
                try: win.activate()
                except: pass
                if not self._wait(2): self.status.set("멈춤"); return

            if self._stop_flag: self.status.set("멈춤"); return

            # 접속 완료 → 20초 대기 → 클릭 등록(그룹1,2) 실행
            self.status.set("✔ 모든 계정 접속 완료! 20초 후 클릭 등록 실행...")
            if not self._wait(20): self.status.set("멈춤"); return

            active = [(i, s) for i, s in enumerate(self.cfg.get("click_slots", []))
                      if s[0] and s[1]]
            for done, (i, pair) in enumerate(active):
                if self._stop_flag: self.status.set("멈춤"); return
                grp = (i // GROUP_SIZE) + 1
                self.status.set(f"그룹{grp} #{i+1}번 클릭1...")
                pyautogui.click(*pair[0])
                # 두번째 클릭이 좀 빨라서 0.5~0.7초 랜덤 추가로 늦춤
                if not self._wait(random.uniform(0.6, 1.2) + random.uniform(0.5, 0.7)):
                    self.status.set("멈춤"); return
                self.status.set(f"그룹{grp} #{i+1}번 클릭2...")
                pyautogui.click(*pair[1])
                if i == 4 and len(pair) > 2 and pair[2]:
                    if not self._wait(random.uniform(0.6, 1.2)): self.status.set("멈춤"); return
                    self.status.set(f"그룹{grp} #{i+1}번 클릭3...")
                    pyautogui.click(*pair[2])
                if done < len(active) - 1:
                    if not self._wait(2.5): self.status.set("멈춤"); return
            # 캐릭터01 접속 → 그룹2 완료까지 실제 소요시간 측정 (4분30초=270초 제한 확인)
            _t0 = getattr(self, "_run_char01_t", None)
            if _t0:
                _elapsed = time.time() - _t0
                _mark = "✔270초이내" if _elapsed <= 270 else "⚠270초초과!"
                _msg = f"[타이밍] 캐릭터01→그룹2 완료: {_elapsed:.1f}초 ({_mark})"
                try:
                    with open(os.path.join(LOGS_DIR, "run_timing.txt"), "a", encoding="utf-8") as _f:
                        import datetime as _dt
                        _f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {_msg}\n")
                except Exception:
                    pass
                self.status.set(_msg)
                time.sleep(1)
            # 그룹→사냥 전환 시간 35%로 축소 (5초 → 1.75초)
            self.status.set(f"✔ 클릭 등록 완료! 1.75초 후 사냥 실행 시작...")
            if not self._wait(1.75): self.status.set("멈춤"); return

            if not self._stop_flag:
                self._hunt_stop = False
                self._run_hunt()
            self.status.set("✔ 전체 실행 완료!")

        except Exception as e:
            import traceback as _tb2
            _err = f"오류: {type(e).__name__}: {e}"
            self.status.set(_err)
            try:
                with open(os.path.join(LOGS_DIR, "run_debug.txt"), "a", encoding="utf-8") as _f:
                    _f.write(_err + "\n" + _tb2.format_exc())
            except Exception:
                pass
        finally:
            self._running = False
            self._clear_busy("전체자동실행")
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="normal")   # 항상 누를 수 있게 — 색으로만 상태 표시
            self._stop_flag = False
            self.after(0, self._restore_back)


# ── 좌표 오버레이 ─────────────────────────────────────────────────────────
class _PresetDotOverlay(tk.Toplevel):
    """프리셋 번호 미리보기 — 반투명 화면에 점 하나 표시, 아무 키/클릭으로 닫기."""

    def __init__(self, app, num, pos, note=""):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(str(sw) + "x" + str(sh) + "+0+0")
        self.attributes("-alpha", 0.35)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        cv = tk.Canvas(self, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(sw // 2, 40,
                       text="클릭 " + str(num) + "번 위치  (" + note + ")  —  아무 곳이나 클릭하면 닫힘",
                       fill="white", font=("맑은 고딕", 13))
        x, y = int(pos[0]), int(pos[1])
        for r, col in ((26, "#f1c40f"), (16, "#e67e22"), (6, "#e74c3c")):
            cv.create_oval(x - r, y - r, x + r, y + r, outline=col, width=2)
        cv.create_line(x - 40, y, x + 40, y, fill="#f1c40f")
        cv.create_line(x, y - 40, x, y + 40, fill="#f1c40f")
        cv.create_text(x, y - 34, text=str(num), fill="white", font=("맑은 고딕", 11, "bold"))
        for w in (self, cv):
            w.bind("<Button-1>", lambda e: self.destroy())
            w.bind("<Escape>", lambda e: self.destroy())
        self.after(6000, lambda: self.winfo_exists() and self.destroy())


class _HuntGroupMoveOverlay(tk.Toplevel):
    """사냥 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 4

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="red", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36:
            return
        self._drag  = True
        self._moved = False
        self._last  = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag:
            return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3:
                return
            self._moved = True
        dx = e.x - self._last[0]
        dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots:
            d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag  = False
            self._moved = False
        else:
            # 빈 곳 클릭 → 저장 후 닫기
            coords = self.app.cfg["hunt_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["hunt_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg)
            self.app._refresh_ui()
            self.app.status.set(f"✔ 사냥 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _DungeonGroupMoveOverlay(tk.Toplevel):
    """던전 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 4

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#e67e22", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["dungeon_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["dungeon_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg)
            self.app._refresh_ui()
            self.app.status.set(f"✔ 던전 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _PastChainMoveOverlay(tk.Toplevel):
    """과거섬 #01→#04 순차 그룹 이동: 저장하면 자동으로 다음 슬롯으로 이어짐"""
    R = 4

    def __init__(self, app, slot_idx, dots, next_idx, end):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self.next_idx = next_idx; self.end = end
        self._dots = [[x, y, num] for x, y, num in dots]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close_all())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        remain = self.end - self.slot_idx
        cv.create_text(self._sw//2, 18,
            text=f"#{self.slot_idx+1:02d} 위치 조정 ({remain}개 남음)  |  드래그: 이동  |  빈 곳 클릭: 저장→다음  |  ESC: 전체취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#c0392b", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            # 저장
            coords = self.app.cfg["past_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["past_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.destroy()
            # 다음 슬롯으로
            if self.next_idx < self.end:
                self.app._past_chain_move(self.next_idx, self.end)
            else:
                self.app.deiconify()
                self.app.status.set("✔ #01~#04 그룹 이동 저장 완료")

    def _close_all(self):
        self.destroy(); self.app.deiconify()
        self.app.status.set("취소됨")


class _PastGroupMoveOverlay(tk.Toplevel):
    """과거섬 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장
    dots: [(x, y, num, coord_idx), ...]  — coord_idx 가 실제 coords 배열 인덱스
    """
    R = 4

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        # dots 는 (x, y, num, coord_idx) 또는 (x, y, num) 둘 다 허용
        self._dots = [[d[0], d[1], d[2], d[3] if len(d)>3 else i]
                      for i, d in enumerate(dots)]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for d in self._dots:
            x, y, num = d[0], d[1], d[2]
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#c0392b", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["past_slots"][self.slot_idx].get("coords", [])
            for x, y, _, ci in self._dots:
                if ci < len(coords):
                    coords[ci] = [x, y]
            self.app.cfg["past_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 과거섬 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _SchedGroupMoveOverlay(tk.Toplevel):
    """스케줄 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장
    dots: [(x, y, num, coord_idx), ...]
    """
    R = 4

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self._dots = [[d[0], d[1], d[2], d[3] if len(d)>3 else i]
                      for i, d in enumerate(dots)]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for d in self._dots:
            x, y, num = d[0], d[1], d[2]
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#16a085", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["sched_slots"][self.slot_idx].get("coords", [])
            for x, y, _, ci in self._dots:
                if ci < len(coords):
                    coords[ci] = [x, y]
            self.app.cfg["sched_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 스케줄 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _SlotGroupMoveOverlay(tk.Toplevel):
    """클릭 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 8

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app = app; self.slot_idx = slot_idx
        self._dots = [[x, y, num] for x, y, num in dots]
        self._drag = False; self._moved = False; self._last = (0, 0)
        self.overrideredirect(True); self.attributes("-topmost", True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")
        from PIL import ImageGrab as _IG, ImageTk as _ITk
        self._bg_img = _ITk.PhotoImage(_IG.grab(all_screens=False).resize((sw, sh)))
        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()
        self._cv.bind("<ButtonPress-1>", self._on_press)
        self._cv.bind("<B1-Motion>", self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv; cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#2980b9", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white", font=("맑은 고딕", 8, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            pair = [None, None]
            for x, y, num in self._dots:
                step = 0 if str(num) == "1" else 1
                pair[step] = [x, y]
            self.app.cfg["click_slots"][self.slot_idx] = pair
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _MailGroupMoveOverlay(tk.Toplevel):
    """우편함 슬롯 좌표 전체를 그룹으로 드래그해 이동 후 저장"""
    R = 4

    def __init__(self, app, slot_idx, dots):
        super().__init__()
        self.app      = app
        self.slot_idx = slot_idx
        self._dots    = [[x, y, num] for x, y, num in dots]
        self._drag    = False
        self._moved   = False
        self._last    = (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="fleur")
        self._cv.pack(fill="both", expand=True)
        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.lift(); self.focus_force()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="드래그로 전체 이동  |  빈 곳 클릭: 저장 후 닫기  |  ESC: 취소",
            fill="#aaa", font=("맑은 고딕", 10))
        r = self.R
        for x, y, num in self._dots:
            cv.create_oval(x-r, y-r, x+r, y+r, fill="#8e44ad", outline="white", width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 5, "bold"))

    def _on_press(self, e):
        if e.y < 36: return
        self._drag = True; self._moved = False; self._last = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag: return
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3: return
            self._moved = True
        dx = e.x - self._last[0]; dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        for d in self._dots: d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        if self._moved:
            self._drag = False; self._moved = False
        else:
            coords = self.app.cfg["mail_slots"][self.slot_idx].get("coords", [])
            for i, (x, y, _) in enumerate(self._dots):
                if i < len(coords) and coords[i]:
                    coords[i] = [x, y]
            self.app.cfg["mail_slots"][self.slot_idx]["coords"] = coords
            save_cfg(self.app.cfg); self.app._refresh_ui()
            self.app.status.set(f"✔ 우편함 #{self.slot_idx+1:02d} 그룹 이동 저장 완료")
            self._close()

    def _close(self):
        self.destroy(); self.app.deiconify()


class _DotPreviewOverlay(tk.Toplevel):
    """스크린샷 배경 + 드래그 가능한 빨간 점 미리보기.
    dots: [(x, y, num), ...]
    save_fn(dot_idx, new_x, new_y): 점 이동 시 호출
    rereg_fn: ✏ 재등록 버튼 콜백
    """
    R = 3

    def __init__(self, app, title, dots, rereg_fn, save_fn=None, dot_r=3):
        super().__init__()
        self.R        = dot_r
        self.app      = app
        self.rereg_fn = rereg_fn
        self.save_fn  = save_fn
        self._dots    = [[x, y, num] for x, y, num in dots]  # mutable
        self._drag      = None   # dragging dot index
        self._grp_drag  = False  # dragging empty space (group move)
        self._moved     = False
        self._last      = (0, 0)
        self._sel       = None   # 키보드(WASD/방향키) 미세이동 대상 — 드래그한 점 유지, None=전체

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._sw, self._sh = sw, sh
        self.geometry(f"{sw}x{sh}+0+0")

        from PIL import ImageGrab as _IG, ImageTk as _ITk
        shot = _IG.grab(all_screens=False).resize((sw, sh))
        self._bg_img = _ITk.PhotoImage(shot)

        self._cv = tk.Canvas(self, highlightthickness=0, cursor="hand2")
        self._cv.pack(fill="both", expand=True)
        self._bx = sw - 100

        self._draw()

        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_drag)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._close())
        self.bind("<Key>", self._on_key)   # WASD/방향키 1px 미세이동
        self.lift(); self.focus_force()

    def _on_key(self, e):
        """WASD·방향키 미세이동 — 드래그했던 점이 있으면 그 점만, 없으면 전체 1px 이동."""
        ks = (e.keysym or "").lower()
        ch = e.char or ""
        if   ks in ("w", "up")    or ch == "ㅈ": dx, dy = 0, -1
        elif ks in ("s", "down")  or ch == "ㄴ": dx, dy = 0, 1
        elif ks in ("a", "left")  or ch == "ㅁ": dx, dy = -1, 0
        elif ks in ("d", "right") or ch == "ㅇ": dx, dy = 1, 0
        else:
            return
        if self._sel is not None and self._sel < len(self._dots):
            d = self._dots[self._sel]
            d[0] += dx; d[1] += dy
            if self.save_fn: self.save_fn(self._sel, d[0], d[1])
        else:
            for i, d in enumerate(self._dots):
                d[0] += dx; d[1] += dy
                if self.save_fn: self.save_fn(i, d[0], d[1])
        self._draw()

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self._bg_img)
        # 상단 안내바
        cv.create_rectangle(0, 0, self._sw, 36, fill="#1a252f", outline="")
        cv.create_text(self._sw//2, 18,
            text="점 드래그: 개별 이동  |  빈 곳 드래그: 전체 이동  |  WASD·방향키: 1px 미세이동(드래그한 점, 없으면 전체)  |  빈 곳 클릭: 닫기",
            fill="#aaa", font=("맑은 고딕", 10))
        bx = self._bx
        cv.create_rectangle(bx, 6, bx+90, 30, fill="#e67e22", outline="")
        cv.create_text(bx+45, 18, text="✏ 재등록", fill="white",
                       font=("맑은 고딕", 9, "bold"))
        # 점들 (키보드 이동 대상으로 선택된 점은 노란 테두리)
        r = self.R
        for i, (x, y, num) in enumerate(self._dots):
            outline = "yellow" if i == self._sel else "white"
            cv.create_oval(x-r, y-r, x+r, y+r, fill="red", outline=outline, width=2)
            cv.create_text(x, y, text=str(num), fill="white",
                           font=("맑은 고딕", 5, "bold"))

    def _hit(self, ex, ey):
        r = self.R + 6
        for i, (x, y, _) in enumerate(self._dots):
            if abs(ex - x) < r and abs(ey - y) < r:
                return i
        return None

    def _on_press(self, e):
        if e.y < 36: return
        hit = self._hit(e.x, e.y)
        if hit is not None:
            self._drag      = hit     # 개별 점 드래그
            self._grp_drag  = False
            self._sel       = hit     # 누르는 순간 선택 → 잡고 있는 중에도 WASD 미세조정 가능
        else:
            self._drag      = None
            self._grp_drag  = True   # 빈 공간 → 그룹 드래그
            self._sel       = None   # 전체 모드 → WASD도 전체 이동
        self._moved = False
        self._last  = (e.x, e.y)
        self._draw()

    def _on_drag(self, e):
        # 3px 미만 미세 끌림 무시 — 클릭할 때 좌표가 1~2px 밀려 저장되는 사고 방지
        if not self._moved:
            if abs(e.x - self._last[0]) <= 3 and abs(e.y - self._last[1]) <= 3:
                return
            self._moved = True
        dx = e.x - self._last[0]
        dy = e.y - self._last[1]
        self._last = (e.x, e.y)
        if self._drag is not None:
            self._dots[self._drag][0] += dx
            self._dots[self._drag][1] += dy
        elif self._grp_drag:
            for d in self._dots:
                d[0] += dx; d[1] += dy
        self._draw()

    def _on_release(self, e):
        # 재등록 버튼 클릭
        if self._bx <= e.x <= self._bx + 90 and 6 <= e.y <= 30:
            self._close(); self.rereg_fn(None); return
        if self._moved:
            # 드래그 후 저장
            if self._drag is not None:
                x, y, num = self._dots[self._drag]
                if self.save_fn: self.save_fn(self._drag, x, y)
                self._sel = self._drag   # 드래그한 점을 키보드 미세이동 대상으로 유지
            elif self._grp_drag:
                if self.save_fn:
                    for i, (x, y, _) in enumerate(self._dots):
                        self.save_fn(i, x, y)
                self._sel = None         # 그룹 이동 후엔 키보드도 전체 이동
            self._drag = None; self._grp_drag = False; self._moved = False
            self._draw()
        elif self._drag is not None and not self._moved:
            # 점 클릭 → 개별 재등록
            dot_idx = self._drag
            self._drag = None
            self._close(); self.rereg_fn(dot_idx)
        else:
            # 빈 곳 단순 클릭 → 닫기
            self._close()

    def _close(self):
        self.destroy()
        self.app.deiconify()


class _DotPreviewOverlayNav(_DotPreviewOverlay):
    """그룹 이동(이전/다음) 버튼이 추가된 미리보기 오버레이."""
    def __init__(self, app, title, dots, rereg_fn, save_fn, prev_fn, next_fn, dot_r=3):
        self._prev_fn = prev_fn
        self._next_fn = next_fn
        super().__init__(app, title, dots, rereg_fn, save_fn, dot_r)

    def _close(self):
        self.destroy()
        self.app.deiconify()
        if self.app._pass_win and self.app._pass_win.winfo_exists():
            self.app._pass_win.deiconify()

    PW = 42; PH = 18; PY = 9

    def _draw(self):
        super()._draw()
        cv = self._cv
        pw, ph, py = self.PW, self.PH, self.PY
        px = 10
        cv.create_rectangle(px, py, px+pw, py+ph, fill="#2c3e50", outline="")
        cv.create_text(px+pw//2, py+ph//2, text="◀ 이전", fill="white", font=("맑은 고딕", 7, "bold"))
        nx = px + pw + 4
        cv.create_rectangle(nx, py, nx+pw, py+ph, fill="#2c3e50", outline="")
        cv.create_text(nx+pw//2, py+ph//2, text="다음 ▶", fill="white", font=("맑은 고딕", 7, "bold"))

    def _on_release(self, e):
        pw, ph, py = self.PW, self.PH, self.PY
        px = 10; nx = px + pw + 4
        if py <= e.y <= py+ph:
            if px <= e.x <= px+pw:
                self._close(); self.app.after(300, self._prev_fn); return
            if nx <= e.x <= nx+pw:
                self._close(); self.app.after(300, self._next_fn); return
        super()._on_release(e)


class _ZoomCaptureOverlay(tk.Toplevel):
    """드래그한 영역을 캡처해 확대 표시 (가려/쪼개진 아이디를 사람이 읽기 쉽게)"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.3)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text="확대해서 볼 영역(아이디)을 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 16, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.06, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root, outline="cyan", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start; x1, y1 = e.x_root, e.y_root
        self.destroy()
        # 오버레이가 완전히 사라진 뒤 캡처 (오버레이가 스샷에 안 찍히게)
        self.app.after(180, lambda: self.app._vf_show_zoom((x0, y0, x1, y1)))

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()


class _ProfileAreaOverlay(tk.Toplevel):
    """퍼플 아이디 표시 영역 드래그 등록"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text="퍼플 아이디가 표시되는 영역을 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 16, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root, outline="cyan", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start
        x1, y1 = e.x_root, e.y_root
        self.destroy()
        self.app.cfg["profile_id_area"] = {
            "x": min(x0,x1), "y": min(y0,y1),
            "w": abs(x1-x0), "h": abs(y1-y0)
        }
        # 등록 당시 퍼플 창 위치도 저장 → 다른 컴퓨터/다른 창위치에서 자동 보정
        try:
            w = find_purple()
            if w:
                self.app.cfg["profile_id_area_win"] = [w.left, w.top]
        except Exception:
            pass
        save_cfg(self.app.cfg)
        self.app.deiconify()
        self.app._profile_area_var.set("등록됨")
        self.app.status.set("✔ 아이디 영역 등록 완료 (창 위치 보정 지원)")

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()


class _ProfileRefOverlay(tk.Toplevel):
    """계정 대조 기준이미지 캡처 영역 드래그 등록 — 놓는 즉시 캡처해 기준으로 저장"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text="계정 대조 기준으로 쓸 영역을 드래그하세요\n"
                            "(계정마다 확실히 다른 부분 — 아이디 글자·프로필 사진 등)\nESC = 취소",
                 font=("맑은 고딕", 16, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root, outline="lime", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start
        x1, y1 = e.x_root, e.y_root
        self.destroy()
        if abs(x1-x0) < 8 or abs(y1-y0) < 8:
            self.app.deiconify()
            self.app.status.set("영역이 너무 작습니다 — 다시 드래그해주세요")
            return
        region = {"x": min(x0,x1), "y": min(y0,y1),
                  "w": abs(x1-x0), "h": abs(y1-y0)}
        # 등록 당시 퍼플 창 위치 저장 → 창이 옮겨져도 자동 보정
        try:
            w = find_purple()
            if w:
                region["win"] = [w.left, w.top]
        except Exception:
            pass
        self.app._finish_ref_capture(region)

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()


class _NameAreaOverlay(tk.Toplevel):
    """캐릭터 이름 OCR 영역을 드래그로 등록하는 오버레이"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        self._start = None
        self._rect = None
        tk.Label(self, text="캐릭터 이름 영역을 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 18, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root,
                                                    outline="yellow", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start
        x1, y1 = e.x_root, e.y_root
        self.destroy()
        ax, ay = min(x0,x1), min(y0,y1)
        self.app.cfg["name_ocr_area"] = {
            "x": ax, "y": ay,
            "w": abs(x1-x0), "h": abs(y1-y0)
        }
        save_cfg(self.app.cfg)
        self.app.deiconify()
        self.app.status.set(f"✔ 이름 영역 등록 완료 ({ax},{ay} / {abs(x1-x0)}×{abs(y1-y0)})")

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()
        self.app.status.set("이름 영역 등록 취소")


class _AssignWindowOverlay(tk.Toplevel):
    """클릭한 창을 사냥 슬롯에 지정하는 전체화면 오버레이"""
    def __init__(self, app, slot_idx, on_done=None):
        super().__init__()
        self.app = app
        self.slot_idx = slot_idx
        self.on_done = on_done
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(bg="black")
        tk.Label(self, text=f"#{slot_idx+1:02d} 창 지정\n지정할 리니지M 창을 클릭하세요\nESC = 취소",
                 font=("맑은 고딕", 22, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self.bind("<Button-1>", self._on_click)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_click(self, e):
        x, y = e.x_root, e.y_root
        self.destroy()
        try:
            self.app.update()
            time.sleep(0.1)
            # win32gui로 안정적으로 창 감지
            hwnd = win32gui.WindowFromPoint((x, y))
            root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT) if hwnd else hwnd
            if not root: root = hwnd
            r = win32gui.GetWindowRect(root)
            title = win32gui.GetWindowText(root) or f"hwnd:{root}"
            cx, cy = (r[0]+r[2])//2, (r[1]+r[3])//2
            slot_num = f"#{self.slot_idx+1:02d}"
            new_title = f"리니지M {slot_num}"
            try:
                win32gui.SetWindowText(root, new_title)
            except: pass
            aw = {"hwnd": root, "cx": cx, "cy": cy,
                  "x": r[0], "y": r[1],
                  "w": r[2]-r[0], "h": r[3]-r[1],
                  "title": new_title,
                  "slot_num": slot_num}
            self.app.cfg["hunt_slots"][self.slot_idx]["assigned_window"] = aw
            save_cfg(self.app.cfg)
            if self.on_done:
                self.app.after(0, lambda t=title: self.on_done(self.slot_idx, t))
        except Exception as ex:
            self.app.after(0, lambda: self.app.status.set(f"지정 오류: {type(ex).__name__}: {ex}"))
        finally:
            self.app.deiconify()

    def _cancel(self, e=None):
        self.destroy()
        self.app.deiconify()
        self.app.status.set(f"#{self.slot_idx+1:02d} 창 지정 취소")


class CoordOverlay(tk.Toplevel):
    def __init__(self, app, mode="single"):
        super().__init__()
        self.app  = app
        self.mode = mode
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # ⚠ 캡처가 끝날 때까지 이 창을 절대 보이면 안 된다.
        #    전체화면 창이 먼저 뜬 상태로 ImageGrab 하면 '아직 안 그려진 자기 자신(검은 화면)'이
        #    배경으로 찍혀서 화면 전체가 새까맣게 되고, 그대로 갇힌다.
        self.withdraw()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        # 좌표 등록 시 클로드(항상 위) 창이 타깃을 가리지 않도록 캡처 전에 최소화
        try:
            app._minimize_claude()
        except Exception:
            pass
        time.sleep(0.15)   # 최소화가 화면에 반영될 시간

        from PIL import Image as _Img, ImageTk as _ITk, ImageGrab as _IG
        shot = _IG.grab(all_screens=True).resize((sw, sh))
        self._bg = _ITk.PhotoImage(shot)

        c = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=self._bg)
        c.create_rectangle(0, 0, sw, 54, fill="#1a252f", outline="")

        if mode == "char":
            n = len(app.cfg.get("char_btns", [])) + 1
            label = f"캐릭터 접속 버튼 #{n}"
        elif mode == "char_rereg":
            idx = app._char_rereg_idx
            label = f"캐릭터 #{idx+1} 새 위치"
        elif mode == "slot":
            label = f"#{app._slot_target+1}번 슬롯 클릭{app._slot_step+1}"
        elif mode == "hunt":
            idx  = app._hunt_reg_idx
            step = app._hunt_reg_step
            name = app.cfg["hunt_slots"][idx].get("name", f"#{idx+1}")
            label = f"[{name}] 클릭{step+1} 위치"
        elif mode == "mail":
            label = f"우편함 #{app._reg_mail_slot_idx+1} 클릭{app._reg_mail_click_idx+1} 위치"
        elif mode == "dungeon":
            lbl = ["클릭1", "클릭2", "클릭3", "클릭4", "클릭5"][app._reg_dungeon_click_idx]
            label = f"던전 #{app._reg_dungeon_slot_idx+1} [{lbl}] 위치"
        elif mode == "past":
            label = f"과거의말하는섬 #{app._reg_past_slot_idx+1} [클릭] 위치"
        elif mode == "pass":
            label = f"패스권 #{app._reg_pass_slot_idx+1} [{PASS_LABELS[app._reg_pass_click_idx]}] 위치"
        elif mode == "sched":
            label = f"매일매일 스케줄 #{app._reg_sched_slot_idx+1} [클릭] 위치"
        elif mode == "dgn2":
            _f, _s, _c = app._reg_dgn2
            _t = app._dgn2_info(_f)[1]
            label = f"{_t} #{_s+1} [클릭{_c+1}] 위치"
        elif mode == "item":
            _ci = app._reg_item_click_idx
            _w  = "쓸어올리기 시작점" if _ci == 2 else f"클릭{_ci+1}"
            label = f"아이템정리 #{app._reg_item_slot_idx+1} [{_w}] 위치"
        elif mode == "slp":
            label = f"절전모드 #{app._slp_reg_idx+1} 위치"
        elif mode == "seq":
            label = f"연속클릭 #{app._seq_reg_idx+1} 위치"
        elif mode == "tj":
            label = f"TJ성공!! #{app._reg_tj_slot_idx+1} [좌표{app._reg_tj_click_idx+1}] 위치"
        elif mode == "dc":
            label = f"일반던전충전 #{app._dc_reg_idx+1} 위치"
        elif mode == "dollpreset":
            label = f"인형탐험 프리셋 — 클릭 {getattr(app, '_doll_pick', {}).get('jx', 0)+1} 번 위치"
        elif mode == "doll":
            label = f"인형탐험 #{app._doll_reg_idx+1} 좌표{app._doll_reg_step+1} 위치"
        elif mode == "wdoff":
            label = f"주말던전끄기 #{app._wdoff_reg_idx+1} 위치"
        else:
            label = LABELS.get(app._reg_target, "버튼")

        c.create_text(sw//2, 27, text=f"{label}  —  클릭하세요  (ESC: 취소)",
                      fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._click)
        self.bind("<Escape>", lambda e: [self.destroy(), app.deiconify()])

        # 배경(스크린샷)이 준비된 뒤에야 보여준다 → 검은 화면이 찍히는 일이 없다.
        self.deiconify()
        self.lift()
        # 포커스를 강제로 가져와야 ESC 취소가 먹는다. (없으면 전체화면에 갇힘)
        self.focus_force()

    def _click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        if   self.mode == "char":      self.app.on_char_coord(x, y)
        elif self.mode == "char_rereg":self.app.on_char_rereg_coord(x, y)
        elif self.mode == "slot":      self.app.on_slot_coord(x, y)
        elif self.mode == "hunt":      self.app.on_hunt_coord(x, y)
        elif self.mode == "mail":      self.app.on_mail_coord(x, y)
        elif self.mode == "dungeon":   self.app.on_dungeon_coord(x, y)
        elif self.mode == "past":      self.app.on_past_coord(x, y)
        elif self.mode == "pass":      self.app.on_pass_coord(x, y)
        elif self.mode == "sched":     self.app.on_sched_coord(x, y)
        elif self.mode == "dgn2":      self.app.on_dgn2_coord(x, y)
        elif self.mode == "item":      self.app.on_item_coord(x, y)
        elif self.mode == "tj":        self.app.on_tj_coord(x, y)
        elif self.mode == "seq":       self.app.on_seq_coord(x, y)
        elif self.mode == "slp":       self.app.on_slp_coord(x, y)
        elif self.mode == "dc":        self.app.on_dc_coord(x, y)
        elif self.mode == "doll":      self.app.on_doll_coord(x, y)
        elif self.mode == "dollpreset": self.app.on_dollpreset_coord(x, y)
        elif self.mode == "wdoff":     self.app.on_wdoff_coord(x, y)
        else:                          self.app.on_coord(x, y)


class _RerollPointOverlay(tk.Toplevel):
    """아이템 리롤용 단일 좌표 클릭 등록 (스크린샷 배경)."""
    def __init__(self, app, label, on_pick):
        super().__init__()
        self.app = app; self.on_pick = on_pick
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True); self.attributes("-topmost", True)
        from PIL import ImageTk as _ITk, ImageGrab as _IG
        self._bg = _ITk.PhotoImage(_IG.grab(all_screens=True).resize((sw, sh)))
        c = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=self._bg)
        c.create_rectangle(0, 0, sw, 54, fill="#1a252f", outline="")
        c.create_text(sw//2, 27, text=f"{label}  —  클릭하세요  (ESC: 취소)",
                      fill="white", font=("맑은 고딕", 14))
        c.bind("<ButtonPress-1>", self._click)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _click(self, e):
        x, y = e.x, e.y
        self.destroy(); self.update_idletasks()
        self.on_pick(x, y)

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()
        if self.app._reroll_win and self.app._reroll_win.winfo_exists():
            self.app._reroll_win.deiconify()
        self.app.status.set("좌표 등록 취소")


class _PotionAreaOverlay(tk.Toplevel):
    """물약색 확인용 영역 드래그 등록 (01번 클라 기준)."""
    def __init__(self, app, on_pick):
        super().__init__()
        self.app = app; self.on_pick = on_pick
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0"); self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text="01번 클라의 '물약 색이 보이는 자리'를 드래그하세요\nESC = 취소",
                 font=("맑은 고딕", 18, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root,
                                                    outline="yellow", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start; x1, y1 = e.x_root, e.y_root
        self.destroy()
        self.app.after(150, lambda: self.on_pick(min(x0, x1), min(y0, y1),
                                                 abs(x1 - x0), abs(y1 - y0)))

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()
        w = getattr(self.app, "_potion_win", None)
        if w and w.winfo_exists():
            try: w.deiconify()
            except Exception: pass
        self.app.status.set("물약 영역 등록 취소")


class _RerollAreaOverlay(tk.Toplevel):
    """아이템 리롤용 캡처 영역 드래그 등록."""
    def __init__(self, app, on_pick, label="아이템 이미지 영역을 드래그하세요"):
        super().__init__()
        self.app = app; self.on_pick = on_pick
        self.overrideredirect(True); self.attributes("-topmost", True)
        self.attributes("-alpha", 0.35)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0"); self.configure(bg="black")
        self._start = None; self._rect = None
        tk.Label(self, text=f"{label}\nESC = 취소",
                 font=("맑은 고딕", 18, "bold"), fg="white", bg="black",
                 justify="center").place(relx=0.5, rely=0.5, anchor="center")
        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, e):
        self._start = (e.x_root, e.y_root)
        if self._rect: self._canvas.delete(self._rect)

    def _on_drag(self, e):
        if not self._start: return
        if self._rect: self._canvas.delete(self._rect)
        x0, y0 = self._start
        self._rect = self._canvas.create_rectangle(x0, y0, e.x_root, e.y_root,
                                                    outline="yellow", width=2)

    def _on_release(self, e):
        if not self._start: return
        x0, y0 = self._start; x1, y1 = e.x_root, e.y_root
        self.destroy()
        ax, ay = min(x0, x1), min(y0, y1)
        self.on_pick(ax, ay, abs(x1 - x0), abs(y1 - y0))

    def _cancel(self, e=None):
        self.destroy(); self.app.deiconify()
        if self.app._reroll_win and self.app._reroll_win.winfo_exists():
            self.app._reroll_win.deiconify()
        self.app.status.set("영역 등록 취소")


def _watch_and_restart():
    """파일 변경 감지 시 자동 재시작"""
    watch = [
        os.path.join(BASE, "lineagem_launcher.py"),
        os.path.join(BASE, "lineagem_island.py"),
    ]
    mtimes = {f: os.path.getmtime(f) for f in watch if os.path.exists(f)}
    while True:
        time.sleep(1.5)
        for f in watch:
            if not os.path.exists(f): continue
            try:
                mt = os.path.getmtime(f)
            except OSError:
                continue
            if mt != mtimes.get(f):
                time.sleep(0.5)  # 저장 완료 대기
                subprocess.Popen(
                    [r"C:\Users\user\AppData\Local\Python\bin\pythonw.exe",
                     os.path.join(BASE, "lineagem_launcher.py")]
                )
                os._exit(0)

if __name__ == "__main__":
    threading.Thread(target=_watch_and_restart, daemon=True).start()
    App().mainloop()
