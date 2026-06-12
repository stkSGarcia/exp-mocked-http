from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus, urljoin


def discover_yaml_files(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"directory not found: {directory}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {directory}")
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )


def load_yaml_payload(directory: str | Path) -> str:
    parts = [path.read_text() for path in discover_yaml_files(directory)]
    return "\n".join(part.strip() for part in parts if part.strip()) + ("\n" if parts else "")


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _request(url: str, method: str, body: str | None = None, headers: dict[str, str] | None = None) -> int:
    data = body.encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code


def push(directory: str, url: str, set_key: str | None = None) -> int:
    payload = load_yaml_payload(directory)
    path = "/api/v1/templates" if not set_key else f"/api/v1/template_sets/{quote_plus(set_key, safe='')}"
    status = _request(
        _endpoint(url, path),
        "POST",
        payload,
        {"Content-Type": "application/yaml"},
    )
    if status != 200:
        raise RuntimeError(f"push failed with status {status}")
    return status


def delete(url: str, set_key: str) -> int:
    status = _request(_endpoint(url, f"/api/v1/template_sets/{quote_plus(set_key, safe='')}"), "DELETE")
    if status != 204:
        raise RuntimeError(f"delete failed with status {status}")
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
            parser.error("unknown command")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
