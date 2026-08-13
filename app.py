import os
import io
import re
import requests
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

def clean_blog_text(text):
    """URLや署名、日時などのノイズを除去して本文のみを抽出"""
    if not text:
        return ""
    # URLの除去
    text = re.sub(r'https?://[^\s\u3000]+', '', text)
    # 日付や署名などの末尾ノイズ行を除去（例：令和8年7月23日、@大田市...、氏名など）
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if not l:
            continue
        # 日付署名パターンを除外
        if re.search(r'^(令和|平成|20\d\d年|\d{4}年)', l) or re.search(r'@|チーム員会議|小林|事務局', l) and len(l) < 30:
            if "参加してきました" not in l and "開催" not in l:
                continue
        cleaned_lines.append(l)
    return " ".join(cleaned_lines)

def summarize_text_jp(text, max_chars=120):
    """ブログ・報告記事等をAI風に分析し、120文字程度の自然な完結文に集約"""
    clean_text = clean_blog_text(text)
    if not clean_text:
        return ""

    # 余分な記号・箇条書き・連続空白の除去
    clean_text = re.sub(r'^[・\-*•\d+\.]+\s*', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    # 句点（。！？）で文に分割
    raw_sentences = re.split(r'(?<=[。！？!\?])', clean_text)
    valid_sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 5]

    selected_sentences = []
    current_len = 0

    for sentence in valid_sentences:
        if current_len + len(sentence) <= max_chars:
            selected_sentences.append(sentence)
            current_len += len(sentence)
        else:
            break

    # 1文目すら長すぎる場合は自然な読点で区切る
    if not selected_sentences and valid_sentences:
        first_s = valid_sentences[0]
        comma_parts = re.split(r'(?<=[、,])', first_s)
        sub_build = ""
        for part in comma_parts:
            if len(sub_build) + len(part) <= max_chars - 10:
                sub_build += part
            else:
                break
        if sub_build:
            sub_build = re.sub(r'(について|の|および|また|における|等|など|へ|より|で)$', '', sub_build.strip())
            return sub_build + "についてご報告いたします。"
        else:
            return first_s[:max_chars - 10] + "についてご報告いたします。"

    result = "".join(selected_sentences).strip()
    if result and not result.endswith(('。', '！', '？', '!')):
        result += "。"

    return result

def smart_wrap(text, font, max_width):
    """単語・文脈（BudouX）を意識した自然な改行処理"""
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

