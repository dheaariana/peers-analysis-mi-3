import io
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from ddgs import DDGS

st.set_page_config(page_title="PEARL MI3 Dynamic", page_icon="◈", layout="wide")
st.markdown("""
<style>
.stApp{background:#f4f7fb;color:#172033}.block-container{max-width:1280px;padding-top:1.4rem}
.hero{background:linear-gradient(120deg,#082b5c,#0b559d);padding:26px 30px;border-radius:18px;color:white;margin-bottom:18px}
.hero h1{margin:6px 0;font-size:2.1rem}.hero p{margin:0;color:#dcecff}
.tag{display:inline-block;padding:4px 10px;border-radius:999px;background:#e6f1ff;color:#0b4d8f;font-weight:750;font-size:.78rem}
[data-testid="stMetric"]{background:#fff;border:1px solid #dfe7f1;padding:12px;border-radius:14px}
</style>
""", unsafe_allow_html=True)

TAXONOMY = {
    "Mining & Energy": {
        "Mining Contractor": ["mining contractor","mining services","contract mining","overburden","drilling and blasting","coal hauling"],
        "Coal Owner/Producer": ["coal producer","coal concession","coal reserves","thermal coal","coal production"],
        "Mineral Mining": ["gold mining","nickel mining","copper mining","mineral producer","mineral resources"],
        "Power Generation": ["power generation","electricity producer","power plant","independent power producer"],
        "Renewable/Geothermal": ["renewable energy","geothermal","solar power","hydropower","wind power"]},
    "Oil & Gas": {
        "Upstream E&P": ["exploration and production","upstream oil","oil and gas producer","oil reserves","gas reserves","lifting"],
        "Oilfield/Drilling Services": ["oilfield services","drilling services","offshore services","well services","rig services"],
        "Midstream/Distribution": ["gas transmission","pipeline","gas distribution","fuel distribution","energy logistics"],
        "Downstream/Refinery": ["oil refinery","refining","petrochemical","downstream oil","fuel retail"]},
    "Construction": {
        "General Contractor": ["general contractor","construction services","building contractor","civil contractor"],
        "EPC Contractor": ["engineering procurement construction","epc contractor","industrial construction"],
        "Infrastructure Contractor": ["infrastructure construction","toll road","railway construction","bridge construction"]},
    "Property": {
        "Residential/Township": ["residential developer","housing development","property developer","township"],
        "Commercial Property": ["office property","commercial property","shopping mall","mixed use development"],
        "Industrial Estate": ["industrial estate","industrial land","industrial park","logistics estate"]},
    "Hotel": {
        "Hotel Owner/Operator": ["hotel operator","hotel owner","hospitality company","hotel management"],
        "Resort Operator": ["resort operator","resort hotel","leisure hospitality"],
        "Budget Hotel": ["budget hotel","economy hotel","limited service hotel"]}
}

SCALE_KEYWORDS = {
    "Large/National": ["largest","leading","major","national","nationwide","public listed","tbk","market leader","international","billion","trillion"],
    "Medium": ["mid-sized","medium-sized","regional","established company","multiple projects","million"],
    "Small/Regional": ["small company","local contractor","local developer","boutique","single project","regional operator"]
}

