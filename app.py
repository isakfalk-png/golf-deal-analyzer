import os, re, json, math
from dataclasses import dataclass
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import streamlit as st

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

st.set_page_config(page_title="Golf Deal Analyzer V2", page_icon="⛳", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/139 Safari/537.36"}

KNOWN_BRANDS = [
    "Titleist","TaylorMade","Callaway","Ping","Cobra","Mizuno","Srixon",
    "Cleveland","Wilson","Bridgestone","Odyssey","Scotty Cameron","PXG","Honma"
]
CLUB_TYPES = ["driver","fairway wood","hybrid","iron","wedge","putter","bag"]

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def money(s):
    if not s: return None
    pats = [
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{3,6})\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*:-",
    ]
    for p in pats:
        m = re.search(p, s, re.I)
        if m:
            try: return float(re.sub(r"[ .]","",m.group(1)))
            except: pass
    return None

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = clean(soup.title.get_text(" ")) if soup.title else ""
    meta = soup.find("meta", attrs={"name":"description"})
    desc = clean(meta.get("content","")) if meta else ""
    body = clean(soup.get_text(" ", strip=True))
    return title, desc, body

def identify(text):
    low = text.lower()
    brands = [b for b in KNOWN_BRANDS if b.lower() in low]
    types = [t for t in CLUB_TYPES if t in low]
    return brands, types

def web_comps(query, n=10):
    key = os.getenv("TAVILY_API_KEY","").strip()
    if not key or TavilyClient is None:
        return []
    client = TavilyClient(api_key=key)
    res = client.search(
        query=query + " begagnad golf Sverige pris",
        search_depth="advanced",
        max_results=n
    )
    out=[]
    for x in res.get("results",[]):
        text=clean((x.get("title","")+" "+x.get("content","")))
        out.append({
            "title":clean(x.get("title","")),
            "price":money(text),
            "url":x.get("url",""),
            "source":urlparse(x.get("url","")).netloc,
            "snippet":clean(x.get("content",""))[:350]
        })
    return out

def robust_value(items):
    vals=sorted([x["price"] for x in items if x["price"] and x["price"] >= 100])
    if len(vals) < 2: return None
    if len(vals) >= 6: vals=vals[1:-1]
    return round(sum(vals)/len(vals)/100)*100

def score(price, value, liquidity=0.0):
    if not price or not value: return None
    discount=max(-0.5,min(0.7,(value-price)/value))
    s=50+discount*120+liquidity*10
    return max(0,min(100,round(s)))

def verdict(s):
    if s is None: return "⚪ UNDERLAG SAKNAS"
    if s>=82: return "🟢 STARKT KÖP"
    if s>=68: return "🟢 KÖP"
    if s>=52: return "🟡 KANSKE"
    return "🔴 SKIPPA"

st.title("⛳ Golf Deal Analyzer V2")
st.write("Analysera en annons med fokus på återförsäljning.")

url=st.text_input("1. Klistra in annonslänk", placeholder="https://www.blocket.se/annons/...")
manual=st.text_area("2. Om sidan blockeras: klistra in titel + beskrivning här", height=120)

c1,c2,c3=st.columns(3)
with c1: resale_fee=st.number_input("Försäljningskostnad/avgift (%)",0.0,30.0,5.0,0.5)
with c2: shipping=st.number_input("Frakt/övriga kostnader (kr)",0.0,2000.0,150.0,50.0)
with c3: target_margin=st.number_input("Önskad säkerhetsmarginal (%)",0.0,50.0,15.0,1.0)

if st.button("🔎 Analysera fynd", type="primary"):
    try:
        if manual.strip():
            title,desc,body = manual[:200],manual,""
        elif url.strip():
            title,desc,body=fetch(url.strip())
        else:
            st.error("Lägg in en länk eller annonsens text.")
            st.stop()
    except Exception as e:
        st.error(f"Kunde inte läsa annonsen: {e}")
        st.stop()

    text=clean(" ".join([title,desc,body]))
    brands,types=identify(text)
    query=(title+" "+desc)[:500]

    st.subheader("Identifierat objekt")
    a,b,c=st.columns(3)
    a.metric("Annonspris", f"{money(text):,.0f} kr" if money(text) else "Ej hittat")
    b.write("**Märke:** "+(", ".join(brands) if brands else "Ej säkert identifierat"))
    c.write("**Klubbtyper:** "+(", ".join(types) if types else "Ej säkert identifierat"))
    st.write("**Titel:**",title)

    with st.spinner("Söker jämförbara priser..."):
        comps=web_comps(query)

    value=robust_value(comps)
    price=money(text)

    # A conservative resale estimate: market value minus room for negotiation.
    resale = round(value*0.96/100)*100 if value else None
    fees=(resale*(resale_fee/100)) if resale else 0
    net=resale-fees-shipping if resale else None
    profit=(net-price) if net and price else None
    max_buy=(net*(1-target_margin/100)) if net else None
    s=score(price,value,0.15 if len(comps)>=6 else 0)

    st.divider()
    st.subheader("💰 Återförsäljningskalkyl")
    cols=st.columns(6)
    cols[0].metric("Marknadsvärde",f"{value:,.0f} kr" if value else "—")
    cols[1].metric("Realistiskt säljpris",f"{resale:,.0f} kr" if resale else "—")
    cols[2].metric("Netto efter kostnader",f"{net:,.0f} kr" if net else "—")
    cols[3].metric("Förväntad vinst",f"{profit:,.0f} kr" if profit is not None else "—")
    cols[4].metric("Rekommenderat maxpris",f"{max_buy:,.0f} kr" if max_buy else "—")
    cols[5].metric("Deal Score",f"{s}/100" if s is not None else "—")

    st.markdown(f"# {verdict(s)}")
    if profit is not None and max_buy is not None:
        if price <= max_buy:
            st.success(f"Priset ligger under ditt beräknade maxpris. Det finns utrymme för vidareförsäljning.")
        else:
            st.warning(f"Annonspriset ligger {price-max_buy:,.0f} kr över rekommenderat maxpris.")
    st.caption("Värderingen är en uppskattning. Kontrollera alltid exakt modell, antal klubbor, skaft/flex, loft, skick och att jämförelseobjekten verkligen är jämförbara.")

    st.subheader("🔍 Jämförbara objekt")
    if comps:
        rows=[]
        for x in comps:
            rows.append({
                "Pris":f'{x["price"]:,.0f} kr' if x["price"] else "—",
                "Objekt":x["title"],
                "Källa":x["source"],
                "Länk":x["url"],
                "Utdrag":x["snippet"]
            })
        st.dataframe(rows,use_container_width=True,hide_index=True)
    else:
        st.info("Ingen webbsökning tillgänglig. Lägg till TAVILY_API_KEY i appens secrets.")

    with st.expander("Annonsdata"):
        st.write(text[:8000])
