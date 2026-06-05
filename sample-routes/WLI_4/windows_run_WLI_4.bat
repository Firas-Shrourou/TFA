@echo off
set PYTHONUTF8=1

echo.
echo ================================================================
echo   Thawing Field Analyzer ^| WLI_4 Sample Run
echo ================================================================
echo   This script runs the WLI_4 benchmark route.
echo.
echo   The tfa-environment-settings.json in this folder is
echo   pre-configured for WLI_4:
echo     Potential  : WLI  (Peebles ^& Vilenkin 1999)
echo     Parameters : alpha = 1.0 ^|  phi_inf = 1.35
echo     Initial    : phi_i = 1.35,  phi_N_i = 0.0
echo.
echo   Results will be written to the results\ subfolder.
echo ================================================================
echo.

python "%~dp0run_WLI_4.py"

echo.
echo ================================================================
echo   WLI_4 run complete.
echo   Open the results\ subfolder to inspect outputs.
echo ================================================================
echo.

pause
