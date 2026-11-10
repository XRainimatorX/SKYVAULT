"""Rule set = the named parameters a world's rules are tuned by."""

from collections.abc import Iterator, Mapping
from typing import Any


class RuleSet(Mapping[str, Any]):
    """
    Read-only access to world_contract.rule_set.

    Important:
    Phase 2 only stores and serves the parameters (a convoy size limit, a
    movement cost). The rules that act on them — what an action may do and
    what it causes — are the Phase 3 action framework. Keeping the parameters
    in the world contract means a scenario can change them without code.

    require() raises KeyError for a missing rule, so a scenario that forgot a
    parameter fails loudly instead of running on a silent default.
    """

    def __init__(self, rules: Mapping[str, Any] | None = None) -> None:
        self._rules: dict[str, Any] = dict(rules or {})

    def require(self, name: str) -> Any:
        if name not in self._rules:
            raise KeyError(f"Missing rule: {name}")
        return self._rules[name]

    def as_dict(self) -> dict[str, Any]:
        return dict(self._rules)

    def __getitem__(self, name: str) -> Any:
        return self._rules[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)
