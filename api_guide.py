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

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))

def show_img(num: int, caption: str = ""):
    path = os.path.join(ROOT_DIR, f"{num}.png")
    if os.path.exists(path):
        st.image(path, caption=caption, use_container_width=True)
    else:
        st.markdown(
            f"""<div style="background:#f0f2f6;border:1.5px dashed #bbb;border-radius:8px;
            padding:16px;text-align:center;color:#999;font-size:0.85rem;">
            📸 이미지 <code>{num}.png</code> 없음
            </div>""",
            unsafe_allow_html=True,
        )
    st.markdown("")

# ─────────────────────────────────────────
st.title("📋 YouTube API 키 발급 가이드")
st.markdown("""
YouTube 영상 수집기를 사용하려면 **YouTube Data API v3 키**가 필요합니다.
구글 계정만 있으면 **완전 무료**로 발급받을 수 있으며, 아래 순서대로 따라하면 약 **5~10분** 안에 완료됩니다.
""")
st.info("👉 구글 계정이 없다면 먼저 [accounts.google.com](https://accounts.google.com) 에서 계정을 만들어 주세요.")
st.divider()

# ─────────────────────────────────────────
st.subheader("Step 1. Google Cloud Console 접속 및 프로젝트 확인")
st.markdown("""
아래 링크를 클릭해 **Google Cloud Console**에 접속하세요.

👉 **[console.cloud.google.com](https://console.cloud.google.com)**

접속하면 아래와 같은 **"시작하기"** 화면이 나타납니다.
상단 바에 현재 선택된 **프로젝트 이름**이 표시됩니다. (예: `My Project 44083`)

> 💡 처음 접속 시 서비스 약관 동의 팝업이 나올 수 있습니다. **동의 및 계속**을 눌러주세요.
""")
show_img(1, "Google Cloud Console 메인 화면 — 상단에 현재 프로젝트 이름이 표시됩니다")

st.divider()

# ─────────────────────────────────────────
st.subheader("Step 2. 새 프로젝트 만들기")
st.markdown("""
상단 바의 **프로젝트 이름 부분을 클릭**하면 프로젝트 선택 팝업이 열립니다.

팝업 **오른쪽 상단**에 있는 **"새 프로젝트"** 버튼을 클릭하세요.

> 💡 기존 프로젝트가 있다면 그냥 사용해도 되지만, YouTube API 전용으로 새로 만드는 것을 추천합니다.
""")
show_img(2, "프로젝트 선택 팝업 — 오른쪽 상단 '새 프로젝트' 버튼을 클릭")

st.markdown("""
새 프로젝트 생성 화면이 열립니다.

- **프로젝트 이름**: 자유롭게 입력 (예: `youtube-api`)
- **위치(조직)**: 기본값 그대로 두기

입력 후 **"만들기"** 버튼을 클릭하면 프로젝트가 생성됩니다.
""")
show_img(3, "새 프로젝트 이름 입력 후 '만들기' 클릭")

st.divider()

# ─────────────────────────────────────────
st.subheader("Step 3. YouTube Data API v3 활성화")
st.markdown("""
프로젝트 생성 후 왼쪽 메뉴에서 **"API 및 서비스"** 를 클릭하면 하위 메뉴가 펼쳐집니다.
그 중 **"라이브러리"** 를 클릭하세요.

> 💡 왼쪽 메뉴가 보이지 않으면 좌측 상단 **≡ (햄버거 아이콘)** 을 클릭해 메뉴를 펼쳐주세요.
""")
show_img(4, "왼쪽 메뉴 → API 및 서비스 → 라이브러리 클릭")

st.markdown("""
API 라이브러리 검색창에 **`youtube`** 를 입력하면 자동완성 목록이 나타납니다.
목록에서 **"YouTube Data API v3"** 를 클릭하세요.
""")
show_img(5, "검색창에 'youtube' 입력 → 'YouTube Data API v3' 선택")

st.markdown("""
YouTube Data API v3 상세 페이지가 열립니다. 카드 형태로 API 정보가 표시됩니다.
카드를 클릭해 상세 페이지로 진입하세요.
""")
show_img(6, "YouTube Data API v3 카드 클릭")

st.markdown("""
상세 페이지에서 파란색 **"사용 설정"** 버튼을 클릭하세요.

버튼이 **"API 사용 중지"** 로 바뀌면 활성화 완료입니다.
""")
show_img(7, "'사용 설정' 버튼 클릭 → 활성화 완료")

st.divider()

# ─────────────────────────────────────────
st.subheader("Step 4. API 키 생성")
st.markdown("""
API가 활성화되면 상단에 **"사용자 인증 정보 만들기"** 버튼이 나타납니다.
해당 버튼을 클릭하세요.

> 💡 버튼이 보이지 않으면 왼쪽 메뉴 **"API 및 서비스" → "사용자 인증 정보"** 로 이동한 뒤 상단 **"＋ 사용자 인증 정보 만들기"** 를 클릭하세요.
""")
show_img(8, "'사용자 인증 정보 만들기' 버튼 클릭")

st.markdown("""
인증 정보 유형 선택 화면이 나타납니다.

- **어떤 API를 사용할 건가요?** → `YouTube Data API v3` 선택
- **어떤 데이터에 액세스할 건가요?** → **"공개 데이터"** 선택

선택 후 **"다음"** 버튼을 클릭하세요.
""")
show_img(9, "YouTube Data API v3 선택 → '공개 데이터' 선택 → 다음")

st.markdown("""
API 키가 생성되어 화면에 표시됩니다.

**키 값 전체를 복사**해 안전한 곳에 저장해 두세요.

> ⚠️ 이 키는 다시 확인할 수 있지만, 외부에 노출되지 않도록 주의하세요.
""")
show_img(10, "생성된 API 키 — 전체 복사 후 저장")

st.divider()

# ─────────────────────────────────────────
st.subheader("Step 5. 앱에 API 키 입력")
st.markdown("""
1. 왼쪽 사이드바 상단 **🎬 YouTube 영상 수집기** 를 클릭해 메인 앱으로 이동
2. 사이드바 **API 키** 입력란에 복사한 키를 붙여넣기
3. **💾 저장** 클릭 (브라우저에 저장되어 다음에 다시 입력할 필요 없음)
4. **✅ 검증** 클릭으로 정상 작동 확인
""")

st.success("✅ '유효한 API 키입니다.' 메시지가 나오면 모든 준비 완료!")

st.divider()

# ─────────────────────────────────────────
st.subheader("💡 무료 쿼터 안내")
st.markdown("""
YouTube Data API는 **하루 10,000 유닛**을 무료로 제공합니다.

| 기능 | 소모 유닛 | 비고 |
|------|-----------|------|
| 키워드 검색 1회 (50개 결과) | 약 100 유닛 | |
| 영상 상세 정보 조회 (50개) | 1 유닛 | |
| 채널 정보 조회 (50개) | 1 유닛 | |
| 자동완성 키워드 조회 | **0 유닛** | API 키 불필요 |
| 스크립트(자막) 수집 | **0 유닛** | API 키 불필요 |

> ⚠️ 쿼터는 **매일 한국 시간 오후 4시** (태평양 자정)에 초기화됩니다.
>
> 쿼터가 부족하면 Google Cloud Console에서 **새 프로젝트를 만들고 API 키를 추가 발급**받으면 됩니다.
""")
