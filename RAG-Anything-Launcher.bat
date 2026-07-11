@echo off
setlocal enabledelayedexpansion

title RAG-Anything Launcher

where wsl.exe >nul 2>nul
if errorlevel 1 (
    echo WSL is required for this launcher because this project is installed in Linux.
    echo Install or enable WSL, then try again.
    echo.
    pause
    exit /b 1
)

:menu
cls
echo ==========================================
echo RAG-Anything Launcher
echo Project: %~dp0
echo WSL will open in this project folder.
echo ==========================================
echo.
echo 1. Open interactive starter menu
echo 2. Run full readiness check
echo 3. Start persistent MinerU API
echo 4. Show MinerU API status
echo 5. Stop persistent MinerU API
echo 6. Large PDF wizard
echo 7. Batch folder wizard
echo 8. Show all commands and options
echo 9. Exit
echo.
set /p "choice=Choose an option [1-9]: "

if "%choice%"=="1" goto interactive
if "%choice%"=="2" goto doctor
if "%choice%"=="3" goto api_start
if "%choice%"=="4" goto api_status
if "%choice%"=="5" goto api_stop
if "%choice%"=="6" goto large_pdf
if "%choice%"=="7" goto batch
if "%choice%"=="8" goto help_all
if "%choice%"=="9" goto done

echo.
echo Unknown choice.
pause
goto menu

:interactive
call :run_wsl ".venv/bin/python start.py"
goto menu

:help_all
call :run_wsl ".venv/bin/python start.py --help"
goto menu

:doctor
call :run_wsl ".venv/bin/python start.py doctor"
goto menu

:api_start
call :run_wsl ".venv/bin/python start.py mineru-api start"
goto menu

:api_status
call :run_wsl ".venv/bin/python start.py mineru-api status"
goto menu

:api_stop
call :run_wsl ".venv/bin/python start.py mineru-api stop"
goto menu

:large_pdf
echo.
echo Enter paths as WSL/Linux paths, for example:
echo /mnt/d/Codex/my-file.pdf
echo.
set /p "pdf_path=PDF path: "
set /p "out_dir=Output folder [./large_pdf_output]: "
if "%out_dir%"=="" set "out_dir=./large_pdf_output"
set /p "page_window=Pages per MinerU run [300]: "
if "%page_window%"=="" set "page_window=300"
set /p "min_window=Smallest adaptive page window [25]: "
if "%min_window%"=="" set "min_window=25"
set /p "method=Method auto/txt/ocr [auto]: "
if "%method%"=="" set "method=auto"
set /p "use_api=Use persistent MinerU API [Y/n]: "
set "api_arg="
if /i not "%use_api%"=="n" (
    call :run_wsl ".venv/bin/python start.py mineru-api start"
    if not errorlevel 1 set "api_arg=--api-url http://127.0.0.1:18080"
)
call :run_wsl ".venv/bin/python start.py large-pdf '%pdf_path%' --output '%out_dir%' --page-window %page_window% --min-page-window %min_window% --retries 1 --method %method% !api_arg! --log-file '%out_dir%/large_pdf.log'"
goto menu

:batch
echo.
echo Enter paths as WSL/Linux paths, for example:
echo /mnt/d/Codex/docs-folder
echo.
set /p "folder_path=Folder path: "
set /p "batch_out=Output folder [./batch_output]: "
if "%batch_out%"=="" set "batch_out=./batch_output"
set /p "workers=Workers [2]: "
if "%workers%"=="" set "workers=2"
set /p "use_api=Use persistent MinerU API [Y/n]: "
set "api_arg="
if /i not "%use_api%"=="n" (
    call :run_wsl ".venv/bin/python start.py mineru-api start"
    if not errorlevel 1 set "api_arg=--api-url http://127.0.0.1:18080"
)
set "batch_command=.venv/bin/python start.py batch '%folder_path%' --output '%batch_out%' --recursive --incremental --workers %workers% --no-progress !api_arg! --log-file '%batch_out%/batch.log'"
call :run_wsl "!batch_command! --dry-run"
if errorlevel 1 goto menu
set /p "run_now=Dry run passed. Process these files now [y/N]: "
if /i "%run_now%"=="y" call :run_wsl "!batch_command!"
if /i "%run_now%"=="yes" call :run_wsl "!batch_command!"
goto menu

:run_wsl
echo.
echo Running in WSL:
echo %~1
echo.
wsl.exe --cd "%~dp0" bash -lc "if [ ! -x .venv/bin/python ]; then command -v uv >/dev/null 2>&1 || { echo 'uv is required to create the environment.'; exit 127; }; uv sync --frozen --all-extras --link-mode copy || exit $?; fi; %~1"
set "run_code=!errorlevel!"
echo.
echo Command finished with exit code !run_code!.
echo.
pause
exit /b !run_code!

:done
endlocal
exit /b 0
