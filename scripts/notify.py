"""텔레그램 채널로 오늘의 알림을 보낸다.

- 신규 AI·개발 관련 공고: 하나씩 제목·기관·마감일·링크
- 그 외 신규 공고: 건수만 요약 + 사이트 링크
- 마감 REMIND_DAYS일 전인 AI·개발 관련 공고: 리마인드
환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID 가 없으면 조용히 건너뛴다.
DRY_RUN=1 이면 보내지 않고 메시지만 출력한다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TODAY = datetime.now(timezone(timedelta(hours=9))).date()
LIMIT = 3800  # 텔레그램 메시지 최대 4096자, 여유 있게


def fmt(d):
    if not d:
        return "상시"
    x = date.fromisoformat(d)
    return f"{x.month}/{x.day}"


def line(it):
    url = f"{config.SITE_URL}/p/{it['id']}.html"
    org = f" · {escape(it['org'])}" if it["org"] else ""
    return f"• <a href=\"{escape(url)}\">{escape(it['title'])}</a>\n  {escape(it['region'])}{org} · ~{fmt(it['end'])}"


def build_messages():
    new = json.loads((DATA / "new_today.json").read_text(encoding="utf-8"))
    items = json.loads((DATA / "announcements.json").read_text(encoding="utf-8"))["items"]
    new_ai = [x for x in new if x["ai"]]
    new_etc = [x for x in new if not x["ai"]]
    remind = [x for x in items if x["ai"] and x["end"]
              and (date.fromisoformat(x["end"]) - TODAY).days == config.REMIND_DAYS]

    blocks = []
    if new_ai:
        blocks.append(f"🆕 <b>새 AI·개발 관련 지원사업 {len(new_ai)}건</b>")
        blocks += [line(x) for x in new_ai]
    if new_etc:
        blocks.append(f"\n📋 그 밖의 신규 공고 {len(new_etc)}건은 사이트에서 확인하세요\n{config.SITE_URL}/")
    if remind:
        blocks.append(f"\n⏰ <b>마감 {config.REMIND_DAYS}일 전</b>")
        blocks += [line(x) for x in remind]
    if not blocks:
        return []

    # 길이 제한에 맞춰 여러 메시지로 나누기
    msgs, cur = [], ""
    for b in blocks:
        if len(cur) + len(b) + 1 > LIMIT:
            msgs.append(cur)
            cur = ""
        cur += b + "\n"
    msgs.append(cur)
    return msgs


def send(token, chat, text):
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(f"텔레그램 전송 실패: {res}")


def main():
    msgs = build_messages()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHANNEL_ID")
    if not msgs:
        print("보낼 알림 없음")
        return
    if os.environ.get("DRY_RUN") or not (token and chat):
        print("[미전송 - 미리보기]\n" + "\n---\n".join(msgs))
        return
    for m in msgs:
        send(token, chat, m)
    print(f"텔레그램 {len(msgs)}개 메시지 전송")


if __name__ == "__main__":
    main()
