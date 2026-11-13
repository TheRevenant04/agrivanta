import json
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from api.models import (
    Customer,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Harvest,
    Sale,
    User,
)
from api.query_tools import crop_cycle_costs, field_profitability
from llm import (
    FakeLLMClient,
    LLMError,
    LLMResponse,
    LLMStreamCompleted,
    LLMTextDelta,
)

pytestmark = pytest.mark.django_db

CHAT = "/api/chat"


def _fake_client(plan, answer):
    response = LLMResponse(text=answer, model="fake")
    return FakeLLMClient(
        response=response,
        completion_response=LLMResponse(text=json.dumps(plan), model="fake"),
        stream_events=(
            LLMTextDelta(answer[:12]),
            LLMTextDelta(answer[12:]),
            LLMStreamCompleted(response),
        ),
    )


def _stream_events(response):
    assert response.status_code == 200
    assert response.streaming
    return [json.loads(line) for line in response.streaming_content]


def _create_cycle_data(cycle, with_expense=True):
    data = cycle()
    user = User.objects.get(email="owner@agrivanta.test")
    farm = user.farm
    cycle_model = farm.crop_cycles.get(pk=data["cycle"]["id"])
    if with_expense:
        Expense.objects.create(
            farm=farm,
            cycle=cycle_model,
            category=ExpenseCategory.INPUTS,
            amount="75.00",
            date="2026-03-15",
            status=ExpenseStatus.POSTED,
        )
    customer = Customer.objects.create(farm=farm, name="Buyer")
    harvest = Harvest.objects.create(
        farm=farm,
        cycle=cycle_model,
        quantity="20",
        unit=farm.units.get(pk=data["unit"]["id"]),
        date="2026-03-20",
    )
    Sale.objects.create(
        farm=farm,
        customer=customer,
        harvest=harvest,
        quantity="10",
        unit_price="30.00",
        date="2026-03-21",
        revenue="300.00",
    )
    return user, data, cycle_model


def _numeric_data_figures(result, path="/data"):
    figures = []

    def visit(value, current_path):
        if isinstance(value, dict):
            for key in sorted(value):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(value[key], f"{current_path}/{escaped}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{current_path}/{index}")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            figures.append({"path": current_path, "value": value})

    visit(result.get("data", {}), path)
    return figures


def test_chat_streams_multi_tool_answer_with_exact_evidence(
    client, cycle, monkeypatch
):
    user, data, cycle_model = _create_cycle_data(cycle)
    field_model = user.farm.fields.get(pk=data["field"]["id"])
    period = {"start_date": "2026-03-01", "end_date": "2026-03-31"}
    expected_costs = crop_cycle_costs(user, cycle_model.id, **period)
    expected_profitability = field_profitability(user, field_model.id, **period)
    answer = (
        "Actual recorded costs and revenue are available in the evidence."
    )
    fake = _fake_client(
        {
            "tool_calls": [
                {
                    "name": "crop_cycle_costs",
                    "arguments": {
                        "crop_cycle_id": str(cycle_model.id),
                        **period,
                    },
                },
                {
                    "name": "field_profitability",
                    "arguments": {"field_id": str(field_model.id), **period},
                },
            ]
        },
        answer,
    )
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    with CaptureQueriesContext(connection) as queries:
        response = client.post(
            CHAT,
            {"question": "Compare costs and profitability for this cycle."},
            format="json",
        )
        events = _stream_events(response)

    assert [event["type"] for event in events] == ["token", "token", "final"]
    assert "".join(event["text"] for event in events[:-1]) == answer
    final = events[-1]
    assert final["answer"] == answer
    assert "actual" in final["answer"].lower()
    assert not re.search(r"\d", final["answer"])
    evidence = final["evidence"]
    results = {item["tool"]: item["result"] for item in evidence["toolResults"]}
    assert results == {
        "crop_cycle_costs": expected_costs,
        "field_profitability": expected_profitability,
    }
    expected_figures = [
        {"tool": name, **figure}
        for name, result in sorted(results.items())
        for figure in _numeric_data_figures(result)
    ]
    assert evidence["figures"] == expected_figures
    assert {
        period["startDate"] for period in evidence["reportingPeriods"]
    } == {
        "2026-03-01"
    }
    assert evidence["cropCycles"][0]["id"] == str(cycle_model.id)
    assert {basis["tool"] for basis in evidence["calculationBasis"]} == set(results)

    write_statements = [
        query["sql"]
        for query in queries
        if query["sql"].lstrip().split(maxsplit=1)[0].upper()
        in {"INSERT", "UPDATE", "DELETE", "REPLACE"}
    ]
    assert write_statements == []

    planner = fake.completion_messages[0][0].content
    serialized_tools = planner.split(
        "Permitted read-only tool definitions (JSON):\n", maxsplit=1
    )[1]
    assert {tool["name"] for tool in json.loads(serialized_tools)} == {
        "crop_cycle_costs",
        "field_profitability",
        "inventory_position",
        "activity_listing",
    }
    assert len(fake.stream_messages) == 1


