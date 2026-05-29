import csv
import os
import re
import shutil
import sys
import ctypes
from collections import OrderedDict, defaultdict
from datetime import datetime, date, timedelta
from io import BytesIO
from tkinter import Tk, Button, Label, Entry, Frame, StringVar, PhotoImage, filedialog, messagebox
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageFont


APP_TITLE = "마감 보고"
SPECIAL_TOP_CATEGORY = "누스&리퍼브"

# 표 색상
HEADER_FILL = "#d9e2f3"
FOOTER_FILL = "#d9e2f3"
GROUP_FILL = "#fce4d6"
WHITE_FILL = "#ffffff"
GRID_COLOR = "#111111"
TEXT_COLOR = "#111111"

# UI 색상
WINDOW_BG = "#f5f7fb"
CARD_BG = "#ffffff"
BUTTON_BG = "#f8fafc"
BUTTON_ACTIVE_BG = "#eef4ff"
ACCENT_BLUE = "#2563eb"
ACCENT_ORANGE = "#f97316"
BORDER_COLOR = "#d7deea"
TEXT_DARK = "#172033"
TEXT_MUTED = "#667085"

# 발송 통계 표 기본 크기
BALSONG_ROW_H = 22
BALSONG_LEFT_W = 121
BALSONG_RIGHT_W = 122
BALSONG_TABLE_W = 244

# 미발송 통계 표 기본 크기
UNSHIP_ROW_H = 22
UNSHIP_SIZE_W = 69
UNSHIP_TOTAL_W = 59
UNSHIP_DELAY_LEFT_W = 108
UNSHIP_DELAY_RIGHT_W = 120

# 선명도 보정: 실제 PNG는 2배 해상도로 그림
IMAGE_SCALE = 2
FONT_SIZE = 14


# =========================
# 공통 유틸
# =========================

def resource_path(filename):
    """PyInstaller onefile 실행과 일반 Python 실행을 모두 지원하는 리소스 경로."""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, filename)


def resource_font_path(filename):
    return resource_path(filename)


