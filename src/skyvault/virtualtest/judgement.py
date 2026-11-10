"""final_judgement = continue, redesign, reject or require_external_simulation.

Important:
Pure. Checked in this order, the first that holds decides:

reject                       physically impossible and not worth engineering
                             (score below not_worth_below), or a fix that
                             needs a parameter moved by more than
                             max_fixable_change (or no fix at all)
redesign                     physically impossible but each fix is within
                             reach; or not worth investing (engineering below
                             worth_investing); or of no value in any mission
require_external_simulation  possible and worth it, but a margin is too close
                             to call, or the design is outside what the
                             rules cover
continue                     none of the above
"""

from typing import Any


def final_judgement(
    physics: dict[str, Any],
    engineering: dict[str, Any],
    tactical: dict[str, Any],
    external: dict[str, Any],
    triggers: list[dict[str, Any]],
    rules: dict[str, Any],
) -> dict[str, str]:
    """{status, reason}."""
    table = rules["engineering"]
    limit = float(rules["judgement"]["max_fixable_change"])
    fixes = [t for t in triggers if t["status"] == "impossible"]
    if physics["impossible_flags"]:
        flags = "; ".join(physics["impossible_flags"])
        if engineering["score"] < float(table["not_worth_below"]):
            return {
                "status": "reject",
                "reason": f"physically impossible ({flags}) and not worth engineering "
                f"(score {engineering['score']:.2f}: "
                f"{', '.join(engineering['bottlenecks']) or 'weak on every count'})",
            }
        too_far = [
            t
            for t in fixes
            if t["change"] is None
            or abs(float(t["change"])) > limit
            or t["required"] is None
        ]
        if too_far or not fixes:
            names = ", ".join(t["parameter"] for t in too_far) or "no lever"
            return {
                "status": "reject",
                "reason": f"physically impossible ({flags}); the fix needs more than "
                f"{limit:.0%} change ({names})",
            }
        moves = ", ".join(
            f"{t['parameter']} {t['current']} → {t['required']}" for t in fixes
        )
        return {
            "status": "redesign",
            "reason": f"physically impossible as specified ({flags}); within reach: "
            f"{moves}",
        }
    if engineering["score"] < float(table["worth_investing"]):
        return {
            "status": "redesign",
            "reason": f"possible, but not worth investing yet (engineering "
            f"{engineering['score']:.2f}: {', '.join(engineering['bottlenecks'])})",
        }
    if tactical.get("score") is not None and not tactical["useful_contexts"]:
        weak = ", ".join(tactical["weak_contexts"]) or "every context"
        return {
            "status": "redesign",
            "reason": f"possible and worth building, but no mission gained from it "
            f"(weak in {weak})",
        }
    if external["required"]:
        return {
            "status": "require_external_simulation",
            "reason": "possible and worth it, but physics-lite cannot decide: "
            + "; ".join(external["reasons"]),
        }
    useful = ", ".join(tactical.get("useful_contexts") or []) or "not tested"
    return {
        "status": "continue",
        "reason": f"possible (physics {physics['score']:.2f}), worth building "
        f"(engineering {engineering['score']:.2f}) and useful in {useful}",
    }