# Fallback keeps the demonstration useful if a search provider is temporarily unavailable.
REFERENCE = [
    ("PT Bukit Makmur Mandiri Utama","Mining & Energy","Mining Contractor","Large/National","BUMA mining services and contract mining in Indonesia and Australia."),
    ("PT Pamapersada Nusantara","Mining & Energy","Mining Contractor","Large/National","Large national mining contractor providing overburden removal and coal hauling."),
    ("PT Saptaindra Sejati","Mining & Energy","Mining Contractor","Large/National","Integrated mining services and coal mining contractor."),
    ("PT Putra Perkasa Abadi","Mining & Energy","Mining Contractor","Large/National","Mining contractor providing earthmoving and overburden services."),
    ("PT Cipta Kridatama","Mining & Energy","Mining Contractor","Medium","Mining services contractor for coal and mineral operations."),
    ("PT Darma Henwa Tbk","Mining & Energy","Mining Contractor","Medium","Public listed integrated mining services contractor."),
    ("PT Petrosea Tbk","Mining & Energy","Mining Contractor","Medium","Contract mining and EPC services company."),
    ("PT Adaro Andalan Indonesia Tbk","Mining & Energy","Coal Owner/Producer","Large/National","Large thermal coal producer and concession owner."),
    ("PT Bukit Asam Tbk","Mining & Energy","Coal Owner/Producer","Large/National","National coal producer with reserves and integrated logistics."),
    ("PT Bayan Resources Tbk","Mining & Energy","Coal Owner/Producer","Large/National","Major coal producer and concession owner."),
    ("PT Medco Energi Internasional Tbk","Oil & Gas","Upstream E&P","Large/National","International upstream oil and gas exploration and production company."),
    ("PT Energi Mega Persada Tbk","Oil & Gas","Upstream E&P","Medium","Upstream oil and gas producer."),
    ("PT Elnusa Tbk","Oil & Gas","Oilfield/Drilling Services","Large/National","Integrated national oilfield and drilling services."),
    ("PT Apexindo Pratama Duta Tbk","Oil & Gas","Oilfield/Drilling Services","Medium","Onshore and offshore drilling contractor."),
    ("PT Wijaya Karya (Persero) Tbk","Construction","EPC Contractor","Large/National","National EPC and infrastructure construction company."),
    ("PT PP (Persero) Tbk","Construction","General Contractor","Large/National","National general construction and EPC contractor."),
    ("PT Adhi Karya (Persero) Tbk","Construction","Infrastructure Contractor","Large/National","National railway and infrastructure contractor."),
    ("PT Nusa Raya Cipta Tbk","Construction","General Contractor","Medium","Public listed building and general contractor."),
    ("PT Total Bangun Persada Tbk","Construction","General Contractor","Medium","Building contractor for premium property projects."),
    ("PT Bumi Serpong Damai Tbk","Property","Residential/Township","Large/National","Large integrated township property developer."),
    ("PT Ciputra Development Tbk","Property","Residential/Township","Large/National","National residential and township developer."),
    ("PT Summarecon Agung Tbk","Property","Residential/Township","Large/National","Township and commercial property developer."),
    ("PT Puradelta Lestari Tbk","Property","Industrial Estate","Medium","Industrial estate and industrial land developer."),
    ("PT Kawasan Industri Jababeka Tbk","Property","Industrial Estate","Large/National","Large industrial estate and township developer."),
    ("PT Hotel Sahid Jaya International Tbk","Hotel","Hotel Owner/Operator","Medium","Hotel owner and hospitality operator."),
    ("PT Eastparc Hotel Tbk","Hotel","Hotel Owner/Operator","Small/Regional","Single-market hotel owner and operator."),
    ("PT Indonesian Paradise Property Tbk","Hotel","Hotel Owner/Operator","Medium","Hospitality and lifestyle property owner."),
]
REF = pd.DataFrame(REFERENCE, columns=["company_name","sector","business_model","scale","description"])

def clean(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9&.,()'’\- ]", " ", str(value))).strip()

def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

@st.cache_data(ttl=1800, show_spinner=False)
def web_search(query, limit=8):
    rows=[]
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, region="id-id", safesearch="moderate", max_results=limit):
                rows.append({"title":item.get("title", ""), "url":item.get("href", ""), "snippet":item.get("body", ""), "query":query})
    except Exception:
        pass
    return rows

def keyword_hits(text, keywords):
    lowered=text.lower()
    return [keyword for keyword in keywords if keyword in lowered]

def classify_business(text):
    rows=[]
    for sector, models in TAXONOMY.items():
        for model, keywords in models.items():
            hits=keyword_hits(text, keywords)
            rows.append((len(hits), sector, model, hits))
    rows.sort(reverse=True)
    return rows[0] if rows and rows[0][0] else (0,"Unclassified","Unclassified",[])

def classify_scale(text):
    scores=[]
    for scale, keywords in SCALE_KEYWORDS.items():
        hits=keyword_hits(text, keywords)
        scores.append((len(hits),scale,hits))
    scores.sort(reverse=True)
    return scores[0] if scores and scores[0][0] else (0,"Undetermined",[])

def target_profile(company):
    exact=REF[REF.company_name.map(norm)==norm(company)]
    queries=[f'"{company}" company profile business activities', f'"{company}" industry sector Indonesia']
    sources=sum([web_search(query,6) for query in queries],[])
    text=" ".join(f"{x['title']} {x['snippet']}" for x in sources)
    if not exact.empty:
        row=exact.iloc[0]
        return row.sector,row.business_model,row.scale,row.description,sources,"Reference + public search"
    _,sector,model,_=classify_business(text)
    _,scale,_=classify_scale(text)
    return sector,model,scale,text[:1800],sources,"Dynamic public search"

