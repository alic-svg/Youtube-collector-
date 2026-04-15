"""
YouTube 스크립트(자막) 수집 모듈
- youtube-transcript-api 사용 (쿼터 소모 없음)
- 영상 메타데이터(제목·조회수·채널·태그)는 YouTube Data API로 조회
"""

import re
import time
import random
import requests

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _api = YouTubeTranscriptApi()
    _TRANSCRIPT_AVAILABLE = True
except ImportError:
    _api = None
    _TRANSCRIPT_AVAILABLE = False

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


# ─────────────────────────────────────────
# 영상 메타데이터 (Data API)
# ─────────────────────────────────────────
def get_video_metadata(video_ids: list, api_key: str):
    """제목, 채널, 조회수, 태그 일괄 조회"""
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
                ch_id = snip["channelId"]
                results[vid] = {
                    "channel_id":   ch_id,
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
# 자막 수집
# ─────────────────────────────────────────
def get_transcript(video_id: str, lang_pref: str = "한국어", max_retries: int = 3):
    """
    반환: (full_text, lang_used, is_auto, error_msg)
    블로킹 방지를 위해 재시도 + 지수 백오프 적용
    """
    if not _TRANSCRIPT_AVAILABLE:
        return None, None, None, "youtube-transcript-api 패키지가 설치되지 않았습니다."

    for attempt in range(max_retries):
        try:
            langs = LANG_PRIORITY.get(lang_pref)
            tl = _api.list(video_id)
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
            err_msg = str(e)
            # 블로킹/레이트리밋 관련 오류면 대기 후 재시도
            is_blocking = any(k in err_msg.lower() for k in
                              ["429", "too many", "blocked", "rate", "timeout", "timed out"])
            if attempt < max_retries - 1 and is_blocking:
                wait = (2 ** attempt) * 3 + random.uniform(1.0, 3.0)
                time.sleep(wait)
                continue
            return None, None, None, err_msg


# ─────────────────────────────────────────
# 통합 수집
# ─────────────────────────────────────────
def collect_transcripts(urls: list, api_key: str, lang_pref: str = "한국어", callback=None):
    """
    URL 목록 → 메타데이터 + 스크립트 수집
    출력 컬럼: 채널명, 구독자수, 채널평균조회수, 썸네일, 썸네일URL,
               제목, 조회수, 업로드일자, URL, 스크립트, 핵심키워드(태그)
    """
    total = len(urls)

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

        meta  = metadata.get(vid, {})
        cid   = meta.get("channel_id", "")
        ch    = ch_stats.get(cid, {"subscribers": 0, "avg_views": 0})
        tags  = meta.get("tags", [])
        keywords = ", ".join(tags[:10]) if tags else ""

        text, lang, is_auto, err = get_transcript(vid, lang_pref)
        # 블로킹 방지: 요청 간 랜덤 딜레이 (1.5~3.5초)
        time.sleep(random.uniform(1.5, 3.5))

        results.append({
            "채널명":         meta.get("channel_name", ""),
            "구독자수":       ch["subscribers"],
            "채널평균조회수": ch["avg_views"],
            "썸네일":         build_thumbnail_formula(vid),
            "썸네일URL":      f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "제목":           meta.get("title", vid),
            "조회수":         meta.get("views", 0),
            "업로드일자":     meta.get("upload_date", ""),
            "URL":            url,
            "스크립트":       text or "",
            "핵심키워드(태그)": keywords,
            "_오류":          err or "",
        })

    if callback:
        callback(1.0, "완료")
    return results
