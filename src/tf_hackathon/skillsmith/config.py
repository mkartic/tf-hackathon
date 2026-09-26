import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    trueforge_url: str
    github_token: str
    github_repo: str  # owner/name
    skills_dir: str
    team_agents: list[str]
    state_path: Path

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.github_repo}"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            trueforge_url=os.environ.get("TRUEFORGE_URL", "http://localhost:8790").rstrip("/"),
            github_token=os.environ["GITHUB_TOKEN"],
            github_repo=os.environ.get("SKILLSMITH_REPO", "mkartic/tf-hackathon"),
            skills_dir=os.environ.get("SKILLSMITH_SKILLS_DIR", "skills"),
            team_agents=os.environ.get("SKILLSMITH_TEAM_AGENTS", "acme-ops").split(","),
            state_path=Path(os.environ.get("SKILLSMITH_STATE", ".skillsmith/state.json")),
        )
