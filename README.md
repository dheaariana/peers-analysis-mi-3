# PEARL MI3 — Analisis Peer Model Bisnis

Versi ini fokus pada informasi kualitatif yang tidak diduplikasi oleh tools analisis laporan keuangan Bank Mandiri.

## Prinsip

- Tidak ada data asumsi.
- Setiap nilai memiliki judul sumber, URL, tanggal, status, dan catatan CRM.
- Hanya status `Sumber Resmi` dan `Terverifikasi CRM` yang dihitung.
- Hasil scraping baru selalu berstatus `Menunggu Verifikasi CRM`.
- Data yang tidak ditemukan dibiarkan kosong.
- Skor kemiripan bukan rating atau keputusan kredit.
- Satu kolom pencarian digunakan untuk seluruh perusahaan; pengguna tidak perlu memilih database atau web.
- PEARL otomatis mengecek database, lalu mencari publikasi web jika perusahaan belum tersedia.
- Pengguna tidak perlu memasukkan URL; pencarian halaman perusahaan dan berita dilakukan otomatis.
- URL hasil pencarian ditampilkan sebagai tautan yang dapat langsung diklik.
- Kolom awal dikosongkan; aplikasi tidak lagi otomatis memilih BUMA.
- Profil hasil ekstraksi web ditampilkan bersama sumber dan selalu diberi label sementara sampai diverifikasi CRM.

## Deploy Streamlit

Unggah lima file berikut langsung ke root repository GitHub:

- `app.py`
- `perusahaan.csv`
- `bukti_model_bisnis.csv`
- `requirements.txt`
- `README.md`

Branch: `main`  
Main file path: `app.py`

## Memperbarui database

Gunakan menu `Pembaruan Publik`, masukkan nama perusahaan, lalu pilih sumber dari hasil pencarian otomatis. Pilih parameter dan masukkan hanya nilai yang benar-benar didukung isi sumber. Setelah CRM memverifikasi bukti pada `Kelola Database`, unduh `bukti_model_bisnis.csv` dan ganti file yang sama di GitHub.

Jangan mengunggah data rahasia ke Streamlit publik.
