@echo off
set PYTHONUTF8=1

echo.
echo ================================================================
echo   Thawing Field Analyzer ^| WQI_F765 Sample Run
echo ================================================================
echo   This script runs the WQI_F765 benchmark route.
echo.
echo   The tfa-environment-settings.json in this folder is
echo   pre-configured for WQI_F765:
echo     Potential  : WQI  (Dimopoulos ^& Donaldson-Wood 2019)
echo     Parameters : phi_F = 7.65 ^|  M_Mp = 1.794e-13
echo     Initial    : phi_i = 7.65,  phi_N_i = 0.0
echo.
echo   Results will be written to the results\ subfolder.
echo ================================================================
echo.

python "%~dp0run_WQI_F765.py"

echo.
echo ================================================================
echo   WQI_F765 run complete.
echo   Open the results\ subfolder to inspect outputs.
echo ================================================================
echo.

pause
