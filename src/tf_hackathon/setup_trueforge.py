"""Create or update the demo's TrueForge agents and schedule from the specs in trueforge/.

Idempotent: agents and schedules are matched by name and updated in place. An existing agent
keeps its model (unless --model is given) and every skill already attached to it, so a re-run
never detaches a skill skillsmith has published.

    uv run setup-trueforge --model openai/gpt-5.2   # first run: new agents need a model
    uv run setup-trueforge                          # later runs
    uv run setup-trueforge --run-now                # also trigger the distiller now
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from tf_hackathon.skillsmith.trueforge import TrueForge


def load_agent(path: Path) -> dict:
    """An agent spec file, with `instructions_file` inlined from next to it."""
    spec = json.loads(path.read_text())
    manifest = spec["manifest"]
    if file := manifest.pop("instructions_file", None):
        manifest["instructions"] = (path.parent / file).read_text().strip()
    return spec


def merge_manifest(spec: dict, existing: dict | None, model: str | None) -> dict:
    """The manifest to save: the spec, plus the model and skills the live agent already has."""
    existing = existing or {}
    manifest = dict(spec)
    if model:
        manifest["model"] = {"name": model}
    elif existing.get("model"):
        manifest["model"] = existing["model"]
    skills = list(existing.get("skills") or [])
    for skill in spec.get("skills") or []:
        if all(s["name"] != skill["name"] for s in skills):
            skills.append(skill)
    manifest["skills"] = skills
    return manifest


def _connectors(specs: list[dict]) -> set[str]:
    return {m["name"] for s in specs for m in s["manifest"].get("mcp_servers") or []}


def setup(tf: TrueForge, root: Path, model: str | None = None, run_now: bool = False,
          log: Callable[[str], None] = print) -> None:
    agents = [load_agent(p) for p in sorted((root / "agents").glob("*.json"))]
    schedules = [json.loads(p.read_text()) for p in sorted((root / "schedules").glob("*.json"))]

    missing = sorted(c for c in _connectors(agents) if not tf.mcp_server_exists(c))
    if missing:
        raise SystemExit(f"Register these connectors in TrueForge first: {', '.join(missing)}")
    if model and model not in (available := tf.model_names()):
        raise SystemExit(f"Model {model!r} isn't configured. Available: {', '.join(available)}")

    existing = {a["name"]: tf.find_agent(a["name"]) for a in agents}
    new = [name for name, agent in existing.items() if agent is None]
    if new and not model:
        raise SystemExit(f"New agent(s) {', '.join(new)} need a model: pass --model "
                         f"(available: {', '.join(tf.model_names())})")

    for spec in agents:
        name, current = spec["name"], existing[spec["name"]]
        manifest = merge_manifest(spec["manifest"], current and current["manifest"], model)
        if current is None:
            tf.create_agent(name, spec["description"], manifest)
            log(f"agent {name}: created")
        else:
            tf.update_agent(current | {"description": spec["description"]}, manifest)
            log(f"agent {name}: updated")

    for spec in schedules:
        agent, name = spec["agent_name"], spec["name"]
        current = tf.find_schedule(agent, name)
        if current is None:
            schedule = tf.create_schedule(agent, name, spec["manifest"])
            log(f"schedule {name}: created")
        else:
            schedule = tf.update_schedule(current["id"], name, spec["manifest"])
            log(f"schedule {name}: updated")
        if run_now:
            run = tf.run_schedule(schedule["id"])
            log(f"schedule {name}: triggered run {run['id']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="setup-trueforge", description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=os.environ.get("TRUEFORGE_URL", "http://localhost:8790"))
    parser.add_argument("--model", help="model for the agents, e.g. openai/gpt-5.2")
    parser.add_argument("--dir", type=Path, default=Path("trueforge"), help="spec directory")
    parser.add_argument("--run-now", action="store_true", help="trigger every schedule now")
    args = parser.parse_args()
    try:
        setup(TrueForge(args.url.rstrip("/")), args.dir, args.model, args.run_now)
    except ToolError as e:
        sys.exit(str(e))
