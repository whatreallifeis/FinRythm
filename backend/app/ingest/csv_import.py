"""Импорт операций из CSV. Заглушка S1: профиль не меняется."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from app.models import ImportReport, Profile


def import_csv(
    profile: Profile,
    content: bytes,
    *,
    mode: Literal["append", "replace"],
    today: dt.date | None = None,
) -> tuple[Profile, ImportReport]:
    return profile, ImportReport(added=0, skipped=0, duplicates=0, errors=[], mode=mode)
