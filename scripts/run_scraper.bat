@echo off
echo ============================================
echo  Twitter Scraper - Single Run
echo ============================================
echo.

:: Pull latest
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git pull

:: Run scraper
echo [%date% %time%] Running Twitter scraper...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python main.py

:: Push to GitHub Pages
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\*.xml
git diff --staged --quiet || (
    git commit -m "Update feeds %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)

echo.
echo [%date% %time%] Done.
