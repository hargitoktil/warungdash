"""
WarungDash: catatan penjualan warung yang langsung jadi dashboard,
plus patokan harga jual dari data inflasi BPS.

"""
from __future__ import annotations

import io
import urllib.parse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bps

WIB = ZoneInfo("Asia/Jakarta")
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_PENDEK = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
KOLOM_PRODUK = ["Produk", "Modal", "Harga jual", "Margin minimal", "Stok", "Stok minimum", "Terakhir naik harga"]
KOLOM_WAJIB = ["Produk", "Modal", "Harga jual", "Stok"]  # kolom lain diisi otomatis bila tidak ada
MARGIN_BAWAAN = 10  # persen
KOLOM_TRANSAKSI = ["Waktu", "Produk", "Jumlah", "Harga jual", "Modal", "Omzet", "Laba"]
WARNA_TINTA = "#00E5FF"       # cyan futuristik
WARNA_TINTA_MUDA = "#7C3AED"  # ungu elegan

# Data contoh (fiktif):
# (nama, modal, harga jual, margin minimal %, stok, stok minimum, terakhir naik harga [bulan lalu], bobot laku)
PRODUK_CONTOH = [
    ("Beras 1 kg", 13_500, 15_000, 8, 40, 10, 14, 3),
    ("Minyak goreng 1 liter", 17_000, 19_000, 8, 24, 6, 9, 2),
    ("Gula pasir 1 kg", 16_500, 18_000, 7, 5, 5, 6, 2),
    ("Telur ayam 1 kg", 28_500, 30_000, 8, 15, 5, 3, 2),
    ("Mi instan goreng", 3_000, 3_500, 12, 120, 30, 20, 6),
    ("Kopi sachet", 1_300, 2_000, 30, 80, 20, 12, 5),
    ("Air mineral 600 ml", 2_500, 3_500, 25, 48, 12, 8, 4),
    ("Sabun mandi batang", 3_200, 4_000, 20, 2, 4, 10, 1),
]

