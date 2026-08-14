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
# APP
# =========================================================

st.set_page_config(
    page_title="Golf Deal Analyzer",
    page_icon="⛳",
    layout="wide"
)


# =========================================================
# KONSTANTER
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/139 Safari/537.36"
    )
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
    "fairway",
    "hybrid",
    "iron",
    "irons",
    "wedge",
    "putter",
    "järnset",
    "järnklubbor",
    "golfklubba",
    "golfklubbor"
]


EXCLUDED_TERMS = [
    "golfbil",
    "golf bil",
    "golfcart",
    "golf cart",
    "golfcar",
    "golf car",
    "golfvagn",
    "golf vagn",
    "golf buggy",
    "golf trolley",
    "club car",
    "ezgo",
    "e-z-go",
    "yamaha golf cart"
]


USED_WORDS = [
    "begagnad",
    "begagnat",
    "begagnade",
    "använd",
    "använt",
    "used",
    "second hand"
]


NEW_WORDS = [
    "nypris",
    "ny produkt",
    "helt ny",
    "oöppnad",
    "new",
    "retail",
    "msrp"
]


CONDITION_SCORES = {
    "ny/oöppnad": 1.00,
    "nyskick": 0.97,
    "mycket bra": 0.93,
    "bra": 0.88,
    "normalt bruksslitage": 0.80,
    "slitet": 0.68,
    "okänt": 0.82
}


# =========================================================
# TEXT / PRIS
# =========================================================

def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def normalize(text):
    return clean(text).lower()


def money(text):
    if not text:
        return None

    patterns = [
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{3,6})\s*(?:kr|sek)\b",
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+)\s*:-",
        r"(?<!\d)(\d{3,6})\s*:-"
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:
            try:
                return float(
                    re.sub(
                        r"[ .]",
                        "",
                        match.group(1)
                    )
                )
            except ValueError:
                pass

    return None


# =========================================================
# ANNONS
# =========================================================

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
        attrs={
            "name": "description"
        }
    )

    description = ""

    if meta:
        description = clean(
            meta.get(
                "content",
                ""
            )
        )

    body = clean(
        soup.get_text(
            " ",
            strip=True
        )
    )

    return (
        title,
        description,
        body
    )


# =========================================================
# TAVILY KEY
# =========================================================

def get_tavily_key():

    try:

        key = st.secrets[
            "TAVILY_API_KEY"
        ]

        if key:
            return str(key).strip()

    except Exception:
        pass

    return os.getenv(
        "TAVILY_API_KEY",
        ""
    ).strip()


# =========================================================
# PRODUKTIDENTIFIERING
# =========================================================

def extract_year(text):

    match = re.search(
        r"\b(20(?:19|20|21|22|23|24|25|26))\b",
        text
    )

    if match:
        return match.group(1)

    return None


def extract_number_of_clubs(text):

    low = normalize(text)

    # Exempel:
    # "6 klubbor"
    # "6 clubs"
    # "6 st"
    patterns = [
        r"\b(\d{1,2})\s*(?:st|stycken|klubbor|clubs)\b",
        r"\b(\d{1,2})\s*clubs\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            low
        )

        if match:

            number = int(
                match.group(1)
            )

            if 1 <= number <= 15:
                return number

    # Exempel 5-PW
    match = re.search(
        r"\b([3-9])\s*[-–]\s*(pw|gw|aw)\b",
        low,
        re.I
    )

    if match:

        start = int(
            match.group(1)
        )

        end = 10

        # PW räknas här som sista klubban.
        # 5-PW ≈ 6 klubbor.
        return max(
            1,
            end - start + 1
        )

    return None


def extract_set(text):

    low = normalize(text)

    patterns = [
        r"\b([3-9])\s*[-–]\s*(pw|gw|aw)\b",
        r"\b([3-9])\s*[-–]\s*([9])\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            low,
            re.I
        )

        if match:

            return (
                match.group(1)
                + "-"
                + match.group(2).upper()
            )

    return None


