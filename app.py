import io
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import trafilatura
from ddgs import DDGS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="PEARL MI3", page_icon="◈", layout="wide")

st.markdown("""
<style>
.stApp {background:#f4f7fb;color:#172033}.block-container{max-width:1280px;padding-top:1.5rem}
.hero{background:linear-gradient(120deg,#082b5c,#0b4d8f);padding:28px 32px;border-radius:18px;color:white;margin-bottom:18px}
.hero h1{margin:0;font-size:2.15rem}.hero p{margin:.45rem 0 0;color:#d9e9ff}
.badge{display:inline-block;padding:4px 10px;border-radius:999px;background:#e7f1ff;color:#0b4d8f;font-weight:700;font-size:.78rem}
[data-testid="stMetric"]{background:white;border:1px solid #e1e8f2;padding:12px;border-radius:14px}
</style>
""", unsafe_allow_html=True)

SECTOR_RULES = {
    "Mining & Energy": {
        "Mining Contractor": ["mining contractor", "mining services", "contract mining", "overburden", "drilling", "blasting", "coal hauling"],
        "Coal Owner/Producer": ["coal producer", "coal concession", "coal reserves", "thermal coal", "coal production"],
        "Power & Renewable Energy": ["power generation", "electricity", "renewable energy", "geothermal", "solar power", "hydropower"]},
    "Oil & Gas": {
        "Upstream E&P": ["exploration and production", "upstream oil", "oil and gas producer", "oil reserves", "gas reserves", "lifting"],
        "Oilfield Services": ["oilfield services", "drilling services", "offshore services", "well services", "rig services"],
        "Downstream & Distribution": ["fuel distribution", "refinery", "downstream oil", "gas distribution", "petroleum distribution"]},
    "Construction": {
        "General Contractor": ["general contractor", "construction services", "building contractor", "civil contractor"],
        "EPC & Infrastructure": ["engineering procurement construction", "epc contractor", "infrastructure construction", "toll road construction"]},
    "Property": {
        "Residential Developer": ["residential developer", "housing development", "property developer", "township"],
        "Commercial & Industrial Estate": ["industrial estate", "office property", "commercial property", "shopping mall", "recurring income"]},
    "Hotel": {
        "Hotel Owner/Operator": ["hotel operator", "hotel owner", "hospitality company", "hotel management", "resort operator"]}
}

