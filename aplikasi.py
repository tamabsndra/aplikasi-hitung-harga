import csv
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

import fitz
import numpy as np
from PIL import Image

from pdf_splitter import split_pdf_by_colors

# Artivity design tokens, taken from the landing DESIGN.md palette.
BG = "#F8FAFC"
WHITE = "#FFFFFF"
BORDER = "#E2E8F0"
INK = "#0F172A"
INK_SOFT = "#334155"
INK_MUTED = "#64748B"
BLUE = "#0C82E8"
BLUE_TINT = "#F0F7FE"
ROSE = "#E11D62"
ROSE_HOVER = "#BE1255"

# Neither Poppins nor Avenir Next ships with Windows, so each family list ends in
# fonts that exist on every platform Tk supports.
HEADING_FAMILIES = ("Poppins", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans")
BODY_FAMILIES = ("Avenir Next", "Nunito", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans")

WHITE_LEVEL = 250
CHROMA_LEVEL = 12


def format_number(value):
    return f"{value:,}".replace(",", ".")


def resolve_family(candidates, available):
    for family in candidates:
        if family in available:
            return family
    return candidates[-1]


def default_output_dir():
    # A frozen build lives under Program Files, which normal users cannot write to.
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    return documents if os.path.isdir(documents) else os.path.expanduser("~")


def enable_hidpi():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def run_selftest(report_path=None):
    import platform

    lines = []
    state = {"ok": True}

    def record(name, passed, detail=""):
        state["ok"] = state["ok"] and passed
        suffix = f" -> {detail}" if detail else ""
        lines.append(f"{'PASS' if passed else 'FAIL'} {name}{suffix}")

    record("platform", True, f"{platform.platform()} / Python {platform.python_version()}")

    for module_name in ("fitz", "numpy", "PIL", "tkinter"):
        try:
            __import__(module_name)
            record(f"import {module_name}", True)
        except Exception as exc:
            record(f"import {module_name}", False, str(exc))

    try:
        probe = tk.Tk()
        probe.withdraw()
        available = set(tkfont.families())
        probe.destroy()
        record("heading font resolved", True, resolve_family(HEADING_FAMILIES, available))
        record("body font resolved", True, resolve_family(BODY_FAMILIES, available))
    except Exception as exc:
        lines.append(f"SKIP font probe -> {exc}")

    try:
        out_dir = default_output_dir()
        record("output dir exists", os.path.isdir(out_dir), out_dir)
        probe_file = os.path.join(out_dir, ".aplikasi_write_test")
        with open(probe_file, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe_file)
        record("output dir writable", True, out_dir)
    except Exception as exc:
        record("output dir writable", False, str(exc))

    try:
        doc = fitz.open()
        page = doc.new_page()
        page.draw_rect(fitz.Rect(72, 72, 400, 400), fill=(0.1, 0.5, 0.9))
        result = analyse_page(doc.load_page(0), 1)
        doc.close()
        record("analyse colored page", result["color_area"] > 0, result)
        record("price above color floor", result["price"] >= 500, result["price"])
    except Exception as exc:
        record("pdf analysis", False, str(exc))

    record("bw floor", pricePrediction(0, 0) == 300, pricePrediction(0, 0))
    record("color floor", pricePrediction(0.5, 0.5) == 500, pricePrediction(0.5, 0.5))

    text = "\n".join(lines)
    print(text)
    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            print(f"could not write report: {exc}")
    return 0 if state["ok"] else 1


def image_preprocess(img):
    w, h = img.size
    img = img.rotate(90, expand=True) if w > h else img
    return img.resize((2480, 3508))


def measure_areas(img):
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    highest = arr.max(axis=2)
    lowest = arr.min(axis=2)

    # Pixels within CHROMA_LEVEL of neutral count as grayscale; anything lighter
    # than WHITE_LEVEL is paper, not ink. Mirrors the web API classifier so both
    # produce the same areas for the same PDF.
    is_color = (highest - lowest) > CHROMA_LEVEL
    is_ink = highest < WHITE_LEVEL

    total = arr.shape[0] * arr.shape[1]
    color_area = round(np.count_nonzero(is_color) / total * 100, 2)
    bw_area = round(np.count_nonzero(is_ink & ~is_color) / total * 100, 2)
    return color_area, bw_area


def lin_reg(x1, x2):
    return 191.3642 + (x1 * 19.59733806) + (x2 * 7.05360083)


def pricePrediction(color_area, print_area):
    prediction = lin_reg(color_area, print_area)
    if prediction < 300 and color_area == 0:
        prediction = 300
    if prediction < 500 and color_area != 0:
        prediction = 500
    return round(prediction)


def analyse_page(page, page_number):
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img = image_preprocess(image)
    color_area, bw_area = measure_areas(img)
    print_area = round(color_area + bw_area, 2)
    return {
        "page": page_number,
        "color_area": color_area,
        "bw_area": bw_area,
        "print_area": print_area,
        "price": pricePrediction(color_area, print_area),
    }


class PriceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Penghitung Harga Cetak")
        self.root.configure(bg=BG)
        self.root.geometry("940x720")
        self.root.minsize(820, 620)

        self.analysis_queue = queue.Queue()
        self.split_queue = queue.Queue()
        self.results = []
        self.total_price = 0
        self.total_pages = 0
        self.busy = False

        self.pdf_path = tk.StringVar()
        self.split_input = tk.StringVar()
        self.split_output = tk.StringVar()
        self.split_output.set(default_output_dir())
        self.status_var = tk.StringVar(value="Pilih file PDF untuk mulai.")
        self.split_status_var = tk.StringVar(value="Pilih file PDF dan folder tujuan.")

        self.configure_styles()
        self.build_layout()
        self.clear_results()

    def configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        available = set(tkfont.families())
        heading = resolve_family(HEADING_FAMILIES, available)
        body = resolve_family(BODY_FAMILIES, available)
        title_font = (heading, 20, "bold")
        field_font = (heading, 11, "bold")
        body_font = (body, 11)
        caption_font = (body, 10)
        value_font = (heading, 18, "bold")
        button_font = (heading, 11, "bold")
        small_button_font = (heading, 10, "bold")
        self.body_font = body_font

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE, relief="solid", borderwidth=1)
        style.configure("TLabel", background=BG, foreground=INK_SOFT, font=body_font)
        style.configure("Title.TLabel", background=BG, foreground=INK, font=title_font)
        style.configure("Sub.TLabel", background=BG, foreground=INK_MUTED, font=caption_font)
        style.configure("Field.TLabel", background=BG, foreground=INK_SOFT, font=field_font)
        style.configure("CardCaption.TLabel", background=WHITE, foreground=INK_MUTED, font=caption_font)
        style.configure("CardValue.TLabel", background=WHITE, foreground=INK, font=value_font)
        style.configure("Status.TLabel", background=BG, foreground=INK_MUTED, font=caption_font)
        style.configure("Error.TLabel", background=BG, foreground="#DC2626", font=caption_font)

        style.configure("Accent.TButton", background=ROSE, foreground=WHITE,
                        font=button_font, padding=(18, 10), borderwidth=0)
        style.map("Accent.TButton",
                  background=[("active", ROSE_HOVER), ("disabled", "#F3B3CC")],
                  foreground=[("disabled", WHITE)])
        style.configure("Secondary.TButton", background=WHITE, foreground=BLUE,
                        font=small_button_font, padding=(14, 9), borderwidth=1, relief="solid")
        style.map("Secondary.TButton",
                  background=[("active", BLUE_TINT), ("disabled", "#EEF2F7")],
                  foreground=[("disabled", INK_MUTED)])

        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure("TNotebook.Tab", background="#E8EDF3", foreground=INK_SOFT,
                        font=small_button_font, padding=(18, 9), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", WHITE)],
                  foreground=[("selected", BLUE)])

        style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor=BORDER,
                        borderwidth=0, thickness=8)

        style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK_SOFT,
                        font=body_font, rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background="#F1F5F9", foreground=INK,
                        font=small_button_font, relief="flat", padding=(8, 8))
        style.map("Treeview.Heading", background=[("active", "#E8EDF3")])
        style.map("Treeview", background=[("selected", "#D8EBFD")], foreground=[("selected", INK)])

    def build_layout(self):
        outer = ttk.Frame(self.root, padding=(20, 16, 20, 16))
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Penghitung Harga Cetak", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(outer, text="Perkiraan biaya cetak dari persentase tinta per halaman.",
                  style="Sub.TLabel").pack(anchor=tk.W, pady=(2, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_price = ttk.Frame(notebook, padding=(0, 14, 0, 0))
        self.tab_split = ttk.Frame(notebook, padding=(0, 14, 0, 0))
        notebook.add(self.tab_price, text="Hitung Harga")
        notebook.add(self.tab_split, text="Split PDF")

        self.build_price_tab()
        self.build_split_tab()

    def build_price_tab(self):
        tab = self.tab_price

        file_row = ttk.Frame(tab)
        file_row.pack(fill=tk.X)
        ttk.Label(file_row, text="File PDF", style="Field.TLabel").pack(anchor=tk.W)
        picker = ttk.Frame(file_row)
        picker.pack(fill=tk.X, pady=(4, 0))
        ttk.Entry(picker, textvariable=self.pdf_path, state="readonly",
                  font=self.body_font).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(picker, text="Pilih PDF", style="Secondary.TButton",
                   command=self.select_pdf).pack(side=tk.LEFT, padx=(8, 0))

        progress_row = ttk.Frame(tab)
        progress_row.pack(fill=tk.X, pady=(12, 0))
        self.progress = ttk.Progressbar(progress_row, mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X)
        self.status_label = ttk.Label(progress_row, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(anchor=tk.W, pady=(6, 0))

        cards = ttk.Frame(tab)
        cards.pack(fill=tk.X, pady=(14, 0))
        self.card_values = {}
        card_defs = (("total", "Total Harga"), ("pages", "Halaman"),
                     ("color", "Halaman Warna"), ("bw", "Halaman B&W"))
        for index, (key, caption) in enumerate(card_defs):
            pad = (0, 10) if index < len(card_defs) - 1 else 0
            card = ttk.Frame(cards, style="Card.TFrame", padding=(14, 12))
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=pad)
            ttk.Label(card, text=caption, style="CardCaption.TLabel").pack(anchor=tk.W)
            value = ttk.Label(card, text="0", style="CardValue.TLabel")
            value.pack(anchor=tk.W, pady=(4, 0))
            self.card_values[key] = value

        tree_wrap = ttk.Frame(tab)
        tree_wrap.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        columns = ("page", "kind", "color", "bw", "print", "price")
        headings = {"page": "Hal", "kind": "Jenis", "color": "Warna %",
                    "bw": "B&W %", "print": "Cetak %", "price": "Harga"}
        widths = {"page": 55, "kind": 80, "color": 95, "bw": 95, "print": 95, "price": 120}
        self.tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=8)
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], stretch=(col == "price"),
                             anchor=tk.CENTER if col == "page" else tk.E)
        self.tree.column("kind", anchor=tk.W)

        scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Row tint encodes page type, so a long table can be scanned by colour.
        self.tree.tag_configure("color", background=BLUE_TINT)
        self.tree.tag_configure("bw", background=WHITE)

        self.empty_label = ttk.Label(
            tree_wrap, style="Status.TLabel", justify=tk.CENTER, anchor=tk.CENTER,
            text="Belum ada hasil.\nPilih file PDF lalu klik Hitung Harga.")
        self.empty_label.place(relx=0.5, rely=0.4, anchor=tk.CENTER)

        actions = ttk.Frame(tab)
        actions.pack(fill=tk.X, pady=(14, 0))
        self.calc_button = ttk.Button(actions, text="Hitung Harga", style="Accent.TButton",
                                      command=self.start_analysis)
        self.calc_button.pack(side=tk.LEFT)
        self.save_button = ttk.Button(actions, text="Simpan CSV", style="Secondary.TButton",
                                      command=self.save_csv, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))
        self.clear_button = ttk.Button(actions, text="Bersihkan", style="Secondary.TButton",
                                       command=self.clear_results, state=tk.DISABLED)
        self.clear_button.pack(side=tk.LEFT, padx=(8, 0))

    def build_split_tab(self):
        tab = self.tab_split

        ttk.Label(tab, text="Pisahkan halaman berwarna dan hitam-putih ke dua file PDF.",
                  style="Sub.TLabel").pack(anchor=tk.W)

        in_row = ttk.Frame(tab)
        in_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(in_row, text="File PDF", style="Field.TLabel").pack(anchor=tk.W)
        in_picker = ttk.Frame(in_row)
        in_picker.pack(fill=tk.X, pady=(4, 0))
        ttk.Entry(in_picker, textvariable=self.split_input, state="readonly",
                  font=self.body_font).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(in_picker, text="Pilih PDF", style="Secondary.TButton",
                   command=self.select_split_input).pack(side=tk.LEFT, padx=(8, 0))

        out_row = ttk.Frame(tab)
        out_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(out_row, text="Folder Tujuan", style="Field.TLabel").pack(anchor=tk.W)
        out_picker = ttk.Frame(out_row)
        out_picker.pack(fill=tk.X, pady=(4, 0))
        ttk.Entry(out_picker, textvariable=self.split_output, state="readonly",
                  font=self.body_font).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(out_picker, text="Pilih Folder", style="Secondary.TButton",
                   command=self.select_split_output).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(tab, textvariable=self.split_status_var,
                  style="Status.TLabel").pack(anchor=tk.W, pady=(12, 0))

        self.split_button = ttk.Button(tab, text="Split PDF", style="Accent.TButton",
                                       command=self.start_split)
        self.split_button.pack(anchor=tk.W, pady=(10, 0))

        log_wrap = ttk.Frame(tab)
        log_wrap.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.split_log = tk.Text(log_wrap, height=10, wrap=tk.WORD, font=self.body_font, bg=WHITE,
                                 fg=INK_SOFT, relief="solid", borderwidth=1,
                                 highlightthickness=1, highlightbackground=BORDER)
        log_scroll = ttk.Scrollbar(log_wrap, orient=tk.VERTICAL, command=self.split_log.yview)
        self.split_log.configure(yscrollcommand=log_scroll.set, state=tk.DISABLED)
        self.split_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def select_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path.set(path)
            self.status_var.set("File siap dihitung.")

    def select_split_input(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.split_input.set(path)
            self.split_output.set(os.path.dirname(path))

    def select_split_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.split_output.set(folder)

    def set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.calc_button.configure(state=state)
        self.split_button.configure(state=state)
        self.save_button.configure(state=state if self.results else tk.DISABLED)
        self.clear_button.configure(state=state if self.results else tk.DISABLED)

    def start_analysis(self):
        path = self.pdf_path.get()
        if not path:
            messagebox.showwarning("Belum ada file", "Pilih file PDF terlebih dahulu.")
            return
        if not os.path.exists(path):
            messagebox.showerror("File tidak ditemukan", "File PDF yang dipilih tidak ada.")
            return
        if self.busy:
            return

        self.clear_results()
        self.set_busy(True)
        self.status_label.configure(style="Status.TLabel")
        self.status_var.set("Membuka PDF...")
        threading.Thread(target=self.analysis_worker, args=(path,), daemon=True).start()
        self.root.after(80, self.poll_analysis)

    def analysis_worker(self, path):
        try:
            doc = fitz.open(path)
            total = len(doc)
            if total == 0:
                doc.close()
                self.analysis_queue.put(("error", "PDF tidak memiliki halaman."))
                return
            self.analysis_queue.put(("total", total))
            total_price = 0
            color_pages = 0
            for index in range(total):
                result = analyse_page(doc.load_page(index), index + 1)
                if result["color_area"] > 0:
                    color_pages += 1
                total_price += result["price"]
                self.analysis_queue.put(("page", result))
            doc.close()
            self.analysis_queue.put(("done", {"total_price": total_price, "pages": total,
                                              "color_pages": color_pages}))
        except Exception as exc:
            self.analysis_queue.put(("error", str(exc)))

    def poll_analysis(self):
        try:
            while True:
                kind, payload = self.analysis_queue.get_nowait()
                if kind == "total":
                    self.total_pages = payload
                    self.progress.configure(maximum=payload, value=0)
                    self.status_var.set(f"Memproses 0/{payload} halaman...")
                elif kind == "page":
                    self.add_result_row(payload)
                    self.progress.configure(value=payload["page"])
                    self.status_var.set(f"Memproses {payload['page']}/{self.total_pages} halaman...")
                elif kind == "done":
                    self.finish_analysis(payload)
                    return
                elif kind == "error":
                    self.fail_analysis(payload)
                    return
        except queue.Empty:
            pass
        self.root.after(80, self.poll_analysis)

    def finish_analysis(self, summary):
        self.total_price = summary["total_price"]
        bw_pages = summary["pages"] - summary["color_pages"]
        self.card_values["total"].configure(text="Rp " + format_number(summary["total_price"]))
        self.card_values["pages"].configure(text=str(summary["pages"]))
        self.card_values["color"].configure(text=str(summary["color_pages"]))
        self.card_values["bw"].configure(text=str(bw_pages))
        self.status_var.set(f"Selesai. {summary['pages']} halaman diproses.")
        self.set_busy(False)

    def fail_analysis(self, message):
        self.status_label.configure(style="Error.TLabel")
        self.status_var.set(f"Gagal memproses PDF: {message}")
        self.set_busy(False)
        messagebox.showerror("Gagal", f"Tidak dapat memproses PDF.\n\n{message}")

    def add_result_row(self, result):
        is_color_page = result["color_area"] > 0
        kind = "Warna" if is_color_page else "B&W"
        self.tree.insert("", tk.END, values=(
            result["page"], kind,
            f"{result['color_area']:.2f}", f"{result['bw_area']:.2f}",
            f"{result['print_area']:.2f}", format_number(result["price"]),
        ), tags=("color" if is_color_page else "bw",))
        self.results.append(result)
        self.empty_label.place_forget()
        self.tree.yview_moveto(1.0)
        self.save_button.configure(state=tk.NORMAL)
        self.clear_button.configure(state=tk.NORMAL)

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        self.total_price = 0
        self.total_pages = 0
        for key in ("total", "pages", "color", "bw"):
            self.card_values[key].configure(text="0")
        self.progress.configure(value=0)
        self.status_label.configure(style="Status.TLabel")
        self.status_var.set("Pilih file PDF untuk mulai.")
        self.empty_label.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
        self.save_button.configure(state=tk.DISABLED)
        self.clear_button.configure(state=tk.DISABLED)

    def save_csv(self):
        if not self.results:
            messagebox.showinfo("Belum ada data", "Hitung harga terlebih dahulu.")
            return
        base = os.path.splitext(os.path.basename(self.pdf_path.get()))[0] or "hasil"
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{base}_harga.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["halaman", "jenis", "color_area", "bw_area", "print_area", "harga"])
                for row in self.results:
                    writer.writerow([
                        row["page"], "warna" if row["color_area"] > 0 else "bw",
                        f"{row['color_area']:.2f}", f"{row['bw_area']:.2f}",
                        f"{row['print_area']:.2f}", row["price"],
                    ])
                writer.writerow([])
                writer.writerow(["total", "", "", "", "", self.total_price])
            self.status_var.set(f"CSV disimpan: {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("Gagal menyimpan", str(exc))

    def start_split(self):
        input_path = self.split_input.get()
        output_dir = self.split_output.get()
        if not input_path or not os.path.exists(input_path):
            messagebox.showwarning("Belum ada file", "Pilih file PDF yang valid terlebih dahulu.")
            return
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("Folder tujuan", "Pilih folder tujuan yang valid.")
            return
        if self.busy:
            return

        self.set_busy(True)
        self.split_status_var.set("Memproses...")
        self.clear_split_log()
        threading.Thread(target=self.split_worker, args=(input_path, output_dir), daemon=True).start()
        self.root.after(80, self.poll_split)

    def split_worker(self, input_path, output_dir):
        try:
            base = os.path.splitext(os.path.basename(input_path))[0]
            colored_path = os.path.join(output_dir, f"{base}_colored.pdf")
            bw_path = os.path.join(output_dir, f"{base}_bw.pdf")
            colored_pages, bw_pages = split_pdf_by_colors(input_path, colored_path, bw_path)
            self.split_queue.put(("split_done", {"colored": colored_pages, "bw": bw_pages,
                                                 "colored_path": colored_path, "bw_path": bw_path}))
        except Exception as exc:
            self.split_queue.put(("split_error", str(exc)))

    def poll_split(self):
        try:
            while True:
                kind, payload = self.split_queue.get_nowait()
                if kind == "split_done":
                    self.finish_split(payload)
                    return
                if kind == "split_error":
                    self.fail_split(payload)
                    return
        except queue.Empty:
            pass
        self.root.after(80, self.poll_split)

    def finish_split(self, summary):
        self.log_split(f"Halaman berwarna   : {len(summary['colored'])} -> {summary['colored']}")
        self.log_split(f"Halaman hitam-putih: {len(summary['bw'])} -> {summary['bw']}")
        for label, path in (("Warna", summary["colored_path"]), ("Hitam-putih", summary["bw_path"])):
            if os.path.exists(path):
                self.log_split(f"Tersimpan ({label}): {path}")
            else:
                self.log_split(f"Tidak ada halaman {label.lower()}, file tidak dibuat.")
        self.split_status_var.set("Selesai.")
        self.set_busy(False)
        messagebox.showinfo("Selesai", "PDF berhasil dipisahkan.")

    def fail_split(self, message):
        self.log_split(f"Gagal: {message}")
        self.split_status_var.set("Gagal memisahkan PDF.")
        self.set_busy(False)
        messagebox.showerror("Gagal", message)

    def log_split(self, message):
        self.split_log.configure(state=tk.NORMAL)
        self.split_log.insert(tk.END, message + "\n")
        self.split_log.see(tk.END)
        self.split_log.configure(state=tk.DISABLED)

    def clear_split_log(self):
        self.split_log.configure(state=tk.NORMAL)
        self.split_log.delete("1.0", tk.END)
        self.split_log.configure(state=tk.DISABLED)


def main():
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        report = sys.argv[index + 1] if len(sys.argv) > index + 1 else "selftest_report.txt"
        raise SystemExit(run_selftest(report))

    enable_hidpi()
    root = tk.Tk()
    PriceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
