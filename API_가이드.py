"""
YouTube Data API 키 발급 가이드 페이지
"""

import os
import streamlit as st

st.set_page_config(
    page_title="API 키 발급 가이드",
    page_icon="📋",
    layout="wide",
)

# 이미지는 앱 루트 폴더에 1.png ~ 10.png 로 저장
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))

def show_img(num: int, caption: str = ""):
    path = os.path.join(ROOT_DIR, f"{num}.png")
    if os.path.exists(path):
        st.image(path, caption=caption, use_container_width=True)
    else:
        st.markdown(
            f"""<div style="background:#f0f2f6;border:1.5px dashed #bbb;border-radius:8px;
            padding:16px;text-align:center;color:#999;font-size:0.85rem;">
            📸 이미지를 <code>{num}.png</code> 파일로 저장해 주세요.
            </div>""",
            unsafe_allow_html=True,
        )
    st.markdown("")

# ─────────────────────────────────────────
st.title("📋 YouTube API 키 발급 가이드")
st.markdown("""
YouTube 영상 수집기를 사용하려면 **YouTube Data API v3** 키가 필요합니다.
아래 단계를 따라 무료로 발급받을 수 있습니다.

> 💡 **소요 시간**: 약 5~10분 &nbsp;|&nbsp; 💡 **비용**: 완전 무료
""")
st.info("👉 구글 계정이 없다면 먼저 [accounts.google.com](https://accounts.google.com) 에서 만들어 주세요.")
st.divider()

# ─────────────────────────────────────────
st.subheader("Step 1. Google Cloud Console 접속")
st.markdown("""
아래 링크를 클릭해 **Google Cloud Console** 에 접속하고, 구글 계정으로 로그인하세요.

👉 **[console.cloud.google.com](https://console.cloud.google.com)**

처음 접속 시 서비스 약관 동의 팝업이 나올 수 있습니다. **동의 및 계속** 을 눌러 진행하세요.
""")
show_img(1, "Google Cloud Console 메인 화면")

st.divider()
# ─────────────────────────────────────────
st.subheader("Step 2. 새 프로젝트 만들기")
st.markdown("""
상단 내비게이션 바에서 **프로젝트 선택 드롭다운** 을 클릭하세요.
(처음이라면 "Google Cloud" 옆에 표시됩니다.)
""")
show_img(2, "상단 프로젝트 선택 드롭다운 클릭")

st.markdown("""
팝업 우측 상단 **새 프로젝트** 를 클릭하세요.
""")
show_img(3, "'새 프로젝트' 버튼 클릭")

st.markdown("""
프로젝트 이름을 입력하고 **만들기** 를 클릭하세요.

| 항목 | 입력값 |
|------|--------|
| 프로젝트 이름 | `youtube-api` (자유롭게) |
| 위치 | 기본값 유지 |
""")
show_img(4, "프로젝트 이름 입력 후 '만들기'")

st.divider()
# ─────────────────────────────────────────
st.subheader("Step 3. YouTube Data API v3 활성화")
st.markdown("""
좌측 메뉴 **≡ → API 및 서비스 → 라이브러리** 를 클릭하세요.
""")
show_img(5, "API 및 서비스 → 라이브러리 메뉴")

st.markdown("""
검색창에 **`YouTube Data API v3`** 를 입력하고 검색 결과를 클릭하세요.
""")
show_img(6, "YouTube Data API v3 검색 결과")

st.markdown("""
상세 페이지에서 파란색 **사용 설정** 버튼을 클릭하세요.
버튼이 **API 사용 중지** 로 바뀌면 활성화 완료입니다.
""")
show_img(7, "'사용 설정' 클릭 → 활성화 완료")

st.divider()
# ─────────────────────────────────────────
st.subheader("Step 4. API 키 생성")
st.markdown("""
좌측 메뉴 **API 및 서비스 → 사용자 인증 정보** 를 클릭하세요.
상단 **＋ 사용자 인증 정보 만들기 → API 키** 를 선택하세요.
""")
show_img(8, "사용자 인증 정보 → API 키 선택")

st.markdown("""
잠시 후 API 키가 생성되며 팝업에 표시됩니다. **키를 복사** 해 두세요.
""")
show_img(9, "생성된 API 키 복사")

st.divider()
# ─────────────────────────────────────────
st.subheader("Step 5. 앱에 API 키 입력")
st.markdown("""
1. 좌측 사이드바 상단 **🎬 YouTube 영상 수집기** 를 클릭해 메인 앱으로 이동
2. 사이드바 **API 설정** 입력란에 복사한 키를 붙여넣기
3. **💾 저장** 클릭
4. **✅ 검증** 클릭으로 정상 작동 확인
""")
show_img(10, "앱 사이드바에 API 키 입력 및 저장")

st.success("✅ '유효한 API 키입니다.' 메시지가 나오면 모든 준비 완료!")

st.divider()
# ─────────────────────────────────────────
st.subheader("💡 무료 쿼터 안내")
st.markdown("""
YouTube Data API는 **하루 10,000 유닛** 을 무료로 제공합니다.

| 기능 | 소모 유닛 |
|------|-----------|
| 키워드 검색 1회 (50개 결과) | 약 100 유닛 |
| 영상 상세 정보 50개 | 1 유닛 |
| 채널 정보 50개 | 1 유닛 |
| 스크립트 수집 | **0 유닛** ✅ |
| 자동완성 키워드 조회 | **0 유닛** ✅ |

> ⚠️ 쿼터는 **매일 한국 시간 오후 4시** (태평양 자정)에 초기화됩니다.
> 부족하면 Google Cloud Console에서 새 API 키를 추가 발급받으세요.
""")
