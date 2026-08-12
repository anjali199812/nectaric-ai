"""
Nectaric AI — Decision Engine
BUY / WATCH / SKIP analysis with ATR entry tiers, RSI/MACD, and
6-step long-term playbook scoring.  Called by api/main.py /api/decision.
"""

import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import requests as _req

try:
    import yfinance as yf
    from curl_cffi import requests as cffi_requests
    _yf_session = cffi_requests.Session(impersonate='chrome')
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

_AV_KEY  = os.environ.get('ALPHAVANTAGE_API_KEY')
_AV_BASE = 'https://www.alphavantage.co/query'


# ── SHARED HELPERS ──────────────────────────────────────────────────────────────

def _safe_float(val):
    if val in (None, 'None', '-', '', 'N/A'):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def fmt_cap(cap):
    if cap is None: return 'N/A'
    if cap >= 1e12: return f'${cap/1e12:.1f}T'
    if cap >= 1e9:  return f'${cap/1e9:.1f}B'
    return f'${cap/1e6:.0f}M'

def wk52_label(price, low, high):
    if high == low: return 'N/A'
    pct = (price - low) / (high - low) * 100
    if pct >= 85: return f'{pct:.0f}% of range — near 52wk HIGH'
    if pct <= 20: return f'{pct:.0f}% of range — near 52wk LOW'
    return f'{pct:.0f}% of 52wk range — mid-range'

def position_guide(beta):
    if beta is None: return 'Unknown — use 8-10% as safe default'
    try:
        b = float(beta)
    except (TypeError, ValueError):
        return 'Unknown — use 8-10% as safe default'
    if b < 0.5:  return '15-20% of portfolio (very low volatility)'
    if b < 0.8:  return '12-15% of portfolio (low volatility)'
    if b < 1.3:  return '10-12% of portfolio (moderate volatility)'
    if b < 1.8:  return '8-10% of portfolio (high volatility)'
    if b < 2.5:  return '5-8% of portfolio (very high volatility)'
    return '3-5% of portfolio (speculative)'


# ── PRICE / DERIVED FIELDS ──────────────────────────────────────────────────────

