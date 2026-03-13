@echo off
cd /d C:\Users\waros\Documents\Develop\recomend-feeder

:: Pull latest
git pull

:: Run YouTube summarizer
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python youtube_main.py
if %ERRORLEVEL% NEQ 0 (
    echo YouTube summarizer failed with error %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

:: Push YouTube feed to GitHub Pages
cd /d C:\Users\waros\Documents\Develop\recomend-feeder
git add docs\feed-ai-youtuber.xml
git diff --staged --quiet || (
    git commit -m "Update YouTube feed %date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%"
    git push
)
echo YouTube summarizer completed successfully