COMPANIES = [
    ("PT Bukit Makmur Mandiri Utama", "BUMA", "Mining & Energy", "Mining Contractor", "Indonesia", 95, "Mining services and contract mining including overburden removal, coal hauling, drilling and blasting."),
    ("PT Pamapersada Nusantara", "PAMA", "Mining & Energy", "Mining Contractor", "Indonesia", 100, "Large mining contractor providing mine planning, overburden removal, coal mining and hauling."),
    ("PT Saptaindra Sejati", "SIS", "Mining & Energy", "Mining Contractor", "Indonesia", 78, "Integrated mining services covering exploration support, overburden, mining and coal hauling."),
    ("PT Putra Perkasa Abadi", "PPA", "Mining & Energy", "Mining Contractor", "Indonesia", 72, "Coal mining contractor providing earthmoving, overburden removal and mining services."),
    ("PT Cipta Kridatama", "CK", "Mining & Energy", "Mining Contractor", "Indonesia", 48, "Mining services contractor for overburden removal, coal extraction and infrastructure."),
    ("PT Darma Henwa Tbk", "DEWA", "Mining & Energy", "Mining Contractor", "Indonesia", 45, "Integrated mining services, earthworks, mining infrastructure and mineral processing."),
    ("PT Petrosea Tbk", "PTRO", "Mining & Energy", "Mining Contractor", "Indonesia", 55, "Contract mining, EPC, engineering and logistics services for mining and energy."),
    ("PT Adaro Andalan Indonesia Tbk", "AADI", "Mining & Energy", "Coal Owner/Producer", "Indonesia", 92, "Thermal coal producer with mining concessions, coal reserves and integrated logistics."),
    ("PT Bukit Asam Tbk", "PTBA", "Mining & Energy", "Coal Owner/Producer", "Indonesia", 86, "State-owned coal producer with coal reserves, mines, logistics and power development."),
    ("PT Bayan Resources Tbk", "BYAN", "Mining & Energy", "Coal Owner/Producer", "Indonesia", 82, "Coal producer and concession owner operating integrated mining and logistics assets."),
    ("PT Medco Energi Internasional Tbk", "MEDC", "Oil & Gas", "Upstream E&P", "Indonesia", 88, "Upstream oil and gas exploration and production with international assets and power operations."),
    ("PT Energi Mega Persada Tbk", "ENRG", "Oil & Gas", "Upstream E&P", "Indonesia", 52, "Upstream oil and gas exploration, development and production company."),
    ("PT Elnusa Tbk", "ELSA", "Oil & Gas", "Oilfield Services", "Indonesia", 50, "Integrated oilfield services including seismic, drilling, well services and energy logistics."),
    ("PT Apexindo Pratama Duta Tbk", "APEX", "Oil & Gas", "Oilfield Services", "Indonesia", 32, "Onshore and offshore drilling contractor providing rig services to oil and gas companies."),
    ("PT Perusahaan Gas Negara Tbk", "PGAS", "Oil & Gas", "Downstream & Distribution", "Indonesia", 90, "Natural gas transmission, distribution, trading and infrastructure company."),
    ("PT Wijaya Karya (Persero) Tbk", "WIKA", "Construction", "EPC & Infrastructure", "Indonesia", 90, "EPC and infrastructure contractor covering transport, buildings, energy and industrial projects."),
    ("PT PP (Persero) Tbk", "PTPP", "Construction", "General Contractor", "Indonesia", 88, "General construction and EPC company for buildings, infrastructure, property and energy projects."),
    ("PT Adhi Karya (Persero) Tbk", "ADHI", "Construction", "EPC & Infrastructure", "Indonesia", 80, "Infrastructure and EPC contractor for railway, toll road, building and water projects."),
    ("PT Nusa Raya Cipta Tbk", "NRCA", "Construction", "General Contractor", "Indonesia", 40, "General contractor focused on commercial, industrial, hotel and infrastructure construction."),
    ("PT Total Bangun Persada Tbk", "TOTL", "Construction", "General Contractor", "Indonesia", 35, "Building contractor for premium high-rise, commercial, residential and hospitality projects."),
    ("PT Bumi Serpong Damai Tbk", "BSDE", "Property", "Residential Developer", "Indonesia", 92, "Integrated township and residential property developer with commercial recurring assets."),
    ("PT Ciputra Development Tbk", "CTRA", "Property", "Residential Developer", "Indonesia", 84, "Diversified residential and township developer operating projects across Indonesia."),
    ("PT Summarecon Agung Tbk", "SMRA", "Property", "Residential Developer", "Indonesia", 65, "Township developer with residential sales, malls and recurring commercial income."),
    ("PT Puradelta Lestari Tbk", "DMAS", "Property", "Commercial & Industrial Estate", "Indonesia", 60, "Industrial estate developer selling industrial land and commercial property."),
    ("PT Kawasan Industri Jababeka Tbk", "KIJA", "Property", "Commercial & Industrial Estate", "Indonesia", 58, "Industrial estate and township developer with infrastructure and recurring services."),
    ("PT Hotel Sahid Jaya International Tbk", "SHID", "Hotel", "Hotel Owner/Operator", "Indonesia", 32, "Hotel owner and hospitality operator managing accommodation, food and event facilities."),
    ("PT Eastparc Hotel Tbk", "EAST", "Hotel", "Hotel Owner/Operator", "Indonesia", 20, "Hotel and resort owner focused on rooms, food and beverage, meetings and leisure facilities."),
    ("PT Indonesian Paradise Property Tbk", "INPP", "Hotel", "Hotel Owner/Operator", "Indonesia", 45, "Hospitality and lifestyle property owner with hotels, malls and mixed-use assets."),
    ("PT Menteng Heritage Realty Tbk", "HRME", "Hotel", "Hotel Owner/Operator", "Indonesia", 18, "Hotel property owner generating revenue from rooms, food, beverage and hospitality services.")
]

