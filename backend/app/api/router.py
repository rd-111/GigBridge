"""Versioned API router."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.workspaces import router as workspaces_router
from app.api.routes.paypal import router as paypal_router
from app.api.routes.ledger import router as ledger_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(paypal_router)
api_router.include_router(ledger_router)
