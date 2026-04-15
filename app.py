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
)

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

    with st.expander("📋 API 키 발급 방법", expanded=False):
        st.markdown("""
**1. Google Cloud Console 접속**
👉 [console.cloud.google.com](https://console.cloud.google.com)

**2. 새 프로젝트 생성**
상단 프로젝트 선택 → **새 프로젝트** → 이름 입력 → 만들기

**3. YouTube Data API v3 활성화**
좌측 메뉴 → API 및 서비스 → 라이브러리
→ **YouTube Data API v3** 검색 → **사용 설정**

**4. API 키 생성**
API 및 서비스 → **사용자 인증 정보**
→ 사용자 인증 정보 만들기 → **API 키**

**5. 키 복사 후 위 입력란에 붙여넣기**

---
> 💡 **무료 쿼터**: 하루 10,000 유닛
> 키워드 검색 1건 ≈ 100 유닛
> 영상 상세 50건 조회 ≈ 1 유닛
        """)

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
tab1, tab2 = st.tabs(["🔍 키워드 검색", "📺 채널 수집"])

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

        # 키워드당 최대 영상 수
        max_per_kw = st.slider(
            "키워드당 최대 영상 수", min_value=10, max_value=50, value=50, key="kw_max",
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
        else:
            region_map = {
                "🇰🇷 한국 (KR / ko)": ("KR", "ko"),
                "🇯🇵 일본 (JP / ja)": ("JP", "ja"),
                "🌐 전체":            (None, None),
            }
            rc, lc = region_map[region_kw]

            st.info(f"총 **{len(keywords)}개** 키워드 · 최소 조회수 **{views_to_man(min_views_kw)}** · 기간 **{days_kw}일**")
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
                    max_per_keyword=max_per_kw,
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

        st.markdown("""
        <small>
        ℹ️ 채널의 전체 영상을 탐색한 뒤<br>숏폼 제외 및 조회수 조건을 적용합니다.<br>
        채널 영상 수가 많을수록 시간이 더 걸립니다.
        </small>
        """, unsafe_allow_html=True)

    if st.button("🚀 수집 시작", key="btn_ch", use_container_width=True, type="primary"):
        channel_urls = [u.strip() for u in channels_input.strip().splitlines() if u.strip()]
        if not channel_urls:
            st.error("채널 URL을 한 줄에 하나씩 입력해 주세요.")
        else:
            st.info(f"총 **{len(channel_urls)}개** 채널 · 최소 조회수 **{views_to_man(min_views_ch)}**")
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
                "URL": st.column_config.LinkColumn("URL", display_text="▶ 보기"),
            },
        )

        # CSV 생성 (썸네일 수식 포함)
        fieldnames = ["채널명", "구독자수", "채널평균조회수", "썸네일", "제목", "조회수", "업로드일자", "URL"]
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
