"""Herkese açık piyasa verisi. Anahtar gerekmez.
GitHub Actions ABD'de çalışır; api.binance.com ABD'den 451 verir. Bu yüzden sırayla:
1) data-api.binance.vision  2) Kraken  (ikisi de anahtarsız, herkese açık)."""
import requests

TIMEOUT = 15
KRAKEN_PAIR = {"BTCUSDT": "XBTUSDT", "ETHUSDT": "ETHUSDT", "SOLUSDT": "SOLUSDT"}


def _binance(symbol, interval, limit):
    r = requests.get(
        "https://data-api.binance.vision/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [
        {"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])}
        for k in r.json()
    ]


def _kraken(symbol, interval, limit):
    iv = {"1h": 60, "15m": 15, "5m": 5, "4h": 240}[interval]
    pair = KRAKEN_PAIR.get(symbol, symbol)
    r = requests.get(
        "https://api.kraken.com/0/public/OHLC", params={"pair": pair, "interval": iv}, timeout=TIMEOUT
    )
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(str(j["error"]))
    rows = next(v for k, v in j["result"].items() if k != "last")
    return [
        {"t": int(k[0]) * 1000, "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])}
        for k in rows[-limit:]
    ]


def get_candles(symbol, interval="1h", limit=300):
    """Mumlar eski→yeni. Son mum henüz kapanmamış olabilir."""
    last_err = None
    for fn in (_binance, _kraken):
        try:
            data = fn(symbol, interval, limit)
            if len(data) >= 50:
                return data
        except Exception as e:  # ücretsiz okuma isteği: sıradaki kaynağa geç
            last_err = e
    raise RuntimeError(f"{symbol}: veri alınamadı ({last_err})")
