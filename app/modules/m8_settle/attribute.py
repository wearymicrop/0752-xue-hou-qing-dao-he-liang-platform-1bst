from app.clock import instant


def describe(part, registry):
    """汇总区间证据，供结算页展示归属依据。"""
    refs = part["references"]
    return {"vehicles": sorted({ref["vehicle"] for ref in refs}),
            "track_lines": [[ref["line"], ref["end_line"]] for ref in refs],
            "window_lines": sorted({line for ref in refs for line in ref["window_lines"]}),
            "vehicle_lines": sorted({registry["vehicles"][ref["vehicle"]]["line"]
                                     for ref in refs if ref["vehicle"] in registry["vehicles"]}),
            "dispatch": None, "dispatch_line": None}


def add_reason(reasons, code, detail):
    if (code, detail) not in reasons:
        reasons.append((code, detail))


def covers(dispatch, team, road, direction, start, end):
    return (dispatch["team"] == team and dispatch["road"] == road
            and dispatch["direction"] == direction and dispatch["start"] <= start and end <= dispatch["end"])


def attribute(part, lane_team, registry):
    """裁定一段已覆盖区间的结算归属。

    自营：车辆所属班组即路段责任班组；支援：跨班组且有时段方向匹配的支援单。
    任何证据未核清（车辆未登记、无责任班组、无支援单、多班组同段）都只列待复核。
    """
    reasons, candidates = [], {}
    for ref in part["references"]:
        record = registry["vehicles"].get(ref["vehicle"])
        if record is None:
            add_reason(reasons, "VEHICLE_UNKNOWN", f"车辆 {ref['vehicle']} 未登记车辆名册")
            continue
        team = record["team"]
        if lane_team is None:
            add_reason(reasons, "ROAD_TEAM_MISSING", "线路册未登记责任班组")
            continue
        if team == lane_team:
            candidates.setdefault((team, "self", None), []).append(ref)
            continue
        dispatch = next((row for row in registry["dispatches"] if covers(
            row, team, ref["road"], ref["direction"], instant(ref["start"]), instant(ref["end"]))), None)
        if dispatch is None:
            add_reason(reasons, "SUPPORT_UNVERIFIED", f"车辆 {ref['vehicle']} 跨班组作业缺少有效支援单")
            continue
        candidates.setdefault((team, "support", dispatch["dispatch"]), []).append(ref)
    basis = describe(part, registry)
    if reasons or len(candidates) != 1:
        if len(candidates) > 1:
            add_reason(reasons, "ATTRIBUTION_CONFLICT", "同一区间多班组覆盖，归属待裁定")
        return {"state": "review", "team": None, "mode": None, "basis": basis,
                "reasons": [{"code": code, "detail": detail} for code, detail in reasons]}
    (team, mode, dispatch_id), _refs = next(iter(candidates.items()))
    if dispatch_id is not None:
        row = next(row for row in registry["dispatches"] if row["dispatch"] == dispatch_id)
        basis = {**basis, "dispatch": dispatch_id, "dispatch_line": row["line"]}
    return {"state": "settled", "team": team, "mode": mode, "basis": basis, "reasons": []}
