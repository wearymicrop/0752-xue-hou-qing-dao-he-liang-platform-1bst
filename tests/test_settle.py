import json

from app.modules.m7_archive import service as archive
from app.pipeline import evaluate


def lane(result, road, direction):
    return next(row for row in result["settle"]["rows"]
                if row["road"] == road and row["direction"] == direction)


def test_dirty_settlement_totals(dirty_result):
    assert dirty_result["settle"]["totals"] == {"covered_m": 3049, "settled_m": 1569, "review_m": 1480,
        "self_m": 1369, "support_m": 200, "amount_fen": 13352, "unpriced_m": 0, "lanes": 8, "teams": 2}
    assert dirty_result["settle"]["status"] == "REVIEW_REQUIRED"


def test_support_with_dispatch_settles_to_external_team(dirty_result):
    part = lane(dirty_result, "S07", "+")["parts"][0]
    assert (part["state"], part["team"], part["mode"]) == ("settled", "迅洁队", "support")
    assert part["basis"]["dispatch"] == "援单-01" and part["basis"]["dispatch_line"] == 1
    assert part["basis"]["vehicles"] == ["云扫-08"]


def test_support_without_dispatch_goes_to_review(dirty_result):  # TRAP-27
    part = lane(dirty_result, "S01", "+")["parts"][0]
    assert part["state"] == "review" and part["m"] == 780
    assert {reason["code"] for reason in part["reasons"]} == {"SUPPORT_UNVERIFIED"}
    assert part["basis"]["vehicles"] == ["云扫-01", "云扫-02"]  # 证据保留供人工裁定
    assert "SUPPORT_UNVERIFIED" in dirty_result["settle"]["reasons"]


def test_unregistered_vehicle_goes_to_review(dirty_result):
    part = lane(dirty_result, "S03", "+")["parts"][0]
    assert part["state"] == "review" and part["reasons"][0]["code"] == "VEHICLE_UNKNOWN"


def test_clean_all_settled_with_amount(clean_result):
    settle = clean_result["settle"]
    assert settle["status"] == "SETTLED" and settle["totals"]["review_m"] == 0
    assert settle["teams"] == [{"team": "一班", "name": "松岚一班", "self_m": 5265, "support_m": 0,
                                "settled_m": 5265, "rate_per_km": 80, "amount_fen": 42120}]


def test_missing_registry_all_review(clean):
    for table in ("teams", "vehicles", "dispatches"):
        clean.pop(table)
    settle = evaluate(clean)["settle"]
    assert settle["status"] == "REVIEW_REQUIRED"
    assert settle["totals"]["settled_m"] == 0 and settle["totals"]["review_m"] == 5265
    assert settle["totals"]["amount_fen"] is None
    assert settle["reasons"] == {"REGISTRY_MISSING": 8}


def test_conflicting_vehicle_registry_quarantined(clean):  # TRAP-29
    clean["teams"].append({"team": "迅洁队", "name": "迅洁外援队", "rate_per_km": 120})
    clean["vehicles"].append({"vehicle": "净-01", "team": "迅洁队"})
    settle = evaluate(clean)["settle"]
    assert settle["reasons"]["VEHICLE_CONFLICT"] == 2
    part = lane({"settle": settle}, "S01", "+")["parts"][0]
    assert part["state"] == "review" and part["reasons"][0]["code"] == "VEHICLE_UNKNOWN"


def test_road_without_team_goes_to_review(clean):
    del clean["roads"][0]["team"]
    part = lane(evaluate(clean), "S01", "+")["parts"][0]
    assert part["state"] == "review" and part["reasons"][0]["code"] == "ROAD_TEAM_MISSING"


def test_dispatch_outside_work_time_not_matched(clean):
    clean["teams"].append({"team": "迅洁队", "name": "迅洁外援队", "rate_per_km": 120})
    clean["vehicles"][0]["team"] = "迅洁队"
    clean["dispatches"].append({"dispatch": "援单-02", "team": "迅洁队", "road": "S01", "direction": "+",
                                "start": "2026-01-17T06:10:00+08:00", "end": "2026-01-17T06:16:00+08:00"})
    part = lane(evaluate(clean), "S01", "+")["parts"][0]
    assert part["state"] == "review" and part["reasons"][0]["code"] == "SUPPORT_UNVERIFIED"


