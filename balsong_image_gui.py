import csv
import os
import re
import shutil
import tempfile
from datetime import datetime
from tkinter import Tk, Button, Entry, Label, filedialog, messagebox, StringVar
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageFont


APP_TITLE = "통계 정리"

SPECIAL_TOP_CATEGORY = "누스&리퍼브"

# 결과 이미지 색상
# 나중에 RGB 값을 알게 되면 이 부분만 바꾸면 됩니다.
HEADER_FILL = "#d9e2f3"
FOOTER_FILL = "#d9e2f3"
CATEGORY_FILL = "#fce4d6"
WHITE_FILL = "#ffffff"
GRID_COLOR = "#111111"
TEXT_COLOR = "#111111"

# 프로그램 UI 색상
WINDOW_BG = "#ffffff"
BUTTON_BG = "#e5e5e5"
BUTTON_ACTIVE_BG = "#d6d6d6"
ENTRY_BG = "#ffffff"
BORDER_COLOR = "#cccccc"

# 발송 통계 이미지 표 크기
ROW_H = 22
LEFT_W = 121
RIGHT_W = 122
TABLE_W = LEFT_W + 1 + RIGHT_W
FONT_SIZE = 14

# 프로그램 창 크기
WINDOW_W = 640
WINDOW_H = 270


def load_font(size=14, bold=False):
    """
    결과 이미지에 사용할 폰트.
    Windows에서는 맑은 고딕을 우선 사용합니다.
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
    n5285  -> 5285
    n083   -> 83
    n86037 -> 86037

    숫자가 없으면 뒤로 보냅니다.
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
    국내 쇼핑몰/관리자 CSV는 cp949, euc-kr인 경우가 많아서 같이 시도합니다.
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
    공백 차이는 무시하고 컬럼명을 찾습니다.
    예: '상품 분류명'도 '상품분류명'처럼 인식 가능.
    """
    normalized_target = target_name.replace(" ", "").strip()

    for col in columns:
        normalized_col = str(col).replace(" ", "").strip()
        if normalized_col == normalized_target:
            return col

    return None


def parse_date_info_from_filename(file_path):
    """
    파일명에 20260528 같은 날짜가 있으면:
    - 이미지 상단 표시: 5월 28일
    - 저장 파일명 코드: 260528

    날짜가 없으면 오늘 날짜를 사용합니다.
    """
    name = os.path.basename(file_path)
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", name)

    if match:
        year_full = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        date_label = f"{month}월 {day}일"
        date_code = f"{str(year_full)[2:]}{month:02d}{day:02d}"
        return date_label, date_code

    now = datetime.now()
    return f"{now.month}월 {now.day}일", now.strftime("%y%m%d")


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

    # 누스&리퍼브는 수량과 관계없이 맨 위 고정
    if SPECIAL_TOP_CATEGORY in summary:
        sorted_categories.append((SPECIAL_TOP_CATEGORY, summary[SPECIAL_TOP_CATEGORY]))

    # 나머지 상품분류는 발송수량 합계 많은 순
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

        # 상품명은 발송수량 많은 순,
        # 수량이 같으면 n 뒤 숫자 작은 순
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
    PIL의 textbbox 기준으로 가로/세로 중앙정렬.
    """
    x, y, w, h = box
    text = str(text)

    bbox = text_bbox(draw, text, font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = x + (w - tw) / 2 - bbox[0]
    ty = y + (h - th) / 2 - bbox[1]

    draw.text((tx, ty), text, font=font, fill=fill)


def draw_count_right(draw, x, y, width, height, quantity, bold_number=False):
    """
    오른쪽 수량 칸.
    숫자 + ' (건)'을 오른쪽 정렬로 표시합니다.
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


def fill_row(draw, row_index, fill):
    """
    행 배경만 채웁니다.
    선은 마지막에 draw_grid에서 한 번에 그립니다.
    """
    y = row_index * ROW_H

    draw.rectangle(
        [0, y, LEFT_W - 1, y + ROW_H - 1],
        fill=fill
    )

    draw.rectangle(
        [LEFT_W + 1, y, TABLE_W - 1, y + ROW_H - 1],
        fill=fill
    )


