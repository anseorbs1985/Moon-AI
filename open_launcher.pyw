"""
open_launcher.pyw
메인런처 바로가기용 — 켜져 있으면 앞으로 복원, 꺼져 있으면 새로 켜서 보여준다.
(워치독과 별개로 수동으로 열 때 사용)
"""
import subprocess, sys, os, time
import win32gui, win32con

BASE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(BASE, "lineagem_launcher.py")
PYW = sys.executable.replace("python.exe", "pythonw.exe")


def find_hwnd():
    res = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "리니지M 자동 실행" in t or "리니지M 자동실행" in t:
                res.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


def bring_front(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def main():
    hwnd = find_hwnd()
    if hwnd:
        bring_front(hwnd)
        return
    # 꺼져 있으면 새로 실행 후 앞으로
    subprocess.Popen([PYW, LAUNCHER])
    for _ in range(30):
        time.sleep(1)
        hwnd = find_hwnd()
        if hwnd:
            bring_front(hwnd)
            break


if __name__ == "__main__":
    main()
