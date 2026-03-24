import os
import uuid
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timezone
from datetime import date, timedelta
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .models import OHLCBar, StockResponse, SearchResult, UserCreate, Token, WatchlistItem, TrendingItem, StockNews, EarningsDate, SECFiling, ForgotPasswordRequest, ResetPasswordRequest, MessageResponse
from .stock import fetch_bars, fetch_info, search_tickers, fetch_news, fetch_earnings_dates
from .edgar import fetch_sec_filings
from . import cache
from .database import init_db, get_conn, cursor as db_cursor, PH
from .auth import hash_password, verify_password, create_token, get_current_user

app = FastAPI(title="ChronoStock API", version="0.1.0")

# ── Rate limiting ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup_event():
    init_db()

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    os.environ.get("FRONTEND_URL", ""),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*", "Authorization"],
)

# ── Email helper ──────────────────────────────────────────────────────────────

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "log")  # "log" | "ses"
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "")


def _send_reset_email(to_email: str, reset_link: str) -> None:
    if EMAIL_BACKEND == "ses":
        import boto3
        ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": "Reset your ChronoStock password"},
                "Body": {"Text": {"Data": f"Click the link to reset your password (expires in 1 hour):\n\n{reset_link}"}},
            },
        )
    else:
        # Dev mode: print link to stdout so you can copy it from the server log
        print(f"[PASSWORD RESET] {to_email} → {reset_link}", flush=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

RANGE_DAYS: dict[str, int] = {
    "1W": 7,
    "1M": 30,
    "6M": 182,
    "1Y": 365,
    "5Y": 1825,
}

TimeRange = Literal["1W", "1M", "6M", "1Y", "5Y", "ALL"]


def _filter_bars(bars: list[OHLCBar], range_key: str) -> list[OHLCBar]:
    if range_key == "ALL":
        return bars
    cutoff = (date.today() - timedelta(days=RANGE_DAYS[range_key])).isoformat()
    return [b for b in bars if b.time >= cutoff]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/stock/{ticker}", response_model=StockResponse)
@limiter.limit("60/minute")
def get_stock(
    request: Request,
    ticker: str,
    range: TimeRange = Query(default="1Y"),
):
    ticker = ticker.upper()

    STOCK_CACHE_TTL_HOURS = 24

    # One cache file per ticker — stores full history + timestamp
    cached = cache.get(f"stock:{ticker}")
    cache_fresh = False
    if cached is not None:
        cached_at_str = cached.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=STOCK_CACHE_TTL_HOURS):
                cache_fresh = True

    if cache_fresh:
        full = StockResponse(**{k: v for k, v in cached.items() if k != "cached_at"})
    else:
        try:
            bars = fetch_bars(ticker)
            company_name, meta, asset_type = fetch_info(ticker)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Data provider error: {e}")

        full = StockResponse(
            ticker=ticker,
            companyName=company_name,
            assetType=asset_type,
            bars=bars,
            events=[],  # AI layer plugs in here later
            meta=meta,
        )
        payload = full.model_dump()
        payload["cached_at"] = datetime.now(timezone.utc).isoformat()
        cache.set(f"stock:{ticker}", payload)

    # Slice to the requested range in memory — no extra network call
    filtered_bars = _filter_bars(full.bars, range)
    from_date = filtered_bars[0].time if filtered_bars else ""
    filtered_events = [e for e in full.events if e.time >= from_date]

    return StockResponse(
        ticker=full.ticker,
        companyName=full.companyName,
        assetType=full.assetType,
        bars=filtered_bars,
        events=filtered_events,
        meta=full.meta,
    )


@app.get("/api/earnings/{ticker}", response_model=list[EarningsDate])
@limiter.limit("60/minute")
def get_earnings(request: Request, ticker: str):
    ticker = ticker.upper()
    CACHE_KEY = f"earnings:{ticker}"
    CACHE_TTL_HOURS = 24

    cached = cache.get(CACHE_KEY)
    if cached:
        cached_at_str = cached.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=CACHE_TTL_HOURS):
                return [EarningsDate(**item) for item in cached["items"]]

    try:
        items = fetch_earnings_dates(ticker)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Earnings fetch error: {e}")

    cache.set(CACHE_KEY, {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump() for item in items],
    })
    return items


