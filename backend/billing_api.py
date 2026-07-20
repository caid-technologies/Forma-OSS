from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.auth import clerk_user_email, require_deployed_user_id
from blueprint_core.database import (
    add_user_credits,
    get_user_credit_balance,
    list_user_credit_transactions,
    user_credit_balance_public_payload,
)


router = APIRouter(prefix="/user/billing", tags=["user-billing"])


@dataclass(frozen=True)
class CreditPackage:
    package_id: str
    name: str
    credits: int
    unit_amount_cents: int
    currency: str = "usd"


DEFAULT_CREDIT_PACKAGES = [
    CreditPackage(package_id="starter", name="Starter credit pack", credits=100, unit_amount_cents=1000),
    CreditPackage(package_id="builder", name="Builder credit pack", credits=500, unit_amount_cents=4500),
    CreditPackage(package_id="studio", name="Studio credit pack", credits=1200, unit_amount_cents=10000),
]


class CheckoutSessionRequest(BaseModel):
    package_id: str
    quantity: int = 1
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _stripe_secret_key() -> str:
    key = _env("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe billing is not configured. Set STRIPE_SECRET_KEY on the backend.",
        )
    return key


def _stripe_webhook_secret() -> str:
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook verification is not configured. Set STRIPE_WEBHOOK_SECRET on the backend.",
        )
    return secret


def _stripe_module():
    try:
        import stripe
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe SDK is not installed. Install backend dependencies before enabling billing.",
        ) from exc
    stripe.api_key = _stripe_secret_key()
    return stripe


def _app_base_url() -> str:
    value = (
        _env("BLUEPRINT_APP_URL")
        or _env("NEXT_PUBLIC_APP_URL")
        or _env("VERCEL_PROJECT_PRODUCTION_URL")
        or _env("VERCEL_URL")
        or "http://localhost:3000"
    )
    if value.startswith(("http://", "https://")):
        return value.rstrip("/")
    return f"https://{value.rstrip('/')}"


def _public_package(package: CreditPackage) -> Dict[str, Any]:
    return {
        "package_id": package.package_id,
        "name": package.name,
        "credits": package.credits,
        "unit_amount_cents": package.unit_amount_cents,
        "currency": package.currency,
    }


def _load_credit_packages() -> List[CreditPackage]:
    raw = _env("BLUEPRINT_CREDIT_PACKAGES_JSON")
    if not raw:
        return DEFAULT_CREDIT_PACKAGES
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("BLUEPRINT_CREDIT_PACKAGES_JSON must be valid JSON.") from exc
    if not isinstance(items, list):
        raise RuntimeError("BLUEPRINT_CREDIT_PACKAGES_JSON must be a JSON array.")
    packages: List[CreditPackage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        package_id = str(item.get("package_id") or item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        credits = int(item.get("credits") or 0)
        unit_amount_cents = int(item.get("unit_amount_cents") or item.get("amount_cents") or 0)
        currency = str(item.get("currency") or "usd").strip().lower()
        if package_id and name and credits > 0 and unit_amount_cents > 0 and currency:
            packages.append(
                CreditPackage(
                    package_id=package_id,
                    name=name,
                    credits=credits,
                    unit_amount_cents=unit_amount_cents,
                    currency=currency,
                )
            )
    return packages or DEFAULT_CREDIT_PACKAGES


def _package_by_id(package_id: str) -> CreditPackage:
    normalized = str(package_id or "").strip()
    for package in _load_credit_packages():
        if package.package_id == normalized:
            return package
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown credit package.")


def _transaction_payload(record: Any) -> Dict[str, Any]:
    return {
        "id": getattr(record, "id", None),
        "owner_user_id": getattr(record, "owner_user_id", None),
        "credit_delta": int(getattr(record, "credit_delta", 0) or 0),
        "balance_after": int(getattr(record, "balance_after", 0) or 0),
        "source": getattr(record, "source", None),
        "stripe_checkout_session_id": getattr(record, "stripe_checkout_session_id", None),
        "created_at": getattr(record, "created_at", None),
        "metadata": getattr(record, "metadata_json", None) or {},
    }


@router.get("/credits")
def get_credits_endpoint(owner_user_id: str = Depends(require_deployed_user_id)) -> Dict[str, Any]:
    balance = get_user_credit_balance(owner_user_id)
    transactions = list_user_credit_transactions(owner_user_id, limit=10)
    return {
        **user_credit_balance_public_payload(balance),
        "packages": [_public_package(package) for package in _load_credit_packages()],
        "transactions": [_transaction_payload(transaction) for transaction in transactions],
    }


@router.post("/checkout-sessions")
def create_checkout_session_endpoint(
    request: CheckoutSessionRequest,
    owner_user_id: str = Depends(require_deployed_user_id),
) -> Dict[str, str]:
    stripe = _stripe_module()
    package = _package_by_id(request.package_id)
    quantity = max(1, min(int(request.quantity or 1), 99))
    app_url = _app_base_url()
    success_url = request.success_url or f"{app_url}/settings?credits=success"
    cancel_url = request.cancel_url or f"{app_url}/settings?credits=cancelled"
    session_metadata = {
        "owner_user_id": owner_user_id,
        "package_id": package.package_id,
        "credits_per_unit": str(package.credits),
    }
    kwargs: Dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": owner_user_id,
        "metadata": session_metadata,
        "line_items": [
            {
                "quantity": quantity,
                "adjustable_quantity": {"enabled": True, "minimum": 1, "maximum": 99},
                "price_data": {
                    "currency": package.currency,
                    "unit_amount": package.unit_amount_cents,
                    "product_data": {
                        "name": package.name,
                        "metadata": session_metadata,
                    },
                },
            }
        ],
    }
    email = clerk_user_email(owner_user_id)
    if email:
        kwargs["customer_email"] = email
    session = stripe.checkout.Session.create(**kwargs)
    url = getattr(session, "url", None) or session.get("url")
    if not url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe did not return a Checkout URL.")
    return {"checkout_url": url, "session_id": getattr(session, "id", None) or session.get("id")}


def _event_object_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _session_metadata(session: Any) -> Dict[str, str]:
    value = _event_object_value(session, "metadata")
    return dict(value or {}) if isinstance(value, (dict,)) else {}


def _checkout_session_line_items(stripe: Any, session_id: str) -> List[Any]:
    try:
        response = stripe.checkout.Session.list_line_items(session_id, limit=100)
    except Exception:
        return []
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])


