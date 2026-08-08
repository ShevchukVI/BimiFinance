from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, categories, families, jars, notes, system, transactions, users
from app.config import settings
from app.core.migrations import run_migrations
from app.core.security import encrypt_legacy_tokens


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    encrypt_legacy_tokens()
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(system.router)
app.include_router(families.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(jars.router)
app.include_router(notes.router)


@app.get("/health")
def health():
    return {"status": "ok"}
