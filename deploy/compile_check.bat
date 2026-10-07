@echo off
cd /d "C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy"
"C:\Users\MY PC\Documents\Default Project\Five mark v1\venv\Scripts\python.exe" -m py_compile src/paper/journal.py
echo compile:%errorlevel%