from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Notification, NotificationType, User

NOTIFICATIONS = "/api/notifications"


def current_user(session):
    return User.objects.get(pk=session["user"]["id"])


def make_notification(user, **overrides):
    payload = {
        "user": user,
        "type": NotificationType.INFO,
        "message": "A notification",
    }
    payload.update(overrides)
    return Notification.objects.create(**payload)


def make_user_client(email="other@agrivanta.test"):
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {
            "name": "Other Owner",
            "email": email,
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['token']}"
    )
    return client, User.objects.get(email=email)


def test_create_notification_defaults_and_timestamps(db, session):
    user = current_user(session)

    notification = Notification.objects.create(
        user=user,
        type=NotificationType.WARNING,
        message="Inventory is below its reorder level.",
    )

    assert notification.read is False
    assert notification.is_read is False
    assert notification.created_at is not None
    assert notification.updated_at is not None
    assert notification.type == "warning"
    assert Notification.objects.filter(
        user=user, read=False
    ).count() == 1


def test_list_is_reverse_chronological_and_paginated(db, session, client):
    user = current_user(session)
    now = timezone.now()
    created = []
    for index in range(5):
        notification = make_notification(
            user,
            message=f"Notification {index}",
            read=index == 0,
        )
        Notification.objects.filter(pk=notification.pk).update(
            created_at=now - timedelta(minutes=index)
        )
        created.append(notification)

    first_page = client.get(f"{NOTIFICATIONS}?page=1&page_size=2")
    assert first_page.status_code == 200, first_page.data
    body = first_page.data
    assert body["count"] == 5
    assert body["unreadCount"] == 4
    assert body["page"] == 1
    assert body["pageSize"] == 2
    assert body["totalPages"] == 3
    assert body["nextPage"] == 2
    assert body["previousPage"] is None
    assert [item["id"] for item in body["results"]] == [
        str(created[0].id),
        str(created[1].id),
    ]
    assert body["results"][0]["createdAt"]
    assert body["results"][0]["updatedAt"]

    second_page = client.get(f"{NOTIFICATIONS}?page=2&page_size=2")
    assert second_page.status_code == 200, second_page.data
    assert [item["id"] for item in second_page.data["results"]] == [
        str(created[2].id),
        str(created[3].id),
    ]
    assert second_page.data["nextPage"] == 3
    assert second_page.data["previousPage"] == 1

    last_page = client.get(f"{NOTIFICATIONS}?page=3&page_size=2")
    assert last_page.status_code == 200, last_page.data
    assert [item["id"] for item in last_page.data["results"]] == [
        str(created[4].id)
    ]
    assert last_page.data["nextPage"] is None
    assert last_page.data["previousPage"] == 2


def test_list_defaults_to_first_page(db, session, client):
    user = current_user(session)
    for index in range(3):
        make_notification(user, message=f"Notification {index}")

    response = client.get(NOTIFICATIONS)

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert response.data["page"] == 1
    assert response.data["pageSize"] == 20
    assert len(response.data["results"]) == 3


def test_list_rejects_invalid_pagination(db, session, client):
    user = current_user(session)
    make_notification(user)

    bad_page = client.get(f"{NOTIFICATIONS}?page=not-a-number")
    assert bad_page.status_code == 400
    assert bad_page.data["field"] == "page"

    bad_size = client.get(f"{NOTIFICATIONS}?page_size=0")
    assert bad_size.status_code == 400
    assert bad_size.data["field"] == "page_size"

    too_large = client.get(f"{NOTIFICATIONS}?page_size=101")
    assert too_large.status_code == 400
    assert too_large.data["field"] == "page_size"

    missing_page = client.get(f"{NOTIFICATIONS}?page=99")
    assert missing_page.status_code == 404
    assert missing_page.data["field"] == "page"


def test_mark_read_persists_and_is_idempotent(db, session, client):
    user = current_user(session)
    notification = make_notification(user, message="Read me")
    old_update = timezone.now() - timedelta(days=1)
    Notification.objects.filter(pk=notification.pk).update(
        updated_at=old_update
    )

    response = client.post(
        f"{NOTIFICATIONS}/{notification.id}/read"
    )

    assert response.status_code == 200, response.data
    assert response.data["read"] is True
    notification.refresh_from_db()
    assert notification.read is True
    assert notification.updated_at > old_update

    again = client.put(f"{NOTIFICATIONS}/{notification.id}/read")
    assert again.status_code == 200
    assert again.data["read"] is True
    notification.refresh_from_db()
    assert notification.read is True


def test_mark_all_read_updates_only_the_current_user(db, session, client):
    user = current_user(session)
    first = make_notification(user, message="First")
    second = make_notification(user, message="Second", read=True)
    third = make_notification(user, message="Third")
    _, other_user = make_user_client()
    foreign = make_notification(other_user, message="Foreign")

    response = client.post(f"{NOTIFICATIONS}/read-all")

    assert response.status_code == 200, response.data
    assert response.data == {"updated": 2, "unreadCount": 0}
    for notification in (first, second, third):
        notification.refresh_from_db()
        assert notification.read is True
    foreign.refresh_from_db()
    assert foreign.read is False

    repeat = client.put(f"{NOTIFICATIONS}/read-all")
    assert repeat.status_code == 200
    assert repeat.data == {"updated": 0, "unreadCount": 0}


