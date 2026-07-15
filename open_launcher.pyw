"""
open_launcher.pyw
메인런처 바로가기용 — 켜져 있으면 앞으로 복원, 꺼져 있으면 새로 켜서 보여준다.
(워치독과 별개로 수동으로 열 때 사용)

'가끔 다른 창이 뜬다' 문제 대응:
 - lineagem_launcher 는 단일 인스턴스(mutex)라 이미 켜져 있으면 새로 실행해도 그냥 종료된다.
 - 그래서 켜져 있을 땐 반드시 '기존 창'을 확실히 앞으로 끌어와야 하는데,
   SetForegroundWindow 는 포그라운드 잠금 때문에 자주 실패한다(게임 창 등 다른 창이 앞에 남음).
 - AttachThreadInput 으로 포그라운드 스레드에 붙어 제한을 우회하고, 최소화 복원까지 확실히 한다.
"""
import subprocess, sys, os, time
import win32gui, win32con, win32process, win32api
import win32con as wc

BASE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(BASE, "lineagem_launcher.py")
PYW = sys.executable
if PYW.lower().endswith("python.exe"):
    PYW = PYW[:-len("python.exe")] + "pythonw.exe"

TITLES = ("리니지M 자동 실행", "리니지M 자동실행")


def find_hwnd():
    """정확히 메인런처 창만 찾는다(게임 창 '리니지M l ...' 등은 제외)."""
    res = []

    def cb(hwnd, _):
        if not win32gui.IsWindow(hwnd):
            return True
        t = win32gui.GetWindowText(hwnd)
        for want in TITLES:
            if t == want or t.startswith(want):
                res.append(hwnd)
                break
        return True

    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


def bring_front(hwnd):
    """포그라운드 잠금을 우회해 창을 확실히 앞으로 끌어온다."""
    try:
        # 최소화돼 있으면 복원
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        fg = win32gui.GetForegroundWindow()
        cur_thread = win32api.GetCurrentThreadId()
        fg_thread = win32process.GetWindowThreadProcessId(fg)[0]
        tgt_thread = win32process.GetWindowThreadProcessId(hwnd)[0]

        # 포그라운드/대상 스레드 입력에 붙어 SetForegroundWindow 제한을 우회
        for th in {fg_thread, tgt_thread}:
            if th and th != cur_thread:
                try:
                    win32process.AttachThreadInput(cur_thread, th, True)
                except Exception:
                    pass
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetActiveWindow(hwnd)
        finally:
            for th in {fg_thread, tgt_thread}:
                if th and th != cur_thread:
                    try:
                        win32process.AttachThreadInput(cur_thread, th, False)
                    except Exception:
                        pass

        # 그래도 안 되면 잠깐 TOPMOST 토글로 강제로 올림
        if win32gui.GetForegroundWindow() != hwnd:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    except Exception:
        pass


def main():
    hwnd = find_hwnd()
    if hwnd:
        bring_front(hwnd)
        return
    # 꺼져 있으면 새로 실행 후 앞으로
    subprocess.Popen([PYW, LAUNCHER], cwd=BASE)
    for _ in range(40):
        time.sleep(0.5)
        hwnd = find_hwnd()
        if hwnd:
            # 창이 완전히 그려질 시간을 아주 짧게 준 뒤 앞으로
            time.sleep(0.3)
            bring_front(hwnd)
            break


if __name__ == "__main__":
    main()
