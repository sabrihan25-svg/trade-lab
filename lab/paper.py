"""Sanal hesap. Gerçek emir YOK; yalnız JSON durumu üzerinde hesap yapar."""
import datetime as dt


def new_state(start_equity):
    return {
        "start_equity": start_equity,
        "realized": 0.0,
        "fees_paid": 0.0,
        "positions": [],
        "closed": [],
        "events": [],
        "day": None,
        "day_start_equity": start_equity,
        "day_trades": 0,
        "halted_day": None,
        "last_run": None,
    }


def utc_day(ts_ms):
    return dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def unrealized(state, prices):
    u = 0.0
    for p in state["positions"]:
        px = prices.get(p["symbol"])
        if px is not None:
            u += p["side"] * (px - p["entry"]) * p["qty"]
    return u


def equity(state, prices):
    return state["start_equity"] + state["realized"] + unrealized(state, prices)


def log(state, ts_ms, text):
    state["events"].append({"t": ts_ms, "text": text})
    del state["events"][:-30]


def roll_day(state, ts_ms, prices):
    d = utc_day(ts_ms)
    if state["day"] != d:
        state["day"] = d
        state["day_start_equity"] = equity(state, prices)
        state["day_trades"] = 0


def open_position(state, bot, symbol, side, price, atr_v, cfg, ts_ms, prices):
    """side: +1 long, -1 short. Komisyon ve kayma düşülür."""
    eq = equity(state, prices)
    used = sum(p["notional"] for p in state["positions"])
    notional = min(cfg["position_pct"] * eq * cfg.get("leverage", 1), eq * cfg.get("leverage", 1) - used)
    if notional <= 1:
        return None
    entry = price * (1 + side * cfg["slippage_rate"])
    fee = notional * cfg["fee_rate"]
    pos = {
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "qty": notional / entry,
        "notional": notional,
        "tp": entry + side * cfg["tp_atr"] * atr_v,
        "sl": entry - side * cfg["sl_atr"] * atr_v,
        "opened": ts_ms,
        "checked": ts_ms,
        "fee_in": fee,
    }
    state["realized"] -= fee
    state["fees_paid"] += fee
    state["positions"].append(pos)
    state["day_trades"] += 1
    log(state, ts_ms, f"{bot}: {symbol} {'LONG' if side > 0 else 'SHORT'} açıldı @ {entry:.2f}")
    return pos


def close_position(state, pos, raw_price, reason, cfg, ts_ms, gap=False):
    exit_px = raw_price * (1 - pos["side"] * cfg["slippage_rate"])
    fee = pos["qty"] * exit_px * cfg["fee_rate"]
    gross = pos["side"] * (exit_px - pos["entry"]) * pos["qty"]
    net = gross - fee - pos["fee_in"]
    state["realized"] += gross - fee
    state["fees_paid"] += fee
    state["positions"].remove(pos)
    state["closed"].append(
        {
            "bot": pos["bot"],
            "symbol": pos["symbol"],
            "side": pos["side"],
            "entry": round(pos["entry"], 4),
            "exit": round(exit_px, 4),
            "net": round(net, 4),
            "fees": round(fee + pos["fee_in"], 4),
            "reason": reason + (" (boşluk)" if gap else ""),
            "opened": pos["opened"],
            "closed": ts_ms,
        }
    )
    del state["closed"][:-200]
    log(state, ts_ms, f"{pos['bot']}: {pos['symbol']} kapandı ({reason}) net {net:+.2f}")


def manage_position(state, pos, candles, cfg, ts_ms):
    """Girişten beri her mumun high/low'unu gez. Aynı mumda hem stop hem hedef değerse
    muhafazakâr davran: stop önce. Açılışta stop/hedefi aşan boşlukta açılış fiyatından dolum."""
    last = candles[-1]["c"]
    # Girişten sonra başlayan mumlar + güncel fiyat (giriş mumunun giriş öncesi aşırı uçları sayılmaz).
    seq = [c for c in candles if c["t"] > pos["opened"]]
    seq.append({"t": ts_ms, "o": last, "h": last, "l": last, "c": last})
    for c in seq:
        s = pos["side"]
        sl_hit = c["l"] <= pos["sl"] if s > 0 else c["h"] >= pos["sl"]
        tp_hit = c["h"] >= pos["tp"] if s > 0 else c["l"] <= pos["tp"]
        if sl_hit:
            gap = (c["o"] < pos["sl"]) if s > 0 else (c["o"] > pos["sl"])
            close_position(state, pos, c["o"] if gap else pos["sl"], "stop", cfg, ts_ms, gap)
            return True
        if tp_hit:
            close_position(state, pos, pos["tp"], "hedef", cfg, ts_ms)
            return True
    if ts_ms - pos["opened"] > cfg["max_hold_minutes"] * 60_000:
        close_position(state, pos, candles[-1]["c"], "süre doldu", cfg, ts_ms)
        return True
    pos["checked"] = ts_ms
    return False
