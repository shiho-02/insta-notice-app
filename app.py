import os
import io
import re
import textwrap
import requests
from bs4 import BeautifulSoup
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
    """記事本文からグループ・部会名を含めた詳細な主催情報を抽出し、タイトルとサブタイトルを自動分離する関数"""
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

        # --- 2. タイトルの抽出・サブタイトルの自動検出 ---
        raw_title = ""
        title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'entry-title|post-title|title')) or main_content.find(['h1', 'h2'])
        
        if title_tag and title_tag.get_text(strip=True):
            raw_title = title_tag.get_text(strip=True)
        elif soup.title and soup.title.string:
            raw_title = soup.title.string.strip()

        raw_title = re.sub(r'[\-|\||│].*$', '', raw_title).strip()
        if raw_title in ["研修会情報", "お知らせ", "イベント情報", "サイトマップ"]:
            other_h = main_content.find(['h1', 'h2', 'h3'])
            if other_h:
                raw_title = other_h.get_text(strip=True)

        cleaned_title = raw_title.strip(" \t\n")

        title = cleaned_title
        extracted_subtitle = ""

        # サブタイトルの自動分離ロジック（記号の除去を強化）
        bracket_match = re.search(r'^(.*?)\s*[［\[（\(](.*?)[］\]）\)]$', cleaned_title)
        if bracket_match:
            title = bracket_match.group(1).strip(" ［］[]「」『』【】〜~-ー：:")
            extracted_subtitle = bracket_match.group(2).strip(" ［］[]「」『』【】〜~-ー：:")
        elif any(sep in cleaned_title for sep in [':', '：', '-', '〜', '~', '─']):
            parts = re.split(r'[:：\-〜~─]|\s+-\s+', cleaned_title, maxsplit=1)
            title = parts[0].strip(" ［］[]「」『』【】〜~-ー：:")
            if len(parts) > 1:
                # ★ サブタイトルの前後から「〜」や「-」等の余分な区切り記号をきれいに除去
                extracted_subtitle = parts[1].strip(" ［］[]「」『』【】〜~-ー：:")

        # --- 3. 本文テキストの取得 ---
        text = main_content.get_text()

        # --- 4. 日時・場所の抽出 ---
        date_match = re.search(r'(日時|開催日時|日 時)[:：\s]*([^\n]+)', text)
        place_match = re.search(r'(場所|開催場所|会場|場 所)[:：\s]*([^\n]+)', text)

        extracted_date = date_match.group(2).strip() if date_match else ""
        extracted_place = place_match.group(2).strip() if place_match else ""

        # --- 5. 主催・グループ・部署の抽出 ---
        extracted_org = ""

        group_match = re.search(r'([^\s\n]+?(?:グループ|チーム|部|委員会|局))', text)
        found_group = ""
        ignore_words = ["庶務", "サイトマップ", "注意事項", "免責事項", "参加", "研修会"]
        
        if group_match:
            candidate_group = group_match.group(1).strip(" \t\n")
            if not any(word in candidate_group for word in ignore_words) and len(candidate_group) <= 20:
                found_group = candidate_group

        org_match = re.search(r'(主催|主催者|担当|問合せ先|問い合わせ)[:：\s]*([^\n]+)', text)
        if org_match:
            candidate_org = org_match.group(2).strip(" \t\n")
            if not any(word in candidate_org for word in ignore_words) and len(candidate_org) <= 30:
                if candidate_org != raw_title and candidate_org != "研修会情報":
                    extracted_org = candidate_org

        if found_group:
            if "作業療法士会" not in found_group and "島根" not in found_group:
                extracted_org = f"（一社）島根県作業療法士会 {found_group}"
            else:
                extracted_org = found_group
        elif not extracted_org:
            extracted_org = "（一社）島根県作業療法士会"
        elif "作業療法士会" not in extracted_org and "島根" not in extracted_org:
            extracted_org = f"（一社）島根県作業療法士会 {extracted_org}"

        return {
            "title": title,
            "subtitle": extracted_subtitle,
            "date": extracted_date,
            "place": extracted_place,
            "org": extracted_org,
            "error": None
        }
    except Exception as e:
        return {
            "title": "",
            "subtitle": "",
            "date": "",
            "place": "",
            "org": "",
            "error": str(e)
        }

def draw_white_glow(img, bbox):
    """文字の背後に柔らかい白いモヤ（グラデーション）を描画して視認性を高める関数"""
    x1, y1, x2, y2 = bbox
    padding = 60
    
    mask = Image.new('L', (1080, 1080), 0)
    draw_mask = ImageDraw.Draw(mask)
    
    rect_box = (max(0, x1 - padding), max(0, y1 - padding), min(1080, x2 + padding), min(1080, y2 + padding))
    draw_mask.rounded_rectangle(rect_box, radius=40, fill=210)
    
    blurred_mask = mask.filter(ImageFilter.GaussianBlur(35))
    
    white_layer = Image.new('RGB', (1080, 1080), (255, 255, 255))
    img.paste(white_layer, (0, 0), blurred_mask)

