"""data/*.json 으로 정적 사이트(site/)를 만든다.

site/index.html        모집 중 공고 목록 + 필터
site/p/<id>.html       공고별 상세 페이지 (검색 유입용, 마감 후 180일 유지)
site/sitemap.xml, robots.txt, feed.xml, CNAME
"""
import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site"
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()

e = lambda s: escape(str(s or ""), quote=True)  # noqa: E731


def dday(end):
    if not end:
        return None
    return (date.fromisoformat(end) - TODAY).days


def dday_label(end):
    d = dday(end)
    if d is None:
        return "상시"
    if d < 0:
        return "마감"
    return "오늘 마감" if d == 0 else f"D-{d}"


def fmt(d):
    if not d:
        return "-"
    x = date.fromisoformat(d)
    return f"{x.year}.{x.month:02d}.{x.day:02d}"


def short(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--sub:#5d6470;--line:#e3e6eb;
--accent:#2f5bea;--accent-soft:#e8eefe;--hot:#d6402b;--hot-soft:#fdecea;--ok:#1f8a5b;--ok-soft:#e3f5ec}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#181b21;--ink:#eceef2;--sub:#9aa2ae;
--line:#2a2f38;--accent:#7b9bff;--accent-soft:#1f2a4a;--hot:#ff7b67;--hot-soft:#3a1f1b;--ok:#5fd19b;--ok-soft:#173326}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 "Pretendard","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;word-break:keep-all}
a{color:inherit}.wrap{max-width:880px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line);background:var(--card)}
header.top .wrap{display:flex;align-items:center;justify-content:space-between;height:56px;gap:12px}
.logo{font-weight:800;text-decoration:none;letter-spacing:-.02em}.logo span{color:var(--accent)}
.toplink{font-size:14px;color:var(--sub);text-decoration:none}
.hero{padding:36px 0 20px}.hero h1{font-size:clamp(24px,5vw,32px);line-height:1.3;margin:0 0 8px;letter-spacing:-.03em}
.hero p{margin:0;color:var(--sub)}.updated{font-size:13px;color:var(--sub);margin-top:6px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:22px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.stat b{display:block;font-size:24px;letter-spacing:-.02em}.stat small{color:var(--sub);font-size:13px}
.cta{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--accent-soft);
border-radius:12px;padding:14px 16px;margin-bottom:20px;font-size:15px}
.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;
padding:10px 16px;border-radius:10px;white-space:nowrap;font-size:15px}
.filters{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:7px 14px;font-size:14px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.filters select,.filters input{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:7px 10px;font-size:14px}
.filters input{flex:1;min-width:140px}
.list{list-style:none;padding:0;margin:8px 0 40px;display:grid;gap:10px}
.item a{display:block;text-decoration:none;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.item a:hover{border-color:var(--accent)}
.item h2{font-size:16px;margin:6px 0 4px;line-height:1.45}
.meta{font-size:13px;color:var(--sub);display:flex;flex-wrap:wrap;gap:4px 10px}
.badges{display:flex;flex-wrap:wrap;gap:6px}
.badge{font-size:12px;font-weight:700;border-radius:6px;padding:2px 7px;background:var(--line);color:var(--sub)}
.badge.hot{background:var(--hot-soft);color:var(--hot)}.badge.ai{background:var(--accent-soft);color:var(--accent)}
.badge.ok{background:var(--ok-soft);color:var(--ok)}
.empty{text-align:center;color:var(--sub);padding:40px 0;display:none}
article{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 18px;margin:24px 0}
article h1{font-size:clamp(20px,4.5vw,26px);line-height:1.4;margin:10px 0 16px;letter-spacing:-.02em}
dl.info{display:grid;grid-template-columns:96px 1fr;gap:8px 12px;margin:0 0 18px;font-size:15px}
dl.info dt{color:var(--sub)}dl.info dd{margin:0}
.summary{white-space:pre-line;border-top:1px solid var(--line);padding-top:16px;color:var(--ink)}
.closed{background:var(--hot-soft);color:var(--hot);border-radius:10px;padding:10px 14px;font-weight:700;margin-bottom:14px}
.related h3{font-size:17px}.note{font-size:13px;color:var(--sub)}
footer{border-top:1px solid var(--line);padding:24px 0 40px;font-size:13px;color:var(--sub)}
footer a{color:var(--sub)}
@media (max-width:560px){.stats{gap:6px}.stat{padding:10px}.stat b{font-size:20px}.cta{flex-direction:column;align-items:flex-start}
dl.info{grid-template-columns:80px 1fr}}
"""


def head(title, desc, path, extra=""):
    canonical = config.SITE_URL + path
    ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
           f'{e(config.ADSENSE_CLIENT)}" crossorigin="anonymous"></script>') if config.ADSENSE_CLIENT else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}"><meta property="og:type" content="website"><meta property="og:locale" content="ko_KR">
<link rel="alternate" type="application/rss+xml" title="{e(config.SITE_NAME)}" href="/feed.xml">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📡</text></svg>">
<style>{CSS}</style>{ads}{extra}</head><body>
<header class="top"><div class="wrap"><a class="logo" href="/">📡 <span>{e(config.SITE_NAME)}</span></a>
<a class="toplink" href="{e(config.BLOG_URL)}">{e(config.BLOG_NAME)} →</a></div></header>"""


def foot():
    return f"""<footer><div class="wrap">
<p>공고 정보는 창업진흥원 K-Startup 공공데이터(공공데이터포털)를 매일 자동으로 받아 정리한 것입니다.
신청 전 반드시 K-Startup 원문 공고에서 자격 요건과 마감일을 확인하세요.</p>
<p>운영: <a href="{e(config.BLOG_URL)}">{e(config.BLOG_NAME)}</a> · <a href="/feed.xml">RSS</a></p>
</div></footer></body></html>"""


def badges(it):
    out = []
    d = dday(it["end"])
    if d is not None and d < 0:
        out.append('<span class="badge">마감</span>')
    elif d is not None and d <= 7:
        out.append(f'<span class="badge hot">{e(dday_label(it["end"]))}</span>')
    else:
        out.append(f'<span class="badge ok">{e(dday_label(it["end"]))}</span>')
    if it["ai"]:
        out.append('<span class="badge ai">AI·개발</span>')
    if it["category"]:
        out.append(f'<span class="badge">{e(it["category"])}</span>')
    return '<div class="badges">' + "".join(out) + "</div>"


def card(it):
    d = dday(it["end"])
    soon = "1" if d is not None and 0 <= d <= 7 else "0"
    search = " ".join([it["title"], it["org"], it["target"], it["category"], it["region"]])
    return (f'<li class="item" data-ai="{int(it["ai"])}" data-soon="{soon}" data-region="{e(it["region"])}" '
            f'data-cat="{e(it["category"])}" data-q="{e(search.lower())}"><a href="/p/{e(it["id"])}.html">'
            f'{badges(it)}<h2>{e(it["title"])}</h2><div class="meta"><span>{e(it["org"] or "주관기관 미상")}</span>'
            f'<span>{e(it["region"])}</span><span>~{e(fmt(it["end"]))}</span></div></a></li>')


def build_index(items, updated):
    ai_n = sum(x["ai"] for x in items)
    week_n = sum(1 for x in items if (dday(x["end"]) is not None and 0 <= dday(x["end"]) <= 7))
    regions = sorted({x["region"] for x in items if x["region"]})
    cats = sorted({x["category"] for x in items if x["category"]})
    opt = lambda vals: "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in vals)  # noqa: E731
    cta = (f'<div class="cta"><span>새 공고와 마감 임박 알림을 텔레그램으로 받아보세요.</span>'
           f'<a class="btn" href="{e(config.TELEGRAM_CHANNEL_URL)}">텔레그램 구독</a></div>'
           if config.TELEGRAM_CHANNEL_URL else "")
    desc = f"지금 모집 중인 정부 창업 지원사업 {len(items)}건. AI·SW·1인 창업 관련 공고를 매일 자동으로 정리합니다."
    html = head(f"{config.SITE_NAME} - {config.SITE_TAGLINE}", desc, "/") + f"""
<main class="wrap"><section class="hero"><h1>{e(config.SITE_TAGLINE)}</h1>
<p>K-Startup 공고를 매일 아침 자동으로 모아, AI·개발 관련 사업을 따로 표시해 드려요.</p>
<div class="updated">마지막 업데이트 {e(updated.replace("T", " ")[:16])}</div></section>
<div class="stats"><div class="stat"><b>{len(items)}</b><small>모집 중 공고</small></div>
<div class="stat"><b>{ai_n}</b><small>AI·개발 관련</small></div>
<div class="stat"><b>{week_n}</b><small>7일 내 마감</small></div></div>
{cta}
<div class="filters" role="search">
<button class="chip" data-f="all" aria-pressed="true">전체</button>
<button class="chip" data-f="ai" aria-pressed="false">AI·개발 추천</button>
<button class="chip" data-f="soon" aria-pressed="false">마감 임박</button>
<select id="region" aria-label="지역"><option value="">전체 지역</option>{opt(regions)}</select>
<select id="cat" aria-label="지원 분야"><option value="">전체 분야</option>{opt(cats)}</select>
<input id="q" type="search" placeholder="검색 (예: 예비창업, 바우처)" aria-label="검색">
</div>
<ul class="list" id="list">{"".join(card(x) for x in items)}</ul>
<p class="empty" id="empty">조건에 맞는 공고가 없어요.</p></main>
<script>
(function(){{var f='all',L=document.querySelectorAll('#list .item'),R=document.getElementById('region'),
C=document.getElementById('cat'),Q=document.getElementById('q'),E=document.getElementById('empty');
function run(){{var q=Q.value.trim().toLowerCase(),n=0;L.forEach(function(li){{var d=li.dataset,
ok=(f=='all'||(f=='ai'&&d.ai=='1')||(f=='soon'&&d.soon=='1'))&&(!R.value||d.region==R.value||d.region=='전국')
&&(!C.value||d.cat==C.value)&&(!q||d.q.indexOf(q)>-1);li.style.display=ok?'':'none';if(ok)n++}});
E.style.display=n?'none':'block'}}
document.querySelectorAll('.chip').forEach(function(b){{b.onclick=function(){{f=b.dataset.f;
document.querySelectorAll('.chip').forEach(function(x){{x.setAttribute('aria-pressed',x==b)}});run()}}}});
[R,C].forEach(function(x){{x.onchange=run}});Q.oninput=run;}})();
</script>""" + foot()
    (OUT / "index.html").write_text(html, encoding="utf-8")


def build_detail(it, related):
    closed = dday(it["end"]) is not None and dday(it["end"]) < 0
    rows = [("주관기관", it["org"]), ("지원분야", it["category"]), ("지역", it["region"]),
            ("신청대상", it["target"]), ("창업기간", it["years"]), ("대상연령", it["age"]),
            ("접수기간", f'{fmt(it["start"])} ~ {fmt(it["end"])}')]
    info = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows if v and v.strip(" ~-"))
    body = it["summary"] or it["target_detail"]
    desc = short(f'{it["title"]} - {it["org"]} 주관, 접수 {fmt(it["start"])}~{fmt(it["end"])}. {body}', 150)
    ld = json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": it["title"][:110],
                     "datePublished": it.get("first_seen") or TODAY.isoformat(),
                     "publisher": {"@type": "Organization", "name": config.BLOG_NAME}},
                    ensure_ascii=False).replace("</", "<\\/")
    rel = "".join(card(x) for x in related)
    html = head(f'{it["title"]} | {config.SITE_NAME}', desc, f'/p/{it["id"]}.html',
                f'<script type="application/ld+json">{ld}</script>') + f"""
<main class="wrap"><article>
{'<div class="closed">모집이 마감된 공고입니다. 아래에서 지금 모집 중인 공고를 확인하세요.</div>' if closed else ''}
{badges(it)}<h1>{e(it["title"])}</h1><dl class="info">{info}</dl>
{f'<div class="summary">{e(body)}</div>' if body else ''}
<p style="margin-top:20px"><a class="btn" href="{e(it["url"])}" rel="nofollow noopener" target="_blank">K-Startup 원문 공고 보기</a></p>
<p class="note">자격 요건·제출 서류·마감일은 원문 공고가 기준입니다.</p>
</article>
{f'<section class="related"><h3>지금 모집 중인 비슷한 공고</h3><ul class="list">{rel}</ul></section>' if rel else ''}
</main>""" + foot()
    (OUT / "p" / f'{it["id"]}.html').write_text(html, encoding="utf-8")


