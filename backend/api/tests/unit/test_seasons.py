from rest_framework.test import APIClient

from api.tests.conftest import register

SEASONS = "/api/seasons"
REPORTING_PERIODS = "/api/reporting-periods"


def second_user(email="other@agrivanta.test"):
    client = APIClient()
    response = register(client, email=email)
    assert response.status_code == 201, response.data
    token = response.data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, response.data


def season_payload(**overrides):
    payload = {
        "name": "Winter 2025/26",
        "startDate": "2025-10-01",
        "endDate": "2026-04-30",
    }
    payload.update(overrides)
    return payload


def period_payload(**overrides):
    payload = {
        "name": "Q1 2026",
        "startDate": "2026-01-01",
        "endDate": "2026-03-31",
    }
    payload.update(overrides)
    return payload


def test_season_spans_two_calendar_years_and_year_is_optional(client):
    created = client.post(
        SEASONS, season_payload(year=2025), format="json"
    )
    assert created.status_code == 201, created.data
    season = created.data
    assert season["name"] == "Winter 2025/26"
    assert season["startDate"] == "2025-10-01"
    assert season["endDate"] == "2026-04-30"
    assert season["year"] == 2025
    assert season["farmId"] == client.get("/api/farm").data["id"]

    no_year = client.post(
        SEASONS,
        season_payload(
            name="Summer 2026",
            startDate="2026-05-01",
            endDate="2026-09-30",
        ),
        format="json",
    )
    assert no_year.status_code == 201, no_year.data
    assert "year" not in no_year.data

    detail = client.get(f"{SEASONS}/{no_year.data['id']}")
    assert detail.status_code == 200
    assert detail.data["startDate"] == "2026-05-01"
    assert detail.data["endDate"] == "2026-09-30"
    assert "year" not in detail.data


