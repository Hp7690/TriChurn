"""Load the small, private demo customer sample without exposing its CSV or target labels."""
from __future__ import annotations

import csv
import re
from pathlib import Path

from app.schemas.common import CustomerFeatures
from app.schemas.customers import CustomerDirectoryRecord

_CUSTOMER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_INTEGER_FIELDS = frozenset({"SeniorCitizen", "tenure"})
_NUMBER_FIELDS = frozenset({"MonthlyCharges", "TotalCharges"})


def load_customer_records(path: Path) -> tuple[CustomerDirectoryRecord, ...]:
    records: list[CustomerDirectoryRecord] = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"customerID", *CustomerFeatures.model_fields}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("The private demo customer dataset has an invalid schema.")
        for row in reader:
            customer_id = row.get("customerID", "").strip()
            if not _CUSTOMER_ID.fullmatch(customer_id):
                raise ValueError("The private demo customer dataset has an invalid customer identifier.")
            features: dict[str, object] = {}
            for name in CustomerFeatures.model_fields:
                value = row.get(name, "").strip()
                if name in _INTEGER_FIELDS:
                    features[name] = int(value)
                elif name in _NUMBER_FIELDS:
                    features[name] = None if name == "TotalCharges" and not value else float(value)
                else:
                    features[name] = value
            records.append(CustomerDirectoryRecord(customer_id=customer_id,
                                                   features=CustomerFeatures.model_validate(features)))
    if not records:
        raise ValueError("The private demo customer dataset contains no customers.")
    return tuple(records)
