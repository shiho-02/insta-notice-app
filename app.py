import os
import io
import re
import math
import requests
import numpy as np
from bs4 import BeautifulSoup
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import budouX
    parser = budouX.load_defaultjapanese_parser()
except ImportError:
    parser = None

st.set_page_config(page_title="インスタ投稿作成アプリ", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_FILE_NAME = "BananaSlip-Bold.otf"
BG_IMAGE_DEFAULT = "instagram.png"
BG_IMAGE_NOTICE = "instagram_notice.png"

font_path = os.path.join(BASE_DIR, FONT_FILE_NAME)
DEFAULT_HASHTAGS = "#（一社）島根県作業療法士会 #島根OT #作業療法 #OT"

def get_font(size):
    candidates = [
        font_path,
        "C:\\Windows\\Fonts\\msgothic.ttc",
        "C:\\Windows\\Fonts\\meiryo.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def clean_scraped_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://[^\s\u3000]+', '', text)
    noise_patterns = [
        r'会員の方へ', r'会員動向', r'Tweet', r'tweet', r'シェア', r'LINE', r'Facebook',
        r'はてブ', r'ポケット', r'印刷', r'カテゴリー[:：]?', r'タグ[:：]?',
        r'ホーム', r'お知らせ', r'記事一覧', r'投稿日[:：]?', r'更新日[:：]?'
    ]
    for pat in noise_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if not l:
            continue
        cleaned_lines.append(l)
    return " ".join(cleaned_lines)

def summarize_text_jp(text, target_chars=160):
    clean_text = clean_scraped_text(text)
    if not clean_text:
        return ""

    clean_text = re.sub(r'^[・\-*•\d+\.]+\s*', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    if len(clean_text) <= target_chars:
        return clean_text

    cutoff_min = max(0, target_chars - 30)
    cutoff_max = target_chars + 30
    cutoff = clean_text[cutoff_min:cutoff_max]
    
    punct_pos = [m.start() for m in re.finditer(r'[。！？]', cutoff)]
    
    if punct_pos:
        best_relative_p = min(punct_pos, key=lambda x: abs((cutoff_min + x) - target_chars))
        best_p = cutoff_min + best_relative_p
        return clean_text[:best_p + 1]

    comma_pos = [m.start() for m in re.finditer(r'[、,]', clean_text[:target_chars])]
    if comma_pos:
        return clean_text[:comma_pos[-1]] + "など。"

    return clean_text[:target_chars] + "..."

def smart_wrap(text, font, max_width):
    if not text:
        return []

    if parser:
        chunks = parser.parse(text)
    else:
        chunks = re.split(r'(?<=[\s、。！？\-\:\/])', text)
        if len(chunks) == 1:
            chunks = list(text)

    lines = []
    current_line = ""

    for chunk in chunks:
        test_line = current_line + chunk
        try:
            w = font.getbbox(test_line)[2] - font.getbbox(test_line)[0]
        except AttributeError:
            w = font.getsize(test_line)[0]

        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
                current_line = chunk
            else:
                for char in chunk:
                    if font.getbbox(current_line + char)[2] - font.getbbox(current_line + char)[0] <= max_width:
                        current_line += char
                    else:
                        lines.append(current_line)
                        current_line = char

    if current_line:
        lines.append(current_line)

    return lines

def wrap_and_get_font(text, max_width=750, initial_size=36, min_size=20, max_lines=7):
    if not text:
        return [""], get_font(min_size)

    size = initial_size
    while size >= min_size:
        font = get_font(size)
        lines = smart_wrap(text, font, max_width)
        if len(lines) <= max_lines:
            return lines, font
        size -= 2

    font = get_font(min_size)
    lines = smart_wrap(text, font, max_width)
    return lines[:max_lines], font

def fetch_page_info(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.raise_for_status()
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

        raw_full_text = soup.get_text()

        extracted_org = ""
        date_bracket_match = re.search(r'\d{4}年\d{1,2}月\d{1,2}日\s*[\[［](.*?)[\]］]', raw_full_text)
        if not date_bracket_match:
            date_bracket_match = re.search(r'\d{4}[\/\.-]\d{1,2}[\/\.-]\d{1,2}\s*[\[［](.*?)[\]］]', raw_full_text)

        if date_bracket_match:
            org_name = date_bracket_match.group(1).strip()
            if org_name:
                if "作業療法士会" in org_name:
                    extracted_org = org_name
                else:
                    extracted_org = f"（一社）島根県作業療法士会 {org_name}"

        if not extracted_org:
            if "認知症の作業療法委員会" in raw_full_text:
                extracted_org = "（一社）島根県作業療法士会 認知症の作業療法委員会"
            else:
                comm_match = re.search(r'([^\s\n]+?委員会)', raw_full_text)
                if comm_match:
                    comm_name = comm_match.group(1).strip()
                    if "作業療法士会" not in comm_name:
                        extracted_org = f"（一社）島根県作業療法士会 {comm_name}"
                    else:
                        extracted_org = comm_name
                else:
                    extracted_org = "（一社）島根県作業療法士会 事務局"

        for tag in soup([
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            '.share', '.sns', '.social', '.entry-meta', '.cat-links',
            '.post-meta', '.meta', '.byline', '.author', '.posted-on'
        ]):
            tag.decompose()

        main_content = soup.find('article') or soup.find(class_=re.compile(r'entry-content|post-content|main|content'))
        if not main_content:
            main_content = soup

        raw_title = ""
        title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'entry-title|post-title|title')) or main_content.find(['h1', 'h2'])
        if title_tag and title_tag.get_text(strip=True):
            raw_title = title_tag.get_text(strip=True)
        elif soup.title and soup.title.string:
            raw_title = soup.title.string.strip()

        raw_title = re.sub(r'[\-|\||│].*$', '', raw_title).strip()
        cleaned_title = clean_scraped_text(raw_title).strip(" ［］[]「」『』【】\t\n")

        title = cleaned_title
        extracted_subtitle = ""

        bracket_match = re.search(r'^(.*?)\s*[［\[（\(](.*?)[］\]）\)]$', cleaned_title)
        if bracket_match:
            title = bracket_match.group(1).strip(" ［］[]「」『』【】")
            extracted_subtitle = bracket_match.group(2).strip(" ［］[]「」『』【】")

        date_match = re.search(r'(日時|開催日時)[:：\s]*([^\n]+)', raw_full_text)
        place_match = re.search(r'(場所|開催場所|会場)[:：\s]*([^\n]+)', raw_full_text)

        extracted_date = date_match.group(2).strip() if date_match else ""
        extracted_place = place_match.group(2).strip() if place_match else ""

        extracted_summary = summarize_text_jp(main_content.get_text(), target_chars=160)

        return {
            "title": title,
            "subtitle": extracted_subtitle,
            "date": extracted_date,
            "place": extracted_place,
            "org": extracted_org,
            "summary": extracted_summary,
            "error": None
        }
    except Exception as e:
        return {
            "title": "", "subtitle": "", "date": "", "place": "", "org": "", "summary": "", "error": str(e)
        }

def draw_clean_white_blur_base(img, center_y, total_height, box_width=850, max_alpha=230, blur_radius=30, padding=(60, 60)):
    """白ぼかし背景シートを描画"""
    width, height = img.size
    
    mask = Image.new('L', (width, height), 0)
    draw_mask = ImageDraw.Draw(mask)
    
    x1 = 540 - (box_width / 2)
    x2 = 540 + (box_width / 2)
    y1 = center_y - (total_height / 2) - padding[1]
    y2 = center_y + (total_height / 2) + padding[1]

    draw_mask.rounded_rectangle([x1, y1, x2, y2], radius=45, fill=max_alpha)
    
    blurred_mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    
    white_surface = Image.new('RGB', (width, height), (255, 255, 255))
    white_surface.putalpha(blurred_mask)
    
    img.alpha_composite(white_surface)

def get_bg(mode):
    target_bg = BG_IMAGE_NOTICE if mode == "お知らせ" else BG_IMAGE_DEFAULT
    bg_p = os.path.join(BASE_DIR, target_bg)
    default_bg_p = os.path.join(BASE_DIR, BG_IMAGE_DEFAULT)
    
    if os.path.exists(bg_p):
        bg_img = Image.open(bg_p)
    elif os.path.exists(default_bg_p):
        bg_img = Image.open(default_bg_p)
    else:
        bg_img = Image.new('RGB', (1080, 1080), color=(255, 255, 255))
    
    bg_img = bg_img.convert('RGBA').resize((1080, 1080))
    return bg_img

def draw_pink_underline(img, center_x, y_bottom, text_width, height=12):
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x1 = center_x - (text_width / 2) - 10
    x2 = center_x + (text_width / 2) + 10
    y1 = y_bottom - (height / 2)
    y2 = y_bottom + (height / 2)
    
    draw.rounded_rectangle([x1, y1, x2, y2], radius=height//2, fill=(255, 130, 170, 200))
    blurred_overlay = overlay.filter(ImageFilter.GaussianBlur(radius=2))
    img.alpha_composite(blurred_overlay)

def draw_image_page(img, 挿入画像):
    if 挿入画像 is not None:
        try:
            image_bytes = 挿入画像.getvalue()
            if image_bytes:
                insert_img = Image.open(io.BytesIO(image_bytes))
                if insert_img.mode != 'RGBA':
                    insert_img = insert_img.convert('RGBA')

                max_w, max_h = 750, 750
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                insert_img.thumbnail((max_w, max_h), resample_filter)

                pos_x = (1080 - insert_img.width) // 2
                pos_y = (1080 - insert_img.height) // 2
                img.alpha_composite(insert_img, (pos_x, pos_y))
        except Exception:
            st.warning("画像の読み込みに失敗しました。")

def draw_text_page(img, title, text):
    """お知らせ用 テキスト詳細ページ（文字大＆シート850px）"""
    MAX_TEXT_WIDTH = 780

    title_lines, f_title = ([], get_font(34))
    if title and title.strip():
        clean_t = clean_scraped_text(title)
        title_lines, f_title = wrap_and_get_font(clean_t, max_width=MAX_TEXT_WIDTH, initial_size=46, min_size=32, max_lines=3)

    display_text = text if len(text) <= 160 else summarize_text_jp(text, target_chars=160)
    body_lines, f_body = wrap_and_get_font(display_text, max_width=MAX_TEXT_WIDTH, initial_size=34, min_size=24, max_lines=10)

    title_size = getattr(f_title, 'size', 46)
    body_size = getattr(f_body, 'size', 34)

    title_lh = title_size * 1.4
    body_lh = body_size * 1.5

    total_title_h = len(title_lines) * title_lh
    total_body_h = len(body_lines) * body_lh
    gap = 35 if total_title_h > 0 and total_body_h > 0 else 0

    total_content_h = total_title_h + gap + total_body_h
    start_y = 540 - (total_content_h / 2)

    # お知らせ用の大きな白ぼかしシート (850px)
    center_y = start_y + (total_content_h / 2)
    draw_clean_white_blur_base(img, center_y, total_content_h, box_width=850, max_alpha=230, blur_radius=30, padding=(60, 50))

    d = ImageDraw.Draw(img)
    curr_y = start_y + (title_lh / 2)

    # タイトル
    if title_lines:
        for line in title_lines:
            try:
                w = f_title.getbbox(line)[2] - f_title.getbbox(line)[0]
            except AttributeError:
                w = f_title.getsize(line)[0]

            draw_pink_underline(img, 540, curr_y + (title_size / 2) - 2, w, height=10)
            d.text((540, curr_y), line, fill=(30, 30, 30), font=f_title, anchor="mm")
            curr_y += title_lh

        curr_y += gap - (title_lh / 2) + (body_lh / 2)
    else:
        curr_y = start_y + (body_lh / 2)

    # 本文
    for line in body_lines:
        d.text((540, curr_y), line, fill=(40, 40, 40), font=f_body, anchor="mm")
        curr_y += body_lh

def generate_posts(mode, 主催, タイトル, サブタイトル, 項目1, 項目2, second_type, 挿入画像, 詳細テキスト, ハッシュタグ):
    f_org = get_font(30)
    f_label = get_font(30)
    f_val = get_font(36)

    clean_org = 主催 or '（一社）島根県作業療法士会 事務局'
    display_subtitle = f"〜 {サブタイトル.strip(' 〜~')} 〜" if サブタイトル and サブタイトル.strip() else ""

    generated_images = []

    # 1枚目生成
    img1 = get_bg(mode)

    if mode == "研修会情報":
        # ---------------- 研修会情報（従来バランス） ----------------
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=680, initial_size=36, min_size=24, max_lines=3)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.35
        total_title_height = line_height * len(title_lines)

        sub_lines, f_sub_dynamic = ([], get_font(26))
        sub_total_h = 0
        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=680, initial_size=26, min_size=18, max_lines=2)
            sub_total_h = (getattr(f_sub_dynamic, 'size', 26) * 1.3 * len(sub_lines)) + 15

        info_h = 200 if (項目2 and 項目2.strip()) else 110
        total_content_h = 50 + total_title_height + sub_total_h + info_h
        
        # 研修会用標準シート (700px)
        draw_clean_white_blur_base(img1, 540, total_content_h, box_width=700, max_alpha=200, blur_radius=20, padding=(40, 40))

        d1 = ImageDraw.Draw(img1)
        start_y = 540 - (total_content_h / 2) + 20

        d1.text((540, start_y), clean_org, fill=(50, 50, 50), font=f_org, anchor="mm")

        curr_y = start_y + 40 + (line_height / 2)
        for line in title_lines:
            d1.text((540, curr_y), line, fill=(20, 20, 20), font=f_title, anchor="mm")
            curr_y += line_height

        if sub_lines:
            curr_y += 10
            sub_lh = getattr(f_sub_dynamic, 'size', 26) * 1.3
            for line in sub_lines:
                d1.text((540, curr_y), line, fill=(60, 60, 60), font=f_sub_dynamic, anchor="mm")
                curr_y += sub_lh

        curr_y += 15
        d1.text((540, curr_y), "【日時】", fill=(80, 80, 80), font=f_label, anchor="mm")
        curr_y += 35
        d1.text((540, curr_y), 項目1 or "", fill=(30, 30, 30), font=f_val, anchor="mm")

        if 項目2 and 項目2.strip():
            curr_y += 55
            d1.text((540, curr_y), "【場所】", fill=(80, 80, 80), font=f_label, anchor="mm")
            curr_y += 35
            d1.text((540, curr_y), 項目2 or "", fill=(30, 30, 30), font=f_val, anchor="mm")

        generated_images.append(img1.convert('RGB'))

        img2 = get_bg(mode)
        draw_image_page(img2, 挿入画像)
        generated_images.append(img2.convert('RGB'))

    else:
        # ---------------- お知らせ（文字拡大＆ぼかし可視化） ----------------
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=780, initial_size=46, min_size=32, max_lines=3)
        font_size = getattr(f_title, 'size', 46)
        line_height = font_size * 1.45
        total_height = line_height * len(title_lines) + 60

        sub_lines, f_sub_dynamic = ([], get_font(32))
        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=750, initial_size=34, min_size=24, max_lines=2)
            total_height += (getattr(f_sub_dynamic, 'size', 34) * 1.3 * len(sub_lines)) + 20

        start_y = 540 - (total_height / 2)

        # お知らせ専用：横幅850pxの大きな白ぼかしシート
        draw_clean_white_blur_base(img1, 540, total_height, box_width=850, max_alpha=230, blur_radius=30, padding=(60, 50))

        d1 = ImageDraw.Draw(img1)
        d1.text((540, start_y + 15), clean_org, fill=(50, 50, 50), font=f_org, anchor="mm")

        curr_y = start_y + 60 + (line_height / 2)
        for line in title_lines:
            d1.text((540, curr_y), line, fill=(20, 20, 20), font=f_title, anchor="mm")
            curr_y += line_height

        if sub_lines:
            curr_y += 15
            sub_lh = getattr(f_sub_dynamic, 'size', 34) * 1.3
            for line in sub_lines:
                d1.text((540, curr_y), line, fill=(70, 70, 70), font=f_sub_dynamic, anchor="mm")
                curr_y += sub_lh

        generated_images.append(img1.convert('RGB'))

        if second_type == "📷 画像のみ":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2.convert('RGB'))

        elif second_type == "📝 テキストのみ":
            img2 = get_bg(mode)
            draw_text_page(img2, タイトル, 詳細テキスト)
            generated_images.append(img2.convert('RGB'))

        elif second_type == "🖼️ 画像＋テキスト（3枚）":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2.convert('RGB'))

            img3 = get_bg(mode)
            draw_text_page(img3, タイトル, 詳細テキスト)
            generated_images.append(img3.convert('RGB'))

    sub_text = f"\n{サブタイトル}\n" if サブタイトル and サブタイトル.strip() else ""
    tags_text = f"\n\n{ハッシュタグ}" if ハッシュタグ and ハッシュタグ.strip() else ""

    if mode == "研修会情報":
        caption_text = f"""【{タイトル or 'お知らせ'}】のご案内✨
{sub_text}
📌 主催：{clean_org}
📅 日時：{項目1 or ''}
📍 場所：{項目2 or ''}

みなさまのご参加をお待ちしております！{tags_text}"""
    else:
        summary_str = summarize_text_jp(詳細テキスト, target_chars=160) if 詳細テキスト else "詳細内容は画像をご確認ください。"
        caption_text = f"""【{タイトル or 'お知らせ'}】
{sub_text}
📌 発信：{clean_org}
📢 内容：{summary_str}

よろしくお願いいたします。{tags_text}"""

    return generated_images, caption_text

