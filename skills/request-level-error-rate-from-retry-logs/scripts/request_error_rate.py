#!/usr/bin/env python3
"""Compute line-level and request-level 5xx error rates from service logs.

Reads raw log lines from stdin. Parses explicit status fields and request IDs, then
collapses retries by request id to the final status.
"""
import argparse
import json
import re
import sys
from collections import Counter, OrderedDict

STATUS_PATTERNS = [
    re.compile(r'\bstatus[=: ]+(\d{3})\b', re.IGNORECASE),
    re.compile(r'"status"\s*:\s*(\d{3})'),
]
REQ_PATTERNS = [
    re.compile(r'\breq_id[=: ]+([A-Za-z0-9_.:-]+)\b'),
    re.compile(r'\brequest_id[=: ]+([A-Za-z0-9_.:-]+)\b'),
    re.compile(r'\btrace_id[=: ]+([A-Za-z0-9_.:-]+)\b'),
    re.compile(r'"(?:req_id|request_id|trace_id)"\s*:\s*"([^"]+)"'),
]

def parse_first(patterns, line):
    for pattern in patterns:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None

def pct(numerator, denominator):
    return 100.0 * numerator / denominator if denominator else 0.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--newest-first', action='store_true', help='raw logs are reverse chronological; first status per request id is final')
    parser.add_argument('--json', action='store_true', help='emit machine-readable JSON')
    args = parser.parse_args()

    lines = [line.rstrip('\n') for line in sys.stdin]
    line_statuses = []
    req_statuses = OrderedDict()
    missing_status = 0
    missing_req_id = 0

    for line in lines:
        status_s = parse_first(STATUS_PATTERNS, line)
        if status_s is None:
            missing_status += 1
            continue
        status = int(status_s)
        line_statuses.append(status)

        req_id = parse_first(REQ_PATTERNS, line)
        if req_id is None:
            missing_req_id += 1
            continue
        if args.newest_first:
            req_statuses.setdefault(req_id, status)
        else:
            req_statuses[req_id] = status

    line_counts = Counter(line_statuses)
    final_counts = Counter(req_statuses.values())
    line_5xx = sum(count for status, count in line_counts.items() if 500 <= status <= 599)
    final_5xx = sum(count for status, count in final_counts.items() if 500 <= status <= 599)
    repeated_req_ids = max(0, len(line_statuses) - missing_req_id - len(req_statuses))

    result = {
        'raw_log_lines': len(lines),
        'parsed_status_lines': len(line_statuses),
        'missing_status_lines': missing_status,
        'missing_request_id_lines_with_status': missing_req_id,
        'line_status_counts': dict(sorted(line_counts.items())),
        'line_5xx_errors': line_5xx,
        'line_5xx_rate_pct': pct(line_5xx, len(line_statuses)),
        'unique_request_ids': len(req_statuses),
        'extra_retry_or_duplicate_lines': repeated_req_ids,
        'final_status_counts': dict(sorted(final_counts.items())),
        'final_5xx_requests': final_5xx,
        'request_5xx_rate_pct': pct(final_5xx, len(req_statuses)),
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    for key, value in result.items():
        if isinstance(value, dict):
            value = ', '.join(f'{k}:{v}' for k, v in value.items())
        elif isinstance(value, float):
            value = f'{value:.6f}'
        print(f'{key}={value}')

if __name__ == '__main__':
    main()
