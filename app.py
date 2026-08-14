import os
import re
import statistics
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import streamlit as st

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


# =========================================================
# INSTÄLLNINGAR
# =========================================================

st.set_page_config(
    page_title="Golf Deal Analyzer V3",
    page_icon="⛳",
    layout="wide"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

KNOWN_BRANDS = [
    "Titleist",
    "TaylorMade",
    "Callaway",
    "Ping",
    "Cobra",
    "Mizuno",
    "Srixon",
    "Cleveland",
    "Wilson",
    "Bridgestone",
    "Odyssey",
    "Scotty Cameron",
    "PXG",
    "Honma"
]

CLUB_TYPES = [
    "driver",
    "fairway wood",
    "hybrid",
    "iron",
    "wedge",
    "putter",
    "golfbag",
    "golf bag"
]

BAD_TERMS = [
    "ny",
    "new",
    "nypris",
    "ordinarie pris",
    "rek pris",
    "retail",
    "msrp"
]


# =========================================================
# HJÄLPFUNKTIONER
# =========================================================

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize(text):
    text = clean(text).lower()
    text = text.replace("–", "-").replace("—", "-")
    return text


def money(text):
    if not text:
        return None

    patterns = [
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{3,6})\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*:-",
        r"(?<!\d)(\d{3,6})\s*:-",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            try:
                return float(
                    re.sub(r"[ .]", "", match.group(1))
                )
            except ValueError:
                pass

    return None


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = ""

    if soup.title:
        title = clean(
            soup.title.get_text(" ")
        )

    meta = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    description = ""

    if meta:
        description = clean(
            meta.get("content", "")
        )

    body = clean(
        soup.get_text(" ", strip=True)
    )

    return title, description, body


def get_tavily_key():
    """
    Försöker först läsa Streamlit Secrets.
    Fungerar även med environment variable.
    """

    try:
        key = st.secrets["TAVILY_API_KEY"]

        if key:
            return str(key).strip()
    except Exception:
        pass

    return os.getenv(
        "TAVILY_API_KEY",
        ""
    ).strip()


def identify_product(text):
    """
    Försöker identifiera produktens viktigaste egenskaper.
    """

    low = normalize(text)

    brands = []

    for brand in KNOWN_BRANDS:
        if brand.lower() in low:
            brands.append(brand)

    club_types = []

    for club_type in CLUB_TYPES:
        if club_type in low:
            club_types.append(club_type)

    # Hämta några modellord efter varumärket
    model_words = []

    for brand in brands:
        pattern = re.escape(brand) + r"\s+([A-Za-z0-9\- ]{2,35})"

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:
            candidate = clean(
                match.group(1)
            )

            candidate = re.split(
                r"\b(?:kr|sek|pris|begagnad|begagnat)\b",
                candidate,
                flags=re.I
            )[0]

            model_words.append(candidate.strip())

    # Årsmodell
    year_match = re.search(
        r"\b(20(?:19|20|21|22|23|24|25|26))\b",
        text
    )

    year = year_match.group(1) if year_match else None

    # Setstorlek
    set_match = re.search(
        r"\b(\d+)\s*[-–]\s*(\d+)\b",
        text
    )

    set_range = None

    if set_match:
        set_range = (
            set_match.group(1)
            + "-"
            + set_match.group(2)
        )

    return {
        "brands": brands,
        "types": club_types,
        "models": model_words,
        "year": year,
        "set_range": set_range
    }


# =========================================================
# TAVILY
# =========================================================

def tavily_search(query, max_results=8):
    key = get_tavily_key()

    if not key:
        return []

    if TavilyClient is None:
        return []

    client = TavilyClient(
        api_key=key
    )

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results
    )

    return response.get(
        "results",
        []
    )


# =========================================================
# JÄMFÖRELSEOBJEKT
# =========================================================

def build_search_queries(product):
    """
    Flera sökningar är bättre än en enda bred sökning.
    """

    brand = (
        product["brands"][0]
        if product["brands"]
        else ""
    )

    model = (
        product["models"][0]
        if product["models"]
        else ""
    )

    club_type = (
        product["types"][0]
        if product["types"]
        else "golf"
    )

    year = product["year"] or ""

    queries = []

    base = clean(
        f"{brand} {model} {year}"
    )

    queries.append(
        f'"{base}" begagnad pris Sverige'
    )

    queries.append(
        f'{base} begagnat golf pris'
    )

    queries.append(
        f'{base} säljes begagnad'
    )

    if club_type:
        queries.append(
            f'{base} {club_type} begagnad Sverige'
        )

    return list(dict.fromkeys(queries))


