@echo off
cd /d "%~dp0"
start "Clinic Server" cmd /k ".\env\Scripts\python.exe manage.py runserver"