DB = pd.DataFrame(COMPANIES, columns=["company_name","ticker","sector","business_model","country","scale_index","description"])

def norm(s): return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).strip()

@st.cache_data(ttl=3600, show_spinner=False)
def search_web(company):
    rows=[]
    queries=[f'"{company}" company profile business', f'"{company}" annual report sector']
    try:
        with DDGS() as ddgs:
            for query in queries:
                for r in ddgs.text(query, region="id-id", max_results=5):
                    rows.append({"title":r.get("title",""),"url":r.get("href",""),"snippet":r.get("body","")})
    except Exception:
        pass
    seen=set(); out=[]
    for r in rows:
        if r["url"] and r["url"] not in seen:
            seen.add(r["url"]); out.append(r)
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_text(url):
    try:
        res=requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
        if "pdf" in res.headers.get("content-type","").lower(): return ""
        return trafilatura.extract(res.text, favor_precision=True) or ""
    except Exception: return ""

def classify(text):
    text=norm(text); scores=[]
    for sector, models in SECTOR_RULES.items():
        for model, keys in models.items():
            score=sum(text.count(k) for k in keys)
            scores.append((score,sector,model,[k for k in keys if k in text]))
    scores.sort(reverse=True)
    return scores[0] if scores and scores[0][0] else (0,"Unclassified","Unclassified",[])

def resolve_target(name, web_text):
    exact=DB[DB.company_name.map(norm).str.contains(norm(name),regex=False)]
    if not exact.empty:
        row=exact.iloc[0]
        return row.sector,row.business_model,row.description,"Reference database"
    score,sector,model,_=classify(web_text)
    return sector,model,web_text[:1200] or "Public profile could not be extracted.","Live public search"

def rank_peers(name, sector, model, description):
    pool=DB[(DB.sector==sector)&(DB.company_name.map(norm)!=norm(name))].copy()
    if pool.empty: return pool
    docs=[description]+pool.description.tolist()
    tf=TfidfVectorizer(ngram_range=(1,2),stop_words="english").fit_transform(docs)
    pool["text_similarity"]=cosine_similarity(tf[0:1],tf[1:])[0]*100
    pool["model_match"]=(pool.business_model==model).astype(int)*100
    known=DB[DB.company_name.map(norm)==norm(name)]
    target_scale=float(known.iloc[0].scale_index) if not known.empty else float(pool.scale_index.median())
    pool["scale_similarity"]=(1-(pool.scale_index-target_scale).abs()/max(target_scale,1)).clip(0,1)*100
    pool["similarity_score"]=.50*pool.model_match+.30*pool.text_similarity+.20*pool.scale_similarity
    pool["peer_type"]=np.where(pool.model_match==100,"Direct Operational Peer","Sector Peer")
    return pool.sort_values("similarity_score",ascending=False).head(7)

def excel_bytes(target, peers, sources):
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine="xlsxwriter") as writer:
        pd.DataFrame([target]).to_excel(writer,sheet_name="Target",index=False)
        peers.to_excel(writer,sheet_name="Peer Ranking",index=False)
        pd.DataFrame(sources).to_excel(writer,sheet_name="Source Log",index=False)
    return output.getvalue()

