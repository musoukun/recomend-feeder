@echo off
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python youtube_main.py
if %ERRORLEVEL% NEQ 0 (
    echo YouTube summarizer failed with error %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo YouTube summarizer completed successfully
