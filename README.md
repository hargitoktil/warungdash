# WarungDash

Catatan penjualan warung yang langsung jadi dashboard, plus patokan harga jual
dari data inflasi Badan Pusat Statistik (BPS).

Aplikasi: [https://hargitoktil.streamlit.app](https://warungdash.streamlit.app/)

## Fitur

- **Catat penjualan**: pilih produk, isi jumlah, simpan. Stok berkurang otomatis.
- **Dashboard**: omzet dan laba kotor hari ini, tren 7 hari, produk terlaris,
  stok menipis, dan tombol kirim rekap ke WhatsApp.
- **Harga vs inflasi BPS**: inflasi bulanan (m-to-m) 150 kabupaten/kota dari
  WebAPI BPS dipakai untuk menghitung harga saran tiap produk, dengan
  memperhatikan margin minimal yang ditetapkan pemilik warung.
- **Produk & data**: ubah daftar produk, unduh/pulihkan data lewat Excel.

Data contoh tampil otomatis saat aplikasi dibuka, jadi semua fitur bisa
langsung dicoba tanpa login.

## Menjalankan di komputer

Butuh Python 3.11 atau lebih baru (sudah diuji di 3.12 dan 3.14).
Contoh di macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp secrets.contoh.toml .streamlit/secrets.toml   # lalu isi BPS_API_KEY
python ambil_data_bps.py      # ambil data BPS -> data/bps_inflasi.json
streamlit run app.py
```

## Cara kerja data BPS

1. Aplikasi mencoba mengambil data langsung dari WebAPI BPS (hasilnya
   disimpan sementara selama 3 jam).
2. Jika gagal, misalnya karena server cloud diblokir, aplikasi memakai arsip
   `data/bps_inflasi.json` yang dibuat dengan `ambil_data_bps.py` dari
   komputer lokal. Sumber yang dipakai selalu ditampilkan di aplikasi.

Tabel yang dipakai: tabel dinamis BPS var 2246, Inflasi Bulanan (M-to-M)
150 Kabupaten/Kota (2022=100), domain 0000. Untuk mencari tabel lain:
`python ambil_data_bps.py --cari kata kunci`.

## Struktur

```
app.py                 aplikasi Streamlit
bps.py                 pengambil & pengurai data WebAPI BPS
ambil_data_bps.py      skrip lokal pembuat arsip data BPS
data/bps_inflasi.json  arsip data BPS (dibuat oleh skrip)
.streamlit/config.toml tema tampilan
secrets.contoh.toml    contoh isi secrets (file asli tidak diunggah)
```

## Sumber data dan batasan

Sumber data inflasi: Badan Pusat Statistik (BPS) melalui WebAPI BPS.
Aplikasi ini tidak berafiliasi dengan BPS. Harga saran hanya patokan; untuk
barang yang memiliki harga eceran tertinggi (HET) dari pemerintah, ikuti HET.
Data penjualan hanya tersimpan selama sesi; gunakan fitur unduh Excel untuk
menyimpannya.