def extract_flex(text):

    low = normalize(text)

    flexes = [
        "x-stiff",
        "x stiff",
        "extra stiff",
        "stiff",
        "regular",
        "senior",
        "ladies",
        "lite"
    ]

    for flex in flexes:

        if flex in low:

            return flex

    return None


def extract_shaft(text):

    low = normalize(text)

    shaft_keywords = [
        "project x",
        "kbs",
        "dynamic gold",
        "modus",
        "tensei",
        "ventus",
        "hzrdus",
        "diamana",
        "aldila"
    ]

    for shaft in shaft_keywords:

        if shaft in low:

            return shaft

    return None


def extract_condition(text):

    low = normalize(text)

    if (
        "oöppnad" in low
        or "helt ny" in low
    ):
        return "ny/oöppnad"

    if (
        "nyskick" in low
        or "som ny" in low
    ):
        return "nyskick"

    if (
        "mycket bra skick" in low
        or "mycket fint skick" in low
    ):
        return "mycket bra"

    if (
        "bra skick" in low
        or "fint skick" in low
    ):
        return "bra"

    if (
        "bruksslitage" in low
        or "normalt slitage" in low
    ):
        return "normalt bruksslitage"

    if (
        "slitet" in low
        or "slitage" in low
        or "skador" in low
    ):
        return "slitet"

    return "okänt"


def extract_brand(text):

    low = normalize(text)

    for brand in KNOWN_BRANDS:

        if brand.lower() in low:

            return brand

    return None


def extract_club_type(text):

    low = normalize(text)

    # Prioritera specifika typer
    if "fairway wood" in low:
        return "fairway wood"

    if "hybrid" in low:
        return "hybrid"

    if "driver" in low:
        return "driver"

    if (
        "wedge" in low
        or "wedges" in low
    ):
        return "wedge"

    if "putter" in low:
        return "putter"

    if (
        "järnset" in low
        or "järnklubbor" in low
        or "irons" in low
        or "iron set" in low
    ):
        return "iron"

    if (
        "golfklubba" in low
        or "golfklubbor" in low
    ):
        return "golfklubba"

    return None


def extract_model(text, brand):

    if not brand:
        return None

    # Försök hitta text efter varumärket.
    pattern = (
        re.escape(brand)
        + r"\s+([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+){0,3})"
    )

    matches = re.findall(
        pattern,
        text,
        re.I
    )

    if not matches:
        return None

    candidate = clean(
        matches[0]
    )

    # Ta bort vanliga saker som inte är modellnamn.
    candidate = re.split(
        r"\b(?:kr|sek|pris|"
        r"begagnad|begagnat|"
        r"golfklubba|golfklubbor|"
        r"stiff|regular|senior)\b",
        candidate,
        flags=re.I
    )[0]

    return clean(
        candidate
    )


def identify_product(text):

    brand = extract_brand(
        text
    )

    model = extract_model(
        text,
        brand
    )

    return {
        "brand": brand,
        "model": model,
        "year": extract_year(text),
        "club_count": extract_number_of_clubs(text),
        "set": extract_set(text),
        "flex": extract_flex(text),
        "shaft": extract_shaft(text),
        "condition": extract_condition(text),
        "club_type": extract_club_type(text)
    }


# =========================================================
# TAVILY SEARCH
# =========================================================

def tavily_search(
    query,
    max_results=8
):

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
# SÖKFRÅGOR
# =========================================================

def build_search_queries(product):

    brand = product["brand"] or ""
    model = product["model"] or ""
    year = product["year"] or ""
    club_type = product["club_type"] or "golfklubba"

    base = clean(
        f"{brand} {model} {year}"
    )

    queries = [

        f'"{base}" "{club_type}" begagnad pris',

        f'"{base}" begagnade golfklubbor pris',

        f'"{base}" säljes golfklubbor',

        f'"{base}" begagnad Sverige',

        f'"{base}" Blocket',

        f'"{base}" Tradera',

        f'"{base}" Golfbidder'
    ]

    return list(
        dict.fromkeys(
            queries
        )
    )


