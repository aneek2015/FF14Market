@echo off
@chcp 65001 >nul
setlocal

REM Get current date and time for folder name
set "YYYY=%date:~0,4%"
set "MM=%date:~5,2%"
set "DD=%date:~8,2%"
set "HH=%time:~0,2%"
set "Min=%time:~3,2%"
set "Sec=%time:~6,2%"

REM Replace space with 0 in hour if necessary
if "%HH:~0,1%" == " " set "HH=0%HH:~1,1%"

set "BACKUP_DIR=backup\%YYYY%%MM%%DD%_%HH%%Min%%Sec%"

echo Creating backup at: %BACKUP_DIR%
mkdir "%BACKUP_DIR%"

echo Copying files...
copy app.py "%BACKUP_DIR%\"
copy market_api.py "%BACKUP_DIR%\"
copy database.py "%BACKUP_DIR%\"
copy crafting_service.py "%BACKUP_DIR%\"
copy recipe_provider.py "%BACKUP_DIR%\"
copy items_cache_tw.json "%BACKUP_DIR%\"
copy recipes_cache.json "%BACKUP_DIR%\"
copy meta_items.json "%BACKUP_DIR%\"
copy market_app.db "%BACKUP_DIR%\"
copy build.bat "%BACKUP_DIR%\"
copy backup.bat "%BACKUP_DIR%\"
copy README.md "%BACKUP_DIR%\"
copy 使用說明.txt "%BACKUP_DIR%\"

echo.
echo Backup completed successfully!
pause
