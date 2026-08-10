YT_Script_Agent 사용법
========================

1. YT_Script_Agent.exe 를 더블클릭해서 실행하세요.

2. 처음 실행하면 Upstash Redis 연결 정보를 물어봅니다.
   - upstash.com 무료 가입 → Redis 데이터베이스 생성 → "REST API" 탭에서
     REST URL / REST TOKEN 을 복사해 붙여넣으세요.
   - 웹앱(YouTube 영상 수집기) 사이드바의 "🖥️ 로컬 에이전트" 섹션에도
     반드시 같은 URL/TOKEN 을 입력해야 서로 연결됩니다.

3. "✅ Redis 연결 성공" 이 뜨고 "작업 대기 중..." 상태가 되면 준비 완료.
   이 창을 켜둔 채로 두면, 웹앱에서 스크립트 수집을 시작할 때 이 PC의
   IP로 자막을 가져와 차단을 피할 수 있습니다.

4. 설정을 바꾸고 싶으면 exe 옆에 생기는 config.json 을 지우고
   다시 실행하면 처음부터 다시 물어봅니다.

5. 종료하려면 창에서 Ctrl+C.
