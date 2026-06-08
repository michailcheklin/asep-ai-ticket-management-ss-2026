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
        print(text.split()[0])
        print(text)
        print(urljoin(BASE_URL, a["href"]))
        print("-"*50)
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
    print(items)
    print("-"*50)

    for item in items:
        name = item.get("name")

        if name not in gesehen:
            gesehen.add(name)
            zwischenergebnis.append(item)

name_url = []

for e in zwischenergebnis:
    # print(e)
    # print("-"*50)
    url = urljoin(BASE_URL, e["href"])
    # print(url)
    # print("-"*50)
    name_url.append({
        "name": e,
        "url": url
    })

for e in name_url:
    print(e)

level3 = []

for entry in name_url:
    b = entry["name"].find("b")
    if b:
        text = b.get_text(strip=True)

        if re.match(r"^\d+\.\d+\.\d+\s", text):
            level3.append(entry)

zwischenergebnisLevel3 = []
gesehenLevel3 = set()

print("Now printing level 3")
for e in level3:
    print(e)

    soup = get_soup(e["url"])
    items = soup.select("a[name]")
    print(items)
    print("-"*50)

    for item in items:
        name = item.get("name")

        if name not in gesehenLevel3:
            gesehenLevel3.add(name)
            zwischenergebnisLevel3.append(item)

print("Now printing Zwischenergebnis level 3")
for e in zwischenergebnisLevel3:
    print(e)


name_url_level3 = []

for e in zwischenergebnisLevel3:
    # print(e)
    # print("-"*50)
    url = urljoin(BASE_URL, e["href"])
    # print(url)
    # print("-"*50)
    name_url_level3.append({
        "name": e,
        "url": url
    })

for e in name_url_level3:
    print(e)

for e in name_url_level3:
    if e not in name_url:
        name_url.append(e)


print("Now printing final")
for e in name_url:
    print(e)

#     structured = {}
#     current_section = None
#     current_subsection = None
#
#     for a in items:
#         text = a.get_text(strip=True)
#         href = a.get("href")
#         url = urljoin(cat["url"], href) if href else cat["url"]
#
#         # LEVEL 2
#         if is_level2(text):
#             key = text.split()[0]
#             structured[key] = {
#                 "title": text,
#                 "url": url,
#                 "children": [],
#                 "subsections": {}
#             }
#             current_section = key
#             current_subsection = None
#             continue
#
#         # LEVEL 1 RESET
#         if is_level1(text):
#             current_section = None
#             current_subsection = None
#             continue
#
#         # LEVEL 3 (nur struktur setzen, KEIN request!)
#         if is_level3(text) and current_section:
#             key = text.split()[0]
#
#             structured[current_section]["subsections"][key] = {
#                 "title": text,
#                 "url": url,
#                 "children": []
#             }
#
#             current_subsection = key
#             continue
#
#         # LEVEL 4 / CHILDREN direkt aus DOM (wichtig!)
#         if current_section and current_subsection:
#             li = a.find_parent("li")
#             if not li:
#                 continue
#
#             ul = li.find("ul", class_="plain")
#
#             if ul:
#                 for sub_li in ul.find_all("li", recursive=False):
#                     sub_a = sub_li.find("a")
#                     if not sub_a:
#                         continue
#
#                     sub_text = sub_a.get_text(strip=True)
#                     sub_href = sub_a.get("href")
#                     sub_url = urljoin(cat["url"], sub_href) if sub_href else cat["url"]
#
#                     if sub_text and not is_level1(sub_text) and not is_level2(sub_text) and not is_level3(sub_text):
#                         structured[current_section]["subsections"][current_subsection]["children"].append({
#                             "title": sub_text,
#                             "url": sub_url
#                         })
#
#         # LEAF (Level 2 children)
#         if current_section and not is_noise(text) and not is_level3(text):
#             if current_subsection is None:
#                 structured[current_section]["children"].append({
#                     "title": text,
#                     "url": url
#                 })
#
#     result[cat["title"]] = {
#         "url": cat["url"],
#         "sections": structured
#     }
#
#
# # -----------------------------
# # DUPLIKAT-CHECK
# # -----------------------------
# def collect_all_urls(result):
#     urls = []
#     for cat_name, cat_data in result.items():
#         urls.append((cat_data["url"], f"[KAT] {cat_name}"))
#         for k, v in cat_data["sections"].items():
#             urls.append((v["url"], f"[L2] {v['title']}"))
#             for child in v["children"]:
#                 urls.append((child["url"], f"[L3-leaf] {child['title']}"))
#             for sk, sv in v["subsections"].items():
#                 urls.append((sv["url"], f"[L3] {sv['title']}"))
#                 for child in sv["children"]:
#                     urls.append((child["url"], f"[L4-leaf] {child['title']}"))
#     return urls
#
#
# all_urls = collect_all_urls(result)
#
# url_counts = {}
# for url, label in all_urls:
#     url_counts.setdefault(url, []).append(label)
#
# duplicates = {url: labels for url, labels in url_counts.items() if len(labels) > 1}
#
# if duplicates:
#     print("=== DUPLIKATE GEFUNDEN ===")
#     for url, labels in duplicates.items():
#         print(f"\n  URL: {url}")
#         for label in labels:
#             print(f"    -> {label}")
# else:
#     print("=== KEINE DUPLIKATE GEFUNDEN ===")
#
#
# # -----------------------------
# # OUTPUT
# # -----------------------------
# for cat_name, cat_data in result.items():
#     print(f"\n{cat_name}, {cat_data['url']}")
#
#     for k, v in cat_data["sections"].items():
#         print(f"  {k} - {v['title']}, {v['url']}")
#
#         for child in v["children"]:
#             print(f"    - {child['title']}, {child['url']}")
#
#         for sk, sv in v["subsections"].items():
#             print(f"    {sk} - {sv['title']}, {sv['url']}")
#
#             for child in sv["children"]:
#                 print(f"      - {child['title']}, {child['url']}")