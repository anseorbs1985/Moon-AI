# -*- coding: utf-8 -*-
"""🆕 새 컴퓨터(로컬) 첫 세팅 — 저장소에 올라간 것을 전부 받아 메인런처를 띄운다.

쓰는 법 (새 컴퓨터 PowerShell 에서 두 줄):

    git clone https://github.com/anseorbs1985/Moon-AI.git "$env:USERPROFILE\\Desktop\\Moon-AI"
    py "$env:USERPROFILE\\Desktop\\Moon-AI\\setup_local.py"

이 스크립트가 하는 일 — ①~④ 만 한다. 실제 배포는 검증된 길인
`lineagem_update.py`(🔄 업데이트) 에 그대로 맡긴다.

    ① 바탕화면·저장소 위치 확인 (OneDrive 바탕화면도 찾는다)
    ② 파이썬 패키지 확인 → 없는 것만 pip install
    ③ local_config.json 만들기 (**없을 때만** · is_main 은 넣지 않는다 = 로컬)
    ④ lineagem_update.py 실행 → 코드·그림 배포 · 좌표 복구 · 예약작업 · 런처 시작

🚫 **메인 컴퓨터에서는 실행을 거부한다** (local_config.json 에 is_main 이 있으면).
   메인은 좌표·설정의 원본이라 이 스크립트가 건드릴 일이 없다.
"""
import io
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def say(m=""):
    print(m, flush=True)


# ── ① 바탕화면·저장소 찾기 ──────────────────────────────────────────
def find_repo(here):
    """저장소 = .git 과 lineagem_launcher.py 가 같이 있는 폴더"""
    home = os.path.expanduser("~")
    cands = [
        here,
        os.path.join(here, "Moon-AI"),
        os.path.join(home, "Desktop", "Moon-AI"),
        os.path.join(home, "OneDrive", "Desktop", "Moon-AI"),
        os.path.join(home, "Moon-AI"),
    ]
    for c in cands:
        if (os.path.isdir(os.path.join(c, ".git"))
                and os.path.exists(os.path.join(c, "lineagem_launcher.py"))):
            return c
    return None


def find_desk(repo):
    """런처가 돌 폴더 = 저장소의 상위 (보통 바탕화면).
    lineagem_update.py 의 DESK 계산과 **같은 규칙**이라야 한다."""
    if os.path.basename(repo).lower() == "moon-ai":
        return os.path.dirname(repo)
    return repo


# ── ② 패키지 ────────────────────────────────────────────────────────
# (모듈 이름, pip 이름) — easyocr 은 넣지 않는다: torch 까지 수 GB 라
# 다야 OCR 을 쓸 컴퓨터만 따로 깐다 (아래 안내에 적는다).
NEED = [
    ("PIL", "pillow"),
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pyautogui", "pyautogui"),
    ("pygetwindow", "pygetwindow"),
    ("win32gui", "pywin32"),
]


def check_pkgs():
    import importlib
    miss = []
    for mod, pip in NEED:
        try:
            importlib.import_module(mod)
            say(f"   ✔ {mod:12s} ({pip})")
        except Exception:
            say(f"   ✘ {mod:12s} ({pip}) — 설치 필요")
            miss.append(pip)
    return miss


def install(pkgs):
    say(f"   pip install {' '.join(pkgs)}")
    r = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs])
    return r.returncode == 0


