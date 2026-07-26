from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routers import cases

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Frictionless Dispute & Chargeback Resolution")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)


@app.get("/health")
def health():
    return {"status": "ok"}
