@echo off
rem Update WebPilot: the newest code (git pull), the extension build (extension\dist), the Python packages and,
rem when it was installed with `uv tool install`, the `webpilot` command. The daemon is stopped so the next
rem `webpilot` command starts the new one. Afterwards, reload the extension on the browser's extensions page.
rem   update.bat            pull and build
rem   update.bat --no-pull  build only (after changing the code yourself)
setlocal
title WebPilot - update
cd /d "%~dp0"
rem All of it in one block: cmd reads a .bat file while it runs it, and the git pull can change this very file.
(
  set "PULL=1"
  if /i "%~1"=="--no-pull" set "PULL="
  for %%t in (uv npm) do (
    where %%t >nul 2>nul || (
      echo  %%t is not on PATH: install it ^(see README.md, "Setup"^), then run update.bat again.
      pause
      exit /b 1
    )
  )

  echo  Stopping the WebPilot daemon ^(it starts again on the next webpilot command^) ...
  call uv run --no-sync webpilot stop >nul 2>nul

  if defined PULL (
    if not exist ".git" (
      echo  This folder is not a git clone, so it cannot fetch new files itself. Clone it again:
      echo    git clone https://github.com/thkprado/webpilot.git
      pause
      exit /b 1
    )
    where git >nul 2>nul || (
      echo  git is not on PATH: install Git for Windows ^(winget install Git.Git^) or run "git pull" here yourself,
      echo  then run "update.bat --no-pull".
      pause
      exit /b 1
    )
    echo  Getting the newest WebPilot ^(git pull^) ...
    git pull --ff-only
    if errorlevel 1 (
      echo.
      echo  git pull did not succeed ^(the reason is above^): nothing was updated. Files you changed here can stop it:
      echo  "git status" lists them.
      pause
      exit /b 1
    )
  )

  echo  Building the extension ...
  pushd extension
  call npm ci --no-audit --no-fund
  if errorlevel 1 (
    popd
    echo  npm ci failed ^(the reason is above^).
    pause
    exit /b 1
  )
  call npm run build
  if errorlevel 1 (
    popd
    echo  The extension build failed ^(the reason is above^).
    pause
    exit /b 1
  )
  popd

  echo  Installing the Python packages ^(uv sync^) ...
  call uv sync
  if errorlevel 1 (
    echo  uv sync failed ^(the reason is above^).
    pause
    exit /b 1
  )

  if not exist "extension\dist\config.json" (
    call uv run --no-sync webpilot setup
    if errorlevel 1 (
      pause
      exit /b 1
    )
  )

  uv tool list 2>nul | findstr /b /c:"webpilot " >nul
  if not errorlevel 1 (
    echo  Updating the `webpilot` command ^(uv tool install^) ...
    call uv tool install --editable --reinstall .
    if errorlevel 1 (
      echo  uv tool install failed ^(the reason is above^). A running `webpilot` command can hold its files: close it
      echo  and run "update.bat --no-pull".
      pause
      exit /b 1
    )
  )

  echo.
  echo  WebPilot is up to date. Now reload the extension: on the browser's extensions page ^(chrome://extensions,
  echo  edge://extensions, ...^) click reload on the WebPilot card, in each profile that uses it.
  echo  If you installed the agent skill, "webpilot skill list" shows "outdated" when it needs "webpilot skill install".
  pause
  exit /b 0
)
