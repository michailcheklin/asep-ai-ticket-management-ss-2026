import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json

BASE_URL = "https://www.uni-due.de/zim/hilfecenter/faqs.php"


def get_soup(url):
    """
    Returns a BeautifulSoup object of the specified object to later inspect
    :param url: The URL where the BeautifulSoup object is to be fetched
    :return: The BeautifulSoup object of the specified URL
    """
    return BeautifulSoup(requests.get(url=url, timeout=30).text, "html.parser")


# -----------------------------
# INDEX
# -----------------------------
soup = get_soup(BASE_URL)
rahmen = soup.select_one("div.rahmen_rund")

categories = []

for a in rahmen.select("a[href]"):
    text = a.get_text(strip=True)

    if re.match(r"^\d{2}\s", text):
        categories.append({
            "code": text.split()[0],
            "title": text,
            "url": urljoin(BASE_URL, a["href"])
        })


# -----------------------------
# HELPERS
# -----------------------------
def is_level1(text):
    """
    Returns True if the text is a level 1 tag
    :param text: The text to be checked
    :return: True if the text is a level 1 tag
    """
    return re.match(r"^\d{2}\s", text)

def is_level2(text):
    """
    Returns True if the text is a level 2 tag
    :param text: The text to be checked
    :return: True if the text is a level 2 tag
    """
    return re.match(r"^\d{2}\.\d{2}(?!\.\d)", text)

def is_level3(text):
    """
    Returns True if the text is a level 3 tag
    :param text: The text to be checked
    :return: True if the text is a level 3 tag
    """
    return re.match(r"^\d{2}\.\d{2}\.\d+", text)

def is_noise(text):
    """
    Returns True if the text is not in any level
    :param text: The text to be checked
    :return: True if the text is not in any level
    """
    return is_level1(text)


result = {}


# -----------------------------
# PARSER
# -----------------------------

zwischenergebnis = []
gesehen = set()

for cat in categories:

    soup = get_soup(cat["url"])
    items = soup.select("a[name]")

    for item in items:
        name = item.get("name")

        if name not in gesehen:
            gesehen.add(name)
            zwischenergebnis.append(item)

name_url = []

for e in zwischenergebnis:
    url = urljoin(BASE_URL, e["href"])
    name_url.append({
        "name": e,
        "url": url
    })

level3 = []

for entry in name_url:
    b = entry["name"].find("b")
    if b:
        text = b.get_text(strip=True)

        if re.match(r"^\d+\.\d+\.\d+\s", text):
            level3.append(entry)

zwischenergebnisLevel3 = []
gesehenLevel3 = set()

for e in level3:

    soup = get_soup(e["url"])
    items = soup.select("a[name]")

    for item in items:
        name = item.get("name")

        if name not in gesehenLevel3:
            gesehenLevel3.add(name)
            zwischenergebnisLevel3.append(item)


name_url_level3 = []

for e in zwischenergebnisLevel3:
    url = urljoin(BASE_URL, e["href"])
    name_url_level3.append({
        "name": e,
        "url": url
    })

for e in name_url_level3:
    if e not in name_url:
        name_url.append(e)

print("-"*100)

# print("Now printing final")
# for e in name_url:
#     print(e)

json_data = []
for e in name_url:
    b = e["name"].find("b")

    json_data.append({
        "title": b.get_text(strip=True) if b else e["name"].get_text(strip=True),
        "url": e["url"]
    })

with open("faqs.json", "w", encoding="utf-8") as f:
    json.dump(json_data, f, ensure_ascii=False, indent=2)

print(f"{len(json_data)} Urls with names from FAQ stored in faqs.json.")