# =========================================================
# COMPARABLE MATCHING
# =========================================================

def condition_similarity(
    target,
    comp
):

    if target == "okänt":
        return 0

    if comp == "okänt":
        return 0

    if target == comp:
        return 15

    # Närliggande skick
    good_conditions = {
        "ny/oöppnad": 4,
        "nyskick": 3,
        "mycket bra": 2,
        "bra": 1,
        "normalt bruksslitage": 0,
        "slitet": -2
    }

    t = good_conditions.get(
        target,
        0
    )

    c = good_conditions.get(
        comp,
        0
    )

    difference = abs(
        t - c
    )

    if difference == 1:
        return 8

    if difference == 2:
        return 3

    return -5


def comparable_score(
    product,
    result
):

    text = normalize(
        result.get("title", "")
        + " "
        + result.get("content", "")
    )

    # -----------------------------------------------------
    # GOLFBILAR = DIREKT BORT
    # -----------------------------------------------------

    for term in EXCLUDED_TERMS:

        if term in text:
            return -100, {}

    score = 0


    # -----------------------------------------------------
    # EXTRAHERA COMPS EGEN DATA
    # -----------------------------------------------------

    comp = identify_product(
        text
    )


    # -----------------------------------------------------
    # EXAKT MÄRKE
    # -----------------------------------------------------

    if (
        product["brand"]
        and comp["brand"]
    ):

        if (
            product["brand"].lower()
            == comp["brand"].lower()
        ):
            score += 30

        else:
            return -50, comp


    # -----------------------------------------------------
    # EXAKT MODELL
    # -----------------------------------------------------

    if (
        product["model"]
        and comp["model"]
    ):

        target_model = normalize(
            product["model"]
        )

        comp_model = normalize(
            comp["model"]
        )

        if (
            target_model
            == comp_model
        ):

            score += 35

        elif (
            target_model in text
        ):

            score += 25

        else:

            score -= 15


    # Om modellen finns i texten direkt
    if (
        product["model"]
        and normalize(
            product["model"]
        ) in text
    ):

        score += 15


    # -----------------------------------------------------
    # ÅR
    # -----------------------------------------------------

    if product["year"]:

        if (
            product["year"]
            in text
        ):

            score += 20

        else:

            score -= 8


    # -----------------------------------------------------
    # KLUBBTYP
    # -----------------------------------------------------

    if (
        product["club_type"]
        and comp["club_type"]
    ):

        if (
            product["club_type"]
            == comp["club_type"]
        ):

            score += 15

        else:

            score -= 10


    # -----------------------------------------------------
    # ANTAL KLUBBOR
    # -----------------------------------------------------

    if product["club_count"]:

        if comp["club_count"]:

            difference = abs(
                product["club_count"]
                - comp["club_count"]
            )

            if difference == 0:

                score += 25

            elif difference == 1:

                score += 15

            elif difference == 2:

                score += 5

            else:

                score -= 15

        else:

            # Vi vet inte antal i comp
            score -= 3


    # -----------------------------------------------------
    # SET
    # -----------------------------------------------------

    if product["set"]:

        if comp["set"]:

            if (
                product["set"].lower()
                == comp["set"].lower()
            ):

                score += 20

            else:

                score -= 5


    # -----------------------------------------------------
    # FLEX
    # -----------------------------------------------------

    if product["flex"]:

        if comp["flex"]:

            if (
                product["flex"]
                == comp["flex"]
            ):

                score += 10

            else:

                score -= 5


    # -----------------------------------------------------
    # SKAFT
    # -----------------------------------------------------

    if product["shaft"]:

        if comp["shaft"]:

            if (
                product["shaft"]
                == comp["shaft"]
            ):

                score += 8


    # -----------------------------------------------------
    # SKICK
    # -----------------------------------------------------

    score += condition_similarity(
        product["condition"],
        comp["condition"]
    )


    # -----------------------------------------------------
    # BEGAGNAD
    # -----------------------------------------------------

    if any(
        word in text
        for word in USED_WORDS
    ):

        score += 10


    # -----------------------------------------------------
    # NYPRIS
    # -----------------------------------------------------

    if any(
        word in text
        for word in NEW_WORDS
    ):

        score -= 20


    return score, comp


