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
# ⚙️ GLOBAL CONFIGURATION (5:3 RATIO -> 1200 x 720)
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CRICKET_POSTER_DIR = os.path.join(BASE_DIR, "posters")
FOOTY_POSTER_DIR = os.path.join(BASE_DIR, "footy_posters")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(CRICKET_POSTER_DIR, exist_ok=True)
os.makedirs(FOOTY_POSTER_DIR, exist_ok=True)

POSTER_WIDTH = 1200
POSTER_HEIGHT = 720  # Mathematically exact 5:3 ratio

CURRENT_REPO = os.getenv("GITHUB_REPOSITORY", "sawaridtv/PosterMaker")
BRANCH_NAME = "main"

TARGET_REPO = os.getenv("TARGET_REPO", "samnite2290/your-data-repo")
TARGET_JSON_PATH = "matches.json"
TARGET_GH_PAT = os.getenv("TARGET_REPO_PAT")

TIMEZONE = pytz.timezone("Asia/Dhaka")

WATERMARK_TEXT = "SAWARID سواريد"
LOCAL_LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")
BG_IMAGE_PATH = os.path.join(ASSETS_DIR, "background.jpg")
BG_FALLBACK_URL = "https://raw.githubusercontent.com/sawaridtv/PosterMaker/main/assets/background.jpg"

ARABIC_FONT_PATH = os.path.join(ASSETS_DIR, "Cairo-Bold.ttf")
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/static/Cairo-Bold.ttf"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ==============================================================================
# 🌐 THESPORTSDB INTEGRATION (OFFICIAL TRANSPARENT BADGES & CRESTS)
# ==============================================================================
THESPORTSDB_LEAGUES_CACHE = {}

def preload_thesportsdb_leagues():
    """Fetches all official transparent league badges from TheSportsDB API"""
    global THESPORTSDB_LEAGUES_CACHE
    url = "https://www.thesportsdb.com/api/v1/json/3/all_leagues.php"
    try:
        print("[*] Preloading official transparent league badges from TheSportsDB...")
        res = session.get(url, timeout=12)
        if res.status_code == 200:
            data = res.json()
            leagues = data.get("leagues", [])
            for item in leagues:
                name = item.get("strLeague", "").strip().lower()
                alt_name = item.get("strLeagueAlternate", "").strip().lower()
                badge = item.get("strBadge") or item.get("strLogo")
                if badge and name:
                    THESPORTSDB_LEAGUES_CACHE[name] = badge
                if badge and alt_name:
                    THESPORTSDB_LEAGUES_CACHE[alt_name] = badge
            print(f"[+] Successfully loaded {len(THESPORTSDB_LEAGUES_CACHE)} official league badges.")
    except Exception as e:
        print(f"[!] Warning: Could not preload TheSportsDB leagues: {e}")

def resolve_official_league_badge(league_name):
    """Matches a league name to TheSportsDB transparent badge"""
    if not league_name:
        return None
    query = league_name.lower().strip()
    
    # Direct match
    if query in THESPORTSDB_LEAGUES_CACHE:
        return THESPORTSDB_LEAGUES_CACHE[query]
        
    # Substring search
    for name, badge_url in THESPORTSDB_LEAGUES_CACHE.items():
        if query in name or name in query:
            return badge_url
    return None

def fetch_transparent_team_crest(team_name):
    """Searches TheSportsDB for official HD transparent club crest"""
    try:
        clean_name = re.sub(r'[^a-zA-Z0-9 ]', '', team_name).strip()
        url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={clean_name}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            teams = res.json().get("teams")
            if teams and len(teams) > 0:
                badge = teams[0].get("strBadge")
                if badge and badge.endswith((".png", ".webp")):
                    return badge
    except Exception:
        pass
    return None

# ==============================================================================
# 🛠️ HELPER FUNCTIONS
# ==============================================================================
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def format_custom_date(dt):
    return dt.strftime("%d-%m-%Y-%I:%M 00 %p").lower()

