@echo off
title DataScope - Analytics Job Radar
echo.
echo  ================================================
echo   DataScope v2 - Analytics Job Radar
echo   Real jobs from Greenhouse, Lever, Ashby + more
echo  ================================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found on your computer.
    echo.
    echo  Please install Python from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During install, check the box:
    echo  "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo  Python found. Installing dependencies...
pip install flask requests beautifulsoup4 lxml python-dateutil --quiet

echo  Starting DataScope...
echo.
echo  --------------------------------------------------
echo  Open your browser and go to: http://localhost:5000
echo  Then click the green "Scan Live Jobs" button
echo  --------------------------------------------------
echo.
python app.py
pause