def main():
    say("=" * 66)
    say("🆕 Moon-AI 새 컴퓨터 첫 세팅")
    say("=" * 66)

    # ── ① 위치 ──────────────────────────────────────────────────
    repo = find_repo(HERE)
    if not repo:
        say("")
        say("✘ Moon-AI 저장소를 못 찾았습니다.")
        say("  PowerShell 에서 먼저 이것부터 돌려주세요:")
        say('    git clone https://github.com/anseorbs1985/Moon-AI.git '
            '"$env:USERPROFILE\\Desktop\\Moon-AI"')
        return 1
    desk = find_desk(repo)
    say("")
    say("① 위치")
    say(f"   저장소   {repo}")
    say(f"   런처폴더 {desk}")
    if not os.path.isdir(desk):
        say(f"   ✘ 런처폴더가 없습니다: {desk}")
        return 1

    # 🚫 메인에서는 돌리지 않는다
    lc_path = os.path.join(desk, "local_config.json")
    lc = {}
    if os.path.exists(lc_path):
        try:
            lc = json.load(io.open(lc_path, encoding="utf-8-sig"))
        except Exception as e:
            say(f"   ⚠ local_config.json 을 읽지 못했습니다: {e}")
    if lc.get("is_main"):
        say("")
        say("🚫 여기는 **메인 컴퓨터**입니다 (local_config.json 의 is_main=true).")
        say("   메인은 좌표·설정의 원본이라 이 스크립트가 건드릴 것이 없습니다.")
        say("   새 컴퓨터에서 돌려주세요.")
        return 2

    # ── ② 패키지 ────────────────────────────────────────────────
    say("")
    say(f"② 파이썬 패키지 ({sys.version.split()[0]})")
    miss = check_pkgs()
    if miss:
        say("")
        if not install(miss):
            say("   ✘ 설치가 실패했습니다 — 인터넷·파이썬을 확인하고 다시 돌려주세요")
            return 1
        say("   다시 확인합니다")
        if check_pkgs():
            say("   ✘ 아직 빠진 것이 있습니다")
            return 1

    # ── ③ local_config.json ─────────────────────────────────────
    say("")
    say("③ local_config.json (이 컴퓨터만의 설정 · GitHub 에 안 올라간다)")
    if os.path.exists(lc_path):
        say(f"   이미 있습니다 — 건드리지 않습니다 (키 {len(lc)}개)")
    else:
        # is_main 은 **넣지 않는다** — 없으면 로컬로 동작한다
        # (push 금지 · skip-worktree · 좌표 잠금이 올바르게 걸린다)
        base = {"pc_name": os.environ.get("COMPUTERNAME", "로컬")}
        try:
            with io.open(lc_path, "w", encoding="utf-8") as f:
                json.dump(base, f, ensure_ascii=False, indent=2)
            say(f"   만들었습니다 — pc_name = {base['pc_name']}")
            say("   (is_main 을 넣지 않았으므로 **로컬**로 동작합니다 = push 안 함)")
        except Exception as e:
            say(f"   ⚠ 만들지 못했습니다: {e} — 업데이트는 그대로 진행합니다")

    # ── ④ 업데이트 실행 ─────────────────────────────────────────
    up = os.path.join(repo, "lineagem_update.py")
    if not os.path.exists(up):
        say(f"\n✘ {up} 가 없습니다 — clone 이 덜 됐을 수 있습니다")
        return 1
    say("")
    say("④ 🔄 업데이트 실행 — 여기서부터는 업데이트 창이 알려줍니다")
    say("   코드·그림 배포 → 좌표 복구 → 예약작업 등록 → 메인런처 시작")
    say("")
    say("   ⚠ 끝나면 **한 번 더 🔄 업데이트** 를 눌러주세요 (첫 세팅만).")
    say("      새 재시작 코드가 업데이트 자신에 들어 있어, 이번 판은 옛 방식으로")
    say("      재시작됩니다. 다음부터는 한 번에 먹힙니다.")
    say("")
    say("=" * 66)
    try:
        subprocess.Popen([sys.executable, up], cwd=repo)
        say("업데이트 창을 띄웠습니다. 창의 기록을 끝까지 읽어주세요.")
        say("기록 파일: %LOCALAPPDATA%\\MoonAI\\update_log.txt")
    except Exception as e:
        say(f"✘ 업데이트를 띄우지 못했습니다: {e}")
        say(f"  직접 돌려주세요:  py \"{up}\"")
        return 1

    say("")
    say("── 그 다음 (사용자가 직접) ────────────────────────────────")
    say("  1. 리니지M 클라 16개를 격자로 배치한다")
    say("  2. 메인런처 [좌표등록] 에서 접속 좌표를 확인·수정한다")
    say("     (저장소 좌표를 받았지만 **클라 위치가 다르면 어긋난다**)")
    say("  3. 던전·런처별 좌표를 찍는다 — 한 슬롯만 찍고 [📋 전체붙임] 하면")
    say("     클라 창 위치로 자동보정된다")
    say("  4. 좌표를 맞춘 뒤 **[💾 좌표저장]** 을 눌러둔다 (되돌릴 수 있게)")
    say("")
    say("  선택 — 다야 OCR 을 쓸 컴퓨터만:  py -m pip install easyocr")
    say("         (torch 까지 수 GB 라 기본 설치에서 뺐습니다)")
    say("  선택 — 폰 텔레그램 알림:  local_config.json 에")
    say('         "telegram_token": "<@BotFather 에서 받은 토큰>" 추가')
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\n중단했습니다")
        sys.exit(130)
