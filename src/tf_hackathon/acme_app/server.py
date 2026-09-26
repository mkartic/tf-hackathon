"""acme-app MCP server: read-only access to the fictional service's logs."""

import argparse
import os
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tf_hackathon.acme_app import logs

ServiceName = Literal["checkout-api", "inventory-api", "payments-api"]
Window = Literal["1h", "6h", "24h"]

mcp = MCPServer(
    "acme-app",
    instructions="Production logs for acme-app services. Windows end at 2026-09-25T15:00Z.",
)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def fetch_logs(service: ServiceName, window: Window = "1h") -> str:
    """Fetch request logs for one acme-app service, oldest line first.

    Each line is one logged request with its status and duration.
    """
    return logs.render(service, window)


def main() -> None:
    parser = argparse.ArgumentParser(prog="acme-app")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the MCP server (default)")
    stats = sub.add_parser("stats", help="print the ground-truth error rates")
    stats.add_argument("service", choices=sorted(logs.SERVICES))
    stats.add_argument("window", choices=sorted(logs.WINDOWS))
    args = parser.parse_args()

    if args.command == "stats":
        s = logs.stats(args.service, args.window)
        print(f"requests={s.requests} failed={s.failed_requests} attempts={s.attempts}")
        print(f"error rate (correct): {s.error_rate:.1%}")
        print(f"error rate (naive):   {s.naive_error_rate:.1%}")
        return

    mcp.run(
        "streamable-http",
        host=os.environ.get("ACME_HOST", "127.0.0.1"),
        port=int(os.environ.get("ACME_PORT", "8801")),
    )
