import math
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lab import bots, paper, run  # noqa: E402
from lab.indicators import ema, rsi, atr  # noqa: E402

CFG = dict(fee_rate=0.0005, slippage_rate=0.0003, position_pct=0.33, max_open=3, rsi_low=35, rsi_high=65,
           tp_atr=4, sl_atr=2, max_hold_minutes=2880, max_trades_per_day=10, daily_loss_limit_pct=0.05,
           leverage=1, symbols=["BTCUSDT"])
H = 3_600_000
T0 = 1_700_000_000_000


def candle(i, o, h, l, c):
    return {"t": T0 + i * H, "o": o, "h": h, "l": l, "c": c}


def synth(seed, n=300, drift=0.0004):
    rnd = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p = p * (1 + drift + rnd.gauss(0, 0.006) + 0.004 * math.sin(i / 7))
        out.append(candle(i, o, max(o, p) * 1.002, min(o, p) * 0.998, p))
    return out


class Indicators(unittest.TestCase):
    def test_rsi_bounds_and_trend(self):
        up = [100 + i for i in range(60)]
        self.assertEqual(rsi(up)[-1], 100.0)
        down = [100 - i for i in range(60)]
        self.assertLess(rsi(down)[-1], 1)

    def test_atr_constant_range(self):
        c = [candle(i, 10, 11, 9, 10) for i in range(40)]
        self.assertAlmostEqual(atr(c)[-1], 2.0, places=6)

    def test_ema_constant(self):
        self.assertAlmostEqual(ema([5] * 100, 50)[-1], 5)


class Paper(unittest.TestCase):
    def setUp(self):
        self.s = paper.new_state(5000)
        self.prices = {"BTCUSDT": 100.0}

    def test_fee_slippage_long_target(self):
        pos = paper.open_position(self.s, "b", "BTCUSDT", 1, 100.0, 1.0, CFG, T0, self.prices)
        self.assertAlmostEqual(pos["entry"], 100.03, places=4)
        self.assertAlmostEqual(pos["notional"], 1650.0, places=4)
        self.assertAlmostEqual(pos["tp"], 104.03, places=4)
        # sonraki mum hedefi vurur
        done = paper.manage_position(self.s, pos, [candle(1, 100, 105, 99.5, 104)], CFG, T0 + 2 * H)
        self.assertTrue(done)
        c = self.s["closed"][0]
        self.assertEqual(c["reason"], "hedef")
        self.assertGreater(c["fees"], 0)
        self.assertAlmostEqual(self.s["realized"], c["net"], places=3)  # komisyon dahil tek kaynak
        self.assertAlmostEqual(self.s["fees_paid"], c["fees"], places=4)

    def test_stop_first_when_both_hit(self):
        pos = paper.open_position(self.s, "b", "BTCUSDT", 1, 100.0, 1.0, CFG, T0, self.prices)
        paper.manage_position(self.s, pos, [candle(1, 100, 110, 90, 100)], CFG, T0 + 2 * H)
        self.assertEqual(self.s["closed"][0]["reason"], "stop")

    def test_short_gap_fill_is_worse(self):
        pos = paper.open_position(self.s, "b", "BTCUSDT", -1, 100.0, 1.0, CFG, T0, self.prices)
        # stop ~102; mum 105'te açılıyor → boşluk, 105'ten dolum
        paper.manage_position(self.s, pos, [candle(1, 105, 106, 104, 105)], CFG, T0 + 2 * H)
        c = self.s["closed"][0]
        self.assertIn("boşluk", c["reason"])
        self.assertGreater(c["exit"], 104.9)
        self.assertLess(c["net"], 0)

    def test_no_check_on_entry_candle_extremes(self):
        pos = paper.open_position(self.s, "b", "BTCUSDT", 1, 100.0, 1.0, CFG, T0, self.prices)
        # giriş mumunun (t=T0) giriş öncesi dibi stop'u vursa da sayılmaz
        done = paper.manage_position(self.s, pos, [candle(0, 100, 100.5, 95, 100)], CFG, T0 + 1000)
        self.assertFalse(done)

    def test_max_hold(self):
        pos = paper.open_position(self.s, "b", "BTCUSDT", 1, 100.0, 1.0, CFG, T0, self.prices)
        paper.manage_position(self.s, pos, [candle(1, 100, 100.5, 99.5, 100)], CFG, T0 + 49 * H)
        self.assertEqual(self.s["closed"][0]["reason"], "süre doldu")

    def test_position_size_capped_by_equity(self):
        for _ in range(3):
            paper.open_position(self.s, "b", "BTCUSDT", 1, 100.0, 1.0, CFG, T0, self.prices)
        used = sum(p["notional"] for p in self.s["positions"])
        self.assertLessEqual(used, 5000 * 1.0 + 1e-6)


class EndToEnd(unittest.TestCase):
    def test_signal_open_close_and_readme(self):
        # Sinyal üreten bir tohum bul (sentetik trend + geri çekilme)
        found = None
        for seed in range(400):
            cs = synth(seed)
            if bots.crypto_signal(cs, CFG):
                found = cs
                break
        self.assertIsNotNone(found, "sentetik veride sinyal bulunamadı")
        s = paper.new_state(5000)
        now = found[-1]["t"] + 60_000
        bots.run_crypto("crypto_rules", CFG, s, lambda sym, iv, n: found, now)
        self.assertEqual(len(s["positions"]), 1)
        self.assertEqual(s["day_trades"], 1)
        # aynı sembolde ikinci pozisyon açılmaz
        bots.run_crypto("crypto_rules", CFG, s, lambda sym, iv, n: found, now + 1000)
        self.assertEqual(len(s["positions"]), 1)

    def test_daily_loss_limit_halts(self):
        s = paper.new_state(5000)
        cs = synth(1)
        now = cs[-1]["t"] + 60_000
        paper.roll_day(s, now, {"BTCUSDT": cs[-1]["c"]})
        s["realized"] = -400  # %8 zarar
        bots.run_crypto("crypto_rules", CFG, s, lambda sym, iv, n: cs, now)
        self.assertEqual(s["positions"], [])
        self.assertEqual(s["halted_day"], s["day"])

    def test_run_main_writes_state_and_readme(self):
        with tempfile.TemporaryDirectory() as d:
            run.STATE = os.path.join(d, "state", "state.json")
            run.README = os.path.join(d, "README.md")
            cs = synth(3)
            run.main(get_candles=lambda sym, iv, n: cs, now_ms=cs[-1]["t"] + 60_000)
            self.assertTrue(os.path.exists(run.STATE))
            txt = open(run.README, encoding="utf-8").read()
            self.assertIn("SANAL", txt)
            self.assertIn("Ödenen komisyon", txt)
            # ikinci koşu mevcut durumu devralır
            run.main(get_candles=lambda sym, iv, n: cs, now_ms=cs[-1]["t"] + 900_000)

    def test_data_failure_does_not_crash(self):
        s = paper.new_state(5000)

        def boom(sym, iv, n):
            raise RuntimeError("ağ yok")

        bots.run_crypto("crypto_rules", CFG, s, boom, T0)
        self.assertEqual(s["positions"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
