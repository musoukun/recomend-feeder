@echo off
echo ============================================
echo  AI Daily Report
echo ============================================
echo [%date% %time%] Start

cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git pull

:: YouTube 要約
echo [%date% %time%] Running YouTube summarizer...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python youtube_main.py

:: X おすすめ → 分類 → RSS + レポート → Webhook投稿
echo [%date% %time%] Running daily report...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python daily_report.py

:: Push
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\*.xml docs\reports\*.md
git diff --staged --quiet || (
    git commit -m "Update feeds + report %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)

echo [%date% %time%] Done.
