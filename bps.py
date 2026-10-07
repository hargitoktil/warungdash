"""
bps.py - Mengambil data tabel dinamis dari WebAPI BPS (https://webapi.bps.go.id)
lalu mengubahnya menjadi tabel pandas.

Catatan format WebAPI BPS:
- Alamat data dinamis:
  /v1/api/list/model/data/lang/ind/domain/{domain}/var/{var}/key/{API_KEY}/
- Kunci di bagian "datacontent" adalah gabungan kode:
  vervar + var + turvar + tahun + turtahun
  (urutan yang sama dipakai paket Python resmi BPS, "stadata").
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

# --- Pengaturan tabel yang dipakai aplikasi ---------------------------------
# Tabel "Inflasi Bulanan (M-to-M) 38 Provinsi (2022=100)" di bps.go.id.
# var = 2262, tabel dinamis.
VAR_INFLASI = 2262
DOMAIN = "0000"  # 0000 = BPS pusat (nasional)

BASE_URL = "https://webapi.bps.go.id/v1/api"
PATH_ARSIP = Path(__file__).parent / "data" / "bps_inflasi.json"
USER_AGENT = "WarungDash/1.0 (aplikasi lomba; Streamlit)"

BULAN = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
}
NAMA_BULAN = {nomor: nama.capitalize() for nama, nomor in BULAN.items()}


class BPSError(Exception):
    """
    Kesalahan saat mengambil data BPS. Pesannya aman ditampilkan (tanpa API key).
    koneksi=True berarti server BPS tidak bisa dijangkau atau menolak akses
    (timeout, 403, bukan JSON); percobaan ulang dengan parameter lain percuma.
    """

    def __init__(self, pesan: str, koneksi: bool = False):
        super().__init__(pesan)
        self.koneksi = koneksi


def _minta(path: str, api_key: str, timeout: float = 15) -> dict:
    """Kirim satu permintaan GET ke WebAPI BPS dan kembalikan JSON-nya."""
    url = f"{BASE_URL}/{path.strip('/')}/key/{api_key}/"
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except requests.Timeout:
        raise BPSError("Server BPS tidak merespons (timeout).", koneksi=True) from None
    except requests.RequestException as exc:
        # Sengaja tidak menampilkan str(exc): pesan bawaan requests memuat URL
        # lengkap, termasuk API key.
        raise BPSError(f"Gagal terhubung ke server BPS ({type(exc).__name__}).", koneksi=True) from None

    if resp.status_code == 403:
        raise BPSError(
            "Akses ke WebAPI BPS ditolak (HTTP 403). Server cloud kemungkinan "
            "diblokir oleh proteksi Cloudflare BPS.",
            koneksi=True,
        )
    if resp.status_code != 200:
        raise BPSError(f"Server BPS membalas HTTP {resp.status_code}.", koneksi=True)
    try:
        isi = resp.json()
    except ValueError:
        raise BPSError(
            "Balasan server BPS bukan JSON (kemungkinan halaman verifikasi Cloudflare).",
            koneksi=True,
        ) from None
    if not isinstance(isi, dict) or isi.get("status") != "OK":
        pesan = str(isi.get("message", "")) if isinstance(isi, dict) else ""
        pesan = pesan.replace(api_key, "***").strip().rstrip(".")
        raise BPSError(f"WebAPI BPS menolak permintaan: {pesan or 'tanpa keterangan'}.")
    return isi


def ambil_tabel_dinamis(
    var_id: int,
    api_key: str,
    domain: str = DOMAIN,
    th: str | None = None,
    timeout: float = 15,
) -> dict:
    """Ambil satu tabel dinamis BPS (respons mentah)."""
    path = f"list/model/data/lang/ind/domain/{domain}/var/{var_id}"
    if th:
        path += f"/th/{th}"
    isi = _minta(path, api_key, timeout=timeout)
    if isi.get("data-availability") != "available" or not isi.get("datacontent"):
        raise BPSError(f"Tabel BPS var={var_id} (domain {domain}) tidak tersedia atau kosong.")
    return isi


def gabung_respons(utama: dict, tambahan: dict) -> dict:
    """Gabungkan dua respons tabel dinamis yang sama (misalnya beda tahun)."""
    hasil = dict(utama)
    for bagian in ("vervar", "turvar", "tahun", "turtahun"):
        gabungan = {x["val"]: x for x in utama.get(bagian) or []}
        for x in tambahan.get(bagian) or []:
            gabungan.setdefault(x["val"], x)
        hasil[bagian] = list(gabungan.values())
    hasil["tahun"] = sorted(hasil["tahun"], key=lambda t: t["val"])
    hasil["datacontent"] = {**(utama.get("datacontent") or {}), **(tambahan.get("datacontent") or {})}
    return hasil


def daftar_periode(var_id: int, api_key: str, domain: str = DOMAIN, timeout: float = 15) -> list[tuple[int, str]]:
    """Daftar periode (th_id, label) yang tersedia untuk satu tabel (model "th")."""
    hasil, halaman, total = [], 1, 1
    while halaman <= min(total, 10):
        isi = _minta(f"list/model/th/lang/ind/domain/{domain}/var/{var_id}/page/{halaman}", api_key, timeout=timeout)
        data = isi.get("data")
        if not isinstance(data, list) or len(data) < 2:
            break
        total = int((data[0] or {}).get("pages", 1) or 1)
        for item in data[1] or []:
            try:
                hasil.append((int(item["th_id"]), str(item["th"]).strip()))
            except (KeyError, TypeError, ValueError):
                continue
        halaman += 1
    return hasil


def kode_periode(
    var_id: int, api_key: str, domain: str, tahun_mulai: int, tahun_akhir: int, timeout: float = 15
) -> list[int]:
    """
    Kode periode (th) untuk rentang tahun. Diambil dari daftar periode resmi tabel;
    jika daftar itu tidak tersedia, dipakai aturan BPS: th = tahun - 1900
    (contoh di dokumentasi BPS: th_id 117 = 2017).
    """
    try:
        periode = daftar_periode(var_id, api_key, domain, timeout=timeout)
    except BPSError as exc:
        if exc.koneksi:
            raise
        periode = []
    kode = sorted(
        {th_id for th_id, label in periode if label.isdigit() and tahun_mulai <= int(label) <= tahun_akhir}
    )
    return kode or [tahun - 1900 for tahun in range(tahun_mulai, tahun_akhir + 1)]


def ambil_dengan_tahun_lengkap(
    var_id: int,
    api_key: str,
    domain: str = DOMAIN,
    tahun_mulai: int | None = None,
    timeout: float = 15,
) -> dict:
    """
    Ambil tabel dinamis untuk beberapa tahun sekaligus. WebAPI BPS mewajibkan
    parameter th; beberapa kode digabung dengan titik koma (contoh: 124;125;126).
    Jika permintaan gabungan ditolak, tiap tahun diambil satu per satu.
    """
    tahun_akhir = datetime.now().year
    if tahun_mulai is None:
        tahun_mulai = tahun_akhir - 2
    kode = kode_periode(var_id, api_key, domain, tahun_mulai, tahun_akhir, timeout=timeout)
    try:
        return ambil_tabel_dinamis(var_id, api_key, domain, th=";".join(map(str, kode)), timeout=timeout)
    except BPSError as galat:
        if galat.koneksi or len(kode) == 1:
            raise
        hasil = None
        for satu in kode:
            try:
                isi = ambil_tabel_dinamis(var_id, api_key, domain, th=str(satu), timeout=timeout)
            except BPSError as exc:
                if exc.koneksi:
                    raise
                continue  # tahun itu belum ada datanya
            hasil = isi if hasil is None else gabung_respons(hasil, isi)
        if hasil is None:
            raise galat
        return hasil


def ke_tabel(isi: dict) -> pd.DataFrame:
    """Ubah respons tabel dinamis menjadi tabel panjang: satu baris per angka."""
    daftar_var = isi.get("var") or []
    if not daftar_var:
        raise BPSError("Respons BPS tidak memuat informasi variabel.")
    kode_var = str(daftar_var[0]["val"])
    kosong = [{"val": 0, "label": "-"}]
    vervar = isi.get("vervar") or kosong
    turvar = isi.get("turvar") or kosong
    tahun = isi.get("tahun") or []
    turtahun = isi.get("turtahun") or kosong
    angka = isi.get("datacontent") or {}

    baris = []
    for vv in vervar:
        for tv in turvar:
            for th in tahun:
                for tt in turtahun:
                    kunci = f"{vv['val']}{kode_var}{tv['val']}{th['val']}{tt['val']}"
                    if kunci not in angka:
                        continue
                    baris.append(
                        {
                            "wilayah": str(vv["label"]).strip(),
                            "turvar": str(tv["label"]).strip(),
                            "tahun": str(th["label"]).strip(),
                            "turtahun": str(tt["label"]).strip(),
                            "nilai": angka[kunci],
                        }
                    )
    if not baris:
        raise BPSError("Tidak ada angka yang cocok dengan struktur tabel BPS.")

    df = pd.DataFrame(baris)
    df["nilai"] = pd.to_numeric(df["nilai"], errors="coerce")
    df["tahun"] = pd.to_numeric(df["tahun"], errors="coerce").astype("Int64")
    df["bulan"] = df["turtahun"].str.lower().map(BULAN).astype("Int64")
    ada_periode = df["tahun"].notna() & df["bulan"].notna()
    df["periode"] = pd.to_datetime(
        {
            "year": df["tahun"].fillna(1900).astype(int),
            "month": df["bulan"].fillna(1).astype(int),
            "day": 1,
        }
    ).where(ada_periode)
    return df


def info_tabel(isi: dict) -> dict:
    """Ambil keterangan tabel (judul, satuan, dsb.) dari respons BPS."""
    var = (isi.get("var") or [{}])[0]
    return {
        "judul": var.get("label", "-"),
        "satuan": var.get("unit", ""),
        "catatan": var.get("note", ""),
        "label_wilayah": isi.get("labelvervar", "Wilayah"),
        "diambil_pada": isi.get("_diambil_pada"),
    }


def simpan_arsip(isi: dict, path: Path = PATH_ARSIP) -> None:
    """Simpan respons BPS ke file JSON (dipakai saat koneksi langsung gagal)."""
    data = dict(isi)
    data["_diambil_pada"] = datetime.now().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def baca_arsip(path: Path = PATH_ARSIP) -> dict | None:
    """Baca arsip JSON. Kembalikan None jika file belum ada atau rusak."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cari_variabel(kata_kunci: str, api_key: str, domain: str = DOMAIN, maks_halaman: int = 30) -> pd.DataFrame:
    """Cari ID variabel (tabel dinamis) berdasarkan kata di judulnya."""
    hasil, halaman, total = [], 1, 1
    while halaman <= min(total, maks_halaman):
        isi = _minta(
            f"list/model/var/lang/ind/domain/{domain}/keyword/{quote(kata_kunci)}/page/{halaman}",
            api_key,
        )
        data = isi.get("data")
        if not isinstance(data, list) or len(data) < 2:
            break
        total = int((data[0] or {}).get("pages", 1) or 1)
        hasil.extend(data[1] or [])
        halaman += 1
    df = pd.DataFrame(hasil)
    if df.empty or "title" not in df.columns:
        return pd.DataFrame(columns=["var_id", "title"])
    kata = [k.lower() for k in kata_kunci.split()]
    cocok = df["title"].astype(str).str.lower().apply(lambda judul: all(k in judul for k in kata))
    kolom = [k for k in ("var_id", "title", "sub_name", "unit") if k in df.columns]
    return df.loc[cocok, kolom].reset_index(drop=True)
