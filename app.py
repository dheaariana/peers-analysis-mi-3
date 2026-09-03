import io
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="PEARL MI3", page_icon="◈", layout="wide")

st.markdown(
    """
    <style>
    .stApp {background:#f3f6fb;color:#172033}
    .block-container {max-width:1380px;padding-top:1.1rem}
    .hero {background:linear-gradient(120deg,#07366d,#0d5da5);color:white;
           padding:22px 28px;border-radius:8px 22px 22px 8px;border-left:7px solid #f4b000}
    .hero h1 {margin:.2rem 0;font-size:2rem}.hero p {margin:0;color:#dcecff}
    .tag {display:inline-block;background:#eaf3ff;color:#07447f;padding:4px 10px;
          border-radius:99px;font-size:.78rem;font-weight:700}
    [data-testid="stMetric"] {background:white;border:1px solid #dfe7f1;padding:12px;border-radius:12px}
    </style>
    """,
    unsafe_allow_html=True,
)

ROOT = Path(__file__).parent
MASTER_PATH = ROOT / "peer_database.csv"

PORTFOLIO_COLUMNS = [
    "segment", "sector", "adjusted_sector", "cif", "company_name", "unit", "kol",
    "restructuring", "bade_rp_m", "limit_rp_m", "ckpn_pct", "coal_related",
    "mine_location", "coal_revenue_pct", "coal_role", "group_support",
]

PROFILE_COLUMNS = [
    "company_name", "sector", "subsector", "business_role", "service_scope",
    "primary_commodity", "contract_profile", "tariff_model", "customer_profile",
    "customer_concentration", "geography", "fleet_model", "fuel_cost_allocation",
    "growth_stage", "growth_pattern", "revenue_growth_band", "margin_driver",
    "key_risk", "source", "source_period", "last_updated", "verification_status",
]

# Higher weight is assigned to operating characteristics that directly shape mining-services economics.
SCORING_FIELDS = {
    "subsector": ("Subsector", 5),
    "business_role": ("Business role", 10),
    "service_scope": ("Service scope", 15),
    "primary_commodity": ("Commodity", 8),
    "contract_profile": ("Contract profile", 10),
    "tariff_model": ("Tariff / revenue model", 10),
    "customer_profile": ("Customer profile", 7),
    "customer_concentration": ("Customer concentration", 5),
    "geography": ("Operating geography", 5),
    "fleet_model": ("Fleet / operating model", 8),
    "fuel_cost_allocation": ("Fuel-cost allocation", 5),
    "growth_stage": ("Growth stage", 5),
    "growth_pattern": ("Growth pattern", 5),
    "revenue_growth_band": ("Revenue-growth band", 2),
}

EXCEL_MAP = {
    "Segmen": "segment",
    "Sektor": "sector",
    "Sektor Penyesuaian": "adjusted_sector",
    "CIF": "cif",
    "Debitur": "company_name",
    "Unit": "unit",
    "KOL": "kol",
    "RESTRU": "restructuring",
    "Bade (Rp M)": "bade_rp_m",
    "Limit (Rp M)": "limit_rp_m",
    "%CKPN": "ckpn_pct",
    "Coal Related Industry \n(Y/T)": "coal_related",
    "Lokasi Tambang \n(Indonesia / Luar)": "mine_location",
    "% Coal Related": "coal_revenue_pct",
    "Tagging Debitur Batubara\n(Pemegang IUP/ Kontraktor/ Trader/ Transporter/Holding Non Operating/Holding Operating)": "coal_role",
    "Klasifikasi Dukungan Group Usaha": "group_support",
}


def text_tokens(value):
    missing = {"", "nan", "n/a", "na", "unknown", "undetermined", "belum diisi"}
    return {
        item.strip().casefold()
        for item in str(value).replace("|", ";").split(";")
        if item.strip().casefold() not in missing
    }


def normalize_name(value):
    """Normalize legal prefixes/punctuation so the same company is not selected as its own peer."""
    name = str(value).casefold()
    for token in ["pt.", "pt ", "tbk.", "tbk", ",", "."]:
        name = name.replace(token, " ")
    return " ".join(name.split())


