#!/usr/bin/env python3
"""Depoda anahtar/kişisel veri benzeri içerik arar. Bulursa çıkış kodu 1.
Bir satırı bilerek geçmek için satır sonuna `# guvenlik:izin` yaz."""
import re
import subprocess
import sys

IZIN = "guvenlik:izin"

PATTERNS = {
    "anahtar (sk-/ghp_/AKIA/xox)": r"(sk-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,})",
    "özel anahtar bloğu": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "atanmış gizli değer": r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:\s?\d{4}){4,7}(?:\s?\d{1,4})?\b",
    "telefon (TR)": r"(?<!\d)(?:\+?90|0)?\s?5\d{2}\s?\d{3}\s?\d{2}\s?\d{2}(?!\d)",
}


def tc_gecerli(s: str) -> bool:
    if not re.fullmatch(r"[1-9]\d{10}", s):
        return False
    d = [int(c) for c in s]
    if ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def dosyalar():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and f != "scripts/guvenlik_tarama.py"]


def main() -> int:
    bulunan = []
    for f in dosyalar():
        try:
            with open(f, encoding="utf-8") as fh:
                satirlar = fh.read().splitlines()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for no, s in enumerate(satirlar, 1):
            if IZIN in s:
                continue
            for ad, rx in PATTERNS.items():
                if re.search(rx, s):
                    bulunan.append((f, no, ad))
            for m in re.finditer(r"(?<!\d)\d{11}(?!\d)", s):
                if tc_gecerli(m.group()):
                    bulunan.append((f, no, "kimlik numarası"))
    for f, no, ad in bulunan:
        # Değeri yazdırma: yalnız yer ve tür.
        print(f"::error file={f},line={no}::{ad} benzeri içerik")
    print(f"Tarama bitti: {len(bulunan)} bulgu")
    return 1 if bulunan else 0


if __name__ == "__main__":
    sys.exit(main())
