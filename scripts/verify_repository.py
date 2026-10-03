"""Deterministic offline repository audit: local links, workflows, secrets and packaging."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {
    "node_modules",
    ".git",
    "dist",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "test-results",
    "playwright-report",
}


def main() -> None:
    errors = []
    files = [
        p
        for p in ROOT.rglob("*")
        if p.is_file() and not EXCLUDE.intersection(p.relative_to(ROOT).parts)
    ]
    for p in files:
        if p.suffix == ".md":
            for target in re.findall(r"\]\(([^)\s]+)(?:\s+[^)]*)?\)", p.read_text()):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                destination = (p.parent / target.split("#")[0]).resolve()
                if not destination.exists():
                    errors.append(f"Broken local link: {p.relative_to(ROOT)} → {target}")
        if (
            p.suffix in (".py", ".md", ".yaml", ".yml", ".ts", ".tsx", ".json", ".toml")
            and "package-lock" not in p.name
        ):
            content = p.read_text()
            for pattern in (
                r"gh[pousr]_[A-Za-z0-9]{30,}",
                r"AIza[A-Za-z0-9_-]{30,}",
                r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            ):
                if re.search(pattern, content):
                    errors.append(f"Possible secret: {p.relative_to(ROOT)}")
    workflows = list((ROOT / ".github/workflows").glob("*.yml"))
    for p in workflows:
        data = yaml.load(p.read_text(), Loader=yaml.BaseLoader)
        if not all(k in data for k in ("name", "on", "jobs", "permissions")):
            errors.append(f"Invalid workflow structure: {p.name}")
        for name, job in data["jobs"].items():
            if "runs-on" not in job or not job.get("steps"):
                errors.append(f"Incomplete workflow job: {p.name}/{name}")
            for step in job["steps"]:
                if not ("uses" in step or "run" in step):
                    errors.append(f"Invalid workflow step in {p.name}")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name in ("backend", "frontend"):
        service = compose["services"][name]
        if not service.get("read_only") or "ALL" not in service.get("cap_drop", []):
            errors.append(f"Missing secure container defaults: {name}")
        if not (ROOT / service["build"]["dockerfile"]).exists():
            errors.append(f"Dockerfile missing: {name}")
    print(
        json.dumps(
            {"checked_files": len(files), "workflows": len(workflows), "errors": errors}, indent=2
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
