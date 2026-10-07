import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin
import hashlib
import re


BASE_URL = "https://www.chugoku-np.co.jp"

SEARCH_URL = (
    "https://www.chugoku-np.co.jp/"
    "search?fulltext=%E3%83%A9%E3%82%B0%E3%83%93%E3%83%BC"
)

OUTPUT = Path(__file__).parent / "chugoku_rugby.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}


# --------------------------------------------------
# 既存RSSを読み込む
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():
    try:
        old_tree = ET.parse(OUTPUT)

        for item in old_tree.getroot().findall("./channel/item"):

            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext(
                        "description",
                        ""
                    ),
                    "pubDate": item.findtext("pubDate", ""),
                    "guid": guid,
                }

    except Exception:
        old_items = {}


# --------------------------------------------------
# 検索ページ取得
# --------------------------------------------------

response = requests.get(
    SEARCH_URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()
response.encoding = "utf-8"

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


# --------------------------------------------------
# 検索結果の記事を取得
#
# 条件：
# ・記事URL /articles/-/数字
# ・YYYY/M/D の日付がある
# ・m-article-card-list の中にある
# ・さらに l-list-block の中にある
#
# ランキング等の m-list-ranking は除外される
# --------------------------------------------------

current_items = []
seen_urls = set()


for a in soup.find_all("a", href=True):

    href = a.get("href", "")

    if not re.fullmatch(
        r"/articles/-/\d+",
        href
    ):
        continue


    # --------------------------------------------------
    # 検索結果カード内か確認
    # --------------------------------------------------

    card = a.find_parent(
        "div",
        class_=lambda classes:
            classes
            and "m-article-card-list" in classes
    )

    if card is None:
        continue


    # --------------------------------------------------
    # l-list-block内か確認
    # --------------------------------------------------

    list_block = card.find_parent(
        "div",
        class_=lambda classes:
            classes
            and "l-list-block" in classes
    )

    if list_block is None:
        continue


    # --------------------------------------------------
    # ランキング内なら除外
    # --------------------------------------------------

    ranking = a.find_parent(
        "div",
        class_=lambda classes:
            classes
            and "m-list-ranking" in classes
    )

    if ranking is not None:
        continue


    # --------------------------------------------------
    # リンク文字列
    # --------------------------------------------------

    text = a.get_text(
        " ",
        strip=True
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()


    # --------------------------------------------------
    # 日付
    # --------------------------------------------------

    date_match = re.search(
        r"(20\d{2})/"
        r"(\d{1,2})/"
        r"(\d{1,2})",
        text
    )

    if not date_match:
        continue


    # --------------------------------------------------
    # URL
    # --------------------------------------------------

    article_url = urljoin(
        BASE_URL,
        href
    )

    article_url = article_url.split("?")[0]


    if article_url in seen_urls:
        continue

    seen_urls.add(article_url)


    # --------------------------------------------------
    # タイトル
    # --------------------------------------------------

    title = text[
        :date_match.start()
    ].strip()

    if not title:
        continue


    # --------------------------------------------------
    # 公開日
    # --------------------------------------------------

    year = int(date_match.group(1))
    month = int(date_match.group(2))
    day = int(date_match.group(3))

    pub_date = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )


    # --------------------------------------------------
    # 無料・限定
    # --------------------------------------------------

    after_date = text[
        date_match.end():
    ].strip()

    description = (
        "中国新聞デジタル "
        "「ラグビー」検索結果"
    )

    if "限定" in after_date:

        description += " / 限定記事"

    elif "無料" in after_date:

        description += " / 無料記事"


    # --------------------------------------------------
    # GUID
    # --------------------------------------------------

    guid = hashlib.sha256(
        article_url.encode("utf-8")
    ).hexdigest()


    current_items.append(
        {
            "title": title,
            "link": article_url,
            "description": description,
            "pubDate": format_datetime(
                pub_date
            ),
            "guid": guid,
        }
    )


    print(
        f"[{len(current_items)}] "
        f"{pub_date.strftime('%Y/%m/%d')} "
        f"{title}"
    )


# --------------------------------------------------
# 既存RSSと統合
# --------------------------------------------------

all_items = []
seen_guids = set()


for item in current_items:

    if item["guid"] not in seen_guids:

        all_items.append(item)
        seen_guids.add(item["guid"])


for guid, item in old_items.items():

    if guid not in seen_guids:

        all_items.append(item)
        seen_guids.add(guid)


# --------------------------------------------------
# 新しい順
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)

all_items = all_items[:300]


# --------------------------------------------------
# RSS作成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)


ET.SubElement(
    channel,
    "title"
).text = (
    "中国新聞デジタル「ラグビー」"
)


ET.SubElement(
    channel,
    "link"
).text = SEARCH_URL


ET.SubElement(
    channel,
    "description"
).text = (
    "中国新聞デジタルで"
    "「ラグビー」と検索した新着記事"
)


ET.SubElement(
    channel,
    "language"
).text = "ja"


# --------------------------------------------------
# RSS記事
# --------------------------------------------------

for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )


    ET.SubElement(
        element,
        "title"
    ).text = item["title"]


    ET.SubElement(
        element,
        "link"
    ).text = item["link"]


    ET.SubElement(
        element,
        "description"
    ).text = item["description"]


    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]


    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


# --------------------------------------------------
# 結果表示
# --------------------------------------------------

print()
print("RSS作成成功")

print(
    "今回取得:",
    len(current_items),
    "件"
)

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)

print()
print("最新20件:")

for item in all_items[:20]:

    print(
        item["pubDate"],
        item["title"],
        "->",
        item["link"]
    )