st.markdown('<div class="hero"><span class="badge">COMMERCIAL RISK 3 GROUP</span><h1>PEARL MI3</h1><p>Peer Analytics and Risk Lens · Multi-sector peer discovery for credit analysis</p></div>',unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Coverage")
    st.write("Mining & Energy\n\nOil & Gas\n\nConstruction\n\nProperty\n\nHotel")
    st.divider()
    st.caption("Public-information decision support. Every result requires CRM verification.")

left,right=st.columns([4,1])
with left:
    company=st.text_input("Company name",value="PT Bukit Makmur Mandiri Utama",placeholder="e.g. PT Bukit Makmur Mandiri Utama")
with right:
    sector_override=st.selectbox("Sector",["Auto Detect"]+list(SECTOR_RULES.keys()))

if st.button("Search & analyze peers",type="primary",use_container_width=True):
    if not company.strip(): st.warning("Enter a company name first."); st.stop()
    with st.spinner("Searching public sources and matching comparable companies..."):
        sources=search_web(company)
        web_text=" ".join([s["title"]+" "+s["snippet"] for s in sources])
        for source in sources[:3]: web_text += " " + fetch_text(source["url"])[:20000]
        sector,model,description,method=resolve_target(company,web_text)
        if sector_override!="Auto Detect":
            sector=sector_override
            _,auto_model,_,_=classify(web_text)
            if auto_model in SECTOR_RULES[sector]: model=auto_model
            else: model=list(SECTOR_RULES[sector].keys())[0]
        peers=rank_peers(company,sector,model,description)
        st.session_state.result=(sector,model,description,method,peers,sources)

if "result" in st.session_state:
    sector,model,description,method,peers,sources=st.session_state.result
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Detected sector",sector); c2.metric("Business model",model); c3.metric("Peers selected",len(peers)); c4.metric("Public sources",len(sources))
    tab1,tab2,tab3,tab4=st.tabs(["Peer ranking","Comparison","Sources","NAK narrative"])
    with tab1:
        shown=peers[["company_name","ticker","business_model","peer_type","similarity_score"]].copy()
        shown.index=np.arange(1,len(shown)+1)
        st.dataframe(shown,use_container_width=True,column_config={"similarity_score":st.column_config.ProgressColumn("Similarity",min_value=0,max_value=100,format="%.1f")})
        st.caption("Similarity combines business-model match, profile-text similarity, and relative operating scale proxy.")
    with tab2:
        if not peers.empty:
            fig=px.bar(peers.sort_values("similarity_score"),x="similarity_score",y="company_name",orientation="h",color="peer_type",labels={"similarity_score":"Similarity score","company_name":""},color_discrete_sequence=["#0b4d8f","#e6a700"])
            fig.update_layout(template="plotly_white",legend_title="")
            st.plotly_chart(fig,use_container_width=True)
    with tab3:
        st.write(f"Classification method: **{method}**")
        if sources:
            for s in sources: st.markdown(f"- [{s['title']}]({s['url']}) — {s['snippet'][:220]}")
        else: st.info("Live sources were unavailable; the reference database kept the demo operational.")
    with tab4:
        names=", ".join(peers.company_name.head(5).tolist())
        narrative=(f"Berdasarkan pemetaan perusahaan pembanding, {company} diklasifikasikan pada sektor {sector} dengan business model {model}. Kandidat peers yang paling relevan meliputi {names}. Pemilihan didasarkan pada kesamaan kegiatan usaha, layanan utama, dan proksi skala operasi. Hasil ini merupakan preliminary peer screening dan tetap memerlukan validasi laporan keuangan, periode data, struktur grup, serta professional judgment Credit Risk Manager sebelum digunakan dalam NAK.")
        st.text_area("Draft peer analysis",narrative,height=190)
        target={"company_name":company,"sector":sector,"business_model":model,"classification_method":method,"retrieved_at":datetime.now(timezone.utc).isoformat()}
        st.download_button("Download analysis (Excel)",excel_bytes(target,peers,sources),file_name="PEARL_MI3_Peer_Analysis.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
else:
    st.info("Enter a company name, then select **Search & analyze peers**. Try BUMA, Medco, WIKA, BSDE, or Eastparc Hotel.")

