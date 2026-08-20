"""The two LLM roles, both running on the Claude Agent SDK.

Interest separation is enforced structurally, not by prompt:
- Implementer: can edit files and run commands inside the workdir, but the
  workdir's push URL is disabled (see github.py) -- it cannot publish.
- Reviewer: read-only tools, fresh context every round, sees only the diff
  and the rulebook. It never knows how many rounds have happened.
"""

import json
import re
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

IMPLEMENTER_TOOLS = ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
REVIEWER_TOOLS = ["Read", "Grep", "Glob"]

IMPLEMENTER_SYSTEM = """You are the implementer agent of an automated PR pipeline.
Your job: address ONE review comment with the smallest correct change.
Rules:
- Modify files in the working tree only. NEVER run `git commit`, `git push`,
  or change git config/remotes. The orchestrator handles publishing.
- Run the project's tests if a test setup exists; fix failures you caused.
- If the comment is a question rather than a change request, make no edits
  and answer it in your final message."""

REVIEWER_SYSTEM = """You are a strict, independent code reviewer agent.
You did not write this change and have no stake in it. Judge only what you
see: the diff, the rulebook, and the repository context (read-only).
Be concrete: every rejection must cite the file/line and the reason or the
violated rule ID."""


async def _collect(prompt: str, options: ClaudeAgentOptions) -> str:
    """Run one agent session and return its final text output."""
    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
        elif isinstance(message, ResultMessage) and message.result:
            return message.result
    return "\n".join(chunks)


def _run(prompt: str, options: ClaudeAgentOptions) -> str:
    return anyio.run(_collect, prompt, options)


def run_implementer(
    workdir: Path,
    comment_body: str,
    comment_path: str | None,
    comment_line: int | None,
    reviewer_feedback: str = "",
) -> str:
    location = ""
    if comment_path:
        location = f"\nThe comment is anchored at: {comment_path}"
        if comment_line:
            location += f" line {comment_line}"
    feedback = (
        f"\n\nAn internal reviewer rejected your previous attempt. "
        f"Address these points as well:\n{reviewer_feedback}"
        if reviewer_feedback
        else ""
    )
    prompt = (
        f"Address this PR review comment:{location}\n\n"
        f"---\n{comment_body}\n---{feedback}"
    )
    options = ClaudeAgentOptions(
        cwd=str(workdir),
        system_prompt=IMPLEMENTER_SYSTEM,
        allowed_tools=IMPLEMENTER_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=50,
    )
    return _run(prompt, options)


def run_reviewer(workdir: Path, diff: str, rulebook: str) -> dict:
    prompt = (
        "Review the following diff against the rulebook. You may read the "
        "surrounding repository files for context.\n\n"
        f"## Rulebook\n{rulebook}\n\n"
        f"## Diff\n```diff\n{diff}\n```\n\n"
        'End your reply with ONLY a JSON object on the last line:\n'
        '{"pass": true|false, "issues": ["<file>:<reason>", ...]}'
    )
    options = ClaudeAgentOptions(
        cwd=str(workdir),
        system_prompt=REVIEWER_SYSTEM,
        allowed_tools=REVIEWER_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=25,
    )
    text = _run(prompt, options)
    return _parse_verdict(text)


def _parse_verdict(text: str) -> dict:
    """Extract the trailing JSON verdict; fail closed (reject) if unparsable."""
    matches = re.findall(r"\{[^{}]*\}", text, re.S)
    for candidate in reversed(matches):
        try:
            verdict = json.loads(candidate)
            if "pass" in verdict:
                verdict.setdefault("issues", [])
                return verdict
        except json.JSONDecodeError:
            continue
    return {"pass": False, "issues": ["reviewer output unparsable: " + text[-500:]]}