@app.get("/api/news/{ticker}", response_model=list[StockNews])
@limiter.limit("60/minute")
def get_news(request: Request, ticker: str):
    ticker = ticker.upper()
    NEWS_CACHE_TTL_HOURS = 24
    CACHE_KEY = f"news:{ticker}"

    cached = cache.get(CACHE_KEY)
    if cached:
        cached_at_str = cached.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=NEWS_CACHE_TTL_HOURS):
                return [StockNews(**item) for item in cached["items"]]

    try:
        items = fetch_news(ticker, limit=250)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"News fetch error: {e}")

    cache.set(CACHE_KEY, {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump() for item in items],
    })
    return items


@app.get("/api/prices", response_model=list[TrendingItem])
@limiter.limit("30/minute")
def prices(request: Request, tickers: str = Query(description="Comma-separated list of tickers")):
    """Bulk price fetch for a list of tickers (used by watchlist enrichment)."""
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        return []

    PRICE_CACHE_TTL_HOURS = 24
    results: list[TrendingItem] = []
    missing: list[str] = []

    for sym in symbols:
        cached = cache.get(f"price:{sym}")
        if cached:
            cached_at_str = cached.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                if datetime.now(timezone.utc) - cached_at < timedelta(hours=PRICE_CACHE_TTL_HOURS):
                    results.append(TrendingItem(**{k: v for k, v in cached.items() if k != "cached_at"}))
                    continue
        missing.append(sym)

    if missing:
        try:
            from yahooquery import Ticker as YQTicker
            price_data = YQTicker(missing).price
            for sym in missing:
                info = price_data.get(sym, {})
                if not isinstance(info, dict):
                    results.append(TrendingItem(ticker=sym, companyName=sym))
                    continue
                item = TrendingItem(
                    ticker=sym,
                    companyName=info.get("longName") or info.get("shortName") or sym,
                    price=info.get("regularMarketPrice"),
                    change=info.get("regularMarketChange"),
                    changePct=info.get("regularMarketChangePercent"),
                )
                payload = item.model_dump()
                payload["cached_at"] = datetime.now(timezone.utc).isoformat()
                cache.set(f"price:{sym}", payload)
                results.append(item)
        except Exception:
            for sym in missing:
                results.append(TrendingItem(ticker=sym, companyName=sym))

    # Preserve original order
    order = {sym: i for i, sym in enumerate(symbols)}
    results.sort(key=lambda r: order.get(r.ticker, 999))
    return results


@app.get("/api/sec/{ticker}", response_model=list[SECFiling])
@limiter.limit("60/minute")
def get_sec_filings(request: Request, ticker: str):
    ticker = ticker.upper()
    CACHE_KEY = f"sec:filings:{ticker}"
    CACHE_TTL_HOURS = 24

    cached = cache.get(CACHE_KEY)
    if cached:
        cached_at_str = cached.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=CACHE_TTL_HOURS):
                return [SECFiling(**item) for item in cached["items"]]

    try:
        items = fetch_sec_filings(ticker)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SEC EDGAR error: {e}")

    cache.set(CACHE_KEY, {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump() for item in items],
    })
    return items


@app.get("/api/search", response_model=list[SearchResult])
@limiter.limit("30/minute")
def search(request: Request, q: str = Query(min_length=1)):
    return [SearchResult(**r) for r in search_tickers(q)]


