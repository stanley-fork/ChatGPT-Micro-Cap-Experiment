import yfinance as yf
import datetime
from libb.execution.get_market_data import download_data_on_given_date
from libb import LIBBmodel

import io
import csv

# loop through orders
# if company is an IPO (age < 3 years) or market cap < 200M, append to rejected_orders with reasons
# otherwise append to filtered_orders
# return the filtered orders and the rejected orders
# take rejected order dict and (if not None) append to `filtered_orders.csv` via `save_additional_log()` from LIBB
# TODO: fix potential type hint error of orders being "dict" and not "list[dict]" in LIBB

TODAY = datetime.date.today()
MINIMUM_MARKET_CAP = 200_000_000
IPO_LOCKOUT_YEARS = 3

import os
import requests

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY")

def _get_shares_outstanding(ticker: str) -> float:
    """
    Try yfinance first, fall back to Polygon if yfinance fails.
    Returns 0 if both fail so market_cap math doesn't crash.
    """
    # --- attempt 1: yfinance ---
    try:
        info = yf.Ticker(ticker).info
        shares = info.get("sharesOutstanding")
        if shares:
            return float(shares)
    except Exception:
        pass

    # --- attempt 2: Polygon ---
    try:
        resp = requests.get(
            f"https://api.polygon.io/v3/reference/tickers/{ticker}",
            params={"apiKey": MASSIVE_API_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("results", {})
            shares = data.get("share_class_shares_outstanding") or data.get("weighted_shares_outstanding")
            if shares:
                return float(shares)
    except Exception:
        pass

    return 0  # both failed — market_cap will be 0, rejection check will catch it

def _get_ipo_date(ticker: str) -> datetime.date | None:
    """
    Try yfinance first, fall back to Polygon if yfinance fails.
    Returns None if both fail — caller treats this as unverifiable.
    """
    # --- attempt 1: yfinance ---
    try:
        info = yf.Ticker(ticker).info
        raw = info.get("ipoDate") or info.get("firstTradeDateEpochUtc")
        if raw:
            if isinstance(raw, int):  # epoch
                return datetime.date.fromtimestamp(raw)
            return datetime.date.fromisoformat(raw)
    except Exception:
        pass

    # --- attempt 2: Polygon ---
    try:
        resp = requests.get(
            f"https://api.polygon.io/v3/reference/tickers/{ticker}",
            params={"apiKey": MASSIVE_API_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("results", {})
            raw = data.get("list_date")
            if raw:
                return datetime.date.fromisoformat(raw)
    except Exception:
        pass

    return None


def _get_rejection_reasons(ticker: str, market_cap: float) -> list[str]:
    """
    Collect ALL reasons an order should be rejected rather than checking them
    one at a time. This prevents an order from appearing in rejected_orders
    multiple times while still surfacing every problem.

    Returns an empty list if the order passes all checks.
    """
    reasons = []

    # --- IPO check ---
    # `ipoDate` from yfinance is a "YYYY-MM-DD" string; we parse it into a
    # date object so we can do real calendar arithmetic.
    ipo_date = _get_ipo_date(ticker)
    if ipo_date:
        age_years = (TODAY - ipo_date).days / 365.25
        if age_years < IPO_LOCKOUT_YEARS:
            reasons.append(f"IPO too recent ({age_years:.1f} yrs < {IPO_LOCKOUT_YEARS})")
    else:
        reasons.append("IPO date unknown — cannot verify age")

    # --- Market cap check ---
    if market_cap < MINIMUM_MARKET_CAP:
        reasons.append(f"market cap too low (${market_cap:,.0f} < ${MINIMUM_MARKET_CAP:,.0f})")

    return reasons  # empty → passes all checks; non-empty → one or more failures


def filter_orders(orders: list[str, dict]) -> tuple[list[dict], list[dict] | None]:

    orders = orders.get("orders", [])

    rejected_orders: list[dict] = []
    filtered_orders: list[dict] = []

    for order in orders:
        order_type = order.get("order_type", "NULL")
        action = order.get("action", "NULL")
        ticker = order.get("ticker", "NULL")
        limit_price = order.get("limit_price", 0)
        date = datetime.date.fromisoformat(order["date"])

        if action != "b":
            filtered_orders.append(order)
            continue  # only reject buys; sells/holds pass straight through

        shares_outstanding = _get_shares_outstanding(ticker)

        if order_type == "LIMIT":
            if limit_price:
                market_cap = shares_outstanding * limit_price
            else: 
                market_cap = 0

        else:  # MARKET order
            if date > TODAY:
                filtered_orders.append(order)
                continue  # future order — open price unknown, revisit later

            if ticker != "NULL":
                ticker_data = download_data_on_given_date(ticker, TODAY)
                open_price = ticker_data["Open"]
            else:
                open_price = 0

            market_cap = shares_outstanding * open_price

        # --- Single rejection gate ---
        # Both checks run regardless of each other; reasons accumulates all failures.
        reasons = _get_rejection_reasons(ticker, market_cap)

        if reasons:
            # Attach the reasons to a new copy
            rejected_orders.append({**order, "rejection_reasons": reasons})
        else:
            filtered_orders.append(order)

    filtered_orders = {"orders": filtered_orders}

    return filtered_orders, rejected_orders or None