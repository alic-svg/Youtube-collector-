"""
YouTube 영상 수집 핵심 로직
- 키워드 검색 기반 수집
- 채널 URL 기반 수집
- 숏폼 판별 (60초 이하 OR #shorts 태그)
"""

import re
import time
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote

BASE_URL = "https://www.googleapis.com/youtube/v3"


# ─────────────────────────────────────────
# API 공통
# ─────────────────────────────────────────
def api_get(endpoint, params, api_key):
    params["key"] = api_key
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        d = r.json()
        if "error" in d:
            return None, d["error"].get("message", "알 수 없는 오류")
        return d, None
    except Exception as e:
        return None, str(e)


def validate_api_key(api_key):
    d, err = api_get("videos", {"part": "snippet", "id": "dQw4w9WgXcQ"}, api_key)
    if d is None:
        return False, err
    return True, "유효한 API 키입니다."


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def parse_duration(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def is_short(duration_sec, title, tags):
    """숏폼 탭 업로드 기준: 60초 이하 OR #shorts 태그"""
    if duration_sec <= 60:
        return True
    combined = (title + " " + " ".join(tags or [])).lower()
    if "#shorts" in combined or re.search(r"#short\b", combined):
        return True
    return False


def parse_channel_urls(urls):
    """URL 목록에서 @핸들 추출"""
    handles = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        parsed = urlparse(url)
        path = unquote(parsed.path)
        if "/@" in path:
            m = re.search(r"/@([^/\s?]+)", path)
            if m:
                handles.append(m.group(1))
    return handles


def build_thumbnail_formula(video_id):
    return f'=IFERROR(IMAGE("https://i.ytimg.com/vi/{video_id}/mqdefault.jpg","",0),"")'


# ─────────────────────────────────────────
# YouTube API 요청
# ─────────────────────────────────────────
def search_videos(keyword, pub_after, api_key, max_results=50,
                  region_code="KR", lang_code="ko", order="relevance"):
    ids, page_token = [], None
    while len(ids) < max_results:
        params = {
            "part": "id", "q": keyword, "type": "video",
            "maxResults": min(50, max_results - len(ids)),
            "order": order,
            "publishedAfter": pub_after,
        }
        if region_code:
            params["regionCode"] = region_code
        if lang_code:
            params["relevanceLanguage"] = lang_code
        if page_token:
            params["pageToken"] = page_token

        d, _ = api_get("search", params, api_key)
        if not d:
            break
        for item in d.get("items", []):
            v = item["id"].get("videoId")
            if v:
                ids.append(v)
        page_token = d.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.3)
    return ids


def get_video_details(video_ids, api_key, callback=None):
    results = {}
    total = len(video_ids)
    for i in range(0, total, 50):
        batch = video_ids[i: i + 50]
        d, _ = api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
            api_key,
        )
        if d:
            for item in d.get("items", []):
                vid = item["id"]
                stats = item.get("statistics", {})
                snip = item["snippet"]
                results[vid] = {
                    "title":        snip["title"],
                    "tags":         snip.get("tags", []),
                    "channel_name": snip["channelTitle"],
                    "channel_id":   snip["channelId"],
                    "views":        int(stats.get("viewCount", 0)),
                    "upload_date":  snip["publishedAt"][:10],
                    "duration_sec": parse_duration(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                }
        if callback:
            callback(min(i + 50, total), total)
        time.sleep(0.2)
    return results


def get_channel_stats(channel_ids, api_key):
    results = {}
    ids = list(channel_ids)
    for i in range(0, len(ids), 50):
        batch = ids[i: i + 50]
        d, _ = api_get("channels", {"part": "statistics", "id": ",".join(batch)}, api_key)
        if d:
            for item in d.get("items", []):
                cid = item["id"]
                stats = item.get("statistics", {})
                vc = int(stats.get("videoCount", 1)) or 1
                results[cid] = {
                    "subscribers": int(stats.get("subscriberCount", 0)),
                    "avg_views":   round(int(stats.get("viewCount", 0)) / vc),
                }
        time.sleep(0.2)
    return results


def get_channel_info(handle, api_key):
    d, err = api_get(
        "channels",
        {"part": "id,snippet,statistics,contentDetails", "forHandle": handle},
        api_key,
    )
    if not d or not d.get("items"):
        return None, err
    item = d["items"][0]
    stats = item.get("statistics", {})
    vc = int(stats.get("videoCount", 1)) or 1
    return {
        "channel_id":   item["id"],
        "channel_name": item["snippet"]["title"],
        "uploads_pl":   item["contentDetails"]["relatedPlaylists"]["uploads"],
        "subscribers":  int(stats.get("subscriberCount", 0)),
        "avg_views":    round(int(stats.get("viewCount", 0)) / vc),
    }, None


def get_all_video_ids(uploads_pl, api_key):
    ids, page_token = [], None
    while True:
        params = {"part": "contentDetails", "playlistId": uploads_pl, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        d, _ = api_get("playlistItems", params, api_key)
        if not d:
            break
        for item in d.get("items", []):
            vid = item["contentDetails"].get("videoId")
            if vid:
                ids.append(vid)
        page_token = d.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.2)
    return ids


# ─────────────────────────────────────────
# 자동완성 조회 (API 키 불필요, 쿼터 소모 없음)
# ─────────────────────────────────────────
def get_autocomplete(keyword, lang="ko", region="KR"):
    """YouTube 검색 자동완성 키워드 조회"""
    try:
        r = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "ds": "yt", "q": keyword, "hl": lang, "gl": region},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = r.json()
        return data[1] if len(data) > 1 else []
    except Exception:
        return []


