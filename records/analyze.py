#!/usr/bin/env python3
"""
Analyze Claude Code session recordings.
Produces per-query statistics sorted by checkpoint order.
"""

import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent


# ── helpers ──────────────────────────────────────────────────────────────────

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_ts(ts):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt_duration(seconds):
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def fmt_latency(ms):
    if ms is None:
        return "N/A"
    if ms >= 1000:
        return f"{ms/1000:.1f}s"
    return f"{ms:.0f}ms"


# ── core parsing ─────────────────────────────────────────────────────────────

def get_unique_llm_calls(records):
    """
    Return deduplicated LLM calls. Each real API call produces a chain of
    assistant records (streaming artifacts); keep only the first in each chain
    (the one whose parent is NOT another assistant record).
    """
    by_uuid = {r["uuid"]: r for r in records if r.get("uuid")}
    calls = []
    for r in records:
        if r.get("type") != "assistant":
            continue
        parent = by_uuid.get(r.get("parentUuid"))
        if parent and parent.get("type") == "assistant":
            continue  # streaming duplicate
        calls.append(r)
    return calls


def collect_tool_names(records):
    """Count tool_use names from assistant content."""
    counts = defaultdict(int)
    for r in records:
        if r.get("type") != "assistant":
            continue
        for item in r.get("message", {}).get("content", []):
            if isinstance(item, dict) and item.get("type") == "tool_use":
                counts[item.get("name", "unknown")] += 1
    return counts


def count_tool_results(records):
    """Count tool_result items inside user messages."""
    total = 0
    for r in records:
        if r.get("type") != "user":
            continue
        content = r.get("message", {}).get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    total += 1
    return total


