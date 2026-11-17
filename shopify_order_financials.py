"""Financial pairs from Shopify; missing fields are never a clearing instruction."""
from decimal import Decimal, InvalidOperation
import re


def money_pair(amount, currency):
    if amount is None or isinstance(amount, bool) or not isinstance(currency, str):
        return None
    currency = currency.strip()
    if not re.fullmatch(r"[A-Z]{3}", currency) or not str(amount).strip():
        return None
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return format(value, "f"), currency


def graphql_financial_fields(node):
    if "totalPriceSet" not in node:
        return {"_financial_fields_state": "missing"}
    price = node.get("totalPriceSet")
    money = price.get("shopMoney") if isinstance(price, dict) else None
    if not isinstance(money, dict) or "amount" not in money or "currencyCode" not in money:
        return {"_financial_fields_state": "incomplete"}
    pair = money_pair(money["amount"], money["currencyCode"])
    if pair is None:
        return {"_financial_fields_state": "invalid"}
    return {"total_price": pair[0], "currency": pair[1], "_financial_fields_state": "complete"}


def prepare_financial_fields(order):
    """Also protect callers supplying normalized webhook/legacy dictionaries."""
    prepared = dict(order)
    pair = money_pair(order.get("total_price"), order.get("currency"))
    prepared.pop("total_price", None)
    prepared.pop("currency", None)
    if pair is not None:
        prepared.update(total_price=pair[0], currency=pair[1])
    return prepared
