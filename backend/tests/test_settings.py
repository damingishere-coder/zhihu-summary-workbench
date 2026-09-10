import pytest

from backend.app.db.session import get_session_factory
from backend.app.models.core import SystemSetting


@pytest.mark.asyncio
async def test_mock_model_endpoint_and_public_settings(app_client) -> None:
    _, client, _ = app_client
    settings = await client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json()["provider_mode"] == "mock"
    assert isinstance(settings.json()["codex_configured"], bool)
    assert settings.json()["codex_model"] == "gpt-6-astra"
    assert settings.json()["deepseek_configured"] is False
    assert settings.json()["fast_text_model"] == "deepseek-v4-flash"
    assert settings.json()["reasoning_model"] == "deepseek-v4-flash"
    assert settings.json()["fallback_text_model"] == "deepseek-v4-flash"
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


@pytest.mark.asyncio
async def test_unrelated_setting_can_repair_legacy_inconsistent_quotas(app_client) -> None:
    _, client, _ = app_client
    async with get_session_factory()() as session:
        for key, value in {
            "daily_question_limit": 1,
            "hot_question_quota": 6,
            "manual_question_quota": 4,
        }.items():
            item = await session.get(SystemSetting, key)
            assert item is not None
            item.value = value
        await session.commit()

    response = await client.patch(
        "/api/settings", json={"request_timeout_seconds": 300}
    )
    assert response.status_code == 200, response.text
    assert response.json()["request_timeout_seconds"] == 300


@pytest.mark.asyncio
async def test_long_review_timeout_round_trip_and_runtime_limit(app_client) -> None:
    from backend.app.services.settings import configured_settings_copy
    from backend.app.core.config import get_settings
    _, client, _ = app_client
    response = await client.patch('/api/settings', json={'request_timeout_seconds': 1200})
    assert response.status_code == 200
    assert (await client.get('/api/settings')).json()['request_timeout_seconds'] == 1200
    async with get_session_factory()() as session:
        runtime = await configured_settings_copy(session, get_settings())
        assert runtime.codex_timeout_seconds == 1200
    rejected = await client.patch('/api/settings', json={'request_timeout_seconds': 1801})
    assert rejected.status_code == 422
