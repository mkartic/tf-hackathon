import itertools
import json
from pathlib import Path

import httpx
import pytest

from tf_hackathon import setup_trueforge
from tf_hackathon.setup_trueforge import load_agent, merge_manifest, setup
from tf_hackathon.skillsmith import server
from tf_hackathon.skillsmith.config import Config
from tf_hackathon.skillsmith.state import State
from tf_hackathon.skillsmith.trueforge import TrueForge

SPECS = Path(__file__).parent.parent / "trueforge"


class FakeTrueForgeServer:
    """The agent, schedule, connector and model endpoints the setup script uses."""

    def __init__(self, connectors=("acme-app", "skillsmith"), models=("openai/gpt-5.2",)):
        self.connectors, self.models = set(connectors), list(models)
        self.agents, self.schedules, self.runs = {}, {}, []
        self.ids = itertools.count(1)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else None
        match request.method, path.strip("/").split("/"):
            case "GET", ["mcp-servers", name]:
                return httpx.Response(200 if name in self.connectors else 404, json={})
            case "GET", ["models"]:
                return httpx.Response(200, json={"data": [{"name": m} for m in self.models]})
            case "GET", ["agents"]:
                q = request.url.params.get("agent_name", "")
                data = [a for a in self.agents.values() if q in a["name"]]
                return httpx.Response(200, json={"data": data, "pagination": {}})
            case "POST", ["agents"]:
                agent = body | {"id": f"agent_{next(self.ids)}"}
                self.agents[agent["id"]] = agent
                return httpx.Response(201, json={"data": agent})
            case "PUT", ["agents", agent_id]:
                self.agents[agent_id] |= body
                return httpx.Response(200, json={"data": self.agents[agent_id]})
            case "GET", ["schedules"]:
                names = request.url.params["agent_names"].split(",")
                data = [s for s in self.schedules.values() if s["agent_name"] in names]
                return httpx.Response(200, json={"data": data, "pagination": {}})
            case "POST", ["schedules"]:
                if not any(a["name"] == body["agent_name"] for a in self.agents.values()):
                    return httpx.Response(404, json={"error": {"message": "agent not found"}})
                schedule = body | {"id": f"sched_{next(self.ids)}"}
                self.schedules[schedule["id"]] = schedule
                return httpx.Response(201, json={"data": schedule})
            case "PUT", ["schedules", schedule_id]:
                self.schedules[schedule_id] |= body
                return httpx.Response(200, json={"data": self.schedules[schedule_id]})
            case "POST", ["schedules", "runs"]:
                self.runs.append(body["schedule_id"])
                return httpx.Response(201, json={"data": {"id": f"run_{len(self.runs)}"}})
        return httpx.Response(404, json={"error": {"message": f"{request.method} {path}"}})

    def agent(self, name):
        return next(a for a in self.agents.values() if a["name"] == name)


@pytest.fixture
def fake():
    return FakeTrueForgeServer()


def client(fake):
    return TrueForge("http://tf", transport=httpx.MockTransport(fake.handle))


def test_first_run_creates_agents_and_schedule(fake):
    log = []
    setup(client(fake), SPECS, model="openai/gpt-5.2", log=log.append)

    assert sorted(log) == ["agent acme-ops: created", "agent distiller: created",
                           "schedule distiller-hourly: created"]
    distiller = fake.agent("distiller")["manifest"]
    assert distiller["model"] == {"name": "openai/gpt-5.2"}
    assert [m["name"] for m in distiller["mcp_servers"]] == ["skillsmith"]
    assert distiller["mcp_servers"][0]["require_approval_for_tools"] == ["@destructive"]
    assert distiller["config"]["sandbox"] == {"enabled": True}
    assert distiller["config"]["ask_user_questions"] == {"enabled": False}
    assert "publish_skill" in distiller["instructions"]
    assert "instructions_file" not in distiller

    acme = fake.agent("acme-ops")["manifest"]
    assert [m["name"] for m in acme["mcp_servers"]] == ["acme-app"]
    assert acme["config"]["sandbox"] == {"enabled": True}

    (schedule,) = fake.schedules.values()
    assert schedule["agent_name"] == "distiller"
    assert schedule["manifest"]["cron"] == "0 * * * *"
    assert fake.runs == []


