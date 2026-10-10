# -*- coding: utf-8 -*-
"""📱 폰에서 버튼 하나로 — 텔레그램 봇 (2026-10-11 사용자 요청).

사용자: *"내가 밖에 있을 때 점검을 해버리면 방치할 수밖에 없거든. 게임을 그렇게 하면
안 되니까, 핸드폰에 어플을 만들어서 내가 버튼을 누르면 재부팅을 해주고 게임 접속에
사냥까지 보내주면 좋겠는데 가능해?"*

**폰 앱을 따로 만들지 않는다.** 앱스토어 등록·서명·업데이트가 계속 따라붙는다.
폰에 이미 있는 텔레그램에 버튼을 띄우고, 이 프로그램이 봇을 지켜본다.
서버도 포트 개방도 필요 없다.

```
폰 텔레그램  ──버튼──▶  lineagem_bot.py (이 파일)
                           │  명령을 파일에 적는다
                           ▼
              %LOCALAPPDATA%\\MoonAI\\bot_cmd.json
                           │  메인런처가 1초마다 파일 시각만 확인 (부하 0)
                           ▼
                      퍼플 재실행 → 계정 접속 → 캐릭 선택 → 사냥
                           │  결과를 적는다
                           ▼
              %LOCALAPPDATA%\\MoonAI\\bot_out.json  ──▶ 폰으로 글·사진 전송
```

명령을 **파일로 주고받는 방식**은 이 저장소가 이미 쓰는 방식이다
(`bar.json` 의 `raise`, `island_run.json` 의 `pid`). 런처는 **파일 수정시각만** 보므로
평소 부하가 없고, 무거운 일은 전부 백그라운드 스레드에서 한다
(CLAUDE.md 2026-09-16: `self.after` 틱에서 화면을 긁지 말 것).

## 🚫 실행은 버튼을 누를 때만 (2026-08-10 최우선 규칙 그대로)

이 봇은 **스스로 아무것도 시작하지 않는다.** 폰에서 버튼을 눌렀을 때만 명령을 적는다.
주기적으로 하는 일은 '텔레그램에 새 메시지가 왔나' 물어보는 것뿐이다.
⚠ 클로드는 여기에 자동 실행·자동 재시도·스케줄을 넣지 말 것.

## ⚠ 통신은 반드시 윈도 curl 로 — 파이썬 기본 통신은 막혀 있다 (2026-10-11 실측)

이 컴퓨터는 SSL 검사를 하는 보안 프로그램이 있어서 파이썬 `urllib` 은 이렇게 막힌다:

```
urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain
```

반면 `C:\\Windows\\System32\\curl.exe` 는 **윈도 인증서 저장소(Schannel)** 를 쓰므로
그 검사 프로그램의 인증서를 신뢰해서 정상 동작한다 (실측: `getMe` 성공).
`certifi`·`requests`·`truststore` 는 이 컴퓨터에 **없다**.
⚠ 클로드는 이것을 `urllib`·`requests` 로 되돌리지 말 것 — 조용히 전부 실패한다.
   `verify=False` 같은 '검증 끄기' 로 우회하지도 말 것.

## 토큰은 머신별 파일에만 — 깃허브에 올라가지 않는다

`local_config.json` 의 `telegram_token` / `telegram_chat_id` 를 읽는다.
그 파일은 `.gitignore` 1번 줄(`*.json`)에 걸려 있어 저장소에 올라가지 않는다.
⚠ 토큰을 코드에 적지 말 것. 기록에도 남기지 말 것.
"""
import io
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("LOCALAPPDATA", BASE), "MoonAI")
CFG_FILE = os.path.join(BASE, "local_config.json")
CMD_FILE = os.path.join(DATA, "bot_cmd.json")
OUT_FILE = os.path.join(DATA, "bot_out.json")
LOG_FILE = os.path.join(DATA, "bot_log.txt")
STATE_FILE = os.path.join(DATA, "bot_state.json")

# 윈도 curl — 파이썬 기본 통신이 SSL 검사에 막히므로 이것만 쓴다 (맨 위 설명 참조)
CURL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                    "System32", "curl.exe")

POLL_TIMEOUT = 25        # 텔레그램 long-poll — 새 메시지가 없으면 이만큼 기다린다
OUT_TICK = 1.0           # 런처가 적어둔 답(bot_out.json)을 확인하는 간격(초)

