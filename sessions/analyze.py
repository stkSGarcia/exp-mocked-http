#!/usr/bin/env python3
"""
Analyze copied Codex session recordings in the current directory.

This script is designed to run after copy_codex_sessions.py has copied a
project's Codex JSONL files into one flat folder. By default it reads
`*.jsonl` from the current working directory and deduplicates repeated
snapshots of the same Codex session.
"""

import argparse
import json
import re
import shlex
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).parent
STAGE_ORDER = {"propose": 0, "apply": 1, "archive": 2, "unknown": 3}


# --- helpers -----------------------------------------------------------------

def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"Skipping bad JSON in {path}:{lineno}: {exc}")
    return records


def parse_ts(ts):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt_duration_ms(ms):
    if ms is None:
        return "N/A"
    seconds = int(ms / 1000)
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def fmt_duration_s(seconds):
    if seconds is None:
        return "N/A"
    return fmt_duration_ms(seconds * 1000)


def fmt_latency(ms):
    if ms is None:
        return "N/A"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def fmt_int(value):
    return f"{value:,}"


def md_escape(value):
    return str(value).replace("\n", " ").replace("|", "\\|")


def md_row(*cells):
    return "| " + " | ".join(md_escape(cell) for cell in cells) + " |"


def md_sep(*alignments):
    parts = []
    for alignment in alignments:
        if alignment == "r":
            parts.append("---:")
        elif alignment == "c":
            parts.append(":---:")
        else:
            parts.append("---")
    return "| " + " | ".join(parts) + " |"


