from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence


DEFAULT_DIRECTORY = "./demo_templates"
DEFAULT_URL = "http://localhost:9998"


def discover_yaml_files(root: str | Path) -> list[Path]:
    path = Path(root)
    if not path.exists():
        return []
    return sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )


def load_yaml_payload(directory: str | Path) -> str:
    parts = [path.read_text() for path in discover_yaml_files(directory)]
    if not parts:
        return "[]\n"
    return "\n".join(part.rstrip() for part in parts if part.strip()) + "\n"


def admin_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def send_request(url: str, method: str, body: str | None = None) -> tuple[int, bytes]:
    data = body.encode() if body is not None else None
    headers = {"Content-Type": "application/yaml"} if body is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push = subparsers.add_parser("push")
    push.add_argument("--directory", "-d", default=DEFAULT_DIRECTORY)
    push.add_argument("--url", "-u", default=DEFAULT_URL)
    push.add_argument("--set-key", "-k")
    push.set_defaults(func=push_command)

    delete = subparsers.add_parser("delete")
    delete.add_argument("--url", "-u", default=DEFAULT_URL)
    delete.add_argument("--set-key", "-k", required=True)
    delete.set_defaults(func=delete_command)

    return parser


def push_command(args: argparse.Namespace) -> int:
    payload = load_yaml_payload(args.directory)
    path = (
        f"/api/v1/template_sets/{args.set_key}"
        if args.set_key
        else "/api/v1/templates"
    )
    status, body = send_request(admin_url(args.url, path), "POST", payload)
    if status != 200:
        raise RuntimeError(f"push failed with HTTP {status}")
    if body:
        sys.stdout.write(body.decode(errors="replace") + "\n")
    return 0


def delete_command(args: argparse.Namespace) -> int:
    status, _ = send_request(admin_url(args.url, f"/api/v1/template_sets/{args.set_key}"), "DELETE")
    if status != 204:
        raise RuntimeError(f"delete failed with HTTP {status}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except urllib.error.HTTPError as exc:
        sys.stderr.write(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}\n")
        return 1
    except urllib.error.URLError as exc:
        sys.stderr.write(f"request failed: {exc.reason}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"I/O error: {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
