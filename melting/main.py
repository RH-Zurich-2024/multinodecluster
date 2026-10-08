"""
Smelting Service
================

Microservice einer containerisierten Fabrik-Pipeline. Nimmt ein
Material-Datenpaket entgegen, simuliert den Schmelzvorgang (asynchron)
und reicht das angereicherte Paket per HTTP an den Casting Service weiter.

Endpunkte:
    POST /smelt   – Schmelzauftrag verarbeiten und weiterleiten
    GET  /health  – Liveness-/Readiness-Probe für Kubernetes

Konfiguration (Umgebungsvariablen):
    CASTING_SERVICE_URL      Ziel-URL des Casting Service
    SMELT_DURATION_SECONDS   Simulierte Schmelzdauer in Sekunden
    LOG_LEVEL                Logstufe (DEBUG/INFO/WARNING/ERROR)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

SERVICE_NAME = "smelting-service"
SERVICE_VERSION = "1.0.0"

#: Ziel-URL des Casting Service, konfigurierbar für Kubernetes.
CASTING_SERVICE_URL: str = os.getenv(
    "CASTING_SERVICE_URL", "http://localhost:8004/cast"
)

#: Simulierte Schmelzdauer. In Produktion wird der echte Ofenprozess
#: durch dieses Warten ersetzt; der Wert ist bewusst konfigurierbar,
#: damit Smoke-Tests nicht 3 Sekunden pro Request warten müssen.
SMELT_DURATION_SECONDS: float = float(os.getenv("SMELT_DURATION_SECONDS", "3"))

#: Temperatur des geschmolzenen Materials in Celsius.
MELT_TEMPERATURE_CELSIUS: int = int(os.getenv("MELT_TEMPERATURE_CELSIUS", "1450"))

#: Zeitlimit für den HTTP-Call zum Casting Service.
CASTING_TIMEOUT_SECONDS: float = float(os.getenv("CASTING_TIMEOUT_SECONDS", "10"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

#: Startzeitpunkt des Prozesses – für die Uptime in der Health-Antwort.
_START_TIME = time.monotonic()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)


# ---------------------------------------------------------------------------
# Datenmodelle
# ---------------------------------------------------------------------------


class SmeltRequest(BaseModel):
    """Eingehender Schmelzauftrag.

    ``extra="allow"`` erlaubt optionale Felder (z. B. ``smelter_id``), die
    von vorgelagerten Services ergänzt werden. Diese werden unverändert an
    den Casting Service weitergereicht, damit die Pipeline durchgängig bleibt.
    """

    model_config = ConfigDict(extra="allow")

    batch_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Eindeutige ID des Chargen-/Material-Loses",
        examples=["MET-101"],
    )
    material: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Rohstoff, z. B. Eisen oder Aluminium",
        examples=["Eisen"],
    )
    weight_kg: float = Field(
        ...,
        gt=0,
        description="Chargengewicht in Kilogramm",
        examples=[500],
    )
    location: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Standort des Ofens",
        examples=["furnace"],
    )


class SmeltResponse(BaseModel):
    """Antwort nach erfolgreicher Weiterleitung an den Casting Service."""

    batch_id: str
    material: str
    weight_kg: float
    location: str
    status: str = Field(default="liquid", description="Zustand nach dem Schmelzen")
    temp_celsius: int = Field(
        default=1450, description="Temperatur der Schmelze in Celsius"
    )
    casting_service_status: int | None = Field(
        default=None, description="HTTP-Statuscode der Antwort des Casting Service"
    )
    casting_response: dict[str, Any] | None = Field(
        default=None, description="Antwortpayload des Casting Service"
    )
    processing_time_s: float = Field(
        description="Dauer der Verarbeitung in Sekunden"
    )


# ---------------------------------------------------------------------------
# Application-Lifecycle: gemeinsamer HTTP-Client (Connection-Pooling)
# ---------------------------------------------------------------------------


class HttpClient:
    """Duenner Wrapper um einen langlebigen ``httpx.AsyncClient``.

    Der Client wird einmalig beim Startup erzeugt und beim Shutdown wieder
    geschlossen. Das hält den Connection-Pool warm und vermeidet pro
    Request einen neuen TLS-/TCP-Handshake.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        return await self._client.post(url, json=payload)

    async def aclose(self) -> None:
        await self._client.aclose()


_http_client: HttpClient | None = None


def get_http_client() -> HttpClient:
    """Liefert den initialisierten Client oder wirft einen klaren Fehler."""
    if _http_client is None:  # pragma: no cover - defensive branch
        raise RuntimeError("HTTP-Client ist nicht initialisiert")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client

    timeout = httpx.Timeout(
        CASTING_TIMEOUT_SECONDS,
        connect=5.0,
        read=CASTING_TIMEOUT_SECONDS,
        write=CASTING_TIMEOUT_SECONDS,
    )
    limits = httpx.Limits(
        max_connections=50,
        max_keepalive_connections=20,
        keepalive_expiry=30.0,
    )
    _http_client = HttpClient(
        httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False)
    )

    logger.info(
        "%s v%s gestartet – Ziel: %s (Schmelzdauer: %.1fs)",
        SERVICE_NAME,
        SERVICE_VERSION,
        CASTING_SERVICE_URL,
        SMELT_DURATION_SECONDS,
    )
    try:
        yield
    finally:
        await _http_client.aclose()
        _http_client = None
        logger.info("%s gestoppt", SERVICE_NAME)


