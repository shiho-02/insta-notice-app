import os
import io
import re
import textwrap
import requests
from bs4 import BeautifulSoup
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="インスタ投稿作成アプリ", layout="wide")

FONT_FILE_NAME = "BananaSlip-Bold.otf"
BG_IMAGE_DEFAULT = "instagram.png"
BG_IMAGE_NOTICE = "instagram_notice.png"

font_path = os.path.join(".", FONT_FILE_NAME)

DEFAULT_HASHTAGS = "#（一社）島根県作業療法士会 #島根OT #作業療法 #OT"

@st.cache_resource
def load_fonts():
    if os.path.exists(font_path):
        try:
            f_org = ImageFont.truetype(font_path, 36)
            f_sub = ImageFont.truetype(font_path, 36)
            f_label = ImageFont.truetype(font_path, 30)
            f_val = ImageFont.truetype(font_path, 40)
            return f_org, f_sub, f_label, f_val
        except Exception:
            pass
    
    def_font = ImageFont.load_default()
    return def_font, def_font, def_font, def_font

def fetch_page_info(url):
    """ウェブサイトからテキストを解析し、各項目を抽出する関数"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')

        # ページのテキスト全体を取得
        text = soup.get_text()
        
        # タイトルの取得
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        # サイト名などの不要な後続文字を除去
        title = re.sub(r'[\-|\||│].*$', '', title).strip()

        # キーワード検索による抽出
        date_match = re.search(r'(日時|開催日時|日 時)[:：\s]*([^\n]+)', text)
        place_match = re.search(r'(場所|開催場所|会場|場 所)[:：\s]*([^\n]+)', text)
        org_match = re.search(r'(主催|主催者)[:：\s]*([^\n]+)', text)

        extracted_date = date_match.group(2).strip() if date_match else ""
        extracted_place = place_match.group(2).strip() if place_match else ""
        extracted_org = org_match.group(2).strip() if org_match else "（一社）島根県作業療法士会"

        return {
            "title": title,
            "date": extracted_date,
            "place": extracted_place,
            "org": extracted_org,
            "raw_text": text[:200]
        }
    except Exception as e:
        return None

def wrap_and_get_font(text, max_width=900, initial_size=64, min_size=34):
    if not text or not os.path.exists(font_path):
        return [text or ""], ImageFont.load_default()

    size = initial_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        sample_char_w = font.getbbox("あ")[2] - font.getbbox("あ")[0]
        chars_per_line = max(1, int(max_width / sample_char_w))
        
        lines = textwrap.wrap(text, width=chars_per_line)
        
        all_fit = True
        for line in lines:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            if w > max_width:
                all_fit = False
                break
                
        if all_fit and len(lines) <= 4:
            return lines, font
            
        size -= 4

    font = ImageFont.truetype(font_path, min_size)
    lines = textwrap.wrap(text, width=16)
    return lines, font

def get_bg(mode):
    target_bg = BG_IMAGE_NOTICE if mode == "お知らせ" else BG_IMAGE_DEFAULT
    bg_p = os.path.join(".", target_bg)
    
    if os.path.exists(bg_p):
        return Image.open(bg_p).convert('RGB').resize((1080, 1080))
    elif os.path.exists(os.path.join(".", BG_IMAGE_DEFAULT)):
        return Image.open(os.path.join(".", BG_IMAGE_DEFAULT)).convert('RGB').resize((1080, 1080))
    else:
        return Image.new('RGB', (1080, 1080), color=(255, 255, 255))

def generate_posts(mode, 主催, タイトル, サブタイトル, 項目1, 項目2, second_type, 挿入画像, 詳細テキスト, ハッシュタグ):
    f_org, f_sub, f_label, f_val = load_fonts()

    # --- 1枚目生成 ---
    img1 = get_bg(mode)
    d1 = ImageDraw.Draw(img1)

    d1.text((540, 290), 主催 or "", fill=(30, 30, 30), font=f_org, anchor="mm")

    if mode == "研修会情報":
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=900, initial_size=64, min_size=34)
        line_height = f_title.size * 1.25
        total_height = line_height * len(title_lines)
        start_y = 430 - (total_height / 2) + (line_height / 2)

        for i, line in enumerate(title_lines):
            y = start_y + (i * line_height)
            d1.text((540, y), line, fill=(20, 20, 20), font=f_title, anchor="mm")

        if サブタイトル and サブタイトル.strip():
            sub_y = max(510, start_y + total_height + 20)
            d1.text((540, sub_y), サブタイトル, fill=(40, 40, 40), font=f_sub, anchor="mm")

        d1.text((540, 620), "【日時】", fill=(80, 80, 80), font=f_label, anchor="mm")
        d1.text((540, 665), 項目1 or "", fill=(30, 30, 30), font=f_val, anchor="mm")

        if 項目2 and 項目2.strip():
            d1.text((540, 745), "【場所】", fill=(80, 80, 80), font=f_label, anchor="mm")
            d1.text((540, 790), 項目2 or "", fill=(30, 30, 30), font=f_val, anchor="mm")

    else:
        title_lines, f_title = wrap_and_get_font(タイトル or "", max_width=880, initial_size=68, min_size=36)
        line_height = f_title.size * 1.3
        total_height = line_height * len(title_lines)
        start_y = 540 - (total_height / 2) + (line_height / 2)

        for i, line in enumerate(title_lines):
            y = start_y + (i * line_height)
            d1.text((540, y), line, fill=(20, 20, 20), font=f_title, anchor="mm")

        if サブタイトル and サブタイトル.strip():
            sub_y = start_y + total_height + 30
            d1.text((540, sub_y), サブタイトル, fill=(40, 40, 40), font=f_sub, anchor="mm")

    # --- 2枚目生成 ---
    img2 = get_bg(mode)
    d2 = ImageDraw.Draw(img2)

    if mode == "研修会情報" or (mode == "お知らせ" and second_type == "画像添付"):
        if 挿入画像 is not None:
            try:
                image_bytes = 挿入画像.getvalue()
                if image_bytes:
                    insert_img = Image.open(io.BytesIO(image_bytes))
                    if insert_img.mode != 'RGBA':
                        insert_img = insert_img.convert('RGBA')

                    max_w, max_h = 800, 800
                    try:
                        resample_filter = Image.Resampling.LANCZOS
                    except AttributeError:
                        resample_filter = Image.LANCZOS

                    insert_img.thumbnail((max_w, max_h), resample_filter)
                    pos_x = (1080 - insert_img.width) // 2
                    pos_y = (1080 - insert_img.height) // 2
                    img2.paste(insert_img, (pos_x, pos_y), mask=insert_img)
            except Exception:
                st.warning("画像の読み込みに失敗しました。")
    else:
        if 詳細テキスト and 詳細テキスト.strip():
            detail_lines, f_detail = wrap_and_get_font(詳細テキスト, max_width=850, initial_size=48, min_size=28)
            line_height = f_detail.size * 1.4
            total_height = line_height * len(detail_lines)
            start_y = 540 - (total_height / 2) + (line_height / 2)

            for i, line in enumerate(detail_lines):
                y = start_y + (i * line_height)
                d2.text((540, y), line, fill=(30, 30, 30), font=f_detail, anchor="mm")

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

with col1:
    # 💡 URLからの自動入力エリア
    with st.expander("🔗 Webページ（URL）から情報を自動読み込み", expanded=False):
        input_url = st.text_input("研修会やお知らせページのURLを入力", placeholder="https://example.com/event/123")
        if st.button("🌐 情報を自動取得する", use_container_width=True):
            if input_url:
                with st.spinner("ページ情報を取得中..."):
                    info = fetch_page_info(input_url)
                    if info:
                        st.session_state["auto_title"] = info["title"]
                        st.session_state["auto_date"] = info["date"]
                        st.session_state["auto_place"] = info["place"]
                        st.session_state["auto_org"] = info["org"]
                        st.success("情報をフォームに反映しました！")
                    else:
                        st.error("ページの読み込みに失敗しました。URLをご確認ください。")

    st.subheader("📄 1. テキスト入力")
    
    # セッション状態から取得値があるか判定
    val_org = st.session_state.get("auto_org", "（一社）島根県作業療法士会")
    val_title = st.session_state.get("auto_title", "")
    val_date = st.session_state.get("auto_date", "")
    val_place = st.session_state.get("auto_place", "")

    if mode == "研修会情報":
        主催 = st.text_input("主催者・団体名", value=val_org)
        タイトル = st.text_input("研修会名・イベントタイトル", value=val_title)
        サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）")
        項目1 = st.text_input("開催日時", value=val_date)
        項目2 = st.text_input("開催場所", value=val_place)
        second_type = "画像添付"
        詳細テキスト = ""
        
        st.subheader("📷 2. 2枚目の画像設定")
        挿入画像 = st.file_uploader("2枚目に挿入する画像（任意）", type=["png", "jpg", "jpeg"])

    else:
        主催 = st.text_input("発信元・団体名", value=val_org)
        タイトル = st.text_input("お知らせタイトル", value=val_title)
        サブタイトル = st.text_input("サブタイトル（不要な場合は空欄）")
        項目1, 項目2 = "", ""

        st.subheader("🖼️ 2. 2枚目のコンテンツ選択")
        
        type_options = ["📷 画像添付", "📝 詳細テキスト"]
        selected_type = st.pills(
            "2枚目の内容",
            type_options,
            default="📷 画像添付"
        )
        second_type = "画像添付" if "画像添付" in (selected_type or "") else "詳細テキスト"

        if second_type == "画像添付":
            挿入画像 = st.file_uploader("2枚目に挿入する画像", type=["png", "jpg", "jpeg"])
            詳細テキスト = ""
        else:
            挿入画像 = None
            詳細テキスト = st.text_area("2枚目に表示する詳細テキスト", value=val_title or "", placeholder="例：定時社員総会を開催いたしました！\nご参加いただいた皆様、ありがとうございました。")

    st.subheader("🏷️ 3. ハッシュタグ設定")
    ハッシュタグ = st.text_area("固定ハッシュタグ", value=DEFAULT_HASHTAGS, height=70)

    submit = st.button("✨ 画像と文章を作成する", type="primary", use_container_width=True)

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
