from app.clock import instant
from app.records import group_by, integer, issue, token
from app.source import lines


def parse_team(record):
    raw = record["raw"]
    rate = raw.get("rate_per_km")
    if (not token(raw.get("team")) or not token(raw.get("name"))
            or not (rate is None or integer(rate, 0, 1_000_000))):
        return None
    return {**record, "team": raw["team"], "name": raw["name"], "rate_per_km": rate}


def parse_vehicle(record):
    raw = record["raw"]
    if not token(raw.get("vehicle")) or not token(raw.get("team")):
        return None
    return {**record, "vehicle": raw["vehicle"], "team": raw["team"]}


def parse_dispatch(record):
    raw = record["raw"]
    try:
        start, end = instant(raw.get("start")), instant(raw.get("end"))
    except ValueError:
        start = end = 0
    if (not token(raw.get("dispatch")) or not token(raw.get("team")) or not token(raw.get("road"))
            or raw.get("direction") not in ("+", "-") or not 0 < end - start <= 86400):
        return None
    return {**record, **{key: raw[key] for key in ("dispatch", "team", "road", "direction")},
            "start": start, "end": end}


def dedupe(rows, key, fields, conflict, duplicate, conflict_detail, duplicate_detail):
    """同键定义冲突全部隔离，完全相同的重复行只采信一行。"""
    kept, problems = [], []
    for group in group_by(rows, key).values():
        signature = {tuple(row[field] for field in fields) for row in group}
        if len(signature) > 1:
            problems.extend(issue(row, conflict, conflict_detail) for row in group)
            continue
        kept.append(group[0])
        problems.extend(issue(row, duplicate, duplicate_detail) for row in group[1:])
    return kept, problems


def load(source, routes):
    """读取可选名册表：班组册、车辆名册、支援单。缺表时返回空名册。"""
    problems = []
    parsed = {"teams": [], "vehicles": [], "dispatches": []}
    parsers = {"teams": (parse_team, "TEAM_SCHEMA", "班组编号、名称或公里单价无效"),
               "vehicles": (parse_vehicle, "VEHICLE_SCHEMA", "车辆或所属班组无效"),
               "dispatches": (parse_dispatch, "DISPATCH_SCHEMA", "支援单编号、班组、方向或时段无效")}
    for table, (parse, code, detail) in parsers.items():
        for record in lines(source, table):
            row = parse(record)
            if row is None:
                problems.append(issue(record, code, detail))
            else:
                parsed[table].append(row)
    teams, dup = dedupe(parsed["teams"], "team", ("name", "rate_per_km"),
                        "TEAM_CONFLICT", "TEAM_DUPLICATE", "同一班组编号定义冲突", "重复班组定义")
    problems.extend(dup)
    known = {row["team"] for row in teams} if "teams" in source else None
    vehicles, dup = dedupe(parsed["vehicles"], "vehicle", ("team",),
                           "VEHICLE_CONFLICT", "VEHICLE_DUPLICATE", "同一车辆归属班组冲突", "重复车辆登记")
    problems.extend(dup)
    dispatches, dup = dedupe(parsed["dispatches"], "dispatch", ("team", "road", "direction", "start", "end"),
                             "DISPATCH_CONFLICT", "DISPATCH_DUPLICATE", "同一支援单号定义冲突", "重复支援单")
    problems.extend(dup)
    lanes = {(row["road"], row["direction"]) for row in routes}
    registry = {"teams": {row["team"]: row for row in teams}, "vehicles": {}, "dispatches": []}
    for row in vehicles:
        if known is not None and row["team"] not in known:
            problems.append(issue(row, "VEHICLE_TEAM_UNKNOWN", "车辆所属班组不在班组册"))
        else:
            registry["vehicles"][row["vehicle"]] = row
    for row in dispatches:
        if known is not None and row["team"] not in known:
            problems.append(issue(row, "DISPATCH_TEAM_UNKNOWN", "支援单班组不在班组册"))
        elif (row["road"], row["direction"]) not in lanes:
            problems.append(issue(row, "DISPATCH_LANE_UNKNOWN", "支援单线路方向不在线路册"))
        else:
            registry["dispatches"].append(row)
    return registry, problems
