import os
import io
import re
import textwrap
import requests
from bs4 import BeautifulSoup
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import budouX
    parser = budouX.load_default_japanese_parser()
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

def fetch_page_info(url):
    """記事本文からタイトル・サブタイトル・日時・場所・発信元(主催)・概要文(テキスト)を抽出する関数"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.raise_for_status()
        
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

        # --- 1. メイン記事領域の取得 ---
        main_content = soup.find('article') or soup.find(class_=re.compile(r'entry-content|post-content|main|content'))
        if not main_content:
            main_content = soup

        # --- 2. タイトルの抽出・サブタイトルの自動分離 ---
        raw_title = ""
        title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'entry-title|post-title|title')) or main_content.find(['h1', 'h2'])
        
        if title_tag and title_tag.get_text(strip=True):
            raw_title = title_tag.get_text(strip=True)
        elif soup.title and soup.title.string:
            raw_title = soup.title.string.strip()

        raw_title = re.sub(r'[\-|\||│].*$', '', raw_title).strip()
        cleaned_title = raw_title.strip(" ［］[]「」『』【】\t\n")

        title = cleaned_title
        extracted_subtitle = ""

        bracket_match = re.search(r'^(.*?)\s*[［\[（\(](.*?)[］\]）\)]$', cleaned_title)
        if bracket_match:
            title = bracket_match.group(1).strip(" ［］[]「」『』【】")
            extracted_subtitle = bracket_match.group(2).strip(" ［］[]「」『』【】")
        elif any(sep in cleaned_title for sep in [':', '：', '-', '〜', '~', '─']):
            parts = re.split(r'[:：\-〜~─]|\s+-\s+', cleaned_title, maxsplit=1)
            title = parts[0].strip(" ［］[]「」『』【】〜~")
            if len(parts) > 1:
                extracted_subtitle = parts[1].strip(" ［］[]「」『』【】〜~")

        # --- 3. 本文テキストの取得 ---
        text = main_content.get_text()

        # --- 4. 日時・場所の抽出 ---
        date_match = re.search(r'(日時|開催日時|日 時)[:：\s]*([^\n]+)', text)
        place_match = re.search(r'(場所|開催場所|会場|場 所)[:：\s]*([^\n]+)', text)

        extracted_date = date_match.group(2).strip() if date_match else ""
        extracted_place = place_match.group(2).strip() if place_match else ""

        # --- 5. 発信元（主催・担当部会等）の抽出整理 ---
        extracted_org = ""
        ignore_words = ["庶務", "サイトマップ", "注意事項", "免責事項", "参加", "研修会", "案内", "詳細"]

        sender_match = re.search(r'(発信元|担当|主催|主催者|問合せ先|問い合わせ)[:：\s]*([^\n]+)', text)
        if sender_match:
            candidate_sender = sender_match.group(2).strip().strip(" ［］[]「」『』【】\t\n")
            if not any(word in candidate_sender for word in ignore_words) and len(candidate_sender) <= 30:
                if candidate_sender != raw_title and candidate_sender != "研修会情報":
                    extracted_org = candidate_sender

        if not extracted_org:
            group_match = re.search(r'([^\s\n]+?(?:グループ|チーム|部|委員会|局|事務局))', text)
            if group_match:
                candidate_group = group_match.group(1).strip().strip(" ［］[]「」『』【】\t\n")
                # タイトルそのものと被っている場合は除外
                if candidate_group not in title and not any(word in candidate_group for word in ignore_words) and len(candidate_group) <= 20:
                    extracted_org = candidate_group

        if "事務局" in text and not extracted_org:
            extracted_org = "事務局"

        if extracted_org:
            if "作業療法士会" not in extracted_org and "島根" not in extracted_org:
                extracted_org = f"（一社）島根県作業療法士会 {extracted_org}"
        else:
            extracted_org = "（一社）島根県作業療法士会"

        # --- 6. 概要（要約テキスト）の自動作成 ---
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        summary_lines = []
        char_count = 0
        
        for p in paragraphs:
            if any(k in p for k in ["日時", "場所", "会場", "主催", "発信元", "お問合せ", "ログイン", "ホーム", "サイトマップ"]):
                continue
            if len(p) > 10:
                summary_lines.append(p)
                char_count += len(p)
                if char_count >= 180:
                    break
        
        extracted_summary = "\n".join(summary_lines)
        if len(extracted_summary) > 220:
            extracted_summary = extracted_summary[:217] + "..."

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
            "title": "",
            "subtitle": "",
            "date": "",
            "place": "",
            "org": "",
            "summary": "",
            "error": str(e)
        }

def draw_white_glow(img, bbox, mode="normal"):
    x1, y1, x2, y2 = bbox
    mask = Image.new('L', (1080, 1080), 0)
    draw_mask = ImageDraw.Draw(mask)
    
    if mode == "card":
        rect_box = (x1, y1, x2, y2)
        draw_mask.rounded_rectangle(rect_box, radius=20, fill=235)
        blurred_mask = mask.filter(ImageFilter.GaussianBlur(15))
    else:
        padding = 70
        rect_box = (max(0, x1 - padding), max(0, y1 - padding), min(1080, x2 + padding), min(1080, y2 + padding))
        draw_mask.rounded_rectangle(rect_box, radius=40, fill=210)
        blurred_mask = mask.filter(ImageFilter.GaussianBlur(35))
    
    white_layer = Image.new('RGB', (1080, 1080), (255, 255, 255))
    img.paste(white_layer, (0, 0), blurred_mask)

def smart_wrap(text, font, max_width):
    """「を」「に」「で」などの助詞で改行しやすいようにテキストを分割・改行処理"""
    if not text:
        return []

    # 「〜を」などの後ろで強制改行を試みる分割
    if "を" in text and len(text) > 8:
        parts = text.split("を", 1)
        line1 = parts[0] + "を"
        line2 = parts[1]
        
        # それぞれの行が入りきるかチェック
        try:
            w1 = font.getbbox(line1)[2] - font.getbbox(line1)[0]
            w2 = font.getbbox(line2)[2] - font.getbbox(line2)[0]
        except AttributeError:
            w1 = font.getsize(line1)[0]
            w2 = font.getsize(line2)[0]

        if w1 <= max_width and w2 <= max_width:
            return [line1, line2]

    # 通常の分かち書き処理
    if parser:
        raw_chunks = parser.parse(text)
    else:
        raw_chunks = re.split(r'(?<=[、。・\s\─\〜~：:\-\_\/をにで])', text)

    chunks = []
    current_chunk = ""
    for chunk in raw_chunks:
        if re.match(r'^[\u4e00-\u9faf]+$', chunk) or re.match(r'^[a-zA-Z0-9\-\_\.]+$', chunk):
            current_chunk += chunk
        else:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            chunks.append(chunk)
    if current_chunk:
        chunks.append(current_chunk)

    lines = []
    current_line = ""

    for chunk in chunks:
        if chunk.strip() == "" and chunk != " ": continue
            
        test_line = current_line + chunk
        try:
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = font.getsize(test_line)[0]

        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = chunk

    if current_line:
        lines.append(current_line)

    return lines

def wrap_and_get_font(text, max_width=860, initial_size=60, min_size=20, max_lines=3):
    if not text:
        return [""], get_font(min_size)

    size = initial_size
    font = get_font(size)
    lines = smart_wrap(text, font, max_width)
    
    all_fit = True
    for line in lines:
        try:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = font.getsize(line)[0]
        if w > max_width:
            all_fit = False
            break

    if not all_fit or len(lines) > max_lines:
        while size >= min_size:
            size -= 2
            font = get_font(size)
            lines = smart_wrap(text, font, max_width)

            all_fit_retry = True
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    w = bbox[2] - bbox[0]
                except AttributeError:
                    w = font.getsize(line)[0]
                if w > max_width:
                    all_fit_retry = False
                    break
            
            if all_fit_retry and len(lines) <= max_lines:
                return lines, font
    else:
        return lines, font

    return lines[:max_lines], font

def get_bg(mode):
    target_bg = BG_IMAGE_NOTICE if mode == "お知らせ" else BG_IMAGE_DEFAULT
    bg_p = os.path.join(BASE_DIR, target_bg)
    default_bg_p = os.path.join(BASE_DIR, BG_IMAGE_DEFAULT)
    
    if os.path.exists(bg_p):
        return Image.open(bg_p).convert('RGB').resize((1080, 1080))
    elif os.path.exists(default_bg_p):
        return Image.open(default_bg_p).convert('RGB').resize((1080, 1080))
    else:
        return Image.new('RGB', (1080, 1080), color=(255, 255, 255))

def draw_pink_underline(img, center_x, y_bottom, text_width, height=12):
    """タイトル文字の下にピンクのマーカー下線を描画する関数"""
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    x1 = center_x - (text_width / 2) - 10
    x2 = center_x + (text_width / 2) + 10
    y1 = y_bottom - (height / 2)
    y2 = y_bottom + (height / 2)
    
    # やわらかく可愛いピンク（#FFB6C1 / RGBA: 255, 182, 193, 180）
    draw.rounded_rectangle([x1, y1, x2, y2], radius=height//2, fill=(255, 150, 180, 190))
    
    img.paste(overlay, (0, 0), overlay)

def draw_image_page(img, 挿入画像):
    if 挿入画像 is not None:
        try:
            image_bytes = 挿入画像.getvalue()
            if image_bytes:
                insert_img = Image.open(io.BytesIO(image_bytes))
                if insert_img.mode != 'RGBA':
                    insert_img = insert_img.convert('RGBA')

                max_w, max_h = 800, 800
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                insert_img.thumbnail((max_w, max_h), resample_filter)

                pos_x = (1080 - insert_img.width) // 2
                pos_y = (1080 - insert_img.height) // 2
                img.paste(insert_img, (pos_x, pos_y), mask=insert_img)
        except Exception:
            st.warning("画像の読み込みに失敗しました。")

def draw_text_page(img, text):
    if text and text.strip():
        max_w = 900
        init_s = 34
        min_s = 20
        max_l = 12
        
        detail_lines, f_detail = wrap_and_get_font(text, max_width=max_w, initial_size=init_s, min_size=min_s, max_lines=max_l)
        
        font_size = getattr(f_detail, 'size', 28)
        line_height = font_size * 1.5
        total_height = line_height * len(detail_lines)
        
        start_y = 540 - (total_height / 2)

        rect_margin = 40
        bbox = (540 - (max_w // 2) - rect_margin, int(start_y - rect_margin), 540 + (max_w // 2) + rect_margin, int(start_y + total_height + rect_margin))
        draw_white_glow(img, bbox, mode="card")

        d = ImageDraw.Draw(img)
        curr_y = start_y + (line_height / 2)

        for line in detail_lines:
            d.text((540, curr_y), line, fill=(30, 30, 30), font=f_detail, anchor="mm")
            curr_y += line_height

def generate_posts(mode, 主催, タイトル, サブタイトル, 項目1, 項目2, second_type, 挿入画像, 詳細テキスト, ハッシュタグ, use_underline=True):
    f_org = get_font(36)
    f_sub = get_font(32)
    f_label = get_font(28)
    f_val = get_font(36)

    clean_org = 主催 or ''
    display_subtitle = f"〜 {サブタイトル.strip(' 〜~')} 〜" if サブタイトル and サブタイトル.strip() else ""

    generated_images = []

    # --- 1枚目生成 ---
    img1 = get_bg(mode)
    d1 = ImageDraw.Draw(img1)

    if mode == "研修会情報":
        d1.text((540, 270), clean_org, fill=(30, 30, 30), font=f_org, anchor="mm")

        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=880, initial_size=58, min_size=20, max_lines=3)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.4
        total_title_height = line_height * len(title_lines)
        title_start_y = 360 + (line_height / 2)

        for i, line in enumerate(title_lines):
            y = title_start_y + (i * line_height)
            
            # ピンクのマーカー下線を描画
            if use_underline:
                try:
                    w = f_title.getbbox(line)[2] - f_title.getbbox(line)[0]
                except AttributeError:
                    w = f_title.getsize(line)[0]
                draw_pink_underline(img1, 540, y + (font_size / 2) - 4, w, height=14)

            d1 = ImageDraw.Draw(img1)
            d1.text((540, y), line, fill=(20, 20, 20), font=f_title, anchor="mm")

        current_y = title_start_y + total_title_height + 15

        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=880, initial_size=32, min_size=20, max_lines=2)
            sub_line_height = getattr(f_sub_dynamic, 'size', 28) * 1.25
            for line in sub_lines:
                d1.text((540, current_y), line, fill=(50, 50, 50), font=f_sub_dynamic, anchor="mm")
                current_y += sub_line_height
            current_y += 15
        else:
            current_y += 20

        date_label_y = max(current_y, 600)
        d1.text((540, date_label_y), "【日時】", fill=(80, 80, 80), font=f_label, anchor="mm")
        date_val_y = date_label_y + 40
        d1.text((540, date_val_y), 項目1 or "", fill=(30, 30, 30), font=f_val, anchor="mm")

        if 項目2 and 項目2.strip():
            place_label_y = date_val_y + 60
            d1.text((540, place_label_y), "【場所】", fill=(80, 80, 80), font=f_label, anchor="mm")
            place_val_y = place_label_y + 40
            d1.text((540, place_val_y), 項目2 or "", fill=(30, 30, 30), font=f_val, anchor="mm")
            
        generated_images.append(img1)

        # 研修会の2枚目
        img2 = get_bg(mode)
        draw_image_page(img2, 挿入画像)
        generated_images.append(img2)

    else:
        # お知らせ用1枚目
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=820, initial_size=58, min_size=28, max_lines=4)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.45
        total_height = line_height * len(title_lines)
        
        sub_lines, f_sub_dynamic = ([], get_font(32))
        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=820, initial_size=32, min_size=20, max_lines=2)
            total_height += (getattr(f_sub_dynamic, 'size', 28) * 1.3 * len(sub_lines)) + 20

        start_y = 540 - (total_height / 2)

        bbox = (120, int(240), 960, int(start_y + total_height + 20))
        draw_white_glow(img1, bbox)

        d1_glow = ImageDraw.Draw(img1)
        d1_glow.text((540, 270), clean_org, fill=(30, 30, 30), font=f_org, anchor="mm")

        curr_y = start_y + (line_height / 2)
        for line in title_lines:
            # ピンクのマーカー下線を描画
            if use_underline:
                try:
                    w = f_title.getbbox(line)[2] - f_title.getbbox(line)[0]
                except AttributeError:
                    w = f_title.getsize(line)[0]
                draw_pink_underline(img1, 540, curr_y + (font_size / 2) - 4, w, height=14)

            d1_glow = ImageDraw.Draw(img1)
            d1_glow.text((540, curr_y), line, fill=(20, 20, 20), font=f_title, anchor="mm")
            curr_y += line_height

        if sub_lines:
            curr_y += 15
            sub_lh = getattr(f_sub_dynamic, 'size', 28) * 1.3
            for line in sub_lines:
                d1_glow.text((540, curr_y), line, fill=(50, 50, 50), font=f_sub_dynamic, anchor="mm")
                curr_y += sub_lh
        
        generated_images.append(img1)

        # --- お知らせの2枚目・3枚目 ---
        if second_type == "📷 画像のみ":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2)
            
        elif second_type == "📝 テキストのみ":
            img2 = get_bg(mode)
            draw_text_page(img2, 詳細テキスト)
            generated_images.append(img2)
            
        elif second_type == "🖼️ 画像＋テキスト（3枚）":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2)
            
            img3 = get_bg(mode)
            draw_text_page(img3, 詳細テキスト)
            generated_images.append(img3)

    # --- キャプション生成 ---
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
        if second_type == "📷 画像のみ":
            content_str = "添付画像をご確認ください。"
        elif second_type == "📝 テキストのみ":
            content_str = 詳細テキスト if 詳細テキスト else "詳細内容は画像をご確認ください。"
        else:
            content_str = "詳細内容は添付画像（2〜3枚目）をご確認ください。"
            
        caption_text = f"""【{タイトル or 'お知らせ'}】
{sub_text}
📌 発信：{clean_org}
📢 内容：{content_str}

