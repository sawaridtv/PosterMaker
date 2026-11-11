import os
import re
import json
import base64
import requests
from io import BytesIO
from datetime import datetime, timedelta
import pytz
from PIL import Image, ImageDraw, ImageFont

# ==============================================================================
# ⚙️ GLOBAL CONFIGURATION
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CRICKET_POSTER_DIR = os.path.join(BASE_DIR, "posters")
FOOTY_POSTER_DIR = os.path.join(BASE_DIR, "footy_posters")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(CRICKET_POSTER_DIR, exist_ok=True)
os.makedirs(FOOTY_POSTER_DIR, exist_ok=True)

# Repository configuration
CURRENT_REPO = os.getenv("GITHUB_REPOSITORY", "sawaridtv/PosterMaker")
BRANCH_NAME = "main"

# Remote JSON target repository settings
TARGET_REPO = os.getenv("TARGET_REPO", "samnite2290/your-data-repo")
TARGET_JSON_PATH = "matches.json"
TARGET_GH_PAT = os.getenv("TARGET_REPO_PAT")

# Timezone (UTC+6)
TIMEZONE = pytz.timezone("Asia/Dhaka")

# Watermark & Branding
WATERMARK_TEXT = "SAWARID سواريد"
LOCAL_LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

# Background Image Setting:
# Put your background image in assets/background.jpg (or assets/bg_cricket.jpg)
BG_IMAGE_PATH = os.path.join(ASSETS_DIR, "background.jpg")
BG_FALLBACK_URL = "https://raw.githubusercontent.com/sawaridtv/PosterMaker/main/assets/background.jpg"

# Google Font for English + Arabic character rendering
ARABIC_FONT_PATH = os.path.join(ASSETS_DIR, "cairo_arabic.ttf")
FONT_DOWNLOAD_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/Cairo-Bold.ttf"

# Requests session
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ==============================================================================
# 🛠️ HELPER FUNCTIONS
# ==============================================================================
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def format_custom_date(dt):
    # Output format: 08-11-2026-10:55 00 am
    return dt.strftime("%d-%m-%Y-%I:%M 00 %p").lower()

