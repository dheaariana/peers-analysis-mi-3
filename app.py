import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="PEARL Mining Services", page_icon="◈", layout="wide")
st.markdown("""
<style>
.stApp{background:#f3f6fb;color:#172033}.block-container{max-width:1320px;padding-top:1.2rem}
.topline{border-left:6px solid #f4b000;background:#07366d;color:white;padding:18px 22px;border-radius:5px 16px 16px 5px;margin-bottom:16px}
.topline h1{font-size:1.9rem;margin:0 0 4px}.topline p{margin:0;color:#d9e8fb}
.pill{display:inline-block;background:#e8f2ff;color:#06417f;padding:4px 9px;border-radius:99px;font-size:.78rem;font-weight:700}
[data-testid="stMetric"]{background:#fff;border:1px solid #dfe7f1;padding:12px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

DATA_PATH=Path(__file__).parent/"data"/"mining_services_database.csv"

FIELDS={
    "service_scope":("Service scope",25),
    "primary_commodity":("Commodity",15),
    "contract_profile":("Contract profile",15),
    "customer_profile":("Customer profile",15),
    "geography":("Operating geography",10),
    "operating_model":("Operating model",10),
    "revenue_driver":("Revenue driver",5),
    "capex_intensity":("Capex intensity",5),
}

NAK_QUESTIONS=[
    "Apa lingkup pekerjaan utama: full mining services atau hanya sebagian aktivitas?",
    "Apa komoditas dan karakteristik tambang yang dilayani?",
    "Bagaimana struktur tarif: per bcm, per ton, lump sum, atau cost-plus?",
    "Berapa tenor kontrak dan remaining contract period?",
    "Apakah terdapat minimum volume, escalation clause, atau fuel pass-through?",
    "Seberapa tinggi konsentrasi pelanggan dan site?",
    "Bagaimana ownership, usia, utilisasi, dan kebutuhan replacement fleet?",
    "Siapa yang menanggung fuel, spare parts, mobilization, dan site infrastructure?",
    "Bagaimana historical achievement volume terhadap target kontrak?",
    "Apa penyebab utama perbedaan margin terhadap peers?",
]

@st.cache_data(show_spinner=False)
def base_data():
    return pd.read_csv(DATA_PATH).fillna("Undetermined")

def tokens(value):
    return {x.strip().lower() for x in str(value).split(";") if x.strip() and x.strip().lower()!="undetermined"}

def similarity(a,b):
    left,right=tokens(a),tokens(b)
    if not left or not right:
        return 50.0
    return 100*len(left&right)/len(left|right)

def compare(target,candidate):
    detail=[];total=0
    for field,(label,weight) in FIELDS.items():
        score=similarity(target[field],candidate[field])
        total+=score*weight/100
        shared=tokens(target[field])&tokens(candidate[field])
        detail.append((label,score,", ".join(sorted(shared)) or "Needs confirmation"))
    return total,detail

def rank_peers(df,target_name):
    target=df[df.company_name==target_name].iloc[0]
    rows=[]
    for _,candidate in df[df.company_name!=target_name].iterrows():
        # Mining Contractor and Diversified Mining Services remain eligible, but exact model receives a bonus.
        score,detail=compare(target,candidate)
        model_bonus=5 if candidate.subsector==target.subsector else 0
        final=min(100,score+model_bonus)
        strongest=sorted(detail,key=lambda x:x[1],reverse=True)[:3]
        weakest=sorted(detail,key=lambda x:x[1])[:2]
        rows.append({
            **candidate.to_dict(),
            "peer_score":round(final,1),
            "comparable_because":"; ".join(f"{x[0]}: {x[2]}" for x in strongest),
            "key_differences":"; ".join(x[0] for x in weakest if x[1]<100) or "No material difference identified",
        })
    return pd.DataFrame(rows).sort_values("peer_score",ascending=False).reset_index(drop=True),target

def margin_explanation(target,peer):
    notes=[]
    if target.contract_profile!=peer.contract_profile:
        notes.append("Different contract mix may change pricing certainty, mobilization burden, and margin volatility.")
    if target.customer_concentration!=peer.customer_concentration:
        notes.append("Different customer concentration may affect bargaining power and contract-renewal risk.")
    if target.primary_commodity!=peer.primary_commodity:
        notes.append("Different commodity exposure may lead to different mine characteristics, equipment needs, and utilization.")
    if target.operating_model!=peer.operating_model:
        notes.append("Different fleet/subcontracting models may change fixed-cost intensity and operating leverage.")
    if target.geography!=peer.geography:
        notes.append("Different operating geography may affect labor, logistics, mobilization, and regulatory costs.")
    return notes or ["Public business-pattern data does not yet explain the margin difference; CRM validation is required."]

def excel_output(target,ranked):
    stream=io.BytesIO()
    with pd.ExcelWriter(stream,engine="xlsxwriter") as writer:
        pd.DataFrame([target]).to_excel(writer,sheet_name="Target",index=False)
        ranked.to_excel(writer,sheet_name="Peer Shortlist",index=False)
        pd.DataFrame({"NAK review question":NAK_QUESTIONS}).to_excel(writer,sheet_name="NAK Checklist",index=False)
    return stream.getvalue()

st.markdown('<div class="topline"><span class="pill">MULTI INDUSTRIES 3 · PILOT</span><h1>PEARL Mining Services</h1><p>Peer mapping and business-pattern analysis for mining contractors</p></div>',unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Purpose")
    st.write("Find operationally comparable mining-services companies and explain why their performance may differ.")
    st.warning("Use public/approved information only. Every profile remains subject to CRM validation.")
    uploaded=st.file_uploader("Use updated database (CSV)",type=["csv"])

df=base_data().copy()
if uploaded is not None:
    try:
        incoming=pd.read_csv(uploaded).fillna("Undetermined")
        missing=set(df.columns)-set(incoming.columns)
        if missing: st.error("Missing database columns: "+", ".join(sorted(missing)))
        else: df=incoming[df.columns];st.sidebar.success("Updated database loaded")
    except Exception as error:
        st.sidebar.error(f"Could not read CSV: {error}")

left,right=st.columns([3,1])
with left:
    target_name=st.selectbox("Target company",sorted(df.company_name.unique()),index=sorted(df.company_name.unique()).index("PT Bukit Makmur Mandiri Utama") if "PT Bukit Makmur Mandiri Utama" in sorted(df.company_name.unique()) else 0)
with right:
    peer_count=st.selectbox("Number of candidates",[3,5,7,10],index=2)

ranked,target=rank_peers(df,target_name)
shortlist=ranked.head(peer_count).copy()

m1,m2,m3,m4=st.columns(4)
m1.metric("Subsector",target.subsector)
m2.metric("Portfolio status",target.portfolio_status)
m3.metric("Candidates",len(shortlist))
m4.metric("Data status",target.verification_status)

tabs=st.tabs(["Peer shortlist","Business-pattern comparison","Why performance differs","NAK checklist","Maintain database"])

with tabs[0]:
    view=shortlist[["company_name","portfolio_status","subsector","peer_score","comparable_because","key_differences","verification_status"]].copy()
    view.index=np.arange(1,len(view)+1)
    st.dataframe(view,use_container_width=True,column_config={"peer_score":st.column_config.ProgressColumn("Comparability",min_value=0,max_value=100,format="%.1f")},height=410)
    chart=px.bar(shortlist.sort_values("peer_score"),x="peer_score",y="company_name",orientation="h",color="portfolio_status",labels={"peer_score":"Comparability score","company_name":""},color_discrete_sequence=["#0b4d8f","#e6a700","#5e7490"])
    chart.update_layout(template="plotly_white",legend_title="")
    st.plotly_chart(chart,use_container_width=True)

with tabs[1]:
    selected_peer=st.selectbox("Compare with",shortlist.company_name.tolist(),key="compare_peer")
    peer=shortlist[shortlist.company_name==selected_peer].iloc[0]
    rows=[]
    for field,(label,weight) in FIELDS.items():
        rows.append({"Parameter":label,"Target":target[field],"Peer":peer[field],"Weight":f"{weight}%","Similarity":f"{similarity(target[field],peer[field]):.0f}%"})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption("The score indicates business-pattern comparability, not credit quality or financial performance.")

with tabs[2]:
    selected_peer_2=st.selectbox("Peer for diagnostic",shortlist.company_name.tolist(),key="diagnostic_peer")
    peer=shortlist[shortlist.company_name==selected_peer_2].iloc[0]
    st.markdown(f"#### Potential reasons {target_name} and {selected_peer_2} may show different margins")
    for note in margin_explanation(target,peer): st.write("- "+note)
    st.markdown("#### Information CRM should confirm")
    st.write("- Actual contract mix and tariff mechanism\n- Volume achievement and fleet utilization\n- Fuel and spare-parts cost allocation\n- Mobilization and infrastructure responsibility\n- Customer/site concentration\n- One-off claims, penalties, or project ramp-up")

with tabs[3]:
    for number,question in enumerate(NAK_QUESTIONS,1): st.checkbox(f"{number}. {question}",key=f"q{number}")
    st.download_button("Download peer analysis (Excel)",excel_output(target.to_dict(),shortlist),file_name="PEARL_Mining_Services_Peer_Analysis.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

with tabs[4]:
    st.write("Edit the table, download the result, then replace the CSV in the GitHub `data` folder. This keeps the database separate from the application code.")
    edited=st.data_editor(df,use_container_width=True,num_rows="dynamic",height=420)
    st.download_button("Download updated database",edited.to_csv(index=False).encode("utf-8"),file_name="mining_services_database.csv",mime="text/csv",use_container_width=True)
    st.download_button("Download blank template",pd.DataFrame(columns=df.columns).to_csv(index=False).encode("utf-8"),file_name="mining_services_template.csv",mime="text/csv",use_container_width=True)

