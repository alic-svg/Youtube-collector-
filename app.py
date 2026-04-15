"""
YouTube 영상 수집기 - Streamlit Web App
"""

import csv
import io
from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

from collector import (
    collect_by_keywords,
    collect_by_channels,
    validate_api_key,
    get_autocomplete_bulk,
)
from transcript import collect_transcripts, extract_video_id

# ─────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="YouTube 영상 수집기",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# 쿠키 매니저 (캐시 없이 직접 선언)
# ─────────────────────────────────────────
cookie_manager = stx.CookieManager(key="yt_cookie_manager")

# ─────────────────────────────────────────
# 세션 초기화
# ─────────────────────────────────────────
if "api_key" not in st.session_state:
    try:
        saved = cookie_manager.get("yt_api_key") or ""
    except Exception:
        saved = ""
    st.session_state.api_key = saved

if "results" not in st.session_state:
    st.session_state.results = None
if "result_label" not in st.session_state:
    st.session_state.result_label = ""

# ─────────────────────────────────────────
# 유틸: 만 단위 → 실제 조회수
# ─────────────────────────────────────────
def man_to_views(man_value: float) -> int:
    return int(man_value * 10_000)

def views_to_man(views: int) -> str:
    v = views / 10_000
    return f"{v:.1f}만" if v != int(v) else f"{int(v)}만"

# ─────────────────────────────────────────
# 유틸: 기간 선택 위젯
# ─────────────────────────────────────────
PERIOD_PRESETS = {
    "최근 1개월":  30,
    "최근 3개월":  90,
    "최근 6개월":  180,
    "최근 1년":    365,
    "최근 2년":    730,
    "직접 설정":   -1,
}

