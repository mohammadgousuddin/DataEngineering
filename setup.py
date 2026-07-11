#!/usr/bin/env python3
"""
MAD setup — environment checks + runtime directory scaffolding.

This tree ships pre-scaffolded (every service file already exists under mad_project/),
so setup.py does NOT regenerate the tree. It:
  1. verifies Python / Docker / Docker Compose are available,
  2. creates the runtime directories the stack writes into (data/, model/),
  3. prints the next steps.

Run from the MAD/ folder:  python3 setup.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT = BASE / "mad_project"

OK = "\033[92m"   # green
WARN = "\033[93m"  # yellow
ERR = "\033[91m"   # red
DIM = "\033[2m"
RST = "\033[0m"


def check(label, ok, detail=""):
    mark = f"{OK}OK{RST}" if ok else f"{ERR}MISSING{RST}"
    print(f"  [{mark}] {label}" + (f"  {DIM}{detail}{RST}" if detail else ""))
    return ok


def have(cmd):
    return shutil.which(cmd) is not None


def docker_compose_cmd():
    """Return the working compose invocation, or None."""
    for candidate in (["docker", "compose", "version"], ["docker-compose", "version"]):
        try:
            subprocess.run(candidate, capture_output=True, check=True)
            return candidate[:-1]
        except Exception:
            continue
    return None


def main():
    print(f"\n{'='*58}")
    print("  MAD — Monitor · Automate · Detect  ·  setup")
    print(f"{'='*58}\n")

    print("Environment:")
    py_ok = sys.version_info >= (3, 9)
    check(f"Python {sys.version_info.major}.{sys.version_info.minor} (>= 3.9)", py_ok)
    docker_ok = check("docker", have("docker"))
    compose = docker_compose_cmd()
    check("docker compose", compose is not None,
          " ".join(compose) if compose else "install docker-compose-plugin")

    print("\nRuntime directories:")
    for sub in ("data", "model"):
        d = PROJECT / sub
        d.mkdir(parents=True, exist_ok=True)
        gk = d / ".gitkeep"
        gk.touch(exist_ok=True)
        check(f"mad_project/{sub}/", d.is_dir())

    print("\nProject tree:")
    expected = [
        "docker-compose.yml",
        ".env",
        "mosquitto/config/mosquitto.conf",
        "simulator/sensor_sim.py",
        "ingestion/app.py",
        "control/app.py",
        "controller/loop.py",
        "csv_logger/app.py",
        "dashboard/app.py",
    ]
    all_present = True
    for rel in expected:
        present = (PROJECT / rel).exists()
        all_present = all_present and present
        check(rel, present)

    print()
    if not all_present:
        print(f"{ERR}Some service files are missing — re-extract the MAD folder.{RST}")
        sys.exit(1)

    print(f"{OK}Setup complete.{RST}  Next steps:\n")
    print("  1. python3 generate_dataset.py --train   # build dataset + train Random Forest")
    print("  2. bash launch.sh                        # docker compose up the stack")
    print("  3. xdg-open http://localhost:8050        # open the dashboard\n")
    if not (docker_ok and compose):
        print(f"{WARN}Install Docker + the compose plugin before launching (see README §1).{RST}\n")


if __name__ == "__main__":
    main()
