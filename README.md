# YouTube 영상 수집기

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

---

## Streamlit Cloud 배포 (무료 공유)

### 1. GitHub 저장소 생성
- github.com 접속 → **New repository**
- 이름 입력 (예: `youtube-collector`) → **Public** → Create

### 2. 파일 업로드
저장소 페이지에서 **Add file → Upload files**
- `app.py`
- `collector.py`
- `requirements.txt`

### 3. Streamlit Cloud 배포
- [share.streamlit.io](https://share.streamlit.io) 접속 → GitHub 로그인
- **New app** → 저장소 선택 → Main file path: `app.py` → **Deploy**

### 4. 공유 URL 발급
배포 완료 후 `https://[앱이름].streamlit.app` 형태의 URL을 팀원에게 공유

---

## 사용 방법

1. 사이드바에서 **YouTube API 키 입력 → 저장**
   - 브라우저 쿠키에 저장되어 다음 방문 시 자동 로드
   - API 키 발급 방법은 사이드바 내 가이드 참고

2. **키워드 검색** 탭
   - 키워드를 줄바꿈으로 구분하여 복수 입력
   - 최소 조회수, 수집 기간, 지역 설정 후 수집 시작

3. **채널 수집** 탭
   - `https://www.youtube.com/@채널명` 형식으로 줄바꿈 구분 입력
   - 최소 조회수 설정 후 수집 시작

4. 결과 확인 후 **CSV 다운로드** (Excel에서 썸네일 수식 포함)