def get_autocomplete_bulk(keywords, lang="ko", region="KR"):
    """
    여러 키워드의 자동완성 결과 일괄 조회
    반환: [{"키워드": kw, "자동완성": [suggestion, ...]}, ...]
    """
    results = []
    for kw in keywords:
        suggestions = get_autocomplete(kw, lang, region)
        results.append({"키워드": kw, "자동완성": suggestions})
        time.sleep(0.2)
    return results


# ─────────────────────────────────────────
# 수집 메인 함수
# ─────────────────────────────────────────
def collect_combined(keywords, channel_urls, exclude_urls, min_views, days, api_key,
                     include_longform=True, include_shorts=False,
                     result_limit=None, region_code="KR", lang_code="ko",
                     top_n_rank=None, search_order="relevance",
                     callback=None):
    """
    키워드 검색 + 채널 수집 통합 함수
    - keywords:      키워드 목록 (없으면 스킵)
    - channel_urls:  수집할 채널 URL 목록 (없으면 스킵)
    - exclude_urls:  제외할 채널 URL 목록
    - top_n_rank:    키워드 검색 상위 N위 이내 영상만 포함 (None = 제한 없음)
    - search_order:  "relevance" | "viewCount"
    """
    pub_after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    all_ids = set()
    include_ch_stats = {}
    channel_video_map = {}
    # {video_id: (keyword, rank)} — 여러 키워드 중 최고 순위(낮은 숫자) 기록
    keyword_rank_map = {}

    total_steps = sum([bool(keywords), bool(channel_urls)])
    step = 0

    # ── 1. 키워드 검색 ──────────────────────
    if keywords:
        total_kw = len(keywords)
        for i, kw in enumerate(keywords):
            if callback:
                callback(step / max(total_steps, 1) * 0.3 + i / total_kw * 0.3,
                         "키워드 검색", f"'{kw}' 검색 중... ({i+1}/{total_kw})")
            ids = search_videos(kw, pub_after, api_key, 50, region_code, lang_code,
                                order=search_order)
            for rank, vid in enumerate(ids, 1):
                # 상위노출 필터
                if top_n_rank and rank > top_n_rank:
                    continue
                # 여러 키워드에 중복 시 순위 높은(숫자 낮은) 것 유지
                if vid not in keyword_rank_map or rank < keyword_rank_map[vid][1]:
                    keyword_rank_map[vid] = (kw, rank)
                all_ids.add(vid)
            time.sleep(0.4)
        step += 1
        if callback:
            callback(step / max(total_steps, 1) * 0.3,
                     "키워드 검색", f"완료 · {len(all_ids)}개 ID 수집")

    # ── 2. 채널 수집 ────────────────────────
    if channel_urls:
        handles = parse_channel_urls(channel_urls)
        channels = {}
        total_ch = len(handles)
        for i, handle in enumerate(handles):
            if callback:
                callback(step / max(total_steps, 1) * 0.3 + i / max(total_ch, 1) * 0.15,
                         "채널 정보 수집", f"@{handle} 수집 중... ({i+1}/{total_ch})")
            info, err = get_channel_info(handle, api_key)
            if info:
                channels[info["channel_id"]] = info
            time.sleep(0.3)

        for i, (cid, info) in enumerate(channels.items()):
            if callback:
                callback(step / max(total_steps, 1) * 0.3 + 0.15 + i / max(len(channels), 1) * 0.1,
                         "채널 영상 목록 수집", f"{info['channel_name']} 영상 목록 수집 중...")
            ids = get_all_video_ids(info["uploads_pl"], api_key)
            channel_video_map[cid] = ids
            all_ids.update(ids)
            include_ch_stats[cid] = {"subscribers": info["subscribers"], "avg_views": info["avg_views"]}
            time.sleep(0.3)
        step += 1

    # ── 3. 제외 채널 ID 확인 ─────────────────
    exclude_ids = set()
    if exclude_urls:
        exclude_handles = parse_channel_urls(exclude_urls)
        if callback:
            callback(0.55, "제외 채널 확인", f"{len(exclude_handles)}개 채널 ID 조회 중...")
        for handle in exclude_handles:
            info, _ = get_channel_info(handle, api_key)
            if info:
                exclude_ids.add(info["channel_id"])
            time.sleep(0.2)

    # ── 4. 영상 상세 정보 ────────────────────
    id_list = list(all_ids)
    if callback:
        callback(0.58, "영상 정보 수집", f"총 {len(id_list)}개 영상 정보 수집 중...")

    def detail_cb(done, total):
        if callback:
            callback(0.58 + done / max(total, 1) * 0.25,
                     "영상 정보 수집", f"({done}/{total})")

    details = get_video_details(id_list, api_key, callback=detail_cb)

    # ── 5. 필터링 ────────────────────────────
    if callback:
        callback(0.84, "필터링", "조건 적용 중...")

    ch_video_ids = {v for ids in channel_video_map.values() for v in ids}
    passed = []
    for vid, d in details.items():
        if d["channel_id"] in exclude_ids:
            continue
        if vid in ch_video_ids and d["upload_date"] < pub_after[:10]:
            continue
        short = is_short(d["duration_sec"], d["title"], d["tags"])
        if short and not include_shorts:
            continue
        if not short and not include_longform:
            continue
        if d["views"] < min_views:
            continue
        kw, rank = keyword_rank_map.get(vid, ("", 0))
        passed.append({"video_id": vid, "is_short": short,
                       "검색키워드": kw, "노출순위": rank, **d})

    # ── 6. 채널 통계 ─────────────────────────
    kw_channel_ids = {d["channel_id"] for d in passed} - set(include_ch_stats.keys())
    ch_stats = get_channel_stats(kw_channel_ids, api_key) if kw_channel_ids else {}
    ch_stats.update(include_ch_stats)

    passed.sort(key=lambda x: x["views"], reverse=True)
    if result_limit:
        passed = passed[:result_limit]

    results = []
    for d in passed:
        cid = d["channel_id"]
        ch = ch_stats.get(cid, {"subscribers": 0, "avg_views": 0})
        vid = d["video_id"]
        results.append({
            "검색키워드":    d["검색키워드"],
            "노출순위":      d["노출순위"] if d["노출순위"] else "-",
            "채널명":        d["channel_name"],
            "구독자수":      ch["subscribers"],
            "채널평균조회수": ch["avg_views"],
            "썸네일":        build_thumbnail_formula(vid),
            "썸네일URL":     f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "구분":          "숏폼" if d["is_short"] else "롱폼",
            "제목":          d["title"],
            "조회수":        d["views"],
            "업로드일자":    d["upload_date"],
            "URL":           f"https://www.youtube.com/watch?v={vid}",
        })

    if callback:
        callback(1.0, "완료", f"{len(results)}개 영상 수집 완료")
    return results


