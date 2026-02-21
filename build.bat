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
    --collect-all customtkinter ^
    --collect-all matplotlib ^
    --collect-all pkg_resources ^
    app.py

echo.
echo Copying data files to dist/FF14MarketApp...
copy "items_cache_tw.json" "dist\FF14MarketApp\"
copy "recipes_cache.json" "dist\FF14MarketApp\"
copy "meta_items.json" "dist\FF14MarketApp\"
copy "market_app.db" "dist\FF14MarketApp\"
copy "使用說明.txt" "dist\FF14MarketApp\"
copy "README.md" "dist\FF14MarketApp\"
copy "update_items_cache.py" "dist\FF14MarketApp\"

echo.
echo.
echo ========================================================
echo Build Complete!
echo You can find the executable folder in 'dist/FF14MarketApp'.
echo ========================================================

