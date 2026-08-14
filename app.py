import streamlit as st
from tavily import TavilyClient
from openai import OpenAI

st.set_page_config(
    page_title="Golf Deal Analyzer",
    page_icon="⛳",
    layout="wide"
)

st.title("⛳ Golf Deal Analyzer")
st.write("Sök på nätet och få en AI-analys av golfpriser.")

# -------------------------
# API-NYCKLAR
# -------------------------

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

# Hämta Tavily från Streamlit Secrets
try:
    tavily_key = st.secrets["TAVILY_API_KEY"]
except Exception:
    tavily_key = None

# -------------------------
# SÖKNING
# -------------------------

search_query = st.text_input(
    "Vad vill du analysera?",
    placeholder="t.ex. Titleist T200 2024 5-PW begagnat"
)

if st.button("🚀 Sök och Analysera", type="primary"):

    if not tavily_key:
        st.error(
            "❌ Tavily API-nyckeln saknas. "
            "Lägg till TAVILY_API_KEY under Streamlit → Manage app → Settings → Secrets."
        )
        st.stop()

    if not openai_key:
        st.error("❌ Fyll i din OpenAI API Key i sidomenyn.")
        st.stop()

    if not search_query:
        st.warning("⚠️ Skriv in något att söka efter först.")
        st.stop()

    # -------------------------
    # TAVILY
    # -------------------------

    with st.spinner("🔍 Söker på webben..."):

        try:
            tavily = TavilyClient(api_key=tavily_key)

            search_response = tavily.search(
                query=search_query,
                max_results=max_results,
                search_depth="basic"
            )

            results = search_response.get("results", [])

        except Exception as e:
            st.error(f"❌ Tavily-fel: {e}")
            st.stop()

    if not results:
        st.warning("Hittade inga sökresultat.")
        st.stop()

    # -------------------------
    # VISA KÄLLOR
    # -------------------------

    with st.expander("🌐 Visa sökresultat"):

        for item in results:
            st.markdown(
                f"### [{item['title']}]({item['url']})"
            )
            st.write(item.get("content", ""))
            st.markdown("---")

    # -------------------------
    # OPENAI
    # -------------------------

    with st.spinner("🤖 AI analyserar priserna..."):

        try:
            client = OpenAI(api_key=openai_key)

            context = "\n\n".join(
                [
                    f"Källa: {item['url']}\n"
                    f"Information: {item.get('content', '')}"
                    for item in results
                ]
            )

            prompt = f"""
Du är en AI-assistent som analyserar priser på begagnad golfutrustning.

Använd endast informationen från sökresultaten nedan.

Sökfråga:
{search_query}

Sökresultat:
{context}

Ge en tydlig analys med:

1. Ungefärligt marknadsvärde
2. Vilka priser du hittade
3. Lägsta relevanta pris
4. Genomsnittligt pris om möjligt
5. Om produkten verkar vara ett bra köp
6. Om den kan säljas vidare med vinst
7. En uppskattad maximal köpesumma
8. En enkel rekommendation: KÖP, KANSKE eller SKIPPA

Var tydlig med att priserna är uppskattningar baserade på sökresultaten.
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

            st.markdown("## 📊 AI-Analys")

            st.markdown(
                response.choices[0].message.content
            )

        except Exception as e:
            st.error(f"❌ OpenAI-fel: {e}")
