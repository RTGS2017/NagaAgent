@echo off
chcp 65001

call .venv\Scripts\activate.bat
cd frontend
npm run dev
