from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.core.config import Settings

GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubSnapshot:
    owner: str
    name: str
    branch: str
    commit_sha: str
    canonical_url: str


def parse_github_url(raw_url: str) -> tuple[str, str, str]:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("Only public https://github.com repositories are supported")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("Use a repository URL such as https://github.com/owner/repository")
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    owner_is_valid = bool(owner and GITHUB_NAME_PATTERN.fullmatch(owner))
    name_is_valid = bool(name and GITHUB_NAME_PATTERN.fullmatch(name))
    if not owner_is_valid or not name_is_valid:
        raise ValueError("The GitHub owner or repository name is invalid")

    return owner, name, f"https://github.com/{owner}/{name}"


class GitHubClient:
    def __init__(self, settings: Settings):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoWiseAI/0.1",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = httpx.Client(headers=headers, follow_redirects=True, timeout=30.0)
        self.settings = settings

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def resolve_snapshot(self, owner: str, name: str, branch: str | None) -> GitHubSnapshot:
        repository_response = self.client.get(f"https://api.github.com/repos/{owner}/{name}")
        self._raise_for_status(repository_response, "Repository metadata could not be loaded")
        repository = repository_response.json()
        if repository.get("private"):
            raise GitHubError("Private repositories are not supported in the MVP")

        resolved_branch = branch or repository.get("default_branch")
        if not resolved_branch:
            raise GitHubError("The repository default branch could not be determined")

        commit_response = self.client.get(
            f"https://api.github.com/repos/{owner}/{name}/commits/{quote(resolved_branch, safe='')}"
        )
        self._raise_for_status(commit_response, "The requested branch could not be resolved")
        commit_sha = commit_response.json().get("sha")
        if not commit_sha:
            raise GitHubError("GitHub did not return a commit SHA")

        return GitHubSnapshot(
            owner=owner,
            name=name,
            branch=resolved_branch,
            commit_sha=commit_sha,
            canonical_url=f"https://github.com/{owner}/{name}",
        )

    def download_archive(self, snapshot: GitHubSnapshot, destination: Path) -> None:
        url = (
            f"https://api.github.com/repos/{snapshot.owner}/{snapshot.name}/tarball/"
            f"{snapshot.commit_sha}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        with self.client.stream("GET", url) as response:
            self._raise_for_status(response, "The repository archive could not be downloaded")
            with destination.open("wb") as archive:
                for chunk in response.iter_bytes():
                    downloaded += len(chunk)
                    if downloaded > self.settings.max_archive_bytes:
                        raise GitHubError("The compressed repository archive is too large")
                    archive.write(chunk)

    @staticmethod
    def _raise_for_status(response: httpx.Response, message: str) -> None:
        if response.is_success:
            return
        if response.status_code == 404:
            raise GitHubError(f"{message}: repository or branch not found")
        if response.status_code == 403:
            remaining = response.headers.get("x-ratelimit-remaining")
            suffix = " (GitHub rate limit reached)" if remaining == "0" else ""
            raise GitHubError(f"{message}{suffix}")
        raise GitHubError(f"{message}: GitHub returned HTTP {response.status_code}")