def compute_metrics(calls, all_records, window_start, window_end):
    """
    Given a list of deduplicated LLM call records and all records in the window,
    compute aggregated statistics.
    """
    by_uuid = {r["uuid"]: r for r in all_records if r.get("uuid")}

    # filter calls to this window
    window_calls = []
    for c in calls:
        ts = parse_ts(c.get("timestamp"))
        if ts and window_start <= ts < window_end:
            window_calls.append(c)

    # filter all_records to window
    window_records = []
    for r in all_records:
        ts = parse_ts(r.get("timestamp"))
        if ts and window_start <= ts < window_end:
            window_records.append(r)

    # tokens
    input_tokens = 0
    cache_create_1h = 0
    cache_create_5m = 0
    cache_read = 0
    output_tokens = 0

    # call metadata
    stop_tool_use = 0
    stop_end_turn = 0
    thinking_calls = 0
    skill_calls = defaultdict(int)
    skill_output = defaultdict(int)

    # latency
    latencies_ms = []

    for c in window_calls:
        usage = c.get("message", {}).get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        cc = usage.get("cache_creation", {})
        cache_create_1h += cc.get("ephemeral_1h_input_tokens", 0)
        cache_create_5m += cc.get("ephemeral_5m_input_tokens", 0)
        cache_read += usage.get("cache_read_input_tokens", 0)
        out = usage.get("output_tokens", 0)
        output_tokens += out

        stop_reason = c.get("message", {}).get("stop_reason", "")
        if stop_reason == "tool_use":
            stop_tool_use += 1
        elif stop_reason == "end_turn":
            stop_end_turn += 1

        content = c.get("message", {}).get("content", [])
        if any(isinstance(x, dict) and x.get("type") == "thinking" for x in content):
            thinking_calls += 1

        skill = c.get("attributionSkill", "none")
        skill_calls[skill] += 1
        skill_output[skill] += out

        # latency: time from parent to this call
        parent = by_uuid.get(c.get("parentUuid"))
        if parent and parent.get("timestamp") and c.get("timestamp"):
            t_parent = parse_ts(parent.get("timestamp"))
            t_self = parse_ts(c.get("timestamp"))
            if t_parent and t_self:
                latencies_ms.append((t_self - t_parent).total_seconds() * 1000)

    total_tokens = input_tokens + cache_create_1h + cache_create_5m + cache_read + output_tokens
    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else None

    # tool calls from all records in window
    tool_names = collect_tool_names(window_records)
    tool_results = count_tool_results(window_records)

    return {
        "llm_calls": len(window_calls),
        "input_tokens": input_tokens,
        "cache_create_1h": cache_create_1h,
        "cache_create_5m": cache_create_5m,
        "cache_read": cache_read,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "stop_tool_use": stop_tool_use,
        "stop_end_turn": stop_end_turn,
        "thinking_calls": thinking_calls,
        "skill_calls": dict(skill_calls),
        "skill_output": dict(skill_output),
        "avg_latency_ms": avg_latency,
        "tool_names": dict(tool_names),
        "tool_results": tool_results,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # 1. load all session files
    session_files = sorted(BASE.glob("*.jsonl"))
    subagent_files = sorted(BASE.rglob("subagents/agent-*.jsonl"))

    # 2. load subagent records keyed by parent session id
    subagent_by_session = defaultdict(list)
    for sf in subagent_files:
        session_id = sf.parts[-3]  # grandparent dir = session id
        records = load_jsonl(sf)
        subagent_by_session[session_id].extend(records)

    rows = []

    for session_file in session_files:
        records = load_jsonl(session_file)
        session_id = session_file.stem

        # build uuid index
        by_uuid = {r["uuid"]: r for r in records if r.get("uuid")}

        # find queries
        queries = []
        for r in records:
            if r.get("type") != "user":
                continue
            content = r.get("message", {}).get("content", "")
            if not isinstance(content, str):
                continue
            if "<command-name>" not in content:
                continue
            cmd_m = re.search(r"<command-name>(.*?)</command-name>", content)
            args_m = re.search(r"<command-args>(.*?)</command-args>", content)
            queries.append({
                "uuid": r.get("uuid"),
                "timestamp": r.get("timestamp"),
                "command": cmd_m.group(1).strip() if cmd_m else "",
                "args": args_m.group(1).strip() if args_m else "",
            })

        if not queries:
            continue

        # determine checkpoint number from propose args
        checkpoint_num = None
        for q in queries:
            m = re.search(r"checkpoint_(\d+)", q["args"])
            if m:
                checkpoint_num = int(m.group(1))
                break
        if checkpoint_num is None:
            checkpoint_num = 99  # fallback

        # deduplicated calls for main session
        main_calls = get_unique_llm_calls(records)

        # deduplicated calls for subagents of this session
        sub_records = subagent_by_session.get(session_id, [])
        sub_calls = get_unique_llm_calls(sub_records) if sub_records else []

        # all records combined for tool counting
        all_records = records + sub_records
        all_calls = main_calls + sub_calls

        # timestamps for window bounds
        INF = datetime(9999, 1, 1, tzinfo=timezone.utc)

        for i, q in enumerate(queries):
            q_start = parse_ts(q["timestamp"])
            q_end = parse_ts(queries[i + 1]["timestamp"]) if i + 1 < len(queries) else INF

            metrics = compute_metrics(all_calls, all_records, q_start, q_end)

            # wall-clock: last assistant record in window
            last_ts = None
            for r in all_records:
                if r.get("type") == "assistant":
                    ts = parse_ts(r.get("timestamp"))
                    if ts and q_start <= ts < q_end:
                        if last_ts is None or ts > last_ts:
                            last_ts = ts

            duration_s = (last_ts - q_start).total_seconds() if last_ts else None

            rows.append({
                "checkpoint": checkpoint_num,
                "order": i,
                "command": q["command"],
                "start": q["timestamp"],
                "duration_s": duration_s,
                **metrics,
            })

    # sort by checkpoint then command order
    rows.sort(key=lambda r: (r["checkpoint"], r["order"]))

    # ── output ────────────────────────────────────────────────────────────────

    lines = []
    p = lines.append

    def md_row(*cells):
        return "| " + " | ".join(str(c) for c in cells) + " |"

    def md_sep(*alignments):
        # l=left, r=right, c=center
        parts = []
        for a in alignments:
            if a == "r":
                parts.append("---:")
            elif a == "c":
                parts.append(":---:")
            else:
                parts.append("---")
        return "| " + " | ".join(parts) + " |"

    # ── Table 1: tokens + timing
    p("## Table 1: Tokens & Timing")
    p("")
    p(md_row("CP", "Command", "Start (UTC)", "Duration", "LLM Calls",
             "Input", "CC-1h", "CC-5m", "Cache Read", "Output", "Total"))
    p(md_sep("r", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r"))

    session_totals = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cp = r["checkpoint"]
        p(md_row(
            cp, r["command"], r["start"][:19].replace("T", " "),
            fmt_duration(r["duration_s"]), r["llm_calls"],
            r["input_tokens"], r["cache_create_1h"], r["cache_create_5m"],
            r["cache_read"], r["output_tokens"], r["total_tokens"],
        ))
        for k in ("llm_calls", "input_tokens", "cache_create_1h", "cache_create_5m",
                  "cache_read", "output_tokens", "total_tokens"):
            session_totals[cp][k] += r[k]

    p("")
    p("**Per-checkpoint totals:**")
    p("")
    p(md_row("CP", "LLM Calls", "Input", "CC-1h", "CC-5m", "Cache Read", "Output", "Total"))
    p(md_sep("r", "r", "r", "r", "r", "r", "r", "r"))
    for cp in sorted(session_totals.keys()):
        t = session_totals[cp]
        p(md_row(
            f"**{cp}**", t["llm_calls"], t["input_tokens"],
            t["cache_create_1h"], t["cache_create_5m"],
            t["cache_read"], t["output_tokens"], t["total_tokens"],
        ))

    # ── Table 2: LLM call breakdown + latency
    p("")
    p("## Table 2: LLM Call Breakdown & Latency")
    p("")
    p(md_row("CP", "Command", "LLM Calls", "Tool-use stops", "End-turn stops", "Thinking calls", "Avg Latency"))
    p(md_sep("r", "l", "r", "r", "r", "r", "r"))
    for r in rows:
        p(md_row(
            r["checkpoint"], r["command"], r["llm_calls"],
            r["stop_tool_use"], r["stop_end_turn"],
            r["thinking_calls"], fmt_latency(r["avg_latency_ms"]),
        ))

    # ── Table 3: Skill attribution
    p("")
    p("## Table 3: Skill Attribution")
    p("")
    all_skills = sorted({s for r in rows for s in r["skill_calls"].keys()})
    skill_hdrs = [f"{s} calls" for s in all_skills] + [f"{s} output" for s in all_skills]
    p(md_row("CP", "Command", *skill_hdrs))
    p(md_sep("r", "l", *["r"] * len(skill_hdrs)))
    for r in rows:
        skill_vals = [r["skill_calls"].get(s, 0) for s in all_skills]
        skill_outs = [r["skill_output"].get(s, 0) for s in all_skills]
        p(md_row(r["checkpoint"], r["command"], *skill_vals, *skill_outs))

    # ── Table 4: Tool execution breakdown
    p("")
    p("## Table 4: Tool Executions")
    p("")
    tool_order = ["Bash", "Edit", "Write", "Read", "TodoWrite", "Agent"]
    p(md_row("CP", "Command", "Tool Results", *tool_order, "Other"))
    p(md_sep("r", "l", *["r"] * (len(tool_order) + 2)))
    for r in rows:
        tn = r["tool_names"]
        other = sum(v for k, v in tn.items() if k not in tool_order)
        p(md_row(
            r["checkpoint"], r["command"], r["tool_results"],
            *[tn.get(t, 0) for t in tool_order],
            other,
        ))

    p("")
    p(f"*{len(rows)} queries across {len(session_totals)} checkpoints*")

    md = "\n".join(lines) + "\n"
    out_path = BASE / "results.md"
    with open(out_path, "w") as f:
        f.write(md)
    print(f"Written to {out_path} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