def load_font(size=14, bold=False, family="malgun"):
    """이미지용 폰트. 기본 글씨는 맑은 고딕, 숫자는 Arial 사용."""
    size = int(size * IMAGE_SCALE)

    if family == "arial":
        candidates = [
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    else:
        if bold:
            candidates = [
                r"C:\Windows\Fonts\malgunbd.ttf",
                r"C:\Windows\Fonts\malgun.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        else:
            candidates = [
                r"C:\Windows\Fonts\malgun.ttf",
                r"C:\Windows\Fonts\malgunbd.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]

    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


FONT_HEADER = load_font(FONT_SIZE, bold=True, family="malgun")
FONT_NORMAL = load_font(FONT_SIZE, bold=False, family="malgun")
FONT_BOLD = load_font(FONT_SIZE, bold=True, family="malgun")
FONT_NUM = load_font(FONT_SIZE, bold=False, family="arial")
FONT_NUM_BOLD = load_font(FONT_SIZE, bold=True, family="arial")


def scaled(value):
    return int(round(value * IMAGE_SCALE))


def parse_int(value, default=0):
    if value is None:
        return default

    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return default

    text = text.replace(",", "")
    text = text.replace("건", "")
    text = text.replace("개", "")
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.strip()

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default

    try:
        return int(float(match.group(0)))
    except ValueError:
        return default


def clean_text(value):
    if value is None:
        return ""

    text = str(value).strip()
    if text.lower() in ("nan", "none", "nat"):
        return ""
    return text


def product_number(product_name):
    text = str(product_name).strip().lower()
    match = re.search(r"n\s*0*(\d+)", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))

    return 10**15


def parse_date_from_filename(path):
    """파일명에서 날짜를 찾아 날짜표기, YYMMDD, date 객체를 반환."""
    name = os.path.basename(path)

    match = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        dt = date(y, m, d)
        return f"{m}월 {d}일", f"{str(y)[2:]}{m:02d}{d:02d}", dt

    match = re.search(r"(\d{2})(\d{2})(\d{2})", name)
    if match:
        y, m, d = 2000 + int(match.group(1)), int(match.group(2)), int(match.group(3))
        dt = date(y, m, d)
        return f"{m}월 {d}일", f"{str(y)[2:]}{m:02d}{d:02d}", dt

    now = datetime.now().date()
    return f"{now.month}월 {now.day}일", now.strftime("%y%m%d"), now


def unique_file_path(folder, filename):
    base, ext = os.path.splitext(filename)
    path = os.path.join(folder, filename)

    if not os.path.exists(path):
        return path

    index = 1
    while True:
        new_path = os.path.join(folder, f"{base}_{index}{ext}")
        if not os.path.exists(new_path):
            return new_path
        index += 1


def text_bbox(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)


def draw_rect(draw, x, y, w, h, fill):
    draw.rectangle(
        [scaled(x), scaled(y), scaled(x + w) - 1, scaled(y + h) - 1],
        fill=fill,
    )


def draw_text_center(draw, x, y, w, h, text, font, fill=TEXT_COLOR):
    text = str(text)
    bbox = text_bbox(draw, text, font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = scaled(x) + (scaled(w) - tw) // 2 - bbox[0]
    ty = scaled(y) + (scaled(h) - th) // 2 - bbox[1]

    draw.text((int(tx), int(ty)), text, font=font, fill=fill)


def draw_text_left(draw, x, y, w, h, text, font, padding=6, fill=TEXT_COLOR):
    text = str(text)
    bbox = text_bbox(draw, text, font)
    th = bbox[3] - bbox[1]

    tx = scaled(x + padding) - bbox[0]
    ty = scaled(y) + (scaled(h) - th) // 2 - bbox[1]

    draw.text((int(tx), int(ty)), text, font=font, fill=fill)


def draw_number_center(draw, x, y, w, h, number, bold=False):
    text = "" if number in (None, "", 0) else str(number)
    if not text:
        return
    draw_text_center(draw, x, y, w, h, text, FONT_NUM_BOLD if bold else FONT_NUM)


def draw_number_right(draw, x, y, w, h, number, bold=False, padding=6):
    text = "" if number in (None, "", 0) else str(number)
    if not text:
        return

    font = FONT_NUM_BOLD if bold else FONT_NUM
    bbox = text_bbox(draw, text, font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = scaled(x + w - padding) - tw - bbox[0]
    ty = scaled(y) + (scaled(h) - th) // 2 - bbox[1]
    draw.text((int(tx), int(ty)), text, font=font, fill=TEXT_COLOR)


def draw_count_with_unit_right(draw, x, y, w, h, quantity, bold_number=False, padding=6):
    qty_text = str(quantity)
    unit_text = " (건)"
    qty_font = FONT_NUM_BOLD if bold_number else FONT_NUM
    unit_font = FONT_NORMAL

    qty_bbox = text_bbox(draw, qty_text, qty_font)
    unit_bbox = text_bbox(draw, unit_text, unit_font)

    qty_w = qty_bbox[2] - qty_bbox[0]
    unit_w = unit_bbox[2] - unit_bbox[0]
    total_w = qty_w + unit_w

    start_x = scaled(x + w - padding) - total_w

    qty_h = qty_bbox[3] - qty_bbox[1]
    unit_h = unit_bbox[3] - unit_bbox[1]

    qty_y = scaled(y) + (scaled(h) - qty_h) // 2 - qty_bbox[1]
    unit_y = scaled(y) + (scaled(h) - unit_h) // 2 - unit_bbox[1]

    draw.text((int(start_x - qty_bbox[0]), int(qty_y)), qty_text, font=qty_font, fill=TEXT_COLOR)
    draw.text((int(start_x + qty_w - unit_bbox[0]), int(unit_y)), unit_text, font=unit_font, fill=TEXT_COLOR)


def draw_grid(draw, widths, row_count, row_h):
    table_w = sum(widths)
    table_h = row_count * row_h
    line_w = max(1, IMAGE_SCALE)

    x = 0
    for w in widths:
        draw.line([scaled(x), 0, scaled(x), scaled(table_h)], fill=GRID_COLOR, width=line_w)
        x += w
    draw.line([scaled(table_w) - 1, 0, scaled(table_w) - 1, scaled(table_h)], fill=GRID_COLOR, width=line_w)

    for r in range(row_count + 1):
        y = r * row_h
        draw.line([0, scaled(y), scaled(table_w), scaled(y)], fill=GRID_COLOR, width=line_w)


def draw_expand_icon(draw, x, y, row_h):
    size = 10
    icon_x = scaled(x)
    icon_y = scaled(y + (row_h - size) / 2)
    icon_s = scaled(size)
    line_w = max(1, IMAGE_SCALE)

    draw.rectangle(
        [icon_x, icon_y, icon_x + icon_s, icon_y + icon_s],
        fill="#ffffff",
        outline="#9aa9b8",
        width=line_w,
    )
    draw.line(
        [icon_x + scaled(2), icon_y + icon_s // 2, icon_x + icon_s - scaled(2), icon_y + icon_s // 2],
        fill="#5f6f7f",
        width=line_w,
    )


def draw_text_with_icon_left(draw, x, y, w, h, text, font, icon_x=6):
    draw_expand_icon(draw, x + icon_x, y, h)
    draw_text_left(draw, x, y, w, h, text, font, padding=icon_x + 14)


def draw_text_with_icon_center(draw, x, y, w, h, text, font):
    text = str(text)
    bbox = text_bbox(draw, text, font)
    tw = bbox[2] - bbox[0]
    icon_w = scaled(12)
    gap = scaled(3)
    total_w = icon_w + gap + tw
    start_x = scaled(x) + (scaled(w) - total_w) // 2

    logical_icon_x = start_x / IMAGE_SCALE
    draw_expand_icon(draw, logical_icon_x, y, h)

    th = bbox[3] - bbox[1]
    ty = scaled(y) + (scaled(h) - th) // 2 - bbox[1]
    draw.text((int(start_x + icon_w + gap - bbox[0]), int(ty)), text, font=font, fill=TEXT_COLOR)


# =========================
# 발송 통계 CSV 처리
# =========================

def read_csv_flexible(csv_path):
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error = None

    for enc in encodings:
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                sample = f.read(4096)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(f, dialect=dialect)
                rows = []
                for row in reader:
                    cleaned = {}
                    for key, value in row.items():
                        if key is None:
                            continue
                        cleaned[str(key).strip()] = value
                    rows.append(cleaned)

                return rows
        except Exception as e:
            last_error = e

    raise RuntimeError(f"CSV 파일을 읽지 못했습니다. {last_error}")


def find_column(columns, target_name):
    normalized_target = target_name.replace(" ", "").strip()
    for col in columns:
        normalized_col = str(col).replace(" ", "").strip()
        if normalized_col == normalized_target:
            return col
    return None


def build_balsong_summary(csv_path):
    rows = read_csv_flexible(csv_path)
    if not rows:
        raise RuntimeError("CSV 안에 데이터가 없습니다.")

    columns = list(rows[0].keys())
    category_col = find_column(columns, "상품분류명")
    product_col = find_column(columns, "사입상품명")
    quantity_col = find_column(columns, "발송수량")

    missing = []
    if not category_col:
        missing.append("상품분류명")
    if not product_col:
        missing.append("사입상품명")
    if not quantity_col:
        missing.append("발송수량")

    if missing:
        raise RuntimeError(f"필수 컬럼을 찾지 못했습니다: {', '.join(missing)}")

    summary = OrderedDict()

    for row in rows:
        category = clean_text(row.get(category_col))
        product = clean_text(row.get(product_col))
        quantity = parse_int(row.get(quantity_col), default=0)

        if not category or not product or quantity == 0:
            continue

        if category not in summary:
            summary[category] = {"total": 0, "products": defaultdict(int)}

        summary[category]["total"] += quantity
        summary[category]["products"][product] += quantity

    if not summary:
        raise RuntimeError("집계할 데이터가 없습니다.")

    sorted_categories = []
    if SPECIAL_TOP_CATEGORY in summary:
        sorted_categories.append((SPECIAL_TOP_CATEGORY, summary[SPECIAL_TOP_CATEGORY]))

    others = [(cat, data) for cat, data in summary.items() if cat != SPECIAL_TOP_CATEGORY]
    others.sort(key=lambda item: (-item[1]["total"], item[0]))
    sorted_categories.extend(others)

    result = []
    grand_total = 0

    for category, data in sorted_categories:
        grand_total += data["total"]
        products = list(data["products"].items())
        products.sort(key=lambda item: (-item[1], product_number(item[0]), item[0]))
        result.append({"category": category, "total": data["total"], "products": products})

    return result, grand_total


def create_balsong_image(csv_path, output_path):
    summary, grand_total = build_balsong_summary(csv_path)
    date_label, _, _ = parse_date_from_filename(csv_path)

    rows = [("header", date_label, "합계 : 발송수량")]
    for group in summary:
        rows.append(("category", group["category"], group["total"]))
        for product, quantity in group["products"]:
            rows.append(("product", product, quantity))
    rows.append(("footer", "총합계", grand_total))

    row_count = len(rows)
    image = Image.new("RGB", (scaled(BALSONG_TABLE_W), scaled(row_count * BALSONG_ROW_H)), WHITE_FILL)
    draw = ImageDraw.Draw(image)

    for row_index, row in enumerate(rows):
        row_type = row[0]
        y = row_index * BALSONG_ROW_H

        if row_type == "header":
            draw_rect(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, HEADER_FILL)
            draw_rect(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, HEADER_FILL)
            draw_text_center(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, row[1], FONT_HEADER)
            draw_text_center(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, row[2], FONT_HEADER)

        elif row_type == "category":
            draw_rect(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, GROUP_FILL)
            draw_rect(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, GROUP_FILL)
            draw_text_center(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, row[1], FONT_BOLD)
            draw_count_with_unit_right(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, row[2], bold_number=True)

        elif row_type == "product":
            draw_rect(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, WHITE_FILL)
            draw_rect(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, WHITE_FILL)
            draw_text_center(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, row[1], FONT_NORMAL)
            draw_count_with_unit_right(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, row[2], bold_number=False)

        elif row_type == "footer":
            draw_rect(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, FOOTER_FILL)
            draw_rect(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, FOOTER_FILL)
            draw_text_center(draw, 0, y, BALSONG_LEFT_W, BALSONG_ROW_H, row[1], FONT_BOLD)
            draw_count_with_unit_right(draw, BALSONG_LEFT_W, y, BALSONG_RIGHT_W, BALSONG_ROW_H, row[2], bold_number=True)

    draw_grid(draw, [BALSONG_LEFT_W, BALSONG_RIGHT_W], row_count, BALSONG_ROW_H)
    image.save(output_path, "PNG")


# =========================
# 미발송 통계 엑셀 처리
# =========================

def read_excel_raw_sheets(excel_path, password=""):
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas가 설치되어 있지 않습니다. requirements.txt를 업데이트하세요.")

    ext = os.path.splitext(excel_path)[1].lower()
    password = clean_text(password)

    def read_from_source(source):
        kwargs = {
            "sheet_name": None,
            "header": None,
            "dtype": object,
        }
        if ext == ".xls":
            kwargs["engine"] = "xlrd"
        elif ext in (".xlsx", ".xlsm"):
            kwargs["engine"] = "openpyxl"
        return pd.read_excel(source, **kwargs)

    if password:
        try:
            import msoffcrypto
            decrypted = BytesIO()
            with open(excel_path, "rb") as f:
                office_file = msoffcrypto.OfficeFile(f)
                office_file.load_key(password=password)
                office_file.decrypt(decrypted)
            decrypted.seek(0)
            return read_from_source(decrypted)
        except Exception as e:
            raise RuntimeError(f"엑셀 암호가 틀렸거나 파일을 열 수 없습니다. {e}")

    try:
        return read_from_source(excel_path)
    except Exception as first_error:
        # 암호화 파일인데 암호 입력을 안 한 경우가 많음
        raise RuntimeError(f"엑셀 파일을 읽지 못했습니다. 암호가 필요하면 암호칸에 입력하세요. {first_error}")


def normalize_header(value):
    return re.sub(r"\s+", "", clean_text(value)).lower()


def make_unique_headers(values):
    headers = []
    seen = defaultdict(int)
    for idx, value in enumerate(values):
        name = clean_text(value)
        if not name:
            name = f"컬럼{idx + 1}"
        seen[name] += 1
        if seen[name] > 1:
            name = f"{name}_{seen[name]}"
        headers.append(name)
    return headers


def score_header_row(values):
    text = " ".join(clean_text(v) for v in values)
    norm = normalize_header(text)

    keyword_groups = [
        ["상품명", "품명", "품번", "상품코드", "사입상품명"],
        ["옵션", "색상", "컬러", "color"],
        ["사이즈", "size", "mm"],
        ["주문수량", "수량", "qty"],
        ["미발송", "지연", "경과", "주문일", "결제일", "발송예정"],
    ]

    score = 0
    for group in keyword_groups:
        if any(k.lower() in norm for k in group):
            score += 1

    non_empty = sum(1 for v in values if clean_text(v))
    if non_empty >= 5:
        score += 1

    return score


def find_best_order_dataframe(raw_sheets):
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas가 설치되어 있지 않습니다.")

    best = None

    for sheet_name, raw in raw_sheets.items():
        if raw is None or raw.empty:
            continue

        max_check = min(len(raw), 50)
        for row_idx in range(max_check):
            values = raw.iloc[row_idx].tolist()
            score = score_header_row(values)
            if best is None or score > best[0]:
                best = (score, sheet_name, row_idx, raw)

    if best is None or best[0] < 3:
        raise RuntimeError("엑셀에서 주문 목록 헤더를 찾지 못했습니다.")

    _, _, header_row, raw = best
    headers = make_unique_headers(raw.iloc[header_row].tolist())
    data = raw.iloc[header_row + 1:].copy()
    data.columns = headers
    data = data.dropna(how="all")

    # 완전히 빈 문자열 행 제거
    mask = data.apply(lambda row: any(clean_text(v) for v in row.values), axis=1)
    data = data.loc[mask].reset_index(drop=True)

    return data


def find_columns_by_keywords(columns, keywords):
    result = []
    for col in columns:
        norm = normalize_header(col)
        if any(k.lower().replace(" ", "") in norm for k in keywords):
            result.append(col)
    return result


def first_non_empty(row, columns):
    for col in columns:
        value = clean_text(row.get(col))
        if value:
            return value
    return ""


def concat_columns(row, columns):
    parts = []
    for col in columns:
        value = clean_text(row.get(col))
        if value:
            parts.append(value)
    return " ".join(parts)


def extract_product_code(row, columns):
    primary_cols = find_columns_by_keywords(columns, ["품번", "사입상품명", "상품코드", "상품번호", "관리코드"])
    secondary_cols = find_columns_by_keywords(columns, ["상품명", "품명", "옵션", "상품옵션", "옵션명", "옵션정보"])

    for group_cols in (primary_cols, secondary_cols, columns):
        text = concat_columns(row, group_cols)
        match = re.search(r"\bn\s*0*\d+\b", text, flags=re.IGNORECASE)
        if match:
            raw = re.sub(r"\s+", "", match.group(0)).lower()
            return raw

    return ""


def extract_size(row, columns):
    size_cols = find_columns_by_keywords(columns, ["사이즈", "size", "규격"])
    option_cols = find_columns_by_keywords(columns, ["옵션", "옵션명", "옵션정보", "상품옵션", "상품명", "품명", "사이즈", "size"])

    for group_cols in (size_cols, option_cols, columns):
        text = concat_columns(row, group_cols)
        match = re.search(r"\b(2[0-9]{2})\s*(?:mm|MM|미리)?\b", text)
        if match:
            return f"{int(match.group(1))}mm"

    return "사이즈없음"


def remove_main_product_code(text, product):
    if not product:
        return text
    pattern = re.escape(product)
    return re.sub(pattern, " ", text, flags=re.IGNORECASE)


def extract_color(row, columns, product, size):
    color_cols = find_columns_by_keywords(columns, ["색상", "컬러", "color"])
    value = first_non_empty(row, color_cols)
    if value:
        return clean_color_text(value, product, size)

    option_cols = find_columns_by_keywords(columns, ["옵션명", "옵션정보", "상품옵션", "옵션", "상품명", "품명"])
    text = concat_columns(row, option_cols if option_cols else columns)
    return clean_color_text(text, product, size)


def clean_color_text(text, product, size):
    text = clean_text(text)
    if not text:
        return "색상없음"

    # 라벨 제거
    text = re.sub(r"색상\s*[:：]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"컬러\s*[:：]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"color\s*[:：]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"사이즈\s*[:：]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"size\s*[:：]", " ", text, flags=re.IGNORECASE)

    # 사이즈 제거
    text = re.sub(r"\b2[0-9]{2}\s*(?:mm|MM|미리)?\b", " ", text)

    # 주 품번만 제거. [n5309] 같은 보조 품번은 색상명으로 남길 수 있어야 하므로 완전 동일 주품번만 제거.
    text = remove_main_product_code(text, product)

    candidates = []
    for token in re.split(r"[\n\r/|,;>]+", text):
        token = token.strip(" -_\t")
        if not token:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        if re.search(r"\b2[0-9]{2}\b", token):
            continue
        candidates.append(token)

    if candidates:
        # 너무 긴 상품명보다 색상에 가까운 마지막 후보를 우선
        color = candidates[-1]
    else:
        color = text

    color = re.sub(r"\s+", " ", color).strip(" -_/")
    if not color:
        color = "색상없음"

    return color


def extract_quantity(row, columns):
    qty_cols = find_columns_by_keywords(columns, ["주문수량", "수량", "qty", "quantity"])
    # 금액/가격 계열은 제외
    qty_cols = [c for c in qty_cols if not any(x in normalize_header(c) for x in ["금액", "가격", "단가", "배송비"])]

    for col in qty_cols:
        value = parse_int(row.get(col), default=None)
        if value is not None:
            return max(0, value)

    return 1


def parse_possible_date(value):
    text = clean_text(value)
    if not text:
        return None

    # 엑셀 시리얼 날짜 가능성
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        num = float(text)
        if 20000 <= num <= 80000:
            return date(1899, 12, 30) + timedelta(days=int(num))

    patterns = [
        r"(20\d{2})[-./년\s]*(\d{1,2})[-./월\s]*(\d{1,2})",
        r"(\d{2})[-./년\s]*(\d{1,2})[-./월\s]*(\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            y = int(match.group(1))
            if y < 100:
                y += 2000
            m = int(match.group(2))
            d = int(match.group(3))
            try:
                return date(y, m, d)
            except ValueError:
                return None

    return None


def extract_delay_days(row, columns, report_date):
    delay_cols = find_columns_by_keywords(columns, ["지연", "미발송", "경과"])
    for col in delay_cols:
        text = clean_text(row.get(col))
        if not text:
            continue
        match = re.search(r"(\d+)\s*일", text)
        if match:
            return int(match.group(1))
        value = parse_int(text, default=None)
        if value is not None:
            return max(0, value)

    date_cols = find_columns_by_keywords(columns, ["주문일", "결제일", "주문일시", "등록일", "수집일", "접수일"])
    for col in date_cols:
        dt = parse_possible_date(row.get(col))
        if dt:
            return max(0, (report_date - dt).days)

    return 0


def parse_option_color_size(option_text):
    """옵션내용 예: 'Black,245mm' -> ('Black', '245mm')"""
    text = clean_text(option_text)
    if not text:
        return "색상없음", "사이즈없음"

    # 보통 마지막 콤마 뒤가 사이즈, 앞부분 전체가 색상
    if "," in text:
        color_part, size_part = text.rsplit(",", 1)
        color = re.sub(r"\s+", " ", color_part).strip()
        size_match = re.search(r"(2\d{2})\s*(?:mm|MM)?", size_part)
        size = f"{int(size_match.group(1))}mm" if size_match else clean_text(size_part)
        return color or "색상없음", size or "사이즈없음"

    size_match = re.search(r"(2\d{2})\s*(?:mm|MM)?", text)
    if size_match:
        size = f"{int(size_match.group(1))}mm"
        color = re.sub(r"(2\d{2})\s*(?:mm|MM)?", " ", text).strip(" ,-/")
        return color or "색상없음", size

    return text, "사이즈없음"


def parse_delay_label(value):
    text = clean_text(value)
    if not text:
        return 0, "00일지연"

    match = re.search(r"(\d+)\s*일", text)
    if match:
        days = int(match.group(1))
    else:
        days = parse_int(text, default=0)

    return days, f"{days:02d}일 지연"


def find_exact_or_keyword_column(columns, exact_name, keywords):
    for col in columns:
        if normalize_header(col) == normalize_header(exact_name):
            return col

    found = find_columns_by_keywords(columns, keywords)
    return found[0] if found else None


def extract_unshipped_records(excel_path, password):
    raw_sheets = read_excel_raw_sheets(excel_path, password=password)
    df = find_best_order_dataframe(raw_sheets)
    columns = list(df.columns)

    delay_col = find_exact_or_keyword_column(columns, "배송지연일", ["배송지연일", "지연"])
    product_col = find_exact_or_keyword_column(columns, "재고매칭(1)사입상품명", ["사입상품명", "품번", "상품코드"])
    option_col = find_exact_or_keyword_column(columns, "재고매칭(1)옵션내용", ["옵션내용", "옵션", "상품옵션"])
    quantity_col = find_exact_or_keyword_column(columns, "재고매칭(1)주문수량", ["주문수량", "수량", "qty"])

    missing = []
    if not delay_col:
        missing.append("배송지연일")
    if not product_col:
        missing.append("재고매칭(1)사입상품명")
    if not option_col:
        missing.append("재고매칭(1)옵션내용")
    if not quantity_col:
        missing.append("재고매칭(1)주문수량")

    if missing:
        raise RuntimeError(f"미발송 엑셀 필수 컬럼을 찾지 못했습니다: {', '.join(missing)}")

    records = []
    product_seen = OrderedDict()
    color_seen = defaultdict(OrderedDict)
    product_delay_seen = defaultdict(OrderedDict)

    for _, row in df.iterrows():
        product_raw = clean_text(row.get(product_col))
        match = re.search(r"n\s*0*\d+", product_raw, flags=re.IGNORECASE)
        if match:
            product = re.sub(r"\s+", "", match.group(0)).lower()
        else:
            product = product_raw.strip().lower()

        if not product:
            continue

        quantity = parse_int(row.get(quantity_col), default=0)
        if quantity <= 0:
            continue

        color, size = parse_option_color_size(row.get(option_col))
        delay_days, delay_label = parse_delay_label(row.get(delay_col))

        if product not in product_seen:
            product_seen[product] = None
        if color not in color_seen[product]:
            color_seen[product][color] = None
        if product not in product_delay_seen[delay_label]:
            product_delay_seen[delay_label][product] = None

        records.append({
            "product": product,
            "color": color,
            "size": size,
            "quantity": quantity,
            "delay_days": delay_days,
            "delay_label": delay_label,
        })

    if not records:
        raise RuntimeError("미발송 통계로 집계할 데이터를 찾지 못했습니다.")

    return records, list(product_seen.keys()), color_seen, product_delay_seen

def build_unshipped_size_summary(records, product_order, color_order_map):
    sizes = sorted(
        {r["size"] for r in records if r["size"] != "사이즈없음"},
        key=lambda s: parse_int(s, default=99999),
    )

    if not sizes:
        sizes = ["사이즈없음"]

    color_summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    product_summary = defaultdict(lambda: defaultdict(int))
    total_by_size = defaultdict(int)
    grand_total = 0

    for r in records:
        p, c, s, q = r["product"], r["color"], r["size"], r["quantity"]
        color_summary[p][c][s] += q
        product_summary[p][s] += q
        total_by_size[s] += q
        grand_total += q

    rows = []
    sorted_products = sorted(product_order, key=lambda p: (product_number(p), p))
    for product in sorted_products:
        product_total = sum(product_summary[product].values())
        rows.append({"type": "product", "label": product, "sizes": dict(product_summary[product]), "total": product_total})

        for color in color_order_map[product].keys():
            color_sizes = dict(color_summary[product][color])
            color_total = sum(color_sizes.values())
            rows.append({"type": "color", "label": color, "sizes": color_sizes, "total": color_total})

    footer = {"type": "footer", "label": "총합계", "sizes": dict(total_by_size), "total": grand_total}
    return sizes, rows, footer


def create_unshipped_size_image(records, product_order, color_order_map, output_path):
    sizes, rows, footer = build_unshipped_size_summary(records, product_order, color_order_map)

    # 긴 색상명 때문에 왼쪽 칸은 자동 보정
    tmp = Image.new("RGB", (10, 10), WHITE_FILL)
    tmp_draw = ImageDraw.Draw(tmp)
    max_label_w = 170
    for row in rows:
        font = FONT_BOLD if row["type"] == "product" else FONT_NORMAL
        bbox = text_bbox(tmp_draw, row["label"], font)
        text_w = (bbox[2] - bbox[0]) // IMAGE_SCALE
        if row["type"] == "color":
            max_label_w = max(max_label_w, text_w + 46)
        else:
            max_label_w = max(max_label_w, text_w + 22)
    left_w = max_label_w

    widths = [left_w] + [UNSHIP_SIZE_W for _ in sizes] + [UNSHIP_TOTAL_W]
    table_w = sum(widths)

    header_rows = 1
    all_rows = rows + [footer]
    row_count = header_rows + len(all_rows)
    image = Image.new("RGB", (scaled(table_w), scaled(row_count * UNSHIP_ROW_H)), WHITE_FILL)
    draw = ImageDraw.Draw(image)

    # 헤더 1행만 유지 (사이즈 텍스트 줄 삭제)
    y = 0
    x = 0
    draw_rect(draw, x, y, left_w, UNSHIP_ROW_H, HEADER_FILL)
    draw_text_center(draw, x, y, left_w, UNSHIP_ROW_H, "품번/색상", FONT_HEADER)
    x += left_w
    for size in sizes:
        draw_rect(draw, x, y, UNSHIP_SIZE_W, UNSHIP_ROW_H, HEADER_FILL)
        draw_text_center(draw, x, y, UNSHIP_SIZE_W, UNSHIP_ROW_H, size, FONT_HEADER)
        x += UNSHIP_SIZE_W
    draw_rect(draw, x, y, UNSHIP_TOTAL_W, UNSHIP_ROW_H, HEADER_FILL)
    draw_text_center(draw, x, y, UNSHIP_TOTAL_W, UNSHIP_ROW_H, "총합계", FONT_HEADER)

    # 본문
    for idx, row in enumerate(all_rows):
        y = (header_rows + idx) * UNSHIP_ROW_H
        row_type = row["type"]
        fill = GROUP_FILL if row_type == "product" else FOOTER_FILL if row_type == "footer" else WHITE_FILL
        bold = row_type in ("product", "footer")

        x = 0
        draw_rect(draw, x, y, left_w, UNSHIP_ROW_H, fill)
        if row_type == "product":
            draw_text_center(draw, x, y, left_w, UNSHIP_ROW_H, row["label"], FONT_BOLD)
        elif row_type == "footer":
            draw_text_center(draw, x, y, left_w, UNSHIP_ROW_H, row["label"], FONT_BOLD)
        else:
            draw_text_left(draw, x, y, left_w, UNSHIP_ROW_H, row["label"], FONT_NORMAL, padding=38)
        x += left_w

        for size in sizes:
            draw_rect(draw, x, y, UNSHIP_SIZE_W, UNSHIP_ROW_H, fill)
            draw_number_center(draw, x, y, UNSHIP_SIZE_W, UNSHIP_ROW_H, row["sizes"].get(size, 0), bold=bold)
            x += UNSHIP_SIZE_W

        draw_rect(draw, x, y, UNSHIP_TOTAL_W, UNSHIP_ROW_H, fill)
        draw_number_center(draw, x, y, UNSHIP_TOTAL_W, UNSHIP_ROW_H, row["total"], bold=bold)

    draw_grid(draw, widths, row_count, UNSHIP_ROW_H)
    image.save(output_path, "PNG")


def build_unshipped_delay_summary(records, product_delay_seen):
    delay_summary = defaultdict(lambda: defaultdict(int))
    delay_total = defaultdict(int)
    grand_total = 0

    for r in records:
        d = r["delay_label"]
        p = r["product"]
        q = r["quantity"]
        delay_summary[d][p] += q
        delay_total[d] += q
        grand_total += q

    delay_labels = sorted(delay_summary.keys(), key=lambda label: parse_int(label, default=99999))
    rows = []

    for label in delay_labels:
        rows.append({"type": "delay", "label": label, "total": delay_total[label]})
        product_order = sorted(delay_summary[label].keys(), key=lambda p: (product_number(p), p))
        for product in product_order:
            qty = delay_summary[label][product]
            if qty > 0:
                rows.append({"type": "product", "label": product, "total": qty})

    rows.append({"type": "footer", "label": "총합계", "total": grand_total})
    return rows


def create_unshipped_delay_image(records, product_delay_seen, output_path):
    rows = build_unshipped_delay_summary(records, product_delay_seen)
    widths = [UNSHIP_DELAY_LEFT_W, UNSHIP_DELAY_RIGHT_W]
    table_w = sum(widths)
    row_count = 1 + len(rows)

    image = Image.new("RGB", (scaled(table_w), scaled(row_count * UNSHIP_ROW_H)), WHITE_FILL)
    draw = ImageDraw.Draw(image)

    # 헤더
    y = 0
    draw_rect(draw, 0, y, widths[0], UNSHIP_ROW_H, HEADER_FILL)
    draw_rect(draw, widths[0], y, widths[1], UNSHIP_ROW_H, HEADER_FILL)
    draw_text_center(draw, 0, y, widths[0], UNSHIP_ROW_H, "미발송건", FONT_HEADER)
    draw_text_center(draw, widths[0], y, widths[1], UNSHIP_ROW_H, "합계 : 주문수량", FONT_HEADER)

    # 본문
    for idx, row in enumerate(rows):
        y = (idx + 1) * UNSHIP_ROW_H
        row_type = row["type"]
        fill = GROUP_FILL if row_type == "delay" else FOOTER_FILL if row_type == "footer" else WHITE_FILL
        bold = row_type in ("delay", "footer")

        draw_rect(draw, 0, y, widths[0], UNSHIP_ROW_H, fill)
        draw_rect(draw, widths[0], y, widths[1], UNSHIP_ROW_H, fill)

        if row_type == "delay":
            draw_text_center(draw, 0, y, widths[0], UNSHIP_ROW_H, row["label"], FONT_BOLD)
        elif row_type == "footer":
            draw_text_center(draw, 0, y, widths[0], UNSHIP_ROW_H, row["label"], FONT_BOLD)
        else:
            draw_text_center(draw, 0, y, widths[0], UNSHIP_ROW_H, row["label"], FONT_NORMAL)

        draw_number_center(draw, widths[0], y, widths[1], UNSHIP_ROW_H, row["total"], bold=bold)

    draw_grid(draw, widths, row_count, UNSHIP_ROW_H)
    image.save(output_path, "PNG")


def create_unshipped_images(excel_path, password, output_path_1, output_path_2):
    records, product_order, color_order_map, product_delay_seen = extract_unshipped_records(excel_path, password=password)
    # 이미지 순서 변경: (1)=지연일수별 표, (2)=사이즈별 표
    create_unshipped_delay_image(records, product_delay_seen, output_path_1)
    create_unshipped_size_image(records, product_order, color_order_map, output_path_2)


def set_windows_app_user_model_id():
    """작업표시줄 그룹 아이콘이 프로그램 아이콘을 쓰도록 Windows AppUserModelID 설정."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("No1Overtake.MagamReport.1")
    except Exception:
        pass


def apply_window_icon(root):
    """창 왼쪽 위 아이콘과 작업표시줄 아이콘에 1.png 적용."""
    icon_path = resource_path("1.png")
    if not os.path.exists(icon_path):
        return None
    try:
        icon_image = PhotoImage(file=icon_path)
        root.iconphoto(True, icon_image)
        return icon_image
    except Exception:
        return None


# =========================
# GUI
# =========================

class ClosingReportApp:
    WINDOW_W = 620
    WINDOW_H = 270

    def __init__(self):
        set_windows_app_user_model_id()

        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self.root.resizable(False, False)
        self.root.configure(bg=WINDOW_BG)
        self.app_icon = apply_window_icon(self.root)
        self.center_window(self.WINDOW_W, self.WINDOW_H)

        self.title_font = tkfont.Font(family="Malgun Gothic", size=17, weight="bold")
        self.subtitle_font = tkfont.Font(family="Malgun Gothic", size=9)
        self.ui_font = tkfont.Font(family="Malgun Gothic", size=10)
        self.button_font = tkfont.Font(family="Malgun Gothic", size=17, weight="bold")
        self.button_sub_font = tkfont.Font(family="Malgun Gothic", size=8)
        self.small_font = tkfont.Font(family="Malgun Gothic", size=9)
        self.status_font = tkfont.Font(family="Malgun Gothic", size=9, weight="bold")

        self.save_folder = StringVar(value="")
        self.password_value = StringVar(value="")
        self.status_value = StringVar(value="저장 폴더를 선택한 뒤 통계 버튼을 눌러주세요.")

        self.create_widgets()

    def center_window(self, width, height):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def make_card_button(self, x, y, title, subtitle, accent_color, command):
        card = Frame(self.root, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card.place(x=x, y=y, width=270, height=88)

        accent = Frame(card, bg=accent_color)
        accent.place(x=0, y=0, width=6, height=88)

        title_label = Label(
            card,
            text=title,
            font=self.button_font,
            bg=CARD_BG,
            fg=TEXT_DARK,
            anchor="w",
        )
        title_label.place(x=22, y=14, width=205, height=30)

        subtitle_label = Label(
            card,
            text=subtitle,
            font=self.button_sub_font,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            anchor="w",
        )
        subtitle_label.place(x=23, y=48, width=205, height=22)

        button = Button(
            card,
            text="실행",
            font=self.ui_font,
            fg="#ffffff",
            bg=accent_color,
            activeforeground="#ffffff",
            activebackground=accent_color,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=command,
        )
        button.place(x=211, y=26, width=43, height=34)

        def set_card_bg(color):
            card.configure(bg=color)
            title_label.configure(bg=color)
            subtitle_label.configure(bg=color)

        def on_enter(_event):
            set_card_bg(BUTTON_ACTIVE_BG)

        def on_leave(_event):
            set_card_bg(CARD_BG)

        for widget in (card, title_label, subtitle_label, button):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", lambda _event: command())

        return card, button, title_label

    def create_widgets(self):
        title_label = Label(
            self.root,
            text="마감 보고",
            font=self.title_font,
            bg=WINDOW_BG,
            fg=TEXT_DARK,
            anchor="w",
        )
        title_label.place(x=32, y=18, width=240, height=28)

        subtitle_label = Label(
            self.root,
            text="CSV 발송 통계와 엑셀 미발송 통계를 이미지로 자동 저장합니다.",
            font=self.subtitle_font,
            bg=WINDOW_BG,
            fg=TEXT_MUTED,
            anchor="w",
        )
        subtitle_label.place(x=33, y=48, width=520, height=20)

        _, self.balsong_button, self.balsong_title = self.make_card_button(
            32,
            78,
            "발송 통계",
            "발송 CSV 선택 → 이미지 저장",
            ACCENT_BLUE,
            self.run_balsong_summary,
        )

        _, self.unshipped_button, self.unshipped_title = self.make_card_button(
            318,
            78,
            "미발송 통계",
            "암호 엑셀 선택 → 이미지 2장 저장",
            ACCENT_ORANGE,
            self.run_unshipped_summary,
        )

        control_card = Frame(self.root, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        control_card.place(x=32, y=182, width=556, height=58)

        self.folder_button = Button(
            control_card,
            text="저장 폴더 선택",
            font=self.ui_font,
            bg=BUTTON_BG,
            fg=TEXT_DARK,
            activebackground=BUTTON_ACTIVE_BG,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.choose_save_folder,
        )
        self.folder_button.place(x=14, y=14, width=112, height=30)

        self.folder_entry = Entry(
            control_card,
            textvariable=self.save_folder,
            font=self.small_font,
            relief="flat",
            bd=0,
            state="readonly",
            readonlybackground="#f8fafc",
            fg=TEXT_DARK,
        )
        self.folder_entry.place(x=136, y=14, width=250, height=30)

        self.password_label = Label(
            control_card,
            text="엑셀 암호",
            font=self.small_font,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            anchor="w",
        )
        self.password_label.place(x=400, y=4, width=120, height=18)

        self.password_entry = Entry(
            control_card,
            textvariable=self.password_value,
            font=self.ui_font,
            relief="flat",
            bd=0,
            show="*",
            bg="#f8fafc",
            fg=TEXT_DARK,
        )
        self.password_entry.place(x=400, y=22, width=140, height=24)

        self.status_label = Label(
            self.root,
            textvariable=self.status_value,
            font=self.status_font,
            bg=WINDOW_BG,
            fg=TEXT_MUTED,
            anchor="w",
        )
        self.status_label.place(x=34, y=244, width=554, height=18)

    def choose_save_folder(self):
        folder = filedialog.askdirectory(title="저장할 폴더 선택")
        if folder:
            self.save_folder.set(folder)
            self.status_value.set("저장 폴더가 선택되었습니다.")

    def require_save_folder(self):
        folder = clean_text(self.save_folder.get())
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("저장 폴더 선택", "저장 폴더를 먼저 선택하세요.")
            return None
        return folder

    def set_busy(self, button, text):
        button.config(text=text, state="disabled")
        self.status_label.configure(fg=TEXT_DARK)
        self.root.update_idletasks()

    def set_ready(self):
        self.balsong_button.config(text="실행", state="normal")
        self.unshipped_button.config(text="실행", state="normal")
        self.root.update_idletasks()

    def run_balsong_summary(self):
        folder = self.require_save_folder()
        if not folder:
            return

        csv_path = filedialog.askopenfilename(
            title="발송 CSV 파일 선택",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not csv_path:
            return

        _, date_code, _ = parse_date_from_filename(csv_path)
        output_name = f"{date_code}-발송통계.png"
        output_path = unique_file_path(folder, output_name)

        try:
            self.set_busy(self.balsong_button, "정리")
            self.status_value.set("발송 통계를 만드는 중입니다...")
            create_balsong_image(csv_path, output_path)
            self.status_label.configure(fg=ACCENT_BLUE)
            self.status_value.set(f"저장 완료: {os.path.basename(output_path)}")
        except Exception as e:
            self.status_label.configure(fg="#dc2626")
            self.status_value.set(f"오류: {e}")
        finally:
            self.set_ready()

    def run_unshipped_summary(self):
        password = clean_text(self.password_value.get())
        if not password:
            messagebox.showinfo("엑셀 암호 입력", "엑셀 암호를 입력하세요.")
            self.password_entry.focus_set()
            return

        folder = self.require_save_folder()
        if not folder:
            return

        excel_path = filedialog.askopenfilename(
            title="미발송 엑셀 파일 선택",
            filetypes=[
                ("엑셀 파일", "*.xls *.xlsx *.xlsm"),
                ("모든 파일", "*.*"),
            ],
        )
        if not excel_path:
            return

        _, date_code, _ = parse_date_from_filename(excel_path)
        output_path_1 = unique_file_path(folder, f"{date_code}-미발송통계 (1).png")
        output_path_2 = unique_file_path(folder, f"{date_code}-미발송통계 (2).png")
        try:
            self.set_busy(self.unshipped_button, "정리")
            self.status_value.set("미발송 통계 2장을 만드는 중입니다...")
            create_unshipped_images(excel_path, password, output_path_1, output_path_2)
            self.status_label.configure(fg=ACCENT_ORANGE)
            self.status_value.set(
                f"저장 완료: {os.path.basename(output_path_1)}, {os.path.basename(output_path_2)}"
            )
        except Exception as e:
            self.status_label.configure(fg="#dc2626")
            self.status_value.set(f"오류: {e}")
        finally:
            self.set_ready()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ClosingReportApp()
    app.run()
