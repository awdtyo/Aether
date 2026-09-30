"""Rule-based policy engine. Deterministic, tested, LLM cannot override."""
from __future__ import annotations

from policies.schemas import Decision, PolicyCheck, PolicyResult


class PolicyEngine:
    """First matching rule wins. Default: approval-required (fail closed)."""

    def __init__(self):
        # (tool, action_prefix, resource_scope, decision, reason)
        self.rules: list[tuple[str, str, str, Decision, str]] = [
            ("filesystem", "read", "/Private", Decision.DENY, "Private area is denied"),
            ("filesystem", "write", "/Private", Decision.DENY, "Private area is denied"),
            ("filesystem", "read", "", Decision.ALLOW, "Filesystem read within workspace allowed"),
            ("filesystem", "write", "/Projects", Decision.ALLOW, "Project writes allowed"),
            ("filesystem", "write", "/Research", Decision.ALLOW, "Research writes allowed"),
            ("filesystem", "write", "", Decision.APPROVAL_REQUIRED, "Writes outside Projects/Research need approval"),
            ("filesystem", "delete", "", Decision.APPROVAL_REQUIRED, "Deletes need approval"),
            ("git", "status", "", Decision.ALLOW, "Read-only git allowed"),
            ("git", "log", "", Decision.ALLOW, "Read-only git allowed"),
            ("git", "diff", "", Decision.ALLOW, "Read-only git allowed"),
            ("git", "branch", "", Decision.ALLOW, "Branch creation allowed"),
            ("git", "commit", "", Decision.APPROVAL_REQUIRED, "Commits need approval"),
            ("git", "push", "", Decision.APPROVAL_REQUIRED, "Push needs approval"),
            ("git", "merge", "", Decision.DENY, "Merges denied by policy"),
            ("github", "read", "", Decision.ALLOW, "GitHub reads allowed"),
            ("github", "branch", "", Decision.ALLOW, "GitHub branch allowed"),
            ("github", "commit", "", Decision.APPROVAL_REQUIRED, "GitHub commit needs approval"),
            ("github", "merge", "", Decision.DENY, "GitHub merge denied"),
            ("email", "read", "", Decision.ALLOW, "Email read allowed"),
            ("email", "draft", "", Decision.ALLOW, "Email draft allowed"),
            ("email", "send", "", Decision.APPROVAL_REQUIRED, "External send needs approval"),
            ("calendar", "read", "", Decision.ALLOW, "Calendar read allowed"),
            ("calendar", "create", "", Decision.ALLOW, "Calendar create allowed"),
            ("calendar", "delete", "", Decision.APPROVAL_REQUIRED, "Calendar delete needs approval"),
            ("web", "search", "", Decision.ALLOW, "Web search allowed"),
            ("notes", "read", "", Decision.ALLOW, "Notes read allowed"),
            ("notes", "write", "", Decision.ALLOW, "Notes write allowed"),
        ]

    def check(self, req: PolicyCheck) -> PolicyResult:
        tool, action, resource = req.tool.lower(), req.action.lower(), req.resource or ""
        for rtool, raction, rscope, decision, reason in self.rules:
            if rtool != tool:
                continue
            if not action.startswith(raction):
                continue
            if rscope and rscope not in resource:
                continue
            return PolicyResult(decision=decision, reason=reason)
        return PolicyResult(decision=Decision.APPROVAL_REQUIRED,
                            reason="No explicit rule: fail closed, approval required")
