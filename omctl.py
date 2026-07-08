from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def discover_yaml_files(root: str | Path) -> list[Path]:
    path = Path(root)
    if not path.exists():
        raise ValueError(f"directory not found: {path}")
    if not path.is_dir():
        raise ValueError(f"not a directory: {path}")
    return sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )


def load_yaml_payload(directory: str | Path) -> bytes:
    parts: list[str] = []
    for path in discover_yaml_files(directory):
        text = path.read_text()
        if text.strip():
            parts.append(text.rstrip())
    return ("\n".join(parts) + ("\n" if parts else "")).encode()


def _request(url: str, method: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> int:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as response:
        response.read()
        return response.status


def push(directory: str, url: str, set_key: str | None = None) -> int:
    payload = load_yaml_payload(directory)
    base = url.rstrip("/")
    if set_key:
        endpoint = f"{base}/api/v1/template_sets/{quote(set_key, safe='')}"
    else:
        endpoint = f"{base}/api/v1/templates"
    status = _request(endpoint, "POST", payload, {"Content-Type": "application/yaml"})
    if status < 200 or status >= 300:
        raise RuntimeError(f"push failed with HTTP {status}")
    return status


def delete(url: str, set_key: str) -> int:
    if not set_key:
        raise ValueError("--set-key is required")
    endpoint = f"{url.rstrip('/')}/api/v1/template_sets/{quote(set_key, safe='')}"
    status = _request(endpoint, "DELETE")
    if status != 204:
        raise RuntimeError(f"delete failed with HTTP {status}")
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("-d", "--directory", default="./demo_templates")
    push_parser.add_argument("-u", "--url", default="http://localhost:9998")
    push_parser.add_argument("-k", "--set-key")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("-u", "--url", default="http://localhost:9998")
    delete_parser.add_argument("-k", "--set-key", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "push":
            push(args.directory, args.url, args.set_key)
        elif args.command == "delete":
            delete(args.url, args.set_key)
        else:
            parser.error(f"unsupported command: {args.command}")
    except (OSError, ValueError, RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"omctl: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
