from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from .github_builder import BuilderError, GitHubBuilder


_REQUIRED_WORKFLOWS = ("Pull Request Check", "Telegram News Agent CI")


def configured_builder() -> GitHubBuilder:
    """Return the server-side Builder with main as the safe default base.

    main is the tested integration branch. The repository CI promotes a green
    push on main to production, so Builder changes must never target production
    directly unless an operator explicitly overrides the base in server env.
    """
    builder = GitHubBuilder.from_env()
    if not str(os.environ.get("LUNA_BUILDER_BASE_BRANCH") or "").strip() and isinstance(builder, GitHubBuilder):
        builder.base_branch = "main"
    return builder


@dataclass
class BuilderRelease:
    builder: GitHubBuilder

    def _pull(self, pr_number: int) -> dict:
        if int(pr_number or 0) <= 0:
            raise BuilderError("شماره PR معتبر نیست.")
        value = self.builder._request("GET", f"/pulls/{int(pr_number)}")
        if not isinstance(value, dict) or not value.get("number"):
            raise BuilderError("PR پیدا نشد.")
        return value

    def _workflow_state(self, head_sha: str) -> dict:
        payload = self.builder._request(
            "GET",
            f"/actions/runs?head_sha={head_sha}&event=pull_request&per_page=50",
        )
        rows = payload.get("workflow_runs") if isinstance(payload, dict) else []
        latest: dict[str, dict] = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            if name not in _REQUIRED_WORKFLOWS or name in latest:
                continue
            latest[name] = row
        states = {}
        for name in _REQUIRED_WORKFLOWS:
            row = latest.get(name) or {}
            states[name] = {
                "status": str(row.get("status") or "missing"),
                "conclusion": str(row.get("conclusion") or ""),
                "url": str(row.get("html_url") or ""),
            }
        green = all(
            states[name]["status"] == "completed" and states[name]["conclusion"] == "success"
            for name in _REQUIRED_WORKFLOWS
        )
        return {"green": green, "checks": states}

    def status(self, pr_number: int) -> dict:
        pr = self._pull(pr_number)
        head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
        base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
        head_sha = str(head.get("sha") or "")
        ci = self._workflow_state(head_sha) if head_sha else {"green": False, "checks": {}}
        return {
            "ok": True,
            "pr_number": int(pr.get("number") or 0),
            "url": str(pr.get("html_url") or ""),
            "state": str(pr.get("state") or ""),
            "draft": bool(pr.get("draft")),
            "mergeable": pr.get("mergeable"),
            "head_sha": head_sha,
            "base_branch": str(base.get("ref") or ""),
            "ci_green": bool(ci["green"]),
            "checks": ci["checks"],
            "merged": bool(pr.get("merged")),
        }

    def _mark_ready(self, node_id: str) -> None:
        if not node_id:
            raise BuilderError("شناسه GitHub برای خارج کردن PR از Draft پیدا نشد.")
        response = requests.post(
            "https://api.github.com/graphql",
            headers=self.builder._headers(),
            json={
                "query": "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}",
                "variables": {"id": node_id},
            },
            timeout=self.builder.timeout,
        )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BuilderError("GitHub نتوانست Draft PR را آماده merge کند.") from exc
        value = response.json() if response.content else {}
        if value.get("errors"):
            raise BuilderError("GitHub اجازه خارج کردن PR از Draft را نداد.")

    def merge(self, pr_number: int, *, expected_head_sha: str = "") -> dict:
        status = self.status(pr_number)
        if status["merged"]:
            return {**status, "ok": True, "message": "این تغییر قبلاً merge شده است."}
        if status["state"] != "open":
            raise BuilderError("PR باز نیست و قابل merge نیست.")
        if status["base_branch"] != "main":
            raise BuilderError("برای ایمنی، Luna فقط PRهای Builder به شاخه main را merge می‌کند.")
        if expected_head_sha and status["head_sha"] != expected_head_sha:
            raise BuilderError("بعد از تأیید تو، محتوای PR تغییر کرده؛ دوباره وضعیت را بررسی کن.")
        if not status["ci_green"]:
            raise BuilderError("CI هنوز کامل سبز نیست؛ Luna اجازه merge ندارد.")

        pr = self._pull(pr_number)
        if bool(pr.get("draft")):
            self._mark_ready(str(pr.get("node_id") or ""))

        value = self.builder._request(
            "PUT",
            f"/pulls/{int(pr_number)}/merge",
            json={
                "merge_method": "squash",
                "sha": status["head_sha"],
                "commit_title": f"Luna Builder PR #{int(pr_number)}",
            },
        )
        if not bool((value or {}).get("merged")):
            raise BuilderError(str((value or {}).get("message") or "GitHub تغییر را merge نکرد."))
        return {
            "ok": True,
            "merged": True,
            "pr_number": int(pr_number),
            "merge_sha": str((value or {}).get("sha") or ""),
            "rollback_sha": str((pr.get("base") or {}).get("sha") or ""),
            "message": "تغییر با CI سبز به main ادغام شد؛ CI اصلی حالا نسخه تست‌شده را به production منتقل می‌کند.",
        }
