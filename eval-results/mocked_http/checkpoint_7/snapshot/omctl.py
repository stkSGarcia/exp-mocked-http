#!/usr/bin/env python3
"""Command-line client for hmock admin operations."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import yaml

import hmock


DEFAULT_DIRECTORY = "./demo_templates"
DEFAULT_ADMIN_URL = "http://localhost:9998"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push = subparsers.add_parser("push", help="upload YAML templates")
    push.add_argument("-d", "--directory", default=DEFAULT_DIRECTORY)
    push.add_argument("-u", "--url", default=DEFAULT_ADMIN_URL)
    push.add_argument("-k", "--set-key")
    push.set_defaults(handler=_run_push)

    delete = subparsers.add_parser("delete", help="delete a named template set")
    delete.add_argument("-u", "--url", default=DEFAULT_ADMIN_URL)
    delete.add_argument("-k", "--set-key", required=True)
    delete.set_defaults(handler=_run_delete)
    return parser


def load_template_directory(directory: str) -> list[dict[str, object]]:
    root = Path(directory)
    definitions: list[dict[str, object]] = []
    for path in hmock.discover_yaml_files(directory):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(f"{path}: {exc}") from exc
        definitions.extend(hmock._loaded_objects(data, path))
    for index, definition in enumerate(definitions):
        hmock._validate_definition(definition, f"template {index + 1}")
    hmock.compile_runtime(definitions, str(root))
    return definitions


def _admin_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _request(url: str, method: str, expected_status: int, data: Optional[bytes] = None) -> None:
    headers = {"Content-Type": "application/yaml"} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=hmock.OUTBOUND_HTTP_TIMEOUT_SECONDS) as response:
            response.read()
            if response.status != expected_status:
                raise RuntimeError(
                    f"{method} {url} returned {response.status}; expected {expected_status}"
                )
    except urllib.error.HTTPError as exc:
        exc.read()
        raise RuntimeError(
            f"{method} {url} returned {exc.code}; expected {expected_status}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def _run_push(args: argparse.Namespace) -> None:
    definitions = load_template_directory(args.directory)
    payload = yaml.safe_dump(definitions, sort_keys=False).encode("utf-8")
    if args.set_key is None:
        path = "/api/v1/templates"
    else:
        set_key = urllib.parse.quote(args.set_key, safe="")
        path = f"/api/v1/template_sets/{set_key}"
    _request(_admin_url(args.url, path), "POST", 200, payload)


def _run_delete(args: argparse.Namespace) -> None:
    set_key = urllib.parse.quote(args.set_key, safe="")
    path = f"/api/v1/template_sets/{set_key}"
    _request(_admin_url(args.url, path), "DELETE", 204)


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"omctl: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
