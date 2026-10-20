# PDF Price Calculator and Splitter

## Setup Instructions

clone dulu

terus pastiin udah punya semua lib yang dipake

abis tu coba dirun dulu ada error ga

kalo udah bisa running, jalanin script dibawah di terminal

```
pyinstaller --onedir --noconsole --icon print.ico aplikasi.py
```

## Required Libraries

Install the required libraries using pip:

```
pip install PyMuPDF Pillow numpy
```

## Features

1. **Price Calculator**: Calculates the printing price of a PDF based on color content
2. **PDF Splitter**: Splits a PDF into two separate files:
   - One containing only colored pages
   - One containing only black & white pages
   - Maintains original page order in both output files

## How to Use

1. Run the main application:
   ```
   python3 aplikasi.py
   ```

2. To calculate printing price:
   - Click "Pilih PDF" to select a PDF file
   - Click "Hitung Harga" to calculate the price

3. To split a PDF by colors:
   - Click "Split PDF by Colors" to open the splitter tool
   - Select the input PDF file
   - Choose an output directory
   - Click "Split PDF" to process

The splitter will create two files:
- `[filename]_colored.pdf`: Contains all colored pages
- `[filename]_bw.pdf`: Contains all black & white pages

## Install untuk end user (Windows)

1. Unduh `Aplikasi-Setup.exe` dari artifact Actions terakhir atau dari halaman Releases.
2. Klik dua kali, ikuti langkah wizard (install ke `Program Files`, butuh izin admin sekali).
3. Buka dari Start Menu atau ikon desktop. Untuk menghapus, pakai "Uninstall Aplikasi Hitung Harga" di Control Panel.

Installer belum ditandatangani, jadi Windows SmartScreen bisa muncul saat pertama dijalankan. Pilih "More info" lalu "Run anyway".

## Build untuk Windows

PyInstaller tidak bisa cross-compile. File .exe Windows harus dibangun di mesin Windows.

### Cara 1: otomatis lewat GitHub Actions

Setiap push ke `main` atau `test` akan membangun .exe di runner Windows dan mengunggahnya sebagai artifact `aplikasi-windows`. Buka tab Actions di GitHub, pilih run terakhir, lalu unduh artifact-nya.

Untuk membuat release: buat tag lalu publish release di GitHub. File `aplikasi-windows.zip` akan otomatis terlampir ke release tersebut.

### Cara 2: build manual di mesin Windows

Syarat: Python 3.12 dari python.org, centang "Add python.exe to PATH".

Jalankan `build_windows.bat` (klik dua kali, atau dari Command Prompt). Script akan memasang dependensi, membangun aplikasi, dan menjalankan selftest.

Hasilnya ada di folder `dist\aplikasi`. Bagikan SELURUH isi folder itu, bukan hanya file .exe-nya, karena Python dan library dibundel di subfolder `_internal`.

### Verifikasi hasil build

```
dist\aplikasi\aplikasi.exe --selftest selftest_report.txt
```

Perintah itu memeriksa library, font, folder output, dan analisis PDF. Keluar dengan kode 0 kalau semua lolos, dan menulis laporan ke `selftest_report.txt`.

## Catatan font

Aplikasi memakai Poppins untuk judul dan Avenir Next untuk teks. Kalau font itu tidak terpasang (misalnya di Windows), aplikasi otomatis memakai Segoe UI, lalu Arial, lalu DejaVu Sans.
