"""Policy engine tests — security-sensitive, must stay green."""
from policies.engine import PolicyEngine
from policies.schemas import PolicyCheck


def check(tool, action, resource=""):
    return PolicyEngine().check(PolicyCheck(agent="t", tool=tool, action=action, resource=resource))


def test_private_denied():
    assert check("filesystem", "read", "/Private/x").decision.value == "DENY"
    assert check("filesystem", "write", "/Private/x").decision.value == "DENY"


def test_filesystem_scoping():
    assert check("filesystem", "write", "/Projects/a").decision.value == "ALLOW"
    assert check("filesystem", "write", "/elsewhere").decision.value == "APPROVAL_REQUIRED"


def test_git_merge_denied_commit_gated():
    assert check("git", "merge").decision.value == "DENY"
    assert check("git", "commit").decision.value == "APPROVAL_REQUIRED"
    assert check("git", "status").decision.value == "ALLOW"


def test_email_send_gated():
    assert check("email", "send").decision.value == "APPROVAL_REQUIRED"
    assert check("email", "draft").decision.value == "ALLOW"


def test_unknown_fails_closed():
    assert check("nope", "frob").decision.value == "APPROVAL_REQUIRED"