def test_rerun_updates_in_place_and_keeps_published_skills_and_model(fake):
    tf = client(fake)
    setup(tf, SPECS, model="openai/gpt-5.2", log=lambda _: None)
    acme = fake.agent("acme-ops")
    acme["manifest"]["skills"] = [{"name": "acme-error-rate"}]  # published by skillsmith
    before = (set(fake.agents), set(fake.schedules))

    log = []
    setup(tf, SPECS, log=log.append)  # no --model needed now

    assert (set(fake.agents), set(fake.schedules)) == before
    assert sorted(log) == ["agent acme-ops: updated", "agent distiller: updated",
                           "schedule distiller-hourly: updated"]
    assert fake.agent("acme-ops")["manifest"]["skills"] == [{"name": "acme-error-rate"}]
    assert fake.agent("acme-ops")["manifest"]["model"] == {"name": "openai/gpt-5.2"}


def test_run_now_triggers_the_schedule(fake):
    log = []
    setup(client(fake), SPECS, model="openai/gpt-5.2", run_now=True, log=log.append)
    assert fake.runs == list(fake.schedules)
    assert "schedule distiller-hourly: triggered run run_1" in log


def test_missing_connector_stops_before_any_change(fake):
    fake.connectors.discard("skillsmith")
    with pytest.raises(SystemExit, match="connectors in TrueForge first: skillsmith"):
        setup(client(fake), SPECS, model="openai/gpt-5.2")
    assert fake.agents == {}


def test_new_agents_need_a_configured_model(fake):
    with pytest.raises(SystemExit, match="need a model: pass --model"):
        setup(client(fake), SPECS)
    with pytest.raises(SystemExit, match="isn't configured. Available: openai/gpt-5.2"):
        setup(client(fake), SPECS, model="openai/nope")
    assert fake.agents == {}


def test_spec_files_are_valid():
    for path in (SPECS / "agents").glob("*.json"):
        spec = load_agent(path)
        assert spec["name"] == path.stem
        assert spec["manifest"]["instructions"].strip()
    for path in (SPECS / "schedules").glob("*.json"):
        assert json.loads(path.read_text())["name"] == path.stem


def test_merge_manifest_unions_skills_existing_first():
    merged = merge_manifest({"skills": [{"name": "b"}, {"name": "a"}]},
                            {"model": {"name": "m"}, "skills": [{"name": "a"}]}, None)
    assert merged == {"model": {"name": "m"}, "skills": [{"name": "a"}, {"name": "b"}]}


def test_main_reports_api_errors_without_a_traceback(fake, monkeypatch):
    fake.handle = lambda request: httpx.Response(500, text="boom")
    monkeypatch.setattr(setup_trueforge, "TrueForge",
                        lambda url: TrueForge(url, transport=httpx.MockTransport(fake.handle)))
    monkeypatch.setattr("sys.argv", ["setup-trueforge", "--dir", str(SPECS)])
    with pytest.raises(SystemExit, match="-> 500: boom"):
        setup_trueforge.main()


def test_distiller_sessions_are_never_listed(tmp_path, monkeypatch):
    def session(sid, agent_name, metadata=None):
        return {"id": sid, "agent": {"type": "reference", "id": "a", "name": agent_name},
                "metadata": metadata or {}, "title": None, "created_at": "t",
                "created_by_subject": {}, "metrics": {"total_turns": 4}}

    class FakeTF:
        def list_sessions(self, limit):
            return [session("alice", "acme-ops", {"author": "alice"}),
                    session("run", "distiller"),
                    session("replay", None, {"source": "skillsmith"})]

    cfg = Config("http://tf", "tok", "o/r", "skills", ["acme-ops"], tmp_path / "state.json")
    monkeypatch.setattr(server, "_deps", lambda: (cfg, FakeTF(), None, State(cfg.state_path)))
    assert [s["id"] for s in server.list_sessions()] == ["alice"]
