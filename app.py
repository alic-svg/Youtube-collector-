"""
YouTube 영상 수집기 - 네비게이션 진입점
"""

import streamlit as st
from streamlit_cookies_controller import CookieController
from collector import validate_api_key

st.set_page_config(
    page_title="YouTube 영상 수집기",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# 쿠키 컨트롤러
# ─────────────────────────────────────────
cookie = CookieController()

# ─────────────────────────────────────────
# 세션 초기화
# ─────────────────────────────────────────
# 쿠키 컴포넌트는 JS 비동기 로드 → 첫 렌더링에서 None 반환.
# 컴포넌트가 로드되면 자동 rerun을 트리거하므로,
# "api_key_loaded" 플래그를 사용해 로드 완료 후 한 번만 읽는다.
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if not st.session_state.get("_api_key_loaded"):
    saved = cookie.get("yt_api_key")
    if saved is not None:
        st.session_state.api_key = saved
        st.session_state._api_key_loaded = True

if "results" not in st.session_state:
    st.session_state.results = None
if "result_label" not in st.session_state:
    st.session_state.result_label = ""

# ─────────────────────────────────────────
# 공유 사이드바 (모든 페이지 공통)
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
            cookie.set("yt_api_key", api_input, max_age=365*24*3600)
            st.success("저장됐습니다.")
    with col2:
        if st.button("✅ 검증", use_container_width=True):
            if api_input:
                with st.spinner("확인 중..."):
                    ok, msg = validate_api_key(api_input)
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("API 키를 먼저 입력하세요.")

    st.divider()
    st.caption("🎬 YouTube 영상 수집기 v1.0")

# ─────────────────────────────────────────
# 페이지 네비게이션
# ─────────────────────────────────────────
pg = st.navigation([
    st.Page("home.py", title="YouTube 영상 수집기", icon="🎬", default=True),
    st.Page("pages/api_guide.py", title="API 발급방법", icon="📋"),
])
pg.run()
