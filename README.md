# Recommend Feeder

Twitter タイムラインをスクレイピングして RSS フィードを生成し、GitHub Pages で公開するツール。
Feedly 等の RSS リーダーに登録して利用できる。

## 構成

```
GitHub Actions (cron 30分毎)
  → Playwright で Twitter タイムライン取得
  → RSS XML 生成
  → GitHub Pages にデプロイ (docs/)
  → Feedly が自動で fetch
```

## セットアップ

### 1. GitHub Secrets の設定

リポジトリの Settings → Secrets and variables → Actions で以下を設定:

- `TWITTER_USERNAME`: Twitter のユーザー名
- `TWITTER_PASSWORD`: Twitter のパスワード

### 2. GitHub Pages の有効化

Settings → Pages → Source を `Deploy from a branch`、Branch を `main`、Folder を `/docs` に設定。

### 3. Feedly に登録

`https://musoukun.github.io/recomend-feeder/feed.xml` を Feedly に登録。

## ローカル実行

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# .env を編集して Twitter 認証情報を設定
cd src
python main.py
```

## 技術スタック

- Python 3.12
- Playwright (ブラウザ自動化)
- feedgen (RSS 生成)
- GitHub Actions (自動化)
- GitHub Pages (ホスティング)
