import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routers import cases

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Frictionless Dispute & Chargeback Resolution")

# Vite falls forward to the next free port when 5173 is taken, and 127.0.0.1 is a
# different origin from localhost. Pinning one of them turns a busy port into an
# opaque "Failed to fetch" with no clue as to why.
_DEV_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (5173, 5174, 5175, 4173)
]

# A deployed frontend lives on a domain this list cannot know, so it is supplied at
# runtime. Missing it is the single most likely cause of a deployment that renders
# but shows no data.
def _origin(value: str) -> str:
    """Accept a bare hostname as well as a full origin.

    Render's blueprint passes a cross-service reference as just the host, and an
    entry without a scheme never matches an Origin header — the deployment would
    render but every request would fail CORS, which is the least obvious way for
    this to break.
    """
    value = value.strip().rstrip("/")
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


_EXTRA = [_origin(o) for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS + _EXTRA,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Pipeline health, computed live off the labelled corpus.

    The whole replay costs single-digit milliseconds offline, so this is measured on
    request rather than cached — a stale accuracy figure is worse than none. Exposed
    so the claim "95% accurate, bias fully attributable" is something a reader can
    check rather than something the deck asserts.
    """
    from . import evaluate

    results = [evaluate.replay(g) for g in evaluate.load_goldens()]
    accuracy = evaluate.accuracy_report(results)
    bias = evaluate.bias_report(results)
    calibration = evaluate.calibration_report(results)
    latency = evaluate.latency_report(results)

    return {
        "corpus": {
            "total": accuracy["total"],
            "arbitrable": accuracy["arbitrable"],
            "abstained": accuracy["abstained"],
        },
        "accuracy": {
            "overall": round(accuracy["accuracy"], 4),
            "correct": accuracy["correct"],
            "per_claim_type": {
                claim_type: round(b["correct"] / b["n"], 4)
                for claim_type, b in accuracy["per_claim_type"].items()
            },
        },
        "fairness": {
            "recall": {k: (round(v, 4) if v is not None else None) for k, v in bias["recall"].items()},
            "bias_gap": round(bias["bias_gap"], 4),
            "verdict_share_card_member": round(bias["verdict_share_card_member"], 4),
            "label_share_card_member": round(bias["label_share_card_member"], 4),
            "errors_favouring_card_member": bias["errors_favouring_card_member"],
            "errors_favouring_merchant": bias["errors_favouring_merchant"],
        },
        "calibration": {
            "mean_confidence_correct": round(calibration["mean_confidence_correct"], 4),
            "mean_confidence_wrong": round(calibration["mean_confidence_wrong"], 4),
            "separation": round(calibration["separation"], 4),
            "confidently_wrong": len(calibration["confidently_wrong"]),
        },
        "latency_ms": {k: round(v, 3) for k, v in latency.items()},
    }