def collect_by_keywords(keywords, min_views, days, api_key,
                        include_longform=True, include_shorts=False,
                        result_limit=None, region_code="KR", lang_code="ko",
                        callback=None):
    """
    include_longform: 롱폼(60초 초과 + #shorts 미포함) 포함 여부
    include_shorts:   숏폼(60초 이하 OR #shorts 포함) 포함 여부
    result_limit:     최종 결과 상한 (None = 제한 없음)
    검색은 항상 키워드당 50개로 수행 — 필터 후 줄어들기 때문
    """
    pub_after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    total_kw = len(keywords)

    # 1. 키워드 검색 (항상 50개)
    all_ids, keyword_map = set(), {}
    for i, kw in enumerate(keywords):
        if callback:
            callback(i / total_kw * 0.33, "1/3 키워드 검색", f"'{kw}' 검색 중... ({i+1}/{total_kw})")
        ids = search_videos(kw, pub_after, api_key, 50, region_code, lang_code)
        for v in ids:
            keyword_map.setdefault(v, kw)
            all_ids.add(v)
        time.sleep(0.4)

    if callback:
        callback(0.33, "1/3 키워드 검색", f"완료 · {len(all_ids)}개 영상 ID 수집")

    # 2. 상세 정보
    id_list = list(all_ids)

    def detail_cb(done, total):
        if callback:
            callback(0.33 + done / total * 0.33, "2/3 영상 정보 수집",
                     f"영상 정보 수집 중... ({done}/{total})")

    details = get_video_details(id_list, api_key, callback=detail_cb)
    if callback:
        callback(0.66, "2/3 영상 정보 수집", f"완료 · {len(details)}개")

    # 3. 필터링 + 채널 통계
    if callback:
        callback(0.75, "3/3 필터링 및 채널 통계", "필터 적용 중...")

    passed = []
    for vid, d in details.items():
        short = is_short(d["duration_sec"], d["title"], d["tags"])
        if short and not include_shorts:
            continue
        if not short and not include_longform:
            continue
        if d["views"] < min_views:
            continue
        passed.append({"video_id": vid, "is_short": short, **d})

    channel_ids = {d["channel_id"] for d in passed}
    ch_stats = get_channel_stats(channel_ids, api_key)

    passed.sort(key=lambda x: x["views"], reverse=True)
    if result_limit:
        passed = passed[:result_limit]

    results = []
    for d in passed:
        cid = d["channel_id"]
        ch = ch_stats.get(cid, {"subscribers": 0, "avg_views": 0})
        vid = d["video_id"]
        results.append({
            "채널명":        d["channel_name"],
            "구독자수":      ch["subscribers"],
            "채널평균조회수": ch["avg_views"],
            "썸네일":        build_thumbnail_formula(vid),
            "썸네일URL":     f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "구분":          "숏폼" if d["is_short"] else "롱폼",
            "제목":          d["title"],
            "조회수":        d["views"],
            "업로드일자":    d["upload_date"],
            "URL":           f"https://www.youtube.com/watch?v={vid}",
        })

    if callback:
        callback(1.0, "완료", f"{len(results)}개 영상 수집 완료")
    return results


