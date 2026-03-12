@echo off
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src

:: Run scraper
python main.py

:: Push to GitHub Pages
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\*.xml
git diff --staged --quiet || (
    git commit -m "Update RSS feeds %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)
