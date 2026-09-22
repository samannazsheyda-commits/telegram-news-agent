from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .permissions import PermissionGate


class BuilderError(RuntimeError):
    pass


class BuilderWorkflow:
    def __init__(self, *, adapter: Any, permission_gate: PermissionGate) -> None:
        self.adapter = adapter
        self.permission_gate = permission_gate

    def prepare(self, *, change_id: str, patch: str, actor: str) -> dict[str, Any]:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(change_id or "")).strip("-")
        patch_text = str(patch or "").strip()
        if not safe_id or not patch_text:
            raise ValueError("change_id and patch are required")
        branch = f"luna/{safe_id}"
        self.adapter.create_branch(branch)
        self.adapter.apply_patch(branch, patch_text)
        tests = dict(self.adapter.run_tests(branch))
        if not tests.get("passed"):
            raise BuilderError(f"builder tests failed: {tests.get('summary') or 'unknown failure'}")
        preview_url = str(self.adapter.create_preview(branch))
        if not preview_url.startswith(("https://", "http://")):
            raise BuilderError("builder preview did not return a valid URL")
        payload = {"branch": branch}
        return {
            "phase": "preview_ready",
            "branch": branch,
            "tests": tests,
            "preview_url": preview_url,
            "confirmation_token": self.permission_gate.issue(
                actor=actor, action="deploy", payload=payload
            ),
        }

    def deploy(self, *, branch: str, actor: str, confirmation_token: str) -> dict[str, Any]:
        normalized_branch = str(branch or "").strip()
        payload = {"branch": normalized_branch}
        self.permission_gate.verify(
            confirmation_token,
            actor=actor,
            action="deploy",
            payload=payload,
        )
        deployment = self.adapter.deploy(normalized_branch)
        return {"phase": "deployed", "branch": normalized_branch, "result": deployment}


class CommandBuilderAdapter:
    """Runs a guarded branch/test/preview/deploy workflow without a shell."""

    def __init__(
        self,
        *,
        repo_path: str | Path,
        test_command: Sequence[str],
        preview_command: Sequence[str],
        deploy_command: Sequence[str],
        timeout_seconds: int = 900,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / ".git").exists():
            raise ValueError("builder repo_path must be a git repository")
        self.test_command = tuple(test_command)
        self.preview_command = tuple(preview_command)
        self.deploy_command = tuple(deploy_command)
        if not self.test_command or not self.preview_command or not self.deploy_command:
            raise ValueError("builder test, preview and deploy commands are required")
        self.timeout_seconds = max(30, int(timeout_seconds))

    @staticmethod
    def _valid_branch(branch: str) -> str:
        value = str(branch or "")
        if not re.fullmatch(r"luna/[A-Za-z0-9_-]+", value):
            raise BuilderError("builder branch must use the luna/ namespace")
        return value

    def _run(
        self,
        command: Sequence[str],
        *,
        input_text: str | None = None,
        branch: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        rendered = [str(part).replace("{branch}", branch or "") for part in command]
        environment = os.environ.copy()
        if branch:
            environment["BIKHABAR_BUILDER_BRANCH"] = branch
        try:
            return subprocess.run(
                rendered,
                cwd=self.repo_path,
                input=input_text,
                text=True,
                capture_output=True,
                check=True,
                timeout=self.timeout_seconds,
                env=environment,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            output = "\n".join(
                value for value in [getattr(exc, "stdout", ""), getattr(exc, "stderr", "")] if value
            )
            raise BuilderError(f"builder command failed: {output[-4000:]}") from exc

    def create_branch(self, branch: str) -> None:
        name = self._valid_branch(branch)
        dirty = self._run(["git", "status", "--porcelain"]).stdout.strip()
        if dirty:
            raise BuilderError("builder repository has uncommitted changes")
        self._run(["git", "switch", "-c", name])

    def apply_patch(self, branch: str, patch: str) -> None:
        name = self._valid_branch(branch)
        self._run(["git", "apply", "--check", "-"], input_text=patch, branch=name)
        self._run(["git", "apply", "-"], input_text=patch, branch=name)
        self._run(["git", "add", "-A"], branch=name)
        self._run(["git", "commit", "-m", f"feat: Luna builder change {name[5:]}"], branch=name)

    def run_tests(self, branch: str) -> dict[str, Any]:
        name = self._valid_branch(branch)
        result = self._run(self.test_command, branch=name)
        summary = "\n".join(value for value in [result.stdout, result.stderr] if value).strip()
        return {"passed": True, "summary": summary[-4000:]}

    def create_preview(self, branch: str) -> str:
        name = self._valid_branch(branch)
        result = self._run(self.preview_command, branch=name)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise BuilderError("preview command returned no URL")
        return lines[-1]

    def deploy(self, branch: str) -> dict[str, Any]:
        name = self._valid_branch(branch)
        result = self._run(self.deploy_command, branch=name)
        return {"output": result.stdout.strip()[-4000:]}
