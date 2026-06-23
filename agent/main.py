"""
YouTube 스크립트 수집 로컬 에이전트
- Upstash Redis에서 작업 수신 (LPOP yt_jobs)
- youtube-transcript-api로 자막 수집 (로컬/가정용 IP)
- 결과를 Upstash Redis에 반환 (SET yt_result:{job_id})
"""

import json
import sys
import time
import random
import requests
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("[오류] youtube-transcript-api 패키지가 없습니다.")
    print("       pip install youtube-transcript-api 를 실행해 주세요.")
    input("엔터를 누르면 종료됩니다.")
    sys.exit(1)

# exe로 패키징됐을 때는 실행파일 옆에, 개발 시에는 스크립트 옆에 config 저장
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_FILE = BASE_DIR / "config.json"

LANG_PRIORITY = {
    "한국어": ["ko", "ko-KR", "en", "en-US"],
    "일본어": ["ja", "en", "ko"],
    "영어":   ["en", "en-US", "ko", "ja"],
    "자동감지": None,
}

COOKIES_FILE = BASE_DIR / "cookies.json"

POLL_INTERVAL   = 3   # 작업 폴링 간격 (초)
HEARTBEAT_TTL   = 30  # Redis 하트비트 만료 (초)
HEARTBEAT_EVERY = 10  # 하트비트 갱신 주기 (초)
RESULT_TTL      = 3600  # 결과 보관 시간 (초)


# ─────────────────────────────────────────
# 설정 관리
# ─────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def setup_config():
    print()
    print("=" * 55)
    print("   YouTube 스크립트 수집 에이전트 — 초기 설정")
    print("=" * 55)
    print()
    print("  Upstash Redis 연결 정보를 입력해 주세요.")
    print("  ① upstash.com 접속 → 무료 가입")
    print("  ② 새 Redis 데이터베이스 생성")
    print("  ③ 'REST API' 탭에서 아래 두 값 복사")
    print()
    url   = input("  Upstash REST URL   : ").strip().rstrip("/")
    token = input("  Upstash REST TOKEN : ").strip()
    print()
    cfg = {"upstash_url": url, "upstash_token": token}
    save_config(cfg)
    print("  ✅ config.json 에 저장됐습니다.")
    return cfg


