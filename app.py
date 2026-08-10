"""
YouTube 영상 수집기 - 네비게이션 진입점
"""

import streamlit as st
from streamlit_cookies_controller import CookieController
from collector import validate_api_key
import agent_relay

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

# ── 로컬 에이전트(Upstash) / 프록시 설정 ──
if "upstash_url" not in st.session_state:
    st.session_state.upstash_url = ""
if "upstash_token" not in st.session_state:
    st.session_state.upstash_token = ""
if "proxy_list_text" not in st.session_state:
    st.session_state.proxy_list_text = ""
if not st.session_state.get("_relay_cfg_loaded"):
    saved_url   = cookie.get("yt_upstash_url")
    saved_token = cookie.get("yt_upstash_token")
    saved_proxy = cookie.get("yt_proxy_list")
    if saved_url is not None:
        st.session_state.upstash_url = saved_url
        st.session_state.upstash_token = saved_token or ""
        st.session_state.proxy_list_text = saved_proxy or ""
        st.session_state._relay_cfg_loaded = True

# ─────────────────────────────────────────
# 공유 사이드바 (모든 페이지 공통)
# ─────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ API 설정")

    # ── YouTube Data API 키 ──────────────────
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

    # ── 로컬 에이전트 연동 (Upstash Redis) ──
    st.title("🖥️ 로컬 에이전트")
    st.caption(
        "클라우드 서버 IP는 YouTube에 쉽게 차단됩니다. "
        "집 PC에서 [agent] 실행파일을 켜두면 자막 수집을 그쪽으로 넘겨 차단을 피합니다."
    )
    upstash_url_input = st.text_input(
        "Upstash REST URL",
        value=st.session_state.upstash_url,
        placeholder="https://xxxx.upstash.io",
        key="upstash_url_input",
    )
    upstash_token_input = st.text_input(
        "Upstash REST TOKEN",
        value=st.session_state.upstash_token,
        type="password",
        key="upstash_token_input",
    )
    if st.button("💾 에이전트 설정 저장", use_container_width=True):
        st.session_state.upstash_url = upstash_url_input.strip()
        st.session_state.upstash_token = upstash_token_input.strip()
        cookie.set("yt_upstash_url", st.session_state.upstash_url, max_age=365*24*3600)
        cookie.set("yt_upstash_token", st.session_state.upstash_token, max_age=365*24*3600)
        st.success("저장됐습니다.")

    agent_cfg = {"url": st.session_state.upstash_url, "token": st.session_state.upstash_token}
    if agent_relay.is_configured(agent_cfg):
        if agent_relay.is_agent_online(agent_cfg):
            st.success("🟢 에이전트 온라인")
        else:
            st.warning("🔴 에이전트 오프라인 — 집 PC에서 실행파일을 켜주세요.")
    else:
        st.caption("에이전트 설정 전 — 서버 직접수집(프록시)으로 동작합니다.")

    st.divider()

    # ── 프록시 목록 (에이전트 미연결 시 폴백용) ──
    st.title("🌐 프록시 목록")
    st.caption("에이전트가 꺼져 있을 때 서버가 직접 수집하며 사용할 프록시. 한 줄에 하나씩.")
    proxy_input = st.text_area(
        "프록시 (http://user:pass@ip:port)",
        value=st.session_state.proxy_list_text,
        height=80,
        key="proxy_list_input",
        label_visibility="collapsed",
    )
    if st.button("💾 프록시 목록 저장", use_container_width=True):
        st.session_state.proxy_list_text = proxy_input.strip()
        cookie.set("yt_proxy_list", st.session_state.proxy_list_text, max_age=365*24*3600)
        st.success("저장됐습니다.")

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
