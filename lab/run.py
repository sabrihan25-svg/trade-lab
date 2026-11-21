"""Bir 'tik': botları çalıştır, durumu kaydet, README'yi yenile. SANAL — gerçek emir yok."""
import datetime as dt
import json
import os
import sys
import time

import yaml

from . import bots, market, paper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state", "state.json")
CONFIG = os.path.join(ROOT, "config.yaml")
README = os.path.join(ROOT, "README.md")


def load_state(start):
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return paper.new_state(start)


def fmt_t(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%d.%m %H:%M")


def write_readme(state, prices, cfg):
    eq = paper.equity(state, prices)
    total = eq - state["start_equity"]
    closed = state["closed"]
    wins = sum(1 for c in closed if c["net"] > 0)
    today = (eq - state["day_start_equity"])
    rate = f"%{100 * wins / len(closed):.0f}" if closed else "-"
    L = [
        "# trade-lab — SANAL (kâğıt üstünde) işlem laboratuvarı",
        "",
        "> Gerçek para yoktur, hiçbir borsaya emir gitmez. Yatırım tavsiyesi değildir.",
        "",
        f"Son güncelleme: {dt.datetime.now(dt.timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
        "",
        "| Gösterge | Değer |",
        "|---|---|",
        f"| Başlangıç | {state['start_equity']:.2f} $ |",
        f"| Güncel varlık | {eq:.2f} $ |",
        f"| Bugün | {today:+.2f} $ |",
        f"| Toplam | {total:+.2f} $ ({100 * total / state['start_equity']:+.2f}%) |",
        f"| Kapanan işlem | {len(closed)} |",
        f"| Kazanma oranı | {rate} |",
        f"| Ödenen komisyon | {state['fees_paid']:.2f} $ |",
        "",
        "## Açık pozisyonlar",
        "",
    ]
    if state["positions"]:
        L += ["| Bot | Sembol | Yön | Giriş | Hedef | Stop |", "|---|---|---|---|---|---|"]
        for p in state["positions"]:
            L.append(
                f"| {p['bot']} | {p['symbol']} | {'LONG' if p['side'] > 0 else 'SHORT'} | "
                f"{p['entry']:.2f} | {p['tp']:.2f} | {p['sl']:.2f} |"
            )
    else:
        L.append("Yok.")
    L += ["", "## Son işlemler", ""]
    if closed:
        L += ["| Kapanış | Bot | Sembol | Yön | Net | Neden |", "|---|---|---|---|---|---|"]
        for c in reversed(closed[-10:]):
            L.append(
                f"| {fmt_t(c['closed'])} | {c['bot']} | {c['symbol']} | {'LONG' if c['side'] > 0 else 'SHORT'} | "
                f"{c['net']:+.2f} $ | {c['reason']} |"
            )
    else:
        L.append("Henüz yok.")
    L += ["", "## Son olaylar", ""]
    L += [f"- {fmt_t(e['t'])} — {e['text']}" for e in reversed(state["events"][-8:])] or ["- Yok."]
    with open(README, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(get_candles=None, now_ms=None):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    state = load_state(cfg["start_equity_usd"])
    ts = now_ms or int(time.time() * 1000)
    get_candles = get_candles or market.get_candles
    prices = {}
    for name, b in cfg["bots"].items():
        if b.get("enabled") and b["type"] == "crypto_trend":
            prices.update(bots.run_crypto(name, b, state, get_candles, ts))
    state["last_run"] = ts
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    write_readme(state, prices, cfg)
    print("tik tamam; açık:", len(state["positions"]), "kapanan:", len(state["closed"]))


if __name__ == "__main__":
    sys.exit(main())
