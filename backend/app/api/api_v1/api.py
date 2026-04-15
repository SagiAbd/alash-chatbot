from fastapi import APIRouter

from app.api.api_v1 import auth, chat, knowledge_base, me, public, settings

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    knowledge_base.router, prefix="/knowledge-base", tags=["knowledge-base"]
)
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
