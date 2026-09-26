---
name: checkout-request-error-rate
description: "Read before computing checkout-api error rate from raw logs: retries reuse req_id, so naive per-line 5xx counts can vastly overstate user-visible errors."
---

# Compute checkout-api error rate by final req_id status, not raw log lines

Use this when asked to compute `checkout-api` (or similarly retried service) error rate from raw application logs that contain `req_id=` and `status=` fields.

## Trap

Do **not** treat every raw log line as a distinct request. For `checkout-api`, retries can reuse the same `req_id`: intermediate upstream failures may appear as `500`, `502`, or `503` log lines, followed later by a successful final `200` for the same checkout request. Counting every log line produces an inflated attempt/log-line error rate.

## Correct method

1. Fetch the raw logs for the requested service and time window.
2. Parse each log line for:
   - `req_id=<id>`
   - `status=<3-digit HTTP status>`
3. Preserve log order. If the logs are oldest-first, the final status for a request is the last status seen for that `req_id`. If the source returns newest-first, reverse the lines or otherwise confirm ordering before taking the final status.
4. Count exactly one result per unique `req_id`, using that request's final status.
5. Compute the user-visible request error rate as:

   ```text
   final_5xx_requests / unique_req_ids * 100
   ```

6. In the answer, report enough checks to distinguish request-level from line-level counting:
   - raw log lines parsed
   - unique `req_id` count
   - final status counts by request
   - final 5xx request count and rate
   - optionally, line-level 5xx rate only as a diagnostic, clearly labeled as attempt/log-line-level

## Sanity checks

- If the line-level 5xx rate is surprisingly high but pages/alerts do not match it, inspect repeated `req_id`s before answering.
- Show an example repeated `req_id` only if needed to justify the method, and avoid exposing sensitive or unnecessary identifiers.
- If some lines lack `req_id` or `status`, report the parse gap and do not silently mix parsed and unparsed lines into the denominator.

## Helper script

The included `scripts/request_error_rate.py` reads log lines from standard input and computes final-status error rate by `req_id`. Use it after fetching logs, for example:

```bash
python scripts/request_error_rate.py < checkout.log
```

If you need to fetch logs through an MCP tool, write the tool result to a file or pipe only the raw log text into this helper; do not paste large raw logs into the final answer.
