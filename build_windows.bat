@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python tidak ditemukan di PATH.
    echo Install Python 3.12 dari python.org, centang "Add python.exe to PATH", lalu coba lagi.
    exit /b 1
)

echo [1/3] Memasang dependensi build...
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo Gagal memasang dependensi.
    exit /b 1
)

echo [2/3] Membangun aplikasi...
python -m PyInstaller aplikasi.spec --noconfirm
if errorlevel 1 (
    echo Gagal membangun aplikasi.
    exit /b 1
)

echo [3/3] Menguji hasil build...
start "" /wait dist\aplikasi\aplikasi.exe --selftest selftest_report.txt
if errorlevel 1 (
    echo Selftest GAGAL. Isi laporan:
    type selftest_report.txt
    exit /b 1
)

echo.
echo Selesai. Hasil ada di folder dist\aplikasi
echo Bagikan SELURUH isi folder tersebut, bukan hanya file .exe-nya.
exit /b 0
