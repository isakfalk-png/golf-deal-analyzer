import streamlit as st
from tavily import TavilyClient
from openai import OpenAI

st.set_page_config(
    page_title="Golf Deal Analyzer",
    page_icon="⛳",
    layout="wide"
)

st.title("⛳ Golf Deal Analyzer")
st.write(
    "Analysera golfannonser, jämför marknadspriser och bedöm om det är ett bra köp för vidareförsäljning."
)

# --------------------------------------------------
# API-NYCKLAR
# --------------------------------------------------

with st.sidebar:
    st.header("🔑 Inställningar")

    openai_key = st.text_input(
        "OpenAI API Key",
        type="password"
    )

    max_results = st.slider(
        "Antal sökresultat",
        min_value=1,
        max_value=8,
        value=5
    )

# Hämta Tavily API-nyckeln från Streamlit Secrets
try:
    tavily_key = st.secrets["TAVILY_API_KEY"]
except Exception:
    tavily_key = None

# --------------------------------------------------
# SÖKRUTA
# --------------------------------------------------

search_query = st.text_input(
    "Vad vill du analysera?",
    placeholder="Exempel: Titleist T200 2024 5-PW begagnat golfset"
)

if st.button("🚀 Analysera fynd", type="primary"):

    # Kontrollera API-nycklar
    if not tavily_key:
        st.error(
            "❌ Tavily API-nyckeln saknas. "
            "Lägg in TAVILY_API_KEY under Streamlit → Manage app → Settings → Secrets."
        )
        st.stop()

    if not openai_key:
        st.error("❌ Fyll i din OpenAI API Key i sidomenyn.")
        st.stop()

    if not search_query:
        st.warning("Skriv först vad du vill analysera.")
        st.stop()

    # --------------------------------------------------
    # TAVILY
    # --------------------------------------------------

    with st.spinner("🔍 Söker efter jämförbara golfpriser..."):

        try:
            tavily = TavilyClient(api_key=tavily_key)

            search_response = tavily.search(
                query=search_query,
                max_results=max_results,
                search_depth="advanced"
            )

            results = search_response.get("results", [])

        except Exception as e:
            st.error(f"❌ Tavily-fel: {e}")
            st.stop()

    if not results:
        st.warning("Inga relevanta sökresultat hittades.")
        st.stop()

    # --------------------------------------------------
    # VISA KÄLLOR
    # --------------------------------------------------

    with st.expander("🔎 Visa sökresultaten"):

        for item in results:

            st.markdown(
                f"### [{item.get('title', 'Källa')}]({item.get('url', '#')})"
            )

            st.write(item.get("content", ""))

            st.markdown("---")

    # --------------------------------------------------
    # OPENAI ANALYS
    # --------------------------------------------------

    with st.spinner("🤖 Analyserar marknadsvärdet..."):

        try:
            client = OpenAI(api_key=openai_key)

            context = "\n\n".join(
                [
                    f"KÄLLA: {item.get('url', '')}\n"
                    f"{item.get('content', '')}"
                    for item in results
                ]
            )

            prompt = f"""
Du är en expert på begagnad golfutrustning och vidareförsäljning.

Analysera följande golfprodukt baserat på sökresultaten.

SÖKFRÅGA:
{search_query}

SÖKRESULTAT:
{context}

Ge en tydlig bedömning med:

1. Vad produkten verkar vara.
2. Ungefärligt marknadsvärde begagnad.
3. Rimligt försäljningspris.
4. Om produkten verkar vara attraktiv för vidareförsäljning.
5. Potentiell bruttovinst om inköpspriset är känt.
6. Vilket maxpris man bör betala för att affären ska vara intressant.
7. En Deal Score från 0–100.
8. Ett tydligt beslut:
   - 🟢 KÖP
   - 🟡 KANSKE
   - 🔴 SKIPPA

Var försiktig med priser som bara kommer från aktiva annonser.
Försök skilja mellan realistiskt marknadsvärde och säljarens önskade pris.

Var tydlig med osäkerheter.
"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2
            )

            st.markdown("## 📊 Analys")

            st.markdown(
                response.choices[0].message.content
            )

        except Exception as e:
            st.error(f"❌ OpenAI-fel: {e}")
