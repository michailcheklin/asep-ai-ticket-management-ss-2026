import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

BASE_URL = "https://www.uni-due.de/zim/hilfecenter/faqs.php"


def get_soup(url):
    return BeautifulSoup(requests.get(url).text, "html.parser")


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
    return re.match(r"^\d{2}\s", text)

def is_level2(text):
    return re.match(r"^\d{2}\.\d{2}(?!\.\d)", text)

def is_level3(text):
    return re.match(r"^\d{2}\.\d{2}\.\d+", text)

def is_noise(text):
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

print("Now printing final")
for e in name_url:
    print(e)