CORPORATE_PATTERN = re.compile(
    r"\b(?:PT\.?\s+)?[A-Z][A-Za-z0-9&'’.,\-]+(?:\s+[A-Z][A-Za-z0-9&'’.,()\-]+){1,8}"
    r"(?:\s+(?:Tbk|Ltd|Limited|Corporation|Corp|Group|Indonesia))?\b"
)

BAD_PHRASES={"Annual Report","Company Profile","Mining Contractor","Oil Gas","Search Results","Indonesia Stock Exchange","Financial Statements","Sustainability Report"}

def names_from_result(result):
    candidates=[]
    title=clean(re.split(r"[|–—:]",result["title"])[0])
    if 2 <= len(title.split()) <= 12:
        candidates.append(title)
    for match in CORPORATE_PATTERN.findall(f"{result['title']} {result['snippet']}"):
        candidates.append(clean(match))
    return [name for name in candidates if name not in BAD_PHRASES and len(name)>=5]

@st.cache_data(ttl=1800, show_spinner=False)
def discover_live(sector, model, scale):
    queries=[
        f'companies "{model}" Indonesia',
        f'largest "{model}" companies Indonesia',
        f'"{model}" company profile Indonesia',
        f'"{model}" competitors Indonesia {scale}'
    ]
    results=sum([web_search(query,10) for query in queries],[])
    records=[]
    for result in results:
        for name in names_from_result(result):
            records.append({"company_name":name,"description":clean(f"{result['title']} {result['snippet']}"),"source_url":result["url"],"source_title":result["title"],"origin":"Live discovery"})
    return records,results

def build_universe(company, sector, model, scale):
    live,_=discover_live(sector,model,scale)
    fallback=REF[(REF.sector==sector)&(REF.company_name.map(norm)!=norm(company))].copy()
    fallback["source_url"]=""; fallback["source_title"]="Reference database"; fallback["origin"]="Reference fallback"
    records=live+fallback[["company_name","description","source_url","source_title","origin"]].to_dict("records")
    dedup={}
    for record in records:
        key=norm(record["company_name"])
        if key and key!=norm(company) and key not in dedup: dedup[key]=record
    return list(dedup.values())

def score_candidates(company, sector, model, scale, records):
    output=[]
    model_keys=TAXONOMY[sector][model]
    for record in records:
        text=f"{record['company_name']} {record['description']}"
        model_hits=keyword_hits(text,model_keys)
        _,candidate_sector,candidate_model,_=classify_business(text)
        _,candidate_scale,scale_hits=classify_scale(text)
        # Results returned by a highly targeted query remain potential candidates when snippets are sparse.
        targeted=record["origin"]=="Live discovery"
        sector_eligible=(candidate_sector==sector) or targeted
        model_score=min(100, 25+20*len(model_hits)) if targeted else min(100,20*len(model_hits))
        if candidate_model==model: model_score=max(model_score,100)
        if candidate_scale==scale: scale_score=100
        elif candidate_scale=="Undetermined": scale_score=50
        elif {candidate_scale,scale}=={"Large/National","Medium"}: scale_score=65
        elif {candidate_scale,scale}=={"Medium","Small/Regional"}: scale_score=65
        else: scale_score=25
        final=.60*model_score+.40*scale_score
        confidence="Verified by rules" if candidate_model==model and candidate_scale==scale else ("Potential—CRM review" if sector_eligible else "Not comparable")
        if sector_eligible:
            output.append({**record,"detected_business_model":candidate_model,"detected_scale":candidate_scale,"business_similarity":model_score,"scale_similarity":scale_score,"peer_score":final,"status":confidence,"matching_basis":", ".join(model_hits+scale_hits) or "Targeted sector search"})
    if not output: return pd.DataFrame()
    return pd.DataFrame(output).sort_values(["peer_score","origin"],ascending=[False,False]).head(20).reset_index(drop=True)

def to_excel(target, peers, sources):
    stream=io.BytesIO()
    with pd.ExcelWriter(stream,engine="xlsxwriter") as writer:
        pd.DataFrame([target]).to_excel(writer,sheet_name="Target Profile",index=False)
        peers.to_excel(writer,sheet_name="Candidate Peers",index=False)
        pd.DataFrame(sources).to_excel(writer,sheet_name="Target Sources",index=False)
    return stream.getvalue()

st.markdown('<div class="hero"><span class="tag">COMMERCIAL RISK 3 GROUP</span><h1>PEARL MI3 · Dynamic Peer Finder</h1><p>Candidate screening based on sector, business model, and business scale</p></div>',unsafe_allow_html=True)
with st.sidebar:
    st.subheader("Screening principle")
    st.write("**Eligibility:** same sector/subsector\n\n**Ranking:** 60% business model + 40% business scale")
    st.info("This tool finds candidate peers. CRM selects final peers and performs the financial analysis.")

