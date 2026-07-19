import asyncio
import copy
from types import SimpleNamespace

from pywebpush import WebPushException

from Blue_dream_agents import db_client, web_push


def _matches(document, query):
    return all(document.get(key) == value for key, value in query.items())


class FakeCursor:
    def __init__(self, documents):
        self._documents = copy.deepcopy(list(documents))

    def __aiter__(self):
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakePushCollection:
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(list(documents or []))
        self.indexes = []

    async def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))
        return kwargs.get("name")

    def find(self, query):
        return FakeCursor(item for item in self.documents if _matches(item, query))

    async def find_one(self, query):
        return copy.deepcopy(
            next((item for item in self.documents if _matches(item, query)), None)
        )

    async def update_one(self, query, update, upsert=False):
        target = next((item for item in self.documents if _matches(item, query)), None)
        inserted = target is None and upsert
        if target is None and not upsert:
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)
        if inserted:
            target = copy.deepcopy(query)
            target.update(copy.deepcopy(update.get("$setOnInsert", {})))
            self.documents.append(target)
        target.update(copy.deepcopy(update.get("$set", {})))
        return SimpleNamespace(
            matched_count=0 if inserted else 1,
            modified_count=1,
            upserted_id=target.get("subscription_id") if inserted else None,
        )


def test_vapid_public_key_enabled_and_disabled(client, monkeypatch, api_module):
    monkeypatch.setattr(
        api_module.web_push,
        "get_public_key_status",
        lambda: {"enabled": False, "key": None},
    )
    assert client.get("/push/vapid-public-key").json() == {
        "enabled": False,
        "key": None,
    }

    monkeypatch.setattr(
        api_module.web_push,
        "get_public_key_status",
        lambda: {"enabled": True, "key": "public-key"},
    )
    assert client.get("/push/vapid-public-key").json() == {
        "enabled": True,
        "key": "public-key",
    }


def test_subscribe_validates_and_upserts_endpoint(client, monkeypatch, api_module):
    collection = FakePushCollection()

    async def noop_indexes():
        return None

    monkeypatch.setattr(api_module.web_push, "initialize_push_indexes", noop_indexes)
    monkeypatch.setattr(
        api_module, "get_push_subscriptions_collection", lambda: collection
    )

    assert client.post("/push/subscribe", json={}).status_code == 422
    assert (
        client.post(
            "/push/subscribe",
            json={"subscription": {"endpoint": " ", "keys": {"p256dh": "x", "auth": "y"}}},
        ).status_code
        == 400
    )

    first = client.post(
        "/push/subscribe",
        headers={"user-agent": "Memoria Test"},
        json={
            "subscription": {
                "endpoint": "https://push.example/subscription",
                "keys": {"p256dh": "first", "auth": "auth-one"},
            },
            "role": "patient",
        },
    )
    second = client.post(
        "/push/subscribe",
        json={
            "subscription": {
                "endpoint": "https://push.example/subscription",
                "keys": {"p256dh": "renewed", "auth": "auth-two"},
            },
            "role": "patient",
        },
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["subscription_id"] == second.json()["subscription_id"]
    assert len(collection.documents) == 1
    assert collection.documents[0]["keys"] == {
        "p256dh": "renewed",
        "auth": "auth-two",
    }
    assert collection.documents[0]["enabled"] is True


def test_unsubscribe_is_idempotent(client, monkeypatch, api_module):
    collection = FakePushCollection(
        [
            {
                "subscription_id": "ps_existing",
                "endpoint": "https://push.example/existing",
                "enabled": True,
            }
        ]
    )

    async def noop_indexes():
        return None

    monkeypatch.setattr(api_module.web_push, "initialize_push_indexes", noop_indexes)
    monkeypatch.setattr(
        api_module, "get_push_subscriptions_collection", lambda: collection
    )

    for _ in range(2):
        response = client.post(
            "/push/unsubscribe",
            json={"endpoint": "https://push.example/existing"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    assert collection.documents[0]["enabled"] is False

    missing = client.post(
        "/push/unsubscribe", json={"endpoint": "https://push.example/missing"}
    )
    assert missing.status_code == 200
    assert missing.json() == {"ok": True}


def test_push_test_declared_statuses(client, monkeypatch, api_module):
    async def not_configured(payload):
        return {"status": "not_configured", "sent": 0, "failed": 0}

    monkeypatch.setattr(
        api_module.web_push, "send_to_patient_subscriptions", not_configured
    )
    assert client.post("/push/test").json() == {
        "status": "not_configured",
        "sent": 0,
    }

    async def sent(payload):
        assert payload["trigger_type"] == "test"
        return {"status": "sent", "sent": 2, "failed": 0}

    monkeypatch.setattr(api_module.web_push, "send_to_patient_subscriptions", sent)
    assert client.post("/push/test").json() == {"status": "sent", "sent": 2}


def test_gone_subscription_is_disabled(monkeypatch):
    collection = FakePushCollection(
        [
            {
                "subscription_id": "ps_gone",
                "endpoint": "https://push.example/gone",
                "keys": {"p256dh": "public", "auth": "auth"},
                "role": "patient",
                "enabled": True,
            }
        ]
    )

    async def noop_indexes():
        return None

    def gone(**kwargs):
        raise WebPushException(
            "subscription expired", response=SimpleNamespace(status_code=410)
        )

    monkeypatch.setattr(web_push, "_config", lambda: ("private", "public", "mailto:test@example.com"))
    monkeypatch.setattr(web_push, "initialize_push_indexes", noop_indexes)
    monkeypatch.setattr(
        web_push, "get_push_subscriptions_collection", lambda: collection
    )
    monkeypatch.setattr(web_push, "webpush", gone)

    result = asyncio.run(
        web_push.send_to_patient_subscriptions(
            {
                "title": "Reminder",
                "body": "Drink water",
                "tag": "pm_1",
                "url": "/#chat",
                "image": None,
                "trigger_type": "reminder",
                "message_id": "pm_1",
            }
        )
    )

    assert result == {"status": "sent", "sent": 0, "failed": 1}
    assert collection.documents[0]["enabled"] is False
    assert collection.documents[0]["last_result"]["status"] == "gone"
    assert collection.documents[0]["last_result"]["code"] == 410


def test_push_endpoint_index_is_unique(monkeypatch):
    collection = FakePushCollection()
    monkeypatch.setattr(
        db_client, "get_push_subscriptions_collection", lambda: collection
    )

    asyncio.run(db_client.ensure_push_indexes())

    assert collection.indexes == [
        ([('endpoint', 1)], {"name": "endpoint_1", "unique": True})
    ]
