"""Central tool registry. All execution flows through `run()` → policy → audit."""
from __future__ import annotations

from core.config import get_settings
from policies.engine import PolicyEngine
from policies.schemas import PolicyCheck
from tools import filesystem, git_tool, stubs
from tools.schemas import ToolResult, ToolSpec


class ToolRegistry:
    def __init__(self, policy: PolicyEngine | None = None):
        self.policy = policy or PolicyEngine()
        self.specs: dict[str, ToolSpec] = {
            "filesystem": filesystem.SPEC,
            "git": git_tool.SPEC,
            "github": stubs.GITHUB_SPEC,
            "web": stubs.WEB_SPEC,
            "calendar": stubs.CALENDAR_SPEC,
            "notes": stubs.NOTES_SPEC,
            "email": stubs.EMAIL_SPEC,
        }

    def list(self) -> list[ToolSpec]:
        return list(self.specs.values())

    async def run(self, agent: str, tool: str, action: str, args: dict | None = None,
                  resource: str = "", reason: str = "",
                  audit=None, execution_id: str = ""):
        """Policy-gated dispatch. Returns (result, policy_result). Never bypass."""
        from audit.service import AuditService  # lazy to avoid cycles

        args = args or {}
        check = PolicyCheck(agent=agent, tool=tool, action=action, resource=resource, reason=reason)
        verdict = self.policy.check(check)
        if audit is not None:
            await audit.record(execution_id=execution_id, agent=agent, action=f"{tool}.{action}",
                               resource=resource, permission=verdict.decision.value,
                               reason=verdict.reason or reason,
                               status="denied" if verdict.decision.value == "DENY" else "checked")
        if verdict.decision.value == "DENY":
            return ToolResult(ok=False, error=f"Denied by policy: {verdict.reason}"), verdict
        if verdict.decision.value == "APPROVAL_REQUIRED":
            return ToolResult(ok=False, error=f"Approval required: {verdict.reason}"), verdict
        settings = get_settings()
        name = tool.lower()
        if name == "filesystem":
            res = await filesystem.execute(action, args, resource, settings.workspace_root)
        elif name == "git":
            res = await git_tool.execute(action, args, resource, settings.git_allowlist)
        elif name == "github":
            res = await stubs.github_execute(action, args, resource)
        elif name == "web":
            res = await stubs.web_execute(action, args, resource)
        elif name == "calendar":
            res = await stubs.calendar_execute(action, args, resource)
        elif name == "notes":
            res = await stubs.notes_execute(action, args, resource)
        elif name == "email":
            res = await stubs.email_execute(action, args, resource)
        else:
            res = ToolResult(ok=False, error=f"Unknown tool: {tool}")
            return res, verdict
        if audit is not None:
            await audit.record(execution_id=execution_id, agent=agent, action=f"{tool}.{action}",
                               resource=resource, permission=verdict.decision.value,
                               reason="executed", status="ok" if res.ok else "error")
        return res, verdict
