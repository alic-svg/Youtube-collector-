"""
YouTube 영상 수집기 - 메인 페이지 콘텐츠
"""

import csv
import io
import json
import os
import uuid
import time
from datetime import datetime, timedelta, date

import requests
import pandas as pd
import streamlit as st

from collector import collect_combined, get_autocomplete_bulk, QuotaExceededError, get_keyword_volumes
from transcript import extract_video_id, get_video_metadata, get_channel_stats, build_thumbnail_formula

# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def man_to_views(man_value: float) -> int:
    return int(man_value * 10_000)


# ─────────────────────────────────────────
# Upstash Redis 헬퍼 (로컬 에이전트 연동)
# ─────────────────────────────────────────
def _upstash_cfg():
    """Secrets에서 Upstash 설정 읽기. 없으면 None."""
    try:
        u = st.secrets.get("upstash", {})
        url   = u.get("rest_url", "").rstrip("/")
        token = u.get("rest_token", "")
        if url and token:
            return {"url": url, "token": token}
    except Exception:
        pass
    return None

def _redis(cfg, *args):
    """Redis 명령 실행. 실패 시 None."""
    try:
        r = requests.post(
            cfg["url"],
            headers={"Authorization": f"Bearer {cfg['token']}",
                     "Content-Type": "application/json"},
            json=list(args),
            timeout=10,
        )
        return r.json().get("result")
    except Exception:
        return None

def _agent_online(cfg) -> bool:
    """에이전트 하트비트 확인 (30초 이내 갱신 여부)."""
    val = _redis(cfg, "GET", "yt_agent_heartbeat")
    if not val:
        return False
    try:
        return (time.time() - int(val)) <= 30
    except Exception:
        return False

def views_to_man(views: int) -> str:
    v = views / 10_000
    return f"{v:.1f}만" if v != int(v) else f"{int(v)}만"

PERIOD_PRESETS = {
    "최근 1개월":  30,
    "최근 3개월":  90,
    "최근 6개월":  180,
    "최근 1년":    365,
    "최근 2년":    730,
    "직접 설정":   -1,
}

