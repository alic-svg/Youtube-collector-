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
# 일반 사용자는 아무 것도 입력하지 않아도 되도록, 운영자가 Streamlit Secrets에
# 저장해 둔 값을 기본값으로 쓴다. 사이드바에 직접 입력하면 그 값이 우선한다.
# secrets.toml에는 최상위(UPSTASH_URL = "...")나 섹션([upstash] UPSTASH_URL = "...")
# 어느 쪽으로 적어도 되도록 둘 다 지원한다.
def _get_secret(key, section=None, default=""):
    try:
        if section and section in st.secrets and key in st.secrets[section]:
            return st.secrets[section][key]
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

def _get_secret_proxy_list_text():
    try:
        if "proxies" in st.secrets and "list" in st.secrets["proxies"]:
            return "\n".join(st.secrets["proxies"]["list"])
        if "PROXY_LIST" in st.secrets:
            val = st.secrets["PROXY_LIST"]
            return val if isinstance(val, str) else "\n".join(val)
    except Exception:
        pass
    return ""

# Secrets 값만 사용한다 (브라우저 쿠키로 덮어쓰는 경로는 없음 — 쿠키에 옛 값이
# 남아 Secrets 최신값을 가려버리는 문제가 있어 제거했다).
st.session_state.agent_cfg = {
    "url":   _get_secret("UPSTASH_URL", section="upstash"),
    "token": _get_secret("UPSTASH_TOKEN", section="upstash"),
}
st.session_state.effective_proxy_list_text = _get_secret_proxy_list_text()

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
    st.title("🖥️ 스크립트 수집 상태")
    st.caption(
        "클라우드 서버 IP는 YouTube에 쉽게 차단됩니다. "
        "운영자가 미리 연결해 둔 로컬 에이전트(집 PC)로 자막 수집을 우선 처리해 "
        "따로 설정하지 않아도 됩니다."
    )
    if agent_relay.is_configured(st.session_state.agent_cfg):
        if agent_relay.is_agent_online(st.session_state.agent_cfg):
            st.success("🟢 에이전트 온라인")
        else:
            st.warning("🔴 에이전트 오프라인 — 서버가 프록시로 직접 수집합니다.")
    else:
        st.caption("에이전트 미설정 — 서버가 프록시로 직접 수집합니다.")

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
