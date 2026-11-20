"""Private customer-directory response schemas; target labels are intentionally excluded."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import CustomerFeatures

CustomerId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]


class CustomerDirectoryRecord(BaseModel):
    customer_id: CustomerId
    features: CustomerFeatures


class CustomerDirectoryPage(BaseModel):
    total: Annotated[int, Field(ge=0)]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1)]
    page_count: Annotated[int, Field(ge=0)]
    items: list[CustomerDirectoryRecord]