def period_selector(key_prefix: str):
    sel = st.selectbox(
        "수집 기간",
        list(PERIOD_PRESETS.keys()),
        index=4,
        key=f"{key_prefix}_period_sel",
    )
    if sel == "직접 설정":
        today = date.today()
        default_start = today - timedelta(days=730)
        date_range = st.date_input(
            "시작일 ~ 종료일",
            value=(default_start, today),
            max_value=today,
            key=f"{key_prefix}_date_range",
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            return max((date_range[1] - date_range[0]).days, 1)
        return 730
    return PERIOD_PRESETS[sel]

# ─────────────────────────────────────────
# 메인 헤더
# ─────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:0.2rem;">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="44" height="44">
    <path fill="#FF0000" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
  </svg>
  <h1 style="margin:0;padding:0;line-height:1.2;">YouTube 영상 수집기</h1>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🔍 수집", "💡 자동완성 키워드", "📝 스크립트 수집"])

# ─────────────────────────────────────────
# 탭 1 - 통합 수집
# ─────────────────────────────────────────
with tab1:
    if not st.session_state.api_key:
        st.warning("👈 왼쪽 사이드바에서 YouTube API 키를 먼저 입력하고 저장해 주세요.")

    st.caption(
        "키워드 검색과 채널 수집을 동시에 사용할 수 있습니다. "
        "키워드만, 채널만, 또는 둘 다 입력해도 동작합니다. "
        "**출력 항목:** 검색키워드 · 노출순위 · 구분(롱폼/숏폼) · 채널명 · 구독자수 · "
        "채널평균조회수 · 썸네일 · 제목 · 조회수 · 업로드일자 · URL"
    )

    col_left, col_right = st.columns([5, 4])

    # ── 왼쪽: 입력 ──────────────────────────
    with col_left:
        keywords_input = st.text_area(
            "**🔑 키워드** (줄바꿈으로 구분)",
            placeholder="인테리어\n셀프인테리어\n홈인테리어",
            height=270,
            key="kw_input",
        )
        channel_include_input = st.text_area(
            "**📺 수집할 채널 URL** (줄바꿈으로 구분 · 비우면 전체 채널 검색)",
            placeholder="https://www.youtube.com/@channelA\nhttps://www.youtube.com/@channelB",
            height=130,
            key="ch_include_input",
        )
        channel_exclude_input = st.text_area(
            "**🚫 제외할 채널 URL** (줄바꿈으로 구분)",
            placeholder="https://www.youtube.com/@excludeThis",
            height=90,
            key="ch_exclude_input",
        )

    # ── 오른쪽: 수집 조건 ────────────────────
    with col_right:
        # 조회수 필터
        r1, r2 = st.columns([1, 3])
        use_min_views = r1.checkbox("최소 조회수", value=True, key="use_min_views")
        if use_min_views:
            min_views_man = r2.number_input(
                "만", min_value=0.1, value=10.0, step=1.0, format="%.1f",
                key="col_min_views_man", label_visibility="collapsed",
            )
            min_views = man_to_views(min_views_man)
            r2.caption(f"{min_views:,}회 이상")
        else:
            r2.caption("제한 없음")
            min_views = 0

        # 수집 기간 필터
        p1, p2 = st.columns([1, 3])
        use_period = p1.checkbox("수집 기간", value=True, key="use_period")
        if use_period:
            with p2:
                days = period_selector("col")
        else:
            p2.caption("전체 기간")
            days = 36500  # 100년 = 사실상 전체

        # 영상 형태
        st.markdown("<small><b>영상 형태</b></small>", unsafe_allow_html=True)
        fc1, fc2 = st.columns(2)
        inc_longform = fc1.checkbox("롱폼", value=True, key="col_longform")
        inc_shorts   = fc2.checkbox("숏폼", value=False, key="col_shorts")
        if not inc_longform and not inc_shorts:
            st.warning("하나 이상 선택하세요.")

        # 최대 결과 수
        lim1, lim2 = st.columns([1, 3])
        use_limit = lim1.checkbox("최대 결과 수", value=True, key="use_limit")
        if use_limit:
            result_limit = lim2.number_input(
                "개", min_value=10, max_value=500, value=100, step=10,
                key="col_limit", label_visibility="collapsed",
            )
        else:
            lim2.caption("제한 없음")
            result_limit = None

        # 상위노출 필터
        tn1, tn2 = st.columns([1, 3])
        use_top_n = tn1.checkbox("상위노출 필터", value=False, key="use_top_n")
        if use_top_n:
            top_n_val = tn2.number_input(
                "위까지", min_value=1, max_value=50, value=20, step=1,
                key="col_top_n", label_visibility="collapsed",
                help="키워드 검색 상위 N위 이내 영상만 포함",
            )
            tn2.caption(f"상위 {top_n_val}위 이내만")
        else:
            tn2.caption("제한 없음")
            top_n_val = None

        # 검색 지역
        region = st.selectbox(
            "검색 지역 / 언어",
            ["🇰🇷 한국 (KR / ko)", "🇯🇵 일본 (JP / ja)", "🌐 전체"],
            key="col_region",
        )

        # 정렬 기준
        sort_by = st.radio(
            "정렬 기준",
            ["조회수 기준", "상위노출 기준"],
            horizontal=True,
            key="col_sort_by",
        )

    if st.button("🚀 수집 시작", key="btn_collect", use_container_width=True, type="primary"):
        keywords  = [k.strip() for k in keywords_input.strip().splitlines() if k.strip()]
        ch_includes = [u.strip() for u in channel_include_input.strip().splitlines() if u.strip()]
        ch_excludes = [u.strip() for u in channel_exclude_input.strip().splitlines() if u.strip()]

        if not st.session_state.api_key:
            st.error("YouTube API 키를 먼저 입력하고 저장해 주세요.")
        elif not keywords and not ch_includes:
            st.error("키워드 또는 수집할 채널 URL 중 하나 이상 입력해 주세요.")
        elif not inc_longform and not inc_shorts:
            st.error("롱폼/숏폼 중 하나 이상 선택해 주세요.")
        else:
            region_map = {
                "🇰🇷 한국 (KR / ko)": ("KR", "ko"),
                "🇯🇵 일본 (JP / ja)": ("JP", "ja"),
                "🌐 전체":            (None, None),
            }
            rc, lc = region_map[region]

            parts = []
            if keywords:   parts.append(f"키워드 {len(keywords)}개")
            if ch_includes: parts.append(f"채널 {len(ch_includes)}개")
            if ch_excludes: parts.append(f"제외 {len(ch_excludes)}개")
            form_label = "롱폼+숏폼" if inc_longform and inc_shorts else ("롱폼만" if inc_longform else "숏폼만")
            search_order = "relevance" if sort_by == "상위노출 기준" else "viewCount"
            top_n = int(top_n_val) if use_top_n and keywords else None

            filter_parts = [form_label]
            if use_min_views: filter_parts.append(f"최소 {views_to_man(min_views)}")
            if use_period:    filter_parts.append(f"{days}일")
            if use_limit:     filter_parts.append(f"상위 {result_limit}개")
            if top_n:         filter_parts.append(f"노출 {top_n}위내")
            st.info(f"**{' · '.join(parts)}** · {' · '.join(filter_parts)}")

            prog = st.progress(0)
            step_text = st.empty()
            msg_text  = st.empty()

            def cb(progress, step, message):
                prog.progress(min(progress, 1.0))
                step_text.markdown(f"**{step}**")
                msg_text.text(message)

            try:
                results = collect_combined(
                    keywords=keywords,
                    channel_urls=ch_includes,
                    exclude_urls=ch_excludes,
                    min_views=min_views,
                    days=days,
                    api_key=st.session_state.api_key,
                    include_longform=inc_longform,
                    include_shorts=inc_shorts,
                    result_limit=result_limit,
                    region_code=rc,
                    lang_code=lc,
                    top_n_rank=top_n,
                    search_order=search_order,
                    callback=cb,
                )
                st.session_state.results = results
                st.session_state.result_label = f"수집 결과 ({' · '.join(parts)})"
                prog.progress(1.0)
                step_text.markdown("**✅ 수집 완료**")
                if len(results) == 0:
                    msg_text.text("수집된 영상이 없습니다. 조건(최소 조회수, 기간 등)을 완화해 보세요.")
                else:
                    msg_text.text(f"총 {len(results)}개 영상이 수집됐습니다.")
            except QuotaExceededError as e:
                prog.empty()
                step_text.empty()
                msg_text.empty()
                st.error(f"⚠️ API 쿼터 초과\n\n{e}")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# ─────────────────────────────────────────
# 탭 2 - 자동완성 키워드
# ─────────────────────────────────────────
with tab2:
    st.subheader("YouTube 자동완성 키워드 조회")
    st.caption(
        "API 키 불필요 · 쿼터 소모 없음. "
        "YouTube 검색창에서 실제로 자동완성되는 키워드를 대량으로 조회합니다. "
        "콘텐츠 기획 시 연관 키워드 발굴에 활용하세요. "
        "**출력 항목:** 입력 키워드 · 자동완성 키워드 · YouTube 검색관심도(선택)"
    )

    col_left, col_right = st.columns([2, 1])

    with col_left:
        ac_input = st.text_area(
            "**🔑 키워드** (줄바꿈으로 구분)",
            placeholder="인테리어\n화이트우드\n셀프인테리어\n홈스타일링",
            height=180,
            key="ac_input",
        )

    with col_right:
        st.markdown("**🔧 조회 설정**")
        ac_region = st.selectbox(
            "검색 지역 / 언어",
            ["🇰🇷 한국 (KR / ko)", "🇯🇵 일본 (JP / ja)", "🌐 영어 (US / en)"],
            key="ac_region",
        )
        show_volume = st.checkbox(
            "📊 YouTube 검색량 조회",
            value=False,
            key="ac_show_volume",
            help=(
                "Google Trends 기반 YouTube 검색관심도(0-100 상대값)를 함께 조회합니다.\n"
                "키워드 수에 따라 추가 시간이 소요됩니다."
            ),
        )

    if st.button("🔎 자동완성 조회", key="btn_ac", use_container_width=True, type="primary"):
        keywords = [k.strip() for k in ac_input.strip().splitlines() if k.strip()]
        if not keywords:
            st.error("키워드를 한 줄에 하나씩 입력해 주세요.")
        else:
            region_map = {
                "🇰🇷 한국 (KR / ko)": ("KR", "ko"),
                "🇯🇵 일본 (JP / ja)": ("JP", "ja"),
                "🌐 영어 (US / en)":  ("US", "en"),
            }
            region_code, lang_code = region_map[ac_region]
            with st.spinner(f"{len(keywords)}개 키워드 자동완성 조회 중..."):
                ac_results = get_autocomplete_bulk(keywords, lang=lang_code, region=region_code)

            volumes = {}
            if show_volume:
                all_suggestions = list(dict.fromkeys(
                    sug for item in ac_results for sug in item["자동완성"]
                ))
                if all_suggestions:
                    with st.spinner(
                        f"YouTube 검색량 조회 중... ({len(all_suggestions)}개 키워드 · "
                        f"약 {max(1, len(all_suggestions) // 5) * 2}초 소요)"
                    ):
                        volumes = get_keyword_volumes(all_suggestions, lang=lang_code, region=region_code)
                    if not volumes:
                        st.warning("검색량 데이터를 가져오지 못했습니다. (Google 요청 제한 — 잠시 후 재시도해 주세요.)")

            st.session_state.ac_results = ac_results
            st.session_state.ac_volumes = volumes
            # ac_show_volume 은 체크박스 위젯 키라 직접 쓸 수 없음
            # → 조회 시점의 값을 별도 키에 저장
            st.session_state._ac_vol_used = show_volume

    if "ac_results" in st.session_state and st.session_state.ac_results:
        ac_results = st.session_state.ac_results
        volumes    = st.session_state.get("ac_volumes", {})
        show_vol   = st.session_state.get("_ac_vol_used", False)

        st.divider()

        # ── 스프레드시트 형태 테이블 구성 ─────────
        all_rows = []
        for item in ac_results:
            kw          = item["키워드"]
            suggestions = item["자동완성"]
            for sug in suggestions:
                row = {"입력 키워드": kw, "자동완성 키워드": sug}
                if show_vol:
                    row["검색관심도 (0-100)"] = volumes.get(sug, "-")
                all_rows.append(row)

        total_kw  = len(ac_results)
        total_sug = len(all_rows)
        vol_note  = " · 검색관심도: Google Trends YouTube 상대값(0-100)" if show_vol else ""
        st.caption(f"총 **{total_kw}개** 입력 키워드 · **{total_sug}개** 자동완성 키워드{vol_note}")

        if all_rows:
            df = pd.DataFrame(all_rows)
            st.dataframe(df, use_container_width=True, hide_index=True, height=600)

            st.divider()
            csv_fields = ["입력 키워드", "자동완성 키워드"]
            if show_vol:
                csv_fields.append("검색관심도 (0-100)")
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(all_rows)
            csv_bytes = buf.getvalue().encode("utf-8-sig")
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="⬇️ CSV 다운로드",
                data=csv_bytes,
                file_name=f"자동완성키워드_{now_str}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("자동완성 결과가 없습니다.")

# ─────────────────────────────────────────
# 탭 3 - 스크립트 수집 (로컬 에이전트 연동)
# ─────────────────────────────────────────
with tab3:
    st.subheader("영상 스크립트 수집")
    st.caption(
        "API 키 불필요 · 쿼터 소모 없음. "
        "영상 URL을 입력하면 YouTube 자막(수동 자막 우선, 없으면 자동 생성 자막)을 텍스트로 추출합니다. "
        "자막이 비활성화된 영상은 수집 불가. "
        "**출력 항목:** 채널명 · 구독자수 · 채널평균조회수 · 썸네일 · 제목 · 조회수 · 업로드일자 · URL · 스크립트 · 핵심키워드(태그)"
    )

    # ── 사용 방법 + 에이전트 다운로드 ─────────
    with st.expander("📖 사용 방법 — 처음이라면 먼저 읽어주세요", expanded=False):
        st.markdown("스크립트 수집은 **로컬 에이전트 프로그램**이 필요합니다. YouTube가 서버 IP를 차단하기 때문에 개인 PC에서 직접 수집합니다.")
        st.markdown("**① 에이전트 설치파일 다운로드**")

        _zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent", "YT_Script_Agent_release.zip")
        if os.path.exists(_zip_path):
            with open(_zip_path, "rb") as _f:
                st.download_button(
                    label="⬇️ 에이전트 다운로드 (Windows)",
                    data=_f.read(),
                    file_name="YT_Script_Agent.zip",
                    mime="application/zip",
                    type="primary",
                )
        else:
            st.caption("설치파일이 아직 준비되지 않았습니다. 관리자에게 문의해 주세요.")

        st.markdown("""
**② 압축 해제 후 `YT_Script_Agent.exe` 실행**
> Windows 보안 경고 → **추가 정보** 클릭 → **실행** 클릭

**③ 터미널 창에 아래 메시지가 보이면 준비 완료**
```
Waiting for jobs... (Ctrl+C to stop)
```

**④ 에이전트 창을 닫지 않은 채로** 이 페이지에서 URL 입력 후 수집 시작

**⑤ 수집이 끝나면 결과가 자동으로 화면에 표시됩니다**

> 에이전트는 수집할 때만 켜두면 됩니다. 평소에는 닫아도 됩니다.
""")

    # ── 에이전트 상태 표시 ──────────────────
    upstash_cfg = _upstash_cfg()
    if not upstash_cfg:
        st.error("스크립트 수집 서비스에 연결할 수 없습니다. 관리자에게 문의해 주세요.")
    else:
        online = _agent_online(upstash_cfg)
        if online:
            st.success("🟢 로컬 에이전트 연결됨 — 수집 준비 완료")
        else:
            st.warning("🔴 로컬 에이전트 오프라인 — 에이전트를 먼저 실행해 주세요.")

    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        script_urls_input = st.text_area(
            "**🎬 영상 URL** (줄바꿈으로 구분)",
            placeholder=(
                "https://www.youtube.com/watch?v=abc123\n"
                "https://youtu.be/def456\n"
                "https://www.youtube.com/shorts/ghi789"
            ),
            height=220,
            key="script_urls",
        )

    with col_right:
        st.markdown("**🔧 수집 설정**")
        script_lang = st.selectbox(
            "자막 언어 우선순위",
            ["한국어", "일본어", "영어", "자동감지"],
            key="script_lang",
            help="선택한 언어의 자막이 없으면 다음 우선순위 언어로 자동 전환됩니다."
        )
        st.markdown("""
        <small>
        ℹ️ 자막이 없거나 비활성화된 영상은<br>
        오류 메시지와 함께 표시됩니다.<br><br>
        수동 자막 → 자동생성 자막 순으로 시도합니다.
        </small>
        """, unsafe_allow_html=True)

    # ── 수집 시작 버튼 ──────────────────────
    if st.button("📝 스크립트 수집 시작", key="btn_script",
                 use_container_width=True, type="primary",
                 disabled=(not upstash_cfg)):
        urls = [u.strip() for u in script_urls_input.strip().splitlines() if u.strip()]
        if not urls:
            st.error("영상 URL을 한 줄에 하나씩 입력해 주세요.")
        elif not _agent_online(upstash_cfg):
            st.error("로컬 에이전트가 실행 중이지 않습니다. 에이전트를 먼저 실행해 주세요.")
        else:
            # 영상 ID 추출
            url_id_map = {u: extract_video_id(u) for u in urls}
            valid_ids  = [vid for vid in url_id_map.values() if vid]

            # 메타데이터 수집 (클라우드에서 처리)
            with st.spinner("영상 정보 조회 중..."):
                api_key  = st.session_state.api_key
                metadata = get_video_metadata(valid_ids, api_key) if api_key else {}
                ch_ids   = list({m["channel_id"] for m in metadata.values() if "channel_id" in m})
                ch_stats = get_channel_stats(ch_ids, api_key) if api_key and ch_ids else {}

            # Redis에 작업 제출
            job_id = str(uuid.uuid4())
            job_payload = json.dumps({
                "job_id":    job_id,
                "video_ids": valid_ids,
                "lang_pref": script_lang,
            }, ensure_ascii=False)
            _redis(upstash_cfg, "RPUSH", "yt_jobs", job_payload)

            # 세션에 작업 정보 저장
            st.session_state.script_job = {
                "job_id":    job_id,
                "urls":      urls,
                "url_id_map": url_id_map,
                "metadata":  metadata,
                "ch_stats":  ch_stats,
            }
            st.session_state.pop("script_results", None)
            st.rerun()

    # ── 결과 대기 / 표시 ────────────────────
    if "script_job" in st.session_state and upstash_cfg:
        job_info = st.session_state.script_job
        job_id   = job_info["job_id"]

        raw = _redis(upstash_cfg, "GET", f"yt_result:{job_id}")
        if raw:
            # 결과 도착 → 파싱 후 세션에 저장
            try:
                data = json.loads(raw)
                transcripts = data.get("transcripts", {})
            except Exception:
                transcripts = {}

            # 메타데이터 + 자막 병합
            merged = []
            for url in job_info["urls"]:
                vid  = job_info["url_id_map"].get(url)
                meta = job_info["metadata"].get(vid, {}) if vid else {}
                cid  = meta.get("channel_id", "")
                ch   = job_info["ch_stats"].get(cid, {"subscribers": 0, "avg_views": 0})
                tags = meta.get("tags", [])
                tr   = transcripts.get(vid, {}) if vid else {}
                merged.append({
                    "채널명":           meta.get("channel_name", ""),
                    "구독자수":         ch["subscribers"],
                    "채널평균조회수":   ch["avg_views"],
                    "썸네일URL":        f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else "",
                    "제목":             meta.get("title", url),
                    "조회수":           meta.get("views", 0),
                    "업로드일자":       meta.get("upload_date", ""),
                    "URL":              url,
                    "스크립트":         tr.get("text", ""),
                    "핵심키워드(태그)": ", ".join(tags[:10]),
                    "_오류":            tr.get("error", "") or ("유효하지 않은 URL" if not vid else ""),
                })

            st.session_state.script_results = merged
            del st.session_state.script_job
            st.rerun()

        else:
            # 아직 처리 중
            total_vids = len([v for v in job_info["url_id_map"].values() if v])
            st.info(f"⏳ 로컬 에이전트가 처리 중입니다... ({total_vids}개 영상)")
            st.caption("영상 1개당 약 2~4초 소요됩니다. 이 페이지를 닫지 마세요.")
            time.sleep(3)
            st.rerun()

    if "script_results" in st.session_state and st.session_state.script_results:
        script_results = st.session_state.script_results
        st.divider()
        success = [r for r in script_results if r["스크립트"]]
        failed  = [r for r in script_results if not r["스크립트"]]
        st.markdown(f"**✅ 성공 {len(success)}개 / ❌ 실패 {len(failed)}개**")

        if success:
            disp_df = pd.DataFrame([
                {
                    "썸네일":           r.get("썸네일URL", ""),
                    "채널명":           r["채널명"],
                    "구독자수":         f"{r['구독자수']:,}",
                    "채널평균조회수":   f"{r['채널평균조회수']:,}",
                    "제목":             r["제목"],
                    "조회수":           f"{r['조회수']:,}",
                    "업로드일자":       r["업로드일자"],
                    "URL":              r["URL"],
                    "스크립트 미리보기": r["스크립트"][:80] + "…" if len(r["스크립트"]) > 80 else r["스크립트"],
                    "핵심키워드(태그)": r["핵심키워드(태그)"],
                }
                for r in success
            ])
            st.dataframe(
                disp_df,
                use_container_width=True,
                hide_index=True,
                row_height=90,
                column_config={
                    "썸네일": st.column_config.ImageColumn("썸네일", width="medium"),
                    "URL":    st.column_config.LinkColumn("URL", display_text="▶ 보기"),
                },
            )

        for r in success:
            vid_id = extract_video_id(r["URL"]) or r["URL"]
            with st.expander(f"📄 {r['제목']}", expanded=False):
                st.text_area("전체 스크립트", value=r["스크립트"], height=250, key=f"sc_{vid_id}")

        if failed:
            with st.expander(f"❌ 수집 실패 ({len(failed)}개)", expanded=False):
                for r in failed:
                    st.markdown(f"- `{r['URL']}` — {r['_오류']}")

        if success:
            st.divider()
            buf = io.StringIO()
            csv_fields = ["채널명", "구독자수", "채널평균조회수", "썸네일URL",
                          "제목", "조회수", "업로드일자", "URL", "스크립트", "핵심키워드(태그)"]
            writer = csv.DictWriter(buf, fieldnames=csv_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(success)
            csv_bytes = buf.getvalue().encode("utf-8-sig")
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="⬇️ 스크립트 CSV 다운로드",
                data=csv_bytes,
                file_name=f"스크립트수집_{now_str}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )

# ─────────────────────────────────────────
# 결과 출력 (수집 탭 공통)
# ─────────────────────────────────────────
if st.session_state.results is not None:
    results = st.session_state.results
    st.divider()
    st.subheader(f"📊 {st.session_state.result_label}")

    if not results:
        st.info("수집된 영상이 없습니다. 조건(최소 조회수, 기간)을 조정해 보세요.")
    else:
        # 정렬 기준 적용
        saved_sort = st.session_state.get("col_sort_by", "조회수 기준")
        if saved_sort == "상위노출 기준":
            results = sorted(results, key=lambda x: (
                x["노출순위"] if isinstance(x["노출순위"], int) and x["노출순위"] > 0 else 9999
            ))
            sort_label = "상위노출 기준 정렬"
        else:
            results = sorted(results, key=lambda x: x["조회수"], reverse=True)
            sort_label = "조회수 높은 순 정렬"

        st.caption(f"총 **{len(results)}개** 영상 · {sort_label}")

        # 행 높이 / 썸네일 행간 확장 CSS
        st.markdown("""
        <style>
        [data-testid="stDataFrameResizable"] .ag-row { min-height: 90px !important; }
        [data-testid="stDataFrameResizable"] .ag-cell { line-height: 1.6 !important; }
        </style>
        """, unsafe_allow_html=True)

        display_df = pd.DataFrame([
            {
                "검색키워드":     r.get("검색키워드", ""),
                "노출순위":       r.get("노출순위", "-"),
                "구분":           r.get("구분", ""),
                "썸네일":         r.get("썸네일URL", ""),
                "제목":           r["제목"],
                "채널명":         r["채널명"],
                "구독자수":       f"{r['구독자수']:,}",
                "채널평균조회수": f"{r['채널평균조회수']:,}",
                "조회수":         f"{r['조회수']:,}",
                "업로드일자":     r["업로드일자"],
                "URL":            r["URL"],
                "채널URL":        r.get("채널URL", ""),
            }
            for r in results
        ])

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=1000,
            row_height=90,
            column_config={
                "썸네일":  st.column_config.ImageColumn("썸네일", width="medium"),
                "URL":     st.column_config.LinkColumn("URL", display_text="▶ 보기"),
                "채널URL": st.column_config.LinkColumn("채널URL", display_text="채널 보기"),
            },
        )

        fieldnames = ["검색키워드", "노출순위", "구분", "채널명", "구독자수", "채널평균조회수", "썸네일", "제목", "조회수", "업로드일자", "URL", "채널URL"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
        csv_bytes = buf.getvalue().encode("utf-8-sig")
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="⬇️ CSV 다운로드 (Excel용)",
            data=csv_bytes,
            file_name=f"youtube_수집결과_{now_str}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