app = FastAPI(
    title="Smelting Service",
    description="Schmelzt Materialchargen und leitet sie an den Casting Service weiter.",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    """Liveness-/Readiness-Probe für Kubernetes.

    Antwortet mit HTTP 200, sobald der Service bereit ist, Aufträge
    anzunehmen. Bewusst ohne Abhängigkeit zum Casting Service, damit ein
    Ausfall des Downstream-Systems den Container nicht aus dem
    Ready-State entfernt.
    """
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "uptime_s": round(time.monotonic() - _START_TIME, 3),
    }


@app.post(
    "/smelt",
    response_model=SmeltResponse,
    status_code=status.HTTP_200_OK,
    tags=["smelting"],
    summary="Charge schmelzen und an den Casting Service weiterleiten",
    responses={
        422: {"description": "Ungültiger Auftrag (fehlende oder fehlerhafte Felder)"},
        502: {"description": "Casting Service nicht erreichbar oder meldet einen Fehler"},
        504: {"description": "Casting Service hat nicht rechtzeitig geantwortet"},
    },
)
async def smelt(payload: SmeltRequest) -> SmeltResponse:
    """Verarbeitet einen Schmelzauftrag.

    Ablauf:
        1. Schmelzdauer simulieren (asynchrones Warten).
        2. Payload um ``status`` und ``temp_celsius`` anreichern.
        3. Angereicherte Payload an den Casting Service per HTTP POST senden.
    """
    started = time.monotonic()
    batch_id = payload.batch_id

    logger.info(
        "Schmelzauftrag empfangen: batch_id=%s material=%s weight=%s location=%s",
        batch_id,
        payload.material,
        payload.weight_kg,
        payload.location,
    )

    # --- 1. Schmelzvorgang simulieren -------------------------------------
    # Nicht-blockierendes Warten: der Event-Loop bedient währenddessen
    # weiterhin alle anderen Requests.
    await asyncio.sleep(SMELT_DURATION_SECONDS)

    # --- 2. Payload anreichern --------------------------------------------
    # dict(Payload) materialisiert Felder UND erlaubte Extras aus dem Input.
    enriched: dict[str, Any] = payload.model_dump()
    enriched["status"] = "liquid"
    enriched["temp_celsius"] = MELT_TEMPERATURE_CELSIUS

    # --- 3. Weiterleitung an den Casting Service --------------------------
    try:
        response = await get_http_client().post_json(CASTING_SERVICE_URL, enriched)
    except httpx.TimeoutException as exc:
        logger.error("Casting Service Timeout nach %ss: %s", CASTING_TIMEOUT_SECONDS, exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Casting Service nicht rechtzeitig erreichbar",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Casting Service nicht erreichbar (%s): %s", CASTING_SERVICE_URL, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Casting Service nicht erreichbar",
        ) from exc

    # 4xx/5xx des Downstream-Services als Gateway-Fehler weiterreichen.
    if response.status_code >= 500:
        logger.error(
            "Casting Service meldet Fehler: HTTP %s – %s",
            response.status_code,
            response.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Casting Service meldet HTTP {response.status_code}",
        )
    if response.status_code >= 400:
        logger.warning(
            "Casting Service lehnt Auftrag ab: HTTP %s – %s",
            response.status_code,
            response.text[:500],
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Casting Service lehnt Auftrag ab: {response.text[:200]}",
        )

    try:
        casting_payload: dict[str, Any] | None = response.json()
    except ValueError:
        casting_payload = None
        logger.warning("Casting Service lieferte kein gültiges JSON")

    processing_time = round(time.monotonic() - started, 3)
    logger.info(
        "Charge %s geschmolzen (%.3fs) und an Casting Service übergeben (HTTP %s)",
        batch_id,
        processing_time,
        response.status_code,
    )

    return SmeltResponse(
        batch_id=enriched["batch_id"],
        material=enriched["material"],
        weight_kg=enriched["weight_kg"],
        location=enriched["location"],
        status="liquid",
        temp_celsius=MELT_TEMPERATURE_CELSIUS,
        casting_service_status=response.status_code,
        casting_response=casting_payload,
        processing_time_s=processing_time,
    )


# ---------------------------------------------------------------------------
# Globale Exception-Handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fängt unerwartete Fehler ab, damit der ASGI-Server nicht abstürzt."""
    logger.exception("Unbehandelte Ausnahme in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Interner Serverfehler"},
    )


if __name__ == "__main__":
    import uvicorn

    # Lokaler Entwicklungsstart: python main.py
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8003")),
        log_level=LOG_LEVEL.lower(),
    )