def test_shared_interval_attribution_conflict(clean):  # TRAP-28
    clean["teams"].append({"team": "迅洁队", "name": "迅洁外援队", "rate_per_km": 120})
    clean["vehicles"].append({"vehicle": "净-09", "team": "迅洁队"})
    clean["points"] += [{**point, "vehicle": "净-09"} for point in clean["points"] if point["vehicle"] == "净-01"]
    clean["dispatches"].append({"dispatch": "援单-03", "team": "迅洁队", "road": "S01", "direction": "+",
                                "start": "2026-01-17T06:00:00+08:00", "end": "2026-01-17T06:16:00+08:00"})
    part = lane(evaluate(clean), "S01", "+")["parts"][0]
    assert part["state"] == "review"
    assert {reason["code"] for reason in part["reasons"]} == {"ATTRIBUTION_CONFLICT"}


def test_same_team_overlap_not_billed_twice(clean):
    clean["vehicles"].append({"vehicle": "净-09", "team": "一班"})
    clean["points"] += [{**point, "vehicle": "净-09"} for point in clean["points"] if point["vehicle"] == "净-01"]
    totals = evaluate(clean)["settle"]["totals"]
    assert totals["settled_m"] == 5265 and totals["self_m"] == 5265  # 区间并集，不重复计价


def test_settlement_is_deterministic(clean):
    assert evaluate(clean)["settle"] == evaluate(clean)["settle"]


def test_registry_version_pins_team_and_lanes(clean):
    base = evaluate(clean)["settle"]["versions"]
    assert base["ruleset"] == "gb-0752/1.0"
    changed = json.loads(json.dumps(clean))
    changed["teams"][0]["rate_per_km"] = 100
    assert evaluate(changed)["settle"]["versions"]["registry_sha256"] != base["registry_sha256"]


def test_empty_batch_has_explicit_state(clean):
    clean["roads"] = []
    settle = evaluate(clean)["settle"]
    assert settle["status"] == "SETTLED" and settle["totals"]["lanes"] == 0


def test_optional_tables_validated(client, clean):
    assert client.post("/api/runs", json={"source": {**clean, "teams": {"team": "一班"}}}).json()["code"] == "BAD_TABLE"
    assert client.post("/api/runs", json={"source": {**clean, "bribes": []}}).json()["code"] == "BAD_SCHEMA"


def test_rerun_keeps_verified_attribution(client, dirty):  # TRAP-30
    first = client.post("/api/runs", json={"source": dirty}).json()
    again = client.post(f'/api/runs/{first["id"]}/rerun').json()
    assert again["reused"] and again["manifest"]["digest"] == first["manifest"]["digest"]
    assert again["result"]["settle"] == first["result"]["settle"]


def test_resume_repost_not_billed_twice(client, dirty):
    first = client.post("/api/runs", json={"source": dirty}).json()
    resumed = client.post("/api/runs", json={"source": dirty}).json()
    assert resumed["reused"] and resumed["result"]["settle"]["totals"] == first["result"]["settle"]["totals"]
    assert len(client.get("/api/runs").json()["runs"]) == 1


def test_failed_recalculate_keeps_previous_settlement(client, dirty, monkeypatch):
    first = client.post("/api/runs", json={"source": dirty}).json()
    monkeypatch.setattr(archive, "evaluate", lambda source: {"tampered": True})
    response = client.post("/api/runs", json={"source": dirty})
    assert response.status_code == 409 and response.json()["code"] == "REPLAY_MISMATCH"
    kept = client.get(f'/api/runs/{first["id"]}').json()
    assert kept["result"]["settle"] == first["result"]["settle"]


def test_signature_binds_settlement_status(client, dirty):
    first = client.post("/api/runs", json={"source": dirty}).json()
    client.post(f'/api/runs/{first["id"]}/sign',
                json={"reviewer": "周洁", "digest": first["manifest"]["digest"]})
    receipt = client.get(f'/api/runs/{first["id"]}').json()["signature"]
    assert receipt["settlement"] == "REVIEW_REQUIRED" and receipt["balance"] == "MATCHED"
