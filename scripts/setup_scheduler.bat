@echo off
:: Create Windows Task Scheduler task to run scraper every 30 minutes
schtasks /create /tn "RecomendFeeder" /tr "C:\Users\waros\Documents\Develop\recomend-feeder\scripts\run_scraper.bat" /sc minute /mo 30 /f
echo Task "RecomendFeeder" created (runs every 30 minutes)
pause
