from fractions import Fraction

from app.codec import digest
from app.config import RULESET
from app.records import issue, report
from .attribute import attribute, describe
from .registry import load

REGISTRY_TABLES = ("teams", "vehicles", "dispatches")


def amount_fen(meters, rate_per_km):
    """里程折金额（分），分数精确折算后向最近分取整。无单价则不计金额。"""
    if rate_per_km is None:
        return None
    return int(Fraction(meters * rate_per_km, 10) + Fraction(1, 2))


def settle(source, sections):
    registry, problems = load(source, sections["routes"]["rows"])
    provided = any(table in source for table in REGISTRY_TABLES)
    rows, teams = [], {}
    covered_m = settled_m = review_m = self_m = support_m = 0
    for lane in sections["coverage"]["rows"]:
        parts, lane_settled, lane_review = [], 0, 0
        for part in lane["parts"]:
            if part["kind"] != "covered":
                continue
            covered_m += part["m"]
            if provided:
                verdict = attribute(part, lane.get("team"), registry)
            else:
                verdict = {"state": "review", "team": None, "mode": None,
                           "basis": describe(part, registry),
                           "reasons": [{"code": "REGISTRY_MISSING", "detail": "未提供班组名册，归属无法核清"}]}
            anchor = {"table": "points", "line": part["references"][0]["line"],
                      "end_line": part["references"][0]["end_line"]}
            for reason in verdict["reasons"]:
                problems.append(issue(anchor, reason["code"],
                                      f"{lane['road']}·{lane['direction']} 向 {part['from_m']}–{part['to_m']} 米：{reason['detail']}"))
            if verdict["state"] == "settled":
                lane_settled += part["m"]
                settled_m += part["m"]
                bucket = teams.setdefault(verdict["team"], {"self_m": 0, "support_m": 0})
                bucket["self_m" if verdict["mode"] == "self" else "support_m"] += part["m"]
                if verdict["mode"] == "self":
                    self_m += part["m"]
                else:
                    support_m += part["m"]
            else:
                lane_review += part["m"]
                review_m += part["m"]
            parts.append({"from_m": part["from_m"], "to_m": part["to_m"], "m": part["m"],
                          "state": verdict["state"], "team": verdict["team"], "mode": verdict["mode"],
                          "basis": verdict["basis"], "reasons": verdict["reasons"]})
        rows.append({"road": lane["road"], "direction": lane["direction"], "name": lane["name"],
                     "team": lane.get("team"), "settled_m": lane_settled, "review_m": lane_review,
                     "parts": parts})
    team_rows = []
    for team_id, bucket in sorted(teams.items()):
        meta = registry["teams"].get(team_id)
        rate = meta["rate_per_km"] if meta else None
        settled = bucket["self_m"] + bucket["support_m"]
        team_rows.append({"team": team_id, "name": meta["name"] if meta else team_id, **bucket,
                          "settled_m": settled, "rate_per_km": rate, "amount_fen": amount_fen(settled, rate)})
    amounts = [row["amount_fen"] for row in team_rows if row["amount_fen"] is not None]
    totals = {"covered_m": covered_m, "settled_m": settled_m, "review_m": review_m,
              "self_m": self_m, "support_m": support_m,
              "amount_fen": sum(amounts) if amounts else None,
              "unpriced_m": sum(row["settled_m"] for row in team_rows if row["amount_fen"] is None),
              "lanes": len(rows), "teams": len(team_rows)}
    versions = {"ruleset": RULESET,
                "registry_sha256": digest({"roads": source["roads"],
                                           **{table: source.get(table, []) for table in REGISTRY_TABLES}})}
    return report(rows, problems, teams=team_rows, totals=totals, versions=versions,
                  status="SETTLED" if review_m == 0 else "REVIEW_REQUIRED")