# 📱 폰에 뜨는 버튼. (보이는 글, 명령)
BUTTONS = [
    [("🔄 재접속 + 사냥", "reconnect")],
    [("📸 지금 화면", "shot"), ("📋 상태", "status")],
    [("■ 전체멈춤", "stop")],
]


def log(msg):
    try:
        os.makedirs(DATA, exist_ok=True)
        with io.open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def load_cfg():
    try:
        return json.load(io.open(CFG_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_cfg_key(key, val):
    """local_config.json 의 한 칸만 고쳐 쓴다 — 통째로 덮어쓰지 않는다.
    (CLAUDE.md: '쓰기 직전에 다시 읽어 필요한 키만 고쳐 쓴다')"""
    try:
        d = load_cfg()
        d[key] = val
        tmp = CFG_FILE + ".tmp"
        io.open(tmp, "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=2))
        os.replace(tmp, CFG_FILE)
    except Exception as e:
        log("local_config 저장 실패: %s" % e)


class Bot:
    def __init__(self, token):
        self.token = token
        # 이미 아는 대화 상대 — 바뀔 때만 파일에 저장한다 (매번 쓰지 않는다)
        self.chat_known = str(load_cfg().get("telegram_chat_id") or "")
        self.offset = 0
        try:
            self.offset = int(json.load(io.open(STATE_FILE, encoding="utf-8"))
                              .get("offset") or 0)
        except Exception:
            pass

    # ── 텔레그램 통신 (curl 전용) ───────────────────────────────────────────
    def api(self, method, params=None, files=None, timeout=40):
        """봇 API 한 번 호출. 실패하면 None (예외를 밖으로 내보내지 않는다)."""
        url = "https://api.telegram.org/bot%s/%s" % (self.token, method)
        cmd = [CURL, "-s", "-m", str(timeout)]
        for k, v in (params or {}).items():
            # --data-urlencode 라 한글·줄바꿈·특수문자를 그대로 보낼 수 있다
            cmd += ["--data-urlencode", "%s=%s" % (k, v)]
        for k, path in (files or {}).items():
            cmd += ["-F", "%s=@%s" % (k, path)]
        if files:
            # 파일을 보낼 때는 -F 와 --data-urlencode 를 섞을 수 없다 →
            # 일반 값도 -F 로 바꿔 보낸다
            cmd = [CURL, "-s", "-m", str(timeout)]
            for k, v in (params or {}).items():
                cmd += ["-F", "%s=%s" % (k, v)]
            for k, path in (files or {}).items():
                cmd += ["-F", "%s=@%s" % (k, path)]
        cmd.append(url)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               creationflags=getattr(subprocess,
                                                     "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                log("curl 실패(%s) %s" % (method, (r.stderr or "")[:200]))
                return None
            return json.loads(r.stdout)
        except Exception as e:
            log("api 오류(%s) %s" % (method, e))
            return None

    def keyboard(self):
        return json.dumps({"inline_keyboard": [
            [{"text": t, "callback_data": c} for t, c in row] for row in BUTTONS
        ]}, ensure_ascii=False)

    def send(self, chat_id, text, with_keys=False):
        p = {"chat_id": chat_id, "text": text}
        if with_keys:
            p["reply_markup"] = self.keyboard()
        return self.api("sendMessage", p)

    def send_photo(self, chat_id, path, caption=""):
        return self.api("sendPhoto", {"chat_id": chat_id, "caption": caption},
                        files={"photo": path}, timeout=120)

    def answer_cb(self, cb_id, text=""):
        self.api("answerCallbackQuery",
                 {"callback_query_id": cb_id, "text": text}, timeout=15)

    # ── 명령을 파일로 넘긴다 ────────────────────────────────────────────────
    @staticmethod
    def put_cmd(cmd, chat_id):
        os.makedirs(DATA, exist_ok=True)
        tmp = CMD_FILE + ".tmp"
        io.open(tmp, "w", encoding="utf-8").write(json.dumps(
            {"cmd": cmd, "chat_id": str(chat_id), "at": time.time()},
            ensure_ascii=False))
        os.replace(tmp, CMD_FILE)       # 원자적 — 런처가 반쪽 파일을 읽지 않게
        log("명령 적음: %s" % cmd)

    def save_offset(self):
        try:
            os.makedirs(DATA, exist_ok=True)
            io.open(STATE_FILE, "w", encoding="utf-8").write(
                json.dumps({"offset": self.offset}))
        except Exception:
            pass

    # ── 런처가 적어둔 답을 폰으로 보낸다 ────────────────────────────────────
    def pump_out(self):
        """런처가 `bot_out.json` 에 답을 적어두면 폰으로 보내고 파일을 지운다."""
        if not os.path.exists(OUT_FILE):
            return
        try:
            d = json.load(io.open(OUT_FILE, encoding="utf-8"))
        except Exception:
            return                       # 아직 쓰는 중일 수 있다 — 다음 번에 다시
        try:
            os.remove(OUT_FILE)
        except Exception:
            pass
        chat = d.get("chat_id") or load_cfg().get("telegram_chat_id")
        if not chat:
            return
        photo = d.get("photo")
        if photo and os.path.exists(photo):
            self.send_photo(chat, photo, d.get("text") or "")
        elif d.get("text"):
            self.send(chat, d["text"])

    # ── 한 바퀴 ─────────────────────────────────────────────────────────────
    def loop(self):
        log("봇 시작 — 버튼을 누를 때만 움직입니다")
        last_out = 0.0
        while True:
            # 런처가 적어둔 답이 있으면 먼저 보낸다
            if time.time() - last_out >= OUT_TICK:
                last_out = time.time()
                try:
                    self.pump_out()
                except Exception as e:
                    log("답 전송 오류: %s" % e)

            r = self.api("getUpdates",
                         {"offset": self.offset, "timeout": POLL_TIMEOUT,
                          "allowed_updates": json.dumps(["message",
                                                         "callback_query"])},
                         timeout=POLL_TIMEOUT + 15)
            if not r or not r.get("ok"):
                time.sleep(3)
                continue
            for u in r.get("result", []):
                self.offset = max(self.offset, int(u.get("update_id", 0)) + 1)
                try:
                    self.handle(u)
                except Exception as e:
                    log("처리 오류: %s" % e)
            self.save_offset()

    def handle(self, u):
        cb = u.get("callback_query")
        msg = u.get("message") or {}
        if cb:
            chat = str(((cb.get("message") or {}).get("chat") or {}).get("id") or "")
            data = cb.get("data") or ""
            self.remember(chat)
            self.answer_cb(cb.get("id"), "받았습니다")
            label = dict((c, t) for row in BUTTONS for t, c in row).get(data, data)
            self.send(chat, "▶ %s — 시작합니다" % label)
            self.put_cmd(data, chat)
            return
        chat = str((msg.get("chat") or {}).get("id") or "")
        if not chat:
            return
        self.remember(chat)
        text = (msg.get("text") or "").strip()
        if text in ("/start", "/menu", "시작", "메뉴", ""):
            self.send(chat,
                      "🌙 Moon-AI\n\n"
                      "버튼을 누르면 그때만 움직입니다.\n"
                      "스스로 시작하는 건 없습니다.",
                      with_keys=True)
        else:
            self.send(chat, "버튼으로 눌러주세요.", with_keys=True)

    def remember(self, chat):
        """처음 말을 건 상대를 `local_config.json` 에 적어둔다 — **바뀔 때만.**
        예전에는 `chat_known` 을 갱신하지 않아 메시지마다 파일을 다시 썼다."""
        if chat and chat != self.chat_known:
            save_cfg_key("telegram_chat_id", str(chat))
            self.chat_known = str(chat)
            log("chat_id 저장 (%s)" % chat)


def main():
    if not os.path.exists(CURL):
        log("윈도 curl 이 없습니다: %s" % CURL)
        return 2
    tok = (load_cfg().get("telegram_token") or "").strip()
    if not tok:
        log("local_config.json 의 telegram_token 이 비어 있습니다")
        return 2
    # 🪪 내 pid 를 남긴다 — 런처가 이 pid 가 살아 있는지 커널에 바로 물어본다.
    #    (`island_run.json` 과 같은 방식. `wmic` 로 프로세스를 뒤지면 1~3초씩
    #     멈춘다 — CLAUDE.md 2026-08-24 교훈. 다시 쓰지 말 것.)
    try:
        os.makedirs(DATA, exist_ok=True)
        io.open(os.path.join(DATA, "bot_run.json"), "w",
                encoding="utf-8").write(json.dumps({"pid": os.getpid()}))
    except Exception:
        pass
    try:
        Bot(tok).loop()
    finally:
        try:
            os.remove(os.path.join(DATA, "bot_run.json"))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
