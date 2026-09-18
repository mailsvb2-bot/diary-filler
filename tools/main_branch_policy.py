"""Fail-closed provenance guard for pushes to protected production branches.

GitHub branch protection is the primary enforcement mechanism. This repository-level
guard is defense in depth: if branch protection is absent or temporarily misconfigured,
a direct push to main/master makes CI fail immediately and therefore cannot become a
validated/releasable candidate.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request


PROTECTED_REFS = {
    "refs/heads/main": "main",
    "refs/heads/master": "master",
}


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "MAIN BRANCH POLICY FAILED: git "
            + " ".join(args)
            + " failed: "
            + (proc.stderr.strip() or f"exit {proc.returncode}")
        )
    return proc.stdout.strip()


def _associated_pulls(repository: str, sha: str, token: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repository}/commits/{sha}/pulls"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "diary-filler-main-branch-policy",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"MAIN BRANCH POLICY FAILED: cannot verify PR provenance via GitHub API: {exc}") from exc
    if not isinstance(payload, list):
        raise SystemExit("MAIN BRANCH POLICY FAILED: GitHub PR provenance response is not a list")
    return payload


def main() -> None:
    event = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    ref = os.environ.get("GITHUB_REF", "").strip()
    if event != "push" or ref not in PROTECTED_REFS:
        print(f"MAIN BRANCH POLICY SKIP: event={event or '<local>'}; ref={ref or '<local>'}")
        return

    sha = os.environ.get("GITHUB_SHA", "").strip() or "HEAD"
    branch = PROTECTED_REFS[ref]
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository:
        raise SystemExit("MAIN BRANCH POLICY FAILED: GITHUB_REPOSITORY is missing")
    if not token:
        raise SystemExit("MAIN BRANCH POLICY FAILED: GitHub token is missing")

    lineage = _git("rev-list", "--parents", "-n", "1", sha).split()
    if len(lineage) != 3:
        raise SystemExit(
            "MAIN BRANCH POLICY FAILED: direct/squash/rebase push to "
            f"{branch} is forbidden; expected a two-parent PR merge commit"
        )

    message = _git("show", "-s", "--format=%B", sha)
    if not message.startswith("Merge pull request #"):
        raise SystemExit(
            "MAIN BRANCH POLICY FAILED: protected-branch HEAD is not a canonical GitHub PR merge commit"
        )

    pulls = _associated_pulls(repository, sha, token)
    matching = [
        pr
        for pr in pulls
        if pr.get("merged_at")
        and pr.get("merge_commit_sha") == sha
        and (pr.get("base") or {}).get("ref") == branch
        and pr.get("state") == "closed"
    ]
    if len(matching) != 1:
        raise SystemExit(
            "MAIN BRANCH POLICY FAILED: HEAD is not uniquely attributable to a merged PR "
            f"targeting {branch}; matches={len(matching)}"
        )

    pr = matching[0]
    print(
        "MAIN BRANCH POLICY OK: "
        f"{branch} HEAD {sha} is merged PR #{pr.get('number')} ({pr.get('html_url')})"
    )


if __name__ == "__main__":
    main()
