@echo off
echo ============================================
echo  Recommend Feeder - All-in-One Runner
echo ============================================
echo.

:: Discord bot をバックグラウンドで起動
echo [%date% %time%] Starting Discord bot...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\discord-bot
start "DiscordBot" /min cmd /c "node index.js"
echo Discord bot started in background.
echo.

:: メインループ
set LOOP_COUNT=0

:loop
set /a LOOP_COUNT+=1
echo ============================================
echo [%date% %time%] Loop #%LOOP_COUNT%
echo ============================================

:: git pull
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git pull

:: Twitter スクレイピング（毎回実行）
echo.
echo [%date% %time%] Running Twitter scraper...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python main.py

:: YouTube 要約（2回に1回 = 60分ごと）
set /a YT_CHECK=%LOOP_COUNT% %% 2
if %YT_CHECK%==0 (
    echo.
    echo [%date% %time%] Running YouTube summarizer...
    cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
    python youtube_main.py
) else (
    echo.
    echo [%date% %time%] Skipping YouTube summarizer (next loop)
)

:: フィード更新を push
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\*.xml
git diff --staged --quiet || (
    git commit -m "Update feeds %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)

echo.
echo [%date% %time%] Done. Waiting 30 minutes...
echo.

:: 30分待機（1800秒）
timeout /t 1800 /nobreak

goto loop
