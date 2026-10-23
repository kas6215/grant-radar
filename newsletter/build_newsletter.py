#!/usr/bin/env python3
"""
grant-radar 주간 뉴스레터 자동 생성기 (표준 라이브러리만 사용)

하는 일
  1. K-Startup 사업공고 API에서 모집 중인 공고를 수집
  2. 지난주 이후 새로 올라온 공고 + 7일 이내 마감 공고를 정리
  3. 웹 아카이브(issues/*.html, index.html), RSS(feed.xml), 이메일용 HTML 생성
  4. (선택) Brevo로 구독자 목록에 자동 발송

환경 변수
  KSTARTUP_SERVICE_KEY   공공데이터포털 인증키(Decoding 키)          [필수, --sample 제외]
  SITE_URL               예: https://grants.kinfocloud.co.kr           [필수]
  OUTPUT_DIR             결과물 폴더 (기본: newsletter)
  NEWSLETTER_NAME        뉴스레터 이름 (기본: 그랜트 레이더 주간 브리핑)
  BREVO_API_KEY          있으면 이메일 발송, 없으면 웹/RSS만 생성
  BREVO_LIST_ID          Brevo 구독자 목록 번호
  SENDER_EMAIL           Brevo에서 인증한 발신 주소 (예: news@kinfocloud.co.kr)
  SENDER_NAME            발신자 이름 (기본: 뉴스레터 이름)

사용법
  python newsletter/build_newsletter.py            # 실제 수집 + (키가 있으면) 발송
  python newsletter/build_newsletter.py --sample   # 샘플 데이터로 시험
  python newsletter/build_newsletter.py --no-send  # 발송 없이 생성만
"""

import argparse
import hashlib
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()

API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
PER_PAGE = 100
MAX_PAGES = 15
CLOSING_SOON_DAYS = 7
MAX_SEEN_IDS = 5000

# API 필드명이 바뀌어도 버티도록 후보를 여러 개 둠
FIELDS = {
    "id": ["pbanc_sn", "pbancSn", "id"],
    "title": ["biz_pbanc_nm", "intg_pbanc_biz_nm", "pbanc_nm", "bizPbancNm"],
    "org": ["pbanc_ntrp_nm", "sprv_inst", "biz_prch_dprt_nm", "pbancNtrpNm"],
    "start": ["pbanc_rcpt_bgng_dt", "pbancRcptBgngDt", "rcpt_bgng_dt"],
    "end": ["pbanc_rcpt_end_dt", "pbancRcptEndDt", "rcpt_end_dt"],
    "url": ["detl_pg_url", "biz_aply_url", "biz_gdnc_url", "detlPgUrl"],
    "region": ["supt_regin", "suptRegin"],
    "category": ["supt_biz_clsfc", "suptBizClsfc"],
    "target": ["aply_trgt", "aply_trgt_ctnt", "aplyTrgt"],
    "recruiting": ["rcrt_prgs_yn", "rcrtPrgsYn"],
}


class SetupError(Exception):
    pass


# ---------------------------------------------------------------- 수집

def pick(item, key):
    for name in FIELDS[key]:
        val = item.get(name)
        if val not in (None, ""):
            return str(val).strip()
    return ""


def parse_date(text):
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())[:8]
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def extract_rows(payload):
    if isinstance(payload.get("data"), list):
        return payload["data"]
    items = (
        payload.get("response", {}).get("body", {}).get("items", {})
    )
    if isinstance(items, dict):
        item = items.get("item", [])
        return item if isinstance(item, list) else [item]
    if isinstance(items, list):
        return items
    return []


