@echo off
echo ============================================
echo  AI Daily Report Generator
echo ============================================

cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git pull

echo [%date% %time%] Running daily report...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python daily_report.py

cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\daily-report.md docs\reports\*.md docs\feed-daily-report.xml
git diff --staged --quiet || (
    git commit -m "AI Daily Report %date:~0,4%-%date:~5,2%-%date:~8,2%"
    git push
)

echo [%date% %time%] Done!
