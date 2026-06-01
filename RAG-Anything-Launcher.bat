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

for /f "delims=" %%I in ('wsl.exe wslpath -a "%~dp0"') do set "WSL_PROJECT_DIR=%%I"

if "%WSL_PROJECT_DIR%"=="" (
    echo Could not resolve this folder inside WSL.
    echo.
    pause
    exit /b 1
)

:menu
cls
echo ==========================================
echo RAG-Anything Launcher
echo Project: %~dp0
echo WSL path: %WSL_PROJECT_DIR%
echo ==========================================
echo.
echo 1. Open interactive starter menu
echo 2. Show all starter commands and options
echo 3. Check MinerU parser installation
echo 4. Large PDF wizard
echo 5. Batch folder dry-run wizard
echo 6. Show large-PDF help
echo 7. Show batch help
echo 8. Exit
echo.
set /p "choice=Choose an option [1-8]: "

if "%choice%"=="1" goto interactive
if "%choice%"=="2" goto help_all
if "%choice%"=="3" goto check_mineru
if "%choice%"=="4" goto large_pdf
if "%choice%"=="5" goto batch_dry_run
if "%choice%"=="6" goto help_large_pdf
if "%choice%"=="7" goto help_batch
if "%choice%"=="8" goto done

echo.
echo Unknown choice.
pause
goto menu

:interactive
call :run_wsl "uv run python start.py"
goto menu

:help_all
call :run_wsl "uv run python start.py --help"
goto menu

:check_mineru
call :run_wsl "uv run python start.py check --parser mineru"
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
call :run_wsl "uv run python start.py large-pdf '%pdf_path%' --output '%out_dir%' --page-window %page_window% --min-page-window %min_window% --retries 1 --method %method%"
goto menu

:batch_dry_run
echo.
echo Enter paths as WSL/Linux paths, for example:
echo /mnt/d/Codex/docs-folder
echo.
set /p "folder_path=Folder path: "
set /p "batch_out=Output folder [./batch_output]: "
if "%batch_out%"=="" set "batch_out=./batch_output"
set /p "workers=Workers [2]: "
if "%workers%"=="" set "workers=2"
call :run_wsl "uv run python start.py batch '%folder_path%' --output '%batch_out%' --recursive --dry-run --workers %workers% --no-progress"
goto menu

:help_large_pdf
call :run_wsl "uv run python start.py large-pdf --help"
goto menu

:help_batch
call :run_wsl "uv run python start.py batch --help"
goto menu

:run_wsl
echo.
echo Running in WSL:
echo cd '%WSL_PROJECT_DIR%' ^&^& %~1
echo.
wsl.exe bash -lc "cd '%WSL_PROJECT_DIR%' && %~1"
echo.
echo Command finished with exit code %errorlevel%.
echo.
pause
exit /b 0

:done
endlocal
exit /b 0
