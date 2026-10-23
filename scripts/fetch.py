"""K-Startup에서 모집 중인 공고를 모두 받아 data/announcements.json 에 저장한다.

- 환경변수 DATA_GO_KR_API_KEY 필요 (공공데이터포털 '일반 인증키 (Decoding)')
- 새로 나타난 공고는 data/new_today.json 에 따로 저장 (텔레그램 알림용)
- 실패하면 종료 코드 1 → GitHub Actions가 실패 메일을 보내준다
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))


def today_kst():
    return datetime.now(KST).date()


def call_api(key, page):
    params = {
        "serviceKey": key,
        "page": page,
        "perPage": config.PER_PAGE,
        "returnType": "json",
        "cond[rcrt_prgs_yn::EQ]": "Y",
    }
    url = config.API_URL + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8")
            data = json.loads(body)
            if "data" not in data:
                raise RuntimeError(f"예상치 못한 응답: {body[:300]}")
            return data
        except Exception as e:  # 네트워크 일시 오류 대비 재시도
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"API 호출 실패 (page={page}): {last_err}")


def parse_date(s):
    s = re.sub(r"\D", "", str(s or ""))[:8]
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def is_ai_related(row):
    text = " ".join(str(row.get(k, "")) for k in (
        "biz_pbanc_nm", "pbanc_ctnt", "supt_biz_clsfc", "aply_trgt_ctt", "aply_trgt"))
    for kw in config.AI_KEYWORDS:
        if kw in config.AI_KEYWORDS_STRICT:
            if re.search(rf"(?<![A-Za-z]){kw}(?![A-Za-z])", text):
                return True
        elif kw in text:
            return True
    return False


def normalize(row):
    sn = str(row.get("pbanc_sn") or row.get("id") or "").strip()
    end = parse_date(row.get("pbanc_rcpt_end_dt"))
    start = parse_date(row.get("pbanc_rcpt_bgng_dt"))
    url = row.get("detl_pg_url") or (
        f"https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn={sn}")
    return {
        "id": sn,
        "title": (row.get("biz_pbanc_nm") or row.get("intg_pbanc_biz_nm") or "").strip(),
        "org": (row.get("pbanc_ntrp_nm") or row.get("sprv_inst") or "").strip(),
        "category": (row.get("supt_biz_clsfc") or "").strip(),
        "region": (row.get("supt_regin") or "전국").strip(),
        "target": (row.get("aply_trgt") or "").strip(),
        "target_detail": (row.get("aply_trgt_ctt") or "").strip(),
        "years": (row.get("biz_enyy") or "").strip(),
        "age": (row.get("biz_trgt_age") or "").strip(),
        "summary": (row.get("pbanc_ctnt") or "").strip(),
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "url": url,
        "ai": is_ai_related(row),
    }


def fetch_all(key):
    rows = []
    for page in range(1, config.MAX_PAGES + 1):
        res = call_api(key, page)
        batch = res.get("data") or []
        rows.extend(batch)
        total = int(res.get("totalCount") or res.get("matchCount") or 0)
        if not batch or len(rows) >= total:
            break
    return rows


def main():
    key = os.environ.get("DATA_GO_KR_API_KEY")
    sample = os.environ.get("SAMPLE_FILE")  # 테스트용: 실제 API 대신 파일 사용
    if sample:
        raw = json.loads(Path(sample).read_text(encoding="utf-8"))["data"]
    elif key:
        raw = fetch_all(key)
    else:
        sys.exit("DATA_GO_KR_API_KEY 환경변수가 없습니다.")

    today = today_kst()
    items = {}
    for row in raw:
        it = normalize(row)
        if not it["id"] or not it["title"]:
            continue
        if it["end"] and it["end"] < today.isoformat():
            continue  # 이미 마감된 공고 제외
        items[it["id"]] = it

    if not items and not sample:
        # API가 빈 결과를 주면 사이트가 통째로 비지 않도록 실패 처리
        sys.exit("모집 중 공고가 0건입니다. API 상태를 확인하세요.")

    DATA.mkdir(exist_ok=True)
    seen_path = DATA / "seen.json"
    seen = json.loads(seen_path.read_text(encoding="utf-8")) if seen_path.exists() else {}
    first_run = not seen

    new_ids = [i for i in items if i not in seen]
    for i in items:
        seen.setdefault(i, today.isoformat())
        items[i]["first_seen"] = seen[i]

    ordered = sorted(items.values(), key=lambda x: (x["end"] or "9999", x["title"]))
    (DATA / "announcements.json").write_text(
        json.dumps({"updated": datetime.now(KST).isoformat(timespec="minutes"),
                    "items": ordered}, ensure_ascii=False, indent=1), encoding="utf-8")
    # 첫 실행 때는 기존 공고 전체를 '신규'로 알리지 않는다
    new_items = [] if first_run else [items[i] for i in new_ids]
    (DATA / "new_today.json").write_text(
        json.dumps(new_items, ensure_ascii=False, indent=1), encoding="utf-8")
    # seen 은 오래된 항목 정리 (180일)
    cutoff = (today - timedelta(days=180)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff or k in items}
    seen_path.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")

    # 아카이브: 마감된 공고 상세 페이지도 180일간 유지 (검색 유입이 끊기지 않게)
    arch_path = DATA / "archive.json"
    archive = json.loads(arch_path.read_text(encoding="utf-8")) if arch_path.exists() else {}
    archive.update(items)
    archive = {k: v for k, v in archive.items() if k in seen}
    arch_path.write_text(json.dumps(archive, ensure_ascii=False), encoding="utf-8")

    print(f"모집 중 {len(ordered)}건 (AI·개발 관련 {sum(x['ai'] for x in ordered)}건), "
          f"신규 {len(new_items)}건{' (첫 실행이라 알림 생략)' if first_run else ''}")


if __name__ == "__main__":
    main()
