import csv
import os
import re
import shutil
import tempfile
from datetime import datetime
from tkinter import Tk, Button, filedialog

from PIL import Image, ImageDraw, ImageFont


APP_TITLE = "발송 정리"

SPECIAL_TOP_CATEGORY = "누스&리퍼브"

# 표 색상
HEADER_FILL = "#d9e2f3"
FOOTER_FILL = "#d9e2f3"
CATEGORY_FILL = "#fce4d6"
WHITE_FILL = "#ffffff"
GRID_COLOR = "#111111"
TEXT_COLOR = "#111111"

# 프로그램 UI 색상
WINDOW_BG = "#efefef"
BUTTON_BG = "#e5e5e5"

# 네가 보낸 이미지 기준 표 크기
ROW_H = 22
LEFT_W = 121
RIGHT_W = 122
TABLE_W = 244

FONT_SIZE = 14


def load_font(size=14, bold=False):
    """
    Windows 기준 맑은 고딕 사용.
    exe로 만들었을 때도 Windows에서는 Malgun Gothic으로 표시됨.
    """
    if bold:
        candidates = [
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\malgunbd.ttf",
        ]

    candidates += [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


FONT_HEADER = load_font(FONT_SIZE, bold=True)
FONT_NORMAL = load_font(FONT_SIZE, bold=False)
FONT_BOLD = load_font(FONT_SIZE, bold=True)


def parse_int(value):
    if value is None:
        return 0

    text = str(value).strip()
    text = text.replace(",", "")
    text = text.replace("건", "")
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.strip()

    if not text:
        return 0

    try:
        return int(float(text))
    except ValueError:
        return 0


def product_number(product_name):
    """
    n5285 -> 5285
    n083 -> 83
    n86037 -> 86037
    """
    text = str(product_name).strip().lower()

    match = re.search(r"n\s*0*(\d+)", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))

    return 10**15


def read_csv_flexible(csv_path):
    """
    CSV 인코딩 자동 시도.
    국내 쇼핑몰 CSV는 cp949/euc-kr인 경우가 많음.
    """
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

    raise RuntimeError(f"CSV 파일을 읽지 못했습니다.\n{last_error}")


def find_column(columns, target_name):
    normalized_target = target_name.replace(" ", "").strip()

    for col in columns:
        normalized_col = str(col).replace(" ", "").strip()
        if normalized_col == normalized_target:
            return col

    return None


def parse_date_label_from_filename(csv_path):
    """
    파일명에 20260527 같은 날짜가 있으면 '5월 27일'로 표시.
    없으면 오늘 날짜 사용.
    """
    name = os.path.basename(csv_path)
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", name)

    if match:
        month = int(match.group(2))
        day = int(match.group(3))
        date_code = f"{match.group(1)}{match.group(2)}{match.group(3)}"
        return f"{month}월 {day}일", date_code

    now = datetime.now()
    return f"{now.month}월 {now.day}일", now.strftime("%Y%m%d")


def build_summary(csv_path):
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
        raise RuntimeError(
            "필수 컬럼을 찾지 못했습니다.\n\n"
            f"필요한 컬럼: {', '.join(missing)}"
        )

    summary = {}

    for row in rows:
        category = str(row.get(category_col, "")).strip()
        product = str(row.get(product_col, "")).strip()
        quantity = parse_int(row.get(quantity_col, 0))

        if not category or not product:
            continue

        if quantity == 0:
            continue

        if category not in summary:
            summary[category] = {
                "total": 0,
                "products": {}
            }

        summary[category]["total"] += quantity
        summary[category]["products"][product] = (
            summary[category]["products"].get(product, 0) + quantity
        )

    if not summary:
        raise RuntimeError("집계할 데이터가 없습니다.")

    sorted_categories = []

    # 누스&리퍼브는 무조건 맨 위
    if SPECIAL_TOP_CATEGORY in summary:
        sorted_categories.append((SPECIAL_TOP_CATEGORY, summary[SPECIAL_TOP_CATEGORY]))

    # 나머지 분류는 합계 많은 순
    others = [
        (category, data)
        for category, data in summary.items()
        if category != SPECIAL_TOP_CATEGORY
    ]
    others.sort(key=lambda item: (-item[1]["total"], item[0]))

    sorted_categories.extend(others)

    result = []
    grand_total = 0

    for category, data in sorted_categories:
        grand_total += data["total"]

        products = list(data["products"].items())

        # 상품은 발송수량 많은 순, 같으면 n 뒤 숫자 작은 순
        products.sort(key=lambda item: (-item[1], product_number(item[0]), item[0]))

        result.append({
            "category": category,
            "total": data["total"],
            "products": products
        })

    return result, grand_total


