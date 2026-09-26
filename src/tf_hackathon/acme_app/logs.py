"""Deterministic acme-app request logs, with the retry trap baked in.

The gateway retries failed requests up to MAX_ATTEMPTS times, reusing the
request ID and logging nothing that marks a line as a retry. Counting
`status=5xx` lines therefore overstates the error rate; only each request's
final attempt decides whether it failed.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

LOG_END = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
MAX_ATTEMPTS = 3

WINDOWS = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24)}


@dataclass(frozen=True)
class Service:
    name: str
    requests_per_hour: int
    path: str
    method: str
    upstream: str
    first_fail: float  # chance the first attempt fails
    retry_fail: float  # chance each retry fails


SERVICES = {
    s.name: s
    for s in [
        Service("checkout-api", 250, "/v1/checkout", "POST", "payments-api", 0.30, 0.40),
        Service("inventory-api", 400, "/v1/stock", "GET", "inventory-db", 0.12, 0.25),
        Service("payments-api", 180, "/v1/charges", "POST", "card-network", 0.20, 0.35),
    ]
}

FAILURES = [
    (503, "upstream timeout"),
    (502, "bad gateway"),
    (500, "connection reset by peer"),
]


@dataclass(frozen=True)
class Attempt:
    at: datetime
    req_id: str
    status: int
    dur_ms: int
    err: str | None


@dataclass(frozen=True)
class Stats:
    requests: int
    failed_requests: int
    attempts: int
    failed_attempts: int

    @property
    def error_rate(self) -> float:
        """The correct answer: share of requests whose final attempt failed."""
        return self.failed_requests / self.requests

    @property
    def naive_error_rate(self) -> float:
        """The trap: share of status lines that are 5xx."""
        return self.failed_attempts / self.attempts


def _requests(service: Service, window: str) -> list[list[Attempt]]:
    rng = random.Random(f"{service.name}:{window}")
    span = WINDOWS[window]
    start = LOG_END - span
    count = round(service.requests_per_hour * span / timedelta(hours=1))
    requests = []
    for _ in range(count):
        at = start + timedelta(seconds=rng.uniform(0, span.total_seconds()))
        req_id = f"{rng.getrandbits(32):08x}"
        attempts = []
        for n in range(MAX_ATTEMPTS):
            fails = rng.random() < (service.first_fail if n == 0 else service.retry_fail)
            if fails:
                status, err = rng.choice(FAILURES)
                dur_ms = rng.randint(2000, 5000) if status == 503 else rng.randint(5, 80)
            else:
                status, err = 200, None
                dur_ms = rng.randint(40, 400)
            attempts.append(Attempt(at, req_id, status, dur_ms, err))
            if not fails:
                break
            backoff_ms = rng.randint(200, 800) * 2**n
            at += timedelta(milliseconds=dur_ms + backoff_ms)
        requests.append(attempts)
    return requests


def _format(service: Service, a: Attempt) -> str:
    level = "ERROR" if a.status >= 500 else "INFO"
    line = (
        f"{a.at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')} level={level} "
        f"svc={service.name} req_id={a.req_id} method={service.method} path={service.path} "
        f"status={a.status} dur_ms={a.dur_ms} upstream={service.upstream}"
    )
    return line + (f' err="{a.err}"' if a.err else "")


def render(service_name: str, window: str) -> str:
    """The log text for one service over one window, oldest line first."""
    service = SERVICES[service_name]
    attempts = sorted(
        (a for request in _requests(service, window) for a in request), key=lambda a: a.at
    )
    return "\n".join(_format(service, a) for a in attempts) + "\n"


def stats(service_name: str, window: str) -> Stats:
    """Ground truth for a service and window, used to judge answers."""
    requests = _requests(SERVICES[service_name], window)
    return Stats(
        requests=len(requests),
        failed_requests=sum(r[-1].status >= 500 for r in requests),
        attempts=sum(len(r) for r in requests),
        failed_attempts=sum(a.status >= 500 for r in requests for a in r),
    )