def draw_grid(draw, total_rows):
    """
    표 테두리와 칸 선을 1px로 그립니다.
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


def create_balsong_summary_image(csv_path):
    """
    발송 CSV를 분석해서 임시 PNG 파일을 만들고,
    저장 파일명은 YYMMDD-발송통계.png 형태로 반환합니다.
    """
    summary, grand_total = build_summary(csv_path)
    date_label, date_code = parse_date_info_from_filename(csv_path)

    data_rows = []

    # 상단 제목 행
    data_rows.append(("header", date_label, "합계 : 발송수량"))

    # 상품분류 + 상품 행
    for group in summary:
        data_rows.append(("category", group["category"], group["total"]))

        for product, quantity in group["products"]:
            data_rows.append(("product", product, quantity))

    # 총합계 행
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

    output_name = f"{date_code}-발송통계.png"
    temp_path = os.path.join(tempfile.gettempdir(), output_name)

    image.save(temp_path, "PNG")

    return temp_path, output_name


def unique_file_path(folder, filename):
    """
    같은 이름이 이미 있으면 파일명 뒤에 (1), (2)를 붙입니다.
    예: 260528-발송통계.png -> 260528-발송통계 (1).png
    """
    base, ext = os.path.splitext(filename)
    path = os.path.join(folder, filename)

    if not os.path.exists(path):
        return path

    index = 1

    while True:
        new_name = f"{base} ({index}){ext}"
        new_path = os.path.join(folder, new_name)

        if not os.path.exists(new_path):
            return new_path

        index += 1


def get_unsent_output_names(excel_path):
    """
    미발송 통계 저장 파일명 규칙.
    실제 이미지 생성 로직은 추후 추가 예정입니다.
    """
    _, date_code = parse_date_info_from_filename(excel_path)
    return (
        f"{date_code}-미발송통계 (1).png",
        f"{date_code}-미발송통계 (2).png",
    )


def decrypt_excel_to_temp_if_needed(excel_path, password):
    """
    추후 미발송 엑셀 분석에 사용할 암호 해제용 준비 함수입니다.

    현재는 미발송 분석 로직을 아직 연결하지 않았지만,
    암호가 있는 Excel 파일을 열어야 할 때 아래 흐름으로 사용할 수 있습니다.

    사용하려면 requirements.txt에 아래 패키지를 추가해야 합니다.
    msoffcrypto-tool>=5.4.0

    반환값:
    - 암호가 없거나 복호화가 필요 없으면 원본 경로
    - 암호를 입력했고 복호화에 성공하면 임시 xlsx/xls 경로
    """
    if not password:
        return excel_path

    try:
        import msoffcrypto
    except Exception:
        # 아직 미발송 분석 기능을 연결하기 전이라 빌드 실패를 막기 위해 원본 경로를 반환합니다.
        return excel_path

    temp_ext = os.path.splitext(excel_path)[1] or ".xlsx"
    temp_path = os.path.join(tempfile.gettempdir(), f"decrypted_excel_{datetime.now().strftime('%Y%m%d_%H%M%S')}{temp_ext}")

    with open(excel_path, "rb") as src:
        office_file = msoffcrypto.OfficeFile(src)
        office_file.load_key(password=password)

        with open(temp_path, "wb") as dst:
            office_file.decrypt(dst)

    return temp_path


class StatisticsApp:
    def __init__(self):
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.resizable(False, False)
        self.root.configure(bg=WINDOW_BG)

        # Tkinter UI 폰트.
        # tkfont.Font를 사용해 'Malgun Gothic' 띄어쓰기 오류를 방지합니다.
        self.ui_font = tkfont.Font(family="Malgun Gothic", size=11)
        self.small_font = tkfont.Font(family="Malgun Gothic", size=10)
        self.button_font = tkfont.Font(family="Malgun Gothic", size=22, weight="bold")

        self.save_folder_var = StringVar(value="")
        self.excel_password_var = StringVar(value="")

        self.build_ui()
        self.center_window(WINDOW_W, WINDOW_H)

    def center_window(self, width, height):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = int((screen_w - width) / 2)
        y = int((screen_h - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        self.balsong_button = Button(
            self.root,
            text="발송 통계",
            font=self.button_font,
            bg=BUTTON_BG,
            activebackground=BUTTON_ACTIVE_BG,
            relief="solid",
            bd=1,
            command=self.run_balsong_statistics
        )
        self.balsong_button.place(x=40, y=35, width=260, height=95)

        self.unsent_button = Button(
            self.root,
            text="미발송 통계",
            font=self.button_font,
            bg=BUTTON_BG,
            activebackground=BUTTON_ACTIVE_BG,
            relief="solid",
            bd=1,
            command=self.run_unsent_statistics_placeholder
        )
        self.unsent_button.place(x=340, y=35, width=260, height=95)

        self.folder_button = Button(
            self.root,
            text="저장 폴더 선택",
            font=self.ui_font,
            bg=BUTTON_BG,
            activebackground=BUTTON_ACTIVE_BG,
            relief="solid",
            bd=1,
            command=self.choose_save_folder
        )
        self.folder_button.place(x=40, y=155, width=130, height=34)

        self.folder_entry = Entry(
            self.root,
            textvariable=self.save_folder_var,
            font=self.small_font,
            bg=ENTRY_BG,
            relief="solid",
            bd=1,
            state="readonly",
            readonlybackground=ENTRY_BG
        )
        self.folder_entry.place(x=180, y=155, width=280, height=34)

        self.password_label = Label(
            self.root,
            text="엑셀 암호",
            font=self.ui_font,
            bg=WINDOW_BG,
            anchor="w"
        )
        self.password_label.place(x=475, y=137, width=120, height=22)

        self.password_entry = Entry(
            self.root,
            textvariable=self.excel_password_var,
            font=self.ui_font,
            bg=ENTRY_BG,
            relief="solid",
            bd=1,
            show="*"
        )
        self.password_entry.place(x=475, y=155, width=125, height=34)

    def choose_save_folder(self):
        folder = filedialog.askdirectory(title="저장할 폴더 선택")
        if not folder:
            return

        self.save_folder_var.set(folder)

    def get_save_folder_or_warn(self):
        folder = self.save_folder_var.get().strip()

        if not folder:
            messagebox.showwarning("저장 폴더 선택", "먼저 저장 폴더를 선택해 주세요.")
            return None

        if not os.path.isdir(folder):
            messagebox.showwarning("저장 폴더 확인", "선택한 저장 폴더를 찾을 수 없습니다.\n다시 선택해 주세요.")
            self.save_folder_var.set("")
            return None

        return folder

    def flash_button_text(self, button, text, reset_text, delay=1400):
        button.config(text=text)
        self.root.after(delay, lambda: button.config(text=reset_text))

    def run_balsong_statistics(self):
        save_folder = self.get_save_folder_or_warn()
        if not save_folder:
            return

        csv_path = filedialog.askopenfilename(
            title="발송 CSV 파일 선택",
            filetypes=[
                ("CSV 파일", "*.csv"),
                ("모든 파일", "*.*")
            ]
        )

        if not csv_path:
            return

        try:
            self.balsong_button.config(text="정리 중...")
            self.root.update_idletasks()

            temp_image_path, output_name = create_balsong_summary_image(csv_path)
            save_path = unique_file_path(save_folder, output_name)
            shutil.copy2(temp_image_path, save_path)

            self.flash_button_text(self.balsong_button, "저장 완료", "발송 통계")

        except Exception:
            self.flash_button_text(self.balsong_button, "오류", "발송 통계", delay=1600)

    def run_unsent_statistics_placeholder(self):
        """
        미발송 통계는 UI와 파일명 규칙, 암호 입력 연결 자리만 먼저 만든 상태입니다.
        실제 엑셀 분석 후 이미지 2장 생성 로직은 추후 추가합니다.
        """
        save_folder = self.get_save_folder_or_warn()
        if not save_folder:
            return

        excel_path = filedialog.askopenfilename(
            title="미발송 엑셀 파일 선택",
            filetypes=[
                ("Excel 파일", "*.xls *.xlsx"),
                ("모든 파일", "*.*")
            ]
        )

        if not excel_path:
            return

        try:
            self.unsent_button.config(text="준비 중...")
            self.root.update_idletasks()

            password = self.excel_password_var.get()

            # 추후 실제 분석 함수에서 이 경로를 사용하면 됩니다.
            # 암호가 있고 msoffcrypto-tool이 설치되어 있으면 임시 복호화 파일 경로를 반환합니다.
            prepared_excel_path = decrypt_excel_to_temp_if_needed(excel_path, password)
            _ = prepared_excel_path

            # 추후 생성할 파일명 규칙입니다.
            output_name_1, output_name_2 = get_unsent_output_names(excel_path)
            _ = os.path.join(save_folder, output_name_1)
            _ = os.path.join(save_folder, output_name_2)

            self.flash_button_text(self.unsent_button, "기능 준비중", "미발송 통계", delay=1600)

        except Exception:
            self.flash_button_text(self.unsent_button, "오류", "미발송 통계", delay=1600)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = StatisticsApp()
    app.run()
