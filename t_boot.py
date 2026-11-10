# -*- coding: utf-8 -*-
r"""🧪 **실제로 켜지는가** — 런처·요약런처·섬실행기를 띄워 보고 바로 끈다.

🚨 `ast.parse` 는 `NameError` 를 못 잡는다 (2026-11-10 에 `tk.Button(r1, ...)` 로
   런처가 켜지자마자 죽었다). 소스 검사만으로 배포하지 말 것.
🚫 게임은 아무것도 클릭하지 않는다 — 창만 띄우고 끈다.
   (런처는 켜질 때 클릭하지 않는다 — '실행은 사용자가 시킬 때만')
"""
import io, os, sys, time, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DESK = r"C:\Users\user\Desktop"
OUT = os.path.dirname(os.path.abspath(__file__))
OK = True


def boot(name, args, wait=14.0):
    """띄워서 `wait` 초 동안 살아 있으면 통과. 죽으면 stderr 를 보여준다."""
    global OK
    ep = os.path.join(OUT, "boot_%s.err" % name)
    op = os.path.join(OUT, "boot_%s.out" % name)
    fe = io.open(ep, "w", encoding="utf-8", errors="replace")
    fo = io.open(op, "w", encoding="utf-8", errors="replace")
    pr = subprocess.Popen([sys.executable, "-X", "utf8"] + args,
                          cwd=DESK, stderr=fe, stdout=fo,
                          creationflags=0x08000000)
    t0 = time.time()
    while time.time() - t0 < wait:
        if pr.poll() is not None:
            break
        time.sleep(0.3)
    alive = pr.poll() is None
    if alive:
        pr.terminate()
        try:
            pr.wait(6)
        except Exception:
            pr.kill()
    fe.close()
    fo.close()
    el = time.time() - t0
    err = io.open(ep, encoding="utf-8", errors="replace").read().strip()
    if alive:
        print("  ✔ %-14s %.1f초 살아 있었다 → 끔" % (name, el))
    elif pr.returncode == 0 and not err and el < 4.0:
        # 🔒 **뮤텍스** — 이미 켜져 있으면 조용히(code 0) 끝난다. 죽은 것이 아니다.
        #    🚫 이것을 '통과' 로 넘기지 말 것 — 그 판은 **아무것도 시험하지 못했다.**
        OK = False
        print("  🔒 %-14s %.1f초에 조용히 끝났다 (code 0 · 오류 없음)"
              % (name, el))
        print("     → **이미 켜져 있다.** 끄고 다시 돌려야 진짜로 시험된다:")
        print("        powershell \"Get-CimInstance Win32_Process -Filter \\\"Name='pythonw.exe'\\\" |")
        print("          ? { $_.CommandLine -like '*%s*' } | %% { Stop-Process -Id $_.ProcessId -Force }\"" % name)
    else:
        OK = False
        print("  🚨 %-14s **%.1f초에 죽었다** (code=%s)" % (name, el, pr.returncode))
    if err:
        tail = [l for l in err.splitlines() if l.strip()][-14:]
        mark = "     " if alive else "     🚨 "
        for l in tail:
            print(mark + l[:150])
    return alive


print("=" * 98)
print("🧪 실제로 켜지는가 (🚫 클릭 없음)")
print("=" * 98)
boot("launcher", [os.path.join(DESK, "lineagem_launcher.py")])
boot("bar", [os.path.join(DESK, "lineagem_bar.pyw")], wait=9.0)
# 섬 실행기는 **좌표 창**으로만 띄운다 (--run 이면 실제로 돈다 🚫)
boot("island", [os.path.join(DESK, "lineagem_island.py"), "3"], wait=9.0)

print()
print("=" * 98)
print("  → %s" % ("✔ **셋 다 켜진다**" if OK else "🚨 켜지지 않는 것이 있다"))
print("=" * 98)
sys.exit(0 if OK else 1)