st.set_page_config(page_title="WarungDash", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    /* Styling Elegan Futuristik */
    h1 {
        background: -webkit-linear-gradient(45deg, #00E5FF, #7C3AED);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        letter-spacing: -1px;
    }
    [data-testid="stMetricValue"] {
        color: #00E5FF !important;
        text-shadow: 0 0 15px rgba(0, 229, 255, 0.3);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #7C3AED, #4F46E5) !important;
        color: #ffffff !important;
        border: none !important;
        transition: all 0.3s ease;
        font-weight: 600;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 0 15px rgba(0, 229, 255, 0.5);
        transform: translateY(-2px);
    }
    .stButton > button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid #7C3AED !important;
        color: #E2E8F0 !important;
        transition: all 0.3s ease;
    }
    .stButton > button[kind="secondary"]:hover {
        border-color: #00E5FF !important;
        color: #00E5FF !important;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.2);
    }
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- utilitas
def sekarang() -> datetime:
    """Waktu sekarang di WIB, tanpa info zona (lebih mudah untuk pandas dan Excel)."""
    return datetime.now(WIB).replace(tzinfo=None)


def hari_ini() -> date:
    return sekarang().date()


def rupiah(nilai) -> str:
    try:
        angka = round(float(nilai))
    except (TypeError, ValueError):
        return "-"
    teks = f"{abs(angka):,}".replace(",", ".")
    return f"-Rp{teks}" if angka < 0 else f"Rp{teks}"


def persen(nilai, desimal: int = 2) -> str:
    if nilai is None or pd.isna(nilai):
        return "-"
    return f"{nilai:.{desimal}f}%".replace(".", ",")


def tanggal_panjang(d: date) -> str:
    return f"{HARI[d.weekday()]}, {d.day} {bps.NAMA_BULAN[d.month]} {d.year}"


def bulan_tahun(ts) -> str:
    return f"{bps.NAMA_BULAN[ts.month]} {ts.year}"


def selisih_rupiah(nilai: float) -> str | None:
    if round(nilai) == 0:
        return None
    return ("+" if nilai > 0 else "") + rupiah(nilai)


def akumulasi(seri: pd.Series) -> float:
    """Gabungkan inflasi bulanan (%) menjadi inflasi kumulatif (%)."""
    if len(seri) == 0:
        return 0.0
    return float(((1 + seri / 100).prod() - 1) * 100)


def bulat_atas(nilai: float, kelipatan: int) -> int:
    return int(np.ceil(nilai / kelipatan) * kelipatan)


def bulat_terdekat(nilai: float, kelipatan: int) -> int:
    return int(np.floor(nilai / kelipatan + 0.5) * kelipatan)


def rahasia(nama: str, bawaan=None):
    """Baca st.secrets tanpa error kalau file secrets belum ada."""
    try:
        return st.secrets.get(nama, bawaan)
    except Exception:
        return bawaan


# ---------------------------------------------------------------- data & state
def rapikan_produk(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=KOLOM_PRODUK).copy()
    df["Produk"] = df["Produk"].fillna("").astype(str).str.strip()
    df = df[df["Produk"] != ""].copy()
    for kolom in ["Modal", "Harga jual", "Stok", "Stok minimum"]:
        df[kolom] = pd.to_numeric(df[kolom], errors="coerce").fillna(0).clip(lower=0).round().astype("int64")
    margin = pd.to_numeric(df["Margin minimal"], errors="coerce").fillna(MARGIN_BAWAAN)
    df["Margin minimal"] = margin.clip(lower=0, upper=90).round().astype("int64")
    tanggal = pd.to_datetime(df["Terakhir naik harga"], errors="coerce").dt.normalize()
    df["Terakhir naik harga"] = tanggal.fillna(pd.Timestamp(hari_ini())).astype("datetime64[ns]")
    return df.reset_index(drop=True)


def rapikan_transaksi(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=KOLOM_TRANSAKSI).copy()
    df["Waktu"] = pd.to_datetime(df["Waktu"], errors="coerce").astype("datetime64[ns]")
    df["Produk"] = df["Produk"].fillna("").astype(str)
    for kolom in ["Jumlah", "Harga jual", "Modal", "Omzet", "Laba"]:
        df[kolom] = pd.to_numeric(df[kolom], errors="coerce").fillna(0).round().astype("int64")
    return df.dropna(subset=["Waktu"]).sort_values("Waktu").reset_index(drop=True)


def data_contoh() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Data contoh 7 hari agar juri bisa langsung mencoba semua fitur."""
    hari = hari_ini()
    awal_bulan = pd.Timestamp(hari).replace(day=1)
    produk = pd.DataFrame(
        [
            {
                "Produk": nama,
                "Modal": modal,
                "Harga jual": jual,
                "Margin minimal": margin,
                "Stok": stok,
                "Stok minimum": minimum,
                "Terakhir naik harga": awal_bulan - pd.DateOffset(months=bulan_lalu),
            }
            for nama, modal, jual, margin, stok, minimum, bulan_lalu, _ in PRODUK_CONTOH
        ]
    )
    rng = np.random.default_rng(2026)
    bobot = np.array([p[-1] for p in PRODUK_CONTOH], dtype=float)
    bobot /= bobot.sum()
    batas = sekarang()
    baris = []
    for mundur in range(6, -1, -1):
        tanggal = hari - timedelta(days=mundur)
        for _ in range(int(rng.integers(16, 28))):
            nama, modal, jual, *_ = PRODUK_CONTOH[int(rng.choice(len(PRODUK_CONTOH), p=bobot))]
            jumlah = int(rng.integers(1, 4))
            waktu = datetime.combine(tanggal, datetime.min.time()) + timedelta(
                minutes=int(rng.integers(6 * 60, 21 * 60))
            )
            if waktu > batas:
                continue
            baris.append(
                {
                    "Waktu": waktu, "Produk": nama, "Jumlah": jumlah, "Harga jual": jual,
                    "Modal": modal, "Omzet": jual * jumlah, "Laba": (jual - modal) * jumlah,
                }
            )
    return rapikan_produk(produk), rapikan_transaksi(pd.DataFrame(baris, columns=KOLOM_TRANSAKSI))


def mulai_sesi() -> None:
    if "produk" in st.session_state:
        return
    produk, transaksi = data_contoh()
    st.session_state.produk = produk
    st.session_state.transaksi = transaksi
    st.session_state.pakai_contoh = True
    st.session_state.versi_produk = 0


def simpan_produk(df: pd.DataFrame) -> None:
    """Ganti daftar produk dan segarkan tabel editor."""
    st.session_state.produk = rapikan_produk(df)
    st.session_state.versi_produk += 1


def kabar(pesan: str) -> None:
    """Pesan singkat yang muncul setelah halaman dimuat ulang."""
    st.session_state.kabar = pesan


def ke_excel(produk: pd.DataFrame, transaksi: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        produk.to_excel(writer, sheet_name="Produk", index=False)
        transaksi.to_excel(writer, sheet_name="Transaksi", index=False)
    return buffer.getvalue()


def baca_excel(berkas) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        lembar = pd.read_excel(berkas, sheet_name=None)
    except Exception:
        raise ValueError("File tidak bisa dibaca. Pastikan file .xlsx hasil unduhan WarungDash.") from None
    if "Produk" not in lembar:
        raise ValueError("Lembar 'Produk' tidak ditemukan di file.")
    kurang = [k for k in KOLOM_WAJIB if k not in lembar["Produk"].columns]
    if kurang:
        raise ValueError(f"Kolom berikut tidak ada di lembar Produk: {', '.join(kurang)}.")
    transaksi = lembar.get("Transaksi", pd.DataFrame(columns=KOLOM_TRANSAKSI))
    return rapikan_produk(lembar["Produk"]), rapikan_transaksi(transaksi)


@st.cache_data(ttl=3 * 60 * 60, show_spinner="Mengambil data inflasi BPS...")
def muat_data_bps(api_key: str | None, coba_langsung: bool) -> dict:
    """
    Coba ambil langsung dari WebAPI BPS. Kalau gagal (misalnya server cloud
    diblokir), pakai arsip data/bps_inflasi.json. Hasil gagal juga ikut
    di-cache supaya halaman tidak menunggu timeout di setiap klik.
    """
    catatan = ""
    if api_key and coba_langsung:
        try:
            isi = bps.ambil_dengan_tahun_lengkap(
                bps.VAR_INFLASI, api_key, bps.DOMAIN,
                tahun_mulai=datetime.now(WIB).year - 2, timeout=8,
            )
            return {"isi": isi, "sumber": "langsung", "catatan": ""}
        except bps.BPSError as exc:
            catatan = str(exc)
    arsip = bps.baca_arsip()
    if arsip:
        return {"isi": arsip, "sumber": "arsip", "catatan": catatan}
    return {"isi": None, "sumber": None, "catatan": catatan}


# ---------------------------------------------------------------- aksi
def catat_penjualan(nama: str, jumlah: int) -> None:
    produk = st.session_state.produk.copy()
    cocok = produk.index[produk["Produk"] == nama]
    if len(cocok) == 0:
        st.error("Produk tidak ditemukan. Muat ulang halaman lalu coba lagi.")
        return
    i = cocok[0]
    stok = int(produk.at[i, "Stok"])
    if jumlah > stok:
        st.error(f"Stok {nama} tinggal {stok}. Kurangi jumlahnya atau perbarui stok di tab Produk & data.")
        return
    harga, modal = int(produk.at[i, "Harga jual"]), int(produk.at[i, "Modal"])
    baris = pd.DataFrame(
        [{
            "Waktu": sekarang(), "Produk": nama, "Jumlah": jumlah, "Harga jual": harga,
            "Modal": modal, "Omzet": harga * jumlah, "Laba": (harga - modal) * jumlah,
        }]
    )
    lama = st.session_state.transaksi
    st.session_state.transaksi = rapikan_transaksi(baris if lama.empty else pd.concat([lama, baris], ignore_index=True))
    produk.at[i, "Stok"] = stok - jumlah
    simpan_produk(produk)
    st.toast(f"Penjualan tersimpan: {jumlah} × {nama}, {rupiah(harga * jumlah)}")
    if stok - jumlah <= int(produk.at[i, "Stok minimum"]):
        st.warning(f"Stok {nama} tinggal {stok - jumlah}. Saatnya belanja lagi.")


def batalkan_terakhir() -> None:
    trx = st.session_state.transaksi
    if trx.empty:
        return
    terakhir = trx.iloc[-1]
    st.session_state.transaksi = trx.iloc[:-1].reset_index(drop=True)
    produk = st.session_state.produk.copy()
    produk.loc[produk["Produk"] == terakhir["Produk"], "Stok"] += int(terakhir["Jumlah"])
    simpan_produk(produk)
    kabar(f"Penjualan dibatalkan: {terakhir['Jumlah']} × {terakhir['Produk']}")


def hitung_saran(produk: pd.DataFrame, seri: pd.Series, kelipatan: int) -> pd.DataFrame:
    """
    Bandingkan harga jual tiap produk dengan inflasi kota dan margin minimalnya.
    - Patokan inflasi: harga x (1 + inflasi sejak bulan terakhir naik harga),
      dibulatkan ke kelipatan terdekat (kenaikan yang terlalu kecil diabaikan).
    - Patokan margin: modal / (1 - margin minimal), dibulatkan ke atas.
    Harga saran = yang tertinggi di antara harga sekarang dan kedua patokan.
    """
    terbaru, terlama = seri.index.max(), seri.index.min()
    hasil = []
    for _, p in produk.iterrows():
        harga, modal = float(p["Harga jual"]), float(p["Modal"])
        acuan = pd.Timestamp(p["Terakhir naik harga"]).to_period("M").to_timestamp()
        bulan_sesudah = seri[(seri.index > acuan) & (seri.index <= terbaru)]
        inflasi = akumulasi(bulan_sesudah)

        catatan = ""
        if acuan >= terbaru:
            catatan = f"Data BPS baru sampai {bulan_tahun(terbaru)}"
        elif acuan < terlama - pd.DateOffset(months=1):
            catatan = f"Data BPS mulai {bulan_tahun(terlama)}; inflasi sebelumnya belum dihitung"
        elif len(bulan_sesudah) < (terbaru.year - acuan.year) * 12 + terbaru.month - acuan.month:
            catatan = "Ada bulan yang kosong di data BPS"

        margin_min = int(p["Margin minimal"])
        margin_kini = (harga - modal) / harga * 100 if harga > 0 else float("nan")
        patokan_inflasi = bulat_terdekat(harga * (1 + inflasi / 100), kelipatan) if inflasi > 0 else harga
        kurang_margin = harga <= 0 or margin_kini < margin_min
        patokan_margin = bulat_atas(modal / (1 - margin_min / 100), kelipatan) if kurang_margin else harga
        saran = int(round(max(harga, patokan_inflasi, patokan_margin)))
        if saran > harga:
            alasan = "Mengejar inflasi" if patokan_inflasi >= patokan_margin else f"Menjaga margin {margin_min}%"
        else:
            alasan = "Sudah aman"
            if inflasi > 0 and not catatan:
                catatan = f"Kenaikan karena inflasi belum sampai {rupiah(kelipatan)}"

        hasil.append(
            {
                "Produk": p["Produk"],
                "Harga sekarang": int(round(harga)),
                "Terakhir naik": f"{BULAN_PENDEK[acuan.month - 1]} {acuan.year}",
                "Inflasi sejak itu": persen(inflasi),
                "Margin sekarang": persen(margin_kini, 0),
                "Margin minimal": f"{margin_min}%",
                "Harga saran": saran,
                "Kenaikan": saran - int(round(harga)),
                "Alasan": alasan,
                "Catatan": catatan,
            }
        )
    return pd.DataFrame(hasil)


def indeks_wilayah_bawaan(daftar: list[str]) -> int:
    for kata in ("INDONESIA", "NASIONAL", "JAKARTA"):
        for i, nama in enumerate(daftar):
            if kata in nama.upper():
                return i
    return 0


# ---------------------------------------------------------------- tampilan
def tata_grafik(fig: go.Figure, tinggi: int) -> go.Figure:
    fig.update_layout(
        height=tinggi,
        margin=dict(l=0, r=0, t=30, b=0),
        separators=",.",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        font=dict(family="Plus Jakarta Sans, sans-serif"),
    )
    return fig


def bagian_catat() -> None:
    produk = st.session_state.produk
    if produk.empty:
        st.info("Belum ada produk. Tambahkan produk dulu di tab Produk & data.")
        return

    info_produk = produk.set_index("Produk")
    with st.form("form_jual", clear_on_submit=True):
        nama = st.selectbox(
            "Produk",
            produk["Produk"].tolist(),
            format_func=lambda n: f"{n} ({rupiah(info_produk.at[n, 'Harga jual'])})",
            key="produk_jual",
        )
        jumlah = st.number_input("Jumlah", min_value=1, max_value=1000, value=1, step=1, key="jumlah_jual")
        disimpan = st.form_submit_button("Simpan penjualan", type="primary", width="stretch")
    if disimpan:
        catat_penjualan(nama, int(jumlah))

    trx = st.session_state.transaksi
    hari = trx[trx["Waktu"].dt.date == hari_ini()].sort_values("Waktu", ascending=False)
    st.subheader("Penjualan hari ini")
    if hari.empty:
        st.caption("Belum ada penjualan hari ini.")
    else:
        st.dataframe(
            hari.assign(Jam=hari["Waktu"].dt.strftime("%H:%M"))[["Jam", "Produk", "Jumlah", "Omzet", "Laba"]],
            hide_index=True,
            width="stretch",
            column_config={
                "Omzet": st.column_config.NumberColumn("Omzet (Rp)", format="localized"),
                "Laba": st.column_config.NumberColumn("Laba kotor (Rp)", format="localized"),
            },
        )
    if not trx.empty and st.button("Batalkan penjualan terakhir"):
        batalkan_terakhir()
        st.rerun()


def bagian_dashboard() -> None:
    trx, produk = st.session_state.transaksi, st.session_state.produk
    t0 = hari_ini()
    tujuh_hari = pd.date_range(t0 - timedelta(days=6), t0, freq="D")
    per_hari = (
        trx.assign(Tanggal=trx["Waktu"].dt.normalize())
        .groupby("Tanggal")[["Omzet", "Laba"]]
        .sum()
        .reindex(tujuh_hari, fill_value=0)
    )
    jumlah_trx = trx["Waktu"].dt.date.value_counts()
    trx_kini, trx_kemarin = int(jumlah_trx.get(t0, 0)), int(jumlah_trx.get(t0 - timedelta(days=1), 0))
    kini, kemarin = per_hari.iloc[-1], per_hari.iloc[-2]

    k1, k2, k3 = st.columns(3)
    k1.metric(
        "Omzet hari ini", rupiah(kini["Omzet"]), delta=selisih_rupiah(kini["Omzet"] - kemarin["Omzet"]),
        delta_description="dibanding kemarin", chart_data=per_hari["Omzet"].tolist(), chart_type="bar", border=True,
    )
    k2.metric(
        "Laba kotor hari ini", rupiah(kini["Laba"]), delta=selisih_rupiah(kini["Laba"] - kemarin["Laba"]),
        delta_description="dibanding kemarin", chart_data=per_hari["Laba"].tolist(), chart_type="bar", border=True,
    )
    k3.metric(
        "Transaksi hari ini", trx_kini, delta=(trx_kini - trx_kemarin) or None,
        delta_description="dibanding kemarin", border=True,
    )
    st.caption("Laba kotor = (harga jual - modal) × jumlah terjual, belum dikurangi biaya lain.")

    kiri, kanan = st.columns([3, 2])
    with kiri:
        st.subheader("Omzet 7 hari terakhir")
        label = [f"{HARI[d.weekday()][:3]} {d.day}" for d in tujuh_hari]
        fig = go.Figure()
        fig.add_bar(x=label, y=per_hari["Omzet"], name="Omzet", marker_color=WARNA_TINTA,
                    hovertemplate="%{x}: Rp%{y:,.0f}<extra>Omzet</extra>")
        fig.add_bar(x=label, y=per_hari["Laba"], name="Laba kotor", marker_color=WARNA_TINTA_MUDA,
                    hovertemplate="%{x}: Rp%{y:,.0f}<extra>Laba kotor</extra>")
        fig.update_layout(barmode="group", yaxis_tickprefix="Rp")
        st.plotly_chart(tata_grafik(fig, 300), config={"displayModeBar": False}, width="stretch")
    with kanan:
        st.subheader("Paling laku minggu ini")
        minggu = trx[trx["Waktu"] >= pd.Timestamp(t0 - timedelta(days=6))]
        if minggu.empty:
            st.caption("Belum ada penjualan dalam 7 hari terakhir.")
        else:
            top = (minggu.groupby("Produk", as_index=False)[["Jumlah", "Omzet"]].sum()
                   .nlargest(5, "Omzet").sort_values("Omzet"))
            fig2 = go.Figure(go.Bar(
                x=top["Omzet"], y=top["Produk"], orientation="h", marker_color=WARNA_TINTA,
                text=[f"{j} terjual" for j in top["Jumlah"]], textposition="auto",
                hovertemplate="%{y}: Rp%{x:,.0f}<extra></extra>",
            ))
            fig2.update_layout(xaxis_tickprefix="Rp")
            st.plotly_chart(tata_grafik(fig2, 300), config={"displayModeBar": False}, width="stretch")

    st.subheader("Stok menipis")
    menipis = produk[produk["Stok"] <= produk["Stok minimum"]]
    if menipis.empty:
        st.caption("Semua stok masih di atas batas minimum.")
    else:
        st.dataframe(menipis[["Produk", "Stok", "Stok minimum"]], hide_index=True, width="stretch")

    st.subheader("Kirim rekap")
    trx_hari = trx[trx["Waktu"].dt.date == t0]
    terlaris = trx_hari.groupby("Produk")["Jumlah"].sum().sort_values(ascending=False).head(3)
    baris = [
        f"Rekap WarungDash, {tanggal_panjang(t0)}",
        f"Omzet: {rupiah(kini['Omzet'])}",
        f"Laba kotor: {rupiah(kini['Laba'])}",
        f"Transaksi: {trx_kini}",
    ]
    if not terlaris.empty:
        baris.append("Terlaris: " + ", ".join(f"{n} ({j})" for n, j in terlaris.items()))
    if not menipis.empty:
        baris.append("Stok menipis: " + ", ".join(f"{r.Produk} ({r.Stok})" for r in menipis.itertuples()))
    teks = "\n".join(baris)
    st.link_button("Kirim rekap ke WhatsApp", "https://wa.me/?text=" + urllib.parse.quote(teks),
                   type="primary", width="stretch")
    with st.expander("Lihat isi rekap"):
        st.text(teks)


def bagian_harga() -> None:
    api_key = rahasia("BPS_API_KEY")
    coba_langsung = str(rahasia("BPS_LIVE", True)).strip().lower() not in {"false", "0", "tidak", "no"}
    hasil = muat_data_bps(api_key, coba_langsung)
    if hasil["isi"] is None:
        st.warning(
            "Data inflasi BPS belum tersedia. Jalankan `python ambil_data_bps.py` di komputer Anda, "
            "lalu unggah file `data/bps_inflasi.json` ke GitHub."
        )
        if hasil["catatan"]:
            st.caption(f"Status koneksi ke BPS: {hasil['catatan']}")
        return
    try:
        tabel = bps.ke_tabel(hasil["isi"])
    except bps.BPSError as exc:
        st.error(f"Data BPS tidak bisa dibaca: {exc}")
        return
    info = bps.info_tabel(hasil["isi"])
    bulanan = tabel.dropna(subset=["periode", "nilai"])
    if bulanan.empty:
        st.error("Tabel BPS yang dipakai tidak berisi data bulanan. Periksa VAR_INFLASI di bps.py.")
        return

    st.subheader("Inflasi di kota Anda")
    daftar_wilayah = sorted(bulanan["wilayah"].unique())
    kol1, kol2 = st.columns([2, 1])
    label_wilayah = str(info.get("label_wilayah") or "wilayah").lower()
    wilayah = kol1.selectbox(
        f"Pilih {label_wilayah} terdekat (ketik untuk mencari)",
        daftar_wilayah,
        index=indeks_wilayah_bawaan(daftar_wilayah),
        key="wilayah_bps",
    )
    daftar_turvar = list(dict.fromkeys(bulanan.loc[bulanan["wilayah"] == wilayah, "turvar"]))
    turvar = kol2.selectbox("Kelompok", daftar_turvar, key="turvar_bps") if len(daftar_turvar) > 1 else daftar_turvar[0]
    seri = (
        bulanan[(bulanan["wilayah"] == wilayah) & (bulanan["turvar"] == turvar)]
        .drop_duplicates("periode")
        .sort_values("periode")
        .set_index("periode")["nilai"]
    )
    terbaru = seri.index.max()
    dua_belas = seri[seri.index > terbaru - pd.DateOffset(months=12)]
    tahun_ini = seri[seri.index.year == terbaru.year]

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Inflasi {bulan_tahun(terbaru)}", persen(seri.loc[terbaru]), border=True,
              help="Perubahan harga dibanding bulan sebelumnya (month-to-month).")
    m2.metric("Akumulasi 12 bulan", persen(akumulasi(dua_belas)) if len(dua_belas) == 12 else "-", border=True,
              help="Gabungan inflasi bulanan 12 bulan terakhir.")
    m3.metric(f"Sejak Januari {terbaru.year}", persen(akumulasi(tahun_ini)), border=True)

    tampil = seri.tail(24)
    fig = go.Figure(go.Bar(
        x=[f"{BULAN_PENDEK[p.month - 1]} {str(p.year)[2:]}" for p in tampil.index],
        y=tampil.values,
        marker_color=[WARNA_TINTA if v >= 0 else WARNA_TINTA_MUDA for v in tampil.values],
        customdata=[bulan_tahun(p) for p in tampil.index],
        hovertemplate="%{customdata}: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(yaxis_ticksuffix="%", showlegend=False)
    st.plotly_chart(tata_grafik(fig, 260), config={"displayModeBar": False}, width="stretch")

    if hasil["sumber"] == "langsung":
        sumber = "diambil langsung dari WebAPI BPS"
    else:
        try:
            diambil = datetime.fromisoformat(str(info.get("diambil_pada")))
            sumber = f"arsip WebAPI BPS yang diambil {diambil.day} {bps.NAMA_BULAN[diambil.month]} {diambil.year}"
        except ValueError:
            sumber = "arsip WebAPI BPS"
    st.caption(
        f"Sumber: Badan Pusat Statistik, {info['judul']} ({sumber}). "
        "Akumulasi dihitung dari angka bulanan, jadi bisa berbeda sedikit dari angka resmi BPS karena pembulatan."
    )
    if hasil["catatan"]:
        with st.expander("Status koneksi ke BPS"):
            st.write(f"Koneksi langsung tidak tersedia, aplikasi memakai arsip. Keterangan: {hasil['catatan']}")

    st.subheader("Cek harga jual produk Anda")
    st.caption(
        "Patokan inflasi = harga jual sekarang ditambah inflasi kota pilihan sejak bulan terakhir Anda menaikkan harga. "
        "Patokan margin = harga terendah agar margin minimal produk tetap terjaga. "
        "Tanggal terakhir naik harga dan margin minimal bisa diubah di tab Produk & data."
    )
    produk = st.session_state.produk
    if produk.empty:
        st.info("Belum ada produk. Tambahkan produk dulu di tab Produk & data.")
        return
    kelipatan = st.selectbox("Bulatkan harga saran ke kelipatan", [100, 500, 1000], format_func=rupiah,
                             key="kelipatan")
    saran = hitung_saran(produk, seri, kelipatan)
    st.dataframe(
        saran,
        hide_index=True,
        width="stretch",
        column_config={
            "Harga sekarang": st.column_config.NumberColumn("Harga sekarang (Rp)", format="localized"),
            "Harga saran": st.column_config.NumberColumn("Harga saran (Rp)", format="localized"),
            "Kenaikan": st.column_config.NumberColumn("Kenaikan (Rp)", format="localized"),
        },
    )

    perlu = saran[saran["Kenaikan"] > 0]
    if perlu.empty:
        st.success("Semua harga jual sudah mengikuti inflasi kota pilihan dan margin minimal masing-masing produk.")
        return
    daftar = perlu["Produk"].tolist()
    pilihan = st.multiselect(
        "Produk yang harganya mau diperbarui", daftar, default=daftar,
        key="terapkan_" + str(abs(hash((tuple(daftar), st.session_state.versi_produk)))),
    )
    if st.button("Terapkan harga saran", type="primary", disabled=not pilihan):
        baru = st.session_state.produk.copy()
        peta = dict(zip(perlu["Produk"], perlu["Harga saran"]))
        for nama in pilihan:
            baris = baru["Produk"] == nama
            baru.loc[baris, "Harga jual"] = peta[nama]
            baru.loc[baris, "Terakhir naik harga"] = pd.Timestamp(hari_ini())
        simpan_produk(baru)
        kabar(f"Harga {len(pilihan)} produk diperbarui")
        st.rerun()


def bagian_data() -> None:
    st.subheader("Daftar produk")
    st.caption(
        "Ubah langsung di tabel atau tambah baris di bagian bawah, lalu klik Simpan perubahan produk. "
        "Daftar produk juga bisa diimpor dari Excel lewat bagian Simpan dan pulihkan data."
    )
    diedit = st.data_editor(
        st.session_state.produk,
        key=f"editor_produk_{st.session_state.versi_produk}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Produk": st.column_config.TextColumn("Produk", required=True),
            "Modal": st.column_config.NumberColumn("Modal (Rp)", min_value=0, step=100, format="localized"),
            "Harga jual": st.column_config.NumberColumn("Harga jual (Rp)", min_value=0, step=100, format="localized"),
            "Margin minimal": st.column_config.NumberColumn(
                "Margin minimal (%)", min_value=0, max_value=90, step=1,
                help="Margin keuntungan terendah yang masih Anda terima untuk produk ini.",
            ),
            "Stok": st.column_config.NumberColumn("Stok", min_value=0, step=1),
            "Stok minimum": st.column_config.NumberColumn("Stok minimum", min_value=0, step=1),
            "Terakhir naik harga": st.column_config.DateColumn("Terakhir naik harga", format="DD/MM/YYYY"),
        },
    )
    if st.button("Simpan perubahan produk", type="primary"):
        baru = rapikan_produk(diedit)
        kembar = baru["Produk"].str.lower().duplicated()
        if kembar.any():
            st.error(f"Nama produk tidak boleh kembar: {', '.join(baru.loc[kembar, 'Produk'])}.")
        elif (baru["Harga jual"] <= 0).any():
            st.error("Harga jual setiap produk harus lebih dari 0.")
        else:
            simpan_produk(baru)
            kabar("Perubahan produk tersimpan")
            st.rerun()

    st.subheader("Simpan dan pulihkan data")
    st.caption(
        "Data di aplikasi ini hanya bertahan selama halaman terbuka. Unduh file Excel untuk menyimpannya, "
        "lalu unggah lagi saat membuka aplikasi."
    )
    st.download_button(
        "Unduh data (Excel)",
        data=ke_excel(st.session_state.produk, st.session_state.transaksi),
        file_name=f"warungdash_{hari_ini():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    berkas = st.file_uploader(
        "Pulihkan dari file Excel",
        type=["xlsx"],
        help="Pakai file hasil Unduh data, atau Excel sendiri dengan lembar 'Produk' berkolom Produk, Modal, Harga jual, Stok.",
    )
    if berkas is not None and st.button("Pulihkan data dari file"):
        try:
            produk, transaksi = baca_excel(berkas)
        except ValueError as exc:
            st.error(str(exc))
        else:
            simpan_produk(produk)
            st.session_state.transaksi = transaksi
            st.session_state.pakai_contoh = False
            kabar(f"Data dipulihkan: {len(produk)} produk, {len(transaksi)} transaksi")
            st.rerun()

    with st.expander("Mulai dari nol atau isi ulang data contoh"):
        b1, b2 = st.columns(2)
        if b1.button("Hapus semua data", width="stretch"):
            simpan_produk(pd.DataFrame(columns=KOLOM_PRODUK))
            st.session_state.transaksi = rapikan_transaksi(pd.DataFrame(columns=KOLOM_TRANSAKSI))
            st.session_state.pakai_contoh = False
            kabar("Semua data dihapus")
            st.rerun()
        if b2.button("Isi ulang data contoh", width="stretch"):
            produk, transaksi = data_contoh()
            simpan_produk(produk)
            st.session_state.transaksi = transaksi
            st.session_state.pakai_contoh = True
            kabar("Data contoh diisi ulang")
            st.rerun()


# ---------------------------------------------------------------- halaman
mulai_sesi()
if pesan := st.session_state.pop("kabar", None):
    st.toast(pesan)

st.title("WarungDash")
st.caption(
    "Catat penjualan, pantau stok, dan cek apakah harga jual sudah mengejar inflasi di kota Anda. "
    f"{tanggal_panjang(hari_ini())}."
)
if st.session_state.pakai_contoh:
    st.info(
        "Yang tampil sekarang data contoh, supaya semua fitur bisa langsung dicoba. "
        "Untuk mencatat warung sendiri, buka tab Produk & data lalu pilih Hapus semua data."
    )

tab_catat, tab_dashboard, tab_harga, tab_data = st.tabs(
    ["Catat penjualan", "Dashboard", "Harga vs inflasi BPS", "Produk & data"]
)
with tab_catat:
    bagian_catat()
with tab_dashboard:
    bagian_dashboard()
with tab_harga:
    bagian_harga()
with tab_data:
    bagian_data()

st.divider()
st.caption(
    "Data inflasi: Badan Pusat Statistik (BPS) melalui WebAPI BPS. WarungDash tidak berafiliasi dengan BPS. "
    "Harga saran hanya patokan; untuk barang yang punya harga eceran tertinggi (HET) dari pemerintah, "
    "seperti beras dan LPG 3 kg, ikuti HET yang berlaku."
)
