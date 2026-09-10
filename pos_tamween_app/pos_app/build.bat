@echo off
chcp 65001 >nul
echo ================================================
echo   Building Tamween POS - please wait
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Please install Python from python.org and make sure to check
    echo the "Add Python to PATH" option during setup, then run this again.
    pause
    exit /b 1
)

echo [1/3] Installing required libraries...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo [2/3] Building the exe file, this may take a minute...
python -m PyInstaller --noconfirm --onefile --windowed --name pos_tamween --add-data "schema.sql;." --add-data "theme.qss;." main.py
python -m PyInstaller --noconfirm --onefile --name pos_tamween_debug --add-data "schema.sql;." --add-data "theme.qss;." main.py

echo.
echo [3/3] Done! Look inside the "dist" folder for pos_tamween.exe
echo A second file pos_tamween_debug.exe was also created - use it only if
echo something goes wrong, since it shows error messages in a black window.
echo Copy pos_tamween.exe to any computer in the shop and run it directly.
echo.
pause
