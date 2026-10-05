@echo off
rem LivePresenceAI - chamado pelo Instalar-LivePresenceAI.exe depois de extrair os arquivos.
rem O extrator do IExpress e 32 bits: "Sysnative" garante o PowerShell de 64 bits (Program Files correto).
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "PS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0instalador.ps1"
