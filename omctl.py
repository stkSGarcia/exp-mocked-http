#!/usr/bin/env python3
"""omctl — remote admin CLI for the hmock server."""

import argparse
import os
import sys
import urllib.error
import urllib.request

import yaml


def _read_yaml_dir(directory: str) -> list:
    items = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                fpath = os.path.join(root, fname)
                with open(fpath) as fh:
                    data = yaml.safe_load(fh)
                if data is None:
                    continue
                if isinstance(data, list):
                    items.extend(data)
                else:
                    items.append(data)
    return items


def cmd_push(args):
    items = _read_yaml_dir(args.directory)
    payload = yaml.dump(items, allow_unicode=True).encode("utf-8")
    if args.set_key:
        url = f"{args.url.rstrip('/')}/api/v1/template_sets/{args.set_key}"
    else:
        url = f"{args.url.rstrip('/')}/api/v1/templates"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/yaml")
    req.add_header("Content-Length", str(len(payload)))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status < 200 or resp.status >= 300:
                print(f"error: server returned {resp.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as exc:
        print(f"error: server returned {exc.code}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_delete(args):
    url = f"{args.url.rstrip('/')}/api/v1/template_sets/{args.set_key}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 204:
                print(f"error: expected 204, got {resp.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as exc:
        print(f"error: server returned {exc.code}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="omctl", description="Admin CLI for hmock")
    sub = parser.add_subparsers(dest="command")

    push_p = sub.add_parser("push", help="Upload templates to the admin API")
    push_p.add_argument("-d", "--directory", default="./demo_templates",
                        help="Local directory of YAML templates (default: ./demo_templates)")
    push_p.add_argument("-u", "--url", default="http://localhost:9998",
                        help="Admin API base URL (default: http://localhost:9998)")
    push_p.add_argument("-k", "--set-key", default=None, dest="set_key",
                        help="Upload as a named template set")

    del_p = sub.add_parser("delete", help="Delete a named template set")
    del_p.add_argument("-u", "--url", default="http://localhost:9998",
                       help="Admin API base URL (default: http://localhost:9998)")
    del_p.add_argument("-k", "--set-key", required=True, dest="set_key",
                       help="Template set to delete")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(1)
    return args


def main():
    args = _parse_args()
    if args.command == "push":
        cmd_push(args)
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
