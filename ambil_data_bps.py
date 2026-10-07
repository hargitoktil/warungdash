from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import bps


def baca_api_key() -> str | None:
    key = os.environ.get("BPS_API_KEY")
    if key:
        return key.strip()
    berkas = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if berkas.exists():
        teks = berkas.read_text(encoding="utf-8")
        cocok = re.search(r'^\s*BPS_API_KEY\s*=\s*["\']([^"\']+)["\']', teks, re.MULTILINE)
        if cocok:
            return cocok.group(1).strip()
        if any(kutip in teks for kutip in "\u201c\u201d\u2018\u2019"):
            print("Tanda kutip di .streamlit/secrets.toml berubah menjadi kutip miring.")
            print('Ganti dengan kutip lurus ("), lalu simpan ulang. Hindari TextEdit; pakai nano.')
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Ambil data BPS untuk WarungDash")
    parser.add_argument("--cari", nargs="+", help="kata kunci judul tabel BPS yang dicari")
    args = parser.parse_args()

    api_key = baca_api_key()
    if not api_key:
        print("API key BPS belum ditemukan.")
        print('Buat file .streamlit/secrets.toml berisi: BPS_API_KEY = "kunci-anda"')
        return 1

    try:
        if args.cari:
            kata = " ".join(args.cari)
            hasil = bps.cari_variabel(kata, api_key)
            if hasil.empty:
                print(f"Tidak ada tabel yang judulnya memuat: {kata}")
                return 0
            for _, baris in hasil.head(40).iterrows():
                print(f"var {baris['var_id']:>6} | {baris['title']}")
            return 0

        print(f"Mengambil tabel var={bps.VAR_INFLASI} (domain {bps.DOMAIN}) dari WebAPI BPS ...")
        isi = bps.ambil_dengan_tahun_lengkap(
            bps.VAR_INFLASI, api_key, bps.DOMAIN, tahun_mulai=datetime.now().year - 2
        )
        tabel = bps.ke_tabel(isi)
        info = bps.info_tabel(isi)
    except bps.BPSError as exc:
        print(f"Gagal: {exc}")
        return 1

    bulanan = tabel.dropna(subset=["periode", "nilai"])
    print(f"Judul tabel : {info['judul']}")
    print(f"Satuan      : {info['satuan']}")
    print(f"Jumlah baris: {len(tabel)} angka, {tabel['wilayah'].nunique()} wilayah")
    if bulanan.empty:
        print("PERINGATAN: tidak ada data bulanan. Periksa apakah ID tabel sudah benar.")
        return 1
    awal, akhir = bulanan["periode"].min(), bulanan["periode"].max()
    print(f"Periode     : {bps.NAMA_BULAN[awal.month]} {awal.year} s.d. {bps.NAMA_BULAN[akhir.month]} {akhir.year}")
    if "m-to-m" not in info["judul"].lower() and "bulan" not in info["judul"].lower():
        print("PERINGATAN: judul tabel tidak menyebut inflasi bulanan (m-to-m). Periksa VAR_INFLASI di bps.py.")

    bps.simpan_arsip(isi)
    print(f"Tersimpan   : {bps.PATH_ARSIP}")
    print("Langkah berikutnya: unggah file data/bps_inflasi.json ke repository GitHub Anda.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
