import csv
import os
import re
import shutil
import tempfile
from datetime import datetime
from tkinter import Tk, Button, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont


APP_TITLE = "발송 정리"

SPECIAL_TOP_CATEGORY = "누스&리퍼브"

HEADER_FILL = "#d9e2f3"
FOOTER_FILL = "#d9e2f3"
CATEGORY_FILL = "#fce4d6"
WHITE_FILL = "#ffffff"
GRID_COLOR = "#111111"
TEXT_COLOR = "#111111"

WINDOW_BG = "#efefef"
BUTTON_BG = "#e5e5e5"


def load_font(size=15, bold=False):
    """
    Windows 기준 맑은 고딕 사용.
    GitHub Actions Windows 빌드에서도 정상 동작.
    """
    candidates = []

    if bold:
        candidates += [
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
        ]
    else:
        candidates += [
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


FONT_HEADER = load_font(15, bold=True)
FONT_NORMAL = load_font(15, bold=False)
FONT_BOLD = load_font(15, bold=True)


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


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

    숫자가 없으면 맨 뒤로 보냄.
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
    한국 쇼핑몰/관리자 CSV는 cp949인 경우가 많아서
    여러 인코딩을 순서대로 시도.
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
    """
    공백 차이를 어느 정도 허용해서 컬럼 찾기.
    """
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
        return f"{month}월 {day}일", f"{match.group(1)}{match.group(2)}{match.group(3)}"

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

    if SPECIAL_TOP_CATEGORY in summary:
        sorted_categories.append((SPECIAL_TOP_CATEGORY, summary[SPECIAL_TOP_CATEGORY]))

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
        products.sort(key=lambda item: (-item[1], product_number(item[0]), item[0]))

        result.append({
            "category": category,
            "total": data["total"],
            "products": products
        })

    return result, grand_total


def draw_count(draw, x, y, width, height, quantity, bold_number=False):
    qty_text = str(quantity)
    unit_text = " (건)"

    qty_font = FONT_BOLD if bold_number else FONT_NORMAL
    unit_font = FONT_NORMAL

    qty_w, qty_h = text_size(draw, qty_text, qty_font)
    unit_w, unit_h = text_size(draw, unit_text, unit_font)

    total_w = qty_w + unit_w
    start_x = x + width - total_w - 8

    base_y = y + (height - max(qty_h, unit_h)) // 2 - 1

    draw.text((start_x, base_y), qty_text, font=qty_font, fill=TEXT_COLOR)
    draw.text((start_x + qty_w, base_y), unit_text, font=unit_font, fill=TEXT_COLOR)


def draw_center_text(draw, box, text, font):
    x, y, w, h = box
    tw, th = text_size(draw, text, font)
    draw.text(
        (x + (w - tw) // 2, y + (h - th) // 2 - 1),
        text,
        font=font,
        fill=TEXT_COLOR
    )


def draw_left_text(draw, box, text, font, left_padding=8):
    x, y, w, h = box
    tw, th = text_size(draw, text, font)
    draw.text(
        (x + left_padding, y + (h - th) // 2 - 1),
        text,
        font=font,
        fill=TEXT_COLOR
    )


def draw_expand_icon(draw, x, y):
    size = 10
    draw.rectangle(
        [x, y, x + size, y + size],
        fill="#ffffff",
        outline="#888888",
        width=1
    )

    draw.line(
        [x + 2, y + size // 2, x + size - 2, y + size // 2],
        fill="#666666",
        width=1
    )


def create_summary_image(csv_path):
    summary, grand_total = build_summary(csv_path)
    date_label, date_code = parse_date_label_from_filename(csv_path)

    temp_draw_image = Image.new("RGB", (10, 10), "white")
    temp_draw = ImageDraw.Draw(temp_draw_image)

    header_h = 28
    row_h = 25

    rows_for_size = []

    for group in summary:
        rows_for_size.append(("category", group["category"], group["total"]))

        for product, quantity in group["products"]:
            rows_for_size.append(("product", product, quantity))

    rows_for_size.append(("footer", "총합계", grand_total))

    left_w = 140
    right_w = 120

    for row_type, label, quantity in rows_for_size:
        font = FONT_BOLD if row_type in ("category", "footer") else FONT_NORMAL

        if row_type == "category":
            tw, _ = text_size(temp_draw, label, font)
            left_w = max(left_w, tw + 36)
        else:
            tw, _ = text_size(temp_draw, label, font)
            left_w = max(left_w, tw + 28)

        count_text = f"{quantity} (건)"
        cw, _ = text_size(temp_draw, count_text, FONT_BOLD)
        right_w = max(right_w, cw + 24)

    title_w, _ = text_size(temp_draw, "합계 : 발송수량", FONT_HEADER)
    right_w = max(right_w, title_w + 20)

    width = left_w + right_w
    height = header_h + (len(rows_for_size) * row_h)

    image = Image.new("RGB", (width, height), WHITE_FILL)
    draw = ImageDraw.Draw(image)

    y = 0

    # Header
    draw.rectangle([0, y, left_w, y + header_h], fill=HEADER_FILL, outline=GRID_COLOR)
    draw.rectangle([left_w, y, width, y + header_h], fill=HEADER_FILL, outline=GRID_COLOR)

    draw_center_text(draw, (0, y, left_w, header_h), date_label, FONT_HEADER)
    draw_center_text(draw, (left_w, y, right_w, header_h), "합계 : 발송수량", FONT_HEADER)

    y += header_h

    for group in summary:
        # Category row
        draw.rectangle([0, y, left_w, y + row_h], fill=CATEGORY_FILL, outline=GRID_COLOR)
        draw.rectangle([left_w, y, width, y + row_h], fill=CATEGORY_FILL, outline=GRID_COLOR)

        icon_y = y + (row_h - 10) // 2
        draw_expand_icon(draw, 5, icon_y)
        draw_left_text(draw, (0, y, left_w, row_h), group["category"], FONT_BOLD, left_padding=22)
        draw_count(draw, left_w, y, right_w, row_h, group["total"], bold_number=True)

        y += row_h

        # Product rows
        for product, quantity in group["products"]:
            draw.rectangle([0, y, left_w, y + row_h], fill=WHITE_FILL, outline=GRID_COLOR)
            draw.rectangle([left_w, y, width, y + row_h], fill=WHITE_FILL, outline=GRID_COLOR)

            draw_center_text(draw, (0, y, left_w, row_h), product, FONT_NORMAL)
            draw_count(draw, left_w, y, right_w, row_h, quantity, bold_number=False)

            y += row_h

    # Footer row
    draw.rectangle([0, y, left_w, y + row_h], fill=FOOTER_FILL, outline=GRID_COLOR)
    draw.rectangle([left_w, y, width, y + row_h], fill=FOOTER_FILL, outline=GRID_COLOR)

    draw_center_text(draw, (0, y, left_w, row_h), "총합계", FONT_BOLD)
    draw_count(draw, left_w, y, right_w, row_h, grand_total, bold_number=True)

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
            image_path, filename = create_summary_image(csv_path)

            self.generated_image_path = image_path
            self.generated_filename = filename
            self.ready_to_download = True

            self.button.config(text="다운로드")
            messagebox.showinfo(
                "완료",
                "이미지 파일 생성이 완료되었습니다.\n\n다운로드 버튼을 눌러 저장할 폴더를 선택하세요."
            )

        except Exception as e:
            messagebox.showerror("오류", str(e))
            self.reset_state()

    def download_image(self):
        if not self.generated_image_path or not os.path.exists(self.generated_image_path):
            messagebox.showerror("오류", "다운로드할 이미지 파일이 없습니다.")
            self.reset_state()
            return

        folder = filedialog.askdirectory(title="이미지를 저장할 폴더 선택")

        if not folder:
            return

        try:
            save_path = unique_file_path(folder, self.generated_filename)
            shutil.copy2(self.generated_image_path, save_path)

            messagebox.showinfo(
                "저장 완료",
                f"이미지 파일을 저장했습니다.\n\n{save_path}"
            )

            self.reset_state()

        except Exception as e:
            messagebox.showerror("오류", str(e))

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