# Getting started

Use the [root quick start](../README.md) first. Commands below assume the repository root unless they explicitly enter `frontend`. SQLite is created automatically; no database server or paid API is needed for demo mode.

## Windows PowerShell

Install Python 3.12+ and Node 22.12+ from their official installers. Open a new terminal so PATH updates apply.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\.venv\Scripts\python.exe -m trendforge demo
.\.venv\Scripts\python.exe -m trendforge serve
```

No PowerShell execution-policy change is needed when invoking the venv interpreter directly. In a second terminal: `cd frontend`, `npm ci`, `npm run dev`.

## Linux, macOS and WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e backend
python -m trendforge demo
python -m trendforge serve
```

If venv creation fails on Debian/Ubuntu, install the distribution's `python3-venv` package. Use Python 3.12 or later; the lock is tested with 3.12. In WSL, keep the project in the Linux filesystem for better npm/SQLite performance. Open `http://localhost:5173` in the host browser once the Vite server is running.

## Android: practical options

1. Run the backend and frontend on a laptop, Codespace or VPS and use the Android browser. Use an authenticated HTTPS gateway for remote access.
2. For local use, run Debian/Ubuntu inside Termux `proot-distro` and install Python 3.12+, Node 22.12+ and build prerequisites there. Use the same venv workflow.

NumPy/SciPy/scikit-learn wheels and Rollup native binaries are the main portability risks. Native Termux uses Android/Bionic rather than glibc; this is not interchangeable with a standard Linux wheel. Do not install architecture-mismatched binaries or assume a successful `npm install` proves the dev server can execute. If compilation is too heavy for your phone, use a remote backend. The repository has no requirement to run Docker on Android.

If Vite fails with a native Rollup error in proot, verify `uname -m`, your Node architecture, available memory and matching optional dependencies. The clean fix depends on the device; no untested binary workaround is enabled in this project. Python-only CLI commands remain useful even without the dashboard.

## Codespaces

Create a Codespace after publishing the repository. Follow the Linux quick start. Forward ports 5173 and 8000 privately; keep them private because the default demo backend has no account login. Do not change port visibility merely to make the setup convenient. Data on an ephemeral Codespace is not an operational backup.

## Generic VPS

Use the Docker deployment behind TLS and an authenticated gateway. Configure `API_TOKEN`, allowed origins, private network/database access and a persistent scheduler. Read [deployment](deployment.md) before exposing anything beyond localhost. Use a single API worker with SQLite and the built-in per-process rate limiter; use a shared gateway limiter for multiple workers.

## Typical errors

| Symptom | Check |
|---|---|
| Empty dashboard | Run `python -m trendforge demo`; verify `DEMO_MODE` matches the stored data mode |
| API access token required | Enter the server's `API_TOKEN` in connection settings; never a provider key |
| Connection refused | Start the backend on 8000; Vite proxies `/api` there |
| Provider not configured | Check `.env` in the current working directory, then run `trendforge providers` |
| Provider quota exhausted | Wait for the provider's allowed reset; repeated `--force` does not bypass quotas |
| No forecast | History may be too short, too dissimilar, or stale; inspect the evidence |
| Missing `US/Eastern` timezone | Install the locked dependencies; `tzdata` is included |
| No reports | Run `trendforge report` after loading data |
| Mobile table exceeds card width | Swipe inside the table card; the entire page should not scroll horizontally |

`trendforge doctor` reports the runtime, database, data counts and sanitized provider status.
