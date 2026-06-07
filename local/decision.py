# decision.py
"""Action policy: map a classified intent to what the assistant should do.

Kept separate from the classifier so the policy can be tested without the LLM
and so "clarify" / "reject" behaviour is driven by the classifier's category
code rather than free-text reasons.
"""
from dataclasses import dataclass
from typing import Optional

from local.normalizer import NormalizedResult


@dataclass(frozen=True)
class Decision:
    action: str               # "execute" | "clarify" | "reject" | "ignore"
    command: Optional[str]    # "on" | "off" | None
    message: str
    reason: str


def decide_from_result(result: NormalizedResult) -> Decision:
    # 1) Actionable command from the classifier.
    if result.normalized in ("on", "off"):
        return Decision(
            action="execute",
            command=result.normalized,
            message=f"Turning the light {result.normalized}.",
            reason=result.reason,
        )

    # 2) Not actionable — branch on the category the classifier returned.
    if result.category == "conflict":
        return Decision(
            action="clarify",
            command=None,
            message="I heard both on and off. Please say just one command.",
            reason=result.reason,
        )

    if result.category == "negated":
        return Decision(
            action="reject",
            command=None,
            message="I heard a negated command, so I will not execute it.",
            reason=result.reason,
        )

    if result.category == "ambiguous":
        return Decision(
            action="clarify",
            command=None,
            message="Did you want the light on or off?",
            reason=result.reason,
        )

    # 3) Anything else: don't act.
    return Decision(
        action="ignore",
        command=None,
        message="I did not understand the command.",
        reason=result.reason,
    )
