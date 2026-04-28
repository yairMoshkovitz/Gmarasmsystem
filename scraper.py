"""
Scraper for dafyomi.co.il - Review Questions & Answers
מסכתות: ברכות ושבת

הרצה:
    pip install requests beautifulsoup4
    python scraper.py

פלט:
    berachos_qa.json
    shabbos_qa.json
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re

# ===== הגדרות =====

MASECHTOS = {
    "berachos": {
        "name_he": "ברכות",
        "prefix": "br",
        "daf_start": 2,
        "daf_end": 64,
        "q_path": "revques/{prefix}-rq-{daf}.htm",
        "a_path": "revans/{prefix}-ra-{daf}.htm",
    },
    "shabbos": {
        "name_he": "שבת",
        "prefix": "sh",
        "daf_start": 2,
        "daf_end": 157,
        "q_path": "revques/{prefix}-rq-{daf}.htm",
        "a_path": "revans/{prefix}-ra-{daf}.htm",
    },
}

BASE = "https://www.dafyomi.co.il"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TalmudStudy/1.0)"}
DELAY = 1.0

# ===== שליפה =====

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding
            return BeautifulSoup(r.text, "html.parser")
        print(f"  HTTP {r.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  שגיאה: {e}")
        return None


def build_url(masechet_key, path_tpl, daf_num):
    m = MASECHTOS[masechet_key]
    daf_str = str(daf_num).zfill(3)
    path = path_tpl.format(prefix=m["prefix"], daf=daf_str)
    return f"{BASE}/{masechet_key}/{path}"


# ===== פירוס =====

SKIP_PHRASES = [
    "review questions", "review answers", "maseches", "copyright",
    "kollel", "dafyomi", "prepared by", "rosh kollel", "daf@"
]

def is_content(text):
    t = text.lower()
    return not any(s in t for s in SKIP_PHRASES) and len(text) > 12


def parse_numbered(soup, end_marker="?"):
    """מחלץ פריטים ממוספרים מדף"""
    if not soup:
        return []
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)

    items = []
    # תבנית: מספר + נקודה/סוגר
    chunks = re.split(r"\n\s*(\d+)\s*[.)]\s*", text)

    i = 1
    while i < len(chunks) - 1:
        content = chunks[i + 1].strip()
        # קח עד הפסקה הבאה
        content = content.split("\n\n")[0]
        content = re.sub(r"\s+", " ", content).strip()
        if is_content(content):
            items.append(content)
        i += 2

    return items


def scrape_masechet(masechet_key):
    m = MASECHTOS[masechet_key]
    print(f"\n{'='*55}")
    print(f"  מסכת {m['name_he']} | דפים {m['daf_start']}–{m['daf_end']}")
    print(f"{'='*55}")

    dafs = {}
    total_q = 0

    for daf_num in range(m["daf_start"], m["daf_end"] + 1):
        q_url = build_url(masechet_key, m["q_path"], daf_num)
        a_url = build_url(masechet_key, m["a_path"], daf_num)

        print(f"  דף {daf_num:>3}...", end=" ", flush=True)

        q_soup = fetch(q_url)
        time.sleep(DELAY)
        a_soup = fetch(a_url)
        time.sleep(DELAY)

        questions = parse_numbered(q_soup)
        answers   = parse_numbered(a_soup)

        pairs = []
        for i, q in enumerate(questions):
            ans = answers[i] if i < len(answers) else ""
            pairs.append({
                "question_en": q,
                "answer_en":   ans,
                "question_he": "",
                "answer_he":   "",
            })

        print(f"{len(pairs)} שאלות")
        total_q += len(pairs)
        dafs[str(daf_num)] = pairs

    print(f"\n  סה\"כ: {total_q} שאלות ב-{len(dafs)} דפים")
    return dafs


def save(masechet_key, dafs, out_dir="."):
    m = MASECHTOS[masechet_key]
    path = f"{out_dir}/{masechet_key}_qa.json"
    data = {
        "masechet":        masechet_key,
        "name_he":         m["name_he"],
        "source":          "dafyomi.co.il",
        "translated":      False,
        "total_dafs":      len(dafs),
        "total_questions": sum(len(v) for v in dafs.values()),
        "dafs":            dafs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  נשמר: {path}")
    return path


if __name__ == "__main__":
    print("Scraper - dafyomi.co.il | ברכות + שבת\n")
    for key in ["berachos", "shabbos"]:
        dafs = scrape_masechet(key)
        save(key, dafs)
    print("\nסיום! הרץ: python translate_questions.py")