def test_reporting_period_crud_and_optional_year(client):
    created = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    )
    assert created.status_code == 201, created.data
    period = created.data
    assert period["name"] == "Q1 2026"
    assert period["startDate"] == "2026-01-01"
    assert period["endDate"] == "2026-03-31"
    assert "year" not in period
    assert period["farmId"] == client.get("/api/farm").data["id"]

    listed = client.get(REPORTING_PERIODS)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.data] == [period["id"]]

    detail = client.get(f"{REPORTING_PERIODS}/{period['id']}")
    assert detail.status_code == 200
    assert detail.data["id"] == period["id"]

    updated = client.put(
        f"{REPORTING_PERIODS}/{period['id']}",
        {
            "name": "First quarter 2026",
            "startDate": "2026-01-01",
            "endDate": "2026-03-31",
            "year": 2026,
        },
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["name"] == "First quarter 2026"
    assert updated.data["year"] == 2026


def test_end_before_start_is_rejected_for_both_models(client):
    for endpoint in (SEASONS, REPORTING_PERIODS):
        response = client.post(
            endpoint,
            {
                "name": "Backwards",
                "startDate": "2026-05-01",
                "endDate": "2026-04-30",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["field"] == "endDate"
        assert "before" in response.data["detail"].lower()


def test_end_before_start_is_rejected_on_update(client):
    season = client.post(SEASONS, season_payload(), format="json").data
    period = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    ).data

    for endpoint, record in (
        (SEASONS, season),
        (REPORTING_PERIODS, period),
    ):
        response = client.put(
            f"{endpoint}/{record['id']}",
            {
                "name": record["name"],
                "startDate": "2026-05-01",
                "endDate": "2026-04-30",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.data["field"] == "endDate"


def test_overlapping_seasons_are_allowed_and_both_listed(client):
    first = client.post(
        SEASONS, season_payload(), format="json"
    )
    second = client.post(
        SEASONS,
        season_payload(
            name="Winter extended",
            startDate="2026-03-01",
            endDate="2026-07-31",
        ),
        format="json",
    )
    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data

    listed = client.get(SEASONS)
    assert listed.status_code == 200
    assert {item["id"] for item in listed.data} == {
        first.data["id"],
        second.data["id"],
    }
    assert len(listed.data) == 2


def test_duplicate_name_rejected_on_same_farm_but_allowed_elsewhere(client):
    first = client.post(SEASONS, season_payload(), format="json")
    assert first.status_code == 201

    duplicate = client.post(SEASONS, season_payload(), format="json")
    assert duplicate.status_code == 400
    assert duplicate.data["field"] == "name"
    assert "already exists" in duplicate.data["detail"].lower()

    first_period = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    )
    assert first_period.status_code == 201

    duplicate_period = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    )
    assert duplicate_period.status_code == 400
    assert duplicate_period.data["field"] == "name"
    assert "already exists" in duplicate_period.data["detail"].lower()

    other_client, _ = second_user()
    other_season = other_client.post(
        SEASONS, season_payload(), format="json"
    )
    other_period = other_client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    )
    assert other_season.status_code == 201, other_season.data
    assert other_period.status_code == 201, other_period.data


def test_create_with_nonexistent_farm_returns_4xx(client):
    missing_farm = "00000000-0000-0000-0000-000000000000"
    for endpoint, payload in (
        (SEASONS, season_payload(farmId=missing_farm)),
        (REPORTING_PERIODS, period_payload(farmId=missing_farm)),
    ):
        response = client.post(endpoint, payload, format="json")
        assert response.status_code in (400, 404)
        assert response.data["field"] == "farmId"
        assert "does not exist" in response.data["detail"].lower()


def test_create_with_another_users_farm_is_forbidden(client):
    other_client, _ = second_user()
    other_farm_id = other_client.get("/api/farm").data["id"]

    for endpoint, payload in (
        (SEASONS, season_payload(farmId=other_farm_id)),
        (REPORTING_PERIODS, period_payload(farmId=other_farm_id)),
    ):
        response = client.post(endpoint, payload, format="json")
        assert response.status_code == 403
        assert response.data["field"] == "farmId"


def test_lists_are_empty_when_no_records_exist(client):
    seasons = client.get(SEASONS)
    periods = client.get(REPORTING_PERIODS)
    assert seasons.status_code == 200
    assert seasons.data == []
    assert periods.status_code == 200
    assert periods.data == []


def test_farm_isolation_for_lists_and_details(client):
    season = client.post(SEASONS, season_payload(), format="json").data
    period = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    ).data

    other_client, _ = second_user()
    assert other_client.get(SEASONS).data == []
    assert other_client.get(REPORTING_PERIODS).data == []
    assert other_client.get(f"{SEASONS}/{season['id']}").status_code == 404
    assert (
        other_client.get(
            f"{REPORTING_PERIODS}/{period['id']}"
        ).status_code
        == 404
    )
    assert (
        other_client.delete(f"{SEASONS}/{season['id']}").status_code
        == 404
    )

    other_client.post(
        SEASONS,
        season_payload(name="Other farm season"),
        format="json",
    )
    other_client.post(
        REPORTING_PERIODS,
        period_payload(name="Other farm period"),
        format="json",
    )
    assert [item["id"] for item in client.get(SEASONS).data] == [
        season["id"]
    ]
    assert [item["id"] for item in client.get(REPORTING_PERIODS).data] == [
        period["id"]
    ]


def test_anonymous_access_is_rejected(anon):
    assert anon.get(SEASONS).status_code == 401
    assert anon.post(SEASONS, season_payload(), format="json").status_code == 401
    assert anon.get(REPORTING_PERIODS).status_code == 401
    assert (
        anon.post(
            REPORTING_PERIODS, period_payload(), format="json"
        ).status_code
        == 401
    )


def test_seasons_and_periods_can_be_deleted(client):
    season = client.post(SEASONS, season_payload(), format="json").data
    period = client.post(
        REPORTING_PERIODS, period_payload(), format="json"
    ).data

    assert client.delete(f"{SEASONS}/{season['id']}").status_code == 204
    assert client.get(f"{SEASONS}/{season['id']}").status_code == 404
    assert client.delete(
        f"{REPORTING_PERIODS}/{period['id']}"
    ).status_code == 204
    assert (
        client.get(f"{REPORTING_PERIODS}/{period['id']}").status_code
        == 404
    )