@app.get("/api/trending", response_model=list[TrendingItem])
@limiter.limit("30/minute")
def trending(request: Request):
    CACHE_KEY = "trending"
    CACHE_TTL_HOURS = 24

    # Return cached data if it is less than 24 hours old
    cached = cache.get(CACHE_KEY)
    if cached:
        cached_at = datetime.fromisoformat(cached["cached_at"])
        if datetime.now(timezone.utc) - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            return [TrendingItem(**item) for item in cached["items"]]

    try:
        from yahooquery import get_trending, Ticker as YQTicker

        data = get_trending()
        quotes = data.get("quotes", [])
        # Exclude indices (^GSPC etc.) and keep up to 12 symbols
        symbols = [q["symbol"] for q in quotes if not q["symbol"].startswith("^")][:12]

        if not symbols:
            return []

        # Bulk-fetch price + name in one request
        price_data = YQTicker(symbols).price

        items: list[TrendingItem] = []
        for sym in symbols:
            info = price_data.get(sym, {})
            if not isinstance(info, dict):
                continue
            items.append(TrendingItem(
                ticker=sym,
                companyName=info.get("longName") or info.get("shortName") or sym,
                price=info.get("regularMarketPrice"),
                change=info.get("regularMarketChange"),
                changePct=info.get("regularMarketChangePercent"),
            ))

        cache.set(CACHE_KEY, {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "items": [item.model_dump() for item in items],
        })
        return items

    except Exception:
        return []


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/auth/signup", response_model=Token)
@limiter.limit("5/minute")
def signup(request: Request, body: UserCreate):
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"SELECT id FROM users WHERE email = {PH}", (body.email,)
            )
            existing = cur.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        hashed = hash_password(body.password)

        with db_cursor(conn) as cur:
            cur.execute(
                f"INSERT INTO users (id, email, hashed_password, created_at) VALUES ({PH}, {PH}, {PH}, {PH})",
                (user_id, body.email, hashed, created_at),
            )
        conn.commit()
    finally:
        conn.close()

    token = create_token(user_id=user_id, email=body.email)
    return Token(access_token=token)


@app.post("/auth/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, body: UserCreate):
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"SELECT id, email, hashed_password FROM users WHERE email = {PH}", (body.email,)
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or not verify_password(body.password, row["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user_id=row["id"], email=row["email"])
    return Token(access_token=token)


@app.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["sub"], "email": current_user["email"]}


@app.post("/auth/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest):
    import secrets
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(f"SELECT id FROM users WHERE email = {PH}", (body.email,))
            row = cur.fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            with db_cursor(conn) as cur:
                cur.execute(
                    f"INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES ({PH}, {PH}, {PH})",
                    (token, row["id"], expires_at),
                )
            conn.commit()

            frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
            reset_link = f"{frontend_url}/reset-password?token={token}"
            _send_reset_email(body.email, reset_link)
    finally:
        conn.close()
    # Always return the same message to avoid leaking which emails are registered
    return MessageResponse(message="If that email is registered, a reset link has been sent.")


@app.post("/auth/reset-password", response_model=MessageResponse)
@limiter.limit("10/minute")
def reset_password(request: Request, body: ResetPasswordRequest):
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"SELECT user_id, expires_at FROM password_reset_tokens WHERE token = {PH}",
                (body.token,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

        hashed = hash_password(body.new_password)
        with db_cursor(conn) as cur:
            cur.execute(
                f"UPDATE users SET hashed_password = {PH} WHERE id = {PH}",
                (hashed, row["user_id"]),
            )
            cur.execute(
                f"DELETE FROM password_reset_tokens WHERE token = {PH}",
                (body.token,),
            )
        conn.commit()
    finally:
        conn.close()
    return MessageResponse(message="Password updated successfully.")


# ── Watchlist routes ──────────────────────────────────────────────────────────

@app.get("/api/watchlist", response_model=list[WatchlistItem])
def get_watchlist(current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"SELECT ticker, added_at FROM watchlist WHERE user_id = {PH} ORDER BY added_at DESC",
                (current_user["sub"],),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [WatchlistItem(ticker=row["ticker"], added_at=row["added_at"]) for row in rows]


@app.post("/api/watchlist/{ticker}", status_code=204)
def add_to_watchlist(ticker: str, current_user: dict = Depends(get_current_user)):
    ticker = ticker.upper()
    added_at = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"INSERT INTO watchlist (user_id, ticker, added_at) VALUES ({PH}, {PH}, {PH}) ON CONFLICT DO NOTHING",
                (current_user["sub"], ticker, added_at),
            )
        conn.commit()
    finally:
        conn.close()


@app.delete("/api/watchlist/{ticker}", status_code=204)
def remove_from_watchlist(ticker: str, current_user: dict = Depends(get_current_user)):
    ticker = ticker.upper()
    conn = get_conn()
    try:
        with db_cursor(conn) as cur:
            cur.execute(
                f"DELETE FROM watchlist WHERE user_id = {PH} AND ticker = {PH}",
                (current_user["sub"], ticker),
            )
        conn.commit()
    finally:
        conn.close()