def wrap_and_get_font(text, max_width=820, initial_size=52, min_size=24, max_lines=3):
    """自然な折り返しと最適なフォントサイズの算出"""
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
    """Webページからタイトル・サブタイトル・各種情報を自動読み込み"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        res.raise_for_status()
        
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

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

        text = main_content.get_text()

        date_match = re.search(r'(日時|開催日時|日 時)[:：\s]*([^\n]+)', text)
        place_match = re.search(r'(場所|開催場所|会場|場 所)[:：\s]*([^\n]+)', text)

        extracted_date = date_match.group(2).strip() if date_match else ""
        extracted_place = place_match.group(2).strip() if place_match else ""

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
                if candidate_group not in title and not any(word in candidate_group for word in ignore_words) and len(candidate_group) <= 20:
                    extracted_org = candidate_group

        if "事務局" in text and not extracted_org:
            extracted_org = "事務局"

        if extracted_org:
            if "作業療法士会" not in extracted_org and "島根" not in extracted_org:
                extracted_org = f"（一社）島根県作業療法士会 {extracted_org}"
        else:
            extracted_org = "（一社）島根県作業療法士会 事務局"

        extracted_summary = summarize_text_jp(text, max_chars=120)

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

def draw_white_glow(img, bbox, mode="glow"):
    """白背景カードの描画"""
    x1, y1, x2, y2 = bbox
    mask = Image.new('L', (1080, 1080), 0)
    draw_mask = ImageDraw.Draw(mask)
    
    if mode == "card":
        rect_box = (x1, y1, x2, y2)
        draw_mask.rounded_rectangle(rect_box, radius=30, fill=230)
        blurred_mask = mask.filter(ImageFilter.GaussianBlur(15))
    else:
        padding = 40
        rect_box = (max(0, x1 - padding), max(0, y1 - padding), min(1080, x2 + padding), min(1080, y2 + padding))
        draw_mask.rounded_rectangle(rect_box, radius=40, fill=220)
        blurred_mask = mask.filter(ImageFilter.GaussianBlur(25))
    
    white_layer = Image.new('RGB', (1080, 1080), (255, 255, 255))
    img.paste(white_layer, (0, 0), blurred_mask)

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
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    x1 = center_x - (text_width / 2) - 10
    x2 = center_x + (text_width / 2) + 10
    y1 = y_bottom - (height / 2)
    y2 = y_bottom + (height / 2)
    
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

def draw_text_page(img, title, text):
    """テキスト詳細画面（完全上下左右センタリング）"""
    target_text_w = 660
    
    # 要約文の取得
    clean_summary_text = summarize_text_jp(text, max_chars=120)

    # タイトルと本文の行分割
    title_lines, f_title = ([], get_font(32))
    if title and title.strip():
        title_lines, f_title = wrap_and_get_font(title, max_width=680, initial_size=36, min_size=24, max_lines=2)

    font_size = 26
    f_detail = get_font(font_size)
    body_lines = smart_wrap(clean_summary_text, f_detail, target_text_w) if clean_summary_text else []

    title_lh = getattr(f_title, 'size', 32) * 1.35
    body_lh = font_size * 1.65

    total_title_h = len(title_lines) * title_lh
    total_body_h = len(body_lines) * body_lh
    gap = 35 if total_title_h > 0 else 0

    total_content_h = total_title_h + gap + total_body_h

    # 画面全体の中央（Y=540）を意識した基準位置設定
    content_center_y = 520
    start_y = content_center_y - (total_content_h / 2)

    # 背景カードのサイズと位置（上下左右均等余白）
    card_top = max(280, int(start_y - 40))
    card_bottom = min(820, int(start_y + total_content_h + 40))
    draw_white_glow(img, (130, card_top, 950, card_bottom), mode="card")

    curr_y = start_y + (title_lh / 2)
    d = ImageDraw.Draw(img)

    # タイトル描画（中央揃え）
    if title_lines:
        for line in title_lines:
            try:
                w = f_title.getbbox(line)[2] - f_title.getbbox(line)[0]
            except AttributeError:
                w = f_title.getsize(line)[0]
            
            font_s = getattr(f_title, 'size', 32)
            draw_pink_underline(img, 540, curr_y + (font_s / 2) - 2, w, height=10)
            d.text((540, curr_y), line, fill=(30, 30, 30), font=f_title, anchor="mm")
            curr_y += title_lh

        curr_y += gap - (title_lh / 2) + (body_lh / 2)
    else:
        curr_y = start_y + (body_lh / 2)

    # 本文描画（各行完全中央揃え anchor="mm"）
    for line in body_lines:
        d.text((540, curr_y), line, fill=(40, 40, 40), font=f_detail, anchor="mm")
        curr_y += body_lh

def generate_posts(mode, 主催, タイトル, サブタイトル, 項目1, 項目2, second_type, 挿入画像, 詳細テキスト, ハッシュタグ):
    f_org = get_font(36)
    f_sub = get_font(32)
    f_label = get_font(28)
    f_val = get_font(36)

    clean_org = 主催 or '（一社）島根県作業療法士会 事務局'
    display_subtitle = f"〜 {サブタイトル.strip(' 〜~')} 〜" if サブタイトル and サブタイトル.strip() else ""

    generated_images = []

    # 1枚目生成
    img1 = get_bg(mode)

    if mode == "研修会情報":
        d1 = ImageDraw.Draw(img1)
        d1.text((540, 270), clean_org, fill=(30, 30, 30), font=f_org, anchor="mm")

        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=840, initial_size=52, min_size=24, max_lines=3)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.4
        total_title_height = line_height * len(title_lines)
        title_start_y = 360 + (line_height / 2)

        for i, line in enumerate(title_lines):
            y = title_start_y + (i * line_height)
            d1.text((540, y), line, fill=(20, 20, 20), font=f_title, anchor="mm")

        current_y = title_start_y + total_title_height + 15

        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=840, initial_size=30, min_size=20, max_lines=2)
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

        img2 = get_bg(mode)
        draw_image_page(img2, 挿入画像)
        generated_images.append(img2)

    else:
        # お知らせ用 1枚目
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=800, initial_size=52, min_size=26, max_lines=3)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.45
        total_height = line_height * len(title_lines)
        
        sub_lines, f_sub_dynamic = ([], get_font(32))
        if display_subtitle:
            sub_lines, f_sub_dynamic = wrap_and_get_font(display_subtitle, max_width=800, initial_size=30, min_size=20, max_lines=2)
            total_height += (getattr(f_sub_dynamic, 'size', 28) * 1.3 * len(sub_lines)) + 20

        start_y = 540 - (total_height / 2)

        bbox = (120, int(240), 960, int(start_y + total_height + 20))
        draw_white_glow(img1, bbox, mode="glow")

        d1 = ImageDraw.Draw(img1)
        d1.text((540, 270), clean_org, fill=(30, 30, 30), font=f_org, anchor="mm")

        curr_y = start_y + (line_height / 2)
        for line in title_lines:
            d1.text((540, curr_y), line, fill=(20, 20, 20), font=f_title, anchor="mm")
            curr_y += line_height

        if sub_lines:
            curr_y += 15
            sub_lh = getattr(f_sub_dynamic, 'size', 28) * 1.3
            for line in sub_lines:
                d1.text((540, curr_y), line, fill=(50, 50, 50), font=f_sub_dynamic, anchor="mm")
                curr_y += sub_lh
        
        generated_images.append(img1)

        if second_type == "📷 画像のみ":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2)
            
        elif second_type == "📝 テキストのみ":
            img2 = get_bg(mode)
            draw_text_page(img2, タイトル, 詳細テキスト)
            generated_images.append(img2)
            
        elif second_type == "🖼️ 画像＋テキスト（3枚）":
            img2 = get_bg(mode)
            draw_image_page(img2, 挿入画像)
            generated_images.append(img2)
            
            img3 = get_bg(mode)
            draw_text_page(img3, タイトル, 詳細テキスト)
            generated_images.append(img3)

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
            content_str = summarize_text_jp(詳細テキスト, max_chars=120) if 詳細テキスト else "詳細内容は画像をご確認ください。"
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
            second_type, 挿入画像, 詳細テキスト, ハッシュタグ
        )

        st.subheader("🖼️ 完成画像")
        
        cols = st.columns(len(images))
        for i, img in enumerate(images):
            with cols[i]:
                st.image(img, caption=f"{i+1}枚目", use_container_width=True)

        st.subheader("📝 インスタ用キャプション（コピー用）")
        st.code(caption, language=None)
