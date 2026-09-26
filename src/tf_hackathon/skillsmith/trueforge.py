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


def is_skillsmith_session(session: dict) -> bool:
    return (session.get("metadata") or {}).get("source") == SKILLSMITH_SOURCE


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}… [{len(text) - limit} chars cut]"


def transcript(events: list[dict], clip: int = 800) -> str:
    """A readable transcript of a session: user and agent messages, tool calls, results."""
    lines = []
    for e in events:
        match e["type"]:
            case "turn.created":
                for item in e.get("input", []):
                    if item.get("type") == "user.message":
                        lines.append(f"USER: {item['content']}")
                    elif item.get("type") == "user.tool_approval":
                        lines.append(f"USER APPROVAL: {json.dumps(item)}")
            case "model.message":
                if e.get("content"):
                    lines.append(f"AGENT: {e['content']}")
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
