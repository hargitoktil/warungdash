"""
cek_bps.py - Diagnosa WebAPI BPS untuk WarungDash. Tidak perlu diunggah ke GitHub.

  python cek_bps.py          -> cek tabel var 2246, lalu cari tabel inflasi lain
  python cek_bps.py 1234     -> cek tabel var 1234

Hasilnya tidak memuat API key, jadi aman disalin untuk dibahas.
"""
from __future__ import annotations

import sys
from datetime import datetime

import bps
from ambil_data_bps import baca_api_key

KATA_RELEVAN = ("kab", "kota", "m-to-m", "bulan", "2022=100")


def ringkas(isi: dict) -> str:
    var = (isi.get("var") or [{}])[0]
    tahun = [t.get("label") for t in isi.get("tahun") or []]
    turtahun = [t.get("label") for t in isi.get("turtahun") or []]
    turvar = [t.get("label") for t in isi.get("turvar") or []]
    return (
        f"ketersediaan={isi.get('data-availability')} | judul={var.get('label', '-')!r} | "
        f"wilayah={len(isi.get('vervar') or [])} | tahun={tahun} | "
        f"turtahun={turtahun[:2]}..({len(turtahun)}) | turvar={turvar[:2]} | "
        f"angka={len(isi.get('datacontent') or {})} | kunci={sorted(isi.keys())}"
    )


def cari_inflasi(api_key: str) -> list[dict]:
    hasil, halaman, total = [], 1, 1
    while halaman <= min(total, 20):
        isi = bps._minta(
            f"list/model/var/lang/ind/domain/{bps.DOMAIN}/keyword/inflasi/perpage/1000/page/{halaman}", api_key
        )
        data = isi.get("data")
        if not isinstance(data, list) or len(data) < 2:
            break
        total = int((data[0] or {}).get("pages", 1) or 1)
        hasil.extend(data[1] or [])
        halaman += 1
    return hasil


def main() -> int:
    api_key = baca_api_key()
    if not api_key:
        print("API key tidak ditemukan di .streamlit/secrets.toml")
        return 1
    var = int(sys.argv[1]) if len(sys.argv) > 1 else bps.VAR_INFLASI
    tahun_ini = datetime.now().year

    print(f"1) Daftar periode var {var}")
    try:
        periode = bps.daftar_periode(var, api_key)
        print("   ", periode[:15] if periode else "(kosong)")
    except bps.BPSError as exc:
        print("    GAGAL:", exc)
        periode = []

    print(f"2) Data var {var} per tahun")
    kode = [k for k, label in periode if label.isdigit() and int(label) >= tahun_ini - 2]
    kode = kode or [t - 1900 for t in range(tahun_ini - 2, tahun_ini + 1)]
    for k in kode:
        try:
            isi = bps._minta(f"list/model/data/lang/ind/domain/{bps.DOMAIN}/var/{var}/th/{k}", api_key)
            print(f"    th={k}:", ringkas(isi))
        except bps.BPSError as exc:
            print(f"    th={k}: GAGAL:", exc)

    print("3) Tabel dinamis berjudul 'inflasi' di domain 0000")
    try:
        daftar = cari_inflasi(api_key)
    except bps.BPSError as exc:
        print("    GAGAL:", exc)
        return 0
    inflasi = [d for d in daftar if "inflasi" in str(d.get("title", "")).lower()]
    print(f"    ditemukan {len(inflasi)} tabel; yang relevan:")
    relevan = [d for d in inflasi if any(k in str(d.get("title", "")).lower() for k in KATA_RELEVAN)]
    for d in sorted(relevan, key=lambda d: int(d.get("var_id") or 0), reverse=True)[:40]:
        print(f"    var {d.get('var_id'):>6} | {d.get('title')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