# --- UI ---
st.title("📱 インスタ投稿作成アプリ")

st.markdown("### 📌 投稿の種類を選択してください")

options = ["🎓 研修会情報", "📢 お知らせ"]
selected_option = st.pills(
    "投稿の種類",
    options,
    default="📢 お知らせ",
    label_visibility="collapsed"
)

mode = "研修会情報" if "研修会情報" in (selected_option or "") else "お知らせ"

st.divider()

col1, col2 = st.columns([1, 1])

if "auto_org" not in st.session_state:
    st.session_state["auto_org"] = "（一社）島根県作業療法士会 事務局"
if "auto_title" not in st.session_state:
    st.session_state["auto_title"] = ""
if "auto_subtitle" not in st.session_state:
    st.session_state["auto_subtitle"] = ""
if "auto_date" not in st.session_state:
    st.session_state["auto_date"] = ""
if "auto_place" not in st.session_state:
    st.session_state["auto_place"] = ""
if "auto_summary" not in st.session_state:
    st.session_state["auto_summary"] = ""

with col1:
    with st.expander("🔗 Webページ（URL）から情報を自動読み込み", expanded=False):
        input_url = st.text_input("研修会やお知らせページのURLを入力", placeholder="https://shimane-ot.jp/info/article-62394/")
        if st.button("🌐 情報を自動取得する", use_container_width=True):
            if input_url:
                with st.spinner("ページ情報を取得中..."):
                    info = fetch_page_info(input_url)
                    if info and not info.get("error"):
                        st.session_state["auto_title"] = info.get("title", "")
                        st.session_state["auto_subtitle"] = info.get("subtitle", "")
                        st.session_state["auto_date"] = info.get("date", "")
                        st.session_state["auto_place"] = info.get("place", "")
                        st.session_state["auto_org"] = info.get("org", "（一社）島根県作業療法士会 事務局")
                        st.session_state["auto_summary"] = info.get("summary", "")
                        st.success("情報をフォームに反映しました！")
                        st.rerun()
                    else:
                        st.error("ページの読み込みに失敗しました。")

    st.subheader("📄 1. テキスト入力")

    with st.form("input_form"):
        if mode == "研修会情報":
            主催 = st.text_input("主催・発信元", value=st.session_state["auto_org"])
            タイトル = st.text_input("研修会名・イベントタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1 = st.text_input("開催日時", value=st.session_state["auto_date"])
            項目2 = st.text_input("開催場所", value=st.session_state["auto_place"])

            st.subheader("📷 2. 2枚目の画像設定")
            挿入画像 = st.file_uploader("2枚目に挿入する画像（任意）", type=["png", "jpg", "jpeg"])
            second_type = "📷 画像のみ"
            詳細テキスト = ""

        else:
            主催 = st.text_input("発信元・主催者名", value=st.session_state["auto_org"])
            タイトル = st.text_input("お知らせタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1, 項目2 = "", ""

            st.subheader("🖼️ 2. 2枚目以降のコンテンツ選択")
            selected_type = st.radio("構成パターン", ["📷 画像のみ", "📝 テキストのみ", "🖼️ 画像＋テキスト（3枚）"], horizontal=True)
            second_type = selected_type

            if second_type == "📷 画像のみ":
                挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
                詳細テキスト = ""
            elif second_type == "📝 テキストのみ":
                挿入画像 = None
                詳細テキスト = st.text_area("2枚目に表示する詳細テキスト（概要）", value=st.session_state["auto_summary"], placeholder="お知らせの概要テキストを入力してください。", height=180)
            else:
                挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
                詳細テキスト = st.text_area("3枚目に表示する詳細テキスト（概要）", value=st.session_state["auto_summary"], placeholder="お知らせの概要テキストを入力してください。", height=180)

        st.subheader("🏷️ 3. ハッシュタグ設定")
        ハッシュタグ = st.text_area("固定ハッシュタグ", value=DEFAULT_HASHTAGS, height=70)

        submit = st.form_submit_button("✨ 画像と文章を作成する", type="primary", use_container_width=True)

with col2:
    if submit:
        clean_org = 主催 or ''
        images, caption = generate_posts(
            mode, clean_org, タイトル, サブタイトル, 項目1, 項目2, 
            second_type, 挿入画像, 詳細テキスト, ハッシュタグ
        )

        st.subheader("🖼️ 完成画像")
        cols = st.columns(len(images))
        for i, img in enumerate(images):
            with cols[i]:
                st.image(img, caption=f"{i+1}枚目", use_container_width=True)

        st.subheader("📝 インスタ用キャプション（コピー用）")
        st.code(caption, language=None)