def smart_wrap(text, font, max_width):
    """文脈・スペース・単語境界を考慮して変な場所で切れないよう折り返す関数"""
    if not text:
        return []

    # 助詞、句読点、スペース、ハイフン等で分割
    tokens = re.split(r'(?<=[、。・\s\─\〜~：:\-\_\/])', text)
    lines = []
    current_line = ""

    for token in tokens:
        test_line = current_line + token
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
            current_line = token

    if current_line:
        lines.append(current_line)

    final_lines = []
    for line in lines:
        try:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = font.getsize(line)[0]

        if w > max_width:
            # 英語単語や記号のない連続文字の場合は単語を壊さないように折り返し
            sub_lines = textwrap.wrap(
                line, 
                width=max(1, int(len(line) * (max_width / w))),
                break_long_words=True,
                break_on_hyphens=False
            )
            final_lines.extend(sub_lines)
        else:
            final_lines.append(line)

    return final_lines

def wrap_and_get_font(text, max_width=840, initial_size=60, min_size=28, max_lines=4):
    """テキストを収めるフォントサイズと行のリストを計算する関数"""
    if not text:
        return [""], get_font(min_size)

    size = initial_size
    while size >= min_size:
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

        if all_fit and len(lines) <= max_lines:
            return lines, font

        size -= 2

    font = get_font(min_size)
    lines = smart_wrap(text, font, max_width)
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