company=st.text_input("Company name",value="PT Bukit Makmur Mandiri Utama",placeholder="Type any public company name")
c1,c2,c3=st.columns(3)
with c1: selected_sector=st.selectbox("Sector",["Auto Detect"]+list(TAXONOMY.keys()))
with c2:
    possible_models=["Auto Detect"] if selected_sector=="Auto Detect" else ["Auto Detect"]+list(TAXONOMY[selected_sector].keys())
    selected_model=st.selectbox("Subsector / business model",possible_models)
with c3: selected_scale=st.selectbox("Business scale",["Auto Detect","Large/National","Medium","Small/Regional"])

if st.button("Discover candidate peers",type="primary",use_container_width=True):
    if not company.strip(): st.warning("Enter a company name first."); st.stop()
    with st.spinner("Reading the target profile and discovering candidate companies..."):
        auto_sector,auto_model,auto_scale,description,sources,method=target_profile(company)
        sector=auto_sector if selected_sector=="Auto Detect" else selected_sector
        if sector=="Unclassified": st.error("Sector could not be detected. Select the sector manually and run again."); st.stop()
        model=auto_model if selected_model=="Auto Detect" and auto_model in TAXONOMY[sector] else (list(TAXONOMY[sector].keys())[0] if selected_model=="Auto Detect" else selected_model)
        scale=auto_scale if selected_scale=="Auto Detect" else selected_scale
        if scale=="Undetermined": scale="Medium"
        universe=build_universe(company,sector,model,scale)
        peers=score_candidates(company,sector,model,scale,universe)
        st.session_state.analysis=(sector,model,scale,description,sources,method,peers)

if "analysis" in st.session_state:
    sector,model,scale,description,sources,method,peers=st.session_state.analysis
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Sector",sector);m2.metric("Business model",model);m3.metric("Business scale",scale);m4.metric("Candidates",len(peers))
    t1,t2,t3,t4=st.tabs(["Candidate peers","Scoring basis","Public sources","CRM handoff"])
    with t1:
        if peers.empty: st.warning("No candidates found. Select sector, business model, and scale manually, then search again.")
        else:
            view=peers[["company_name","detected_business_model","detected_scale","peer_score","status","origin"]].copy();view.index=np.arange(1,len(view)+1)
            st.dataframe(view,use_container_width=True,column_config={"peer_score":st.column_config.ProgressColumn("Peer score",min_value=0,max_value=100,format="%.1f")})
            chart=px.bar(peers.head(10).sort_values("peer_score"),x="peer_score",y="company_name",orientation="h",color="status",labels={"peer_score":"Peer score","company_name":""})
            chart.update_layout(template="plotly_white",legend_title="");st.plotly_chart(chart,use_container_width=True)
    with t2:
        st.markdown("""**Eligibility filter**\n\nA candidate must be in the same sector or be returned by a targeted subsector search.\n\n**Peer score**\n\n- 60% business-model similarity: similarity of activities, products, services, and revenue drivers.\n- 40% scale similarity: Large/National, Medium, or Small/Regional.\n\nNo financial-performance score is used. CRM performs the financial comparison after selecting the candidates.""")
        if not peers.empty: st.dataframe(peers[["company_name","business_similarity","scale_similarity","matching_basis","source_url"]],use_container_width=True)
    with t3:
        st.write(f"Target identification: **{method}**")
        if sources:
            for source in sources: st.markdown(f"- [{source['title']}]({source['url']}) — {source['snippet'][:240]}")
        else: st.info("Public search was unavailable. Select the classifications manually and use the reference candidates.")
    with t4:
        shortlist=peers.head(7).company_name.tolist() if not peers.empty else []
        st.markdown("**Suggested CRM next steps**")
        st.write("1. Review and confirm the business comparability of each candidate.\n2. Select 3–7 final peers.\n3. Retrieve the latest audited/quarterly financial statements.\n4. Standardize currency, period, and consolidated/standalone basis.\n5. Perform the financial benchmark in the NAK.")
        if shortlist: st.write("Initial shortlist: "+", ".join(shortlist)+".")
        target={"company_name":company,"sector":sector,"business_model":model,"business_scale":scale,"screened_at":datetime.now(timezone.utc).isoformat()}
        st.download_button("Download candidate screening (Excel)",to_excel(target,peers,sources),file_name="PEARL_MI3_Candidate_Peers.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
else:
    st.info("Search any public company. If auto-detection is uncertain, select sector, business model, and scale manually.")

