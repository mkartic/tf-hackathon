#!/usr/bin/env python3
"""Compute request-level HTTP error rate from logs with req_id= and status= fields.

The script treats the final status seen for each req_id as that request's result.
Input is read from stdin. Logs must be ordered oldest-first; pass --newest-first if
input is newest-first.
"""
import argparse
import re
import sys
from collections import Counter

REQ_RE = re.compile(r"\breq_id=([^\s]+)")
STATUS_RE = re.compile(r"\bstatus[=:](\d{3})\b", re.IGNORECASE)


def parse_line(line: str):
    req = REQ_RE.search(line)
    status = STATUS_RE.search(line)
    if not req or not status:
        return None
    return req.group(1), int(status.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--newest-first", action="store_true", help="reverse input before computing final status")
    args = parser.parse_args()

    lines = sys.stdin.read().splitlines()
    ordered = list(reversed(lines)) if args.newest_first else lines

    final_status_by_req = {}
    line_status_counts = Counter()
    parsed = 0
    unparsed = 0
    occurrences = Counter()

    for line in ordered:
        parsed_pair = parse_line(line)
        if parsed_pair is None:
            unparsed += 1
            continue
        req_id, status = parsed_pair
        parsed += 1
        line_status_counts[status] += 1
        occurrences[req_id] += 1
        final_status_by_req[req_id] = status

    final_counts = Counter(final_status_by_req.values())
    unique_requests = len(final_status_by_req)
    final_5xx = sum(count for status, count in final_counts.items() if 500 <= status <= 599)
    line_5xx = sum(count for status, count in line_status_counts.items() if 500 <= status <= 599)
    repeated_req_ids = sum(1 for count in occurrences.values() if count > 1)

    def pct(n, d):
        return 0.0 if d == 0 else n / d * 100

    print(f"raw_log_lines={len(lines)}")
    print(f"parsed_status_lines={parsed}")
    print(f"unparsed_lines={unparsed}")
    print(f"unique_req_ids={unique_requests}")
    print(f"req_ids_with_multiple_log_lines={repeated_req_ids}")
    print("line_status_counts=" + ", ".join(f"{k}:{v}" for k, v in sorted(line_status_counts.items())))
    print(f"line_level_5xx={line_5xx}")
    print(f"line_level_5xx_rate_pct={pct(line_5xx, parsed):.6f}")
    print("final_status_counts=" + ", ".join(f"{k}:{v}" for k, v in sorted(final_counts.items())))
    print(f"final_5xx_requests={final_5xx}")
    print(f"request_level_5xx_rate_pct={pct(final_5xx, unique_requests):.6f}")
    return 0 if unique_requests else 2


if __name__ == "__main__":
    raise SystemExit(main())
