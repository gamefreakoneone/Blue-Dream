import copy
import datetime as dt

from Blue_dream_agents.timezone_utils import LOCAL_TZ


class SummaryCursor:
    def __init__(self, documents):
        self.documents = copy.deepcopy(list(documents))

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda item: (
                    str(item.get(field)) if field == "date" else item.get(field)
                ),
                reverse=direction == -1,
            )
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class SummaryCollection:
    def __init__(self, documents):
        self.documents = documents
        self.last_query = None

    def find(self, query):
        self.last_query = copy.deepcopy(query)
        cutoff = query["date"]["$gte"]
        return SummaryCursor(
            document
            for document in self.documents
            if str(document.get("date")) >= cutoff
        )


def test_summary_shape_filter_order_and_json_safety(client, monkeypatch, api_module):
    collection = SummaryCollection(
        [
            {
                "_id": object(),
                "summary_id": "sum_today_2",
                "date": "2026-07-19",
                "room_number": 2,
                "room_name": "Kitchen",
                "text": "You made tea.",
                "source_event_ids": ["e1", "e2"],
                "created_at": dt.datetime(2026, 7, 19, 18, tzinfo=dt.timezone.utc),
                "internal_prompt": "never expose",
            },
            {
                "summary_id": "sum_today_0",
                "date": dt.date(2026, 7, 19),
                "room_number": 0,
                "room_name": "Bedroom",
                "text": "You opened the curtains.",
                "source_event_ids": ["e3"],
                "created_at": dt.datetime(2026, 7, 19, 8, tzinfo=LOCAL_TZ),
            },
            {
                "summary_id": "sum_yesterday_1",
                "date": "2026-07-18",
                "room_number": 1,
                "room_name": "Living Room",
                "text": "You read with Sarah.",
                "source_event_ids": [],
                "created_at": dt.datetime(2026, 7, 18, 20, tzinfo=LOCAL_TZ),
            },
            {
                "summary_id": "too_old",
                "date": "2026-07-16",
                "room_number": 0,
                "room_name": "Bedroom",
                "text": "Outside the window.",
                "source_event_ids": ["old"],
            },
        ]
    )
    monkeypatch.setattr(
        api_module, "get_memory_summaries_collection", lambda: collection
    )
    monkeypatch.setattr(
        api_module,
        "now_local",
        lambda: dt.datetime(2026, 7, 19, 12, tzinfo=LOCAL_TZ),
    )

    response = client.get("/memory/summaries?days=2")

    assert response.status_code == 200
    assert collection.last_query == {"date": {"$gte": "2026-07-18"}}
    summaries = response.json()["summaries"]
    assert [item["summary_id"] for item in summaries] == [
        "sum_today_0",
        "sum_today_2",
        "sum_yesterday_1",
    ]
    assert summaries[1]["source_event_count"] == 2
    assert summaries[1]["created_at"].endswith("-07:00")
    assert set(summaries[1]) == {
        "summary_id",
        "date",
        "room_number",
        "room_name",
        "text",
        "source_event_count",
        "created_at",
    }
    assert "internal_prompt" not in response.text


def test_summary_empty_result_and_days_validation(client, monkeypatch, api_module):
    collection = SummaryCollection([])
    monkeypatch.setattr(
        api_module, "get_memory_summaries_collection", lambda: collection
    )

    assert client.get("/memory/summaries?days=7").json() == {"summaries": []}
    assert client.get("/memory/summaries?days=0").status_code == 422
