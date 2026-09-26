"""TrueForge HTTP API: read sessions, register skills, attach them to agents."""

import json

import httpx
from mcp.server.mcpserver.exceptions import ToolError

SKILLSMITH_SOURCE = "skillsmith"


class TrueForge:
    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=f"{base_url}/api/v1", timeout=60)

    def _req(self, method: str, url: str, **kw) -> dict:
        r = self.http.request(method, url, **kw)
        if r.is_error:
            raise ToolError(f"TrueForge {method} {url} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def list_sessions(self, limit: int = 100) -> list[dict]:
        sessions, token = [], None
        while len(sessions) < limit:
            params = {"limit": min(100, limit - len(sessions)), "order": "desc"}
            if token:
                params["page_token"] = token
            page = self._req("GET", "/sessions", params=params)
            sessions += page["data"]
            token = page["pagination"].get("next_page_token")
            if not token:
                break
        return sessions

    def session_events(self, session_id: str) -> list[dict]:
        """All persisted events of a session, oldest first."""
        items, token = [], None
        while True:
            params = {"limit": 100} | ({"page_token": token} if token else {})
            page = self._req("GET", f"/sessions/{session_id}/events", params=params)
            items += page["data"]
            token = page["pagination"].get("next_page_token")
            if not token:
                break
        return [it["event"] for it in reversed(items)]

    def get_session(self, session_id: str) -> dict:
        return self._req("GET", f"/sessions/{session_id}")["data"]

    def list_turns(self, session_id: str) -> list[dict]:
        turns, token = [], None
        while True:
            params = {"limit": 100} | ({"page_token": token} if token else {})
            page = self._req("GET", f"/sessions/{session_id}/turns", params=params)
            turns += page["data"]
            token = page["pagination"].get("next_page_token")
            if not token:
                return turns

    def create_session(self, spec: dict, metadata: dict[str, str]) -> dict:
        """A session bound to an inline AgentSpec (no registry agent)."""
        body = {"agent": {"spec": spec}, "metadata": metadata}
        return self._req("POST", "/sessions", json=body)["data"]

    def start_turn(self, session_id: str, message: str) -> dict:
        """Start a root turn with one user message; returns the running turn."""
        body = {"input": [{"type": "user.message", "content": message}], "stream": False}
        return self._req("POST", f"/sessions/{session_id}/turns", json=body)["data"]

    def get_turn(self, session_id: str, turn_id: str) -> dict:
        return self._req("GET", f"/sessions/{session_id}/turns/{turn_id}")["data"]

    def cancel_session(self, session_id: str) -> None:
        self._req("POST", f"/sessions/{session_id}/cancel", json={})

    def get_agent(self, agent_id: str) -> dict:
        return self._req("GET", f"/agents/{agent_id}")["data"]

    def upsert_skill(self, manifest: dict) -> None:
        self._req("PUT", "/settings/skills", json={"manifest": manifest})

    def find_agent(self, name: str) -> dict | None:
        for agent in self._req("GET", "/agents", params={"agent_name": name})["data"]:
            if agent["name"] == name:
                return agent
        return None

    def update_agent(self, agent: dict, manifest: dict) -> None:
        body = {"manifest": manifest}
        if agent.get("description"):
            body["description"] = agent["description"]
        self._req("PUT", f"/agents/{agent['id']}", json=body)


def agent_spec(tf: TrueForge, session: dict) -> dict:
    """The AgentSpec a session ran with: inline, or the registry agent's current manifest."""
    agent = session["agent"]
    return agent["spec"] if agent["type"] == "inline" else tf.get_agent(agent["id"])["manifest"]


def is_skillsmith_session(session: dict) -> bool:
    return (session.get("metadata") or {}).get("source") == SKILLSMITH_SOURCE


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}… [{len(text) - limit} chars cut]"


def text_of(content) -> str:
    """Message content as plain text: a string, or the text parts of a content list."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if p.get("type") == "text")


def first_user_message(events: list[dict]) -> str | None:
    for e in events:
        if e["type"] == "turn.created":
            for item in e.get("input", []):
                if item.get("type") == "user.message" and text_of(item["content"]).strip():
                    return text_of(item["content"])
    return None


def _main_thread_messages(events: list[dict]) -> list[dict]:
    return [e for e in events
            if e["type"] == "model.message" and e.get("thread_id", "main") == "main"]


def final_answer(events: list[dict]) -> str | None:
    """The agent's last non-empty message: its eventual answer."""
    for e in reversed(_main_thread_messages(events)):
        if text_of(e.get("content")).strip():
            return text_of(e["content"])
    return None


def model_calls(events: list[dict]) -> int:
    return len(_main_thread_messages(events))


def turn_tokens(turn: dict) -> int:
    return (turn["state"].get("metrics") or {}).get("total_tokens") or 0


def transcript(events: list[dict], clip: int = 800) -> str:
    """A readable transcript of a session: user and agent messages, tool calls, results."""
    lines = []
    for e in events:
        match e["type"]:
            case "turn.created":
                for item in e.get("input", []):
                    if item.get("type") == "user.message":
                        lines.append(f"USER: {text_of(item['content'])}")
                    elif item.get("type") == "user.tool_approval":
                        lines.append(f"USER APPROVAL: {json.dumps(item)}")
            case "model.message":
                if text_of(e.get("content")):
                    lines.append(f"AGENT: {text_of(e['content'])}")
                for call in e.get("tool_calls") or []:
                    fn = call["function"]
                    lines.append(f"TOOL CALL {fn['name']}: {_clip(fn['arguments'], clip)}")
            case "tool.response":
                content = e.get("content")
                if not isinstance(content, str):
                    content = json.dumps(content)
                lines.append(f"TOOL RESULT: {_clip(content, clip)}")
    return "\n".join(lines)


def with_skill(manifest: dict, skill: str) -> dict:
    """An agent manifest with `skill` attached and the sandbox skills need turned on."""
    skills = manifest.get("skills") or []
    if all(s["name"] != skill for s in skills):
        skills = skills + [{"name": skill}]
    config = manifest.get("config") or {}
    sandbox = (config.get("sandbox") or {}) | {"enabled": True}
    return manifest | {"skills": skills, "config": config | {"sandbox": sandbox}}


def without_skill(manifest: dict, skill: str) -> dict:
    skills = [s for s in manifest.get("skills") or [] if s["name"] != skill]
    return manifest | {"skills": skills}
