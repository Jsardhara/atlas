@echo off
REM ============================================================================
REM Atlas — host bring-up
REM   1. Start infra (postgres + redis + freqtrade) in Docker
REM   2. Wait for postgres healthy
REM   3. Launch API + 5 agents on host, each in its own console window
REM ============================================================================

setlocal

set "ATLAS_ROOT=%~dp0.."
pushd "%ATLAS_ROOT%"

echo [atlas] starting infra containers...
docker compose up -d postgres redis freqtrade
if errorlevel 1 (
    echo [atlas] docker compose up failed
    popd
    exit /b 1
)

echo [atlas] waiting for postgres healthy...
set /a _tries=0
:wait_postgres
set /a _tries+=1
docker compose exec -T postgres pg_isready -U atlas -d atlas >nul 2>&1
if %errorlevel%==0 goto pg_ready
if %_tries% GEQ 60 (
    echo [atlas] postgres did not become healthy within 60s
    popd
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_postgres
:pg_ready
echo [atlas] postgres ready.

echo [atlas] launching API and agents...
start "Atlas-API"        cmd /k "cd /d %ATLAS_ROOT% && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000"
start "Atlas-Oracle"     cmd /k "cd /d %ATLAS_ROOT% && python scripts\run_agent.py oracle"
start "Atlas-Architect"  cmd /k "cd /d %ATLAS_ROOT% && python scripts\run_agent.py architect"
start "Atlas-Guardian"   cmd /k "cd /d %ATLAS_ROOT% && python scripts\run_agent.py guardian"
start "Atlas-Trader"     cmd /k "cd /d %ATLAS_ROOT% && python scripts\run_agent.py trader"
start "Atlas-Sage"       cmd /k "cd /d %ATLAS_ROOT% && python scripts\run_agent.py sage"

echo [atlas] all 6 windows launched (1 API + 5 agents).
echo [atlas] tail logs in each window. shutdown via close-window or Ctrl+C.

popd
endlocal