def auto_crop_and_resize(img, max_w, max_h):
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def is_transparent_badge(img):
    if img.mode != 'RGBA':
        return False
    alpha = img.split()[-1]
    extrema = alpha.getextrema()
    return extrema[0] < 200

def get_cairo_font(size):
    if not os.path.exists(ARABIC_FONT_PATH):
        try:
            print("[*] Downloading Arabic-capable Cairo font...")
            res = session.get(FONT_URL, timeout=15)
            if res.status_code == 200:
                with open(ARABIC_FONT_PATH, "wb") as f:
                    f.write(res.content)
        except Exception as e:
            print(f"[!] Font download failed: {e}")

    if os.path.exists(ARABIC_FONT_PATH):
        try:
            return ImageFont.truetype(ARABIC_FONT_PATH, size)
        except Exception:
            pass

    for path in ["/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    return ImageFont.load_default()

def load_background():
    candidates = [
        BG_IMAGE_PATH,
        os.path.join(ASSETS_DIR, "bg_cricket.jpg"),
        os.path.join(BASE_DIR, "scripts", "IMG_20260810_004413.jpg")
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                bg = Image.open(path).convert('RGBA')
                return bg.resize((POSTER_WIDTH, POSTER_HEIGHT), Image.Resampling.LANCZOS)
            except Exception:
                pass

    try:
        res = session.get(BG_FALLBACK_URL, timeout=8)
        if res.status_code == 200:
            bg = Image.open(BytesIO(res.content)).convert('RGBA')
            return bg.resize((POSTER_WIDTH, POSTER_HEIGHT), Image.Resampling.LANCZOS)
    except Exception:
        pass

    return Image.new('RGBA', (POSTER_WIDTH, POSTER_HEIGHT), (20, 24, 33, 255))

# ==============================================================================
# 🎨 5:3 POSTER GENERATOR ENGINE (EURO-LEAGUE INITIATIVE STYLE)
# ==============================================================================
def create_match_poster(match_title, img1_bytes, img2_bytes, save_path, league_logo_bytes=None):
    try:
        canvas = load_background()

        img1 = Image.open(BytesIO(img1_bytes)).convert('RGBA')
        img2 = Image.open(BytesIO(img2_bytes)).convert('RGBA')

        # Clean resizing for team crests
        img1 = auto_crop_and_resize(img1, 380, 420)
        img2 = auto_crop_and_resize(img2, 380, 420)

        # Positions matching professional broadcast cards
        mid_y = 330
        x1 = 280 - (img1.width // 2)
        y1 = mid_y - (img1.height // 2)
        x2 = 920 - (img2.width // 2)
        y2 = mid_y - (img2.height // 2)

        canvas.paste(img1, (x1, y1), img1)
        canvas.paste(img2, (x2, y2), img2)

        # --- CENTER POSITION: OFFICIAL LEAGUE BADGE ---
        badge_rendered = False
        if league_logo_bytes:
            try:
                l_img = Image.open(BytesIO(league_logo_bytes)).convert('RGBA')
                if is_transparent_badge(l_img):
                    l_img = auto_crop_and_resize(l_img, 220, 220)
                    bx = 600 - (l_img.width // 2)
                    by = mid_y - (l_img.height // 2)
                    canvas.paste(l_img, (bx, by), l_img)
                    badge_rendered = True
            except Exception:
                pass

        # If no transparent league badge is found, show clean text divider
        if not badge_rendered:
            draw = ImageDraw.Draw(canvas)
            vs_font = get_cairo_font(55)
            vs_text = "VS"
            vs_bbox = draw.textbbox((0, 0), vs_text, font=vs_font)
            vs_w = vs_bbox[2] - vs_bbox[0]
            vs_h = vs_bbox[3] - vs_bbox[1]
            vs_x = 600 - (vs_w // 2)
            vs_y = mid_y - (vs_h // 2) - 5
            draw.text((vs_x + 3, vs_y + 3), vs_text, fill=(0, 0, 0, 220), font=vs_font)
            draw.text((vs_x, vs_y), vs_text, fill=(255, 215, 0, 255), font=vs_font)

        # --- BOTTOM-CENTER WATERMARK BRANDING ---
        draw = ImageDraw.Draw(canvas)
        wm_font = get_cairo_font(50)
        logo_img = None
        if os.path.exists(LOCAL_LOGO_PATH):
            try:
                logo_raw = Image.open(LOCAL_LOGO_PATH).convert('RGBA')
                logo_img = auto_crop_and_resize(logo_raw, 100, 70)
            except Exception:
                pass

        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=wm_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        logo_w = logo_img.width if logo_img else 0
        logo_h = logo_img.height if logo_img else 0
        spacing = 18 if logo_img else 0

        # Calculate exact center coordinates for the combined watermark group
        total_group_width = logo_w + spacing + text_w
        start_x = (POSTER_WIDTH - total_group_width) // 2

        max_h = max(logo_h, text_h)
        base_y_center = (POSTER_HEIGHT - 45) - (max_h // 2)

        # Paste logo exactly centered
        if logo_img:
            logo_y = int(base_y_center - (logo_h // 2))
            canvas.paste(logo_img, (int(start_x), logo_y), logo_img)

        # Paste text right after the logo
        text_x = start_x + logo_w + spacing
        text_y = int(base_y_center - (text_h // 2)) - 5

        # Drop shadow and clean white Arabic/English text
        draw.text((text_x + 2, text_y + 2), WATERMARK_TEXT, fill=(0, 0, 0, 240), font=wm_font)
        draw.text((text_x, text_y), WATERMARK_TEXT, fill=(255, 255, 255, 255), font=wm_font)

        # Save optimized PNG
        quantized = canvas.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
        quantized.save(save_path, "PNG", optimize=True)
        return True

    except Exception as e:
        print(f"[!] Poster generation error for '{match_title}': {e}")
        return False

# ==============================================================================
# 🕒 NOTIFICATION TIME SCHEDULING
# ==============================================================================
def calculate_sport_times(start_dt, sport_type, match_format="T20"):
    notif_start = start_dt - timedelta(minutes=5)
    date_and_time_str = format_custom_date(notif_start)

    mult_run = "On"
    sport = sport_type.lower()
    fmt = str(match_format).upper()

    if "football" in sport:
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
# 🏏 SOURCE 1: CRICBUZZ MATCH PROVIDER
# ==============================================================================
def process_cricbuzz():
    json_entries = []
    active_files = []
    print("\n[+] Fetching matches from Cricbuzz API...")
    try:
        res = session.get("https://www.cricbuzz.com/api/home", timeout=15)
        if res.status_code != 200:
            return [], []
            
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
                active_files.append(filename)

                if not os.path.exists(poster_path):
                    # Fetch team logos (Enhance with TheSportsDB transparent crests if available)
                    t1_crest_url = fetch_transparent_team_crest(t1_name)
                    t2_crest_url = fetch_transparent_team_crest(t2_name)

                    s1 = re.sub(r'\s+', '-', t1_name).lower()
                    s2 = re.sub(r'\s+', '-', t2_name).lower()
                    u1 = t1_crest_url or f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t1_id}/{s1}.jpg"
                    u2 = t2_crest_url or f"https://static.cricbuzz.com/a/img/v1/0x0/i1/c{t2_id}/{s2}.jpg"

                    r1 = session.get(u1, timeout=10)
                    r2 = session.get(u2, timeout=10)

                    # Look up official tournament badge from TheSportsDB
                    league_badge_bytes = None
                    tsdb_badge_url = resolve_official_league_badge(series_name)
                    if tsdb_badge_url:
                        try:
                            b_res = session.get(tsdb_badge_url, timeout=6)
                            if b_res.status_code == 200:
                                league_badge_bytes = b_res.content
                        except Exception:
                            pass

                    if r1.status_code == 200 and r2.status_code == 200:
                        print(f"    🎨 Designing Cricket poster: {match_title}")
                        create_match_poster(match_title, r1.content, r2.content, poster_path, league_logo_bytes=league_badge_bytes)

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

    return json_entries, active_files

# ==============================================================================
# ⚽ SOURCE 2: FOOTYSTREAM MATCH PROVIDER
# ==============================================================================
def process_footystream():
    json_entries = []
    active_files = []
    print("\n[+] Fetching matches from Footystream...")
    try:
        res = session.get("https://footystream.pk/", timeout=15)
        if res.status_code != 200:
            return [], []
            
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
                        all_imgs = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', content, re.IGNORECASE)
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
                            active_files.append(filename)

                            if not os.path.exists(poster_path):
                                # Upgrade team images with TheSportsDB HD Transparent crests if found
                                t1_crest = fetch_transparent_team_crest(teams[0])
                                t2_crest = fetch_transparent_team_crest(teams[1])

                                u1 = t1_crest or (team_images[0] if team_images[0].startswith('http') else "https://footystream.pk" + team_images[0])
                                u2 = t2_crest or (team_images[1] if team_images[1].startswith('http') else "https://footystream.pk" + team_images[1])
                                
                                r1 = session.get(u1, timeout=10)
                                r2 = session.get(u2, timeout=10)

                                # Match league logo via TheSportsDB or direct Footystream logo
                                league_bytes = None
                                tsdb_badge_url = resolve_official_league_badge(slug.replace("-", " "))
                                target_badge_url = tsdb_badge_url or league_logo_url

                                if target_badge_url:
                                    if not target_badge_url.startswith('http'):
                                        target_badge_url = "https://footystream.pk" + target_badge_url
                                    try:
                                        l_res = session.get(target_badge_url, timeout=8)
                                        if l_res.status_code == 200:
                                            league_bytes = l_res.content
                                    except Exception:
                                        pass

                                if r1.status_code == 200 and r2.status_code == 200:
                                    print(f"    🎨 Designing Football poster: {match_title}")
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

    return json_entries, active_files

# ==============================================================================
# 🧹 AUTO CLEANUP
# ==============================================================================
def cleanup_old_posters(active_cricket, active_footy):
    print("\n[*] Cleaning up expired match posters...")
    for folder, active_list in [(CRICKET_POSTER_DIR, active_cricket), (FOOTY_POSTER_DIR, active_footy)]:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                if file.endswith('.png') and file not in active_list:
                    try:
                        os.remove(os.path.join(folder, file))
                        print(f"    [-] Removed expired poster: {file}")
                    except Exception as e:
                        print(f"    [!] Error deleting {file}: {e}")

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

    print(f"\n[+] Syncing fresh JSON to remote repo: {TARGET_REPO} ...")
    content_str = json.dumps(data, indent=2, ensure_ascii=False)
    content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    sha = None
    res = requests.get(api_url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get('sha')

    payload = {
        "message": "⚡ Auto-sync active match schedules",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    put_res = requests.put(api_url, headers=headers, json=payload)
    if put_res.status_code in [200, 201]:
        print("[+] Remote matches.json refreshed successfully!")
    else:
        print(f"[!] Failed to push JSON. Status: {put_res.status_code}")

# ==============================================================================
# 🏁 MAIN ENTRYPOINT (MODULAR PROVIDERS PIPELINE)
# ==============================================================================
def main():
    print("="*60)
    print("  🏆 5:3 THE-SPORTS-DB POWERED POSTER & JSON ENGINE  ")
    print("="*60)

    # 1. Preload official badges from TheSportsDB
    preload_thesportsdb_leagues()

    # 2. Run Match Providers
    cricket_matches, active_cricket = process_cricbuzz()
    football_matches, active_footy = process_footystream()

    all_matches = cricket_matches + football_matches

    # 3. Clean expired posters
    cleanup_old_posters(active_cricket, active_footy)

    # 4. Save clean JSON locally
    local_json = os.path.join(BASE_DIR, "matches.json")
    with open(local_json, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, indent=2, ensure_ascii=False)

    # 5. Push to target repo
    push_json_to_remote_repo(all_matches)
    print(f"\n[+] Execution complete. Active matches: {len(all_matches)}")

if __name__ == "__main__":
    main()
