"""Bounded diagnostic of the existing CLI; does not change recorder behavior."""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("users", help="Comma-separated TikTok usernames")
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "diagnostics" / "recordings"
    output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(root / "src" / "main.py"),
        "-user",
        args.users,
        "-mode",
        "manual",
        "-duration",
        str(args.duration),
        "-output",
        str(output),
        "-no-update-check",
    ]
    try:
        result = subprocess.run(command, cwd=root, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("Diagnostic timeout: CLI did not finish within the limit.")
        return 124
    print(f"CLI exit code: {result.returncode}; inspect logs AND output media.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
