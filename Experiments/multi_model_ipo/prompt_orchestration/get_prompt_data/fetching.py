from __future__ import annotations

import time
from datetime import date
import requests
import yfinance as yf

from .utilities import *
from .config import *

def _request_json(
    url: str,
    params: dict,
    api_key: str | None,
) -> dict | list | None:

    global _last_polygon_call
    global _last_fmp_call

    if not api_key:
        return None

    params = dict(params)

    is_polygon = "polygon.io" in url
    is_fmp = "financialmodelingprep.com" in url

    if is_polygon:
        params.setdefault("apiKey", api_key)
    else:
        params.setdefault("apikey", api_key)

    is_polygon = "polygon.io" in url
    is_fmp = "financialmodelingprep.com" in url

    try:

        resp = session.get(url, params=params)

        if resp.status_code == 404:
            return None

        resp.raise_for_status()

        return resp.json()

    except requests.RequestException:
        return None

    except ValueError:
        return None


# =========================================================
# POLYGON
# =========================================================


def get_ipos(start: str, end: str):
    data = _request_json(
        f"{FMP_BASE_URL}/stable/ipos-calendar",
        {
            "from": start,
            "to": end,
        },
        FMP_API_KEY,
    )
    if not data:
        return []
    
    ipos = [
    ipo for ipo in data
    if ipo.get("actions") == "Priced"
    and ipo.get("exchange") in {"NASDAQ", "NYSE", "AMEX", "NYSE ARCA", "NYSE MKT"}
]

    return ipos


# =========================================================
# FMP
# =========================================================


FMP_BASE_URL = "https://financialmodelingprep.com"

def fmp_endpoint(path: str, ticker: str):
    data = _request_json(
        f"{FMP_BASE_URL}/stable/{path}",
        {"symbol": ticker},
        FMP_API_KEY,
    )

    if isinstance(data, list):
        return data[0] if data else {}

    if isinstance(data, dict):
        return data

    return {}


def get_fmp_data(ticker: str):
    return {
        "profile":  fmp_endpoint("profile", ticker),
        "quote":    fmp_endpoint("quote", ticker),
        "income":   fmp_endpoint("income-statement", ticker),
        "balance":  fmp_endpoint("balance-sheet-statement", ticker),
        "cashflow": fmp_endpoint("cash-flow-statement", ticker),

    }


# =========================================================
# MARKET DATA
# =========================================================


def get_market_data(ticker: str):
    try:
        yf_ticker = yf.Ticker(ticker)

        hist = yf_ticker.history(period="6mo")

        if hist.empty:
            return {}

        px = float(hist["Close"].iloc[-1])

        avg_volume = float(hist["Volume"].tail(20).mean())

        dollar_volume = px * avg_volume

        atr = float((hist["High"] - hist["Low"]).tail(14).mean())

        mom_1m = (
            (px / float(hist["Close"].iloc[-21])) - 1
            if len(hist) >= 21
            else 0
        )

        mom_3m = (
            (px / float(hist["Close"].iloc[-63])) - 1
            if len(hist) >= 63
            else 0
        )

        return {
            "price": round(px, 2),
            "avg_volume": int(avg_volume),
            "dollar_volume": int(dollar_volume),
            "atr": round(atr, 2),
            "mom_1m": round(mom_1m * 100, 2),
            "mom_3m": round(mom_3m * 100, 2),
        }

    except:
        return {}


# =========================================================
# ENRICHMENT
# =========================================================

def enrich_company(ticker: str):
    details = get_fmp_data(ticker)

    if not details:
        return None

    listing_date = (
        details["profile"].get("ipoDate")
        or details["profile"].get("ipo_date")
        or details["profile"].get("ipo_Date")
    )

    parsed_listing = parse_date(listing_date)

    # CRITICAL FIX:
    # EXCLUDE FUTURE IPOS
    if parsed_listing is None or parsed_listing > date.today():
        return None

    market_cap = safe_float(details["quote"].get("marketCap"))

    if market_cap is None:
        return None

    if market_cap < MIN_MARKET_CAP:
        return None

    name = details["profile"].get("companyName", ticker)

    description = details["profile"].get("description", "UNKNOWN")

    # FILTER JUNK
    if looks_like_spac(name, description):
        return None

    if looks_shellish(name, description):
        return None

    market = get_market_data(ticker)

    # LIQUIDITY FILTER
    if market.get("dollar_volume", 0) < MIN_DOLLAR_VOLUME:
        return None

    flags = []

    if looks_biotech(name, description):
        flags.append("BIOTECH")

    return {
        "ticker": ticker,
        "name": name,
        "description": description,
        "listing_date": str(parsed_listing),
        "market_cap": market_cap,
        "sector": (
            details["profile"].get("industry")
            or details.get("sic_description")
            or details["profile"].get("sector")
            or "Unknown"
        ),
        "flags": flags,
        "price": market.get("price"),
        "avg_volume": market.get("avg_volume"),
        "dollar_volume": market.get("dollar_volume"),
        "atr": market.get("atr"),
        "mom_1m": market.get("mom_1m"),
        "mom_3m": market.get("mom_3m"),
        "revenue": safe_float(details["income"].get("revenue")),
        "net_income": safe_float(details["income"].get("netIncome")),
        "cash": safe_float(
            details["balance"].get("cashAndCashEquivalents")
        ),
        "debt": safe_float(details["balance"].get("totalDebt")),
        "ocf": safe_float(
            details["cashflow"].get("operatingCashFlow")
        ),
    }

if __name__ == "__main__":
    print(get_ipos("2025-06-25", "2026-07-21"))