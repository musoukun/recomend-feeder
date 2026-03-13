@echo off
echo ============================================
echo  AI Daily Report - Loop Runner
echo ============================================

set LOOP_COUNT=0

:loop
set /a LOOP_COUNT+=1
echo.
echo ============================================
echo [%date% %time%] Loop #%LOOP_COUNT%
echo ============================================

cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git pull

:: YouTube 要約（2回に1回 = 60分ごと）
set /a YT_CHECK=%LOOP_COUNT% %% 2
if %YT_CHECK%==0 (
    echo [%date% %time%] Running YouTube summarizer...
    cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
    python youtube_main.py
) else (
    echo [%date% %time%] Skipping YouTube summarizer (next loop)
)

:: X リスト → RSS + デイリーレポート
echo [%date% %time%] Running daily report...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python daily_report.py

:: Push
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\*.xml docs\daily-report.md docs\reports\*.md
git diff --staged --quiet || (
    git commit -m "Update feeds + report %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)

echo.
echo [%date% %time%] Done. Waiting 30 minutes...
timeout /t 1800 /nobreak

goto loop
