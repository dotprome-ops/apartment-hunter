import requests
import json
import re
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from datetime import datetime

# ===== הגדרות =====
RECIPIENT_EMAIL = "ACE.DORON@GMAIL.COM"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "ACE.DORON@GMAIL.COM")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

MAX_PRICE = 13500
MIN_ROOMS = 5
MIN_SQM = 130

NEIGHBORHOODS = {
    "כוכב הצפון":               198,
    "הצפון החדש - צפון":        204,
    "הצפון הישן - דרום (חן)":   1461,
    "הצפון החדש - כיכר המדינה": 1516,
    "הצפון הישן - צפון":        1483,
}

SEEN_FILE = "seen_listings.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, ensure_ascii=False)


def fetch_page(neighborhood_id, ua_index=0):
    url = (
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area"
        f"?area=1&city=5000&neighborhood={neighborhood_id}"
    )
    headers = {
        "User-Agent": USER_AGENTS[ua_index % len(USER_AGENTS)],
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }
    try:
        session = requests.Session()
        session.get("https://www.yad2.co.il/", headers=headers, timeout=15)
        resp = session.get(url, headers=headers, timeout=20)
        print(f"  HTTP {resp.status_code} | {len(resp.text)} chars")
        if "realestate/item" in resp.text:
            count = resp.text.count("realestate/item")
            print(f"  נמצאו {count} אזכורים של מודעות ב-HTML")
        else:
            print(f"  אין מודעות ב-HTML — יד2 כנראה חוסמת")
            print(f"  תחילת תגובה: {resp.text[:200]}")
        return resp.text
    except Exception as e:
        print(f"  שגיאה: {e}")
        return None


def parse_listings(html, neighborhood_name):
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen_ids = set()
    for link in soup.find_all("a", href=re.compile(r"/realestate/item/")):
        href = link.get("href", "")
        id_match = re.search(r"/realestate/item/[^/]+/([a-z0-9]+)", href)
        if not id_match:
            continue
        listing_id = id_match.group(1)
        if listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)
        text = link.get_text(" ", strip=True)
        price_m = re.search(r"₪\s*([\d,]+)", text)
        rooms_m = re.search(r"([\d.]+)\s+חדרים", text)
        sqm_m   = re.search(r"(\d+)\s+מ[״\"]ר", text)
        if not (price_m and rooms_m and sqm_m):
            continue
        price = int(price_m.group(1).replace(",", ""))
        rooms = float(rooms_m.group(1))
        sqm   = int(sqm_m.group(1))
        floor_m = re.search(r"קומה\s+([^\s•]+)", text)
        floor = floor_m.group(1) if floor_m else "?"
        has_mamad    = bool(re.search(r'ממ["\']?ד|ממד', text))
        has_parking  = "חניה" in text
        has_balcony  = "מרפסת" in text
        has_elevator = "מעלית" in text
        address = re.split(r"₪|דירה|גג|פנטהאוז|דופלקס", text)[0].strip()[:70]
        results.append({
            "id": listing_id, "url": f"https://www.yad2.co.il{href}",
            "address": address, "price": price, "rooms": rooms,
            "sqm": sqm, "floor": floor, "neighborhood": neighborhood_name,
            "has_mamad": has_mamad, "has_parking": has_parking,
            "has_balcony": has_balcony, "has_elevator": has_elevator,
        })
    print(f"  פורסרו {len(results)} מודעות עם פרטים מלאים")
    return results


def filter_listings(listings):
    filtered = [l for l in listings if l["price"] <= MAX_PRICE and l["rooms"] >= MIN_ROOMS and l["sqm"] >= MIN_SQM]
    print(f"  אחרי סינון: {len(filtered)} תואמות")
    return filtered


def feature_icon(present):
    return "v" if present else "?"


def send_email(new_listings, total_seen):
    if not GMAIL_APP_PASSWORD:
        print("GMAIL_APP_PASSWORD לא מוגדר")
        return
    date_str = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"דירות חדשות | צפון תל אביב | {date_str}"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    rows = ""
    for l in new_listings:
        rows += f"""
        <div style="border:1px solid #ddd;padding:16px;margin:12px 0;border-radius:10px;">
            <h3><a href="{l['url']}">{l['address']}</a></h3>
            <p>{l['neighborhood']} | {l['price']:,} שקל | {l['rooms']} חדרים | {l['sqm']} מ"ר | קומה {l['floor']}</p>
            <p>{feature_icon(l['has_mamad'])} ממ"ד | {feature_icon(l['has_parking'])} חניה | {feature_icon(l['has_balcony'])} מרפסת | {feature_icon(l['has_elevator'])} מעלית</p>
            <a href="{l['url']}">לצפייה במודעה</a>
        </div>"""
    html = f"<html><body dir='rtl'><h2>נמצאו {len(new_listings)} דירות חדשות</h2>{rows}</body></html>"
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"מייל נשלח עם {len(new_listings)} דירות")


def main():
    print(f"מתחיל חיפוש — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    seen = load_seen()
    all_new = []
    for i, (name, nid) in enumerate(NEIGHBORHOODS.items()):
        print(f"\n{name}...")
        html     = fetch_page(nid, ua_index=i)
        listings = parse_listings(html, name)
        matched  = filter_listings(listings)
        new      = [l for l in matched if l["id"] not in seen]
        all_new.extend(new)
        for l in matched:
            seen.add(l["id"])
    save_seen(seen)
    print(f"\nסה\"כ חדשות: {len(all_new)}")
    if all_new:
        send_email(all_new, len(seen))
    else:
        print("אין דירות חדשות היום")


if __name__ == "__main__":
    main()
