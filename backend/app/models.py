from pydantic import BaseModel
from typing import Literal, Optional


class OHLCBar(BaseModel):
    time: str          # "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: int


class NewsEvent(BaseModel):
    id: str
    time: str          # "YYYY-MM-DD" — maps to chart x-axis
    title: str
    summary: str
    sentiment: Literal["positive", "negative", "neutral"]
    source: str
    url: str | None = None


class StockMeta(BaseModel):
    marketCap: Optional[float] = None
    revenue: Optional[float] = None
    netIncome: Optional[float] = None
    eps: Optional[float] = None
    sharesOutstanding: Optional[float] = None
    peRatio: Optional[float] = None
    forwardPE: Optional[float] = None
    dividendRate: Optional[float] = None
    dividendYield: Optional[float] = None
    exDividendDate: Optional[str] = None
    volume: Optional[int] = None
    previousClose: Optional[float] = None
    dayLow: Optional[float] = None
    dayHigh: Optional[float] = None
    weekLow52: Optional[float] = None
    weekHigh52: Optional[float] = None
    beta: Optional[float] = None
    analystRating: Optional[str] = None
    priceTarget: Optional[float] = None
    earningsDate: Optional[str] = None


class StockResponse(BaseModel):
    ticker: str
    companyName: str
    assetType: str = "equity"   # "equity" | "index" | "crypto" | "etf" | "unknown"
    bars: list[OHLCBar]
    events: list[NewsEvent]
    meta: Optional[StockMeta] = None


class SearchResult(BaseModel):
    ticker: str
    companyName: str


class UserCreate(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WatchlistItem(BaseModel):
    ticker: str
    added_at: str


class EarningsDate(BaseModel):
    date: str                          # "YYYY-MM-DD"
    epsEstimate: Optional[float] = None
    reportedEps: Optional[float] = None
    surprisePct: Optional[float] = None   # positive = beat, negative = miss


class StockNews(BaseModel):
    id: str
    time: str                    # "YYYY-MM-DD"
    title: str
    publisher: str
    url: Optional[str] = None
    summary: Optional[str] = None
    thumbnail: Optional[str] = None


class TrendingItem(BaseModel):
    ticker: str
    companyName: str
    price: Optional[float] = None
    change: Optional[float] = None
    changePct: Optional[float] = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class SECFiling(BaseModel):
    date: str           # "YYYY-MM-DD" (filingDate)
    form: str           # "8-K" or "4"
    items: list[str]    # ["1.01", "5.02"] — empty for Form 4
    label: str          # human-readable event description
    url: str            # full sec.gov filing URL
