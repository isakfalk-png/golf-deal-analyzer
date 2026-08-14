# Golf Deal Analyzer V2

Flöde:
annons -> identifiering -> jämförelsepriser -> marknadsvärde -> realistiskt säljpris -> kostnader -> netto -> vinst -> maxpris -> Deal Score.

## Deploy
1. Lägg filerna i ett GitHub-repo.
2. Deploya `app.py` på Streamlit Community Cloud.
3. Lägg `TAVILY_API_KEY="..."` under appens Secrets.
4. Öppna appen och testa med en annonslänk eller inklistrad annonstext.

## Nästa steg
För verkligt hög precision bör systemet senare få:
- databas med historiska priser
- sålda priser som primär signal
- exakt modell-/generationidentifiering
- klubb-för-klubb-värdering
- bildanalys av skick
- batchanalys
- lagring av tidigare fynd
