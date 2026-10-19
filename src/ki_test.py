"""Erster Test: Funktioniert die Verbindung zu Gemini?"""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()                          # liest .env ein
MODELL = "gemini-3.8-flash"            # ggf. durch Namen aus AI Studio ersetzen

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
antwort = client.interactions.create(
    model=MODELL,
    input="Erkläre in einem Satz, was der EU-Emissionshandel ist.",
)
print(antwort.output_text)