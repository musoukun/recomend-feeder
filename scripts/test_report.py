"""Report prompt tester.

Usage:
    python scripts/test_report.py tech     # test tech report
    python scripts/test_report.py career   # test career report
    python scripts/test_report.py youtube  # test youtube report

Reads sample data from scripts/test_data/ and generates report.
Edit src/report_generator.py prompts, then re-run to compare.
"""

import json
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from report_generator import (
    generate_tech_report,
    generate_career_report,
    generate_youtube_report,
)

DATA_DIR = Path(__file__).parent / "test_data"


def ensure_sample_data():
    """Create sample test data if not exists."""
    DATA_DIR.mkdir(exist_ok=True)

    tweets_file = DATA_DIR / "sample_tweets.json"
    youtube_file = DATA_DIR / "sample_youtube.json"

    if not tweets_file.exists():
        sample_tweets = [
            {
                "author": "深津 貴之 / THE GUILD, note",
                "handle": "@fladdict",
                "text": "そろそろAIに触らない日常生活というのが、成立しなくなってきてる。マップとGeminiが融合。",
                "url": "https://x.com/fladdict/status/2032418986567303612",
                "category": "ai-tech",
                "summary": "GoogleマップとGeminiが融合し、AIが日常生活に不可欠に",
            },
            {
                "author": "Ryan Yuan",
                "handle": "@RyanYuan_AI",
                "text": "Canvaが世界最先端の画像レイヤー分解モデル「MagicLayers」をグローバルリリース。Qwen-Image-Layerと比較して20〜200倍高速。",
                "url": "https://x.com/RyanYuan_AI/status/123456",
                "category": "ai-tech",
                "summary": "CanvaがMagicLayersリリース、画像を自動レイヤー分解",
            },
            {
                "author": "大曽根宏幸 / Hiroyuki Osone",
                "handle": "@OsoneHiroyuki",
                "text": "戦略17分野における「主要な製品・技術等」1がフィジカルAI",
                "url": "https://x.com/OsoneHiroyuki/status/789012",
                "category": "ai-tech",
                "summary": "政府戦略17分野の主要技術にフィジカルAIが選定",
            },
        ]
        tweets_file.write_text(json.dumps(sample_tweets, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Created: {tweets_file}")

    if not youtube_file.exists():
        sample_youtube = [
            {
                "channel": "Matt Wolfe",
                "title": "The Meta Raybans Scandal Explained",
                "url": "https://www.youtube.com/watch?v=UgS5PihUBQM",
                "summary": "Metaのスマートグラスで録画された映像がAIトレーニング用に外部レビューされていた。バスルームの映像やクレジットカード情報も含まれる。デフォルト設定で共有がオンになっており、米国で訴訟、英国で調査開始。",
            },
            {
                "channel": "Matt Wolfe",
                "title": "Why ChatGPT Isn't Actually Making Your Life Easier",
                "url": "https://www.youtube.com/watch?v=retqU5rjzzI",
                "summary": "ハーバードビジネスレビューの研究によると、AIツールは仕事を減らすどころかタスクを増やしている。AIが知識不足を補い従業員が専門外のタスクもこなすようになりマルチタスク増加。効率化への期待値が上がりペースが加速。",
            },
            {
                "channel": "AI Jason",
                "title": "How to prompt Gemini 3.1 for Epic animations",
                "url": "https://www.youtube.com/watch?v=kcOowmrVI7k",
                "summary": "Gemini 3.1 Proで高品質アニメーション生成するにはシーンベースプロンプトが鍵。アニメーションを複数シーンに分解し、タイミング・UIの状態・特殊効果を詳細記述。AIに設計でなく構築に集中させる。",
            },
            {
                "channel": "All About AI",
                "title": "Long-Running AI Agent Browser Automation Tasks Is Here",
                "url": "https://www.youtube.com/watch?v=8RM-u7TkXpw",
                "summary": "AIエージェントがメールアカウント作成からTwitchライブ配信、アンケート回答で収益獲得まで、複雑なブラウザ自動化タスクを自律実行。FFmpegなど外部ツール連携やDOM解析で自動回答する能力を発揮。",
            },
        ]
        youtube_file.write_text(json.dumps(sample_youtube, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Created: {youtube_file}")

    return tweets_file, youtube_file


def main():
    report_type = sys.argv[1] if len(sys.argv) > 1 else "youtube"

    tweets_file, youtube_file = ensure_sample_data()

    if report_type == "tech":
        tweets = json.loads(tweets_file.read_text(encoding="utf-8"))
        print("--- Generating tech report ---\n")
        result = generate_tech_report(tweets)
    elif report_type == "career":
        tweets = json.loads(tweets_file.read_text(encoding="utf-8"))
        # Filter or use all as career for testing
        for t in tweets:
            t["category"] = "ai-career"
        print("--- Generating career report ---\n")
        result = generate_career_report(tweets)
    elif report_type == "youtube":
        summaries = json.loads(youtube_file.read_text(encoding="utf-8"))
        print("--- Generating youtube report ---\n")
        result = generate_youtube_report(summaries)
    else:
        print(f"Unknown type: {report_type}. Use: tech, career, youtube")
        return

    if result:
        print(result)
        print(f"\n--- {len(result)} chars ---")
    else:
        print("Generation failed. Check GEMINI_API_KEY in .env")


if __name__ == "__main__":
    main()
