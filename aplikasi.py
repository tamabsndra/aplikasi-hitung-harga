import tkinter as tk
from tkinter import filedialog, messagebox
import fitz
from PIL import Image
import numpy as np

def lin_reg(x1, x2):
    return 191.3642 + (x1 * 19.59733806) + (x2 * 7.05360083)

def pricePrediction(color_area, print_area):
    prediction = lin_reg(color_area, print_area)
    if prediction < 300 and color_area == 0 :
        prediction = 300
    if prediction < 500 and color_area != 0 :
        prediction = 500
    return (round(prediction))

def image_preprocess(img):
    w, h = img.size
    img = img.rotate(90, expand=True) if w > h else img
    resized_image = img.resize((2480, 3508))
    return resized_image

def is_color(img):
    img_array = np.array(img)
    if np.array_equal(img_array[..., 0], img_array[..., 1]) and np.array_equal(img_array[..., 1], img_array[..., 2]):
        return False
    return True

def countColorArea(img):
    img_array = np.array(img)
    color_pixels = np.any(img_array[:, :, :3] != img_array[:, :, :3].mean(axis=2, keepdims=True), axis=2)
    color_area = np.sum(color_pixels)
    total_pixels = img_array.shape[0] * img_array.shape[1]
    return round((color_area / total_pixels) * 100, 2)

def priceCounter(img):
    color_area = countColorArea(img)
    return pricePrediction(True, color_area)

def process_page(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    if not is_color(image):
        return 300

    img = image_preprocess(image)
    return priceCounter(img)

def calculate_price(pdf_path):
    try:
        pdf = fitz.open(pdf_path)
        harga_total = sum(process_page(pdf[i]) for i in range(len(pdf)))
        return harga_total
    except Exception as e:
        messagebox.showerror("Error", f"Terjadi kesalahan: {e}")
        return None

def select_pdf():
    file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)

def on_calculate_clicked():
    pdf_path = entry.get()
    if pdf_path:
        harga_total = calculate_price(pdf_path)
        if harga_total is not None:
            messagebox.showinfo("Hasil", f"Total harga: {harga_total}")
    else:
        messagebox.showwarning("Peringatan", "Silakan pilih file PDF terlebih dahulu.")

root = tk.Tk()
root.title("Aplikasi Penghitung Harga PDF")

frame = tk.Frame(root, padx=10, pady=10)
frame.pack(padx=10, pady=10)

entry = tk.Entry(frame, width=50)
entry.pack(side=tk.LEFT, padx=(0, 10))

browse_button = tk.Button(frame, text="Pilih PDF", command=select_pdf)
browse_button.pack(side=tk.LEFT)

calculate_button = tk.Button(root, text="Hitung Harga", command=on_calculate_clicked)
calculate_button.pack(pady=(5, 5))

root.mainloop()