よろしくお願いいたします。{tags_text}"""

    return generated_images, caption_text

# --- UI構築 ---
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
        input_url = st.text_input("研修会やお知らせページのURLを入力", placeholder="https://example.com/event/123")
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
                        st.error(f"ページの読み込みに失敗しました。")

    st.subheader("📄 1. テキスト入力")

    with st.form("input_form"):
        if mode == "研修会情報":
            主催 = st.text_input("主催・発信元", value=st.session_state["auto_org"])
            タイトル = st.text_input("研修会名・イベントタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1 = st.text_input("開催日時", value=st.session_state["auto_date"])
            項目2 = st.text_input("開催場所", value=st.session_state["auto_place"])
            
            use_underline = st.checkbox("🎀 タイトルにピンクの下線を引く", value=True)

            st.subheader("📷 2. 2枚目の画像設定")
            挿入画像 = st.file_uploader("2枚目に挿入する画像（任意）", type=["png", "jpg", "jpeg"])
            
            second_type = "📷 画像のみ"
            詳細テキスト = ""

        else:
            主催 = st.text_input("発信元・主催者名", value=st.session_state["auto_org"])
            タイトル = st.text_input("お知らせタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1, 項目2 = "", ""

            use_underline = st.checkbox("🎀 タイトルにピンクの下線を引く", value=True)

            st.subheader("🖼️ 2. 2枚目以降のコンテンツ選択")
            selected_type = st.radio("構成パターン", ["📷 画像のみ", "📝 テキストのみ", "🖼️ 画像＋テキスト（3枚）"], horizontal=True)
            
            second_type = selected_type

            if second_type == "📷 画像のみ":
                挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
                詳細テキスト = ""
            elif second_type == "📝 テキストのみ":
                挿入画像 = None
                詳細テキスト = st.text_area("2枚目に表示する詳細テキスト（概要）", value=st.session_state["auto_summary"], placeholder="お知らせの概要テキストを入力してください。", height=150)
            else: # 🖼️ 画像＋テキスト（3枚）
                挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
                詳細テキスト = st.text_area("3枚目に表示する詳細テキスト（概要）", value=st.session_state["auto_summary"], placeholder="お知らせの概要テキストを入力してください。", height=150)

        st.subheader("🏷️ 3. ハッシュタグ設定")
        ハッシュタグ = st.text_area("固定ハッシュタグ", value=DEFAULT_HASHTAGS, height=70)

        submit = st.form_submit_button("✨ 画像と文章を作成する", type="primary", use_container_width=True)

with col2:
    if submit:
        clean_org = 主催 or ''

        images, caption = generate_posts(
            mode, clean_org, タイトル, サブタイトル, 項目1, 項目2, 
            second_type, 挿入画像, 詳細テキスト, ハッシュタグ, use_underline=use_underline
        )

        st.subheader("🖼️ 完成画像")
        
        cols = st.columns(len(images))
        for i, img in enumerate(images):
            with cols[i]:
                st.image(img, caption=f"{i+1}枚目", use_container_width=True)

        st.subheader("📝 インスタ用キャプション（コピー用）")
        st.code(caption, language=None)
        
        st.markdown(
            """
            <a href="https://www.instagram.com/" target="_blank" style="text-decoration: none;">
                <div style="
                    background: linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%);
                    color: white;
                    padding: 12px 20px;
                    text-align: center;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 16px;
                    margin-top: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    📸 Instagram を開いて投稿する
                </div>
            </a>
            """,
            unsafe_allow_html=True
        )