# =========================================================
# HÄMTA COMPS
# =========================================================

def get_comps(product):

    queries = build_search_queries(
        product
    )

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
                result.get(
                    "title",
                    ""
                )
            )

            content = clean(
                result.get(
                    "content",
                    ""
                )
            )

            combined = (
                title
                + " "
                + content
            )

            price = money(
                combined
            )

            if not price:
                continue

            if price < 200:
                continue

            score, comp_data = comparable_score(
                product,
                result
            )

            # Bara riktigt relevanta comps
            if score < 55:
                continue

            all_results.append(
                {
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
                    "score": score,
                    "comp": comp_data
                }
            )


    # -----------------------------------------------------
    # DUBLETTER
    # -----------------------------------------------------

    unique = {}

    for item in all_results:

        key = (
            normalize(
                item["title"]
            ),
            item["price"]
        )

        if key not in unique:

            unique[key] = item


    comps = list(
        unique.values()
    )


    # -----------------------------------------------------
    # SORTERA
    # -----------------------------------------------------

    comps.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    return comps[:15]


# =========================================================
# VIKTAT MARKNADSVÄRDE
# =========================================================

def calculate_market_value(
    comps
):

    if len(comps) < 2:

        return (
            None,
            "Låg",
            []
        )


    weighted_prices = []

    for comp in comps:

        score = comp["score"]

        # Högre relevans = större vikt
        weight = max(
            1,
            score - 40
        )

        weighted_prices.append(
            (
                comp["price"],
                weight
            )
        )


    total_weight = sum(
        weight
        for _, weight
        in weighted_prices
    )


    if total_weight <= 0:

        return (
            None,
            "Låg",
            []
        )


    weighted_average = (
        sum(
            price * weight
            for price, weight
            in weighted_prices
        )
        / total_weight
    )


    # Median som skydd mot konstiga priser
    median = statistics.median(
        [
            price
            for price, _ in weighted_prices
        ]
    )


    # Kombinera viktat snitt + median
    market_value = (
        weighted_average * 0.65
        + median * 0.35
    )


    market_value = round(
        market_value / 100
    ) * 100


    if len(comps) >= 8:

        confidence = "Hög"

    elif len(comps) >= 4:

        confidence = "Medel"

    else:

        confidence = "Låg"


    return (
        market_value,
        confidence,
        weighted_prices
    )


# =========================================================
# DEAL SCORE
# =========================================================

def calculate_deal_score(
    asking_price,
    market_value,
    confidence,
    comps
):

    if not asking_price:
        return None

    if not market_value:
        return None


    discount = (
        market_value
        - asking_price
    ) / market_value


    score = 50

    # Pris
    score += (
        discount * 100
    )


    # Kvalitet
    if confidence == "Hög":

        score += 10

    elif confidence == "Medel":

        score += 3

    else:

        score -= 10


    # Hur bra är comps?
    if comps:

        avg_relevance = statistics.mean(
            comp["score"]
            for comp in comps
        )

        if avg_relevance >= 90:

            score += 8

        elif avg_relevance >= 75:

            score += 4

        elif avg_relevance < 65:

            score -= 5


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
# UI
# =========================================================

st.title(
    "⛳ Golf Deal Analyzer"
)

st.write(
    "Analysera golfannonser baserat på "
    "exakt modell, antal klubbor, år, "
    "set, flex, skaft och skick."
)


# =========================================================
# SIDOPANEL
# =========================================================