def test_chat_missing_data_returns_explicit_limitation_without_figures(
    client, cycle, monkeypatch
):
    _, _, cycle_model = _create_cycle_data(cycle, with_expense=False)
    fake = _fake_client(
        {
            "tool_calls": [
                {
                    "name": "crop_cycle_costs",
                    "arguments": {"crop_cycle_id": str(cycle_model.id)},
                }
            ]
        },
        "This should not be used.",
    )
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "What were the costs for this crop cycle?"},
        format="json",
    )
    events = _stream_events(response)

    assert [event["type"] for event in events] == ["token", "final"]
    final = events[-1]
    assert "missing" in final["answer"].lower()
    assert "no posted cost records" in final["answer"].lower()
    assert "0" not in final["answer"]
    assert final["evidence"]["figures"] == []
    assert (
        final["evidence"]["toolResults"][0]["result"]["status"]
        == "missing_data"
    )
    assert fake.stream_messages == []


def test_chat_missing_sales_returns_explicit_limitation(
    client, cycle, monkeypatch
):
    user, _, cycle_model = _create_cycle_data(cycle)
    Sale.objects.filter(farm=user.farm).delete()
    fake = _fake_client(
        {
            "tool_calls": [
                {
                    "name": "field_profitability",
                    "arguments": {
                        "field_id": str(cycle_model.field_id),
                    },
                }
            ]
        },
        "This should not be used.",
    )
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "What is the profitability for this field?"},
        format="json",
    )
    final = _stream_events(response)[-1]

    assert final["evidence"]["toolResults"][0]["result"]["status"] == (
        "missing_data"
    )
    assert "no sale records" in final["answer"].lower()
    assert final["evidence"]["figures"] == []
    assert fake.stream_messages == []


def test_chat_names_unavailable_harvest_records_without_numeric_result(
    client, cycle, monkeypatch
):
    data = cycle()
    user = User.objects.get(email="owner@agrivanta.test")
    cycle_model = user.farm.crop_cycles.get(pk=data["cycle"]["id"])
    assert not cycle_model.harvests.exists()
    fake = _fake_client(
        {"tool_calls": [], "limitations": ["harvest records"]},
        "This should not be used.",
    )
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "How many harvest records are available?"},
        format="json",
    )
    final = _stream_events(response)[-1]

    assert "harvest records" in final["answer"].lower()
    assert not any(character.isdigit() for character in final["answer"])
    assert final["evidence"]["figures"] == []
    assert fake.stream_messages == []


@pytest.mark.parametrize(
    ("question", "plan", "expected_input"),
    [
        (
            "What is profitability for field not-a-field?",
            {
                "tool_calls": [
                    {
                        "name": "field_profitability",
                        "arguments": {"field_id": "not-a-field"},
                    }
                ]
            },
            "field_id",
        ),
        (
            "What were costs in season Spring?",
            {
                "tool_calls": [],
                "limitations": ["season Spring"],
            },
            "season Spring",
        ),
        (
            "Compare costs from 2026-03-31 to 2026-03-01.",
            {
                "tool_calls": [
                    {
                        "name": "crop_cycle_costs",
                        "arguments": {
                            "crop_cycle_id": "invalid-cycle",
                            "start_date": "2026-03-31",
                            "end_date": "2026-03-01",
                        },
                    }
                ]
            },
            "end_date",
        ),
    ],
)
def test_chat_invalid_inputs_are_named_instead_of_guessed(
    client, cycle, monkeypatch, question, plan, expected_input
):
    _, _, cycle_model = _create_cycle_data(cycle)
    if expected_input == "end_date":
        plan["tool_calls"][0]["arguments"]["crop_cycle_id"] = str(
            cycle_model.id
        )
    fake = _fake_client(plan, "This should not be used.")
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(CHAT, {"question": question}, format="json")
    final = _stream_events(response)[-1]

    assert expected_input.lower() in final["answer"].lower()
    assert final["evidence"]["figures"] == []
    assert fake.stream_messages == []


