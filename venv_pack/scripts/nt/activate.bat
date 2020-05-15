@echo off

rem This code copies and modifies the script found at
rem `venv/scripts/nt/activate.bat` in CPython. This file is subject to the
rem license at
rem
rem    https://docs.python.org/3/license.html
rem
rem and is under copyright by the Python Software Foundation
rem
rem    Copyright 2001-2018 Python Software Foundation; All Rights Reserved
rem
rem The full license text can be found at `venv_pack/scripts/CPYTHON_LICENSE.txt

rem This file is UTF-8 encoded, so we need to update the current code page while executing it
for /f "tokens=2 delims=:." %%a in ('"%SystemRoot%\System32\chcp.com"') do (
    set _OLD_CODEPAGE=%%a
)
if defined _OLD_CODEPAGE (
    "%SystemRoot%\System32\chcp.com" 65001 > nul
)

for %%i in ("%~dp0..") do set "VIRTUAL_ENV=%%~fi"
for %%i in ("%VIRTUAL_ENV%") do set "PROMPT_NAME=%%~nxi"

for %%i in ("%~dp0.") do set "BIN_PATH=%%~fi"
for %%i in ("%BIN_PATH%") do set "BIN_NAME=%%~nxi"


if not defined PROMPT set PROMPT=$P$G

if defined _OLD_VIRTUAL_PROMPT set PROMPT=%_OLD_VIRTUAL_PROMPT%
if defined _OLD_VIRTUAL_PYTHONHOME set PYTHONHOME=%_OLD_VIRTUAL_PYTHONHOME%

set _OLD_VIRTUAL_PROMPT=%PROMPT%
set PROMPT=(%PROMPT_NAME%) %PROMPT%

if defined PYTHONHOME set _OLD_VIRTUAL_PYTHONHOME=%PYTHONHOME%
set PYTHONHOME=

if defined _OLD_VIRTUAL_PATH set PATH=%_OLD_VIRTUAL_PATH%
if not defined _OLD_VIRTUAL_PATH set _OLD_VIRTUAL_PATH=%PATH%

set PATH=%VIRTUAL_ENV%\%BIN_NAME%;%PATH%

:END
if defined _OLD_CODEPAGE (
    "%SystemRoot%\System32\chcp.com" %_OLD_CODEPAGE% > nul
    set _OLD_CODEPAGE=
)
