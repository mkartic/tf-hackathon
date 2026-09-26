import re

import pytest

from tf_hackathon.acme_app import logs


def test_render_is_deterministic():
    assert logs.render("checkout-api", "1h") == logs.render("checkout-api", "1h")


@pytest.mark.parametrize("service", sorted(logs.SERVICES))
def test_naive_count_overstates_error_rate(service):
    s = logs.stats(service, "6h")
    assert s.naive_error_rate > 3 * s.error_rate


def test_stats_match_rendered_log():
    text = logs.render("checkout-api", "6h")
    lines = text.splitlines()
    s = logs.stats("checkout-api", "6h")

    assert len(lines) == s.attempts
    assert sum(" status=5" in line for line in lines) == s.failed_attempts

    final_status = {}
    for line in lines:  # lines are time-ordered, so the last one per request wins
        req_id = re.search(r"req_id=(\w+)", line)[1]
        final_status[req_id] = int(re.search(r"status=(\d+)", line)[1])
    assert len(final_status) == s.requests
    assert sum(code >= 500 for code in final_status.values()) == s.failed_requests


def test_retries_reuse_request_id():
    text = logs.render("checkout-api", "1h")
    ids = re.findall(r"req_id=(\w+)", text)
    assert len(ids) > len(set(ids))
