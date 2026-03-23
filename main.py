"""FastAPI entrypoint for RAW co-working WhatsApp rent bot."""

from fastapi import FastAPI

from routes.webhook import router as webhook_router

app = FastAPI(title="RAW Rent Bot", version="0.1.0")
app.include_router(webhook_router)