def fetch_page(service_key, page):
    params = {
        "serviceKey": service_key,
        "page": page,
        "perPage": PER_PAGE,
        "returnType": "json",
        "cond[rcrt_prgs_yn::EQ]": "Y",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "grant-radar-newsletter"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise SetupError(
            "API가 JSON이 아닌 응답을 돌려줬어요. 인증키(Decoding 키)와 활용신청 승인 상태를 확인하세요.\n"
            + body[:300]
        )


def fetch_all(service_key):
    rows = []
    for page in range(1, MAX_PAGES + 1):
        payload = fetch_page(service_key, page)
        batch = extract_rows(payload)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return rows


def normalize(rows):
    if not rows:
        raise SetupError("수집된 공고가 0건이에요. API 응답이나 인증키를 확인해야 합니다.")
    out = []
    for raw in rows:
        title = pick(raw, "title")
        if not title:
            continue
        recruiting = pick(raw, "recruiting")
        if recruiting and recruiting.upper() not in ("Y", "모집중"):
            continue
        end = parse_date(pick(raw, "end"))
        if end and end < TODAY:
            continue
        url = pick(raw, "url")
        uid = pick(raw, "id") or hashlib.sha1((title + url).encode()).hexdigest()[:16]
        out.append({
            "id": uid,
            "title": title,
            "org": pick(raw, "org"),
            "start": parse_date(pick(raw, "start")),
            "end": end,
            "url": url or "https://www.k-startup.go.kr",
            "region": pick(raw, "region"),
            "category": pick(raw, "category"),
            "target": pick(raw, "target"),
        })
    if not out:
        sample_keys = sorted(rows[0].keys())
        raise SetupError(
            "공고는 받았지만 제목 필드를 찾지 못했어요. 실제 필드명: " + ", ".join(sample_keys)
        )
    return out


# ---------------------------------------------------------------- 상태

def load_state(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen": [], "issues": []}


def save_state(path, state):
    state["seen"] = state["seen"][-MAX_SEEN_IDS:]
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 렌더링

def esc(text):
    return html.escape(text or "")


def fmt_date(d):
    return f"{d.month}/{d.day}" if d else "상시"


def dday(d):
    if not d:
        return ""
    left = (d - TODAY).days
    return "오늘 마감" if left == 0 else f"D-{left}"


def item_html(it, highlight_deadline=False):
    meta = " · ".join(x for x in [it["org"], it["region"], it["category"]] if x)
    period = f"{fmt_date(it['start'])} ~ {fmt_date(it['end'])}"
    badge = ""
    if highlight_deadline and it["end"]:
        badge = (f'<span style="display:inline-block;background:#fdecea;color:#b3261e;'
                 f'font-size:12px;font-weight:700;padding:2px 8px;border-radius:10px;'
                 f'margin-right:6px">{dday(it["end"])}</span>')
    target = ""
    if it["target"]:
        t = it["target"] if len(it["target"]) <= 60 else it["target"][:60] + "…"
        target = f'<div style="font-size:13px;color:#555;margin-top:2px">대상: {esc(t)}</div>'
    return (
        '<tr><td style="padding:14px 0;border-bottom:1px solid #eee">'
        f'<div>{badge}<a href="{esc(it["url"])}" style="color:#1a1a1a;font-size:16px;'
        f'font-weight:700;text-decoration:none">{esc(it["title"])}</a></div>'
        f'<div style="font-size:13px;color:#777;margin-top:4px">{esc(meta)}</div>'
        f'<div style="font-size:13px;color:#555;margin-top:2px">접수: {period}</div>'
        f'{target}'
        '</td></tr>'
    )


def section_html(title, items, highlight_deadline=False, empty_text=""):
    if not items:
        body = f'<tr><td style="padding:12px 0;color:#888;font-size:14px">{esc(empty_text)}</td></tr>'
    else:
        body = "".join(item_html(i, highlight_deadline) for i in items)
    return (
        f'<h2 style="font-size:18px;margin:32px 0 4px;color:#1a1a1a">{esc(title)} '
        f'<span style="color:#999;font-weight:400">({len(items)})</span></h2>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{body}</table>'
    )


def build_body(cfg, new_items, closing, total):
    return (
        f'<p style="font-size:15px;color:#333;line-height:1.6">'
        f'{TODAY.year}년 {TODAY.month}월 {TODAY.day}일 기준, 현재 모집 중인 창업 지원사업은 '
        f'<b>{total}건</b>이에요. 이번 주 새로 올라온 공고와 마감이 임박한 공고만 골라 정리했습니다.</p>'
        + section_html("⏰ 7일 안에 마감", closing, True, "이번 주 마감 예정 공고가 없어요.")
        + section_html("🆕 새로 올라온 공고", new_items, False, "새로 올라온 공고가 없어요.")
        + f'<p style="margin-top:32px"><a href="{esc(cfg["site_url"])}" style="display:inline-block;'
          f'background:#1a1a1a;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;'
          f'font-weight:700">전체 공고 보기</a></p>'
    )


FOOTER_NOTE = ("공고 정보는 K-Startup 공개 데이터를 자동으로 정리한 것이며, 신청 전 반드시 원문 공고를 확인하세요. "
               "공고 내용에 대한 문의는 각 주관기관으로 해주세요. 이 메일은 발신 전용입니다.")
WEB_NOTE = ("공고 정보는 K-Startup 공개 데이터를 자동으로 정리한 것이며, 신청 전 반드시 원문 공고를 확인하세요. "
            "공고 내용에 대한 문의는 각 주관기관으로 해주세요.")


def build_email(cfg, body):
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f6f6f4;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border-radius:12px">
<tr><td style="padding:28px 24px">
<div style="font-size:13px;color:#888;letter-spacing:.5px">{esc(cfg['name'])}</div>
<h1 style="font-size:22px;margin:6px 0 16px;color:#1a1a1a">이번 주 창업 지원사업 브리핑</h1>
{body}
<p style="font-size:12px;color:#999;line-height:1.6;margin-top:36px;border-top:1px solid #eee;padding-top:16px">
{esc(FOOTER_NOTE)}<br>
<a href="{esc(cfg['site_url'])}/newsletter/" style="color:#999">지난 브리핑 보기</a> ·
<a href="{{{{ unsubscribe }}}}" style="color:#999">수신거부</a></p>
</td></tr></table></td></tr></table></body></html>"""


PAGE_CSS = """
:root{--bg:#f6f6f4;--card:#fff;--fg:#1a1a1a;--muted:#777}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--fg:#eee;--muted:#999}}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif}
main{max-width:640px;margin:0 auto;padding:24px 16px}
.card{background:var(--card);border-radius:12px;padding:24px}
a{color:inherit} .muted{color:var(--muted);font-size:13px}
.issue-list li{margin:10px 0}
"""


def build_page(cfg, title, inner, rel_root):
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {esc(cfg['name'])}</title>
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['name'])}" href="{rel_root}feed.xml">
<style>{PAGE_CSS}</style></head><body><main>
<p class="muted"><a href="{rel_root}">{esc(cfg['name'])}</a></p>
<div class="card">{inner}</div>
<p class="muted" style="margin-top:20px">{esc(WEB_NOTE)}</p>
</main></body></html>"""


def build_feed(cfg, issues):
    items = []
    for iss in issues[:20]:
        link = f"{cfg['site_url']}/newsletter/issues/{iss['slug']}.html"
        pub = datetime.fromisoformat(iss["date"]).replace(tzinfo=KST)
        items.append(
            f"<item><title>{esc(iss['title'])}</title><link>{esc(link)}</link>"
            f"<guid>{esc(link)}</guid><pubDate>{pub.strftime('%a, %d %b %Y 09:00:00 +0900')}</pubDate>"
            f"<description>{esc(iss['summary'])}</description></item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{esc(cfg['name'])}</title><link>{esc(cfg['site_url'])}/newsletter/</link>"
        "<description>매주 정리하는 창업 지원사업 신규·마감임박 공고</description><language>ko</language>"
        + "".join(items) + "</channel></rss>"
    )


# ---------------------------------------------------------------- 발송

def brevo_request(api_key, path, payload):
    req = urllib.request.Request(
        "https://api.brevo.com/v3" + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def brevo_subscriber_count(cfg):
    req = urllib.request.Request(
        f"https://api.brevo.com/v3/contacts/lists/{int(cfg['brevo_list'])}",
        headers={"api-key": cfg["brevo_key"], "accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return int(data.get("uniqueSubscribers", data.get("totalSubscribers", 0)) or 0)


def send_brevo(cfg, subject, email_html):
    if brevo_subscriber_count(cfg) == 0:
        return None
    campaign = brevo_request(cfg["brevo_key"], "/emailCampaigns", {
        "name": f"grant-radar {TODAY.isoformat()}",
        "subject": subject,
        "sender": {"name": cfg["sender_name"], "email": cfg["sender_email"]},
        "type": "classic",
        "htmlContent": email_html,
        "recipients": {"listIds": [int(cfg["brevo_list"])]},
    })
    brevo_request(cfg["brevo_key"], f"/emailCampaigns/{campaign['id']}/sendNow", {})
    return campaign["id"]


# ---------------------------------------------------------------- 실행

def load_config(args):
    cfg = {
        "site_url": os.environ.get("SITE_URL", "https://grants.kinfocloud.co.kr").rstrip("/"),
        "out": Path(os.environ.get("OUTPUT_DIR", "newsletter")),
        "name": os.environ.get("NEWSLETTER_NAME", "그랜트 레이더 주간 브리핑"),
        "service_key": os.environ.get("KSTARTUP_SERVICE_KEY", ""),
        "brevo_key": os.environ.get("BREVO_API_KEY", ""),
        "brevo_list": os.environ.get("BREVO_LIST_ID", ""),
        "sender_email": os.environ.get("SENDER_EMAIL", ""),
    }
    cfg["sender_name"] = os.environ.get("SENDER_NAME", cfg["name"])
    cfg["send"] = bool(cfg["brevo_key"]) and not args.no_send and not args.sample
    if cfg["send"] and not (cfg["brevo_list"] and cfg["sender_email"]):
        raise SetupError("BREVO_API_KEY는 있는데 BREVO_LIST_ID 또는 SENDER_EMAIL이 비어 있어요.")
    if not args.sample and not cfg["service_key"]:
        raise SetupError("KSTARTUP_SERVICE_KEY가 없어요. 공공데이터포털 인증키를 GitHub Secrets에 넣어주세요.")
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="샘플 데이터로 시험 실행")
    ap.add_argument("--no-send", action="store_true", help="이메일 발송 없이 생성만")
    args = ap.parse_args()

    cfg = load_config(args)
    out = cfg["out"]
    (out / "issues").mkdir(parents=True, exist_ok=True)

    if args.sample:
        rows = json.loads((Path(__file__).parent / "sample_data.json").read_text(encoding="utf-8"))
    else:
        rows = fetch_all(cfg["service_key"])
    items = normalize(rows)

    state_path = out / "state.json"
    state = load_state(state_path)
    seen = set(state["seen"])
    first_run = not seen

    closing = [i for i in items if i["end"] and 0 <= (i["end"] - TODAY).days <= CLOSING_SOON_DAYS]
    closing.sort(key=lambda i: i["end"])
    closing_ids = {i["id"] for i in closing}
    # 마감 임박에 이미 나온 공고는 신규 목록에서 빼서 중복 노출 방지
    new_items = [] if first_run else [i for i in items if i["id"] not in seen and i["id"] not in closing_ids]
    new_items.sort(key=lambda i: (i["end"] or date.max))

    state["seen"].extend(i["id"] for i in items if i["id"] not in seen)

    if first_run:
        # 첫 실행은 기준점만 기록 (전체 공고가 '신규'로 쏟아지는 것 방지)
        save_state(state_path, state)
        print(f"첫 실행: 공고 {len(items)}건을 기준점으로 저장했어요. 다음 실행부터 신규 공고를 추려 발송합니다.")
        write_index_and_feed(cfg, state)
        return

    if not new_items and not closing:
        save_state(state_path, state)
        print("이번 주는 새 공고도 마감 임박 공고도 없어 발송을 건너뜁니다.")
        return

    iso_year, iso_week, _ = TODAY.isocalendar()
    slug = f"{iso_year}-W{iso_week:02d}"
    subject = f"[창업지원] 신규 {len(new_items)}건 · 마감임박 {len(closing)}건 ({TODAY.month}/{TODAY.day})"
    body = build_body(cfg, new_items, closing, len(items))

    page_inner = (f'<h1 style="font-size:22px;margin:0 0 12px">{TODAY.month}월 {TODAY.day}일 창업 지원사업 브리핑</h1>'
                  + body)
    (out / "issues" / f"{slug}.html").write_text(build_page(cfg, subject, page_inner, "../"), encoding="utf-8")
    email_html = build_email(cfg, body)
    (out / "latest-email.html").write_text(email_html, encoding="utf-8")

    state["issues"] = [i for i in state["issues"] if i["slug"] != slug]
    state["issues"].insert(0, {
        "slug": slug, "date": TODAY.isoformat(), "title": subject,
        "summary": f"신규 공고 {len(new_items)}건, 7일 내 마감 {len(closing)}건",
    })
    write_index_and_feed(cfg, state)

    if cfg["send"]:
        cid = send_brevo(cfg, subject, email_html)
        if cid is None:
            print("아직 구독자가 없어 이메일 발송은 건너뛰었어요. (웹 아카이브는 생성됨)")
        else:
            print(f"발송 완료: Brevo 캠페인 #{cid}")
    else:
        print("발송 키가 없거나 시험 모드라 이메일은 보내지 않았어요.")

    save_state(state_path, state)
    print(f"생성 완료: {slug} (신규 {len(new_items)}건, 마감임박 {len(closing)}건, 전체 {len(items)}건)")


def subscribe_form():
    """newsletter/subscribe-form.html 이 있으면 아카이브 페이지에 그대로 끼워 넣음."""
    path = Path(__file__).parent / "subscribe-form.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_index_and_feed(cfg, state):
    out = cfg["out"]
    issues = state["issues"]
    lis = "".join(
        f'<li><a href="issues/{esc(i["slug"])}.html">{esc(i["title"])}</a></li>' for i in issues
    ) or "<li>첫 브리핑을 준비 중이에요.</li>"
    inner = (
        '<h1 style="margin:0 0 8px">창업 지원사업 주간 브리핑</h1>'
        '<p>매주 새로 올라온 공고와 마감이 임박한 공고만 골라 무료로 보내드려요.</p>'
        + subscribe_form()
        +
        f'<h2 style="font-size:17px;margin-top:28px">지난 브리핑</h2><ul class="issue-list">{lis}</ul>'
    )
    (out / "index.html").write_text(build_page(cfg, "지난 브리핑", inner, ""), encoding="utf-8")
    (out / "feed.xml").write_text(build_feed(cfg, issues), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except SetupError as e:
        print("설정 확인 필요: " + str(e), file=sys.stderr)
        sys.exit(1)
