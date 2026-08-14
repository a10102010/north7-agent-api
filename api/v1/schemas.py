"""Pydantic response models for NORTH7 Agent API v1."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class N7Response(BaseModel):
    """Standard wrapper for all v1 responses."""
    ok: bool = True
    data: Any
    meta: dict = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "ok": True,
                "data": {},
                "meta": {
                    "generated_utc": "2026-08-10T16:00:00Z",
                    "endpoint": "signals_latest",
                    "credits_used": 1,
                    "credits_remaining": 9999,
                    "sources": ["yahoo_finance", "claude_analysis"]
                }
            }
        }


class N7Error(BaseModel):
    """Error response."""
    ok: bool = False
    error: str
    code: str


class SignalItem(BaseModel):
    symbol: str
    signal_type: str
    direction: Optional[str] = None
    confidence: Optional[float] = None
    risk_score: Optional[float] = None
    reason_en: Optional[str] = None
    reason_de: Optional[str] = None
    source: Optional[str] = None
    generated_utc: Optional[str] = None


class RiskData(BaseModel):
    value: int = Field(ge=0, le=100)
    status: str
    crises: list[dict] = []
    regions: dict = {}
    updated: str


class RegimeData(BaseModel):
    regime: str
    confidence: Optional[float] = None
    description: Optional[str] = None
    updated: str


class PriceItem(BaseModel):
    symbol: str
    price: float
    change_pct: Optional[float] = None
    updated: Optional[str] = None


class PortfolioPosition(BaseModel):
    symbol: str
    weight: Optional[float] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    signal_source: Optional[str] = None


class ApiKeyInfo(BaseModel):
    name: str
    tier: str
    credits: int
    rate_limit: int
    total_requests: int
    created_utc: str
    last_used_utc: Optional[str] = None


class ApiKeyCreated(BaseModel):
    api_key: str
    name: str
    tier: str
    credits: int
    rate_limit: int
    message: str = "Store this key securely. It cannot be retrieved later."