def field_similarity(left, right):
    a, b = text_tokens(left), text_tokens(right)
    if not a or not b:
        return None
    return 100 * len(a & b) / len(a | b)


def peer_score(target, candidate):
    points = 0.0
    used_weight = 0.0
    details = []
    for field, (label, weight) in SCORING_FIELDS.items():
        score = field_similarity(target.get(field, ""), candidate.get(field, ""))
        if score is None:
            details.append({"Parameter": label, "Target": target.get(field, ""),
                            "Peer": candidate.get(field, ""), "Match": "Need data", "Weight": weight})
            continue
        points += score * weight
        used_weight += weight
        details.append({"Parameter": label, "Target": target.get(field, ""),
                        "Peer": candidate.get(field, ""), "Match": f"{score:.0f}%", "Weight": weight})
    final = points / used_weight if used_weight else 0.0
    coverage = used_weight / sum(weight for _, weight in SCORING_FIELDS.values()) * 100
    return round(final, 1), round(coverage, 1), details


def eligibility_reason(target, candidate):
    if str(candidate.get("business_role", "")).casefold() != "kontraktor":
        return False, "Business role is not Kontraktor"
    target_subsector = text_tokens(target.get("subsector", ""))
    peer_subsector = text_tokens(candidate.get("subsector", ""))
    if target_subsector and peer_subsector and not (target_subsector & peer_subsector):
        return False, "Different mining-services subsector"
    return True, "Eligible operational peer"


def rank_candidates(database, target):
    rows = []
    for _, candidate in database.iterrows():
        if normalize_name(candidate["company_name"]) == normalize_name(target["company_name"]):
            continue
        eligible, reason = eligibility_reason(target, candidate)
        if not eligible:
            continue
        score, coverage, _ = peer_score(target, candidate)
        rows.append({**candidate.to_dict(), "peer_score": score,
                     "data_coverage": coverage, "eligibility": reason})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["peer_score", "data_coverage"], ascending=False)


def read_portfolio_excel(uploaded):
    book = pd.ExcelFile(uploaded)
    sheet = "Input Data" if "Input Data" in book.sheet_names else book.sheet_names[0]
    # The departmental workbook has its field names on Excel row 2.
    raw = pd.read_excel(book, sheet_name=sheet, header=1)
    raw.columns = [str(c).strip() for c in raw.columns]
    normalized_map = {str(k).strip(): v for k, v in EXCEL_MAP.items()}
    available = {c: normalized_map[c] for c in raw.columns if c in normalized_map}
    if "Debitur" not in raw.columns:
        # Also accept a clean extract whose first row is already the header.
        raw = pd.read_excel(book, sheet_name=sheet, header=0)
        raw.columns = [str(c).strip() for c in raw.columns]
        available = {c: normalized_map[c] for c in raw.columns if c in normalized_map}
    result = raw[list(available)].rename(columns=available)
    for column in PORTFOLIO_COLUMNS:
        if column not in result:
            result[column] = ""
    result = result[PORTFOLIO_COLUMNS]
    result = result[result["company_name"].notna()].copy()
    result["company_name"] = result["company_name"].astype(str).str.strip()
    return result


@st.cache_data(show_spinner=False)
def load_master():
    data = pd.read_csv(MASTER_PATH, dtype=str).fillna("")
    for column in PROFILE_COLUMNS:
        if column not in data:
            data[column] = ""
    return data[PROFILE_COLUMNS]


def excel_download(target, shortlist, comparison=None):
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="xlsxwriter") as writer:
        pd.DataFrame([target]).to_excel(writer, sheet_name="Target Profile", index=False)
        shortlist.to_excel(writer, sheet_name="Peer Shortlist", index=False)
        if comparison is not None:
            comparison.to_excel(writer, sheet_name="Comparison", index=False)
        pd.DataFrame({"Interpretation": [
            "Peer score measures operational comparability, not creditworthiness.",
            "Financial statements must be obtained and reviewed separately by CRM.",
            "Low data coverage means the result requires further profiling.",
        ]}).to_excel(writer, sheet_name="Notes", index=False)
    return stream.getvalue()


