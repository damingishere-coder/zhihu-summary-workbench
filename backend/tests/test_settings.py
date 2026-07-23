import pytest


@pytest.mark.asyncio
async def test_mock_model_endpoint_and_public_settings(app_client) -> None:
    _, client, _ = app_client
    settings = await client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json()["provider_mode"] == "mock"
    assert settings.json()["deepseek_configured"] is False
    assert "@" not in settings.json()["redis_url_display"]

    model_test = await client.post(
        "/api/settings/test-model",
        json={
            "provider_mode": "mock",
            "question_title": "如何保持阅读习惯？",
            "sample_answer": "选择感兴趣的书。每天读十页。记录阅读进度。",
        },
    )
    assert model_test.status_code == 200, model_test.text
    body = model_test.json()
    assert body["success"] is True
    assert body["provider"] == "mock"
    assert len(body["analysis"]["core_claims"]) == 3


@pytest.mark.asyncio
async def test_deepseek_mode_cannot_be_saved_without_key(app_client) -> None:
    _, client, _ = app_client
    response = await client.patch(
        "/api/settings", json={"provider_mode": "deepseek"}
    )
    assert response.status_code == 400
    assert "DEEPSEEK_API_KEY" in response.json()["detail"]