@pytest.mark.parametrize(
    "answer",
    [
        "Actual revenue is 75 and actual costs are 300.",
        "Actual revenue is three hundred and costs are seventy-five.",
        "The actuals are 300kg and 75%.",
        "Estimated revenue is 300 and assumed costs are 75.",
        "Actual revenue is one.",
        "Actual revenue is ones.",
        "Actual revenue is two.",
        "Actual revenue is twos.",
        "Actual revenue is one hundred.",
        "Actual costs were hundreds of dollars.",
        "Actual revenue is one thousand.",
        "Actual costs were thousands of dollars.",
        "Actual revenue is one million.",
        "Actual revenue is in the millions.",
        "Actual costs are half of revenue.",
        "Actual costs are in halves.",
        "Actual costs were dozens of dollars.",
        "Revenue is in the twenties.",
        "Costs were in the thirties.",
        "Revenue was in the forties.",
        "Costs reached the fifties.",
        "Revenue is in the sixties.",
        "Costs were in the seventies.",
        "Revenue was in the eighties.",
        "Costs were in the nineties.",
        "Revenue was in the twenty-first year.",
        "Costs were in the mid-forties.",
    ],
)
def test_chat_rejects_numeric_or_speculative_claims(
    client, cycle, monkeypatch, answer
):
    user, data, cycle_model = _create_cycle_data(cycle)
    field_model = user.farm.fields.get(pk=data["field"]["id"])
    fake = _fake_client(
        {
            "tool_calls": [
                {
                    "name": "field_profitability",
                    "arguments": {"field_id": str(field_model.id)},
                }
            ]
        },
        answer,
    )
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "What are the actual costs and revenue?"},
        format="json",
    )
    final = _stream_events(response)[-1]

    assert final["answer"] != answer
    assert "can't include numeric claims" in final["answer"].lower()
    assert not re.search(r"\d", final["answer"])
    assert final["evidence"]["figures"]
    assert fake.stream_messages


def test_worker_gets_no_tool_definitions_or_llm_call(client, monkeypatch):
    user = User.objects.get(email="owner@agrivanta.test")
    user.role = "worker"
    user.save(update_fields=["role"])
    fake = _fake_client({"tool_calls": []}, "unused")
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(CHAT, {"question": "How are costs?"}, format="json")
    events = _stream_events(response)

    assert "no permitted" in events[-1]["answer"].lower()
    assert events[-1]["evidence"]["toolResults"] == []
    assert fake.completion_messages == []
    assert fake.stream_messages == []


def test_chat_requires_authentication_and_valid_question(anon, monkeypatch):
    fake = _fake_client({"tool_calls": []}, "unused")
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    assert anon.post(CHAT, {"question": "Question"}, format="json").status_code == 401
    client = APIClient()
    from api.tests.conftest import register

    registration = register(client)
    client.force_authenticate(
        user=User.objects.get(pk=registration.data["user"]["id"])
    )
    response = client.post(CHAT, {"question": "  "}, format="json")

    assert response.status_code == 400
    assert fake.completion_messages == []


def test_chat_rejects_overlong_question(client, monkeypatch):
    fake = _fake_client({"tool_calls": []}, "unused")
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "x" * 4001},
        format="json",
    )

    assert response.status_code == 400
    assert response.data == {
        "detail": "The question must be 4000 characters or fewer."
    }
    assert fake.completion_messages == []


def test_chat_accepts_ndjson_accept_header(client, monkeypatch):
    fake = _fake_client({"tool_calls": []}, "Inventory looks healthy.")
    monkeypatch.setattr("api.chat.get_llm_client", lambda: fake)

    response = client.post(
        CHAT,
        {"question": "What is my inventory position?"},
        format="json",
        HTTP_ACCEPT="application/x-ndjson",
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/x-ndjson")
    assert _stream_events(response)[-1]["type"] == "final"


def test_chat_returns_503_when_llm_service_is_unavailable(
    client, monkeypatch
):
    def raise_llm_error(*args, **kwargs):
        raise LLMError("provider unavailable")

    monkeypatch.setattr("api.chat.get_llm_client", raise_llm_error)

    response = client.post(
        CHAT,
        {"question": "What were my expenses?"},
        format="json",
    )

    assert response.status_code == 503
    assert response.data == {
        "detail": "The chat service is temporarily unavailable."
    }
