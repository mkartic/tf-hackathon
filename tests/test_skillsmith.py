from tf_hackathon.skillsmith.server import parse_frontmatter, render_skill_md
from tf_hackathon.skillsmith.state import State
from tf_hackathon.skillsmith.trueforge import is_skillsmith_session, transcript, with_skill, without_skill


def test_skill_md_round_trips_awkward_description():
    md = render_skill_md("acme-error-rate", 'Use when: asked for "error rate"', "# Steps\n1. x")
    assert parse_frontmatter(md) == {
        "name": "acme-error-rate",
        "description": 'Use when: asked for "error rate"',
    }


def test_with_skill_attaches_once_and_enables_sandbox():
    manifest = {"model": {"name": "m"}, "skills": [{"name": "a"}]}
    once = with_skill(manifest, "b")
    assert once["skills"] == [{"name": "a"}, {"name": "b"}]
    assert once["config"]["sandbox"]["enabled"] is True
    assert with_skill(once, "b")["skills"] == once["skills"]
    assert without_skill(once, "a")["skills"] == [{"name": "b"}]


def test_skillsmith_sessions_are_recognised():
    assert is_skillsmith_session({"metadata": {"source": "skillsmith"}})
    assert not is_skillsmith_session({"metadata": None})


def test_transcript_orders_messages_and_clips_results():
    events = [
        {"type": "turn.created", "input": [{"type": "user.message", "content": "error rate?"}]},
        {"type": "model.message", "content": None, "tool_calls": [
            {"function": {"name": "fetch_logs", "arguments": '{"service":"checkout-api"}'}}]},
        {"type": "tool.response", "content": "x" * 50},
        {"type": "model.message", "content": "31%"},
    ]
    assert transcript(events, clip=10).splitlines() == [
        "USER: error rate?",
        'TOOL CALL fetch_logs: {"service"… [16 chars cut]',
        "TOOL RESULT: xxxxxxxxxx… [40 chars cut]",
        "AGENT: 31%",
    ]


def test_state_persists(tmp_path):
    path = tmp_path / "state.json"
    State(path).mark_processed(["s1"], "trivial")
    assert State(path).is_processed("s1")
