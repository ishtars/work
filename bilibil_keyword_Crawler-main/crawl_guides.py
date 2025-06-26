import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

LIST_URL = "https://shouyou.3dmgame.com/zt/192161_gl/"
OUTPUT_DIR = "guides"


def slugify(text):
    text = re.sub(r"[\\\\/:*?\"<>|]", "_", text)
    return text.strip()


def fetch_article(url):
    r = requests.get(url, timeout=10)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    body = soup.select_one("div.news_warp_center")
    if not body:
        body = soup.body
    return body.get_text("\n", strip=True)


def fetch_list(url):
    r = requests.get(url, timeout=10)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    articles = [
        (a.get_text(strip=True), urljoin(url, a["href"]))
        for a in soup.select("li.selectpost span.text_h a")
    ]
    next_tag = soup.select_one("li.next a")
    next_url = urljoin(url, next_tag["href"]) if next_tag else None
    return articles, next_url


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    page_url = LIST_URL
    seen_titles = set()
    while page_url:
        articles, next_url = fetch_list(page_url)
        for title, url in articles:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            text = fetch_article(url)
            filename = os.path.join(OUTPUT_DIR, f"{slugify(title)}.txt")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(title + "\n" + url + "\n\n" + text)
            print(f"Saved: {filename}")
            time.sleep(0.5)
        page_url = next_url


if __name__ == "__main__":
    main()
