"""The shared skills repo on GitHub: read skills, open, merge, and close PRs."""

import httpx
from mcp.server.mcpserver.exceptions import ToolError


class GitHub:
    def __init__(self, token: str, repo: str):
        self.repo = repo
        self.http = httpx.Client(
            base_url=f"https://api.github.com/repos/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        r = self.http.request(method, url, **kw)
        if r.is_error:
            raise ToolError(f"GitHub {method} {url} -> {r.status_code}: {r.text[:500]}")
        return r

    def list_dir(self, path: str, ref: str = "main") -> list[dict]:
        r = self.http.get(f"/contents/{path}", params={"ref": ref})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json()

    def read_file(self, path: str, ref: str = "main") -> str | None:
        r = self.http.get(
            f"/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text

    def list_tree(self, path: str, ref: str = "main") -> list[str]:
        """Every file path under `path`, recursively."""
        tree = self._req("GET", f"/git/trees/{ref}", params={"recursive": "1"}).json()["tree"]
        prefix = path.rstrip("/") + "/"
        return [e["path"] for e in tree if e["type"] == "blob" and e["path"].startswith(prefix)]

    def commit_to_new_branch(
        self, branch: str, message: str, files: dict[str, str | None], base: str = "main"
    ) -> str:
        """One commit on a fresh branch off `base`. A None value deletes that path."""
        base_sha = self._req("GET", f"/git/ref/heads/{base}").json()["object"]["sha"]
        base_tree = self._req("GET", f"/git/commits/{base_sha}").json()["tree"]["sha"]
        entries = [
            {"path": p, "mode": "100644", "type": "blob"}
            | ({"sha": None} if content is None else {"content": content})
            for p, content in files.items()
        ]
        tree = self._req("POST", "/git/trees", json={"base_tree": base_tree, "tree": entries})
        commit = self._req(
            "POST",
            "/git/commits",
            json={"message": message, "tree": tree.json()["sha"], "parents": [base_sha]},
        ).json()["sha"]
        self._req("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit})
        return commit

    def open_pr(self, branch: str, title: str, body: str, base: str = "main") -> dict:
        return self._req(
            "POST", "/pulls", json={"title": title, "head": branch, "base": base, "body": body}
        ).json()

    def get_pr(self, number: int) -> dict:
        return self._req("GET", f"/pulls/{number}").json()

    def merge_pr(self, number: int, title: str) -> str:
        r = self._req(
            "PUT", f"/pulls/{number}/merge", json={"merge_method": "squash", "commit_title": title}
        )
        self.delete_branch(self.get_pr(number)["head"]["ref"])
        return r.json()["sha"]

    def close_pr(self, number: int, comment: str) -> None:
        self._req("POST", f"/issues/{number}/comments", json={"body": comment})
        pr = self._req("PATCH", f"/pulls/{number}", json={"state": "closed"}).json()
        self.delete_branch(pr["head"]["ref"])

    def delete_branch(self, branch: str) -> None:
        r = self.http.delete(f"/git/refs/heads/{branch}")
        if r.status_code not in (204, 404, 422):
            r.raise_for_status()
