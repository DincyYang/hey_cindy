from local.normalizer import NormalizedResult
from local.decision import decide_from_result


def make_result(normalized, category, confidence=0.9, reason="test"):
    return NormalizedResult(
        normalized=normalized,
        confidence=confidence,
        category=category,
        reason=reason,
        cleaned_text="test",
    )


class TestDecideFromResult:

    def test_execute_on(self):
        d = decide_from_result(make_result("on", "clear"))
        assert d.action == "execute"
        assert d.command == "on"

    def test_execute_off(self):
        d = decide_from_result(make_result("off", "clear"))
        assert d.action == "execute"
        assert d.command == "off"

    def test_clarify_on_conflict(self):
        d = decide_from_result(make_result("unknown", "conflict", 0.0))
        assert d.action == "clarify"
        assert d.command is None

    def test_clarify_on_ambiguous(self):
        d = decide_from_result(make_result("unknown", "ambiguous", 0.0))
        assert d.action == "clarify"

    def test_reject_negated(self):
        d = decide_from_result(make_result("unknown", "negated", 0.0))
        assert d.action == "reject"

    def test_ignore_unrelated(self):
        d = decide_from_result(make_result("unknown", "unrelated", 0.0))
        assert d.action == "ignore"