with st.sidebar:

    st.header(
        "⚙️ Kalkyl"
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


# =========================================================
# INPUT
# =========================================================

url = st.text_input(
    "🔗 Annonslänk",
    placeholder="Klistra in Blocket-annonsen här"
)


manual = st.text_area(
    "📝 Eller klistra in annonsens text",
    height=180,
    placeholder=(
        "Exempel:\n"
        "Titleist T200 2024\n"
        "5-PW, 6 klubbor\n"
        "Project X 6.0 stiff\n"
        "Mycket bra skick\n"
        "Pris 6000 kr"
    )
)


# =========================================================
# ANALYSERA
# =========================================================

if st.button(
    "🚀 Analysera fynd",
    type="primary"
):

    if not url.strip() and not manual.strip():

        st.error(
            "Lägg in en annonslänk "
            "eller annonsens text."
        )

        st.stop()


    # -----------------------------------------------------
    # LÄS ANNONS
    # -----------------------------------------------------

    try:

        if manual.strip():

            title = manual[:300]

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


    # -----------------------------------------------------
    # PRODUKTDATA
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # VISA PRODUKT
    # -----------------------------------------------------

    st.subheader(
        "🔎 Produktidentifiering"
    )


    c1, c2, c3, c4 = st.columns(4)


    with c1:

        st.write("**Märke**")

        st.write(
            product["brand"]
            or "Ej identifierat"
        )


    with c2:

        st.write("**Exakt modell**")

        st.write(
            product["model"]
            or "Ej identifierad"
        )


    with c3:

        st.write("**Antal klubbor**")

        st.write(
            (
                str(
                    product["club_count"]
                )
                + " st"
                if product["club_count"]
                else "Ej identifierat"
            )
        )


    with c4:

        st.write("**År**")

        st.write(
            product["year"]
            or "Ej identifierat"
        )


    c5, c6, c7, c8 = st.columns(4)


    with c5:

        st.write("**Set**")

        st.write(
            product["set"]
            or "Ej identifierat"
        )


    with c6:

        st.write("**Flex**")

        st.write(
            product["flex"]
            or "Ej identifierad"
        )


    with c7:

        st.write("**Skaft**")

        st.write(
            product["shaft"]
            or "Ej identifierat"
        )


    with c8:

        st.write("**Skick**")

        st.write(
            product["condition"]
        )


    st.metric(
        "Annonspris",
        (
            f"{asking_price:,.0f} kr"
            if asking_price
            else "Ej hittat"
        )
    )


    # -----------------------------------------------------
    # TAVILY
    # -----------------------------------------------------

    with st.spinner(
        "🌐 Söker efter exakt jämförbara golfklubbor..."
    ):

        comps = get_comps(
            product
        )


    # -----------------------------------------------------
    # MARKNADSVÄRDE
    # -----------------------------------------------------

    (
        market_value,
        confidence,
        weighted_prices
    ) = calculate_market_value(
        comps
    )


    # -----------------------------------------------------
    # ÅTERFÖRSÄLJNING
    # -----------------------------------------------------

    if market_value:

        realistic_sale_price = round(
            market_value
            * 0.95
            / 100
        ) * 100


        selling_fee = (
            realistic_sale_price
            * resale_fee
            / 100
        )


        net_sale = (
            realistic_sale_price
            - selling_fee
            - shipping
        )


        if asking_price:

            profit = (
                net_sale
                - asking_price
            )


            max_buy = (
                net_sale
                * (
                    1
                    - target_margin / 100
                )
            )

        else:

            profit = None
            max_buy = None

    else:

        realistic_sale_price = None
        net_sale = None
        profit = None
        max_buy = None


    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    deal_score = calculate_deal_score(
        asking_price,
        market_value,
        confidence,
        comps
    )


    # -----------------------------------------------------
    # RESULTAT
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "💰 Resultat"
    )


    c1, c2, c3, c4, c5, c6 = st.columns(6)


    with c1:

        st.metric(
            "Marknadsvärde",
            (
                f"{market_value:,.0f} kr"
                if market_value
                else "—"
            )
        )


    with c2:

        st.metric(
            "Realistiskt säljpris",
            (
                f"{realistic_sale_price:,.0f} kr"
                if realistic_sale_price
                else "—"
            )
        )


    with c3:

        st.metric(
            "Netto",
            (
                f"{net_sale:,.0f} kr"
                if net_sale
                else "—"
            )
        )


    with c4:

        st.metric(
            "Vinst",
            (
                f"{profit:,.0f} kr"
                if profit is not None
                else "—"
            )
        )


    with c5:

        st.metric(
            "Max inköpspris",
            (
                f"{max_buy:,.0f} kr"
                if max_buy
                else "—"
            )
        )


    with c6:

        st.metric(
            "Deal Score",
            (
                f"{deal_score}/100"
                if deal_score is not None
                else "—"
            )
        )


    st.markdown(
        f"# {verdict(deal_score)}"
    )


    # -----------------------------------------------------
    # KONFIDENS
    # -----------------------------------------------------

    if confidence == "Hög":

        st.success(
            f"📊 Hög konfidens — "
            f"{len(comps)} relevanta "
            f"jämförelseobjekt."
        )

    elif confidence == "Medel":

        st.warning(
            f"📊 Medelkonfidens — "
            f"{len(comps)} relevanta "
            f"jämförelseobjekt."
        )

    else:

        st.error(
            f"📊 Låg konfidens — "
            f"{len(comps)} relevanta "
            f"jämförelseobjekt."
        )


    # -----------------------------------------------------
    # PRIS VS MAXPRIS
    # -----------------------------------------------------

    if (
        asking_price
        and max_buy
    ):

        difference = (
            asking_price
            - max_buy
        )


        if asking_price <= max_buy:

            st.success(
                f"✅ Annonsen ligger "
                f"{abs(difference):,.0f} kr "
                f"under rekommenderat maxpris."
            )

        else:

            st.warning(
                f"⚠️ Annonsen ligger "
                f"{difference:,.0f} kr "
                f"över rekommenderat maxpris."
            )


    # -----------------------------------------------------
    # COMPS
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "🔍 Jämförelseobjekt"
    )


    if comps:

        rows = []

        for comp in comps:

            data = comp["comp"]


            rows.append(
                {
                    "Pris":
                        f"{comp['price']:,.0f} kr",

                    "Match":
                        f"{comp['score']}/100",

                    "Modell":
                        data.get(
                            "model"
                        ) or "—",

                    "År":
                        data.get(
                            "year"
                        ) or "—",

                    "Klubbor":
                        data.get(
                            "club_count"
                        ) or "—",

                    "Set":
                        data.get(
                            "set"
                        ) or "—",

                    "Flex":
                        data.get(
                            "flex"
                        ) or "—",

                    "Skick":
                        data.get(
                            "condition"
                        ) or "—",

                    "Källa":
                        comp["source"],

                    "Annons":
                        comp["title"],

                    "Länk":
                        comp["url"]
                }
            )


        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True
        )


    else:

        st.error(
            "❌ Hittade inte tillräckligt "
            "många relevanta jämförelseobjekt."
        )


    # -----------------------------------------------------
    # TRANSPARENS
    # -----------------------------------------------------

    with st.expander(
        "📊 Visa beräkningen"
    ):

        st.write(
            "Marknadsvärdet baseras på "
            "jämförelseobjektens relevans."
        )


        st.write(
            "**Viktade priser:**"
        )


        if weighted_prices:

            for price, weight in weighted_prices:

                st.write(
                    f"{price:,.0f} kr "
                    f"(vikt {weight})"
                )


        st.write(
            f"**Konfidens:** {confidence}"
        )


        st.write(
            f"**Antal comps:** {len(comps)}"
        )


        st.write(
            f"**Försäljningsavgift:** "
            f"{resale_fee:.1f}%"
        )


        st.write(
            f"**Frakt:** "
            f"{shipping:,.0f} kr"
        )


        st.write(
            f"**Säkerhetsmarginal:** "
            f"{target_margin:.1f}%"
        )


    with st.expander(
        "📄 Visa annonsdata"
    ):

        st.write(
            full_text[:10000]
        )