def similarity_score(product, result):
    """
    Ger varje träff en relevanspoäng.
    """

    text = normalize(
        result.get("title", "")
        + " "
        + result.get("content", "")
    )

    score = 0

    # Varumärke
    for brand in product["brands"]:
        if brand.lower() in text:
            score += 30

    # Modell
    for model in product["models"]:
        words = [
            w for w in normalize(model).split()
            if len(w) >= 2
        ]

        for word in words:
            if word in text:
                score += 12

    # Typ
    for club_type in product["types"]:
        if club_type in text:
            score += 10

    # År
    if product["year"]:
        if product["year"] in text:
            score += 15
        else:
            # Annat år är inte automatiskt fel,
            # men får inte full poäng.
            score -= 5

    # Begagnat
    used_words = [
        "begagnad",
        "begagnat",
        "begagnade",
        "använd",
        "använt",
        "used"
    ]

    if any(word in text for word in used_words):
        score += 15

    # Nya produkter ska straffas
    new_words = [
        "ny",
        "new",
        "nypris",
        "retail",
        "msrp"
    ]

    if any(
        re.search(r"\b" + re.escape(word) + r"\b", text)
        for word in new_words
    ):
        score -= 20

    return score


def get_comps(product):
    """
    Söker flera gånger och filtrerar resultat.
    """

    queries = build_search_queries(product)

    all_results = []

    for query in queries:

        try:
            results = tavily_search(
                query,
                max_results=8
            )
        except Exception as e:
            st.error(
                f"Tavily-fel: {e}"
            )
            return []

        for result in results:

            title = clean(
                result.get("title", "")
            )

            content = clean(
                result.get("content", "")
            )

            combined = (
                title
                + " "
                + content
            )

            price = money(combined)

            if not price:
                continue

            # Golfpriser under 100 kr är nästan
            # alltid irrelevanta.
            if price < 100:
                continue

            relevance = similarity_score(
                product,
                result
            )

            all_results.append({
                "title": title,
                "price": price,
                "url": result.get(
                    "url",
                    ""
                ),
                "source": urlparse(
                    result.get(
                        "url",
                        ""
                    )
                ).netloc,
                "snippet": content[:500],
                "relevance": relevance
            })

    # Ta bort dubbletter
    unique = {}

    for item in all_results:

        key = (
            normalize(item["title"]),
            item["price"]
        )

        if key not in unique:
            unique[key] = item

    comps = list(
        unique.values()
    )

    # Endast relevanta resultat
    comps = [
        x for x in comps
        if x["relevance"] >= 25
    ]

    # Sortera efter relevans
    comps.sort(
        key=lambda x: x["relevance"],
        reverse=True
    )

    return comps[:20]


# =========================================================
# MARKNADSVÄRDE
# =========================================================

def calculate_market_value(comps):
    """
    Beräknar ett konservativt värde.
    """

    prices = [
        x["price"]
        for x in comps
        if x["price"]
    ]

    if len(prices) < 2:
        return None, "Låg", prices

    prices.sort()

    # Ta bort extrema outliers
    if len(prices) >= 5:

        q1 = statistics.quantiles(
            prices,
            n=4
        )[0]

        q3 = statistics.quantiles(
            prices,
            n=4
        )[2]

        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        filtered = [
            p for p in prices
            if lower <= p <= upper
        ]

        if len(filtered) >= 3:
            prices = filtered

    median = statistics.median(
        prices
    )

    # Konservativt marknadsvärde:
    # medianen istället för max eller enkelt snitt.
    value = round(
        median / 100
    ) * 100

    if len(prices) >= 8:
        confidence = "Hög"
    elif len(prices) >= 4:
        confidence = "Medel"
    else:
        confidence = "Låg"

    return value, confidence, prices


# =========================================================
# DEAL SCORE
# =========================================================

