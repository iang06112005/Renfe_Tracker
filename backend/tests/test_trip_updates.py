from trip_updates import enrich_with_trip_update, format_delay, parse_trip_updates


def test_parse_trip_updates_by_trip_id() -> None:
    payload = {
        "entity": [
            {
                "id": "TU1",
                "tripUpdate": {
                    "trip": {"tripId": "3004D23723C5"},
                    "delay": -120,
                    "stopTimeUpdate": [
                        {"stopId": "43002", "arrival": {"delay": -120, "time": "1793545257"}},
                    ],
                },
            },
            {"id": "empty"},
            {"id": "bad", "tripUpdate": {"trip": {}}},
        ]
    }
    updates = parse_trip_updates(payload)
    assert set(updates) == {"3004D23723C5"}
    update = updates["3004D23723C5"]
    assert update.delay == -120
    assert update.predicted_clock("43002") == 1793545257


def test_format_delay_readable_minutes() -> None:
    assert format_delay(0) == "En hora"
    assert format_delay(60) == "Retraso 1 min"
    assert format_delay(150) == "Retraso 2 min"
    assert format_delay(-120) == "Adelanto 2 min"
    assert format_delay(None) is None


def test_enrich_replaces_static_clock_with_prediction() -> None:
    fields = {
        "nextStop": "Brenes · 11:55",
        "_nextStopId": "43002",
        "previousStop": "El Cáñamo",
        "_previousStopId": "43001",
    }
    updates = parse_trip_updates(
        {
            "entity": [
                {
                    "tripUpdate": {
                        "trip": {"tripId": "trip-1"},
                        "delay": 180,
                        "stopTimeUpdate": [
                            {"stopId": "43002", "arrival": {"time": "1730372460", "delay": 180}},
                        ],
                    }
                }
            ]
        }
    )
    merged = enrich_with_trip_update(
        fields,
        stop_id="43002",
        status="IN_TRANSIT_TO",
        update=updates["trip-1"],
    )
    assert merged["delayLabel"] == "Retraso 3 min"
    assert merged["delaySeconds"] == 180
    assert merged["predictionsLabel"] == "Previsión Renfe"
    assert merged["nextStop"].startswith("Brenes · ")
    assert merged["nextStop"] != "Brenes · 11:55"
    assert merged["previousStop"] == "El Cáñamo"
    assert "_nextStopId" not in merged


def test_enrich_omits_missing_prediction_fields() -> None:
    merged = enrich_with_trip_update(
        {"route": "A – B"},
        stop_id="1",
        status="IN_TRANSIT_TO",
        update=None,
    )
    assert merged == {"route": "A – B"}
    assert "delayLabel" not in merged
    assert "predictionsLabel" not in merged
