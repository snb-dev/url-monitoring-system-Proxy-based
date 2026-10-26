@echo off
:: Run this if web pages stopped loading after URL Monitor was closed or crashed.
:: It puts your previous proxy settings back.
call "%~dp0start.bat" restore