def auto_crop_and_resize(img, max_w, max_h):
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def get_arabic_english_font(size):
    """Loads a font supporting both Arabic and English to avoid square boxes"""
    if not os.path.exists(ARABIC_FONT_PATH):
        try:
            print("[*] Downloading Arabic font (Cairo)...")
            res = session.get(FONT_DOWNLOAD_URL, timeout=15)
            if res.status_code == 200:
                with open(ARABIC_FONT_PATH, "wb") as f:
                    f.write(res.content)
        except Exception as e:
            print(f"[!] Font download failed: {e}")

    candidates = [
        ARABIC_FONT_PATH,
        os.path.join(ASSETS_DIR, "oswald.regular.ttf"),
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def load_background(width, height):
    """Loads local background image or falls back to remote URL or gradient"""
    candidates = [
        BG_IMAGE_PATH,
        os.path.join(ASSETS_DIR, "bg_cricket.jpg"),
        os.path.join(BASE_DIR, "scripts", "IMG_20260810_004413.jpg")
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                bg = Image.open(path).convert('RGBA')
                return bg.resize((width, height), Image.Resampling.LANCZOS)
            except Exception:
                pass

    try:
        res = session.get(BG_FALLBACK_URL, timeout=8)
        if res.status_code == 200:
            bg = Image.open(BytesIO(res.content)).convert('RGBA')
            return bg.resize((width, height), Image.Resampling.LANCZOS)
    except Exception:
        pass

    return Image.new('RGBA', (width, height), (15, 23, 42, 255))

# ==============================================================================
# 🎨 POSTER GENERATOR ENGINE
# ==============================================================================
def create_match_poster(match_title, img1_bytes, img2_bytes, save_path, league_logo_bytes=None):
    try:
        width, height = 1080, 720
        canvas = load_background(width, height)

        img1 = Image.open(BytesIO(img1_bytes)).convert('RGBA')
        img2 = Image.open(BytesIO(img2_bytes)).convert('RGBA')

        # Crop and resize team logos
        img1 = auto_crop_and_resize(img1, 380, 400)
        img2 = auto_crop_and_resize(img2, 380, 400)

        # Team positioning
        pos_y = 330
        x1 = 270 - (img1.width // 2)
        y1 = pos_y - (img1.height // 2)
        x2 = 810 - (img2.width // 2)
        y2 = pos_y - (img2.height // 2)

        canvas.paste(img1, (x1, y1), img1)
        canvas.paste(img2, (x2, y2), img2)

        # --- PASTE LEAGUE/TOURNAMENT LOGO (SCRAPED DIRECTLY FROM SOURCE) ---
        if league_logo_bytes:
            try:
                l_img = Image.open(BytesIO(league_logo_bytes)).convert('RGBA')
                l_img = auto_crop_and_resize(l_img, 150, 95)
                bx = (width // 2) - (l_img.width // 2)
                by = 40
                canvas.paste(l_img, (bx, by), l_img)
            except Exception as e:
                print(f"[!] Could not render league logo: {e}")

        # --- DRAW CENTER "VS" BADGE ---
        draw = ImageDraw.Draw(canvas)
        vs_center_x, vs_center_y = 540, 330
        vs_font = get_arabic_english_font(40)
        r = 45

        draw.ellipse((vs_center_x - r, vs_center_y - r, vs_center_x + r, vs_center_y + r), 
                     fill=(10, 10, 10, 200), outline=(255, 215, 0, 255), width=3)
        
        vs_bbox = draw.textbbox((0, 0), "VS", font=vs_font)
        vs_w = vs_bbox[2] - vs_bbox[0]
        vs_h = vs_bbox[3] - vs_bbox[1]
        draw.text((vs_center_x - (vs_w // 2), vs_center_y - (vs_h // 2) - 3), "VS", fill=(255, 255, 255, 255), font=vs_font)

        # --- DRAW WATERMARK & LOCAL LOGO (BOTTOM-LEFT) ---
        font_size = 46
        wm_font = get_arabic_english_font(font_size)
        padding_left = 50
        padding_bottom = 35

        logo_img = None
        if os.path.exists(LOCAL_LOGO_PATH):
            try:
                logo_raw = Image.open(LOCAL_LOGO_PATH).convert('RGBA')
                logo_img = auto_crop_and_resize(logo_raw, 75, 75)
            except Exception as e:
                print(f"[!] Error loading local logo: {e}")

        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=wm_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        logo_w = logo_img.width if logo_img else 0
        logo_h = logo_img.height if logo_img else 0

        element_height = max(logo_h, text_h)
        base_y = height - padding_bottom - element_height

        # Paste logo as-is without circular cuts or extra borders
        if logo_img:
            logo_y = base_y + (element_height - logo_h) // 2
            canvas.paste(logo_img, (padding_left, int(logo_y)), logo_img)

        # Draw Watermark text
        text_x = padding_left + logo_w + 16 if logo_img else padding_left
        text_y = base_y + (element_height - text_h) // 2

        # Shadow and main text
        draw.text((text_x + 2, text_y + 2), WATERMARK_TEXT, fill=(0, 0, 0, 240), font=wm_font)
        draw.text((text_x, text_y), WATERMARK_TEXT, fill=(255, 255, 255, 255), font=wm_font)

        # Optimize size
        quantized = canvas.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
        quantized.save(save_path, "PNG", optimize=True)
        return True

    except Exception as e:
        print(f"[!] Poster generation error for '{match_title}': {e}")
        return False

# ==============================================================================
# 🕒 MATCH TIMING & NOTIFICATION LOGIC
# ==============================================================================
def calculate_sport_times(start_dt, sport_type, match_format="T20"):
    notif_start = start_dt - timedelta(minutes=5)
    date_and_time_str = format_custom_date(notif_start)

    mult_run = "On"
    sport = sport_type.lower()
    fmt = str(match_format).upper()

    if "football" in sport:
        # Halftime break resumption: 45 min + 15 min break = 60 minutes
        break_target = start_dt + timedelta(minutes=60)
    elif "cricket" in sport:
        if "T10" in fmt:
            break_target = start_dt + timedelta(minutes=50)
        elif "T20" in fmt or "T20I" in fmt:
            break_target = start_dt + timedelta(hours=1, minutes=35)
        elif "ODI" in fmt:
            break_target = start_dt + timedelta(hours=3, minutes=45)
        elif "TEST" in fmt:
            break_target = start_dt + timedelta(hours=2, minutes=40)
        else:
            break_target = start_dt + timedelta(hours=1, minutes=35)
    else:
        mult_run = "Off"
        break_target = start_dt + timedelta(hours=1)

    mult_time_str = f"({format_custom_date(break_target)})"
    return date_and_time_str, mult_run, mult_time_str

# ==============================================================================
# 🏏 PROCESS CRICBUZZ MATCHES
# ==============================================================================
def process_cricbuzz():
    json_entries = []
    print("\n[+] Fetching matches from Cricbuzz API...")
    try:
        res = session.get("https://www.cricbuzz.com/api/home", timeout=15)
        if res.status_code != 200:
            return []
            
        data = res.json()
        matches = data.get("matches", [])
        now_utc = datetime.now(pytz.utc)

        for item in matches:
            info = item.get("match", {}).get("matchInfo", {})
            start_ms = info.get("startDate", 0)
            end_ms = info.get("endDate", start_ms + (4 * 3600 * 1000))
            if not start_ms:
                continue

            start_dt_utc = datetime.fromtimestamp(start_ms / 1000, tz=pytz.utc)
            end_dt_utc = datetime.fromtimestamp(end_ms / 1000, tz=pytz.utc)

            if (start_dt_utc - timedelta(hours=4)) <= now_utc <= (end_dt_utc + timedelta(hours=1)):
                t1 = info.get("team1", {})
                t2 = info.get("team2", {})
                t1_name = t1.get("teamName")
                t2_name = t2.get("teamName")
                t1_id = t1.get("imageId")
                t2_id = t2.get("imageId")

                if not (t1_name and t2_name and t1_id and t2_id):
                    continue

                match_title = f"{t1_name} vs {t2_name}"
                series_name = info.get("seriesName", "Cricket Series")
                match_format = info.get("matchFormat", "T20")

                safe_title = sanitize_filename(match_title)
                filename = f"{safe_title}.png"
                poster_path = os.path.join(CRICKET_POSTER_DIR, filename)
                raw_poster_url = f"https://raw.githubusercontent.com/{CURRENT_REPO}/{BRANCH_NAME}/posters/{filename}"

                if not os.path.exists(poster_path):
                    s1 = re.sub(r'\s+', '-', t1_name).lower()
                    s2 = re.sub(r'\s+', '-', t2_name).lower()
                    u1 = f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t1_id}/{s1}.jpg"
                    u2 = f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t2_id}/{s2}.jpg"

                    r1 = session.get(u1, timeout=10)
                    r2 = session.get(u2, timeout=10)

                    # Extract Series / Tournament Logo directly from Cricbuzz
                    series_logo_bytes = None
                    series_id = info.get("seriesId") or info.get("series", {}).get("id")
                    if series_id:
                        s_slug = re.sub(r'\s+', '-', series_name).lower()
                        s_url = f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{series_id}/{s_slug}.jpg"
                        try:
                            s_res = session.get(s_url, timeout=5)
                            if s_res.status_code == 200:
                                series_logo_bytes = s_res.content
                        except Exception:
                            pass

                    if r1.status_code == 200 and r2.status_code == 200:
                        print(f"    🎨 Designing poster: {match_title}")
                        create_match_poster(match_title, r1.content, r2.content, poster_path, league_logo_bytes=series_logo_bytes)

                start_dt_local = start_dt_utc.astimezone(TIMEZONE)
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
        print(f"[!] Cricbuzz Error: {e}")

    return json_entries

# ==============================================================================
# ⚽ PROCESS FOOTYSTREAM MATCHES
# ==============================================================================
def process_footystream():
    json_entries = []
    print("\n[+] Fetching matches from Footystream...")
    try:
        res = session.get("https://footystream.pk/", timeout=15)
        if res.status_code != 200:
            return []
            
        html = res.text
        events = re.findall(r'<a[^>]*href=["\'](?:https://footystream\.pk)?/events/([^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.IGNORECASE)
        now_utc = datetime.now(pytz.utc)

        for slug, content in events:
            if "-vs-" not in slug:
                continue

            start_m = re.search(r'data-start=["\']([^"\']+)["\']', content)
            end_m = re.search(r'data-end=["\']([^"\']+)["\']', content)

            if start_m and end_m:
                try:
                    start_utc = datetime.strptime(start_m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc)
                    end_utc = datetime.strptime(end_m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc)

                    if (start_utc - timedelta(minutes=45)) <= now_utc <= end_utc:
                        # Extract all images in event container
                        all_imgs = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', content, re.IGNORECASE)

                        # Extract team names and team images
                        team_divs = re.findall(r'<div[^>]*class=["\'][^"\']*flex gap-2 items-center[^"\']*["\'][^>]*>([\s\S]*?)</div>', content)
                        teams = []
                        team_images = []

                        for tm in team_divs:
                            t_name = re.sub(r'<[^>]+>', '', tm).strip()
                            if t_name:
                                teams.append(t_name)
                            im = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', tm)
                            if im:
                                team_images.append(im.group(1))

                        # Detect league logo directly: Any image in event card that is NOT a team logo
                        league_logo_url = None
                        for img_url in all_imgs:
                            if img_url not in team_images:
                                league_logo_url = img_url
                                break

                        if len(teams) >= 2 and len(team_images) >= 2:
                            match_title = f"{teams[0]} vs {teams[1]}"
                            safe_title = sanitize_filename(match_title)
                            filename = f"{safe_title}.png"
                            poster_path = os.path.join(FOOTY_POSTER_DIR, filename)
                            raw_poster_url = f"https://raw.githubusercontent.com/{CURRENT_REPO}/{BRANCH_NAME}/footy_posters/{filename}"

                            if not os.path.exists(poster_path):
                                u1 = team_images[0] if team_images[0].startswith('http') else "https://footystream.pk" + team_images[0]
                                u2 = team_images[1] if team_images[1].startswith('http') else "https://footystream.pk" + team_images[1]
                                
                                r1 = session.get(u1, timeout=10)
                                r2 = session.get(u2, timeout=10)

                                # Fetch league logo directly from Footystream
                                league_bytes = None
                                if league_logo_url:
                                    if not league_logo_url.startswith('http'):
                                        league_logo_url = "https://footystream.pk" + league_logo_url
                                    try:
                                        l_res = session.get(league_logo_url, timeout=8)
                                        if l_res.status_code == 200:
                                            league_bytes = l_res.content
                                    except Exception:
                                        pass

                                if r1.status_code == 200 and r2.status_code == 200:
                                    print(f"    🎨 Designing poster: {match_title}")
                                    create_match_poster(match_title, r1.content, r2.content, poster_path, league_logo_bytes=league_bytes)

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
                except Exception:
                    continue

    except Exception as e:
        print(f"[!] Footystream Error: {e}")

    return json_entries

# ==============================================================================
# 🚀 PUSH JSON TO TARGET GITHUB REPOSITORY
# ==============================================================================
def push_json_to_remote_repo(data):
    if not TARGET_GH_PAT:
        print("[!] TARGET_REPO_PAT is not set. Saving JSON locally only.")
        with open("matches.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return

    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{TARGET_JSON_PATH}"
    headers = {
        "Authorization": f"Bearer {TARGET_GH_PAT}",
        "Accept": "application/vnd.github.v3+json"
    }

    print(f"\n[+] Syncing JSON to remote repository: {TARGET_REPO} ...")
    content_str = json.dumps(data, indent=2, ensure_ascii=False)
    content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    sha = None
    res = requests.get(api_url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get('sha')

    payload = {
        "message": "⚡ Auto-update match schedules and posters",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    put_res = requests.put(api_url, headers=headers, json=payload)
    if put_res.status_code in [200, 201]:
        print("[+] Remote matches.json successfully updated!")
    else:
        print(f"[!] Failed to push JSON. Status: {put_res.status_code}, Response: {put_res.text}")

# ==============================================================================
# 🏁 MAIN ENTRYPOINT
# ==============================================================================
def main():
    print("="*60)
    print("  🏆 SPORTS POSTER STUDIO & JSON SCHEDULER ENGINE  ")
    print("="*60)

    cricket_matches = process_cricbuzz()
    football_matches = process_footystream()
    all_matches = cricket_matches + football_matches

    # Save locally
    local_json = os.path.join(BASE_DIR, "matches.json")
    with open(local_json, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, indent=2, ensure_ascii=False)

    # Sync to external repo
    push_json_to_remote_repo(all_matches)
    print(f"\n[+] Execution complete. Processed {len(all_matches)} matches.")

if __name__ == "__main__":
    main()
