import json
import subprocess
import sys
from pathlib import Path

import pytest

from tf_hackathon.skillsmith import scrub, server
from tf_hackathon.skillsmith.config import Config
from tf_hackathon.skillsmith.state import State

# Built by concatenation so the repo never contains a literal that looks like a real key.
FAKE_OPENAI_KEY = "sk-" + "proj-" + "Zq7Lm2Xv9Rt4Kp8Wn3Hy6Bc1Df5Gj0As"
FAKE_GITHUB_TOKEN = "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
FAKE_AWS_KEY = "AKIA" + "Q3EXAMPLE7KEYZZ9"

SKILL_DRAFT = f"""# Computing acme-app error rates

1. Fetch logs with `fetch_logs`.
2. If the API asks for a key, Alice used `OPENAI_API_KEY={FAKE_OPENAI_KEY}`.
3. Group attempts by `req_id`; only the final attempt counts.
Ping alice.nguyen@acme-corp.io if unsure.
"""


def test_fake_api_key_and_email_are_removed():
    text, findings = scrub.scrub_text(SKILL_DRAFT, "SKILL.md")
    assert FAKE_OPENAI_KEY not in text
    assert "alice.nguyen@acme-corp.io" not in text
    assert "[scrubbed:api-key]" in text
    assert "Group attempts by `req_id`; only the final attempt counts." in text
    assert [(f.kind, f.category, f.line) for f in findings] == [
        ("api-key", scrub.SECRET, 4),
        ("email", scrub.PERSONAL, 6),
    ]
    assert scrub.summary(findings) == "1 possible secret and 1 piece of personal data removed"


@pytest.mark.parametrize("secret, kind", [
    (FAKE_GITHUB_TOKEN, "github-token"),
    (FAKE_AWS_KEY, "aws-access-key"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "private-key"),
    ("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4fw", "jwt"),
    ("4111 1111 1111 1111", "card-number"),
    ("+1 415-555-0134", "phone"),
    ("203.0.113.77", "ip-address"),
])
def test_known_secret_shapes(secret, kind):
    text, findings = scrub.scrub_text(f"value: {secret} end")
    assert secret not in text
    assert [f.kind for f in findings] == [kind]


@pytest.mark.parametrize("line, removed", [
    ('password = "hunter2hunter2"', '"hunter2hunter2"'),
    ("curl -H 'Authorization: Bearer Tk9pZ3VhcmFudGVlZFNlY3JldA' ...", "Tk9pZ3VhcmFudGVlZFNlY3JldA"),
    ("postgres://ops:s3cr3tPass@db.internal:5432/app", "s3cr3tPass"),
    ("export TOKEN_X=Qm9vcFx0V9zRkq2LpX7aTe4Y", "Qm9vcFx0V9zRkq2LpX7aTe4Y"),
])
def test_labelled_and_high_entropy_values(line, removed):
    text, findings = scrub.scrub_text(line)
    assert removed not in text
    assert len(findings) == 1
    assert findings[0].kind != "email"


@pytest.mark.parametrize("line", [
    "api_key = os.environ['OPENAI_API_KEY']",
    "token: $GITHUB_TOKEN",
    "password = <your password>",
    "TOKEN = re.compile(r'[A-Za-z0-9_+/=-]{24,}')",
    "session 3f2b8c4e-9a1d-4e7b-8c2f-1a2b3c4d5e6f and commit 0bef897a1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f",
    "listen on 127.0.0.1:8802 or 10.0.0.4",
    "mail ops@example.com",
    "2026-09-25T14:00:12.868Z level=INFO svc=checkout-api req_id=773fcd1a status=200 dur_ms=349",
    "src/tf_hackathon/skillsmith/server.py::test_naive_count_overstates_error_rate",
])
def test_ordinary_skill_text_is_left_alone(line):
    assert scrub.scrub_text(line) == (line, [])


def test_scrub_is_idempotent_and_reports_earlier_markers():
    once, first = scrub.scrub_text(SKILL_DRAFT)
    twice, second = scrub.scrub_text(once)
    assert twice == once
    assert [(f.kind, f.category, f.earlier) for f in second] == [
        (f.kind, f.category, True) for f in first
    ]
    assert "(scrubbed before drafting)" in scrub.report_markdown(second)


def test_standalone_script_runs_without_the_package(tmp_path):
    # The sandbox gets only this file, so it must not import anything from tf_hackathon.
    script = tmp_path / "scrub.py"
    script.write_text(Path(scrub.__file__).read_text())
    draft = tmp_path / "SKILL.md"
    draft.write_text(SKILL_DRAFT)

    report = subprocess.run([sys.executable, "-I", script, draft], capture_output=True,
                            text=True, check=True)
    out = json.loads(report.stdout)
    assert out["summary"] == "1 possible secret and 1 piece of personal data removed"
    assert FAKE_OPENAI_KEY not in report.stdout
    assert draft.read_text() == SKILL_DRAFT  # report mode doesn't touch files

    subprocess.run([sys.executable, "-I", script, "--write", draft], capture_output=True,
                   check=True)
    assert FAKE_OPENAI_KEY not in draft.read_text()


class FakeGitHub:
    def __init__(self):
        self.commits, self.prs = [], []

    def commit_to_new_branch(self, branch, message, files):
        self.commits.append((branch, files))
        return "c0ffee"

    def open_pr(self, branch, title, body):
        self.prs.append({"branch": branch, "title": title, "body": body})
        return {"number": 7, "html_url": "https://github.com/o/r/pull/7"}

    def read_file(self, path, ref="main"):
        return None


@pytest.fixture
def fake_github(tmp_path, monkeypatch):
    gh = FakeGitHub()
    cfg = Config("http://tf", "tok", "o/r", "skills", ["acme-ops"], tmp_path / "state.json")
    monkeypatch.setattr(server, "_deps", lambda: (cfg, None, gh, State(cfg.state_path)))
    return gh


def test_proposal_from_session_with_fake_key_is_scrubbed_and_pr_says_so(fake_github):
    result = server.propose_skill(
        name="acme-error-rate",
        description="Use when asked for an acme-app error rate",
        instructions=SKILL_DRAFT,
        files={"scripts/error_rate.py": f'KEY = "{FAKE_OPENAI_KEY}"\n'},
        rationale=f"Alice pasted {FAKE_GITHUB_TOKEN} while debugging.",
        source_session_ids=["sess_1"],
    )

    (_, files), = fake_github.commits
    committed = "".join(files.values())
    body = fake_github.prs[0]["body"]
    for secret in (FAKE_OPENAI_KEY, FAKE_GITHUB_TOKEN, "alice.nguyen@acme-corp.io"):
        assert secret not in committed
        assert secret not in body
    assert set(files) == {"skills/acme-error-rate/SKILL.md",
                          "skills/acme-error-rate/scripts/error_rate.py"}
    assert result["scrub"] == "3 possible secrets and 1 piece of personal data removed"
    assert "### Scrub\n3 possible secrets and 1 piece of personal data removed." in body
    assert "- api-key (secret) at `scripts/error_rate.py` line 1" in body
    assert "- github-token (secret) at `PR description` line 1" in body


def test_clean_proposal_says_nothing_was_found(fake_github):
    server.propose_skill(
        name="acme-error-rate", description="Use when asked for an error rate",
        instructions="Count only the final attempt per req_id.", rationale="Saves a turn.",
        source_session_ids=[],
    )
    assert "### Scrub\nNo secrets or personal data found." in fake_github.prs[0]["body"]
