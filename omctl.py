from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence
from urllib.parse import quote

import hmock


DEFAULT_DIRECTORY = "./demo_templates"
DEFAULT_URL = "http://localhost:9998"


def _admin_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _load_yaml_payload(directory: str) -> bytes:
    root = Path(directory)
    if not root.is_dir():
        raise hmock.ValidationError(f"directory not found: {directory}")
    parts: list[str] = []
    for path in hmock.discover_yaml_files(root):
        text = path.read_text()
        parsed = hmock.parse_yaml_subset(text)
        if parsed is None:
            parsed = []
        if not isinstance(parsed, list):
            raise hmock.ValidationError(f"{path} must contain a top-level list")
        parts.append(text.strip())
    payload = "\n".join(part for part in parts if part)
    return (payload + "\n").encode() if payload else b""


def _request(url: str, method: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except urllib.error.URLError as exc:
        raise hmock.HMockError(str(exc)) from exc


def push(args: argparse.Namespace) -> int:
    payload = _load_yaml_payload(args.directory)
    if args.set_key:
        path = f"/api/v1/template_sets/{quote(args.set_key, safe='')}"
    else:
        path = "/api/v1/templates"
    status, body = _request(
        _admin_url(args.url, path),
        "POST",
        payload,
        {"Content-Type": "application/yaml"},
    )
    if status != 200:
        print(body or f"push failed with status {status}", file=sys.stderr)
        return 1
    return 0


def delete(args: argparse.Namespace) -> int:
    status, body = _request(
        _admin_url(args.url, f"/api/v1/template_sets/{quote(args.set_key, safe='')}"),
        "DELETE",
    )
    if status != 204:
        print(body or f"delete failed with status {status}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("-d", "--directory", default=DEFAULT_DIRECTORY)
    push_parser.add_argument("-u", "--url", default=DEFAULT_URL)
    push_parser.add_argument("-k", "--set-key")
    push_parser.set_defaults(func=push)

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("-u", "--url", default=DEFAULT_URL)
    delete_parser.add_argument("-k", "--set-key", required=True)
    delete_parser.set_defaults(func=delete)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except hmock.HMockError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
