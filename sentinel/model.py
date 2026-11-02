"""Validate SENTINEL rows and build customer and transaction documents."""

import json
from datetime import datetime, timezone
from decimal import Decimal


def timestamp(value):
    """Normalize a timezone-aware source timestamp to UTC."""
    dt = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def obj(value):
    """Decode a JSON string while preserving already decoded values."""
    return json.loads(value) if isinstance(value, str) and value else value


def documents(rows):
    """Validate joined rows and build customer and transaction documents."""
    customers, transactions, seen = {}, [], set()
    for row in rows:
        t, c, m, d, label = (
            row[k] for k in ("transaction", "customer", "merchant", "device", "label")
        )
        tid, cid = t["transaction_id"], t["customer_id"]
        if tid in seen:
            raise ValueError("Duplicate transaction ID in source")
        seen.add(tid)
        amount = int(t["amount_paise"])
        if amount <= 0 or Decimal(str(t["transaction_amount"])) * 100 != amount:
            raise ValueError("Invalid amount or rupee/paise mismatch")
        if c["customer_id"] != cid or m["merchant_id"] != t["merchant_id"]:
            raise ValueError("Dimension join mismatch")
        if t.get("device_id") and not d:
            raise ValueError("Missing device dimension in source")
        device = {"device_id": d["device_id"], "device_kind": d["device_kind"]} if d else None
        if device and device["device_id"] != t["device_id"]:
            raise ValueError("Device join mismatch")
        fraud = None
        if label:
            if label["transaction_id"] != tid:
                raise ValueError("Label join mismatch")
            fraud = int(label["fraud_label"])
            if fraud not in (0, 1):
                raise ValueError("Fraud label must be 0 or 1")
        customer = customers.setdefault(
            cid,
            {
                "_id": cid,
                "customer_id": cid,
                "created_at": timestamp(c["created_at"]),
                "customer_age": int(c["customer_age"]),
                "home_city": c["home_city"],
                "region": c["region"],
                "devices": [],
                "devices_scope": "observed_in_loaded_sample",
            },
        )
        if device and device not in customer["devices"]:
            customer["devices"].append(device)
        transactions.append(
            {
                "_id": tid,
                "transaction_id": tid,
                "customer_id": cid,
                "customer": {
                    "customer_age": int(t["customer_age"]),
                    "location": obj(t.get("customer_location")),
                },
                "merchant": {
                    "merchant_id": m["merchant_id"],
                    "name": m["synthetic_name"],
                    "location": obj(t["merchant_location"]),
                },
                "merchant_category": t["merchant_category"],
                "device": device,
                "amount_paise": amount,
                "currency": "INR",
                "time": timestamp(t["transaction_time"]),
                "payment_channel": t["payment_channel"],
                "fraud_label": fraud,
                "label_available_at": timestamp(label["label_available_at"]) if label else None,
                "split": t["split"],
                "source": "SENTINEL",
            }
        )
    return list(customers.values()), transactions