def text_bbox(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)


def draw_text_exact_center(draw, box, text, font, fill=TEXT_COLOR):
    """
    PIL 글씨 bbox 기준으로 위/아래 여백을 최대한 같게 중앙정렬.
    """
    x, y, w, h = box
    text = str(text)

    bbox = text_bbox(draw, text, font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = x + (w - tw) / 2 - bbox[0]
    ty = y + (h - th) / 2 - bbox[1]

    draw.text((tx, ty), text, font=font, fill=fill)


def draw_text_left_center(draw, box, text, font, padding=6, fill=TEXT_COLOR):
    """
    왼쪽 정렬 + 세로 중앙정렬.
    현재 표에서는 주로 사용하지 않지만 여분으로 둠.
    """
    x, y, w, h = box
    text = str(text)

    bbox = text_bbox(draw, text, font)
    th = bbox[3] - bbox[1]

    tx = x + padding
    ty = y + (h - th) / 2 - bbox[1]

    draw.text((tx, ty), text, font=font, fill=fill)


def draw_count_right(draw, x, y, width, height, quantity, bold_number=False):
    """
    오른쪽 수량 칸.
    숫자는 오른쪽 정렬.
    숫자와 (건)을 한 줄로 표시.
    """
    qty_text = str(quantity)
    unit_text = " (건)"

    qty_font = FONT_BOLD if bold_number else FONT_NORMAL
    unit_font = FONT_NORMAL

    qty_bbox = text_bbox(draw, qty_text, qty_font)
    unit_bbox = text_bbox(draw, unit_text, unit_font)

    qty_w = qty_bbox[2] - qty_bbox[0]
    unit_w = unit_bbox[2] - unit_bbox[0]

    total_w = qty_w + unit_w

    start_x = x + width - total_w - 6

    # 숫자와 단위를 각각 bbox 기준으로 세로 중앙정렬
    qty_h = qty_bbox[3] - qty_bbox[1]
    unit_h = unit_bbox[3] - unit_bbox[1]

    qty_y = y + (height - qty_h) / 2 - qty_bbox[1]
    unit_y = y + (height - unit_h) / 2 - unit_bbox[1]

    draw.text((start_x - qty_bbox[0], qty_y), qty_text, font=qty_font, fill=TEXT_COLOR)
    draw.text(
        (start_x + qty_w - unit_bbox[0], unit_y),
        unit_text,
        font=unit_font,
        fill=TEXT_COLOR
    )


def fill_row(draw, row_index, left_fill, right_fill=None):
    if right_fill is None:
        right_fill = left_fill

    y = row_index * ROW_H

    draw.rectangle(
        [0, y, LEFT_W - 1, y + ROW_H - 1],
        fill=left_fill
    )
    draw.rectangle(
        [LEFT_W + 1, y, TABLE_W - 1, y + ROW_H - 1],
        fill=right_fill
    )


def draw_grid(draw, total_rows):
    """
    네가 보낸 이미지처럼 얇은 검정 선.
    """
    height = total_rows * ROW_H + 1

    # 세로선
    draw.line([0, 0, 0, height - 1], fill=GRID_COLOR, width=1)
    draw.line([LEFT_W, 0, LEFT_W, height - 1], fill=GRID_COLOR, width=1)
    draw.line([TABLE_W - 1, 0, TABLE_W - 1, height - 1], fill=GRID_COLOR, width=1)

    # 가로선
    for i in range(total_rows + 1):
        y = i * ROW_H
        draw.line([0, y, TABLE_W - 1, y], fill=GRID_COLOR, width=1)


def create_summary_image(csv_path):
    summary, grand_total = build_summary(csv_path)
    date_label, date_code = parse_date_label_from_filename(csv_path)

    data_rows = []

    # header
    data_rows.append(("header", date_label, "합계 : 발송수량"))

    for group in summary:
        data_rows.append(("category", group["category"], group["total"]))

        for product, quantity in group["products"]:
            data_rows.append(("product", product, quantity))

    data_rows.append(("footer", "총합계", grand_total))

    total_rows = len(data_rows)
    height = total_rows * ROW_H + 1

    image = Image.new("RGB", (TABLE_W, height), WHITE_FILL)
    draw = ImageDraw.Draw(image)

    for row_index, row in enumerate(data_rows):
        row_type = row[0]
        y = row_index * ROW_H

        if row_type == "header":
            _, left_text, right_text = row
            fill_row(draw, row_index, HEADER_FILL)

            draw_text_exact_center(
                draw,
                (0, y, LEFT_W, ROW_H),
                left_text,
                FONT_HEADER
            )
            draw_text_exact_center(
                draw,
                (LEFT_W + 1, y, RIGHT_W, ROW_H),
                right_text,
                FONT_HEADER
            )

        elif row_type == "category":
            _, category, quantity = row
            fill_row(draw, row_index, CATEGORY_FILL)

            # 누스 / 누스&리퍼브 가운데 정렬
            draw_text_exact_center(
                draw,
                (0, y, LEFT_W, ROW_H),
                category,
                FONT_BOLD
            )
            draw_count_right(
                draw,
                LEFT_W + 1,
                y,
                RIGHT_W,
                ROW_H,
                quantity,
                bold_number=True
            )

        elif row_type == "product":
            _, product, quantity = row
            fill_row(draw, row_index, WHITE_FILL)

            draw_text_exact_center(
                draw,
                (0, y, LEFT_W, ROW_H),
                product,
                FONT_NORMAL
            )
            draw_count_right(
                draw,
                LEFT_W + 1,
                y,
                RIGHT_W,
                ROW_H,
                quantity,
                bold_number=False
            )

        elif row_type == "footer":
            _, label, quantity = row
            fill_row(draw, row_index, FOOTER_FILL)

            draw_text_exact_center(
                draw,
                (0, y, LEFT_W, ROW_H),
                label,
                FONT_BOLD
            )
            draw_count_right(
                draw,
                LEFT_W + 1,
                y,
                RIGHT_W,
                ROW_H,
                quantity,
                bold_number=True
            )

    draw_grid(draw, total_rows)

    output_name = f"발송정리_{date_code}.png"
    temp_path = os.path.join(tempfile.gettempdir(), output_name)

    image.save(temp_path, "PNG")

    return temp_path, output_name


def unique_file_path(folder, filename):
    base, ext = os.path.splitext(filename)
    path = os.path.join(folder, filename)

    if not os.path.exists(path):
        return path

    index = 1

    while True:
        new_name = f"{base}_{index}{ext}"
        new_path = os.path.join(folder, new_name)

        if not os.path.exists(new_path):
            return new_path

        index += 1


class BalsongApp:
    def __init__(self):
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("360x220")
        self.root.resizable(False, False)
        self.root.configure(bg=WINDOW_BG)

        # Tk 기본 폰트도 맑은 고딕 계열로 지정
        self.root.option_add("*Font", "Malgun Gothic 14")

        self.ready_to_download = False
        self.generated_image_path = None
        self.generated_filename = None

        self.button = Button(
            self.root,
            text="발송 정리",
            font=("Malgun Gothic", 24, "bold"),
            bg=BUTTON_BG,
            activebackground="#d6d6d6",
            relief="solid",
            bd=1,
            command=self.on_button_click
        )

        self.button.place(x=40, y=45, width=280, height=120)

    def on_button_click(self):
        if self.ready_to_download:
            self.download_image()
        else:
            self.analyze_csv()

    def analyze_csv(self):
        csv_path = filedialog.askopenfilename(
            title="CSV 파일 선택",
            filetypes=[
                ("CSV 파일", "*.csv"),
                ("모든 파일", "*.*")
            ]
        )

        if not csv_path:
            return

        try:
            self.button.config(text="정리 중...")
            self.root.update_idletasks()

            image_path, filename = create_summary_image(csv_path)

            self.generated_image_path = image_path
            self.generated_filename = filename
            self.ready_to_download = True

            # 팝업 없이 버튼 이름만 다운로드로 변경
            self.button.config(text="다운로드")

        except Exception:
            # 팝업 없이 버튼에만 오류 표시 후 원래대로 복구
            self.reset_state()
            self.button.config(text="오류\n다시 시도")
            self.root.after(1800, self.reset_state)

    def download_image(self):
        if not self.generated_image_path or not os.path.exists(self.generated_image_path):
            self.reset_state()
            return

        folder = filedialog.askdirectory(title="이미지를 저장할 폴더 선택")

        if not folder:
            return

        try:
            save_path = unique_file_path(folder, self.generated_filename)
            shutil.copy2(self.generated_image_path, save_path)

            # 저장 후 팝업 없이 바로 초기 상태로 복귀
            self.reset_state()

        except Exception:
            self.reset_state()
            self.button.config(text="저장 오류")
            self.root.after(1800, self.reset_state)

    def reset_state(self):
        self.ready_to_download = False
        self.generated_image_path = None
        self.generated_filename = None
        self.button.config(text="발송 정리")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BalsongApp()
    app.run()
