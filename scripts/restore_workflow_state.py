"""Restore the newest state artifact, or fail closed rather than lose forecast history.

Uses the ephemeral GitHub Actions token. No token, URL query secret or data payload
is logged. Public repositories run demo data only in the supplied workflow.
"""

import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path


def request(path: str) -> bytes:
    headers = {
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Repository comes from the runner, not user-supplied URLs.
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)

    class DropAuthorizationOnRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
            if redirected:
                redirected.remove_header("Authorization")
            return redirected

    opener = urllib.request.build_opener(DropAuthorizationOnRedirect())
    with opener.open(req, timeout=30) as response:
        return response.read()


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("Invalid runner repository")
    payload = json.loads(
        request(f"/repos/{repository}/actions/artifacts?name=trendforge-state&per_page=100")
    )
    artifacts = sorted(payload.get("artifacts", []), key=lambda a: a["created_at"], reverse=True)
    if not artifacts:
        # Never silently reinitialize when previous scheduled work existed.
        runs = json.loads(
            request(
                f"/repos/{repository}/actions/workflows/daily-update.yml/runs?status=success&per_page=1"
            )
        )
        if runs.get("total_count", 0):
            raise RuntimeError(
                "Previous runs exist but no state artifact remains. Restore a backup before continuing."
            )
        print("First run: initializing a new forecast ledger.")
        return
    latest = artifacts[0]
    if latest.get("expired"):
        raise RuntimeError(
            "The newest state artifact expired. Restore a backup; refusing to reset the ledger."
        )
    archive = request(f"/repos/{repository}/actions/artifacts/{int(latest['id'])}/zip")
    target = Path("data/trendforge.db")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        candidates = [name for name in zipped.namelist() if name.endswith("trendforge.db")]
        if len(candidates) != 1:
            raise RuntimeError("State artifact has an unexpected layout")
        info = zipped.getinfo(candidates[0])
        if info.file_size > 500_000_000:
            raise RuntimeError("State artifact is too large; use persistent database hosting")
        # Write exactly the known target; never extract paths from the remote archive.
        target.write_bytes(zipped.read(candidates[0]))
    print("Restored the previous forecast ledger.")


if __name__ == "__main__":
    main()
