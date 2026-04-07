import os
import json
import hashlib
import feedparser
import requests
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
POSTED_ARTICLES_FILE = "posted_articles.json"
RSS_URL = "https://news.google.com/rss/search?q=不登校+OR+五月雨登校&hl=ja&gl=JP&ceid=JP:ja"
MAX_ARTICLES_PER_RUN = 5

client = Anthropic(api_key=CLAUDE_API_KEY)


def load_posted_articles() -> list[str]:
    if os.path.exists(POSTED_ARTICLES_FILE):
        with open(POSTED_ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posted_articles(articles: list[str]) -> None:
    with open(POSTED_ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def get_article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def fetch_news() -> list:
    feed = feedparser.parse(RSS_URL)
    return feed.entries


def is_relevant(title: str, summary: str) -> bool:
    """不登校に関連するニュースかClaude APIで判定する"""
    text = title + " " + summary
    prompt = f"""以下のニュース記事が「不登校」に関連する内容かどうか判定してください。
不登校、登校拒否、学校への適応困難、教育機会の確保などに関連する内容であれば「YES」、
無関係であれば「NO」とだけ答えてください。

記事: {text}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = message.content[0].text.strip().upper()
    return "YES" in answer


def summarize_article(title: str, description: str) -> str:
    prompt = f"""以下のニュース記事を3行以内で要約してください。
不登校に関連する重要なポイントを簡潔な日本語でまとめてください。

タイトル: {title}
内容: {description}

要約（3行以内）:"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def post_to_discord(title: str, summary: str, url: str) -> bool:
    message = (
        "📰 **今日の不登校ニュース**\n"
        "─────────────\n"
        f"**【タイトル】** {title}\n\n"
        f"**【要約】**\n{summary}\n\n"
        f"**【元記事リンク】** {url}"
    )

    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    # Discord Webhook は成功時に 204 No Content を返す
    return response.status_code == 204


def main() -> None:
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY が設定されていません")
    if not DISCORD_WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL が設定されていません")

    posted_articles = load_posted_articles()
    entries = fetch_news()
    print(f"取得した記事数: {len(entries)}")

    posted_count = 0

    for entry in entries:
        if posted_count >= MAX_ARTICLES_PER_RUN:
            break

        article_id = get_article_id(entry.link)
        if article_id in posted_articles:
            print(f"スキップ（投稿済み）: {entry.title}")
            continue

        title = entry.title
        description = getattr(entry, "summary", "")

        print(f"関連性チェック中: {title}")
        if not is_relevant(title, description):
            print(f"スキップ（無関係）: {title}")
            # 無関係な記事もIDを記録して再チェックを防ぐ
            posted_articles.append(article_id)
            continue

        print(f"要約中: {title}")
        summary = summarize_article(title, description)

        if post_to_discord(title, summary, entry.link):
            posted_articles.append(article_id)
            posted_count += 1
            print(f"投稿完了: {title}")
        else:
            print(f"投稿失敗: {title}")

    save_posted_articles(posted_articles)
    print(f"\n完了。新規投稿数: {posted_count}")


if __name__ == "__main__":
    main()
