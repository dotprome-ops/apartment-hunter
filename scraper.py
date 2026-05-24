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

# שכונות לחיפוש
NEIGHBORHOODS = {
    "כוכב הצפון":              198,
    "הצפון החדש - צפון":       204,
    "הצפון הישן - דרום (חן)":  1461,
    "הצפון החדש - כיכר המדינה": 1516,
    "הצפון הישן - צפון":       1483,
}

SEEN_FILE = "seen_listings.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://www.yad2.co.il/",
}


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, ensure_ascii=False)


def fetch_page(neighborhood_id):
    url = (
        "https://www.yad2.co.il/realestate/rent/tel-aviv-area"
        f"?area=1&city=5000&neighborhood={neighborhood_id}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ⚠️  שגיאה בטעינת שכונה {neighborhood_id}: {e}")
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
            "id":           listing_id,
            "url":          f"https://www.yad2.co.il{href}",
            "address":      address,
            "price":        price,
            "rooms":        rooms,
            "sqm":          sqm,
            "floor":        floor,
            "neighborhood": neighborhood_name,
            "has_mamad":    has_mamad,
            "has_parking":  has_parking,
            "has_balcony":  has_balcony,
            "has_elevator": has_elevator,
        })

    return results


def filter_listings(listings):
    return [
        l for l in listings
        if l["price"] <= MAX_PRICE
        and l["rooms"] >= MIN_ROOMS
        and l["sqm"] >= MIN_SQM
    ]


def feature_icon(present):
    return "✅" if present else "❓"


def send_email(new_listings, total_seen):
    if not GMAIL_APP_PASSWORD:
        print("⚠️  GMAIL_APP_PASSWORD לא מוגדר, דילוג על שליחת מייל")
        return

    date_str = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 {len(new_listings)} דירות חדשות | צפון ת\"א | {date_str}"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL

    rows = ""
    for l in new_listings:
        rows += f"""
        <div style="border:1px solid #ddd;padding:16px;margin:12px 0;border-radius:10px;background:#fafafa;">
            <h3 style="margin:0 0 8px 0;">
                <a href="{l['url']}" style="color:#1a73e8;text-decoration:none;">{l['address']}</a>
            </h3>
            <p style="margin:4px 0;font-size:15px;">
                📍 <b>{l['neighborhood']}</b> &nbsp;|&nbsp;
                💰 <b>{l['price']:,} ₪</b> &nbsp;|&nbsp;
                🛏 <b>{l['rooms']} חדרים</b> &nbsp;|&nbsp;
                📐 <b>{l['sqm']} מ"ר</b> &nbsp;|&nbsp;
                🏢 קומה {l['floor']}
            </p>
            <p style="margin:6px 0;font-size:14px;color:#555;">
                {feature_icon(l['has_mamad'])} ממ"ד &nbsp;
                {feature_icon(l['has_parking'])} חניה &nbsp;
                {feature_icon(l['has_balcony'])} מרפסת &nbsp;
                {feature_icon(l['has_elevator'])} מעלית
            </p>
            <a href="{l['url']}"
               style="display:inline-block;margin-top:8px;background:#1a73e8;color:white;
                      padding:8px 18px;border-radius:6px;text-decoration:none;font-size:14px;">
                לצפייה במודעה →
            </a>
        </div>"""

    html = f"""
    <html><body dir="rtl" style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;">
        <h2 style="color:#333;">נמצאו {len(new_listings)} דירות חדשות שמתאימות לקריטריונים שלך</h2>
        <p style="color:#666;border-bottom:1px solid #eee;padding-bottom:10px;">
            <b>קריטריונים:</b> 5+ חדרים &nbsp;|&nbsp; 130+ מ"ר &nbsp;|&nbsp; עד 13,500 ₪ &nbsp;|&nbsp; צפון תל אביב
        </p>
        {rows}
        <p style="color:#999;font-size:12px;margin-top:20px;">
            ❓ = לא מצוין במודעה, כדאי לבדוק &nbsp;|&nbsp; סה"כ דירות במעקב: {total_seen}
        </p>
    </body></html>"""

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ מייל נשלח עם {len(new_listings)} דירות")


def main():
    print(f"🔍 מתחיל חיפוש — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    seen = load_seen()
    all_new = []

    for name, nid in NEIGHBORHOODS.items():
        print(f"  📍 {name}...")
        html     = fetch_page(nid)
        listings = parse_listings(html, name)
        matched  = filter_listings(listings)
        new      = [l for l in matched if l["id"] not in seen]

        all_new.extend(new)
        for l in matched:
            seen.add(l["id"])

        print(f"     נמצאו {len(matched)} תואמות, {len(new)} חדשות")

    save_seen(seen)
    print(f"\n📊 סה\"כ חדשות: {len(all_new)}")

    if all_new:
        send_email(all_new, len(seen))
    else:
        print("אין דירות חדשות היום")


if __name__ == "__main__":
    main()
