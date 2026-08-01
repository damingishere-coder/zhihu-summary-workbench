from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


BrowserSessionStatus = Literal[
    "idle",
    "starting",
    "qr_ready",
    "scanned",
    "authenticated",
    "expired",
    "verification_required",
    "failed",
]


class ManagedBrowserSessionRead(BaseModel):
    state: BrowserSessionStatus
    authenticated: bool = False
    message: str
    qr_code_url: str | None = None
    updated_at: datetime
