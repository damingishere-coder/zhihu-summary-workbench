import pytest


@pytest.mark.asyncio
async def test_manual_question_crud_and_duplicate(app_client) -> None:
    _, client, _ = app_client
    payload = {
        "url": "https://www.zhihu.com/question/123456789",
        "title": "怎样建立稳定的学习习惯？",
        "description": "希望了解可以长期执行的方法。",
        "sample_answer": "先把目标拆小。固定每天练习时间。每周复盘一次。",
        "priority": "high",
    }
    response = await client.post("/api/questions/manual", json=payload)
    assert response.status_code == 201, response.text
    question = response.json()
    assert question["status"] == "candidate"
    assert question["external_id"] == "123456789"

    duplicate = await client.post("/api/questions/manual", json=payload)
    assert duplicate.status_code == 409

    listing = await client.get("/api/questions", params={"search": "学习习惯"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    update = await client.patch(
        f"/api/questions/{question['id']}",
        json={"priority": "medium", "status": "ignored"},
    )
    assert update.status_code == 200
    assert update.json()["priority"] == "medium"
    assert update.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_batch_import_reports_duplicates(app_client) -> None:
    _, client, _ = app_client
    response = await client.post(
        "/api/questions/import",
        json={
            "urls": [
                "https://www.zhihu.com/question/10001",
                "https://www.zhihu.com/question/10001",
                "https://www.zhihu.com/question/10002",
            ],
            "priority": "low",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2
    assert response.json()["duplicate"] == 1


@pytest.mark.asyncio
async def test_invalid_zhihu_url_is_rejected(app_client) -> None:
    _, client, _ = app_client
    response = await client.post(
        "/api/questions/manual",
        json={"url": "https://example.com/question/1"},
    )
    assert response.status_code == 422

