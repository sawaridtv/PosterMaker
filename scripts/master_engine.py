import os
import re
import json
import base64
import requests
from io import BytesIO
from datetime import datetime, timedelta
import pytz
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# ⚙️ CONFIGURATION & CREDENTIALS
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRICKET_POSTER_DIR = os.path.join(BASE_DIR, "posters")
FOOTY_POSTER_DIR = os.path.join(BASE_DIR, "footy_posters")

os.makedirs(CRICKET_POSTER_DIR, exist_ok=True)
os.makedirs(FOOTY_POSTER_DIR, exist_ok=True)

# আপনার বর্তমান রিপোজিটরির নাম (পোস্টার লিংকের জন্য)
CURRENT_REPO = os.getenv("GITHUB_REPOSITORY", "your-username/my-sports-poster-engine")
BRANCH_NAME = "main"

# যে রিপোজিটরিতে JSON আপডেট হবে (GitHub Actions Secret থেকে আসবে)
TARGET_REPO = os.getenv("TARGET_REPO", "samnite2290/your-data-repo")
TARGET_JSON_PATH = "matches.json"  # টার্গেট রিপোজিটরিতে ফাইলের লোকেশন
TARGET_GH_PAT = os.getenv("TARGET_REPO_PAT")  # Personal Access Token

# ওয়াটারমার্ক সেটিংস
WATERMARK_TEXT = "@SRHady12"
TELEGRAM_LOGO_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSaSPdPPY4GyA1xREeBCQ7DKXRd-zzddux-SB7CgBQkOg&s=10"

# টাইমজোন (বাংলাদেশ টাইম UTC+6)
TIMEZONE = pytz.timezone("Asia/Dhaka")

# সেশন
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def format_custom_date(dt):
    # Format: 08-11-2026-10:55 00 am
    return dt.strftime("%d-%m-%Y-%I:%M 00 %p").lower()