def build_feeds(items, archive):
    urls = [f"{config.SITE_URL}/"] + [f"{config.SITE_URL}/p/{i}.html" for i in archive]
    sm = "".join(f"<url><loc>{e(u)}</loc></url>" for u in urls)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>',
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {config.SITE_URL}/sitemap.xml\n", encoding="utf-8")
    recent = sorted(items, key=lambda x: x.get("first_seen", ""), reverse=True)[:50]
    entries = "".join(
        f'<item><title>{e(x["title"])}</title><link>{config.SITE_URL}/p/{e(x["id"])}.html</link>'
        f'<guid>{config.SITE_URL}/p/{e(x["id"])}.html</guid>'
        f'<description>{e(x["org"])} · {e(x["region"])} · 마감 {e(fmt(x["end"]))}</description></item>'
        for x in recent)
    (OUT / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(config.SITE_NAME)}</title>'
        f'<link>{config.SITE_URL}/</link><description>{e(config.SITE_TAGLINE)}</description>{entries}</channel></rss>',
        encoding="utf-8")
    (OUT / "CNAME").write_text(urlparse(config.SITE_URL).netloc + "\n", encoding="utf-8")
    (OUT / "404.html").write_text(head(f"페이지를 찾을 수 없어요 | {config.SITE_NAME}", "", "/404.html")
                                  + '<main class="wrap"><article><h1>페이지를 찾을 수 없어요</h1>'
                                    '<p><a class="btn" href="/">모집 중 공고 보기</a></p></article></main>' + foot(),
                                  encoding="utf-8")


def main():
    data = json.loads((DATA / "announcements.json").read_text(encoding="utf-8"))
    items = data["items"]
    arch_path = DATA / "archive.json"
    archive = json.loads(arch_path.read_text(encoding="utf-8")) if arch_path.exists() else {}
    for it in items:
        archive[it["id"]] = it

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "p").mkdir(parents=True)

    build_index(items, data["updated"])
    live = [x for x in items if not (dday(x["end"]) is not None and dday(x["end"]) < 0)]
    for it in archive.values():
        pool = [x for x in live if x["id"] != it["id"]]
        same = [x for x in pool if x["ai"] == it["ai"] and x["category"] == it["category"]]
        related = (same + [x for x in pool if x not in same])[:5]
        build_detail(it, related)
    build_feeds(items, archive)
    print(f"사이트 생성 완료: 목록 {len(items)}건, 상세 페이지 {len(archive)}개 → {OUT}")


if __name__ == "__main__":
    main()
