@echo off
setlocal
set "SRC=%~dp0"
set "DST=%USERPROFILE%\KAREEM_AGENT"
if not exist "%DST%" mkdir "%DST%"
for /f "tokens=1-4 delims=/-. " %%a in ('date /t') do set "D=%%d%%b%%c"
for /f "tokens=1-3 delims=:., " %%a in ('time /t') do set "T=%%a%%b%%c"
set "STAMP=%D%_%T%"
if exist "%DST%\brain" xcopy "%DST%\brain" "%DST%\backups\pre_v7_update_%STAMP%\brain\" /E /I /Y >nul
if exist "%DST%\core" xcopy "%DST%\core" "%DST%\backups\pre_v7_update_%STAMP%\core\" /E /I /Y >nul
if exist "%DST%\tools" xcopy "%DST%\tools" "%DST%\backups\pre_v7_update_%STAMP%\tools\" /E /I /Y >nul
xcopy "%SRC%brain" "%DST%\brain\" /E /I /Y >nul
xcopy "%SRC%core" "%DST%\core\" /E /I /Y >nul
xcopy "%SRC%tools" "%DST%\tools\" /E /I /Y >nul
xcopy "%SRC%tests" "%DST%\tests\" /E /I /Y >nul
copy /Y "%SRC%V7_CHANGELOG.md" "%DST%\" >nul
copy /Y "%SRC%V7_HANDOFF_NOTES.md" "%DST%\" >nul

echo V7 files updated in %DST%
pause
