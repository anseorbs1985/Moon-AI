"""
lineagem_watchdog.py
메인런처가 꺼져 있으면 켜고 '맨 뒤'로 보낸다 (최소화하지 않음)
"""
import subprocess, sys, os, time
import win32gui, win32con

BASE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(BASE, "lineagem_launcher.py")
PYW = sys.executable.replace("python.exe", "pythonw.exe")


def find_launcher_hwnd():
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "리니지M 자동 실행" in t or "리니지M 자동실행" in t or "lineagem" in t.lower():
                result.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return result[0] if result else None


def is_launcher_running():
    # 런처가 켜져 있으면 창이 존재(최소화 상태여도 IsWindowVisible=True)
    return find_launcher_hwnd() is not None


def main():
    if is_launcher_running():
        return  # 이미 실행 중

    # 런처 실행
    subprocess.Popen([PYW, LAUNCHER])

    # 창이 뜨면 최소화하지 않고 '맨 뒤'로만 보낸다 (2026-08-11 사용자 지시)
    # — 최소화하면 작업표시줄에서 다시 꺼내야 해서 불편하다
    for _ in range(30):
        time.sleep(1)
        hwnd = find_launcher_hwnd()
        if hwnd:
            try:
                win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                      | win32con.SWP_NOACTIVATE)
            except Exception:
                pass
            break


if __name__ == "__main__":
    main()
