@echo off
rem Abre o FinTerminal no navegador. Feche esta janela para encerrar o app.
cd /d "%~dp0"
py -3.11 -m streamlit run streamlit_app.py
pause