def stable_json_chars(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    pieces.append(item["text"])
                elif isinstance(item.get("input"), str):
                    pieces.append(item["input"])
                elif isinstance(item.get("output"), str):
                    pieces.append(item["output"])
            elif isinstance(item, str):
                pieces.append(item)
        return "\n".join(pieces)
    return ""


# --- input discovery and deduplication ---------------------------------------

def discover_input_files(paths):
    if not paths:
        return sorted(Path.cwd().glob("*.jsonl"))

    files = []
    for path in paths:
        path = path.expanduser()
        if path.is_dir():
            files.extend(path.rglob("*.jsonl"))
        else:
            files.append(path)
    return sorted(set(files))


def get_session_meta(records, session_file):
    meta = {
        "session_id": session_file.stem,
        "cwd": "",
        "source": "",
        "model_provider": "",
        "cli_version": "",
        "base_instr_chars": 0,
    }
    for record in records:
        if record.get("type") != "session_meta":
            continue
        payload = record.get("payload", {})
        base_instructions = payload.get("base_instructions", {})
        if isinstance(base_instructions, dict):
            base_instr_chars = len(base_instructions.get("text", "") or "")
        else:
            base_instr_chars = len(str(base_instructions))
        meta.update({
            "session_id": payload.get("id", meta["session_id"]),
            "cwd": payload.get("cwd", ""),
            "source": payload.get("source", ""),
            "model_provider": payload.get("model_provider", ""),
            "cli_version": payload.get("cli_version", ""),
            "base_instr_chars": base_instr_chars,
        })
        break
    return meta


def load_candidates(paths):
    candidates = []
    for session_file in discover_input_files(paths):
        records = load_jsonl(session_file)
        if not records:
            continue
        meta = get_session_meta(records, session_file)
        candidates.append({
            "path": session_file,
            "records": records,
            "meta": meta,
            "record_count": len(records),
            "mtime": session_file.stat().st_mtime,
        })
    return candidates


def select_candidates(candidates, include_duplicates):
    by_session = defaultdict(list)
    for candidate in candidates:
        by_session[candidate["meta"]["session_id"]].append(candidate)

    duplicate_counts = {}
    if include_duplicates:
        for group in by_session.values():
            duplicate_count = max(len(group) - 1, 0)
            for candidate in group:
                duplicate_counts[candidate["path"]] = duplicate_count
        return candidates, duplicate_counts

    selected = []
    for group in by_session.values():
        group = sorted(
            group,
            key=lambda item: (item["record_count"], item["mtime"], str(item["path"])),
            reverse=True,
        )
        chosen = group[0]
        duplicate_counts[chosen["path"]] = len(group) - 1
        selected.append(chosen)

    return sorted(selected, key=lambda item: str(item["path"])), duplicate_counts


# --- Codex parsing -----------------------------------------------------------

def request_body(message):
    text = message.strip()
    marker = "## My request for Codex:"
    if marker in text:
        text = text.split(marker, 1)[1].strip()
    return text


def prompt_title(message):
    text = request_body(message)
    command = infer_prompt_command(text)
    if command:
        return command
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "(empty prompt)"
    title = lines[0]
    return title[:117] + "..." if len(title) > 120 else title


def infer_prompt_command(text):
    slash = re.search(r"(?<![\w.~/-])(/(?:prompt:[\w.-]+|opsx:[\w.-]+))\b", text)
    if slash:
        return slash.group(1)

    slash = re.search(r"(?m)^\s*(/[A-Za-z][\w:.-]*)\b", text)
    if slash:
        return slash.group(1)

    lower = text.lower()
    if "propose a new change" in lower:
        return "/opsx:propose"
    if "implement tasks from an openspec change" in lower:
        return "/opsx:apply"
    if "archive a completed change" in lower:
        return "/opsx:archive"
    return ""


def checkpoint_from_message(message):
    match = re.search(r"checkpoint[_ -]?(\d+)", message, re.IGNORECASE)
    return int(match.group(1)) if match else None


def infer_prompt_stage(message):
    text = request_body(message)
    lower = text.lower()
    command = infer_prompt_command(text)

    if command == "/opsx:propose":
        return "propose"
    if command == "/opsx:apply":
        return "apply"
    if command == "/opsx:archive":
        return "archive"

    if re.search(r"(?<![\w-])(?:\$?openspec-propose|opsx:propose)\b", lower):
        return "propose"
    if re.search(r"(?<![\w-])(?:\$?openspec-apply-change|opsx:apply)\b", lower):
        return "apply"
    if re.search(r"(?<![\w-])(?:\$?openspec-archive-change|opsx:archive)\b", lower):
        return "archive"

    if "propose a new change" in lower:
        return "propose"
    if "implement tasks from an openspec change" in lower:
        return "apply"
    if "archive a completed change" in lower:
        return "archive"
    return None


def session_checkpoint(turns):
    for turn in turns:
        checkpoint = checkpoint_from_message(turn["message"])
        if checkpoint is not None:
            return checkpoint
    return 99


def token_usage_from_record(record):
    payload = record.get("payload", {})
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info", {})
    return info.get("last_token_usage") or {}


def function_args(payload):
    args = payload.get("arguments")
    if not isinstance(args, str):
        return {}
    try:
        parsed = json.loads(args)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def command_preview(payload):
    name = payload.get("name", "")
    if name == "exec_command":
        cmd = function_args(payload).get("cmd", "")
    else:
        raw = payload.get("input") or payload.get("arguments") or ""
        cmd = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    return cmd[:117] + "..." if len(cmd) > 120 else cmd


def original_token_count(output):
    if not isinstance(output, str):
        return 0
    match = re.search(r"Original token count:\s*(\d+)", output)
    return int(match.group(1)) if match else 0


def output_body_chars(output):
    if not isinstance(output, str):
        return stable_json_chars(output)
    marker = "\nOutput:\n"
    if marker in output:
        return len(output.split(marker, 1)[1])
    return len(output)


def shell_words(cmd):
    try:
        return shlex.split(cmd)
    except ValueError:
        return []


def strip_shell_wrappers(words):
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    if len(words) >= 3 and words[0] in {"env", "command"}:
        return strip_shell_wrappers(words[1:])
    return words


def extract_file_read_command(cmd):
    words = strip_shell_wrappers(shell_words(cmd))
    if not words:
        return []

    command = Path(words[0]).name
    files = []

    if command == "sed":
        for word in words[1:]:
            if word == "--":
                continue
            if word.startswith("-"):
                continue
            if re.fullmatch(r"\d+(,\d+)?p", word):
                continue
            files.append(word)
        return files[-1:] if files else []

    if command == "cat":
        return [word for word in words[1:] if not word.startswith("-")]

    if command == "nl":
        return [word for word in words[1:] if not word.startswith("-")]

    if command in {"head", "tail"}:
        result = []
        skip_next = False
        options_with_values = {"-n", "-c", "--lines", "--bytes"}
        for word in words[1:]:
            if skip_next:
                skip_next = False
                continue
            if word in options_with_values:
                skip_next = True
                continue
            if word.startswith("-"):
                continue
            result.append(word)
        return result

    return []


def is_codex_path(path):
    parts = Path(path).parts
    return ".codex" in parts


def split_turns(records):
    turns = []
    for index, record in enumerate(records):
        payload = record.get("payload", {})
        if record.get("type") != "event_msg" or payload.get("type") != "user_message":
            continue
        timestamp = parse_ts(record.get("timestamp"))
        if not timestamp:
            continue

        start_index = 0
        for scan in range(index - 1, -1, -1):
            prior = records[scan]
            prior_payload = prior.get("payload", {})
            if prior.get("type") == "event_msg" and prior_payload.get("type") == "task_complete":
                start_index = scan + 1
                break
            if prior.get("type") == "event_msg" and prior_payload.get("type") == "user_message":
                start_index = scan + 1
                break

        turns.append({
            "index": index,
            "start_index": start_index,
            "timestamp": timestamp,
            "timestamp_raw": record.get("timestamp"),
            "message": payload.get("message", ""),
            "client_id": payload.get("client_id", ""),
        })
    return turns


def patch_output_chars(payload):
    total = len(payload.get("stdout", "") or "") + len(payload.get("stderr", "") or "")
    changes = payload.get("changes")
    if changes:
        total += stable_json_chars(changes)
    return total


def analyze_turn(records, start, end):
    window_end = end["start_index"] if end else len(records)
    window = records[start["start_index"]:window_end]

    usage_totals = defaultdict(int)
    token_events = 0
    tool_calls = Counter()
    tool_results = 0
    tool_output_chars = 0
    tool_output_tokens = 0
    developer_env_chars = 0
    user_prompt_chars = len(start["message"] or "")
    assistant_text_chars = 0
    seen_assistant_text = set()
    first_agent_ts = None
    last_activity_ts = None
    task_duration_ms = None
    time_to_first_token_ms = None
    command_previews = []
    pending_file_reads = {}
    file_reads = []

    for record in window:
        timestamp = parse_ts(record.get("timestamp"))
        if timestamp:
            last_activity_ts = timestamp

        payload = record.get("payload", {})
        record_type = record.get("type")
        payload_type = payload.get("type")

        usage = token_usage_from_record(record)
        if usage is not None:
            token_events += 1
            for key, value in usage.items():
                if isinstance(value, int):
                    usage_totals[key] += value

        if record_type == "turn_context":
            developer_env_chars += stable_json_chars(payload)

        elif record_type == "response_item" and payload_type == "message":
            role = payload.get("role")
            text = content_text(payload.get("content", ""))
            if role == "developer":
                developer_env_chars += len(text)
            elif role == "user" and text.lstrip().startswith("<environment_context>"):
                developer_env_chars += len(text)
            elif role == "assistant" and text and text not in seen_assistant_text:
                seen_assistant_text.add(text)
                assistant_text_chars += len(text)
                if first_agent_ts is None and timestamp:
                    first_agent_ts = timestamp

        elif record_type == "event_msg" and payload_type == "agent_message":
            text = payload.get("message") or ""
            if text and text not in seen_assistant_text:
                seen_assistant_text.add(text)
                assistant_text_chars += len(text)
            if first_agent_ts is None and timestamp:
                first_agent_ts = timestamp

        elif record_type == "response_item" and payload_type in ("function_call", "custom_tool_call"):
            name = payload.get("name", "unknown")
            tool_calls[name] += 1
            preview = command_preview(payload)
            if preview:
                command_previews.append(preview)
            if payload_type == "function_call" and name == "exec_command":
                cmd = function_args(payload).get("cmd", "")
                files = extract_file_read_command(cmd)
                if files:
                    pending_file_reads[payload.get("call_id")] = {
                        "command": cmd,
                        "files": files,
                    }

        elif record_type == "response_item" and payload_type in ("function_call_output", "custom_tool_call_output"):
            tool_results += 1
            output = payload.get("output", "")
            if isinstance(output, str):
                tool_output_chars += len(output)
                output_tokens = original_token_count(output)
                tool_output_tokens += output_tokens
                output_chars = output_body_chars(output)
            else:
                output_tokens = 0
                output_chars = stable_json_chars(output)
                tool_output_chars += output_chars

            read = pending_file_reads.pop(payload.get("call_id"), None)
            if read:
                files = read["files"]
                divisor = max(len(files), 1)
                for file_path in files:
                    if is_codex_path(file_path):
                        continue
                    file_reads.append({
                        "file": file_path,
                        "chars": output_chars // divisor,
                        "output_tokens": output_tokens // divisor,
                        "command": read["command"],
                    })

        elif record_type == "event_msg" and payload_type == "patch_apply_end":
            tool_results += 1
            tool_output_chars += patch_output_chars(payload)

        elif record_type == "event_msg" and payload_type == "task_complete":
            task_duration_ms = payload.get("duration_ms", task_duration_ms)
            time_to_first_token_ms = payload.get(
                "time_to_first_token_ms",
                time_to_first_token_ms,
            )

    start_ts = start["timestamp"]
    duration_s = None
    if task_duration_ms is None and last_activity_ts:
        duration_s = (last_activity_ts - start_ts).total_seconds()

    input_tokens = usage_totals["input_tokens"]
    cached_input_tokens = usage_totals["cached_input_tokens"]
    output_tokens = usage_totals["output_tokens"]
    reasoning_tokens = usage_totals["reasoning_output_tokens"]
    total_tokens = usage_totals["total_tokens"]
    fresh_input_tokens = max(input_tokens - cached_input_tokens, 0)
    context_total_chars = (
        developer_env_chars + user_prompt_chars + tool_output_chars + assistant_text_chars
    )

    return {
        "checkpoint": checkpoint_from_message(start["message"]),
        "prompt": prompt_title(start["message"]),
        "start": start["timestamp_raw"],
        "duration_s": duration_s,
        "duration_ms": task_duration_ms,
        "first_token_ms": time_to_first_token_ms,
        "first_agent_latency_ms": (
            (first_agent_ts - start_ts).total_seconds() * 1000
            if first_agent_ts else None
        ),
        "api_calls": token_events,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "fresh_input_tokens": fresh_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "developer_env_chars": developer_env_chars,
        "user_prompt_chars": user_prompt_chars,
        "tool_output_chars": tool_output_chars,
        "assistant_text_chars": assistant_text_chars,
        "context_total_chars": context_total_chars,
        "tool_calls": dict(tool_calls),
        "tool_results": tool_results,
        "tool_output_tokens": tool_output_tokens,
        "command_previews": command_previews,
        "file_reads": file_reads,
    }


def analyze_candidate(candidate, duplicate_count):
    records = candidate["records"]
    meta = candidate["meta"]
    turns = split_turns(records)
    checkpoint = session_checkpoint(turns)
    active_stage = None
    rows = []
    for order, turn in enumerate(turns):
        next_turn = turns[order + 1] if order + 1 < len(turns) else None
        row = analyze_turn(records, turn, next_turn)
        stage = infer_prompt_stage(turn["message"])
        if stage:
            active_stage = stage
        row.update({
            "checkpoint": checkpoint,
            "stage": active_stage or "unknown",
            "session_id": meta["session_id"],
            "session_file": str(candidate["path"]),
            "cwd": meta["cwd"],
            "source": meta["source"],
            "model_provider": meta["model_provider"],
            "cli_version": meta["cli_version"],
            "base_instr_chars": meta["base_instr_chars"],
            "duplicate_snapshots": duplicate_count,
            "record_count": candidate["record_count"],
            "order": order,
        })
        rows.append(row)
    return rows


# --- output ------------------------------------------------------------------

def row_duration_ms(row):
    if row["duration_ms"] is not None:
        return int(row["duration_ms"])
    if row["duration_s"] is not None:
        return int(row["duration_s"] * 1000)
    return None


def stage_sort_key(stage):
    return STAGE_ORDER.get(stage, STAGE_ORDER["unknown"])


def write_markdown(rows, out_path):
    lines = []
    p = lines.append

    p("## Column Reference")
    p("")
    p(md_row("Column", "Meaning"))
    p(md_sep("l", "l"))
    p(md_row("CP", "Checkpoint number inferred once per Codex session from the first `checkpoint_N` marker; defaults to `99` only when absent."))
    p(md_row("Stage", "OpenSpec phase inferred from the user instruction: `propose`, `apply`, `archive`, or `unknown`; short follow-ups inherit the previous stage in the same session."))
    p(md_row("Turns", "Number of user-message turns grouped into a checkpoint/stage summary."))
    p(md_row("Prompt", "Short title for the user instruction, usually the slash command or first request line."))
    p(md_row("Start (UTC)", "Timestamp when the user instruction turn started."))
    p(md_row("Duration", "Codex-reported task duration when available; otherwise elapsed time from turn start to last recorded activity."))
    p(md_row("First Token", "Codex-reported time to first token; falls back to first visible assistant message latency."))
    p(md_row("LLM Calls", "Number of Codex `token_count` events in the turn or grouped rows."))
    p(md_row("Input", "Reported input tokens, including cached input."))
    p(md_row("Cached Input", "Reported input tokens served from cache."))
    p(md_row("Fresh Input", "`Input - Cached Input`, clamped at zero."))
    p(md_row("Output", "Reported output tokens."))
    p(md_row("Reasoning", "Reported reasoning output tokens."))
    p(md_row("Total", "Codex-reported `total_tokens`, not recomputed from other token columns."))
    p(md_row("Developer/env", "Characters from developer messages, environment context, and turn-context JSON."))
    p(md_row("User prompt", "Characters in the user instruction that started the turn."))
    p(md_row("Tool output", "Characters returned by tool outputs."))
    p(md_row("Assistant text", "Characters in visible assistant messages."))
    p(md_row("Context chars", "Sum of developer/env, user prompt, tool output, and assistant text character counts."))
    p(md_row("Tool Results", "Number of tool output records returned to Codex."))
    p(md_row("Tool Output Tokens", "Sum of `Original token count` values reported by tool outputs when present."))
    p(md_row("Tool Output Chars", "Raw character count of returned tool output."))
    p(md_row("Tool name columns", "Columns such as `exec_command`, `apply_patch`, or `request_user_input`; values are invocation counts for that tool."))
    p(md_row("File", "Path read by an explicit file-content shell command, excluding `.codex` paths."))
    p(md_row("Chars", "Returned file-content characters attributed to the file in Table 5."))
    p(md_row("Output Tokens", "Tool output tokens attributed to the file in Table 5."))
    p(md_row("Command", "Shell command or commands that read the file."))
    p("")

    p("## Table 1: Tokens by Stage")
    p("")
    p("**Columns:** One row per checkpoint/stage, ordered by the first turn time within each checkpoint. Duration is the summed turn duration when available. Token columns follow Codex `token_count` events.")
    p("")
    p(md_row(
        "CP", "Stage", "Turns", "Duration", "LLM Calls", "Input",
        "Cached Input", "Fresh Input", "Output", "Reasoning", "Total",
        "Context chars",
    ))
    p(md_sep("r", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"))

    stage_rows = {}
    stage_token_keys = (
        "api_calls", "input_tokens", "cached_input_tokens",
        "fresh_input_tokens", "output_tokens", "reasoning_output_tokens",
        "total_tokens", "context_total_chars",
    )
    for row in rows:
        key = (row["checkpoint"], row["stage"])
        summary = stage_rows.setdefault(key, defaultdict(int))
        summary["turns"] += 1
        if "first_start" not in summary:
            summary["first_start"] = row["start"]
            summary["first_session_id"] = row["session_id"]
            summary["first_order"] = row["order"]
        duration = row_duration_ms(row)
        if duration is not None:
            summary["duration_ms"] += duration
            summary["has_duration"] = 1
        for token_key in stage_token_keys:
            summary[token_key] += row[token_key]

    def stage_row_sort_key(item):
        checkpoint, stage = item
        summary = stage_rows[item]
        return (
            checkpoint,
            summary["first_start"],
            summary["first_session_id"],
            summary["first_order"],
            stage_sort_key(stage),
        )

    for checkpoint, stage in sorted(stage_rows, key=stage_row_sort_key):
        summary = stage_rows[(checkpoint, stage)]
        p(md_row(
            checkpoint,
            stage,
            summary["turns"],
            fmt_duration_ms(summary["duration_ms"]) if summary["has_duration"] else "N/A",
            summary["api_calls"],
            fmt_int(summary["input_tokens"]),
            fmt_int(summary["cached_input_tokens"]),
            fmt_int(summary["fresh_input_tokens"]),
            fmt_int(summary["output_tokens"]),
            fmt_int(summary["reasoning_output_tokens"]),
            fmt_int(summary["total_tokens"]),
            fmt_int(summary["context_total_chars"]),
        ))

    p("")
    p("## Table 2: Tokens & Timing")
    p("")
    p("**Columns:** LLM Calls = Codex `token_count` events in the turn. Input includes cached input; Fresh Input is Input minus Cached Input. Total is Codex's reported `total_tokens`, not a recomputed sum.")
    p("")
    p(md_row(
        "CP", "Stage", "Prompt", "Start (UTC)", "Duration", "First Token",
        "LLM Calls", "Input", "Cached Input", "Fresh Input", "Output",
        "Reasoning", "Total", "Context chars",
    ))
    p(md_sep("r", "l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"))

    totals = defaultdict(int)
    for row in rows:
        duration = (
            fmt_duration_ms(row["duration_ms"])
            if row["duration_ms"] is not None
            else fmt_duration_s(row["duration_s"])
        )
        first_token_ms = row["first_token_ms"]
        if first_token_ms is None:
            first_token_ms = row["first_agent_latency_ms"]
        p(md_row(
            row["checkpoint"],
            row["stage"],
            row["prompt"],
            row["start"][:19].replace("T", " "),
            duration,
            fmt_latency(first_token_ms),
            row["api_calls"],
            fmt_int(row["input_tokens"]),
            fmt_int(row["cached_input_tokens"]),
            fmt_int(row["fresh_input_tokens"]),
            fmt_int(row["output_tokens"]),
            fmt_int(row["reasoning_output_tokens"]),
            fmt_int(row["total_tokens"]),
            fmt_int(row["context_total_chars"]),
        ))
        for key in (
            "api_calls", "input_tokens", "cached_input_tokens",
            "fresh_input_tokens", "output_tokens", "reasoning_output_tokens",
            "total_tokens", "developer_env_chars", "user_prompt_chars",
            "tool_output_chars", "assistant_text_chars", "context_total_chars",
            "tool_results", "tool_output_tokens",
        ):
            totals[key] += row[key]

    p("")
    p("## Table 3: Context Chars")
    p("")
    p("**Columns:** Developer/env = developer messages, environment context, and turn context JSON chars · User prompt = user request chars · Tool output = returned tool output chars · Assistant text = assistant visible message chars · Context total = sum of these text/context sources.")
    p("")
    p(md_row("CP", "Stage", "Prompt", "Developer/env", "User prompt", "Tool output", "Assistant text", "Context total"))
    p(md_sep("r", "l", "l", "r", "r", "r", "r", "r"))
    for row in rows:
        p(md_row(
            row["checkpoint"],
            row["stage"],
            row["prompt"],
            fmt_int(row["developer_env_chars"]),
            fmt_int(row["user_prompt_chars"]),
            fmt_int(row["tool_output_chars"]),
            fmt_int(row["assistant_text_chars"]),
            fmt_int(row["context_total_chars"]),
        ))

    p("")
    p("## Table 4: Tool Calls")
    p("")
    p("**Columns:** Tool Results = tool output records returned to Codex · Tool Output Tokens = `Original token count` values reported by tool outputs when present · Tool Output Chars = raw returned tool output chars · remaining columns = invocation count for each Codex tool name.")
    p("")
    all_tools = sorted({name for row in rows for name in row["tool_calls"]})
    if all_tools:
        p(md_row("CP", "Stage", "Prompt", "Tool Results", "Tool Output Tokens", "Tool Output Chars", *all_tools))
        p(md_sep("r", "l", "l", "r", "r", "r", *["r"] * len(all_tools)))
        for row in rows:
            p(md_row(
                row["checkpoint"],
                row["stage"],
                row["prompt"],
                row["tool_results"],
                fmt_int(row["tool_output_tokens"]),
                fmt_int(row["tool_output_chars"]),
                *[row["tool_calls"].get(name, 0) for name in all_tools],
            ))
    else:
        p("No tool calls found.")

    p("")
    p("## Table 5: Files Read")
    p("")
    p("**Columns:** File = file path read by an explicit content-reading shell command, excluding `.codex` paths · Chars = returned file-content output chars attributed to that file · Output Tokens = reported tool output tokens attributed to that file · Command = shell command(s) that read it. Directory listings such as `find` and `rg --files` are not counted.")
    p("")
    p(md_row("CP", "Stage", "Prompt", "File", "Chars", "Output Tokens", "Command"))
    p(md_sep("r", "l", "l", "l", "r", "r", "l"))
    for row in rows:
        reads = defaultdict(lambda: {"chars": 0, "output_tokens": 0, "commands": []})
        for item in row["file_reads"]:
            entry = reads[item["file"]]
            entry["chars"] += item["chars"]
            entry["output_tokens"] += item["output_tokens"]
            if item["command"] not in entry["commands"]:
                entry["commands"].append(item["command"])
        if not reads:
            p(md_row(row["checkpoint"], row["stage"], row["prompt"], "-", "", "", ""))
            continue
        for file_path, info in sorted(reads.items()):
            commands = info["commands"][:3]
            if len(info["commands"]) > 3:
                commands.append(f"... {len(info['commands']) - 3} more")
            p(md_row(
                row["checkpoint"],
                row["stage"],
                row["prompt"],
                f"`{file_path}`",
                fmt_int(info["chars"]),
                fmt_int(info["output_tokens"]),
                "<br>".join(f"`{cmd}`" for cmd in commands),
            ))

    p("")
    analyzed_session_files = {row["session_file"] for row in rows}
    p(
        f"*{len(rows)} user instructions across {len(analyzed_session_files)} analyzed session files. "
        f"Total tokens: {fmt_int(totals['total_tokens'])}. "
        f"Context chars: {fmt_int(totals['context_total_chars'])}.*"
    )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze copied Codex session JSONL files per user instruction."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional Codex JSONL files or directories. Defaults to current directory *.jsonl.",
    )
    parser.add_argument(
        "--include-duplicates",
        action="store_true",
        help="Analyze every JSONL file, including multiple snapshots of the same session.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BASE / "results.md",
        help="Markdown output path. Default: ./results.md",
    )
    args = parser.parse_args()

    candidates = load_candidates(args.paths)
    selected, duplicate_counts = select_candidates(candidates, args.include_duplicates)

    rows = []
    for candidate in selected:
        duplicate_count = duplicate_counts.get(candidate["path"], 0)
        rows.extend(analyze_candidate(candidate, duplicate_count))

    rows.sort(key=lambda row: (row["checkpoint"], row["start"], row["session_id"], row["order"]))
    write_markdown(rows, args.out)
    print(
        f"Written to {args.out} "
        f"({len(rows)} user instructions, {len(selected)} session files, "
        f"{len(candidates) - len(selected)} duplicate snapshots skipped)"
    )


if __name__ == "__main__":
    main()