def _quantity_from_line_items(line_items: List[Any]) -> int:
    total = 0
    for item in line_items:
        total += int(_event_object_value(item, "quantity") or 0)
    return total or 1


def _fulfill_checkout_session(stripe: Any, session: Any) -> Dict[str, Any]:
    session_id = str(_event_object_value(session, "id") or "").strip()
    if not session_id:
        raise ValueError("Checkout session id is missing.")
    payment_status = str(_event_object_value(session, "payment_status") or "").lower()
    if payment_status and payment_status != "paid":
        return {"fulfilled": False, "reason": f"payment_status={payment_status}"}
    metadata = _session_metadata(session)
    owner_user_id = metadata.get("owner_user_id") or _event_object_value(session, "client_reference_id")
    if not owner_user_id:
        raise ValueError("Checkout session is missing owner_user_id metadata.")
    package = _package_by_id(metadata.get("package_id") or "")
    credits_per_unit = int(metadata.get("credits_per_unit") or package.credits)
    line_items = _checkout_session_line_items(stripe, session_id)
    quantity = _quantity_from_line_items(line_items)
    credits = credits_per_unit * quantity
    transaction = add_user_credits(
        str(owner_user_id),
        credit_delta=credits,
        source="stripe_checkout",
        stripe_checkout_session_id=session_id,
        stripe_payment_intent_id=_event_object_value(session, "payment_intent"),
        stripe_customer_id=_event_object_value(session, "customer"),
        metadata={
            "package_id": package.package_id,
            "credits_per_unit": credits_per_unit,
            "quantity": quantity,
            "amount_total": _event_object_value(session, "amount_total"),
            "currency": _event_object_value(session, "currency"),
        },
    )
    return {"fulfilled": True, "transaction_id": getattr(transaction, "id", None), "credits": credits}


@router.post("/stripe/webhook")
async def stripe_webhook_endpoint(request: Request) -> Dict[str, Any]:
    stripe = _stripe_module()
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, signature, _stripe_webhook_secret())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook payload.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook signature.") from exc

    event_type = _event_object_value(event, "type")
    if event_type == "checkout.session.completed":
        session = _event_object_value(_event_object_value(event, "data"), "object")
        return _fulfill_checkout_session(stripe, session)
    return {"received": True, "ignored": event_type}