def auto_crop_and_resize(img, max_w, max_h):
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = int(img.width * ratio)
    new_h = int(img.height * ratio)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def get_font(size):
    possible_paths = [
        os.path.join(BASE_DIR, "assets", "oswald.regular.ttf"),
        os.path.join(BASE_DIR, "scripts", "oswald.regular.ttf"),
        "oswald.regular.ttf"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def get_bg(width, height):
    possible_paths = [
        os.path.join(BASE_DIR, "assets", "bg_cricket.jpg"),
        os.path.join(BASE_DIR, "scripts", "IMG_20260810_004413.jpg")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            bg = Image.open(p).convert('RGBA')
            return bg.resize((width, height), Image.Resampling.LANCZOS)
    return Image.new('RGBA', (width, height), (30, 30, 30, 255))

def fetch_tg_icon():
    try:
        res = session.get(TELEGRAM_LOGO_URL, timeout=8)
        if res.status_code == 200:
            icon = Image.open(BytesIO(res.content)).convert('RGBA')
            size = (200, 200)
            icon = icon.resize(size, Image.Resampling.LANCZOS)
            mask = Image.new('L', size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size[0], size[1]), fill=255)
            circle = Image.composite(icon, Image.new('RGBA', size, (0, 0, 0, 0)), mask)
            b_draw = ImageDraw.Draw(circle)
            b_draw.ellipse((2, 2, size[0] - 3, size[1] - 3), outline=(0, 0, 0, 255), width=8)
            return circle.resize((80, 80), Image.Resampling.LANCZOS)
    except:
        pass
    return None

# ==========================================
# 🎨 POSTER CREATION LOGIC
# ==========================================
def draw_poster(match_title, img1_bytes, img2_bytes, save_path, is_football=False):
    try:
        img1 = Image.open(BytesIO(img1_bytes)).convert('RGBA')
        img2 = Image.open(BytesIO(img2_bytes)).convert('RGBA')

        if is_football:
            # Football: 1080x810 Transparent Canvas
            canvas = Image.new('RGBA', (1080, 810), (0, 0, 0, 0))
            img1 = auto_crop_and_resize(img1, 480, 600)
            img2 = auto_crop_and_resize(img2, 480, 600)
            canvas.paste(img1, (270 - (img1.width // 2), 405 - (img1.height // 2)), img1)
            canvas.paste(img2, (810 - (img2.width // 2), 405 - (img2.height // 2)), img2)
        else:
            # Cricket: 1080x700 with BG & Watermark
            canvas = get_bg(1080, 700)
            img1 = auto_crop_and_resize(img1, 480, 600)
            img2 = auto_crop_and_resize(img2, 480, 600)

            border_color = (0, 0, 0, 255)
            for img in [img1, img2]:
                d = ImageDraw.Draw(img)
                d.rectangle([(0, 0), (img.width - 1, img.height - 1)], outline=border_color, width=10)

            canvas.paste(img1, (270 - (img1.width // 2), 350 - (img1.height // 2)), img1)
            canvas.paste(img2, (810 - (img2.width // 2), 350 - (img2.height // 2)), img2)

            tg_icon = fetch_tg_icon()
            font = get_font(70)
            draw = ImageDraw.Draw(canvas)
            bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
            text_h = bbox[3] - bbox[1]
            start_y = 700 - 45 - max(80 if tg_icon else 0, text_h)

            if tg_icon:
                canvas.paste(tg_icon, (50, int(start_y)), tg_icon)
                draw.text((150, start_y + (80 - text_h) // 2), WATERMARK_TEXT, fill=(0, 0, 0, 255), font=font)

        quantized = canvas.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
        quantized.save(save_path, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"Error drawing poster for {match_title}: {e}")
        return False

# ==========================================
# 🕒 BREAK-TIME & INTERVAL CALCULATION
# ==========================================
def calculate_sport_times(start_dt, sport_type, match_format="T20"):
    """
    start_dt: ম্যাচ শুরুর আসল সময়
    Notification: খেলা শুরুর ৫ মিনিট আগে (date_and_time)
    multipleTime: বিরতির সময় (2nd innings / 2nd half resumption)
    """
    notif_start = start_dt - timedelta(minutes=5)
    date_and_time_str = format_custom_date(notif_start)

    mult_run = "On"
    break_target = None

    sport = sport_type.lower()
    fmt = str(match_format).upper()

    if "football" in sport:
        # ফুটবল: ৪৫ মিনিট খেলা + ১৫ মিনিট হাফটাইম = ৬০ মিনিট পর ২য় হাফ
        # হাফটাইম শেষ হওয়ার ২ মিনিট আগে নোটিফিকেশন পাঠাতে চাইলে ৫৮-৬০ মিনিট
        break_target = start_dt + timedelta(minutes=60)

    elif "cricket" in sport:
        if "T10" in fmt:
            # T10: ৪৫ মিনিট পর বিরতি শেষ
            break_target = start_dt + timedelta(minutes=50)
        elif "T20" in fmt or "T20I" in fmt:
            # T20: সাধারণত ১ ঘণ্টা ৩৫ মিনিট পর ২য় ইনিংস
            break_target = start_dt + timedelta(hours=1, minutes=35)
        elif "ODI" in fmt:
            # ODI: ইনিংস ব্রেক ৩ ঘণ্টা ৪৫ মিনিট পর
            break_target = start_dt + timedelta(hours=3, minutes=45)
        elif "TEST" in fmt:
            # টেস্ট: লাঞ্চ ব্রেক (২ ঘণ্টা পর)
            break_target = start_dt + timedelta(hours=2, minutes=40)
        else:
            break_target = start_dt + timedelta(hours=1, minutes=35)
    else:
        mult_run = "Off"

    if break_target:
        mult_time_str = f"({format_custom_date(break_target)})"
    else:
        mult_run = "Off"
        mult_time_str = f"({format_custom_date(start_dt + timedelta(hours=1))})"

    return date_and_time_str, mult_run, mult_time_str

# ==========================================
# 🏏 PROCESS CRICBUZZ MATCHES
# ==========================================
def process_cricbuzz():
    json_entries = []
    print("\n🔍 Fetching Cricbuzz...")
    try:
        res = session.get("https://www.cricbuzz.com/api/home", timeout=15)
        if res.status_code != 200: return []
        data = res.json()
        matches = data.get("matches", [])
        
        now = datetime.now(pytz.utc)

        for item in matches:
            info = item.get("match", {}).get("matchInfo", {})
            start_ms = info.get("startDate", 0)
            end_ms = info.get("endDate", start_ms + (4 * 3600 * 1000))
            if not start_ms: continue

            start_dt_utc = datetime.fromtimestamp(start_ms / 1000, tz=pytz.utc)
            end_dt_utc = datetime.fromtimestamp(end_ms / 1000, tz=pytz.utc)

            # আগামী ৪ ঘণ্টা থেকে শুরু করে লাইভ ম্যাচ
            if (start_dt_utc - timedelta(hours=4)) <= now <= (end_dt_utc + timedelta(hours=1)):
                t1 = info.get("team1", {})
                t2 = info.get("team2", {})
                t1_name = t1.get("teamName")
                t2_name = t2.get("teamName")
                t1_id = t1.get("imageId")
                t2_id = t2.get("imageId")

                if not (t1_name and t2_name and t1_id and t2_id): continue

                match_title = f"{t1_name} vs {t2_name}"
                safe_title = sanitize_filename(match_title)
                filename = f"{safe_title}.png"
                poster_path = os.path.join(CRICKET_POSTER_DIR, filename)

                raw_poster_url = f"https://raw.githubusercontent.com/{CURRENT_REPO}/{BRANCH_NAME}/posters/{filename}"

                # পোস্টার না থাকলে বানানো হবে
                if not os.path.exists(poster_path):
                    s1 = re.sub(r'\s+', '-', t1_name).lower()
                    s2 = re.sub(r'\s+', '-', t2_name).lower()
                    u1 = f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t1_id}/{s1}.jpg"
                    u2 = f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t2_id}/{s2}.jpg"

                    r1 = session.get(u1, timeout=10)
                    r2 = session.get(u2, timeout=10)
                    if r1.status_code == 200 and r2.status_code == 200:
                        draw_poster(match_title, r1.content, r2.content, poster_path, is_football=False)

                # লোকাল টাইমজোনে কনভার্ট
                start_dt_local = start_dt_utc.astimezone(TIMEZONE)
                match_format = info.get("matchFormat", "T20")
                series_name = info.get("seriesName", "CRICKET SERIES")

                dt_str, mult_run, mult_time = calculate_sport_times(start_dt_local, "cricket", match_format)

                entry = {
                    "Date & Time": dt_str,
                    "multipleTimeRun": mult_run,
                    "multipleTime": mult_time,
                    "Title": f"{t1_name} 🆚 {t2_name} ({match_format}) । Live Stream",
                    "Subtitle": f"🏏 {series_name.upper()} | Select 🅻🅸🆅🅴 🆂🅿🅾🆁🆃🆂 Button, Share Our Apps.",
                    "Image": raw_poster_url
                }
                json_entries.append(entry)

    except Exception as e:
        print(f"Cricbuzz Error: {e}")

    return json_entries

# ==========================================
# ⚽ PROCESS FOOTYSTREAM MATCHES
# ==========================================
def process_footystream():
    json_entries = []
    print("\n🔍 Fetching Footystream...")
    try:
        res = session.get("https://footystream.pk/", timeout=15)
        if res.status_code != 200: return []
        html = res.text

        events = re.findall(r'<a[^>]*href=["\'](?:https://footystream\.pk)?/events/([^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.IGNORECASE)
        now_utc = datetime.now(pytz.utc)

        for slug, content in events:
            if "-vs-" not in slug: continue
            start_m = re.search(r'data-start=["\']([^"\']+)["\']', content)
            end_m = re.search(r'data-end=["\']([^"\']+)["\']', content)

            if start_m and end_m:
                try:
                    start_utc = datetime.strptime(start_m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc)
                    end_utc = datetime.strptime(end_m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc)

                    # ম্যাচ যদি আর ৩০ মিনিট পর থাকে অথবা চলমান থাকে
                    if (start_utc - timedelta(minutes=45)) <= now_utc <= end_utc:
                        team_divs = re.findall(r'<div[^>]*class=["\'][^"\']*flex gap-2 items-center[^"\']*["\'][^>]*>([\s\S]*?)</div>', content)
                        teams = []
                        images = []

                        for tm in team_divs:
                            t_name = re.sub(r'<[^>]+>', '', tm).strip()
                            if t_name: teams.append(t_name)
                            im = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', tm)
                            if im: images.append(im.group(1))

                        if len(teams) >= 2 and len(images) >= 2:
                            match_title = f"{teams[0]} vs {teams[1]}"
                            safe_title = sanitize_filename(match_title)
                            filename = f"{safe_title}.png"
                            poster_path = os.path.join(FOOTY_POSTER_DIR, filename)

                            raw_poster_url = f"https://raw.githubusercontent.com/{CURRENT_REPO}/{BRANCH_NAME}/footy_posters/{filename}"

                            if not os.path.exists(poster_path):
                                u1 = images[0] if images[0].startswith('http') else "https://footystream.pk" + images[0]
                                u2 = images[1] if images[1].startswith('http') else "https://footystream.pk" + images[1]
                                r1 = session.get(u1, timeout=10)
                                r2 = session.get(u2, timeout=10)
                                if r1.status_code == 200 and r2.status_code == 200:
                                    draw_poster(match_title, r1.content, r2.content, poster_path, is_football=True)

                            start_local = start_utc.astimezone(TIMEZONE)
                            dt_str, mult_run, mult_time = calculate_sport_times(start_local, "football")

                            entry = {
                                "Date & Time": dt_str,
                                "multipleTimeRun": mult_run,
                                "multipleTime": mult_time,
                                "Title": f"{teams[0]} 🆚 {teams[1]} । Watch Live",
                                "Subtitle": "🏆 FOOTBALL LEAGUE LIVE | Select 🅻🅸🆅🅴 🆂🅿🅾🆁🆃🆂 Button, Share Our Apps.",
                                "Image": raw_poster_url
                            }
                            json_entries.append(entry)
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Footy Error: {e}")

    return json_entries

# ==========================================
# 🚀 PUSH JSON TO EXTERNAL GITHUB REPO
# ==========================================
def push_json_to_remote_repo(data):
    if not TARGET_GH_PAT:
        print("⚠️ TARGET_REPO_PAT is not set. Saving JSON locally only.")
        with open("matches.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return

    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{TARGET_JSON_PATH}"
    headers = {
        "Authorization": f"Bearer {TARGET_GH_PAT}",
        "Accept": "application/vnd.github.v3+json"
    }

    print(f"\n📡 Updating JSON in remote repo: {TARGET_REPO} ...")
    content_str = json.dumps(data, indent=2, ensure_ascii=False)
    content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    sha = None
    # Check if file exists to get current sha
    res = requests.get(api_url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get('sha')

    payload = {
        "message": "⚡ Auto-update matches & notification schedules",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    put_res = requests.put(api_url, headers=headers, json=payload)
    if put_res.status_code in [200, 201]:
        print("✅ Remote JSON successfully updated!")
    else:
        print(f"❌ Failed to push JSON. Status: {put_res.status_code}, Response: {put_res.text}")

# ==========================================
# 🏁 MAIN
# ==========================================
def main():
    cricket_matches = process_cricbuzz()
    football_matches = process_footystream()

    all_matches = cricket_matches + football_matches

    # লোকাল রিপোজিটরিতে সেভ রাখা
    local_json = os.path.join(BASE_DIR, "matches.json")
    with open(local_json, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, indent=2, ensure_ascii=False)

    # টার্গেট রিপোজিটরিতে পুশ করা
    push_json_to_remote_repo(all_matches)
    print(f"\n🎉 Completed! Total {len(all_matches)} matches scheduled.")

if __name__ == "__main__":
    main()