def calculate_score(
    asking_price,
    market_value,
    confidence,
    comparable_count
):

    if not asking_price or not market_value:
        return None

    discount = (
        market_value - asking_price
    ) / market_value

    score = 50

    # Prisfördel
    score += discount * 100

    # Datakvalitet
    if confidence == "Hög":
        score += 8
    elif confidence == "Medel":
        score += 3
    else:
        score -= 8

    # Antal comps
    if comparable_count >= 8:
        score += 5
    elif comparable_count < 3:
        score -= 10

    return max(
        0,
        min(
            100,
            round(score)
        )
    )


def verdict(score):

    if score is None:
        return "⚪ UNDERLAG SAKNAS"

    if score >= 85:
        return "🟢 STARKT KÖP"

    if score >= 70:
        return "🟢 KÖP"

    if score >= 55:
        return "🟡 KANSKE"

    return "🔴 SKIPPA"


# =========================================================
# APP
# =========================================================

st.title(
    "⛳ Golf Deal Analyzer V3"
)

st.write(
    "Analysera begagnad golfutrustning "
    "med jämförbara priser och en "
    "konservativ återförsäljningskalkyl."
)


with st.sidebar:

    st.header(
        "⚙️ Inställningar"
    )

    resale_fee = st.number_input(
        "Försäljningskostnad (%)",
        min_value=0.0,
        max_value=30.0,
        value=5.0,
        step=0.5
    )

    shipping = st.number_input(
        "Frakt/övriga kostnader (kr)",
        min_value=0.0,
        max_value=2000.0,
        value=150.0,
        step=50.0
    )

    target_margin = st.number_input(
        "Önskad säkerhetsmarginal (%)",
        min_value=0.0,
        max_value=50.0,
        value=15.0,
        step=1.0
    )


url = st.text_input(
    "1. Annonslänk",
    placeholder="https://..."
)

manual = st.text_area(
    "2. Eller klistra in annonsens titel + beskrivning",
    height=150
)


