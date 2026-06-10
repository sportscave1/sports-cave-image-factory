@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting Sports Cave Image Factory...
echo.
echo Open this on this PC: http://localhost:8501
echo To use it from another device on the same network, open:
echo http://THIS-COMPUTER-IP:8501
echo.
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
pause