def _calc_derived(df, price, wk52_high, wk52_low):
    prev_cls = df['Close'].shift(1)
    tr  = pd.concat([df['High'] - df['Low'],
                     (df['High'] - prev_cls).abs(),
                     (df['Low']  - prev_cls).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().dropna().iloc[-1])

    vol_20d   = float(df['Volume'].tail(20).mean())
    vol_5d    = float(df['Volume'].tail(5).mean())
    vol_ratio = round(vol_5d / vol_20d, 2) if vol_20d > 0 else 1.0

    price_4wk    = float(df['Close'].iloc[-20]) if len(df) >= 20 else price
    momentum_pct = round((price - price_4wk) / price_4wk * 100, 1)

    ma_50d  = float(df['Close'].tail(50).mean())
    ma_200d = float(df['Close'].tail(200).mean()) if len(df) >= 200 else None

    _c     = df['Close']
    _delta = _c.diff()
    _gain  = _delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    _loss  = (-_delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    _rsi_s = 100 - 100 / (1 + _gain / _loss)
    rsi_val = round(float(_rsi_s.iloc[-1]), 1) if len(_rsi_s) > 14 else None

    _ema12   = _c.ewm(span=12, adjust=False).mean()
    _ema26   = _c.ewm(span=26, adjust=False).mean()
    _macd_l  = _ema12 - _ema26
    _macd_sg = _macd_l.ewm(span=9, adjust=False).mean()
    _macd_hv = _macd_l - _macd_sg
    macd_hist_val = round(float(_macd_hv.iloc[-1]), 4) if len(_c) > 26 else None
    macd_bull_val = bool(_macd_hv.iloc[-1] > 0)        if len(_c) > 26 else None

    _ema20  = _c.ewm(span=20, adjust=False).mean()
    _bb_std = _c.rolling(20).std()
    _bb_up  = (_ema20 + 2 * _bb_std).iloc[-1]
    _bb_lo  = (_ema20 - 2 * _bb_std).iloc[-1]

    # ── Historical series for sparklines (last 52 daily points) ──────────
    def _s(arr, rnd=2):
        return [round(float(v), rnd) if not np.isnan(v) else None for v in arr.values[-52:]]

    _vr_s  = df['Volume'].rolling(5).mean() / df['Volume'].rolling(20).mean()
    _ma50s = _c.rolling(50).mean()
    _pma50 = (_c - _ma50s) / _ma50s * 100

    return dict(
        atr          = round(atr, 2),
        wk52_high    = wk52_high,
        wk52_low     = wk52_low,
        st_tier1     = round(wk52_high - 1.0 * atr, 2),
        st_tier2     = round(wk52_high - 2.5 * atr, 2),
        st_tier3     = round(wk52_high - 5.0 * atr, 2),
        lt_tier1     = round(wk52_high * 0.92, 2),
        lt_tier2     = round(wk52_high * 0.82, 2),
        lt_tier3     = round(wk52_high * 0.72, 2),
        vol_ratio    = vol_ratio,
        momentum_pct = momentum_pct,
        ma_50d       = round(ma_50d, 2),
        ma_200d      = round(ma_200d, 2) if ma_200d else None,
        rsi          = rsi_val,
        macd_hist    = macd_hist_val,
        macd_bullish = macd_bull_val,
        bb_upper     = round(float(_bb_up), 2),
        bb_lower     = round(float(_bb_lo), 2),
        hist_rsi           = _s(_rsi_s, 1),
        hist_macd          = _s(_macd_hv, 4),
        hist_vol_ratio     = _s(_vr_s, 2),
        hist_price_vs_ma50 = _s(_pma50, 1),
    )


# ── DATA SOURCES ────────────────────────────────────────────────────────────────

def _av(params):
    p = {'apikey': _AV_KEY, **params}
    r = _req.get(_AV_BASE, params=p, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_alphavantage(ticker):
    try:
        ov = _av({'function': 'OVERVIEW', 'symbol': ticker})
        if not ov or 'Symbol' not in ov:
            msg = ov.get('Note') or ov.get('Information') or f'Ticker "{ticker}" not found.'
            return None, msg

        ts = _av({'function': 'TIME_SERIES_DAILY_ADJUSTED', 'symbol': ticker, 'outputsize': 'full'})
        series = ts.get('Time Series (Daily)', {})
        if not series:
            return None, ts.get('Note') or ts.get('Information') or 'No price data returned.'

        records = [{'Close': float(d['5. adjusted close']),
                    'High':  float(d['2. high']),
                    'Low':   float(d['3. low']),
                    'Volume':float(d['6. volume'])}
                   for date, d in sorted(series.items())]

        df = pd.DataFrame(records)
        if len(df) < 20:
            return None, 'Not enough price history.'

        price     = float(df['Close'].iloc[-1])
        wk52_high = _safe_float(ov.get('52WeekHigh')) or float(df['High'].tail(252).max())
        wk52_low  = _safe_float(ov.get('52WeekLow'))  or float(df['Low'].tail(252).min())
        derived   = _calc_derived(df, price, wk52_high, wk52_low)

        gp  = _safe_float(ov.get('GrossProfitTTM'))
        rev = _safe_float(ov.get('RevenueTTM'))
        gm  = (gp / rev) if (gp and rev and rev != 0) else None
        tpe = _safe_float(ov.get('TrailingPE')) or _safe_float(ov.get('PERatio'))

        chart_dates = [str(r) for r in df.index]
        chart_close = [round(float(v), 2) for v in df['Close'].values]
        _cma50  = df['Close'].rolling(50).mean()
        _cma200 = df['Close'].rolling(200).mean()
        chart_ma50  = [round(float(v), 2) if not np.isnan(v) else None for v in _cma50.values]
        chart_ma200 = [round(float(v), 2) if not np.isnan(v) else None for v in _cma200.values]

        return {
            'name':            ov.get('Name') or ticker,
            'sector':          ov.get('Sector') or 'N/A',
            'price':           price,
            'market_cap':      _safe_float(ov.get('MarketCapitalization')),
            'dividend_yield':  _safe_float(ov.get('DividendYield')),
            'beta':            _safe_float(ov.get('Beta')),
            'peg':             _safe_float(ov.get('PEGRatio')),
            'forward_pe':      _safe_float(ov.get('ForwardPE')),
            'trailing_pe':     tpe,
            'revenue_growth':  _safe_float(ov.get('QuarterlyRevenueGrowthYOY')),
            'earnings_growth': _safe_float(ov.get('QuarterlyEarningsGrowthYOY')),
            'eps':             _safe_float(ov.get('EPS')),
            'gross_margin':    gm,
            'analyst_target':  None,
            'analyst_rec':     'N/A',
            'short_ratio':     None,
            'debt_to_equity':  None,
            'chart_dates':     chart_dates,
            'chart_close':     chart_close,
            'chart_ma50':      chart_ma50,
            'chart_ma200':     chart_ma200,
            **derived,
        }, None

    except Exception as e:
        return None, f'Could not fetch data: {e}'


def fetch_yfinance(ticker):
    try:
        stock = yf.Ticker(ticker, session=_yf_session)
        info  = stock.info

        if not info or (info.get('regularMarketPrice') is None and info.get('currentPrice') is None):
            return None, f'Ticker "{ticker}" not found. Check the spelling.'

        hist = stock.history(period='1y', auto_adjust=True)
        if hist.empty or len(hist) < 20:
            return None, f'Not enough price history for "{ticker}".'

        price     = float(info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1])
        wk52_high = float(info.get('fiftyTwoWeekHigh') or hist['High'].max())
        wk52_low  = float(info.get('fiftyTwoWeekLow')  or hist['Low'].min())
        derived   = _calc_derived(hist, price, wk52_high, wk52_low)

        chart_dates = [str(d.date()) for d in hist.index]
        chart_close  = [round(float(v), 2) for v in hist['Close'].values]
        _cma50       = hist['Close'].rolling(50).mean()
        _cma200      = hist['Close'].rolling(200).mean()
        chart_ma50   = [round(float(v), 2) if not np.isnan(v) else None for v in _cma50.values]
        chart_ma200  = [round(float(v), 2) if not np.isnan(v) else None for v in _cma200.values]

        def safe(key):
            val = info.get(key)
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        return {
            'name':            info.get('longName') or info.get('shortName') or ticker,
            'sector':          info.get('sector') or info.get('quoteType') or 'N/A',
            'price':           price,
            'market_cap':      safe('marketCap'),
            'dividend_yield':  safe('dividendYield'),
            'beta':            safe('beta'),
            'peg':             safe('pegRatio'),
            'forward_pe':      safe('forwardPE'),
            'trailing_pe':     safe('trailingPE'),
            'revenue_growth':  safe('revenueGrowth'),
            'earnings_growth': safe('earningsGrowth'),
            'eps':             safe('trailingEps'),
            'gross_margin':    safe('grossMargins'),
            'analyst_target':  safe('targetMeanPrice'),
            'analyst_rec':     str(info.get('recommendationKey') or 'N/A').replace('_', ' ').upper(),
            'short_ratio':     safe('shortRatio'),
            'debt_to_equity':  safe('debtToEquity'),
            'current_ratio':   safe('currentRatio'),
            'chart_dates':     chart_dates,
            'chart_close':     chart_close,
            'chart_ma50':      chart_ma50,
            'chart_ma200':     chart_ma200,
            **derived,
        }, None

    except Exception as e:
        return None, f'Could not fetch data: {e}'


def fetch(ticker):
    if _AV_KEY:
        return fetch_alphavantage(ticker)
    if _YF_AVAILABLE:
        return fetch_yfinance(ticker)
    return None, 'No data source available. Set ALPHAVANTAGE_API_KEY or install yfinance.'


# ── SCORING ────────────────────────────────────────────────────────────────────

def score_short(d):
    score, factors = 0, []

    rg = d['revenue_growth']
    if rg is None:
        factors.append(('Revenue Growth', 0, 1, 'N/A', '?'))
    elif rg >= 0.05:
        score += 1
        factors.append(('Revenue Growth', 1, 1, f'+{rg*100:.1f}% YoY — growing', '+'))
    else:
        factors.append(('Revenue Growth', 0, 1, f'{rg*100:.1f}% YoY — weak or declining', '-'))

    eps = d['eps']
    if eps is None:
        factors.append(('Profitability (EPS)', 0, 1, 'N/A', '?'))
    elif eps > 0:
        score += 1
        factors.append(('Profitability (EPS)', 1, 1, f'EPS ${eps:.2f} — profitable', '+'))
    else:
        factors.append(('Profitability (EPS)', 0, 1, f'EPS ${eps:.2f} — loss-making', '-'))

    gm = d['gross_margin']
    if gm is None:
        factors.append(('Gross Margin', 0, 1, 'N/A — common for ETFs', '?'))
    elif gm >= 0.40:
        score += 1
        factors.append(('Gross Margin', 1, 1, f'{gm*100:.0f}% — strong margins', '+'))
    else:
        factors.append(('Gross Margin', 0, 1, f'{gm*100:.0f}% — low margin', '-'))

    peg = d['peg']
    if peg is None:
        factors.append(('PEG Ratio', 0, 1, 'N/A', '?'))
    elif peg <= 2.0:
        score += 1
        factors.append(('PEG Ratio', 1, 1, f'{peg:.2f} — fair or cheap', '+'))
    else:
        factors.append(('PEG Ratio', 0, 1, f'{peg:.2f} — expensive', '-'))

    fpe = d['forward_pe']; tpe = d['trailing_pe']
    if fpe and tpe and fpe < tpe:
        score += 1
        factors.append(('Earnings Direction', 1, 1, f'Fwd P/E {fpe:.1f}x < Trail {tpe:.1f}x — earnings growing', '+'))
    elif fpe and tpe:
        factors.append(('Earnings Direction', 0, 1, f'Fwd P/E {fpe:.1f}x > Trail {tpe:.1f}x — earnings shrinking', '-'))
    else:
        factors.append(('Earnings Direction', 0, 1, 'N/A', '?'))

    price = d['price']
    t1 = d['st_tier1']; t2 = d['st_tier2']; t3 = d['st_tier3']
    if price <= t3:
        score += 3
        factors.append(('Price Zone (ATR)', 3, 3, f'${price:.2f} — Tier 3, deep pullback from 52wk high', '+'))
    elif price <= t2:
        score += 2
        factors.append(('Price Zone (ATR)', 2, 3, f'${price:.2f} — Tier 2, moderate pullback from 52wk high', '+'))
    elif price <= t1:
        score += 1
        factors.append(('Price Zone (ATR)', 1, 3, f'${price:.2f} — Tier 1, small pullback from 52wk high', '~'))
    else:
        pct = round((d['wk52_high'] - price) / d['wk52_high'] * 100, 1)
        factors.append(('Price Zone (ATR)', 0, 3, f'${price:.2f} — only {pct}% below 52wk high, above all tiers', '-'))

    vr = d['vol_ratio']
    if vr >= 1.10:
        score += 1
        factors.append(('Volume Trend', 1, 1, f'{vr:.2f}x avg — activity picking up', '+'))
    elif vr >= 0.80:
        factors.append(('Volume Trend', 0, 1, f'{vr:.2f}x avg — normal, no strong signal', '~'))
    else:
        factors.append(('Volume Trend', 0, 1, f'{vr:.2f}x avg — low activity', '-'))

    rsi = d.get('rsi')
    if rsi is None:
        factors.append(('RSI Momentum (14)', 0, 1, 'N/A — insufficient price history', '?'))
    elif rsi < 55:
        score += 1
        factors.append(('RSI Momentum (14)', 1, 1, f'{rsi:.1f} — not overbought, momentum room remains', '+'))
    elif rsi > 70:
        factors.append(('RSI Momentum (14)', 0, 1, f'{rsi:.1f} — OVERBOUGHT, high-risk entry point', '-'))
    else:
        factors.append(('RSI Momentum (14)', 0, 1, f'{rsi:.1f} — elevated, limited upside momentum', '~'))

    return score, 10, factors


def score_long(d):
    score, factors = 0, []

    rg = d['revenue_growth']
    if rg is None:
        factors.append(('Revenue Growth YoY', 0, 1, 'N/A — check financials manually', '?'))
    elif rg >= 0.05:
        score += 1
        factors.append(('Revenue Growth YoY', 1, 1, f'+{rg*100:.1f}% — business is expanding', '+'))
    else:
        factors.append(('Revenue Growth YoY', 0, 1, f'{rg*100:.1f}% — weak, limited tailwind', '-'))

    eps = d['eps']
    if eps is None:
        factors.append(('Profitability (EPS)', 0, 1, 'N/A', '?'))
    elif eps > 0:
        score += 1
        factors.append(('Profitability (EPS)', 1, 1, f'EPS ${eps:.2f} — company is profitable', '+'))
    else:
        factors.append(('Profitability (EPS)', 0, 1, f'EPS ${eps:.2f} — loss-making', '-'))

    gm = d['gross_margin']
    if gm is None:
        factors.append(('Gross Margin (Moat)', 0, 1, 'N/A — common for ETFs and banks', '?'))
    elif gm >= 0.40:
        score += 1
        factors.append(('Gross Margin (Moat)', 1, 1, f'{gm*100:.0f}% — high margin, likely competitive moat', '+'))
    else:
        factors.append(('Gross Margin (Moat)', 0, 1, f'{gm*100:.0f}% — low margin, limited pricing power', '-'))

    eg = d['earnings_growth']
    if eg is None:
        factors.append(('Earnings Growth', 0, 1, 'N/A', '?'))
    elif eg > 0:
        score += 1
        factors.append(('Earnings Growth', 1, 1, f'+{eg*100:.1f}% — profits growing, compounding in place', '+'))
    else:
        factors.append(('Earnings Growth', 0, 1, f'{eg*100:.1f}% — profits shrinking, investigate before buying', '-'))

    peg = d['peg']
    if peg is None:
        factors.append(('PEG Ratio (core metric)', 0, 2, 'N/A — ETF or pre-profit company', '?'))
    elif peg < 1.0:
        score += 2
        factors.append(('PEG Ratio (core metric)', 2, 2, f'{peg:.2f} — UNDERVALUED relative to growth rate', '+'))
    elif peg <= 2.0:
        score += 1
        factors.append(('PEG Ratio (core metric)', 1, 2, f'{peg:.2f} — fairly valued, acceptable long-term entry', '~'))
    else:
        factors.append(('PEG Ratio (core metric)', 0, 2, f'{peg:.2f} — expensive, paying above what growth justifies', '-'))

    fpe = d['forward_pe']; tpe = d['trailing_pe']
    if fpe and tpe and fpe < tpe:
        score += 1
        factors.append(('Earnings Trajectory', 1, 1, f'Fwd P/E {fpe:.1f}x < Trail {tpe:.1f}x — earnings expected to grow', '+'))
    elif fpe and tpe:
        factors.append(('Earnings Trajectory', 0, 1, f'Fwd P/E {fpe:.1f}x > Trail {tpe:.1f}x — earnings expected to shrink', '-'))
    else:
        factors.append(('Earnings Trajectory', 0, 1, 'N/A', '?'))

    price = d['price']
    peak  = d['wk52_high']
    pullback = round((peak - price) / peak * 100, 1)

    if pullback >= 28:
        score += 2
        factors.append(('Entry Zone (% pullback)', 2, 2, f'{pullback}% below 52wk high — Tier 3, strong margin of safety', '+'))
    elif pullback >= 8:
        score += 1
        factors.append(('Entry Zone (% pullback)', 1, 2, f'{pullback}% below 52wk high — Tier 1-2, reasonable entry', '~'))
    else:
        factors.append(('Entry Zone (% pullback)', 0, 2, f'Only {pullback}% below 52wk high — near peak, limited margin of safety', '-'))

    ma200 = d['ma_200d']
    if ma200 is None:
        factors.append(('200-day MA Trend', 0, 1, 'N/A — less than 1 year of data', '?'))
    elif price > ma200:
        score += 1
        factors.append(('200-day MA Trend', 1, 1, f'Price ${price:.2f} ABOVE 200-day MA ${ma200:.2f} — uptrend intact', '+'))
    else:
        factors.append(('200-day MA Trend', 0, 1, f'Price ${price:.2f} BELOW 200-day MA ${ma200:.2f} — long-term downtrend', '-'))

    rsi = d.get('rsi')
    if rsi is not None:
        rsi_ctx = ('overbought >70 — consider waiting for RSI to cool below 60' if rsi > 70
                   else 'oversold <30 — potential mean-reversion bounce' if rsi < 30
                   else 'neutral zone')
        factors.append(('RSI (14) Context', 0, 0, f'RSI {rsi:.1f} — {rsi_ctx}', 'info'))

    macd_h = d.get('macd_hist')
    if macd_h is not None:
        factors.append(('MACD Signal', 0, 0,
                         f'Histogram {macd_h:+.4f} — {"bullish momentum" if macd_h > 0 else "bearish momentum"}',
                         'info'))

    return score, 10, factors


# ── THESIS + RESPONSE BUILDER ──────────────────────────────────────────────────

def _auto_thesis(d, ticker):
    name   = d['name']
    sector = d['sector']
    rg     = d['revenue_growth']
    gm     = d['gross_margin']
    eps    = d['eps']
    peg    = d['peg']
    fpe    = d['forward_pe']
    tpe    = d['trailing_pe']
    price  = d['price']
    ma200  = d['ma_200d']

    chunks = []

    if rg is not None:
        rp = rg * 100
        if rp >= 20:
            chunks.append(f'{name} is a high-growth {sector} company expanding revenue at +{rp:.0f}% per year.')
        elif rp >= 5:
            chunks.append(f'{name} is a steadily growing {sector} company with +{rp:.0f}% annual revenue growth.')
        elif rp >= 0:
            chunks.append(f'{name} is a mature {sector} company with flat revenue growth ({rp:.1f}%) — a stability, not growth, thesis.')
        else:
            chunks.append(f'{name} is a {sector} company with declining revenue ({rp:.1f}%) — the growth story is currently broken.')
    else:
        chunks.append(f'{name} operates in the {sector} sector.')

    if eps is not None and eps > 0:
        if gm is not None and gm >= 0.50:
            chunks.append(f'It is profitable (EPS ${eps:.2f}) with very high gross margins of {gm*100:.0f}%, suggesting a strong competitive moat.')
        elif gm is not None and gm >= 0.35:
            chunks.append(f'It is profitable (EPS ${eps:.2f}) with solid gross margins of {gm*100:.0f}%.')
        else:
            chunks.append(f'It is profitable (EPS ${eps:.2f}).')
    elif eps is not None:
        chunks.append(f'It is currently loss-making (EPS ${eps:.2f}), so the thesis depends on when — and whether — it reaches profitability.')

    if peg is not None:
        if peg < 1.0:
            chunks.append(f'At a PEG ratio of {peg:.2f}, the stock looks undervalued relative to its growth.')
        elif peg <= 2.0:
            chunks.append(f'At a PEG of {peg:.2f}, valuation is fair for the growth on offer.')
        else:
            chunks.append(f'At a PEG of {peg:.2f}, the stock is priced expensively — it needs strong growth just to justify the current price.')
    elif fpe and tpe:
        if fpe < tpe:
            chunks.append(f'Analysts project earnings improvement next year (Forward P/E {fpe:.1f}x vs Trailing {tpe:.1f}x).')
        else:
            chunks.append(f'Analysts project earnings to decline (Forward P/E {fpe:.1f}x > Trailing {tpe:.1f}x) — growth momentum may be slowing.')

    if ma200 and price:
        if price > ma200:
            chunks.append(f'The long-term trend supports this: price (${price:.2f}) is above the 200-day moving average (${ma200:.2f}).')
        else:
            chunks.append(f'One risk: the stock is below its 200-day moving average (${ma200:.2f}), meaning the long-term trend has not yet turned up.')

    return ' '.join(chunks) if chunks else f'Insufficient data to generate a thesis for {ticker.upper()}.'


def build_response(ticker, d, score, max_pts, factors, mode, duration):
    if score >= 8:
        decision, verdict = 'BUY',   'Strong entry — conditions are in your favour'
    elif score >= 5:
        decision, verdict = 'WATCH', 'Not yet — one or more key conditions are against you'
    else:
        decision, verdict = 'SKIP',  'Do not buy — too many conditions are unfavourable'

    price  = d['price']
    thesis = _auto_thesis(d, ticker) if mode == 'long' else None

    factor_list = [
        {'label': label, 'scored': s, 'max': m, 'note': note, 'status': status}
        for label, s, m, note, status in factors
    ]

    beta_str = f'{d["beta"]:.2f}' if d['beta'] else 'N/A'
    pg       = position_guide(d['beta'])

    if mode == 'long':
        factor_list.insert(6, {'label': 'Your Thesis',    'scored': 0, 'max': 0, 'note': thesis,                     'status': 'info'})
        factor_list.insert(7, {'label': 'Position Size',  'scored': 0, 'max': 0, 'note': f'Beta {beta_str} — {pg}.', 'status': 'info'})

    if mode == 'short':
        t1, t2, t3 = d['st_tier1'], d['st_tier2'], d['st_tier3']
        tiers = {
            'method':        'ATR-based (short-term)',
            'method_detail': f'14-day ATR = ${d["atr"]:.2f}  |  52-week high = ${d["wk52_high"]:.2f}',
            't1_range': f'${t2:.2f} to ${t1:.2f}', 't1_label': '~1 ATR below peak — first support',
            't2_range': f'${t3:.2f} to ${t2:.2f}', 't2_label': '~2.5 ATR below peak — moderate pullback',
            't3_range': f'below ${t3:.2f}',         't3_label': '~5 ATR below peak — deep pullback',
            'momentum':      f'{d["momentum_pct"]:+.1f}%',
            'vol_ratio':     f'{d["vol_ratio"]:.2f}x 20-day avg',
            'ma50':          f'${d["ma_50d"]:.2f}',
            'price_vs_ma50': 'ABOVE' if price > d['ma_50d'] else 'BELOW',
        }
    else:
        t1, t2, t3 = d['lt_tier1'], d['lt_tier2'], d['lt_tier3']
        pullback = round((d['wk52_high'] - price) / d['wk52_high'] * 100, 1)
        ma200    = d['ma_200d']
        tiers = {
            'method':        '% pullback from 52-week high (long-term)',
            'method_detail': f'52-week high = ${d["wk52_high"]:.2f}  |  Current pullback = {pullback}% below peak',
            't1_range': f'${t2:.2f} to ${t1:.2f}', 't1_label': '8-18% below peak — first opportunity',
            't2_range': f'${t3:.2f} to ${t2:.2f}', 't2_label': '18-28% below peak — good margin of safety',
            't3_range': f'below ${t3:.2f}',         't3_label': '>28% below peak — strong margin of safety',
            'trailing_pe':    f'{d["trailing_pe"]:.1f}x' if d['trailing_pe'] else 'N/A',
            'forward_pe':     f'{d["forward_pe"]:.1f}x'  if d['forward_pe']  else 'N/A',
            'peg':            f'{d["peg"]:.2f}'           if d['peg']         else 'N/A',
            'ma200':          f'${ma200:.2f}' if ma200 else None,
            'price_vs_ma200': ('ABOVE' if price > ma200 else 'BELOW') if ma200 else None,
        }

    action = []
    if mode == 'short':
        t1v, t2v, t3v = d['st_tier1'], d['st_tier2'], d['st_tier3']
        atr = d['atr']
        if price > t1v:
            how = f'Do not buy yet. Price (${price:.2f}) is still too close to its recent high. Set a price alert at ${t1v:.2f}.'
        elif price <= t3v:
            how = f'Price (${price:.2f}) has dropped significantly. You can buy your full planned amount now — deep pullback, risk/reward is in your favour.'
        elif price <= t2v:
            how = f'Price (${price:.2f}) is at a moderate pullback. Buy half your planned amount now. Add more if it drops to ${t3v:.2f}.'
        else:
            how = f'Price (${price:.2f}) is at a small pullback. Buy cautiously — only a quarter of your planned amount. Add at ${t2v:.2f} and ${t3v:.2f}.'
        sl  = round(price - 1.5 * atr, 2)
        tgt = round(price + 2.5 * atr, 2)
        action = [
            {'heading': 'HOW TO BUY',           'text': how,                                                                                                 'cls': ''},
            {'heading': 'HOW MUCH TO BUY',       'text': f'Limit this stock to {pg}. Example: if your portfolio is $10,000 — keep this position under that limit.', 'cls': 'size'},
            {'heading': 'STOP LOSS (mandatory)', 'text': f'If price falls to ${sl:.2f} — exit immediately. (1.5× ATR below entry — trade has gone wrong.)',          'cls': 'stop'},
            {'heading': 'PROFIT TARGET',          'text': f'Consider selling if price reaches ${tgt:.2f}. That is 2.5× ATR above your entry.',                        'cls': 'target'},
            {'heading': 'MAXIMUM HOLD TIME',      'text': f'Planned duration: {duration}. If the stock has not moved in your favour by then — exit regardless of price.', 'cls': ''},
        ]
    else:
        t1v, t2v, t3v = d['lt_tier1'], d['lt_tier2'], d['lt_tier3']
        peak     = d['wk52_high']
        pullback = round((peak - price) / peak * 100, 1)
        if price > t1v:
            how = f'Do not buy yet. Price (${price:.2f}) is only {pullback}% below its high — not enough discount. Set a price alert at ${t1v:.2f}.'
        elif price <= t3v:
            how = f'Price (${price:.2f}) is {pullback}% below its high — a deep discount. Buy your full planned amount now, split across 2-3 purchases.'
        elif price <= t2v:
            how = f'Price (${price:.2f}) is {pullback}% below its high — a solid entry. Buy 2/3 now. Keep 1/3 in reserve — add at ${t3v:.2f} if it drops further.'
        else:
            how = f'Price (${price:.2f}) is {pullback}% below its high — a reasonable but not ideal entry. Buy 1/3 now. Add at ${t2v:.2f} and ${t3v:.2f} if it keeps falling.'
        rg = d['revenue_growth']
        eps_v = d['eps']
        peg_v = d['peg']
        ma200_v = d['ma_200d']
        sell_pts = [
            f'Revenue growth drops below 0% (currently {rg*100:.1f}%)' if rg is not None else 'Revenue stops growing for two consecutive quarters',
            f'Company starts reporting a loss (EPS is currently ${eps_v:.2f})' if (eps_v is not None and eps_v > 0) else 'Company reports a loss in earnings',
            f'PEG ratio rises above 3.0 (currently {peg_v:.2f})' if peg_v else 'Valuation becomes extreme (check PEG)',
            f'Price {"does not recover above" if price < (ma200_v or price) else "falls and stays below"} ${ma200_v:.2f} (200-day average) for more than 6 months' if ma200_v else None,
            'Company changes its core business or faces a major legal/regulatory threat',
        ]
        sell_pts = [p for p in sell_pts if p]
        action = [
            {'heading': 'HOW TO BUY',       'text': how,       'cls': ''},
            {'heading': 'HOW MUCH TO BUY',  'text': f'Limit this stock to {pg}.', 'cls': 'size'},
            {'heading': 'WHEN TO SELL',     'points': sell_pts, 'cls': 'stop'},
            {'heading': 'WHEN TO CHECK AGAIN', 'text': f'Every 3 months — after each quarterly earnings announcement. Planned holding: {duration}.', 'cls': ''},
        ]

    def _factor_currently(label):
        if 'Revenue' in label:
            rg = d['revenue_growth']
            return f'{rg*100:.1f}%' if rg is not None else 'N/A'
        if 'EPS' in label or 'Profit' in label:
            eps = d['eps']
            return f'${eps:.2f}' if eps is not None else 'N/A'
        if 'Gross' in label or 'Margin' in label or 'Moat' in label:
            gm = d['gross_margin']
            return f'{gm*100:.0f}%' if gm is not None else 'N/A'
        if 'Earnings Growth' in label:
            eg = d['earnings_growth']
            return f'{eg*100:.1f}%' if eg is not None else 'N/A'
        if 'PEG' in label:
            peg = d['peg']
            return f'{peg:.2f}' if peg is not None else 'N/A'
        if 'Trajectory' in label or 'Direction' in label:
            fpe = d['forward_pe']; tpe = d['trailing_pe']
            return f'Fwd {fpe:.1f}x vs Trail {tpe:.1f}x' if fpe and tpe else 'N/A'
        if 'Volume' in label:
            return f'{d["vol_ratio"]:.2f}x avg'
        if 'Price Zone' in label or 'Entry Zone' in label:
            pb = round((d['wk52_high'] - price) / d['wk52_high'] * 100, 1)
            return f'{pb}% below 52wk high'
        if '200' in label or 'MA Trend' in label:
            ma200 = d['ma_200d']
            return f'${price:.2f} vs MA ${ma200:.2f}' if ma200 else 'N/A'
        return 'N/A'

    def _factor_needs(label):
        if 'Revenue' in label:           return 'above +5% to pass'
        if 'EPS' in label or 'Profit' in label: return 'EPS above $0 to pass'
        if 'Gross' in label or 'Margin' in label or 'Moat' in label: return 'above 40% to pass'
        if 'Earnings Growth' in label:   return 'above 0% to pass'
        if 'PEG' in label:               return 'below 2.0 for 1pt, below 1.0 for 2pts'
        if 'Trajectory' in label or 'Direction' in label: return 'Forward P/E must be lower than Trailing P/E'
        if 'Volume' in label:            return 'above 1.10x (buying activity picking up)'
        if 'Price Zone' in label or 'Entry Zone' in label:
            ref = d['lt_tier1'] if mode == 'long' else d['st_tier1']
            return f'price to drop to ${ref:.2f} to score any points'
        if '200' in label or 'MA Trend' in label:
            ma200 = d['ma_200d']
            return f'price to rise above ${ma200:.2f}' if ma200 else 'price to rise above 200-day MA'
        return ''

    if decision == 'BUY':
        closing = {
            'type': 'buy', 'title': 'ALL CONDITIONS MET — CHECKLIST BEFORE YOU BUY',
            'checklist': [
                'You have checked the date of the next earnings announcement',
                'You are not investing money you may need in the next 12 months',
                'You have set your position size limit (see HOW MUCH TO BUY above)',
                'You know your exit conditions (see WHEN TO SELL above)',
            ]
        }
    elif decision == 'WATCH':
        missed = [
            {'label': label, 'currently': _factor_currently(label), 'needs': _factor_needs(label)}
            for label, s, m, _, status in factors if s < m and status == '-'
        ]
        closing = {
            'type': 'watch', 'title': 'WHY IT IS NOT A BUY YET — WHAT NEEDS TO CHANGE',
            'items': missed, 'footer': 'Re-run this analysis in 3 months to check if conditions have improved.',
        }
    else:
        def _skip_reason(label):
            rg = d['revenue_growth']; eps_v = d['eps']; gm = d['gross_margin']
            peg_v = d['peg']; fpe = d['forward_pe']; tpe = d['trailing_pe']; ma200 = d['ma_200d']
            if 'Revenue' in label:
                cur = f'{rg*100:.1f}%' if rg is not None else 'N/A'
                return {'problem': f'Revenue is SHRINKING ({cur}).', 'threshold': 'Needs to be above +5% before this stock is worth considering.'}
            if 'EPS' in label or 'Profit' in label:
                cur = f'${eps_v:.2f}' if eps_v is not None else 'N/A'
                return {'problem': f'Company is making a LOSS (EPS {cur}).', 'threshold': 'EPS must turn positive before this becomes investable.'}
            if 'Gross' in label or 'Margin' in label or 'Moat' in label:
                cur = f'{gm*100:.0f}%' if gm is not None else 'N/A'
                return {'problem': f'Gross margin is only {cur}. After making its product, almost nothing is left.', 'threshold': 'Needs to be above 40%.'}
            if 'PEG' in label:
                cur = f'{peg_v:.2f}' if peg_v is not None else 'N/A'
                return {'problem': f'PEG ratio is {cur} — massively overpaying for the growth rate.', 'threshold': 'Fair price: PEG below 2.0. Undervalued: PEG below 1.0.'}
            if 'Trajectory' in label or 'Direction' in label:
                if fpe and tpe:
                    return {'problem': f'Earnings EXPECTED TO SHRINK (Fwd P/E {fpe:.1f}x > Trail {tpe:.1f}x).', 'threshold': 'Analysts expect the company to earn less next year.'}
            if '200' in label or 'MA Trend' in label:
                if ma200:
                    return {'problem': f'Price (${price:.2f}) is BELOW the 200-day average (${ma200:.2f}).', 'threshold': 'Long-term investors have been selling, not buying.'}
            return None

        reasons = [r for label, *_, status in factors if status == '-' for r in [_skip_reason(label)] if r]
        closing = {
            'type': 'skip', 'title': 'WHY THIS IS A SKIP — DO NOT BUY',
            'score_context': f'Scored {score}/10. Needs {8 - score} more points to reach BUY.',
            'reasons': reasons,
            'bottom_line': 'These are structural business problems, not temporary dips. A cheap price is not a reason to buy a broken business.',
        }

    if mode == 'long':
        scoring_guide = [
            {'section': 'STEP 1 — BUSINESS QUALITY', 'max': 4, 'items': [
                {'factor': 'Revenue Growth YoY', 'pts': '1pt', 'what': 'Is the company selling more each year?',              'pass': '>5% annual growth',       'fail': 'flat or declining'},
                {'factor': 'Profitability (EPS)', 'pts': '1pt', 'what': 'Is the company making money?',                       'pass': 'EPS > $0',                'fail': 'reporting a loss'},
                {'factor': 'Gross Margin',         'pts': '1pt', 'what': 'After making its product, how much profit remains?', 'pass': '>40% (competitive moat)', 'fail': 'low margin'},
                {'factor': 'Earnings Growth',      'pts': '1pt', 'what': 'Are profits growing year over year?',               'pass': 'positive growth',         'fail': 'profits shrinking'},
            ]},
            {'section': 'STEP 2 — VALUATION', 'max': 3, 'items': [
                {'factor': 'PEG Ratio', 'pts': '2pt', 'what': 'Are you paying fair price for growth? (P/E ÷ growth rate)', 'pass': '<1.0 undervalued (2pts), 1–2 fair (1pt)', 'fail': '>2.0 expensive'},
                {'factor': 'Earnings Trajectory', 'pts': '1pt', 'what': "Will earnings be higher next year?", 'pass': 'Forward P/E < Trailing P/E', 'fail': 'Forward P/E > Trailing P/E'},
            ]},
            {'section': 'STEP 5 — ENTRY ZONE', 'max': 2, 'items': [
                {'factor': 'Entry Zone', 'pts': '2pt', 'what': 'How far is price below its 52-week high?', 'pass': '>28% below peak = 2pts, 8–28% = 1pt', 'fail': '<8% below peak — no discount'},
            ]},
            {'section': 'TREND BONUS', 'max': 1, 'items': [
                {'factor': '200-day MA', 'pts': '1pt', 'what': 'Long-term uptrend or downtrend?', 'pass': 'Price above 200-day MA', 'fail': 'Price below 200-day MA (institutions selling)'},
            ]},
        ]
    else:
        scoring_guide = [
            {'section': 'BUSINESS QUALITY', 'max': 3, 'items': [
                {'factor': 'Revenue Growth', 'pts': '1pt', 'what': 'Growing revenue year over year?', 'pass': '>5% growth',   'fail': 'flat or declining'},
                {'factor': 'Profitability',  'pts': '1pt', 'what': 'Is the company profitable?',      'pass': 'EPS > $0',     'fail': 'loss-making'},
                {'factor': 'Gross Margin',   'pts': '1pt', 'what': 'Good profit per sale?',           'pass': '>40%',         'fail': 'low margin'},
            ]},
            {'section': 'VALUATION', 'max': 2, 'items': [
                {'factor': 'PEG Ratio',         'pts': '1pt', 'what': 'Priced reasonably vs growth?',       'pass': 'PEG ≤ 2.0',               'fail': '>2.0 overpriced'},
                {'factor': 'Earnings Direction', 'pts': '1pt', 'what': 'Future earnings expected higher?',   'pass': 'Forward P/E < Trailing P/E', 'fail': 'earnings shrinking'},
            ]},
            {'section': 'ENTRY TIMING', 'max': 4, 'items': [
                {'factor': 'Price Zone (ATR)', 'pts': '3pt', 'what': 'Stock pulled back enough? (14-day ATR)', 'pass': '>5 ATR below high (3pts), 2.5–5 ATR (2pts), 1–2.5 ATR (1pt)', 'fail': 'Above Tier 1'},
                {'factor': 'Volume Trend',     'pts': '1pt', 'what': 'More buyers than usual?',               'pass': '5-day avg > 110% of 20-day avg',                                 'fail': 'low or normal volume'},
            ]},
            {'section': 'TECHNICAL CONFIRMATION', 'max': 1, 'items': [
                {'factor': 'RSI Momentum (14)', 'pts': '1pt', 'what': 'Not overbought?', 'pass': 'RSI below 55', 'fail': 'RSI above 70 (overbought)'},
            ]},
        ]

    dy = d['dividend_yield']
    dy_str = f'{dy*100:.2f}%' if dy and dy < 0.5 else (f'{dy:.2f}%' if dy else 'None')

    return {
        'ticker':         ticker.upper(),
        'name':           d['name'],
        'sector':         d['sector'],
        'market_cap':     fmt_cap(d['market_cap']),
        'price':          d['price'],
        'wk52_low':       d['wk52_low'],
        'wk52_high':      d['wk52_high'],
        'wk52_position':  wk52_label(d['price'], d['wk52_low'], d['wk52_high']),
        'beta':           beta_str,
        'dividend_yield': dy_str,
        'holding_plan':   duration,
        'mode':           mode,
        'mode_label':     'SHORT-TERM TRADING' if mode == 'short' else 'LONG-TERM INVESTING',
        'score':          score,
        'max_pts':        max_pts,
        'decision':       decision,
        'verdict':        verdict,
        'factors':        factor_list,
        'tiers':          tiers,
        'action':         action,
        'closing':        closing,
        'scoring_guide':  scoring_guide,
        'rsi':            d.get('rsi'),
        'macd_hist':      d.get('macd_hist'),
        'macd_bullish':   d.get('macd_bullish'),
        'bb_upper':       d.get('bb_upper'),
        'bb_lower':       d.get('bb_lower'),
        'analyst_target': d.get('analyst_target'),
        'analyst_rec':    d.get('analyst_rec', 'N/A'),
        'short_ratio':    d.get('short_ratio'),
        'debt_to_equity': d.get('debt_to_equity'),
        'chart_dates':    d.get('chart_dates', []),
        'chart_close':    d.get('chart_close', []),
        'chart_ma50':     d.get('chart_ma50', []),
        'chart_ma200':    d.get('chart_ma200', []),
        'revenue_growth_pct': round(d['revenue_growth'] * 100, 1) if d.get('revenue_growth') is not None else None,
        'gross_margin_pct':   round(d['gross_margin'] * 100, 1)   if d.get('gross_margin')   is not None else None,
        'peg_val':            d.get('peg'),
        'ma50_val':           d.get('ma_50d'),
        'hist_rsi':           d.get('hist_rsi', []),
        'hist_macd':          d.get('hist_macd', []),
        'hist_vol_ratio':     d.get('hist_vol_ratio', []),
        'hist_price_vs_ma50': d.get('hist_price_vs_ma50', []),
    }
