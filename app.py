import io
import html
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="PEARL MI3", page_icon="◈", layout="wide")
st.markdown("""
<style>
.stApp{background:#f3f6fb;color:#172033}.block-container{max-width:1380px;padding-top:1.1rem}
.hero{background:linear-gradient(120deg,#07366d,#0d5da5);color:white;padding:22px 28px;
border-radius:8px 22px 22px 8px;border-left:7px solid #f4b000}.hero h1{margin:.2rem 0;font-size:2rem}
.hero p{margin:0;color:#dcecff}.tag{display:inline-block;background:#eaf3ff;color:#07447f;
padding:4px 10px;border-radius:99px;font-size:.78rem;font-weight:700}
[data-testid="stMetric"]{background:white;border:1px solid #dfe7f1;padding:12px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

ROOT = Path(__file__).parent
COMPANY_PATH = ROOT / "perusahaan.csv"
EVIDENCE_PATH = ROOT / "bukti_model_bisnis.csv"

PARAMETERS = {
    "Subsektor": 10,
    "Peran usaha": 10,
    "Lingkup jasa": 25,
    "Komoditas": 10,
    "Cakupan rantai nilai": 15,
    "Profil kontrak": 12,
    "Pelanggan/proyek": 6,
    "Wilayah operasi/proyek": 5,
    "Model armada": 4,
    "Alokasi biaya BBM": 3,
}
ACCEPTED_STATUS = {"Sumber Resmi", "Terverifikasi CRM"}
EVIDENCE_COLUMNS = [
    "nama_perusahaan", "parameter", "nilai", "judul_sumber", "url_sumber",
    "tanggal_sumber", "tanggal_akses", "status", "catatan_crm",
]


class VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}: self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden: self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden and data.strip(): self.parts.append(data.strip())


def normalize_name(value):
    name = str(value).casefold()
    for token in ["pt.", "pt ", "tbk.", "tbk", ",", "."]: name = name.replace(token, " ")
    return " ".join(name.split())


def tokens(value):
    stop = {"", "belum tersedia", "tidak diketahui", "nan"}
    return {x.strip().casefold() for x in str(value).split(";") if x.strip().casefold() not in stop}


def similarity(left, right):
    a, b = tokens(left), tokens(right)
    if not a or not b: return None
    return 100 * len(a & b) / len(a | b)


def valid_profiles(evidence):
    valid = evidence[evidence["status"].isin(ACCEPTED_STATUS)].copy()
    if valid.empty: return pd.DataFrame(columns=["nama_perusahaan", *PARAMETERS])
    valid = valid[valid["parameter"].isin(PARAMETERS)]
    pivot = valid.pivot_table(
        index="nama_perusahaan", columns="parameter", values="nilai",
        aggfunc=lambda values: "; ".join(dict.fromkeys(str(v) for v in values if str(v).strip())),
    ).reset_index()
    for parameter in PARAMETERS:
        if parameter not in pivot: pivot[parameter] = ""
    return pivot[["nama_perusahaan", *PARAMETERS]]


def calculate_score(target, candidate):
    points = 0; used = 0; rows = []
    for parameter, weight in PARAMETERS.items():
        match = similarity(target.get(parameter, ""), candidate.get(parameter, ""))
        if match is None:
            rows.append({"Parameter": parameter, "Target": target.get(parameter, ""),
                         "Peer": candidate.get(parameter, ""), "Kecocokan": "Data belum cukup", "Bobot": weight})
            continue
        points += match * weight; used += weight
        rows.append({"Parameter": parameter, "Target": target.get(parameter, ""),
                     "Peer": candidate.get(parameter, ""), "Kecocokan": f"{match:.0f}%", "Bobot": weight})
    return (round(points / used, 1) if used else 0.0,
            round(used / sum(PARAMETERS.values()) * 100, 1), rows)


def rank_peers(profiles, target):
    rows = []
    for _, peer in profiles.iterrows():
        if normalize_name(peer["nama_perusahaan"]) == normalize_name(target["nama_perusahaan"]): continue
        # Eligibility is data-based: same sourced subsector and business role.
        if not (tokens(target.get("Subsektor", "")) & tokens(peer.get("Subsektor", ""))): continue
        if not (tokens(target.get("Peran usaha", "")) & tokens(peer.get("Peran usaha", ""))): continue
        score, coverage, _ = calculate_score(target, peer)
        rows.append({**peer.to_dict(), "Skor kemiripan": score, "Cakupan data": coverage})
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Skor kemiripan", "Cakupan data"], ascending=False)


def safe_public_url(url):
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "URL harus diawali http:// atau https://"
    if parsed.hostname.casefold() in {"localhost", "metadata.google.internal"}:
        return False, "Alamat lokal tidak diizinkan"
    try:
        for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
            address = ipaddress.ip_address(result[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return False, "Alamat jaringan privat tidak diizinkan"
    except (socket.gaierror, ValueError): return False, "Domain tidak dapat diverifikasi"
    return True, ""


@st.cache_data(ttl=3600, show_spinner=False)
def scrape_page(url):
    allowed, message = safe_public_url(url)
    if not allowed: raise ValueError(message)
    response = requests.get(url, timeout=12, allow_redirects=True, stream=True,
                            headers={"User-Agent": "Mozilla/5.0 PEARL-MI3/1.0"})
    response.raise_for_status()
    allowed, message = safe_public_url(response.url)
    if not allowed: raise ValueError(f"Redirect ditolak: {message}")
    if "html" not in response.headers.get("content-type", "").casefold():
        raise ValueError("Gunakan halaman HTML, bukan tautan langsung PDF.")
    body = response.raw.read(2_000_000, decode_content=True).decode(response.encoding or "utf-8", errors="ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else response.url
    parser = VisibleTextParser(); parser.feed(body)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return {"judul": title, "url": response.url, "teks": text[:8000]}


@st.cache_data(ttl=3600, show_spinner=False)
def discover_news(company):
    query = quote_plus(f'"{company}" kontrak OR proyek OR pertambangan')
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
    response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 PEARL-MI3/1.0"})
    response.raise_for_status(); root = ET.fromstring(response.content)
    rows = []
    for item in root.findall("./channel/item")[:10]:
        source = item.find("source")
        description = re.sub(r"<[^>]+>", " ", item.findtext("description", ""))
        rows.append({"Judul": item.findtext("title", ""), "Ringkasan": re.sub(r"\s+", " ", description).strip(),
                     "Tanggal": item.findtext("pubDate", ""),
                     "Sumber": source.text if source is not None else "",
                     "URL": item.findtext("link", ""), "Status": "Bahan pencarian—belum tervalidasi"})
    return rows


@st.cache_data(ttl=3600, show_spinner=False)
def discover_web_pages(company):
    """Find candidate public/company pages without requiring the user to paste a URL."""
    query = quote_plus(f'"{company}" profil perusahaan pertambangan kontraktor official')
    search_url = f"https://html.duckduckgo.com/html/?q={query}"
    response = requests.get(search_url, timeout=12,
                            headers={"User-Agent": "Mozilla/5.0 PEARL-MI3/1.0"})
    response.raise_for_status()
    matches = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         response.text, flags=re.I | re.S)
    rows = []
    for raw_url, raw_title in matches:
        link = html.unescape(raw_url)
        if link.startswith("//"): link = "https:" + link
        parsed = urlparse(link)
        if "duckduckgo.com" in (parsed.hostname or ""):
            redirected = parse_qs(parsed.query).get("uddg", [])
            if redirected: link = unquote(redirected[0])
        if urlparse(link).scheme not in {"http", "https"}: continue
        title = re.sub(r"<[^>]+>", " ", raw_title)
        rows.append({"Judul": html.unescape(re.sub(r"\s+", " ", title).strip()),
                     "Sumber": urlparse(link).hostname or "", "URL": link,
                     "Status": "Kandidat sumber—belum tervalidasi"})
        if len(rows) == 6: break
    return rows


def extract_business_profile(company, news_rows, official_page=None):
    """Create a provisional profile only from words found in retrieved public text."""
    text_parts = []
    sources = []
    for row in news_rows:
        text_parts.extend([row.get("Judul", ""), row.get("Ringkasan", "")])
        sources.append({"Judul": row.get("Judul", ""), "Sumber": row.get("Sumber", ""),
                        "Tanggal": row.get("Tanggal", ""), "URL": row.get("URL", "")})
    pages = official_page if isinstance(official_page, list) else ([official_page] if official_page else [])
    for page in pages:
        text_parts.extend([page.get("judul", ""), page.get("teks", "")])
        sources.insert(0, {"Judul": page.get("judul", ""), "Sumber": urlparse(page.get("url", "")).hostname or "Halaman publik",
                           "Tanggal": "", "URL": page.get("url", "")})
    text = " ".join(text_parts).casefold()
    profile = {"nama_perusahaan": company, **{parameter: "" for parameter in PARAMETERS}}

    commodities = []
    for words, label in [(["coal", "batubara"], "Batubara"), (["nickel", "nikel"], "Nikel"),
                         (["copper", "tembaga"], "Tembaga"), (["gold", "emas"], "Emas")]:
        if any(word in text for word in words): commodities.append(label)
    if commodities:
        profile["Komoditas"] = "; ".join(commodities)
        subsectors = []
        if "Batubara" in commodities: subsectors.append("Jasa pertambangan batubara")
        if any(x != "Batubara" for x in commodities): subsectors.append("Jasa pertambangan mineral")
        profile["Subsektor"] = "; ".join(subsectors)
    if (any(word in text for word in ["mining contractor", "kontraktor pertambangan", "mining services contractor"])
            or ("kontraktor" in text and "pertambangan" in text)):
        profile["Peran usaha"] = "Kontraktor pertambangan"

    service_map = [
        (["overburden", "lapisan tanah penutup"], "Pengupasan lapisan tanah penutup"),
        (["coal getting", "coal extraction", "ekstraksi batubara", "pengambilan batubara"], "Ekstraksi batubara"),
        (["coal hauling", "hauling", "pengangkutan batubara"], "Pengangkutan"),
        (["drilling", "pengeboran"], "Pengeboran"),
        (["blasting", "peledakan"], "Peledakan"),
        (["mine planning", "perencanaan tambang"], "Perencanaan tambang"),
        (["heavy equipment rental", "penyewaan alat berat"], "Penyewaan alat berat"),
        (["mine infrastructure", "mining infrastructure", "infrastruktur tambang"], "Infrastruktur tambang"),
        (["rehabilitation", "rehabilitasi", "reclamation", "reklamasi"], "Rehabilitasi/reklamasi"),
        (["port management", "operasi pelabuhan", "pengelolaan pelabuhan"], "Pengelolaan pelabuhan"),
    ]
    services = [label for words, label in service_map if any(word in text for word in words)]
    if services: profile["Lingkup jasa"] = "; ".join(services)

    # Contract and project facts are added only when an explicit duration/location is found.
    duration = re.search(r"(?:selama|jangka waktu|periode|for)\s+(\d{1,2})\s+(?:tahun|years?)", text)
    if duration: profile["Profil kontrak"] = f"Kontrak {duration.group(1)} tahun"
    locations = []
    for keyword, label in [("kalimantan", "Kalimantan"), ("sumatera", "Sumatera"),
                           ("sulawesi", "Sulawesi"), ("papua", "Papua")]:
        if keyword in text: locations.append(label)
    if locations: profile["Wilayah operasi/proyek"] = "; ".join(locations)
    return profile, pd.DataFrame(sources).drop_duplicates(subset=["URL"])


def rank_provisional(profiles, target):
    has_eligibility = bool(tokens(target.get("Subsektor", "")) and tokens(target.get("Peran usaha", "")))
    if has_eligibility:
        ranked = rank_peers(profiles, target)
        if not ranked.empty: return ranked, "Peer disaring berdasarkan subsektor dan peran usaha hasil ekstraksi."
    rows = []
    for _, peer in profiles.iterrows():
        score, coverage, _ = calculate_score(target, peer)
        rows.append({**peer.to_dict(), "Skor kemiripan": score, "Cakupan data": coverage})
    ranked = pd.DataFrame(rows).sort_values(["Skor kemiripan", "Cakupan data"], ascending=False)
    return ranked, "Data target belum cukup untuk eligibility; daftar ini adalah kandidat awal dari database pilot."


def excel_output(target, ranked, comparison, sources):
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="xlsxwriter") as writer:
        pd.DataFrame([target]).to_excel(writer, sheet_name="Target", index=False)
        ranked.to_excel(writer, sheet_name="Daftar Peer", index=False)
        comparison.to_excel(writer, sheet_name="Perbandingan", index=False)
        sources.to_excel(writer, sheet_name="Sumber Data", index=False)
    return stream.getvalue()


@st.cache_data(show_spinner=False)
def load_base():
    companies = pd.read_csv(COMPANY_PATH, dtype=str).fillna("")
    evidence = pd.read_csv(EVIDENCE_PATH, dtype=str).fillna("")
    return companies, evidence


st.markdown('<div class="hero"><span class="tag">COMMERCIAL RISK 3 · MI3 PILOT</span>'
            '<h1>PEARL · Analisis Peer Model Bisnis Kontraktor Tambang</h1>'
            '<p>Peer Analytics and Risk Lens — pembandingan berbasis bukti dan sumber</p></div>', unsafe_allow_html=True)

base_companies, base_evidence = load_base()
if "evidence_working" not in st.session_state: st.session_state.evidence_working = base_evidence.copy()
evidence = st.session_state.evidence_working
profiles = valid_profiles(evidence)

with st.sidebar:
    st.subheader("Prinsip penggunaan")
    st.success("Skor hanya memakai data bersumber resmi atau terverifikasi CRM.")
    st.warning("Jangan unggah data rahasia ke deployment publik.")
    st.metric("Perusahaan", profiles["nama_perusahaan"].nunique())
    st.metric("Bukti yang dapat dihitung", len(evidence[evidence["status"].isin(ACCEPTED_STATUS)]))

tabs = st.tabs(["Cari Peer", "Perbandingan", "Sumber Data", "Pembaruan Publik", "Kelola Database", "Metodologi"])

with tabs[0]:
    st.subheader("Cari perusahaan dengan model bisnis sepadan")
    if profiles.empty:
        st.error("Belum ada bukti tervalidasi yang dapat digunakan.")
    else:
        company_query = st.text_input(
            "Nama perusahaan/debitur", "",
            placeholder="Contoh: PT Antareja Mahada Makmur",
            help="Ketik nama perusahaan yang sudah ada maupun perusahaan baru.",
        )
        st.caption("PEARL otomatis mengecek database, mencari publikasi, dan mencari halaman publik perusahaan.")
        if st.button("Cari peers", type="primary", use_container_width=True):
            if not company_query.strip():
                st.error("Nama perusahaan/debitur wajib diisi.")
            else:
                matched = profiles[
                    profiles["nama_perusahaan"].map(normalize_name) == normalize_name(company_query)
                ]
                if not matched.empty:
                    target = matched.iloc[0].to_dict()
                    ranked = rank_peers(profiles, target)
                    canonical_name = target["nama_perusahaan"]
                    st.session_state.target = target; st.session_state.ranked = ranked
                    st.session_state.target_sources = evidence[evidence["nama_perusahaan"] == canonical_name]
                    st.session_state.provisional = False
                    st.session_state.search_note = "Perusahaan ditemukan dalam database. Peer dihitung dari data bersumber."
                else:
                    try:
                        with st.spinner("Perusahaan belum ada di database. Mencari dan membaca data publik..."):
                            news_rows = []
                            web_rows = []
                            scraped_pages = []
                            search_errors = []
                            try:
                                news_rows = discover_news(company_query.strip())
                            except Exception as news_error:
                                search_errors.append(f"Pencarian publikasi: {news_error}")
                            try:
                                web_rows = discover_web_pages(company_query.strip())
                            except Exception as web_error:
                                search_errors.append(f"Pencarian halaman web: {web_error}")
                            for page in web_rows[:3]:
                                try:
                                    scraped_pages.append(scrape_page(page["URL"]))
                                except Exception:
                                    continue
                            if not news_rows and not scraped_pages:
                                raise ValueError("Tidak ada sumber yang berhasil dibaca. " + "; ".join(search_errors))
                            target, source_rows = extract_business_profile(company_query.strip(), news_rows, scraped_pages)
                            ranked, note = rank_provisional(profiles, target)
                            if search_errors:
                                note += " Sebagian sumber gagal dibaca: " + "; ".join(search_errors)
                        st.session_state.target = target; st.session_state.ranked = ranked
                        st.session_state.target_sources = source_rows
                        st.session_state.provisional = True; st.session_state.search_note = note
                    except Exception as error:
                        st.error(f"Pencarian data publik gagal: {error}")
        target = st.session_state.get("target")
        ranked = st.session_state.get("ranked", pd.DataFrame())
        if target is None:
            st.info("Ketik nama perusahaan/debitur lalu tekan **Cari peers**.")
        elif ranked.empty:
            st.warning("Belum ada peer eligible dengan subsektor dan peran usaha yang sama berdasarkan bukti tersedia.")
        else:
            st.success(f"Hasil untuk {target['nama_perusahaan']}")
            if st.session_state.get("provisional", False):
                st.warning("Hasil sementara dari ekstraksi data publik. Periksa sumber dan verifikasi karakteristik target sebelum digunakan dalam NAK.")
                detected = pd.DataFrame([{"Parameter": p, "Nilai terdeteksi": target.get(p, "") or "Belum ditemukan"}
                                         for p in PARAMETERS])
                st.dataframe(detected, use_container_width=True, hide_index=True)
            st.info(st.session_state.get("search_note", ""))
            st.dataframe(ranked[["nama_perusahaan", "Lingkup jasa", "Komoditas", "Skor kemiripan", "Cakupan data"]],
                         use_container_width=True, hide_index=True,
                         column_config={"Skor kemiripan": st.column_config.ProgressColumn(min_value=0,max_value=100),
                                        "Cakupan data": st.column_config.ProgressColumn(min_value=0,max_value=100,format="%.1f%%")})
            st.caption("Skor menunjukkan kemiripan model bisnis berdasarkan bukti tersedia, bukan kualitas kredit.")
            target_sources = st.session_state.get("target_sources", pd.DataFrame())
            if isinstance(target_sources, pd.DataFrame) and not target_sources.empty:
                with st.expander("Lihat sumber data target"):
                    st.dataframe(target_sources, use_container_width=True, hide_index=True,
                                 column_config={"URL": st.column_config.LinkColumn("Buka sumber"),
                                                "url_sumber": st.column_config.LinkColumn("Buka sumber")})

with tabs[1]:
    target = st.session_state.get("target"); ranked = st.session_state.get("ranked", pd.DataFrame())
    if target is None or ranked.empty:
        st.info("Jalankan pencarian peer terlebih dahulu.")
    else:
        peer_name = st.selectbox("Peer pembanding", ranked["nama_perusahaan"].tolist())
        peer = ranked[ranked["nama_perusahaan"] == peer_name].iloc[0].to_dict()
        score, coverage, details = calculate_score(target, peer)
        comparison = pd.DataFrame(details)
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        st.markdown("#### Implikasi yang perlu diuji CRM")
        explanations = {
            "Lingkup jasa": "Perbedaan pekerjaan dapat mengubah kebutuhan alat, kompleksitas pelaksanaan, dan struktur biaya.",
            "Profil kontrak": "Perbedaan tenor, volume minimum, tarif, eskalasi, atau penalti dapat memengaruhi visibilitas pendapatan dan margin.",
            "Pelanggan/proyek": "Perbedaan pelanggan atau proyek dapat menciptakan karakter site dan posisi tawar yang berbeda.",
            "Model armada": "Perbedaan kepemilikan, sewa, atau subcontracting dapat mengubah biaya tetap dan kebutuhan capex.",
            "Alokasi biaya BBM": "Perbedaan pembebanan BBM dapat menghasilkan sensitivitas biaya yang berbeda.",
            "Wilayah operasi/proyek": "Perbedaan lokasi dapat memengaruhi cuaca, jarak angkut, mobilisasi, dan produktivitas.",
        }
        differences = comparison[~comparison["Kecocokan"].isin(["100%", "Data belum cukup"])]
        for parameter in differences["Parameter"]:
            if parameter in explanations: st.write(f"- **{parameter}:** {explanations[parameter]}")
        st.caption("Pernyataan di atas adalah pertanyaan analitis, bukan kesimpulan faktual. Kesimpulan harus didukung kontrak, laporan operasional, atau konfirmasi CRM.")
        source_names = {target["nama_perusahaan"], peer_name}
        source_rows = evidence[evidence["nama_perusahaan"].isin(source_names)]
        provisional_sources = st.session_state.get("target_sources", pd.DataFrame())
        if st.session_state.get("provisional", False) and isinstance(provisional_sources, pd.DataFrame):
            source_rows = pd.concat([source_rows, provisional_sources], ignore_index=True, sort=False)
        st.download_button("Unduh hasil dan sumber", excel_output(target, ranked, comparison, source_rows),
                           file_name="PEARL_analisis_peer.xlsx", use_container_width=True)

with tabs[2]:
    st.subheader("Jejak sumber setiap data")
    company_filter = st.selectbox("Perusahaan", ["Semua"] + sorted(evidence["nama_perusahaan"].unique()), key="source_filter")
    shown = evidence if company_filter == "Semua" else evidence[evidence["nama_perusahaan"] == company_filter]
    st.dataframe(shown, use_container_width=True, hide_index=True,
                 column_config={"url_sumber": st.column_config.LinkColumn("Buka sumber")})

with tabs[3]:
    st.subheader("Pembaruan sumber publik")
    company = st.text_input("Nama perusahaan", placeholder="Contoh: PT Antareja Mahada Makmur")
    if st.button("Cari sumber publik", use_container_width=True):
        if not company.strip():
            st.error("Nama perusahaan wajib diisi.")
        else:
            results = []
            errors = []
            try: results.extend(discover_web_pages(company.strip()))
            except Exception as error: errors.append(f"Pencarian halaman: {error}")
            try: results.extend(discover_news(company.strip()))
            except Exception as error: errors.append(f"Pencarian berita: {error}")
            st.session_state.public_results = results
            if errors: st.warning("; ".join(errors))
    public_results = st.session_state.get("public_results", [])
    if public_results:
        result_df = pd.DataFrame(public_results).drop_duplicates(subset="URL")
        st.dataframe(result_df, use_container_width=True, hide_index=True,
                     column_config={"URL": st.column_config.LinkColumn("Buka berita/sumber")})
        selected_title = st.selectbox("Sumber yang akan dibaca", result_df["Judul"].tolist())
        selected_url = result_df[result_df["Judul"] == selected_title].iloc[0]["URL"]
        if st.button("Baca sumber terpilih", use_container_width=True):
            try: st.session_state.scraped = scrape_page(selected_url)
            except Exception as error: st.error(f"Halaman tidak dapat dibaca: {error}")
    scraped = st.session_state.get("scraped")
    if scraped:
        st.markdown(f"**{scraped['judul']}**")
        st.text_area("Teks hasil scraping", scraped["teks"], height=220)
        st.info("Salin hanya fakta yang tertulis pada sumber. Sistem tidak menebak atau mengisi klasifikasi otomatis.")
        c1, c2 = st.columns(2)
        new_parameter = c1.selectbox("Parameter", list(PARAMETERS))
        new_value = c2.text_input("Nilai yang didukung sumber", placeholder="Pisahkan beberapa nilai dengan titik koma")
        source_date = c1.date_input("Tanggal sumber", value=None)
        note = c2.text_input("Catatan CRM/kalimat pendukung")
        if st.button("Masukkan sebagai Menunggu Verifikasi CRM", use_container_width=True):
            if not company.strip() or not new_value.strip(): st.error("Nama perusahaan dan nilai wajib diisi.")
            else:
                row = {"nama_perusahaan": company.strip(), "parameter": new_parameter, "nilai": new_value.strip(),
                       "judul_sumber": scraped["judul"], "url_sumber": scraped["url"],
                       "tanggal_sumber": source_date.isoformat() if source_date else "",
                       "tanggal_akses": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                       "status": "Menunggu Verifikasi CRM", "catatan_crm": note}
                st.session_state.evidence_working = pd.concat([evidence, pd.DataFrame([row])], ignore_index=True)
                st.success("Bukti ditambahkan. Ubah statusnya setelah diverifikasi pada Kelola Database.")

with tabs[4]:
    st.subheader("Kelola database bukti")
    st.write("CRM dapat memperbaiki nilai, menambah catatan, atau mengubah status menjadi **Terverifikasi CRM** setelah pengecekan.")
    edited = st.data_editor(evidence, use_container_width=True, hide_index=True, num_rows="dynamic", height=520,
                            column_config={"status": st.column_config.SelectboxColumn(options=["Menunggu Verifikasi CRM", "Sumber Resmi", "Terverifikasi CRM", "Ditolak"])})
    if st.button("Terapkan perubahan dalam sesi"):
        st.session_state.evidence_working = edited[EVIDENCE_COLUMNS].copy(); st.rerun()
    st.download_button("Unduh database bukti terbaru", edited.to_csv(index=False).encode("utf-8-sig"),
                       file_name="bukti_model_bisnis.csv", mime="text/csv", use_container_width=True)

with tabs[5]:
    st.subheader("Metodologi berbasis bukti")
    st.dataframe(pd.DataFrame([{"Parameter": p, "Bobot": f"{w}%"} for p,w in PARAMETERS.items()]),
                 use_container_width=True, hide_index=True)
    st.markdown("""
    1. **Eligibility:** subsektor dan peran usaha harus sama berdasarkan data bersumber.
    2. **Kemiripan:** hanya parameter yang tersedia untuk kedua perusahaan yang dihitung.
    3. **Cakupan data:** menunjukkan proporsi bobot yang didukung data, sehingga skor tinggi dengan data minim tidak disalahartikan.
    4. **Validasi:** data hasil scraping berstatus *Menunggu Verifikasi CRM* dan tidak masuk perhitungan.
    5. **Analisis keuangan:** laporan keuangan tetap dianalisis pada tools Bank Mandiri dan tidak diduplikasi di PEARL.
    """)