def test_unread_count_is_scoped_and_does_not_count_read_items(
    db, session, client
):
    user = current_user(session)
    make_notification(user)
    make_notification(user, read=True)
    make_notification(user)
    _, other_user = make_user_client()
    make_notification(other_user)

    response = client.get(f"{NOTIFICATIONS}/unread-count")

    assert response.status_code == 200
    assert response.data == {"unreadCount": 2}

    first = Notification.objects.filter(user=user, read=False).first()
    client.post(f"{NOTIFICATIONS}/{first.id}/read")

    updated = client.get(f"{NOTIFICATIONS}/unread-count")
    assert updated.status_code == 200
    assert updated.data == {"unreadCount": 1}


def test_users_cannot_see_or_mark_another_users_notification(db, session, client):
    user = current_user(session)
    make_notification(user, message="Mine")
    other_client, other_user = make_user_client()
    foreign = make_notification(other_user, message="Theirs")

    listing = client.get(NOTIFICATIONS)
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    assert [item["message"] for item in listing.data["results"]] == [
        "Mine"
    ]

    mark = client.post(f"{NOTIFICATIONS}/{foreign.id}/read")
    assert mark.status_code == 404
    assert mark.data["field"] == "id"
    foreign.refresh_from_db()
    assert foreign.read is False

    other_listing = other_client.get(NOTIFICATIONS)
    assert other_listing.status_code == 200
    assert [item["message"] for item in other_listing.data["results"]] == [
        "Theirs"
    ]


def test_notification_detail_is_scoped_to_the_owner(db, session, client):
    user = current_user(session)
    notification = make_notification(user, message="Mine")
    other_client, other_user = make_user_client()
    foreign = make_notification(other_user, message="Theirs")

    response = client.get(f"{NOTIFICATIONS}/{notification.id}")
    assert response.status_code == 200, response.data
    assert response.data["id"] == str(notification.id)
    assert response.data["message"] == "Mine"

    assert client.get(f"{NOTIFICATIONS}/{foreign.id}").status_code == 404
    assert (
        other_client.get(f"{NOTIFICATIONS}/{foreign.id}").status_code == 200
    )


def test_unknown_and_malformed_notification_ids_return_404(
    db, session, client
):
    missing = client.post(
        f"{NOTIFICATIONS}/00000000-0000-0000-0000-000000000000/read"
    )
    assert missing.status_code == 404
    assert missing.data["field"] == "id"

    malformed = client.post(f"{NOTIFICATIONS}/not-a-uuid/read")
    assert malformed.status_code == 404
    assert malformed.data["field"] == "id"

    detail_missing = client.get(
        f"{NOTIFICATIONS}/00000000-0000-0000-0000-000000000000"
    )
    assert detail_missing.status_code == 404
    assert detail_missing.data["field"] == "id"

    detail_malformed = client.get(f"{NOTIFICATIONS}/not-a-uuid")
    assert detail_malformed.status_code == 404
    assert detail_malformed.data["field"] == "id"


def test_notification_content_is_not_modifiable(db, session, client):
    user = current_user(session)
    notification = make_notification(
        user,
        type=NotificationType.WARNING,
        message="Original message",
    )

    put = client.put(
        f"{NOTIFICATIONS}/{notification.id}",
        {"message": "Changed", "type": "alert", "read": True},
        format="json",
    )
    assert put.status_code == 405

    patch = client.patch(
        f"{NOTIFICATIONS}/{notification.id}",
        {"message": "Changed", "type": "alert", "read": True},
        format="json",
    )
    assert patch.status_code == 405

    delete = client.delete(f"{NOTIFICATIONS}/{notification.id}")
    assert delete.status_code == 405

    create = client.post(
        NOTIFICATIONS,
        {"message": "New", "type": "alert"},
        format="json",
    )
    assert create.status_code == 405

    mark = client.post(
        f"{NOTIFICATIONS}/{notification.id}/read",
        {"message": "Changed", "type": "alert", "read": False},
        format="json",
    )
    assert mark.status_code == 200
    notification.refresh_from_db()
    assert notification.message == "Original message"
    assert notification.type == NotificationType.WARNING
    assert notification.read is True


def test_notifications_require_authentication(db, anon, session):
    user = current_user(session)
    notification = make_notification(user)

    assert anon.get(NOTIFICATIONS).status_code == 401
    assert (
        anon.get(f"{NOTIFICATIONS}/unread-count").status_code == 401
    )
    assert (
        anon.post(f"{NOTIFICATIONS}/{notification.id}/read").status_code
        == 401
    )
    assert anon.post(f"{NOTIFICATIONS}/read-all").status_code == 401
