"""Sandboxed filesystem tool: confined to workspace root, no absolute escapes."""
from __future__ import annotations

from pathlib import Path

from tools.schemas import RiskLevel, ToolResult, ToolSpec

SPEC = ToolSpec(name="filesystem", description="Read/write files inside the AETHER workspace",
                required_permissions=["filesystem:read", "filesystem:write"],
                risk_level=RiskLevel.MEDIUM)


def _resolve(root: Path, resource: str) -> Path:
    p = (root / resource.lstrip("/")).resolve()
    if p != root.resolve() and root.resolve() not in p.parents:
        raise PermissionError(f"Path escapes workspace: {resource}")
    return p


async def execute(action: str, args: dict, resource: str, workspace: str) -> ToolResult:
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    try:
        if action == "read":
            target = _resolve(root, resource or args.get("path", ""))
            if not target.is_file():
                return ToolResult(ok=False, error=f"Not a file: {resource}")
            return ToolResult(ok=True, output={"path": str(target.relative_to(root)),
                                               "content": target.read_text()[:20000]})
        if action == "write":
            target = _resolve(root, resource or args.get("path", ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.get("content", ""))
            return ToolResult(ok=True, output={"path": str(target.relative_to(root)), "bytes": len(args.get("content", ""))})
        if action == "list":
            target = _resolve(root, resource or args.get("path", "/"))
            if not target.exists():
                return ToolResult(ok=False, error=f"Not found: {resource}")
            items = [f"{'d' if x.is_dir() else 'f'} {x.name}" for x in sorted(target.iterdir())]
            return ToolResult(ok=True, output={"path": resource or "/", "items": items[:200]})
        if action == "delete":
            target = _resolve(root, resource or args.get("path", ""))
            if target.is_file():
                target.unlink()
                return ToolResult(ok=True, output={"deleted": resource})
            return ToolResult(ok=False, error="Only file delete supported in MVP")
        return ToolResult(ok=False, error=f"Unknown filesystem action: {action}")
    except PermissionError as e:
        return ToolResult(ok=False, error=str(e))
    except Exception as e:
        return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
