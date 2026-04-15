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
echo.

if not exist dist mkdir dist

echo { > dist\config.json
echo   "upstash_url": "%UPSTASH_URL%", >> dist\config.json
echo   "upstash_token": "%UPSTASH_TOKEN%" >> dist\config.json
echo } >> dist\config.json
echo  [OK] config.json created.

echo.
echo  Installing packages...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo  Building EXE...
pyinstaller --onefile --console --name "YT_Script_Agent" --hidden-import=youtube_transcript_api --hidden-import=youtube_transcript_api.proxies --hidden-import=requests --distpath dist main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo  Creating zip package...
powershell -Command "Compress-Archive -Path 'dist\YT_Script_Agent.exe','dist\config.json' -DestinationPath 'dist\YT_Script_Agent_release.zip' -Force"

echo.
echo ================================================
echo  Build complete!
echo.
echo  Distribute: dist\YT_Script_Agent_release.zip
echo.
echo  User instructions:
echo    1. Unzip the file
echo    2. Double-click YT_Script_Agent.exe
echo    3. Done (no configuration needed)
echo ================================================
echo.
pause