# ─────────────────────────────────────────
# YouTube 쿠키 세션 로드
# ─────────────────────────────────────────
def build_http_client() -> requests.Session:
    """cookies.json을 읽어 requests.Session을 반환. 파일 없으면 빈 세션."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    })
    if not COOKIES_FILE.exists():
        print("  [경고] cookies.json 없음 — 쿠키 없이 시도합니다.")
        return session
    try:
        with open(COOKIES_FILE, encoding="utf-8") as f:
            cookie_list = json.load(f)
        for c in cookie_list:
            session.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain", ".youtube.com"),
                path=c.get("path", "/"),
            )
        print(f"  ✅ 쿠키 {len(cookie_list)}개 로드됨")
    except Exception as e:
        print(f"  [경고] 쿠키 로드 실패: {e}")
    return session


# ─────────────────────────────────────────
# Upstash Redis REST API
# ─────────────────────────────────────────
def redis_cmd(cfg, *args):
    """Redis 명령 실행. 실패 시 None 반환."""
    try:
        r = requests.post(
            cfg["upstash_url"],
            headers={
                "Authorization": f"Bearer {cfg['upstash_token']}",
                "Content-Type": "application/json",
            },
            json=list(args),
            timeout=10,
        )
        return r.json().get("result")
    except Exception as e:
        print(f"  [Redis 오류] {e}")
        return None


def redis_lpop(cfg, key):
    return redis_cmd(cfg, "LPOP", key)


def redis_set(cfg, key, value_str, ex=None):
    if ex:
        redis_cmd(cfg, "SET", key, value_str, "EX", str(ex))
    else:
        redis_cmd(cfg, "SET", key, value_str)


# ─────────────────────────────────────────
# 자막 수집
# ─────────────────────────────────────────
def fetch_transcript(video_id: str, lang_pref: str = "한국어", http_client: requests.Session = None) -> dict:
    """
    반환: {"text": str, "lang": str, "is_auto": bool, "error": str|None}
    """
    try:
        api = YouTubeTranscriptApi(http_client=http_client)
        langs = LANG_PRIORITY.get(lang_pref)
        tl = api.list(video_id)
        transcripts = list(tl)

        chosen   = None
        lang_used = ""
        is_auto   = False

        if langs:
            # 수동 자막 우선
            for lang in langs:
                for t in transcripts:
                    if t.language_code.startswith(lang) and not t.is_generated:
                        chosen, lang_used, is_auto = t, t.language_code, False
                        break
                if chosen:
                    break
            # 없으면 자동생성
            if not chosen:
                for lang in langs:
                    for t in transcripts:
                        if t.language_code.startswith(lang) and t.is_generated:
                            chosen, lang_used, is_auto = t, t.language_code, True
                            break
                    if chosen:
                        break
        else:
            if transcripts:
                chosen   = transcripts[0]
                lang_used = chosen.language_code
                is_auto   = chosen.is_generated

        if not chosen:
            return {"text": "", "lang": "", "is_auto": False, "error": "자막 없음"}

        segments  = chosen.fetch()
        full_text = " ".join(s.text.strip() for s in segments if s.text.strip())
        return {"text": full_text, "lang": lang_used, "is_auto": is_auto, "error": None}

    except Exception as e:
        return {"text": "", "lang": "", "is_auto": False, "error": str(e)}


# ─────────────────────────────────────────
# 작업 처리
# ─────────────────────────────────────────
def process_job(cfg, job: dict, http_client: requests.Session = None):
    job_id    = job.get("job_id", "unknown")
    video_ids = job.get("video_ids", [])
    lang_pref = job.get("lang_pref", "한국어")
    total     = len(video_ids)

    print(f"\n  ▶ 작업 시작  job_id={job_id}  영상 {total}개")

    transcripts = {}
    for i, vid in enumerate(video_ids):
        print(f"    [{i+1}/{total}] {vid} ...", end=" ", flush=True)
        result = fetch_transcript(vid, lang_pref, http_client)
        transcripts[vid] = result

        if result["error"]:
            print(f"❌ {result['error'][:60]}")
        else:
            chars = len(result["text"])
            print(f"✅ {result['lang']} ({chars}자)")

        # 영상 사이 딜레이 (마지막 영상 제외)
        if i < total - 1:
            time.sleep(random.uniform(2.0, 4.0))

    # 결과 Redis에 저장
    result_payload = json.dumps(
        {"job_id": job_id, "status": "done", "transcripts": transcripts},
        ensure_ascii=False,
    )
    redis_set(cfg, f"yt_result:{job_id}", result_payload, ex=RESULT_TTL)
    print(f"  ✅ 작업 완료 → yt_result:{job_id}")


# ─────────────────────────────────────────
# 메인 루프
# ─────────────────────────────────────────
def main():
    print()
    print("=" * 55)
    print("   YouTube 스크립트 수집 에이전트  v1.0")
    print("=" * 55)

    cfg = load_config()
    if not cfg:
        cfg = setup_config()

    # 연결 테스트
    print(f"\n  Upstash: {cfg['upstash_url'][:50]}...")
    test = redis_cmd(cfg, "PING")
    if test != "PONG":
        print("  [오류] Upstash Redis 연결에 실패했습니다. URL/TOKEN을 확인해 주세요.")
        print(f"         config.json 위치: {CONFIG_FILE}")
        input("  엔터를 누르면 종료됩니다.")
        sys.exit(1)

    print("  ✅ Redis 연결 성공")

    http_client = build_http_client()

    print("  📡 작업 대기 중...  (종료: Ctrl+C)\n")

    last_heartbeat = 0.0

    while True:
        try:
            now = time.time()

            # 하트비트 갱신
            if now - last_heartbeat >= HEARTBEAT_EVERY:
                redis_set(cfg, "yt_agent_heartbeat", str(int(now)), ex=HEARTBEAT_TTL)
                last_heartbeat = now

            # 작업 확인
            raw = redis_lpop(cfg, "yt_jobs")
            if raw:
                try:
                    job = json.loads(raw)
                    process_job(cfg, job, http_client)
                except json.JSONDecodeError:
                    print(f"  [경고] 잘못된 작업 데이터: {raw[:80]}")
                except Exception as e:
                    print(f"  [처리 오류] {e}")
            else:
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n  에이전트를 종료합니다.")
            break
        except Exception as e:
            print(f"  [예외] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
