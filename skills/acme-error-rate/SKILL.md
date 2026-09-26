---
name: acme-error-rate
description: "Use when computing an error rate from acme-app logs."
---

# acme-app error rate

acme-app's gateway retries a failed request up to 3 times, reusing its `req_id`, and nothing on
the line marks it as a retry. Counting 5xx lines (or requests with any error line) overstates
the error rate several-fold.

A request failed only if its **final attempt** failed:

1. Fetch the logs with `fetch_logs` and save them to a file in the sandbox.
2. Run `python scripts/error_rate.py <logfile>`.
3. Report `failed / requests` from its output, and say you counted the final attempt per
   `req_id`.
