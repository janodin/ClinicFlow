@echo off
cd /d "D:\Desktop\Clinic Managment & Appointment"
start "Clinic Server" cmd /k ".\env\Scripts\activate && python manage.py runserver"
