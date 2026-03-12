# Recommend Feeder

Twitter おすすめタイムラインをスクレイピングし、AI分類してカテゴリ別RSSフィードを生成するツール。

## 技術スタック

- **スクレイピング**: nodriver (undetected-chromedriver後継、bot検知回避)
- **AI分類**: Gemini 2.5 Flash (google-genai SDK)
- **RSS生成**: feedgen
- **ホスティング**: GitHub Pages (docs/ ディレクトリ)
- **定期実行**: Windows タスクスケジューラ (30分毎)
- **Python**: 3.10 (TUF PC)

## 構成

```
TUF PC (192.168.11.27) タスクスケジューラ 30分毎
  → nodriver で Twitter おすすめタイムライン取得 (30件)
  → Gemini 2.5 Flash でカテゴリ分類
  → カテゴリ別 RSS XML 生成 (docs/)
  → git push → GitHub Pages で公開
  → Feedly が自動 fetch
```

## カテゴリ

| フィード | カテゴリ |
|---|---|
| feed.xml | 全ツイート |
| feed-ai.xml | AI・テック・エンジニア (AI, ML, プログラミング, エンジニア雇用動向, 量子コンピュータ等) |
| feed-politics.xml | 政治 |
| feed-romance.xml | 恋愛 |
| feed-adult.xml | アダルト |
| feed-news.xml | ニュース |
| feed-other.xml | その他 |

## 開発ワークフロー

```bash
# ローカルで編集 → push → TUF PC で pull
git push
ssh waros@192.168.11.27 'cd C:\Users\waros\Documents\Develop\recomend-feeder && git pull'
```

## TUF PC での実行

```bash
# 初回ログイン (ブラウザが開く → 手動でTwitterログイン → Enterキー)
cd C:\Users\waros\Documents\Develop\recomend-feeder\src
python main.py login

# スクレイピング実行
python main.py

# タスクスケジューラ登録済み ("RecomendFeeder", 30分毎)
# scripts/run_scraper.bat が実行される
```

## 重要な設計判断

- **Playwright → nodriver に切り替え**: TwitterがPlaywrightのbot検知で自動ログインをブロックするため
- **永続ブラウザプロファイル**: auth/browser_profile に保存。初回だけ手動ログイン、以降はセッション再利用
- **cookie二重保存**: browser_profile + cookies.dat の両方で永続化
- **GitHub Actions断念**: Twitter がGitHub ActionsのIPレンジからのアクセスをブロックするため、TUF PCローカル実行に変更
- **headless=False 固定**: 表示モードでないとTwitterセッションが切れる場合がある

## Feedly URL

```
https://musoukun.github.io/recomend-feeder/feed-ai.xml
https://musoukun.github.io/recomend-feeder/feed-politics.xml
https://musoukun.github.io/recomend-feeder/feed-romance.xml
https://musoukun.github.io/recomend-feeder/feed-adult.xml
https://musoukun.github.io/recomend-feeder/feed-news.xml
https://musoukun.github.io/recomend-feeder/feed-other.xml
```

## 環境変数 (.env)

- `TWITTER_USERNAME` / `TWITTER_PASSWORD`: Twitter認証情報
- `GEMINI_API_KEY`: Google AI Studio APIキー
- `TWEET_COUNT`: 取得件数 (デフォルト30)
- `HEADLESS`: ヘッドレスモード (デフォルトtrue)
