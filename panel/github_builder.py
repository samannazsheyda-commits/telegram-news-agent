from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from .openai_luna import LunaProviderError, OpenAILunaClient, get_luna_client


_ALLOWED_PREFIXES = ("panel/", "src/", "tests/", "docs/", ".github/")
_ALLOWED_SUFFIXES = (".py", ".js", ".css", ".html", ".md", ".yml", ".yaml", ".json")
_BLOCKED_PATH_PARTS = (".env", "secret", "credential", "token", "private_key")
_MAX_SELECTED_FILES = 8
_MAX_CONTEXT_CHARS = 120_000


class BuilderError(RuntimeError):
    pass


@dataclass
class GitHubBuilder:
    token: str
    repository: str
    base_branch: str = "production"
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "GitHubBuilder":
        return cls(
            token=str(os.environ.get("LUNA_GITHUB_TOKEN") or "").strip(),
            repository=str(
                os.environ.get("LUNA_GITHUB_REPOSITORY")
                or "samannazsheyda-commits/telegram-news-agent"
            ).strip(),
            base_branch=str(os.environ.get("LUNA_BUILDER_BASE_BRANCH") or "production").strip(),
        )

    @property
    def connected(self) -> bool:
        return bool(self.token and "/" in self.repository and self.base_branch)

    @property
    def api_root(self) -> str:
        return f"https://api.github.com/repos/{self.repository}"

    def _headers(self) -> dict[str, str]:
        if not self.connected:
            raise BuilderError("Builder به GitHub متصل نیست؛ LUNA_GITHUB_TOKEN روی سرور تنظیم نشده است.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.api_root}{path}",
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise BuilderError("اتصال Builder به GitHub طول کشید؛ دوباره تلاش کن.") from exc
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", 0)
            detail = ""
            try:
                detail = str((exc.response.json() or {}).get("message") or "")
            except Exception:
                detail = ""
            raise BuilderError(f"GitHub Builder خطا داد ({status}){': ' + detail if detail else ''}") from exc
        except requests.RequestException as exc:
            raise BuilderError("ارتباط Builder با GitHub برقرار نشد.") from exc
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise BuilderError("پاسخ GitHub معتبر نبود.") from exc

    def base_sha(self) -> str:
        value = self._request("GET", f"/git/ref/heads/{self.base_branch}")
        sha = str(((value or {}).get("object") or {}).get("sha") or "").strip()
        if not sha:
            raise BuilderError("SHA شاخه پایه GitHub پیدا نشد.")
        return sha

    def repository_paths(self, sha: str) -> list[str]:
        value = self._request("GET", f"/git/trees/{sha}?recursive=1")
        rows = value.get("tree") if isinstance(value, dict) else []
        paths: list[str] = []
        for row in rows or []:
            if not isinstance(row, dict) or row.get("type") != "blob":
                continue
            path = str(row.get("path") or "")
            if self._path_allowed(path):
                paths.append(path)
        return paths[:2500]

    @staticmethod
    def _path_allowed(path: str) -> bool:
        normalized = str(path or "").strip().lstrip("/")
        lowered = normalized.casefold()
        if not normalized.startswith(_ALLOWED_PREFIXES):
            return False
        if not normalized.endswith(_ALLOWED_SUFFIXES):
            return False
        if any(part in lowered for part in _BLOCKED_PATH_PARTS):
            return False
        if ".." in normalized.split("/"):
            return False
        return True

    def fetch_text_file(self, path: str, ref: str) -> tuple[str, str]:
        if not self._path_allowed(path):
            raise BuilderError(f"Builder اجازه خواندن این مسیر را ندارد: {path}")
        value = self._request("GET", f"/contents/{path}?ref={ref}")
        if not isinstance(value, dict):
            raise BuilderError(f"فایل معتبر نبود: {path}")
        encoded = str(value.get("content") or "").replace("\n", "")
        try:
            content = base64.b64decode(encoded).decode("utf-8")
        except Exception as exc:
            raise BuilderError(f"فایل متنی قابل خواندن نبود: {path}") from exc
        return content, str(value.get("sha") or "")

    def create_branch(self, *, base_sha: str, slug: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe_slug = re.sub(r"[^a-z0-9-]+", "-", slug.casefold()).strip("-")[:36] or "change"
        branch = f"luna/change-{stamp}-{safe_slug}"
        self._request("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
        return branch

    def put_file(self, *, branch: str, path: str, content: str, message: str, sha: str = "") -> None:
        if not self._path_allowed(path):
            raise BuilderError(f"Builder اجازه نوشتن این مسیر را ندارد: {path}")
        payload: dict[str, Any] = {
            "message": message[:180],
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        self._request("PUT", f"/contents/{path}", json=payload)

    def create_draft_pr(self, *, branch: str, title: str, body: str) -> dict:
        value = self._request(
            "POST",
            "/pulls",
            json={
                "title": title[:240],
                "head": branch,
                "base": self.base_branch,
                "body": body,
                "draft": True,
            },
        )
        return {
            "number": int(value.get("number") or 0),
            "url": str(value.get("html_url") or ""),
            "state": str(value.get("state") or ""),
            "draft": bool(value.get("draft", True)),
        }

    @staticmethod
    def _json_schema_selection() -> dict:
        return {
            "type": "json_schema",
            "name": "builder_selection",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary_fa": {"type": "string"},
                    "slug": {"type": "string"},
                    "files": {
                        "type": "array",
                        "maxItems": _MAX_SELECTED_FILES,
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "action": {"type": "string", "enum": ["update", "create"]},
                                "purpose": {"type": "string"},
                            },
                            "required": ["path", "action", "purpose"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "summary_fa", "slug", "files"],
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _json_schema_implementation() -> dict:
        return {
            "type": "json_schema",
            "name": "builder_implementation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary_fa": {"type": "string"},
                    "files": {
                        "type": "array",
                        "maxItems": _MAX_SELECTED_FILES,
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "action": {"type": "string", "enum": ["update", "create"]},
                                "content": {"type": "string"},
                                "commit_message": {"type": "string"},
                            },
                            "required": ["path", "action", "content", "commit_message"],
                            "additionalProperties": False,
                        },
                    },
                    "test_commands": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "summary_fa", "files", "test_commands"],
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _parse_json_text(client: OpenAILunaClient, response: dict) -> dict:
        text = client.output_text(response)
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise BuilderError("Luna نتوانست طرح Builder معتبر تولید کند.") from exc
        if not isinstance(value, dict):
            raise BuilderError("خروجی Builder معتبر نبود.")
        return value

    def _select_files(self, request_text: str, paths: list[str], client: OpenAILunaClient) -> dict:
        manifest = "\n".join(paths[:1400])
        prompt = (
            "درخواست کاربر برای تغییر پروژه بی‌خبر:\n"
            f"{request_text}\n\n"
            "از فهرست مسیرهای موجود فقط فایل‌های واقعاً لازم را انتخاب کن. "
            "برای قابلیت جدید حداقل یک فایل تست در tests/ پیشنهاد بده. "
            "هرگز فایل env، secret، token یا مسیر خارج از panel/src/tests/docs/.github انتخاب نکن. "
            "اگر فایل جدید لازم است action=create بگذار.\n\n"
            f"مسیرهای موجود:\n{manifest}"
        )
        response = client.create_response(
            input_items=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            model=client.complex_model,
            instructions="تو Builder امن پروژه هستی. فقط JSON مطابق schema برگردان.",
            text_format=self._json_schema_selection(),
            reasoning_effort="medium",
        )
        return self._parse_json_text(client, response)

    def _generate_implementation(
        self,
        request_text: str,
        selection: dict,
        base_sha: str,
        client: OpenAILunaClient,
    ) -> dict:
        selected = selection.get("files") if isinstance(selection.get("files"), list) else []
        contexts: list[str] = []
        total = 0
        for item in selected[:_MAX_SELECTED_FILES]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            action = str(item.get("action") or "update")
            if not self._path_allowed(path):
                raise BuilderError(f"مسیر پیشنهادی Builder مجاز نیست: {path}")
            if action == "create":
                block = f"\n--- FILE {path} (NEW) ---\n"
            else:
                content, _ = self.fetch_text_file(path, base_sha)
                block = f"\n--- FILE {path} (CURRENT) ---\n{content}\n--- END FILE ---\n"
            total += len(block)
            if total > _MAX_CONTEXT_CHARS:
                raise BuilderError("درخواست Builder برای یک تغییر خودکار بیش از حد بزرگ است؛ آن را به چند تغییر کوچک‌تر تقسیم کن.")
            contexts.append(block)
        prompt = (
            "درخواست کاربر:\n"
            f"{request_text}\n\n"
            "تغییر را کامل ولی محدود پیاده‌سازی کن. فایل‌های update باید محتوای کامل جایگزین داشته باشند. "
            "تست‌ها را قبل از فایل‌های implementation در آرایه files قرار بده. APIها و رفتار موجود را بی‌دلیل نشکن. "
            "هیچ secret یا کلیدی ننویس. هیچ shell/deploy code اضافه نکن.\n"
            + "".join(contexts)
        )
        response = client.create_response(
            input_items=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            model=client.complex_model,
            instructions="تو مهندس Builder پروژه بی‌خبر هستی. فقط JSON مطابق schema برگردان.",
            text_format=self._json_schema_implementation(),
            reasoning_effort="high",
        )
        return self._parse_json_text(client, response)

    def start_change(self, request_text: str, *, client: OpenAILunaClient | None = None) -> dict:
        if not str(request_text or "").strip():
            raise BuilderError("درخواست Builder خالی است.")
        if not self.connected:
            raise BuilderError("Builder هنوز به GitHub متصل نیست.")
        luna = client or get_luna_client()
        if not luna.connected:
            raise BuilderError("برای Builder، اتصال OpenAI هم لازم است.")

        base_sha = self.base_sha()
        paths = self.repository_paths(base_sha)
        selection = self._select_files(request_text, paths, luna)
        implementation = self._generate_implementation(request_text, selection, base_sha, luna)
        files = implementation.get("files") if isinstance(implementation.get("files"), list) else []
        if not files:
            raise BuilderError("Builder هیچ تغییر فایلی تولید نکرد.")

        normalized: list[dict] = []
        for row in files[:_MAX_SELECTED_FILES]:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            action = str(row.get("action") or "update")
            content = str(row.get("content") or "")
            if not self._path_allowed(path):
                raise BuilderError(f"مسیر خروجی Builder مجاز نیست: {path}")
            if not content.strip():
                raise BuilderError(f"Builder برای {path} محتوای خالی تولید کرد.")
            normalized.append({**row, "path": path, "action": action, "content": content})
        if not any(row["path"].startswith("tests/") for row in normalized):
            raise BuilderError("Builder برای این تغییر تست تولید نکرد؛ تغییر خودکار متوقف شد.")

        slug = str(selection.get("slug") or "change")
        branch = self.create_branch(base_sha=base_sha, slug=slug)
        changed: list[str] = []
        for row in sorted(normalized, key=lambda item: (0 if item["path"].startswith("tests/") else 1)):
            path = row["path"]
            action = row["action"]
            sha = ""
            if action == "update":
                _, sha = self.fetch_text_file(path, branch)
            self.put_file(
                branch=branch,
                path=path,
                content=row["content"],
                message=str(row.get("commit_message") or f"Luna Builder: update {path}"),
                sha=sha,
            )
            changed.append(path)

        title = str(implementation.get("title") or selection.get("title") or "Luna Builder change").strip()
        summary = str(implementation.get("summary_fa") or selection.get("summary_fa") or request_text).strip()
        tests = [str(value) for value in implementation.get("test_commands") or [] if str(value).strip()]
        body = (
            "## Luna Builder\n\n"
            f"درخواست: {request_text}\n\n"
            f"خلاصه: {summary}\n\n"
            "### فایل‌های تغییرکرده\n"
            + "\n".join(f"- `{path}`" for path in changed)
            + "\n\n### تست‌های پیشنهادی\n"
            + ("\n".join(f"- `{cmd}`" for cmd in tests) if tests else "- CI repository")
            + f"\n\nRollback base: `{base_sha}`\n"
        )
        pr = self.create_draft_pr(branch=branch, title=title, body=body)
        return {
            "ok": True,
            "message": "Builder تغییر را روی branch جدا ساخت و Draft PR ایجاد کرد.",
            "summary_fa": summary,
            "branch": branch,
            "base_sha": base_sha,
            "changed_files": changed,
            "test_commands": tests,
            "pull_request": pr,
        }
