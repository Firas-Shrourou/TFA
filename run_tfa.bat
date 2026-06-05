@echo off
set PYTHONUTF8=1

echo.
echo ================================================================
echo   Thawing Field Analyzer
echo ================================================================
echo   Settings: tfa-environment-settings.json
echo   Results : results\
echo ================================================================
echo.

if not exist "%~dp0results" mkdir "%~dp0results"
pushd "%~dp0.."
python "%~dp0run_tfa.py"
set TFA_EXIT=%ERRORLEVEL%
popd

echo.
echo ================================================================
if "%TFA_EXIT%"=="0" (
echo   Run complete.
) else (
echo   Run failed.
)
echo ================================================================
echo.
exit /b %TFA_EXIT%
