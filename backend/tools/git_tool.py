"""Git tool: allowlisted repos, read-only cmds free, mutation via subprocess (no shell)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from tools.schemas import RiskLevel, ToolResult, ToolSpec

SPEC = ToolSpec(name="git", description="Inspect and manage allowlisted git repositories",
                required_permissions=["git:read", "git:write"], risk_level=RiskLevel.MEDIUM)

_READONLY = {"status", "log", "diff"}
_WRITES = {"branch", "commit"}


def _repo_ok(repo: str, allowlist: str) -> Path | None:
    p = Path(repo).resolve()
    for scope in allowlist.split(","):
        scope = scope.strip()
        if not scope:
            continue
        try:
            if p == Path(scope).resolve() or Path(scope).resolve() in p.parents:
                if (p / ".git").exists():
                    return p
        except Exception:
            continue
    return None


async def _run(repo: Path, *args: str) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    text = (out or b"").decode(errors="replace")[:8000]
    return (proc.returncode == 0), text


async def execute(action: str, args: dict, resource: str, allowlist: str) -> ToolResult:
    repo = _repo_ok(resource or args.get("repo", ""), allowlist)
    if repo is None:
        return ToolResult(ok=False, error="Repo not in allowlist or not a git repo")
    try:
        if action in _READONLY:
            flag = {"status": ["status", "--short", "--branch"],
                    "log": ["log", "--oneline", "-15"],
                    "diff": ["diff", "--stat"]}[action]
            ok, out = await _run(repo, *flag)
            return ToolResult(ok=ok, output={"repo": str(repo), "output": out})
        if action == "branch":
            ok, out = await _run(repo, "checkout", "-b", args.get("name", "aether/work"))
            return ToolResult(ok=ok, output={"output": out})
        if action == "commit":
            ok1, o1 = await _run(repo, "add", "-A")
            if not ok1:
                return ToolResult(ok=False, error=o1)
            ok2, o2 = await _run(repo, "commit", "-m", args.get("message", "aether: checkpoint"))
            return ToolResult(ok=ok2, output={"output": o2})
        return ToolResult(ok=False, error=f"Unsupported git action: {action} (push/merge gated by policy)")
    except Exception as e:
        return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
