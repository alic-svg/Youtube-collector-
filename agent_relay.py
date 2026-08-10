"""
로컬 에이전트 릴레이 (Upstash Redis REST API)
- 자막 수집 작업을 Redis 큐(yt_jobs)에 넣으면 agent/main.py(집 PC, 주거용 IP)가
  가져가 처리하고 결과를 yt_result:{job_id}에 저장한다.
- 여기서는 그 큐에 작업을 넣고 결과를 폴링하는 웹앱 쪽 클라이언트만 다룬다.
"""

import json
import time
import uuid

import requests

HEARTBEAT_KEY = "yt_agent_heartbeat"
JOB_QUEUE_KEY = "yt_jobs"
RESULT_PREFIX = "yt_result:"


def _redis_cmd(url: str, token: str, *args):
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=list(args),
            timeout=10,
        )
        return r.json().get("result")
    except Exception:
        return None


def is_configured(cfg: dict) -> bool:
    return bool(cfg and cfg.get("url") and cfg.get("token"))


def is_agent_online(cfg: dict) -> bool:
    """에이전트 하트비트(TTL 30초)가 살아있는지 확인."""
    if not is_configured(cfg):
        return False
    return _redis_cmd(cfg["url"], cfg["token"], "GET", HEARTBEAT_KEY) is not None


def submit_video_job(cfg: dict, video_id: str, lang_pref: str) -> str:
    """영상 1개짜리 작업을 큐에 넣고 job_id 반환."""
    job_id = uuid.uuid4().hex
    payload = json.dumps({
        "job_id": job_id,
        "video_ids": [video_id],
        "lang_pref": lang_pref,
    }, ensure_ascii=False)
    _redis_cmd(cfg["url"], cfg["token"], "RPUSH", JOB_QUEUE_KEY, payload)
    return job_id


def poll_video_result(cfg: dict, job_id: str, video_id: str,
                       timeout: float = 25.0, interval: float = 1.5):
    """
    작업 결과를 폴링. 반환: {"text","lang","is_auto","error"} 또는 None(타임아웃/오류).
    """
    key = RESULT_PREFIX + job_id
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = _redis_cmd(cfg["url"], cfg["token"], "GET", key)
        if raw:
            try:
                data = json.loads(raw)
                return data.get("transcripts", {}).get(video_id)
            except Exception:
                return None
        time.sleep(interval)
    return None
