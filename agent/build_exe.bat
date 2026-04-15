@echo off
echo.
echo ================================================
echo   YouTube Script Agent - EXE Build
echo ================================================
echo.
echo  Enter your Upstash Redis credentials.
echo  (Sign up free at upstash.com, then check REST API tab)
echo.
set /p UPSTASH_URL="  Upstash REST URL   : "
set /p UPSTASH_TOKEN="  Upstash REST TOKEN : "

:: Remove surrounding quotes if user typed them
set UPSTASH_URL=%UPSTASH_URL:"=%
set UPSTASH_TOKEN=%UPSTASH_TOKEN:"=%

echo.

if not exist dist mkdir dist

echo { > dist\config.json
echo   "upstash_url": "%UPSTASH_URL%", >> dist\config.json
echo   "upstash_token": "%UPSTASH_TOKEN%" >> dist\config.json
echo } >> dist\config.json
echo  [OK] config.json created.

echo.
echo  Installing packages...
py -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] pip install failed. Make sure Python is installed.
        pause
        exit /b 1
    )
)

echo  Building EXE...
py -m PyInstaller --onefile --console --name "YT_Script_Agent" --hidden-import=youtube_transcript_api --hidden-import=youtube_transcript_api.proxies --hidden-import=requests --distpath dist main.py
if errorlevel 1 (
    python -m PyInstaller --onefile --console --name "YT_Script_Agent" --hidden-import=youtube_transcript_api --hidden-import=youtube_transcript_api.proxies --hidden-import=requests --distpath dist main.py
    if errorlevel 1 (
        echo [ERROR] Build failed.
        pause
        exit /b 1
    )
)

echo.
echo  Creating zip package...
powershell -Command "Compress-Archive -Path 'dist\YT_Script_Agent.exe','dist\config.json' -DestinationPath 'YT_Script_Agent_release.zip' -Force"

echo.
echo ================================================
echo  Build complete!
echo.
echo  1. Commit 'agent\YT_Script_Agent_release.zip' to GitHub
echo     (the app serves this file as a download button)
echo.
echo  2. Users just unzip and double-click YT_Script_Agent.exe
echo ================================================
echo.
pause