def collect_by_channels(channel_urls, min_views, api_key,
                        include_longform=True, include_shorts=False,
                        result_limit=None, callback=None):
    """
    callback(progress: float 0~1, step: str, message: str)
    """
    handles = parse_channel_urls(channel_urls)
    if not handles:
        return []

    total_ch = len(handles)

    # 1. 채널 정보
    channels = {}
    errors = []
    for i, handle in enumerate(handles):
        if callback:
            callback(i / total_ch * 0.2, "1/4 채널 정보 수집",
                     f"@{handle} 정보 수집 중... ({i+1}/{total_ch})")
        info, err = get_channel_info(handle, api_key)
        if info:
            channels[info["channel_id"]] = info
        else:
            errors.append(f"@{handle}: {err}")
        time.sleep(0.3)

    if callback:
        callback(0.2, "1/4 채널 정보 수집", f"완료 · {len(channels)}개 채널 (실패 {len(errors)}개)")

    # 2. 영상 ID 수집
    channel_video_map = {}
    for i, (cid, info) in enumerate(channels.items()):
        if callback:
            callback(0.2 + i / total_ch * 0.2, "2/4 영상 ID 수집",
                     f"{info['channel_name']} 영상 목록 수집 중...")
        ids = get_all_video_ids(info["uploads_pl"], api_key)
        channel_video_map[cid] = ids
        time.sleep(0.3)

    all_video_ids = list({v for ids in channel_video_map.values() for v in ids})
    if callback:
        callback(0.4, "2/4 영상 ID 수집", f"완료 · 총 {len(all_video_ids)}개 영상")

    # 3. 상세 정보
    def detail_cb(done, total):
        if callback:
            callback(0.4 + done / total * 0.35, "3/4 영상 정보 수집",
                     f"영상 정보 수집 중... ({done}/{total})")

    details = get_video_details(all_video_ids, api_key, callback=detail_cb)
    if callback:
        callback(0.75, "3/4 영상 정보 수집", f"완료 · {len(details)}개")

    # 4. 필터링
    if callback:
        callback(0.85, "4/4 필터링 및 정렬", "필터 적용 중...")

    passed = []
    for cid, info in channels.items():
        for vid in channel_video_map.get(cid, []):
            d = details.get(vid)
            if not d:
                continue
            short = is_short(d["duration_sec"], d["title"], d["tags"])
            if short and not include_shorts:
                continue
            if not short and not include_longform:
                continue
            if d["views"] < min_views:
                continue
            passed.append({
                "video_id":     vid,
                "channel_name": info["channel_name"],
                "subscribers":  info["subscribers"],
                "avg_views":    info["avg_views"],
                "is_short":     short,
                **d,
            })

    passed.sort(key=lambda x: x["views"], reverse=True)
    if result_limit:
        passed = passed[:result_limit]

    results = []
    for d in passed:
        vid = d["video_id"]
        results.append({
            "채널명":        d["channel_name"],
            "구독자수":      d["subscribers"],
            "채널평균조회수": d["avg_views"],
            "썸네일":        build_thumbnail_formula(vid),
            "썸네일URL":     f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "구분":          "숏폼" if d["is_short"] else "롱폼",
            "제목":          d["title"],
            "조회수":        d["views"],
            "업로드일자":    d["upload_date"],
            "URL":           f"https://www.youtube.com/watch?v={vid}",
        })

    if callback:
        callback(1.0, "완료", f"{len(results)}개 영상 수집 완료")
    return results, errors
