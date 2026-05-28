import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


NEWS_URL = "https://www.darpa.mil/news"
RSS_URL = "https://www.darpa.mil/rss.xml"
SEEN_FILE = Path("seen_darpa_quantum_news.json")
DISCORD_LIMIT = 1900

KEYWORDS = [
    "quantum",
    "quantum computing",
    "quantum computer",
    "quantum processor",
    "quantum information science",
    "QIS",
    "quantum network",
    "quantum networking",
    "quantum internet",
    "quantum communication",
    "quantum sensing",
    "quantum sensor",
    "quantum timing",
    "quantum clock",
    "atomic clock",
    "precision timing",
    "quantum navigation",
    "quantum memory",
    "quantum error correction",
    "logical qubit",
    "qubit",
    "trapped ion",
    "neutral atom",
    "superconducting qubit",
    "photonic quantum",
    "entanglement",
    "teleportation",
    "post-quantum",
    "post quantum",
    "quantum-resistant",
    "quantum-safe",
    "cryptography",
    "PQC",
    "DARPA quantum",
    "DARPA Quantum Benchmarking Initiative",
    "QBI",
    "Quantum Benchmarking",
    "Underexplored Systems for Utility-Scale Quantum Computing",
    "US2QC",
]

HEADERS = {
    "User-Agent": "darpa-quantum-news-alert/1.0 (+https://github.com/)"
}


def fetch_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def load_seen() -> Dict[str, dict]:
    if not SEEN_FILE.exists():
        return {}
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Warning: seen file is invalid JSON. Starting with an empty seen list.")
        return {}


def save_seen(seen: Dict[str, dict]) -> None:
    SEEN_FILE.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_rss_items(xml_text: str) -> List[dict]:
    root = ElementTree.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        summary = clean_text(item.findtext("description"))
        date = clean_text(item.findtext("pubDate"))
        if title and link:
            items.append(
                {"title": title, "link": link, "summary": summary, "date": date}
            )
    return items


def parse_news_page_items(html_text: str) -> List[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    seen_links = set()

    for link_tag in soup.select('a[href*="/news/"]'):
        href = link_tag.get("href")
        title = clean_text(link_tag.get_text(" ", strip=True))
        if not href or not title:
            continue

        link = urljoin(NEWS_URL, href)
        if link in seen_links or link.rstrip("/") == NEWS_URL:
            continue
        seen_links.add(link)

        nearby = clean_text(link_tag.parent.get_text(" ", strip=True))
        items.append({"title": title, "link": link, "summary": nearby, "date": ""})

    return items


def fetch_news_items() -> List[dict]:
    try:
        return parse_rss_items(fetch_text(RSS_URL))
    except Exception as error:
        print(f"RSS feed unavailable, falling back to DARPA News page: {error}")
        return parse_news_page_items(fetch_text(NEWS_URL))


def fetch_article_context(link: str) -> str:
    try:
        soup = BeautifulSoup(fetch_text(link), "html.parser")
    except Exception as error:
        print(f"Warning: could not fetch article body for {link}: {error}")
        return ""

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    article = soup.find("article") or soup.find("main") or soup.body or soup
    return clean_text(article.get_text(" ", strip=True))


def matching_keywords(text: str) -> List[str]:
    lowered = text.lower()
    matches = []
    for keyword in KEYWORDS:
        pattern = r"\b" + re.escape(keyword.lower()).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            matches.append(keyword)
    return matches


def is_quantum_related(item: dict) -> List[str]:
    article_context = fetch_article_context(item["link"])
    searchable_text = " ".join(
        [item.get("title", ""), item.get("summary", ""), article_context]
    )
    return matching_keywords(searchable_text)


def discord_post(content: str) -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")

    response = requests.post(
        webhook_url,
        json={"content": content[:DISCORD_LIMIT]},
        timeout=30,
    )
    response.raise_for_status()


def format_discord_message(item: dict, matches: List[str]) -> str:
    date = item.get("date") or "未提供"
    keywords = ", ".join(matches)
    return (
        "🔔 DARPA 量子相关新闻更新\n\n"
        f"标题：{item['title']}\n"
        f"日期：{date}\n"
        f"匹配关键词：{keywords}\n"
        f"链接：{item['link']}"
    )


def send_test_message() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    discord_post(
        "🔔 DARPA 量子相关新闻更新\n\n"
        "标题：Discord 测试消息\n"
        f"日期：{now}\n"
        "匹配关键词：test_mode\n"
        f"链接：{NEWS_URL}"
    )
    print("Discord test message sent.")


def check_news() -> None:
    seen = load_seen()
    items = fetch_news_items()
    found_new_quantum_news = False

    for item in items:
        key = item["link"]
        if key in seen:
            continue

        matches = is_quantum_related(item)
        seen[key] = {
            "title": item["title"],
            "date": item.get("date", ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "matched_keywords": matches,
            "sent_to_discord": bool(matches),
        }

        if matches:
            discord_post(format_discord_message(item, matches))
            found_new_quantum_news = True
            print(f"Sent DARPA quantum-related news: {item['title']}")
        else:
            print(f"Checked non-quantum DARPA news: {item['title']}")

    save_seen(seen)

    if not found_new_quantum_news:
        print("No new DARPA quantum-related news found.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor DARPA quantum-related news.")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Send a Discord test message and skip normal news checking.",
    )
    args = parser.parse_args()

    try:
        if args.test_mode:
            send_test_message()
        else:
            check_news()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
