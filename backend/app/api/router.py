from fastapi import APIRouter

from backend.app.api.routes import (
    analysis,
    answers,
    dashboard,
    drafts,
    health,
    images,
    publish,
    prompts,
    questions,
    settings,
    tasks,
)


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(questions.router)
api_router.include_router(answers.router)
api_router.include_router(analysis.router)
api_router.include_router(tasks.router)
api_router.include_router(drafts.router)
api_router.include_router(images.router)
api_router.include_router(publish.router)
api_router.include_router(settings.router)
api_router.include_router(prompts.router)
