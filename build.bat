@echo off
@chcp 65001 >nul
echo ========================================================
echo Installing PyInstaller and building FF14 Market App...
echo ========================================================

REM Install PyInstaller if not present
pip install pyinstaller

REM Clean previous builds
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"
if exist "FF14MarketApp.spec" del "FF14MarketApp.spec"

REM Run PyInstaller for Main App
echo.
echo Building Application (Folder Mode)...
pyinstaller --noconfirm --onedir --windowed --clean ^
    --name "FF14MarketApp" ^
    --add-data "items_cache_tw.json;." ^
    --add-data "recipes_cache.json;." ^
    --add-data "使用說明.txt;." ^
    --add-data "README.md;." ^
    --collect-all customtkinter ^
    app.py

echo.
echo.
echo ========================================================
echo Build Complete!
echo You can find the executable folder in 'dist/FF14MarketApp'.
echo ========================================================

REM --- Compression Step ---
echo.
echo Attempting to compress to .7z...

set "SEVENZIP_PATH="

REM Check common paths
if exist "C:\Program Files\7-Zip\7z.exe" set "SEVENZIP_PATH=C:\Program Files\7-Zip\7z.exe"
if exist "C:\Program Files (x86)\7-Zip\7z.exe" set "SEVENZIP_PATH=C:\Program Files (x86)\7-Zip\7z.exe"

REM Check PATH (fallback)
if not defined SEVENZIP_PATH (
    where 7z >nul 2>nul
    if %errorlevel% equ 0 set "SEVENZIP_PATH=7z"
)

if defined SEVENZIP_PATH (
    echo Found 7-Zip at: "%SEVENZIP_PATH%"
    if exist "dist\FF14MarketApp.7z" del "dist\FF14MarketApp.7z"
    "%SEVENZIP_PATH%" a -t7z "dist\FF14MarketApp.7z" "dist\FF14MarketApp"
    echo.
    echo Compression Successful: dist\FF14MarketApp.7z
) else (
    echo [WARNING] 7-Zip not found. Skipping compression.
    echo Please install 7-Zip or add it to your PATH.
)

echo ========================================================
pause