def period_selector(key_prefix: str):
    """기간 선택 UI. 선택된 days 반환."""
    sel = st.selectbox(
        "수집 기간",
        list(PERIOD_PRESETS.keys()),
        index=4,  # 기본: 최근 2년
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
# 사이드바 - API 설정
# ─────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ API 설정")

    api_input = st.text_input(
        "YouTube Data API 키",
        value=st.session_state.api_key,
        type="password",
        placeholder="AIzaSy...",
        help="Google Cloud Console에서 발급한 YouTube Data API v3 키를 입력하세요.",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 저장", use_container_width=True):
            st.session_state.api_key = api_input
            try:
                cookie_manager.set("yt_api_key", api_input, key="set_cookie")
                st.success("저장됐습니다.")
            except Exception:
                st.session_state.api_key = api_input
                st.success("저장됐습니다. (세션)")
    with col2:
        if st.button("✅ 검증", use_container_width=True):
            if api_input:
                with st.spinner("확인 중..."):
                    ok, msg = validate_api_key(api_input)
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("API 키를 먼저 입력하세요.")

    st.divider()

    st.page_link("pages/api_guide.py", label="📋 API 키 발급 방법 (스크린샷 가이드)", use_container_width=True)

    st.divider()
    st.caption("🎬 YouTube 영상 수집기 v1.0")

# ─────────────────────────────────────────
# 메인 헤더
# ─────────────────────────────────────────
st.title("🎬 YouTube 영상 수집기")

if not st.session_state.api_key:
    st.warning("👈 왼쪽 사이드바에서 YouTube API 키를 먼저 입력하고 저장해 주세요.")
    st.stop()

# ─────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🔍 키워드 검색", "📺 채널 수집", "💡 자동완성 키워드", "📝 스크립트 수집"])

# ─────────────────────────────────────────
# 탭 1 - 키워드 검색
# ─────────────────────────────────────────
with tab1:
    st.subheader("키워드로 영상 검색")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        keywords_input = st.text_area(
            "키워드 입력 (줄바꿈으로 구분, 복수 입력 가능)",
            placeholder="인테리어\n셀프인테리어\n홈인테리어\n거실인테리어",
            height=180,
            key="kw_input",
        )

    with col_right:
        st.markdown("**🔧 수집 조건**")

        # 최소 조회수 (만 단위)
        min_views_man_kw = st.number_input(
            "최소 조회수 (만)",
            min_value=0.0,
            value=10.0,
            step=1.0,
            format="%.1f",
            key="kw_min_views_man",
            help="예) 10 = 10만(100,000)회 이상 / 0 = 조건 없음",
        )
        min_views_kw = man_to_views(min_views_man_kw)
        if min_views_kw > 0:
            st.caption(f"= {min_views_kw:,}회 이상")
        else:
            st.caption("= 조건 없음 (전체)")

        # 수집 기간
        days_kw = period_selector("kw")

        # 롱폼 / 숏폼 선택
        st.markdown("**영상 형태**")
        fc1, fc2 = st.columns(2)
        with fc1:
            kw_longform = st.checkbox("롱폼", value=True, key="kw_longform")
        with fc2:
            kw_shorts = st.checkbox("숏폼", value=False, key="kw_shorts")
        if not kw_longform and not kw_shorts:
            st.warning("롱폼/숏폼 중 하나는 선택해야 합니다.")

        # 최대 결과 수
        result_limit_kw = st.number_input(
            "최대 결과 수", min_value=10, max_value=500, value=100, step=10, key="kw_limit",
            help="필터링 후 조회수 상위 N개만 표시"
        )

        # 검색 지역
        region_kw = st.selectbox(
            "검색 지역 / 언어",
            ["🇰🇷 한국 (KR / ko)", "🇯🇵 일본 (JP / ja)", "🌐 전체"],
            key="kw_region",
        )

    if st.button("🚀 수집 시작", key="btn_kw", use_container_width=True, type="primary"):
        keywords = [k.strip() for k in keywords_input.strip().splitlines() if k.strip()]
        if not keywords:
            st.error("키워드를 한 줄에 하나씩 입력해 주세요.")
        elif not kw_longform and not kw_shorts:
            st.error("롱폼/숏폼 중 하나 이상 선택해 주세요.")
        else:
            region_map = {
                "🇰🇷 한국 (KR / ko)": ("KR", "ko"),
                "🇯🇵 일본 (JP / ja)": ("JP", "ja"),
                "🌐 전체":            (None, None),
            }
            rc, lc = region_map[region_kw]

            form_label = "롱폼+숏폼" if kw_longform and kw_shorts else ("롱폼만" if kw_longform else "숏폼만")
            st.info(f"총 **{len(keywords)}개** 키워드 · **{form_label}** · 최소 조회수 **{views_to_man(min_views_kw)}** · 기간 **{days_kw}일** · 상위 **{result_limit_kw}개**")
            prog = st.progress(0)
            step_text = st.empty()
            msg_text = st.empty()

            def kw_callback(progress, step, message):
                prog.progress(min(progress, 1.0))
                step_text.markdown(f"**{step}**")
                msg_text.text(message)

            try:
                results = collect_by_keywords(
                    keywords=keywords,
                    min_views=min_views_kw,
                    days=days_kw,
                    api_key=st.session_state.api_key,
                    include_longform=kw_longform,
                    include_shorts=kw_shorts,
                    result_limit=result_limit_kw,
                    region_code=rc,
                    lang_code=lc,
                    callback=kw_callback,
                )
                st.session_state.results = results
                st.session_state.result_label = (
                    f"키워드 검색 결과 ({', '.join(keywords[:3])}"
                    f"{'...' if len(keywords) > 3 else ''})"
                )
                prog.progress(1.0)
                step_text.markdown("**✅ 수집 완료**")
                msg_text.text(f"총 {len(results)}개 영상이 수집됐습니다.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# ─────────────────────────────────────────
# 탭 2 - 채널 수집
# ─────────────────────────────────────────
with tab2:
    st.subheader("채널 URL로 영상 수집")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        channels_input = st.text_area(
            "채널 URL 입력 (줄바꿈으로 구분)",
            placeholder="https://www.youtube.com/@channelname\nhttps://www.youtube.com/@another\nhttps://www.youtube.com/@아정당인테리어",
            height=180,
            key="ch_input",
        )

    with col_right:
        st.markdown("**🔧 수집 조건**")

        # 최소 조회수 (만 단위)
        min_views_man_ch = st.number_input(
            "최소 조회수 (만)",
            min_value=0.0,
            value=10.0,
            step=1.0,
            format="%.1f",
            key="ch_min_views_man",
            help="예) 10 = 10만(100,000)회 이상 / 0 = 조건 없음",
        )
        min_views_ch = man_to_views(min_views_man_ch)
        if min_views_ch > 0:
            st.caption(f"= {min_views_ch:,}회 이상")
        else:
            st.caption("= 조건 없음 (전체)")

        # 롱폼 / 숏폼 선택
        st.markdown("**영상 형태**")
        fc1, fc2 = st.columns(2)
        with fc1:
            ch_longform = st.checkbox("롱폼", value=True, key="ch_longform")
        with fc2:
            ch_shorts = st.checkbox("숏폼", value=False, key="ch_shorts")
        if not ch_longform and not ch_shorts:
            st.warning("롱폼/숏폼 중 하나는 선택해야 합니다.")

        # 최대 결과 수
        result_limit_ch = st.number_input(
            "최대 결과 수", min_value=10, max_value=500, value=100, step=10, key="ch_limit",
            help="필터링 후 조회수 상위 N개만 표시"
        )

        st.markdown("""
        <small>
        ℹ️ 채널의 전체 영상을 탐색한 뒤<br>조건을 적용합니다.<br>
        채널 영상 수가 많을수록 시간이 더 걸립니다.
        </small>
        """, unsafe_allow_html=True)

    if st.button("🚀 수집 시작", key="btn_ch", use_container_width=True, type="primary"):
        channel_urls = [u.strip() for u in channels_input.strip().splitlines() if u.strip()]
        if not channel_urls:
            st.error("채널 URL을 한 줄에 하나씩 입력해 주세요.")
        elif not ch_longform and not ch_shorts:
            st.error("롱폼/숏폼 중 하나 이상 선택해 주세요.")
        else:
            ch_form_label = "롱폼+숏폼" if ch_longform and ch_shorts else ("롱폼만" if ch_longform else "숏폼만")
            st.info(f"총 **{len(channel_urls)}개** 채널 · **{ch_form_label}** · 최소 조회수 **{views_to_man(min_views_ch)}** · 상위 **{result_limit_ch}개**")
            prog = st.progress(0)
            step_text = st.empty()
            msg_text = st.empty()

            def ch_callback(progress, step, message):
                prog.progress(min(progress, 1.0))
                step_text.markdown(f"**{step}**")
                msg_text.text(message)

            try:
                results, errors = collect_by_channels(
                    channel_urls=channel_urls,
                    min_views=min_views_ch,
                    api_key=st.session_state.api_key,
                    include_longform=ch_longform,
                    include_shorts=ch_shorts,
                    result_limit=result_limit_ch,
                    callback=ch_callback,
                )
                st.session_state.results = results
                st.session_state.result_label = f"채널 수집 결과 ({len(channel_urls)}개 채널)"
                prog.progress(1.0)
                step_text.markdown("**✅ 수집 완료**")
                msg_text.text(f"총 {len(results)}개 영상이 수집됐습니다.")
                if errors:
                    with st.expander(f"⚠️ 수집 실패 채널 ({len(errors)}개)"):
                        for e in errors:
                            st.text(e)
            except Exception as e:
                st.error(f"오류 발생: {e}")

# ─────────────────────────────────────────
# 탭 3 - 자동완성 키워드
# ─────────────────────────────────────────
with tab3:
    st.subheader("YouTube 자동완성 키워드 조회")
    st.caption("API 키 불필요 · 쿼터 소모 없음 · 검색창 자동완성 그대로 확인")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        ac_input = st.text_area(
            "키워드 입력 (줄바꿈으로 구분)",
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

            st.session_state.ac_results = ac_results

    if "ac_results" in st.session_state and st.session_state.ac_results:
        ac_results = st.session_state.ac_results
        st.divider()

        # 키워드별로 펼쳐서 표시
        all_rows = []
        for item in ac_results:
            kw = item["키워드"]
            suggestions = item["자동완성"]

            with st.expander(f"**{kw}** — {len(suggestions)}개 자동완성", expanded=True):
                if suggestions:
                    cols = st.columns(2)
                    for idx, sug in enumerate(suggestions):
                        cols[idx % 2].markdown(f"- {sug}")
                else:
                    st.caption("자동완성 결과 없음")

            for sug in suggestions:
                all_rows.append({"입력 키워드": kw, "자동완성 키워드": sug})

        # CSV 다운로드
        if all_rows:
            st.divider()
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=["입력 키워드", "자동완성 키워드"])
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


# ─────────────────────────────────────────
# 탭 4 - 스크립트 수집
# ─────────────────────────────────────────
with tab4:
    st.subheader("영상 스크립트 수집")
    st.caption("API 키 불필요 · 쿼터 소모 없음 · YouTube 자막 기반 텍스트 추출")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        script_urls_input = st.text_area(
            "영상 URL 입력 (줄바꿈으로 구분)",
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

    if st.button("📝 스크립트 수집 시작", key="btn_script", use_container_width=True, type="primary"):
        urls = [u.strip() for u in script_urls_input.strip().splitlines() if u.strip()]
        if not urls:
            st.error("영상 URL을 한 줄에 하나씩 입력해 주세요.")
        else:
            st.info(f"총 **{len(urls)}개** 영상 스크립트 수집 시작")
            prog = st.progress(0)
            status_text = st.empty()

            def script_callback(progress, message):
                prog.progress(min(progress, 1.0))
                status_text.text(message)

            results = collect_transcripts(
                urls=urls,
                api_key=st.session_state.api_key,
                lang_pref=script_lang,
                callback=script_callback,
            )
            st.session_state.script_results = results
            prog.progress(1.0)
            status_text.text(f"완료 · {sum(1 for r in results if r['스크립트'])}개 성공 / {len(results)}개")

    if "script_results" in st.session_state and st.session_state.script_results:
        script_results = st.session_state.script_results
        st.divider()

        success = [r for r in script_results if r["스크립트"]]
        failed  = [r for r in script_results if not r["스크립트"]]

        st.markdown(f"**✅ 성공 {len(success)}개 / ❌ 실패 {len(failed)}개**")

        success = [r for r in script_results if r["스크립트"]]
        failed  = [r for r in script_results if not r["스크립트"]]

        st.markdown(f"**✅ 성공 {len(success)}개 / ❌ 실패 {len(failed)}개**")

        # 결과 테이블
        if success:
            disp_df = pd.DataFrame([
                {
                    "썸네일":          r.get("썸네일URL", ""),
                    "채널명":          r["채널명"],
                    "구독자수":        f"{r['구독자수']:,}",
                    "채널평균조회수":  f"{r['채널평균조회수']:,}",
                    "제목":            r["제목"],
                    "조회수":          f"{r['조회수']:,}",
                    "업로드일자":      r["업로드일자"],
                    "URL":             r["URL"],
                    "스크립트 미리보기": r["스크립트"][:80] + "…" if len(r["스크립트"]) > 80 else r["스크립트"],
                    "핵심키워드(태그)": r["핵심키워드(태그)"],
                }
                for r in success
            ])
            st.dataframe(
                disp_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "썸네일": st.column_config.ImageColumn("썸네일", width="small"),
                    "URL":    st.column_config.LinkColumn("URL", display_text="▶ 보기"),
                },
            )

        # 스크립트 전문 펼침 보기
        for r in success:
            vid_id = extract_video_id(r["URL"]) or r["URL"]
            with st.expander(f"📄 {r['제목']}", expanded=False):
                st.text_area(
                    "전체 스크립트",
                    value=r["스크립트"],
                    height=250,
                    key=f"sc_{vid_id}",
                )

        # 실패 목록
        if failed:
            with st.expander(f"❌ 수집 실패 ({len(failed)}개)", expanded=False):
                for r in failed:
                    st.markdown(f"- `{r['URL']}` — {r['_오류']}")

        # CSV 다운로드
        if success:
            st.divider()
            buf = io.StringIO()
            csv_fields = ["채널명", "구독자수", "채널평균조회수", "썸네일",
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
# 결과 출력
# ─────────────────────────────────────────
if st.session_state.results is not None:
    results = st.session_state.results
    st.divider()
    st.subheader(f"📊 {st.session_state.result_label}")

    if not results:
        st.info("수집된 영상이 없습니다. 조건(최소 조회수, 기간)을 조정해 보세요.")
    else:
        st.caption(f"총 **{len(results)}개** 영상 · 조회수 높은 순 정렬")

        display_df = pd.DataFrame([
            {
                "구분":          r.get("구분", ""),
                "썸네일":        r.get("썸네일URL", ""),
                "채널명":        r["채널명"],
                "구독자수":      f"{r['구독자수']:,}",
                "채널평균조회수": f"{r['채널평균조회수']:,}",
                "제목":          r["제목"],
                "조회수":        f"{r['조회수']:,}",
                "업로드일자":    r["업로드일자"],
                "URL":           r["URL"],
            }
            for r in results
        ])

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "썸네일": st.column_config.ImageColumn("썸네일", width="small"),
                "URL":    st.column_config.LinkColumn("URL", display_text="▶ 보기"),
            },
        )

        # CSV 생성 (썸네일 수식 포함, 썸네일URL 제외)
        fieldnames = ["구분", "채널명", "구독자수", "채널평균조회수", "썸네일", "제목", "조회수", "업로드일자", "URL"]
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
