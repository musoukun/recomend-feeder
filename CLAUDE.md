# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Twitter おすすめタイムラインをスクレイピングし、Gemini 2.5 Flash でカテゴリ分類、カテゴリ別RSSフィードを生成するツール。
加えて YouTube チャンネルの動画字幕を取得し、Gemini で要約して Google Spreadsheet に書き込む機能もある。

## コマンド

```bash
# 依存インストール
pip install -r requirements.txt

# Twitter スクレイピング → 分類 → RSS生成 (docs/*.xml)
cd src && python main.py

# 初回Twitterログイン (ブラウザが開く → 手動ログイン)
cd src && python main.py login

# YouTube 要約パイプライン
cd src && python youtube_main.py
```

テストは未整備。リンターも未設定。

## アーキテクチャ

2つの独立したパイプラインが存在する:

### Twitter RSS パイプライン (`main.py`)
```
scraper.py (nodriver) → classifier.py (Gemini) → feed_generator.py → docs/*.xml
```
- `scraper.py`: nodriver で Twitter `/home` を開き、JS評価でツイートDOM解析。cookie + browser_profile で認証永続化
- `classifier.py`: ツイートをバッチ(20件)で Gemini に送り、JSON Schema で構造化レスポンスを得て6カテゴリに分類
- `feed_generator.py`: feedgen で全体フィード(`feed.xml`)+ カテゴリ別フィード(`feed-{category}.xml`)を `docs/` に出力

### YouTube 要約パイプライン (`youtube_main.py`)
```
youtube_summarizer.py (RSS取得 + yt-dlp字幕) → Gemini要約 → spreadsheet.py (GAS Web App)
```
- `youtube_summarizer.py`: `youtube_feeds.md` のMarkdownリンクからYouTube RSS取得、yt-dlp で字幕DL、Gemini で要約
- `spreadsheet.py`: GAS Web App (POST) 経由で Google Spreadsheet に書き込み
- `gas/Code.gs`: スプレッドシート側のGASコード (video_id で重複排除)

### Discord Bot (`discord-bot/`)
```
GitHub Pages RSS (feed-*.xml) → rss-parser → discord.js Embed → Discord チャンネル投稿
```
- `index.js`: 定期的にRSSフィードをポーリングし、新着ツイートをEmbed形式でDiscordチャンネルに投稿
- `posted.json`: 投稿済みGUID管理（重複防止、直近2000件保持）
- Node.js + discord.js v14

## 実行環境

- TUF PC (192.168.11.27) 上で Windows タスクスケジューラ 30分毎に実行
- `scripts/run_scraper.bat`: スクレイピング → git commit → push (GitHub Pages公開)
- `scripts/run_youtube.bat`: YouTube要約実行
- Python 3.10

## 重要な設計判断

- **nodriver 必須**: Twitter が Playwright の bot 検知でブロックするため nodriver を使用
- **headless=False 固定**: `scraper.py` 内で常に `headless=False` でブラウザ起動（headless だとセッション切れる）
- **GitHub Actions 不可**: Twitter が GitHub Actions の IP レンジをブロックするため、ローカル PC 実行
- **cookie 二重保存**: `auth/browser_profile` + `auth/cookies.dat` の両方で認証永続化

## カテゴリ一覧

`ai`, `politics`, `romance`, `adult`, `news`, `other` — `classifier.py` の `Category` enum で定義

## 環境変数 (.env)

- `TWITTER_USERNAME` / `TWITTER_PASSWORD`: Twitter認証
- `GEMINI_API_KEY`: Google AI Studio APIキー
- `TWEET_COUNT`: 取得件数 (デフォルト50)
- `HEADLESS`: ヘッドレスモード (デフォルトtrue、ただし scraper.py 内で無視される)
- `GAS_WEBAPP_URL`: YouTube要約の書き込み先GAS Web App URL
- `SUBTITLE_LANG`: 字幕言語 (デフォルトja)

## 開発ワークフロー

```bash
# ローカル編集 → push → TUF PC で pull
git push
ssh waros@192.168.11.27 'cd C:\Users\waros\Documents\Develop\recomend-feeder && git pull'
```
