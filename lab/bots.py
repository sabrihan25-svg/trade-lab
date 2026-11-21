"""Bot mantıkları. Şimdilik: kripto trend + geri çekilme (kural tabanlı, yapay zekâ gerekmez)."""
from . import paper
from .indicators import ema, rsi, atr


def crypto_signal(candles, cfg):
    """Yalnız KAPANMIŞ mumlarla karar verir. Dönüş: (side, atr_değeri) ya da None.
    Yükseliş trendi (EMA50>EMA200) + RSI düşük bölgeden yukarı dönüş → long.
    Düşüş trendi + RSI yüksek bölgeden aşağı dönüş → short."""
    closed = candles[:-1]
    if len(closed) < 210:
        return None
    closes = [c["c"] for c in closed]
    e50, e200 = ema(closes, 50)[-1], ema(closes, 200)[-1]
    r = rsi(closes, 14)
    a = atr(closed, 14)[-1]
    if a is None or r[-1] is None or r[-2] is None:
        return None
    lo, hi = cfg["rsi_low"], cfg["rsi_high"]
    recent_low = min(x for x in r[-4:-1] if x is not None)
    recent_high = max(x for x in r[-4:-1] if x is not None)
    if e50 > e200 and recent_low < lo and r[-1] > r[-2] and r[-1] >= lo:
        return (1, a)
    if e50 < e200 and recent_high > hi and r[-1] < r[-2] and r[-1] <= hi:
        return (-1, a)
    return None


def run_crypto(name, cfg, state, get_candles, ts_ms):
    data = {}
    for sym in cfg["symbols"]:
        try:
            data[sym] = get_candles(sym, "1h", 300)
        except Exception as e:
            paper.log(state, ts_ms, f"{name}: {sym} verisi yok ({e})")
    prices = {s: c[-1]["c"] for s, c in data.items()}
    paper.roll_day(state, ts_ms, prices)

    for pos in [p for p in state["positions"] if p["bot"] == name]:
        if pos["symbol"] in data:
            paper.manage_position(state, pos, data[pos["symbol"]], cfg, ts_ms)

    eq = paper.equity(state, prices)
    day_loss = (state["day_start_equity"] - eq) / max(state["day_start_equity"], 1)
    if day_loss >= cfg["daily_loss_limit_pct"]:
        if state["halted_day"] != state["day"]:
            paper.log(state, ts_ms, f"{name}: günlük zarar sınırı aşıldı, bugün durdu")
            state["halted_day"] = state["day"]
        return prices
    if state["halted_day"] == state["day"]:
        return prices

    mine = [p for p in state["positions"] if p["bot"] == name]
    for sym, candles in data.items():
        if len(mine) >= cfg["max_open"] or state["day_trades"] >= cfg["max_trades_per_day"]:
            break
        if any(p["symbol"] == sym for p in mine):
            continue
        sig = crypto_signal(candles, cfg)
        if sig:
            pos = paper.open_position(state, name, sym, sig[0], prices[sym], sig[1], cfg, ts_ms, prices)
            if pos:
                mine.append(pos)
    return prices
