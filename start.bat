@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 Web 管理界面（浏览器会自动打开 http://127.0.0.1:5001）...
".venv\Scripts\python.exe" app.py
pause
