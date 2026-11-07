"""ContractError = the one way any contract reports that data broke it."""


class ContractError(ValueError):
    """
    Raised when data does not satisfy a contract.

    Important:
    It carries every violation found, not just the first one, so a caller can
    fix a malformed scenario in one pass instead of one error at a time.

    It subclasses ValueError, so code that already catches ValueError for a bad
    scenario keeps working.
    """

    def __init__(self, contract: str, errors: list[str]) -> None:
        self.contract = contract
        self.errors = errors
        super().__init__(f"{contract} contract violated: " + "; ".join(errors))
