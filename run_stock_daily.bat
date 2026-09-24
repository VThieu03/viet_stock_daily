@echo off
title VietStock Daily AI Assistant
cd /d "%~dp0"
echo ========================================================
echo   DANG KICH HOAT BOT PHAN TICH CHUNG KHOAN VIET NAM...
echo ========================================================
python vietstock_gemini_bot.py
echo.
echo ========================================================
echo   HOAN TAT! KIEM TRA TELEGRAM TREN DIEN THOAI CUA BAN!
echo ========================================================
timeout /t 5
