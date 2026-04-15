"""
YouTube 영상 수집기 - 메인 페이지 콘텐츠
"""

import csv
import io
from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st

from collector import collect_combined, get_autocomplete_bulk
from transcript import collect_transcripts, extract_video_id

# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def man_to_views(man_value: float) -> int:
    return int(man_value * 10_000)

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
st.title("🎬 YouTube 영상 수집기")

if not st.session_state.api_key:
    st.warning("👈 왼쪽 사이드바에서 YouTube API 키를 먼저 입력하고 저장해 주세요.")
    st.stop()

# ─────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🔍 수집", "💡 자동완성 키워드", "📝 스크립트 수집"])

# ─────────────────────────────────────────
# 탭 1 - 통합 수집
# ─────────────────────────────────────────
with tab1:
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
            "🔑 키워드 (줄바꿈으로 구분)",
            placeholder="인테리어\n셀프인테리어\n홈인테리어",
            height=270,
            key="kw_input",
        )
        channel_include_input = st.text_area(
            "📺 수집할 채널 URL (줄바꿈으로 구분 · 비우면 전체 채널 검색)",
            placeholder="https://www.youtube.com/@channelA\nhttps://www.youtube.com/@channelB",
            height=130,
            key="ch_include_input",
        )
        channel_exclude_input = st.text_area(
            "🚫 제외할 채널 URL (줄바꿈으로 구분)",
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

        if not keywords and not ch_includes:
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
                msg_text.text(f"총 {len(results)}개 영상이 수집됐습니다.")
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
        "**출력 항목:** 입력 키워드 · 자동완성 키워드"
    )

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
# 탭 3 - 스크립트 수집
# ─────────────────────────────────────────
with tab3:
    st.subheader("영상 스크립트 수집")
    st.caption(
        "API 키 불필요 · 쿼터 소모 없음. "
        "영상 URL을 입력하면 YouTube 자막(수동 자막 우선, 없으면 자동 생성 자막)을 텍스트로 추출합니다. "
        "자막이 비활성화된 영상은 수집 불가. "
        "**출력 항목:** 채널명 · 구독자수 · 채널평균조회수 · 썸네일 · 제목 · 조회수 · 업로드일자 · URL · 스크립트 · 핵심키워드(태그)"
    )

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

            # Streamlit Secrets에서 프록시 목록 로드
            try:
                proxy_list = list(st.secrets.get("proxies", {}).get("list", []))
            except Exception:
                proxy_list = []

            results = collect_transcripts(
                urls=urls,
                api_key=st.session_state.api_key,
                lang_pref=script_lang,
                proxy_list=proxy_list or None,
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
                "검색키워드":    r.get("검색키워드", ""),
                "노출순위":      r.get("노출순위", "-"),
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
            row_height=90,
            column_config={
                "썸네일": st.column_config.ImageColumn("썸네일", width="medium"),
                "URL":    st.column_config.LinkColumn("URL", display_text="▶ 보기"),
            },
        )

        fieldnames = ["검색키워드", "노출순위", "구분", "채널명", "구독자수", "채널평균조회수", "썸네일", "제목", "조회수", "업로드일자", "URL"]
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