st.markdown(
    '<div class="hero"><span class="tag">COMMERCIAL RISK 3 · MI3 PILOT</span>'
    '<h1>PEARL · Coal Mining Contractor Peer Finder</h1>'
    '<p>Portfolio mapping, operational peer screening, and business-pattern diagnostics</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Data source")
    st.caption("Default database contains only illustrative/public profiles.")
    portfolio_file = st.file_uploader("Import approved portfolio workbook", type=["xlsx", "xls"])
    profile_file = st.file_uploader("Use updated peer profile (CSV)", type=["csv"])
    st.warning("Do not upload confidential Bank/debtor data to a public deployment. Use only an internally approved environment or sanitized extract.")

master = load_master().copy()
if profile_file is not None:
    incoming = pd.read_csv(profile_file, dtype=str).fillna("")
    missing = set(PROFILE_COLUMNS) - set(incoming.columns)
    if missing:
        st.sidebar.error("Missing profile columns: " + ", ".join(sorted(missing)))
    else:
        master = incoming[PROFILE_COLUMNS]
        st.sidebar.success("Updated peer profile loaded")

if "session_profiles" not in st.session_state:
    st.session_state.session_profiles = []
if st.session_state.session_profiles:
    additions = pd.DataFrame(st.session_state.session_profiles)
    master = pd.concat([master, additions[PROFILE_COLUMNS]], ignore_index=True)
    master = master.drop_duplicates(subset="company_name", keep="last")

portfolio = pd.DataFrame(columns=PORTFOLIO_COLUMNS)
if portfolio_file is not None:
    try:
        portfolio = read_portfolio_excel(portfolio_file)
        st.sidebar.success(f"{len(portfolio):,} portfolio rows imported")
    except Exception as error:
        st.sidebar.error(f"Workbook could not be read: {error}")

pages = st.tabs(["Portfolio map", "Peer finder", "Business-pattern diagnostic", "Maintain database", "Methodology"])

with pages[0]:
    st.subheader("Portfolio map in the format of the previous departmental database")
    if portfolio.empty:
        st.info("Upload an approved/sanitized workbook to reproduce the portfolio view. The app recognizes the `Input Data` format.")
    else:
        mi3 = portfolio[portfolio["unit"].astype(str).str.contains("MINING & ENERGY", case=False, na=False)].copy()
        coal = mi3[mi3["coal_related"].astype(str).str.casefold().isin(["ya", "y", "yes"])].copy()
        contractors = coal[coal["coal_role"].astype(str).str.contains("kontraktor", case=False, na=False)]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Baris portofolio MI3", f"{len(mi3):,}")
        m2.metric("Coal-related MI3", f"{len(coal):,}")
        m3.metric("Baris kontraktor", f"{len(contractors):,}")
        m4.metric("Debitur kontraktor unik", f"{contractors.company_name.nunique():,}")
        summary = (coal.groupby("coal_role", dropna=False)["company_name"].nunique()
                   .sort_values(ascending=False).rename("Unique debtors").reset_index())
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.dataframe(contractors[PORTFOLIO_COLUMNS], use_container_width=True, hide_index=True, height=360)

with pages[1]:
    st.subheader("Cari perusahaan pembanding yang sepadan")
    target_sources = ["Pilih dari database peer", "Masukkan perusahaan baru"]
    mi3_contractors = pd.DataFrame()
    if not portfolio.empty:
        mi3_contractors = portfolio[
            portfolio["unit"].astype(str).str.contains("MINING & ENERGY", case=False, na=False)
            & portfolio["coal_role"].astype(str).str.contains("kontraktor", case=False, na=False)
        ]
        if not mi3_contractors.empty:
            target_sources.insert(1, "Pilih debitur dari workbook")
    mode = st.radio("Sumber target", target_sources, horizontal=True)

    blank = {column: "" for column in PROFILE_COLUMNS}
    if mode == "Pilih dari database peer":
        chosen = st.selectbox("Perusahaan target", sorted(master["company_name"].unique()))
        initial = master[master["company_name"] == chosen].iloc[0].to_dict()
        manual_profile = False
    elif mode == "Pilih debitur dari workbook":
        chosen = st.selectbox("Debitur target", sorted(mi3_contractors["company_name"].dropna().unique()))
        matched = master[master["company_name"].map(normalize_name) == normalize_name(chosen)]
        initial = matched.iloc[0].to_dict() if not matched.empty else blank.copy()
        initial.update({"company_name": chosen, "sector": "Mining & Energy",
                        "subsector": "Coal Mining Services", "business_role": "Kontraktor"})
        manual_profile = True
        if matched.empty:
            st.info("Debitur ditemukan di workbook, tetapi profil operasionalnya belum ada. Lengkapi informasi di bawah sebelum mencari peers.")
    else:
        initial = blank.copy()
        initial["company_name"] = st.text_input("Nama perusahaan baru", "", placeholder="Contoh: PT ABC Mining Services")
        initial.update({"sector": "Mining & Energy", "subsector": "Coal Mining Services", "business_role": "Kontraktor"})
        manual_profile = True

    target = initial.copy()
    if manual_profile:
        st.caption("Kosongkan informasi yang belum diketahui. Data kosong akan menurunkan Data Coverage, bukan dianggap cocok.")
        c1, c2 = st.columns(2)
        target["sector"] = c1.selectbox("Sektor", ["Mining & Energy"])
        subsectors = ["Coal Mining Services", "Diversified Mining Services"]
        subsector_index = subsectors.index(initial.get("subsector")) if initial.get("subsector") in subsectors else 0
        target["subsector"] = c2.selectbox("Subsektor", subsectors, index=subsector_index)
        target["business_role"] = "Kontraktor"
        inputs = {
            "service_scope": "Lingkup jasa (pisahkan dengan titik koma)",
            "primary_commodity": "Komoditas utama",
            "contract_profile": "Profil kontrak",
            "tariff_model": "Model tarif",
            "customer_profile": "Profil pelanggan",
            "customer_concentration": "Konsentrasi pelanggan",
            "geography": "Wilayah operasi",
            "fleet_model": "Model fleet",
            "fuel_cost_allocation": "Pembebanan biaya BBM",
            "growth_stage": "Tahap pertumbuhan",
            "growth_pattern": "Pola pertumbuhan",
            "revenue_growth_band": "Kelompok pertumbuhan pendapatan",
        }
        cols = st.columns(2)
        for index, (field, label) in enumerate(inputs.items()):
            target[field] = cols[index % 2].text_input(label, value=str(initial.get(field, "")), key=f"target_{mode}_{field}")

    run_analysis = st.button("Cari peers", type="primary", use_container_width=True)
    if run_analysis:
        if not str(target.get("company_name", "")).strip():
            st.error("Nama perusahaan wajib diisi.")
        else:
            st.session_state.analysis_target = target
            st.session_state.analysis_ranked = rank_candidates(master, target)

    ranked = st.session_state.get("analysis_ranked", pd.DataFrame())
    analysis_target = st.session_state.get("analysis_target")
    if analysis_target is None:
        st.info("Lengkapi profil target, lalu tekan **Cari peers**.")
    elif ranked.empty:
        st.warning("Belum ada kandidat peer yang memenuhi syarat. Tambahkan atau perkaya profil pada menu Maintain database.")
    else:
        target = analysis_target
        st.success(f"Hasil peer untuk: {target['company_name']}")
        count_options = list(range(1, min(10, len(ranked)) + 1))
        count = st.select_slider("Number of candidates", options=count_options,
                                 value=min(5, len(ranked)))
        shortlist = ranked.head(count)
        view_columns = ["company_name", "subsector", "service_scope", "growth_stage",
                        "peer_score", "data_coverage", "verification_status"]
        st.dataframe(
            shortlist[view_columns], use_container_width=True, hide_index=True,
            column_config={
                "peer_score": st.column_config.ProgressColumn("Peer score", min_value=0, max_value=100, format="%.1f"),
                "data_coverage": st.column_config.ProgressColumn("Data coverage", min_value=0, max_value=100, format="%.1f%%"),
            },
        )
        st.caption("Peer score = operational comparability. It is not a rating, financial-performance score, or credit decision.")
        already_saved = any(master["company_name"].map(normalize_name) == normalize_name(target["company_name"]))
        if not already_saved and st.button("Tambahkan target ke database sesi"):
            saved_target = {column: str(target.get(column, "")) for column in PROFILE_COLUMNS}
            saved_target["verification_status"] = saved_target.get("verification_status") or "Pending CRM Validation"
            st.session_state.session_profiles.append(saved_target)
            st.session_state.profile_saved_message = True
            st.rerun()

with pages[2]:
    st.subheader("Explain why performance can differ")
    ranked = st.session_state.get("analysis_ranked", pd.DataFrame())
    target = st.session_state.get("analysis_target")
    if target is None or ranked.empty:
        st.info("Jalankan pencarian pada menu Peer finder terlebih dahulu.")
    else:
        selected = st.selectbox("Comparison peer", ranked.head(10)["company_name"].tolist())
        peer = ranked[ranked["company_name"] == selected].iloc[0].to_dict()
        score, coverage, details = peer_score(target, peer)
        comparison = pd.DataFrame(details)
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        differing = comparison[comparison["Match"].isin(["0%", "Need data"])]
        st.markdown("#### CRM interpretation prompts")
        prompts = {
            "Service scope": "Different work scopes change equipment mix, execution risk, and achievable margin.",
            "Contract profile": "Contract tenor, minimum volume, escalation, and penalty clauses affect earnings visibility.",
            "Tariff / revenue model": "Different tariff bases and indexation can produce different margins despite similar volumes.",
            "Customer concentration": "Customer/site concentration changes bargaining power and renewal risk.",
            "Fleet / operating model": "Owned versus leased/subcontracted fleets change fixed costs, capex, and operating leverage.",
            "Fuel-cost allocation": "Fuel pass-through versus contractor-borne fuel creates materially different cost sensitivity.",
            "Growth stage": "Ramp-up, mature operations, or aggressive expansion create different utilization and depreciation profiles.",
            "Growth pattern": "Contract-backed growth is structurally different from speculative fleet expansion.",
        }
        shown = False
        for parameter in differing["Parameter"]:
            if parameter in prompts:
                st.write(f"- **{parameter}:** {prompts[parameter]}")
                shown = True
        if not shown:
            st.write("The recorded patterns are broadly similar. CRM should validate volume achievement, fleet utilization, claims/penalties, and one-off project ramp-up effects.")
        st.download_button(
            "Download analysis workbook", excel_download(target, ranked.head(10), comparison),
            file_name="PEARL_peer_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

with pages[3]:
    st.subheader("Maintain the qualitative peer database")
    if st.session_state.pop("profile_saved_message", False):
        st.success("Target telah ditambahkan ke database sesi. Unduh CSV terbaru agar dapat disimpan permanen di GitHub.")
    st.write("CRM/PIC can add a company, update public-source profiles, and validate the record without changing Python code.")
    edited = st.data_editor(master, use_container_width=True, hide_index=True, num_rows="dynamic", height=500)
    c1, c2 = st.columns(2)
    c1.download_button("Download updated database", edited.to_csv(index=False).encode("utf-8-sig"),
                       file_name="peer_database.csv", mime="text/csv", use_container_width=True)
    c2.download_button("Download blank template", pd.DataFrame(columns=PROFILE_COLUMNS).to_csv(index=False).encode("utf-8-sig"),
                       file_name="peer_database_template.csv", mime="text/csv", use_container_width=True)

with pages[4]:
    st.subheader("Peer selection methodology")
    method = pd.DataFrame([
        {"Criterion": label, "Weight": f"{weight}%", "Rationale": "Operational/economic comparability"}
        for _, (label, weight) in SCORING_FIELDS.items()
    ])
    st.dataframe(method, use_container_width=True, hide_index=True)
    st.markdown("""
    **Step 1 — eligibility:** candidate must be a mining contractor in the relevant mining-services subsector.  
    **Step 2 — comparability:** weighted similarity of business pattern and growth characteristics.  
    **Step 3 — CRM judgment:** review contract specifics, customer/site concentration, fleet utilization, and cost allocation.  
    **Step 4 — financial analysis:** CRM obtains the latest statements and compares margins, leverage, cash flow, and DSCR separately.
    """)
    st.info("A high peer score means 'operationally comparable', not 'financially healthy'. Missing fields reduce data coverage instead of being treated as a match.")
