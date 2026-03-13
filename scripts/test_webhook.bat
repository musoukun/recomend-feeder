@echo off
echo Testing Discord Webhooks...
cd /d C:\Users\waros\Documents\Develop\recomend-feeder\src
python -c "import json; from report_generator import post_to_discord_webhook; config = json.loads(open('webhooks.json','r',encoding='utf-8').read()); [print(f'Testing: {e[\"name\"]}...') or print('OK' if post_to_discord_webhook('Webhook test', e['webhook']) else 'FAILED') for e in config]"
pause
