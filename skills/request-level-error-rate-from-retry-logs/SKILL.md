---
name: request-level-error-rate-from-retry-logs
description: "Read before computing service error rates from logs: retries can reuse req_id, so counting each log line can massively overstate user-visible errors."
---

# Compute request-level error rates from retrying service logs

Use this skill before answering an error-rate question from service request logs where a request identifier such as `req_id`, `request_id`, or `trace_id` may appear on multiple log lines.

## Trap

Do **not** assume each log line is one user-visible request. Some services log every retry attempt with the same request id. Intermediate attempts may have `500`, `502`, or `503` statuses and then a later successful final status for the same request. Counting every line can turn retry noise into a falsely high error rate.

## Method

1. Fetch the raw logs for the requested service and time window.
2. Parse an explicit HTTP status field only, for example `status=200`, `status: 200`, or JSON key `"status": 200`. Do not accidentally parse latency values such as `dur_ms=500` as statuses.
3. Parse a stable request identifier, usually `req_id=`. If no stable request id exists, say so and report that only a line/attempt-level rate can be computed.
4. Check whether request ids repeat. If they do, compute the user-visible request-level rate by taking one final status per request id. For logs sorted oldest-to-newest, this is the last status seen for each request id.
5. Count final statuses in the 5xx range as errors unless the user or system definition says to include other statuses.
6. Report both the corrected request-level result and enough diagnostics to show why it differs from line-level counting:
   - raw log lines parsed
   - line-level status counts and 5xx rate
   - unique request ids
   - repeated request ids
   - final-status counts by request id
   - final 5xx request count and rate
7. If the answer changed after a naive count, explicitly explain that the earlier number was attempt/log-line-level, not request-level.

## Sanity checks

- If the calculated error rate seems implausibly high, inspect sample raw lines for repeated request ids and retry chains before finalizing.
- Verify that status parsing requires a status field name. A regex for any three-digit number can mistake durations or timestamps for status codes.
- Verify log ordering. If the logs are newest-first, take the first status seen per request id as the final status, or sort by timestamp before reducing.

## Helper script

The included `scripts/request_error_rate.py` reads log lines from stdin and prints line-level and request-level diagnostics. Use it after fetching logs to a file:

```bash
python scripts/request_error_rate.py < logs.txt
```

By default it assumes logs are oldest-first and uses the last status for each request id. Use `--newest-first` if the raw logs are newest-first.
