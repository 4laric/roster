@echo off
cd /d "%~dp0"
python RosterLauncher.py
if errorlevel 1 pause
