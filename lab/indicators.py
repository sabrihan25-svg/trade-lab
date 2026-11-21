"""Saf Python göstergeler (ek paket yok)."""


def ema(values, period):
    k = 2 / (period + 1)
    out, prev = [], None
    for v in values:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(closes, period=14):
    """Wilder RSI. Dönen liste closes ile aynı uzunlukta; ilk `period` değer None."""
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(candles, period=14):
    """Wilder ATR. candles: [{'h','l','c'}...]"""
    out = [None] * len(candles)
    if len(candles) <= period:
        return out
    trs = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"])))
    a = sum(trs[:period]) / period
    out[period] = a
    for i in range(period + 1, len(candles)):
        a = (a * (period - 1) + trs[i - 1]) / period
        out[i] = a
    return out