def generate_posts(mode, 主催, タイトル, サブタイトル, 項目1, 項目2, second_type, 挿入画像, 詳細テキスト, ハッシュタグ):
    f_org = get_font(36)
    f_sub = get_font(32)
    f_label = get_font(28)
    f_val = get_font(36)

    # --- 1枚目生成 ---
    img1 = get_bg(mode)

    if mode == "研修会情報":
        d1 = ImageDraw.Draw(img1)
        d1.text((540, 270), 主催 or "", fill=(30, 30, 30), font=f_org, anchor="mm")

        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=860, initial_size=58, min_size=28, max_lines=3)
        font_size = getattr(f_title, 'size', 36)
        line_height = font_size * 1.3
        total_title_height = line_height * len(title_lines)
        
        title_start_y = 370 + (line_height / 2)

        for i, line in enumerate(title_lines):
            y = title_start_y + (i * line_height)
            d1.text((540, y), line, fill=(20, 20, 20), font=f_title, anchor="mm")

        current_y = title_start_y + total_title_height + 10

        if サブタイトル and サブタイトル.strip():
            sub_lines, f_sub_dynamic = wrap_and_get_font(サブタイトル, max_width=860, initial_size=32, min_size=24, max_lines=2)
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

    else:
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=820, initial_size=60, min_size=32, max_lines=4)
        line_height = getattr(f_title, 'size', 36) * 1.35
        total_height = line_height * len(title_lines)
        
        sub_lines, f_sub_dynamic = ([], f_sub)
        if サブタイトル and サブタイトル.strip():
            sub_lines, f_sub_dynamic = wrap_and_get_font(サブタイトル, max_width=820, initial_size=32, min_size=24, max_lines=2)
            total_height += (getattr(f_sub_dynamic, 'size', 28) * 1.3 * len(sub_lines)) + 20

        start_y = 540 - (total_height / 2)

        bbox = (120, int(start_y - 20), 960, int(start_y + total_height + 20))
        draw_white_glow(img1, bbox)

        d1 = ImageDraw.Draw(img1)
        d1.text((540, 270), 主催 or "", fill=(30, 30, 30), font=f_org, anchor="mm")

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

    # --- 2枚目生成 ---
    img2 = get_bg(mode)

    if mode == "研修会情報" or (mode == "お知らせ" and second_type == "画像添付"):
        d2 = ImageDraw.Draw(img2)
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
                    img2.paste(insert_img, (pos_x, pos_y), mask=insert_img)
            except Exception:
                st.warning("画像の読み込みに失敗しました。")
    else:
        if 詳細テキスト and 詳細テキスト.strip():
            max_w = 820 if len(詳細テキスト) <= 120 else 880
            init_s = 40 if len(詳細テキスト) <= 120 else 32
            min_s = 22
            
            detail_lines, f_detail = wrap_and_get_font(詳細テキスト, max_width=max_w, initial_size=init_s, min_size=min_s, max_lines=10)
            
            line_height = getattr(f_detail, 'size', 28) * 1.45
            total_height = line_height * len(detail_lines)
            
            start_y = 540 - (total_height / 2)

            bbox = (540 - (max_w // 2) - 20, int(start_y - 25), 540 + (max_w // 2) + 20, int(start_y + total_height + 25))
            draw_white_glow(img2, bbox)

            d2 = ImageDraw.Draw(img2)
            curr_y = start_y + (line_height / 2)

            for line in detail_lines:
                d2.text((540, curr_y), line, fill=(30, 30, 30), font=f_detail, anchor="mm")
                curr_y += line_height

    # --- キャプション生成 ---
    sub_text = f"\n{サブタイトル}\n" if サブタイトル and サブタイトル.strip() else ""
    tags_text = f"\n\n{ハッシュタグ}" if ハッシュタグ and ハッシュタグ.strip() else ""
    
    if mode == "研修会情報":
        caption_text = f"""【{タイトル or 'お知らせ'}】のご案内✨
{sub_text}
📌 主催：{主催 or ''}
📅 日時：{項目1 or ''}
📍 場所：{項目2 or ''}

みなさまのご参加をお待ちしております！{tags_text}"""
    else:
        content_str = 詳細テキスト if second_type == "詳細テキスト" else "添付画像をご確認ください。"
        caption_text = f"""【{タイトル or 'お知らせ'}】
{sub_text}
📌 発信：{主催 or ''}
📢 内容：{content_str}

よろしくお願いいたします。{tags_text}"""

    return img1, img2, caption_text

# --- UI構築 ---
st.title("📱 インスタ投稿画像＆キャプション作成アプリ")

st.markdown("### 📌 投稿の種類を選択してください")

options = ["🎓 研修会情報", "📢 お知らせ"]
selected_option = st.pills(
    "投稿の種類",
    options,
    default="🎓 研修会情報",
    label_visibility="collapsed"
)

mode = "研修会情報" if "研修会情報" in (selected_option or "") else "お知らせ"

st.divider()

col1, col2 = st.columns([1, 1])

if "auto_org" not in st.session_state:
    st.session_state["auto_org"] = "（一社）島根県作業療法士会"
if "auto_title" not in st.session_state:
    st.session_state["auto_title"] = ""
if "auto_subtitle" not in st.session_state:
    st.session_state["auto_subtitle"] = ""
if "auto_date" not in st.session_state:
    st.session_state["auto_date"] = ""
if "auto_place" not in st.session_state:
    st.session_state["auto_place"] = ""

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
                        st.session_state["auto_org"] = info.get("org", "（一社）島根県作業療法士会")
                        st.success("情報をフォームに反映しました！")
                        st.rerun()
                    else:
                        error_msg = info.get("error") if info else "応答がありません"
                        st.error(f"ページの読み込みに失敗しました。\nエラー詳細: {error_msg}")

    st.subheader("📄 1. テキスト入力")

    with st.form("input_form"):
        if mode == "研修会情報":
            主催 = st.text_input("主催者・団体名", value=st.session_state["auto_org"])
            タイトル = st.text_input("研修会名・イベントタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1 = st.text_input("開催日時", value=st.session_state["auto_date"])
            項目2 = st.text_input("開催場所", value=st.session_state["auto_place"])
            second_type = "画像添付"
            詳細テキスト = ""
            
            st.subheader("📷 2. 2枚目の画像設定")
            挿入画像 = st.file_uploader("2枚目に挿入する画像（任意）", type=["png", "jpg", "jpeg"])

        else:
            主催 = st.text_input("発信元・団体名", value=st.session_state["auto_org"])
            タイトル = st.text_input("お知らせタイトル", value=st.session_state["auto_title"])
            サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）", value=st.session_state["auto_subtitle"])
            項目1, 項目2 = "", ""

            st.subheader("🖼️ 2. 2枚目のコンテンツ選択")
            selected_type = st.radio("2枚目の内容", ["📷 画像添付", "📝 詳細テキスト"], horizontal=True)
            second_type = "画像添付" if "画像添付" in selected_type else "詳細テキスト"

            if second_type == "画像添付":
                挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
                詳細テキスト = ""
            else:
                挿入画像 = None
                詳細テキスト = st.text_area("2枚目に表示する詳細テキスト", value=st.session_state["auto_title"], placeholder="例：定時社員総会を開催いたしました！\nご参加いただいた皆様、ありがとうございました。")

        st.subheader("🏷️ 3. ハッシュタグ設定")
        ハッシュタグ = st.text_area("固定ハッシュタグ", value=DEFAULT_HASHTAGS, height=70)

        submit = st.form_submit_button("✨ 画像と文章を作成する", type="primary", use_container_width=True)

with col2:
    if submit:
        img1, img2, caption = generate_posts(
            mode, 主催, タイトル, サブタイトル, 項目1, 項目2, 
            second_type, 挿入画像, 詳細テキスト, ハッシュタグ
        )

        st.subheader("🖼️ 完成画像")
        st.image(img1, caption="1枚目", use_container_width=True)
        st.image(img2, caption="2枚目", use_container_width=True)

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
