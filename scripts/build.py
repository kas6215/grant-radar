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
.badge{
