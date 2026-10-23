
"""사이트 전체 설정. 바꿀 일이 있으면 이 파일만 고치면 됩니다."""

SITE_NAME = "지원사업 레이더"
SITE_TAGLINE = "1인 개발자·AI 창업자를 위한 정부 지원사업 알림"
SITE_URL = "https://grants.kinfocloud.co.kr"  # 하위 도메인 (CNAME 파일과 같아야 함)
BLOG_NAME = "킨포클라우드 개발노트"
BLOG_URL = "https://www.kinfocloud.co.kr"

# 텔레그램 채널 공개 주소 (예: https://t.me/kinfo_grants). 비워두면 구독 버튼 숨김
TELEGRAM_CHANNEL_URL = "https://t.me/kinfo_grants"

# 검색엔진 소유확인 태그 (네이버 서치어드바이저 등)
HEAD_EXTRA = '<meta name="naver-site-verification" content="4243f0485dfd33e16f521f400acaaa3d3900229b" />'

# 애드센스 게시자 ID (블로그에 이미 쓰고 있는 것과 동일)
ADSENSE_CLIENT = "ca-pub-8722569428171346"

# K-Startup 공고 API (공공데이터포털 15125364)
API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
PER_PAGE = 100
MAX_PAGES = 20  # 안전장치: 최대 2,000건

# 마감 며칠 전에 리마인드 알림을 보낼지
REMIND_DAYS = 3

# 'AI·개발자 추천' 태그를 붙일 키워드 (공고명·내용·분야에서 검색)
AI_KEYWORDS = [
    "AI", "인공지능", "SW", "소프트웨어", "디지털", "데이터", "클라우드",
    "플랫폼", "앱", "메타버스", "블록체인", "딥테크", "ICT", "IT", "빅데이터",
    "바우처", "1인 창조", "1인창조", "개발자", "SaaS", "로봇", "디지털전환", "DX",
]
# 짧은 영문 키워드는 다른 단어 일부와 오탐이 나지 않게 단어 경계로 검사
AI_KEYWORDS_STRICT = {"AI", "SW", "IT", "ICT", "DX"}
