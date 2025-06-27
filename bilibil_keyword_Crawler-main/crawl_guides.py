import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

LIST_URL = "https://shouyou.3dmgame.com/zt/192161_gl/"
PAGE_URL_TEMPLATE = "https://shouyou.3dmgame.com/zt/192161_gl_all_{}/"
OUTPUT_DIR = "guides"
TOTAL_PAGES = 32  # 总页数

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
    return articles

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    seen_titles = set()
    for page in range(1, TOTAL_PAGES + 1):
        if page == 1:
            page_url = LIST_URL
        else:
            page_url = PAGE_URL_TEMPLATE.format(page)
        print(f"正在爬取第{page}页: {page_url}")
        try:
            articles = fetch_list(page_url)
        except Exception as e:
            print(f"第{page}页获取失败：{e}")
            continue
        for title, url in articles:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            try:
                text = fetch_article(url)
            except Exception as e:
                print(f"抓取文章失败: {url} -> {e}")
                continue
            filename = os.path.join(OUTPUT_DIR, f"{slugify(title)}.txt")
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(title + "\n" + url + "\n\n" + text)
                print(f"Saved: {filename}")
            except Exception as e:
                print(f"保存失败: {filename} -> {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    main()
