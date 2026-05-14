@echo off
title Iniciando Sistema de Gestao
:: Navega para a pasta onde o arquivo está (mesmo que seja em rede ou caminho longo)
cd /d "%~dp0"

echo Aguarde, iniciando o servidor Streamlit...
:: Tenta rodar o streamlit diretamente, se falhar, tenta via módulo python
python -m streamlit run app.py

pause