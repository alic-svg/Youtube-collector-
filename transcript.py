"""
YouTube 스크립트(자막) 수집 모듈
- youtube-transcript-api 사용 (쿼터 소모 없음)
- 영상 메타데이터(제목·조회수·채널·태그)는 YouTube Data API로 조회
- 프록시 로테이션으로 클라우드 IP 차단 우회
"""

import json
import re
import time
import random
import os
import requests
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_AVAILABLE = True
except ImportError:
    _TRANSCRIPT_AVAILABLE = False

# cookies.json 위치: 이 파일과 같은 폴더의 agent/ 하위
_COOKIES_FILE = Path(__file__).parent / "agent" / "cookies.json"


def _build_http_client() -> requests.Session:
    """agent/cookies.json을 읽어 requests.Session 반환."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36",
    })
    if not _COOKIES_FILE.exists():
        return session
    try:
        with open(_COOKIES_FILE, encoding="utf-8") as f:
            for c in json.load(f):
                session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ".youtube.com"),
                    path=c.get("path", "/"),
                )
    except Exception:
        pass
    return session

BASE_URL = "https://www.googleapis.com/youtube/v3"

LANG_PRIORITY = {
    "한국어": ["ko", "ko-KR", "en", "en-US"],
    "일본어": ["ja", "en", "ko"],
    "영어":   ["en", "en-US", "ko", "ja"],
    "자동감지": None,
}


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def extract_video_id(url: str):
    url = url.strip()
    for p in [r"(?:v=)([A-Za-z0-9_-]{11})",
              r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
              r"(?:shorts/)([A-Za-z0-9_-]{11})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def build_thumbnail_formula(video_id):
    return f'=IFERROR(IMAGE("https://i.ytimg.com/vi/{video_id}/mqdefault.jpg","",0),"")'


def _make_api(proxy_url: str = None, http_client: requests.Session = None):
    """프록시/쿠키 세션으로 API 인스턴스 생성."""
    if not _TRANSCRIPT_AVAILABLE:
        return None

    kwargs = {}
    if http_client:
        kwargs["http_client"] = http_client

    if proxy_url:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            kwargs["proxy_config"] = GenericProxyConfig(
                http_proxy=proxy_url,
                https_proxy=proxy_url,
            )
        except Exception:
            pass

    try:
        return YouTubeTranscriptApi(**kwargs)
    except Exception:
        return YouTubeTranscriptApi()


# ─────────────────────────────────────────
# 영상 메타데이터 (Data API)
# ─────────────────────────────────────────
def get_video_metadata(video_ids: list, api_key: str):
    results = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            r = requests.get(
                f"{BASE_URL}/videos",
                params={"key": api_key, "part": "snippet,statistics", "id": ",".join(batch)},
                timeout=15,
            )
            d = r.json()
            if "error" in d:
                continue
            for item in d.get("items", []):
                vid   = item["id"]
                snip  = item["snippet"]
                stats = item.get("statistics", {})
                results[vid] = {
                    "channel_id":   snip["channelId"],
                    "channel_name": snip["channelTitle"],
                    "title":        snip["title"],
                    "views":        int(stats.get("viewCount", 0)),
                    "upload_date":  snip["publishedAt"][:10],
                    "tags":         snip.get("tags", []),
                }
        except Exception:
            pass
        time.sleep(0.2)
    return results


def get_channel_stats(channel_ids: list, api_key: str):
    results = {}
    for i in range(0, len(channel_ids), 50):
        batch = list(channel_ids)[i:i+50]
        try:
            r = requests.get(
                f"{BASE_URL}/channels",
                params={"key": api_key, "part": "statistics", "id": ",".join(batch)},
                timeout=15,
            )
            d = r.json()
            if "error" in d:
                continue
            for item in d.get("items", []):
                cid   = item["id"]
                stats = item.get("statistics", {})
                vc    = int(stats.get("videoCount", 1)) or 1
                results[cid] = {
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "avg_views":   round(int(stats.get("viewCount", 0)) / vc),
                }
        except Exception:
            pass
        time.sleep(0.2)
    return results


# ─────────────────────────────────────────
# 자막 수집 (프록시 로테이션)
# ─────────────────────────────────────────
def get_transcript(video_id: str, lang_pref: str = "한국어",
                   proxy_list: list = None, http_client: requests.Session = None):
    """
    반환: (full_text, lang_used, is_auto, error_msg)
    http_client: 쿠키가 담긴 requests.Session (없으면 자동으로 cookies.json 로드)
    proxy_list: ["http://user:pass@ip:port", ...] 형식의 프록시 목록
    """
    if not _TRANSCRIPT_AVAILABLE:
        return None, None, None, "youtube-transcript-api 패키지가 설치되지 않았습니다."

    client = http_client or _build_http_client()

    proxies_to_try = [None]
    if proxy_list:
        shuffled = list(proxy_list)
        random.shuffle(shuffled)
        proxies_to_try = shuffled + [None]

    last_err = "알 수 없는 오류"

    for proxy_url in proxies_to_try:
        api = _make_api(proxy_url, client)
        if not api:
            continue
        try:
            langs = LANG_PRIORITY.get(lang_pref)
            tl = api.list(video_id)
            transcripts = list(tl)

            chosen = None
            lang_used = ""
            is_auto = False

            if langs:
                for lang in langs:
                    for t in transcripts:
                        if t.language_code.startswith(lang) and not t.is_generated:
                            chosen = t
                            lang_used = t.language_code
                            is_auto = False
                            break
                    if chosen:
                        break
                if not chosen:
                    for lang in langs:
                        for t in transcripts:
                            if t.language_code.startswith(lang) and t.is_generated:
                                chosen = t
                                lang_used = t.language_code
                                is_auto = True
                                break
                        if chosen:
                            break
            else:
                if transcripts:
                    chosen = transcripts[0]
                    lang_used = chosen.language_code
                    is_auto = chosen.is_generated

            if not chosen:
                return None, None, None, "사용 가능한 자막 없음"

            segments = chosen.fetch()
            full_text = " ".join(s.text.strip() for s in segments if s.text.strip())
            return full_text, lang_used, is_auto, None

        except Exception as e:
            last_err = str(e)
            is_blocking = any(k in last_err.lower() for k in
                              ["blocked", "429", "too many", "rate",
                               "ipblocked", "requestblocked", "cloud"])
            if is_blocking and proxy_url:
                time.sleep(random.uniform(0.5, 1.5))
                continue
            return None, None, None, last_err

    return None, None, None, f"모든 시도 실패 — {last_err}"


# ─────────────────────────────────────────
# 통합 수집
# ─────────────────────────────────────────
def collect_transcripts(urls: list, api_key: str, lang_pref: str = "한국어",
                        proxy_list: list = None, callback=None):
    """URL 목록 → 메타데이터 + 스크립트 수집. 쿠키는 agent/cookies.json에서 자동 로드."""
    total = len(urls)
    http_client = _build_http_client()

    # 1. 영상 ID 추출
    url_id_map = {}
    for url in urls:
        vid = extract_video_id(url)
        if vid:
            url_id_map[url] = vid

    valid_ids = list(set(url_id_map.values()))

    # 2. 메타데이터 조회
    if callback:
        callback(0.1, f"영상 정보 조회 중... ({len(valid_ids)}개)")
    metadata = get_video_metadata(valid_ids, api_key) if api_key else {}

    # 3. 채널 통계
    channel_ids = list({m["channel_id"] for m in metadata.values() if "channel_id" in m})
    ch_stats = get_channel_stats(channel_ids, api_key) if api_key and channel_ids else {}

    # 4. 자막 수집
    results = []
    for i, url in enumerate(urls):
        if callback:
            callback(0.2 + i / total * 0.8, f"자막 수집 중... ({i+1}/{total})")

        vid = url_id_map.get(url)
        if not vid:
            results.append({
                "채널명": "", "구독자수": 0, "채널평균조회수": 0,
                "썸네일": "", "썸네일URL": "",
                "제목": url, "조회수": 0, "업로드일자": "",
                "URL": url, "스크립트": "", "핵심키워드(태그)": "",
                "_오류": "유효하지 않은 URL",
            })
            continue

        meta     = metadata.get(vid, {})
        cid      = meta.get("channel_id", "")
        ch       = ch_stats.get(cid, {"subscribers": 0, "avg_views": 0})
        tags     = meta.get("tags", [])
        keywords = ", ".join(tags[:10]) if tags else ""

        text, lang, is_auto, err = get_transcript(
            vid, lang_pref, proxy_list=proxy_list, http_client=http_client
        )

        time.sleep(random.uniform(2.0, 5.0))

        results.append({
            "채널명":           meta.get("channel_name", ""),
            "구독자수":         ch["subscribers"],
            "채널평균조회수":   ch["avg_views"],
            "썸네일":           build_thumbnail_formula(vid),
            "썸네일URL":        f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "제목":             meta.get("title", vid),
            "조회수":           meta.get("views", 0),
            "업로드일자":       meta.get("upload_date", ""),
            "URL":              url,
            "스크립트":         text or "",
            "핵심키워드(태그)": keywords,
            "_오류":            err or "",
        })

    if callback:
        callback(1.0, "완료")
    return results
