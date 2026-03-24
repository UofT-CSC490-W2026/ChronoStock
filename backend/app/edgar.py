"""
SEC EDGAR integration — fetches 8-K filings and Form 4 insider transactions.

Pipeline:
  ticker → CIK (via company_tickers.json) → submissions API → SECFiling list

Rate limit: 10 req/sec. User-Agent header is required by SEC.
"""

import os

import httpx

from . import cache
from .models import SECFiling

_email = os.environ.get("SEC_USER_AGENT_EMAIL", "")
USER_AGENT = f"ChronoStock {_email}".strip()
HEADERS = {"User-Agent": USER_AGENT}

ITEM_LABELS: dict[str, str] = {
    "1.01": "Material Agreement",
    "1.02": "Agreement Terminated",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition/Disposition",
    "2.02": "Earnings Release",
    "2.03": "Financial Obligation Created",
    "3.01": "Delisting Notice",
    "4.02": "Restatement",
    "5.01": "Charter Amendment",
    "5.02": "Leadership Change",
    "5.03": "Bylaw Amendment",
    "6.01": "ABS Event",
    "7.01": "Reg FD Disclosure",
    "8.01": "Material Event",
    "9.01": "Financial Statements",
}


def _get_cik(ticker: str) -> str | None:
    """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
    CACHE_KEY = "sec:cik_map"

    cached = cache.get(CACHE_KEY)
    if cached:
        ticker_map: dict[str, int] = cached["data"]
        cik_int = ticker_map.get(ticker.upper())
        if cik_int is None:
            return None
        return str(cik_int).zfill(10)

    # Download the full ticker→CIK mapping from SEC
    resp = httpx.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    raw: dict = resp.json()

    # Build a flat {TICKER: cik_int} map
    ticker_map = {entry["ticker"].upper(): entry["cik_str"] for entry in raw.values()}

    cache.set(CACHE_KEY, {"data": ticker_map})

    cik_int = ticker_map.get(ticker.upper())
    if cik_int is None:
        return None
    return str(cik_int).zfill(10)


def fetch_sec_filings(ticker: str) -> list[SECFiling]:
    """
    Fetch recent 8-K and Form 4 filings for a ticker from SEC EDGAR.
    Returns a list sorted by date descending.
    """
    cik = _get_cik(ticker)
    if not cik:
        return []

    resp = httpx.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    acc_numbers: list[str] = recent.get("accessionNumber", [])
    filing_dates: list[str] = recent.get("filingDate", [])
    forms: list[str] = recent.get("form", [])
    primary_docs: list[str] = recent.get("primaryDocument", [])
    items_raw: list[str] = recent.get("items", [])

    # CIK without leading zeros for URL path
    cik_int_str = str(int(cik))

    results: list[SECFiling] = []

    for acc, date, form, doc, items_str in zip(
        acc_numbers, filing_dates, forms, primary_docs, items_raw
    ):
        if form not in ("8-K", "4"):
            continue

        # Build the SEC filing URL
        acc_no_hyphens = acc.replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int_str}/{acc_no_hyphens}/{doc}"
        )

        if form == "8-K":
            item_list = [i.strip() for i in items_str.split(",") if i.strip()]
            label = " · ".join(
                ITEM_LABELS.get(i, f"Item {i}") for i in item_list
            ) or "8-K Filing"
        else:
            item_list = []
            label = "Insider Transaction"

        results.append(SECFiling(
            date=date,
            form=form,
            items=item_list,
            label=label,
            url=url,
        ))


    # Already in reverse-chronological order from EDGAR, but sort to be safe
    results.sort(key=lambda f: f.date, reverse=True)
    return results