if st.button(
    "🔎 Analysera fynd",
    type="primary"
):

    # -----------------------------------------
    # LÄS ANNONS
    # -----------------------------------------

    if not url.strip() and not manual.strip():
        st.error(
            "Lägg in en annonslänk eller "
            "klistra in annonsens text."
        )
        st.stop()

    try:

        if manual.strip():

            title = manual[:250]
            description = manual
            body = ""

        else:

            with st.spinner(
                "📄 Läser annonsen..."
            ):

                title, description, body = fetch(
                    url.strip()
                )

    except Exception as e:

        st.error(
            f"Kunde inte läsa annonsen: {e}"
        )

        st.stop()


    # -----------------------------------------
    # IDENTIFIERA PRODUKT
    # -----------------------------------------

    full_text = clean(
        " ".join(
            [
                title,
                description,
                body
            ]
        )
    )

    product = identify_product(
        full_text
    )

    asking_price = money(
        full_text
    )


    st.subheader(
        "🔎 Identifierat objekt"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Annonspris",
            f"{asking_price:,.0f} kr"
            if asking_price
            else "Ej hittat"
        )

    with col2:
        st.write(
            "**Märke**"
        )

        st.write(
            ", ".join(
                product["brands"]
            )
            if product["brands"]
            else "Ej identifierat"
        )

    with col3:
        st.write(
            "**Typ**"
        )

        st.write(
            ", ".join(
                product["types"]
            )
            if product["types"]
            else "Ej identifierad"
        )

    with col4:
        st.write(
            "**År**"
        )

        st.write(
            product["year"]
            or "Ej identifierat"
        )


    if product["models"]:

        st.write(
            "**Modell:** "
            + ", ".join(
                product["models"]
            )
        )

    if product["set_range"]:

        st.write(
            "**Set:** "
            + product["set_range"]
        )


    # -----------------------------------------
    # TAVILY
    # -----------------------------------------

    with st.spinner(
        "🌐 Söker efter relevanta jämförelseobjekt..."
    ):

        comps = get_comps(
            product
        )


    # -----------------------------------------
    # MARKNADSVÄRDE
    # -----------------------------------------

    market_value, confidence, used_prices = (
        calculate_market_value(
            comps
        )
    )


    # -----------------------------------------
    # KALKYL
    # -----------------------------------------

    if market_value:

        # Vi räknar inte med att du alltid får
        # exakt medianpriset vid försäljning.
        realistic_sale_price = round(
            market_value * 0.95 / 100
        ) * 100

        fee = (
            realistic_sale_price
            * resale_fee
            / 100
        )

        net_sale = (
            realistic_sale_price
            - fee
            - shipping
        )

        if asking_price:

            profit = (
                net_sale
                - asking_price
            )

            max_buy = (
                net_sale
                * (1 - target_margin / 100)
            )

        else:

            profit = None
            max_buy = None

    else:

        realistic_sale_price = None
        fee = None
        net_sale = None
        profit = None
        max_buy = None


    # -----------------------------------------
    # SCORE
    # -----------------------------------------

    deal_score = calculate_score(
        asking_price,
        market_value,
        confidence,
        len(comps)
    )


    st.divider()

    st.subheader(
        "💰 Deal-analys"
    )


    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric(
            "Marknadsvärde",
            f"{market_value:,.0f} kr"
            if market_value
            else "—"
        )

    with c2:
        st.metric(
            "Realistiskt säljpris",
            f"{realistic_sale_price:,.0f} kr"
            if realistic_sale_price
            else "—"
        )

    with c3:
        st.metric(
            "Netto",
            f"{net_sale:,.0f} kr"
            if net_sale
            else "—"
        )

    with c4:
        st.metric(
            "Vinst",
            f"{profit:,.0f} kr"
            if profit is not None
            else "—"
        )

    with c5:
        st.metric(
            "Max inköpspris",
            f"{max_buy:,.0f} kr"
            if max_buy
            else "—"
        )

    with c6:
        st.metric(
            "Deal Score",
            f"{deal_score}/100"
            if deal_score is not None
            else "—"
        )


    st.markdown(
        f"# {verdict(deal_score)}"
    )


    # -----------------------------------------
    # KONFIDENS
    # -----------------------------------------

    if confidence == "Hög":

        st.success(
            f"📊 Hög konfidens — "
            f"{len(comps)} relevanta jämförelseobjekt hittades."
        )

    elif confidence == "Medel":

        st.warning(
            f"📊 Medelkonfidens — "
            f"{len(comps)} relevanta jämförelseobjekt hittades."
        )

    else:

        st.error(
            f"📊 Låg konfidens — "
            f"bara {len(comps)} relevanta jämförelseobjekt hittades."
        )


    # -----------------------------------------
    # BESLUT
    # -----------------------------------------

    if (
        asking_price
        and max_buy
    ):

        difference = (
            asking_price - max_buy
        )

        if asking_price <= max_buy:

            st.success(
                f"✅ Annonspriset ligger "
                f"{abs(difference):,.0f} kr under "
                f"ditt rekommenderade maxpris."
            )

        else:

            st.warning(
                f"⚠️ Annonspriset ligger "
                f"{difference:,.0f} kr över "
                f"ditt rekommenderade maxpris."
            )


    # -----------------------------------------
    # COMPS
    # -----------------------------------------

    st.divider()

    st.subheader(
        "🔍 Jämförelseobjekt som användes"
    )


    if comps:

        rows = []

        for item in comps:

            rows.append(
                {
                    "Pris": f"{item['price']:,.0f} kr",
                    "Relevans": item["relevance"],
                    "Objekt": item["title"],
                    "Källa": item["source"],
                    "Länk": item["url"],
                    "Utdrag": item["snippet"]
                }
            )

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.error(
            "❌ Hittade inga tillräckligt "
            "relevanta jämförelseobjekt."
        )


    # -----------------------------------------
    # TRANSPARENS
    # -----------------------------------------

    with st.expander(
        "📊 Visa hur värdet beräknades"
    ):

        st.write(
            "**Priser som användes:**"
        )

        if used_prices:

            st.write(
                ", ".join(
                    f"{p:,.0f} kr"
                    for p in used_prices
                )
            )

        else:

            st.write(
                "Inga tillräckliga priser."
            )

        st.write(
            f"**Konfidens:** {confidence}"
        )

        st.write(
            f"**Antal relevanta comps:** "
            f"{len(comps)}"
        )

        st.write(
            f"**Försäljningsavgift:** "
            f"{resale_fee:.1f}%"
        )

        st.write(
            f"**Frakt/övriga kostnader:** "
            f"{shipping:,.0f} kr"
        )

        st.write(
            f"**Önskad säkerhetsmarginal:** "
            f"{target_margin:.1f}%"
        )


    with st.expander(
        "📄 Annonsdata"
    ):

        st.write(
            full_text[:10000]
        )
