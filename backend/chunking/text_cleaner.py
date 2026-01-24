import re
import pandas as pd

def clean_medical_report(text: str) -> str:
    if pd.isna(text):
        return ""

    import unicodedata
    text = unicodedata.normalize("NFKC", text)

    # Corriger mots collés par points
    text = re.sub(r"([a-z])\.([A-Z])", r"\1. \2", text)
    text = re.sub(r"([a-z])\.([a-z])", r"\1 \2", text)

    # Corrections OCR fréquentes
    corrections = {
        "tymph": "lymph",
        "attendir g": "attending",
        "alides": "slides",
        "materiala": "materials",
        "(D/": "(0/"
    }
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)

    # Supprimer points inutiles après chiffres ou majuscules avant unité
    text = re.sub(r"(?<=\d)\.(?=\s*[a-zA-Z])", "", text)  # 5.5. cm → 5.5 cm
    text = re.sub(r"\s*\.\s*(?=[a-z])", " ", text)        # "tumor. does" → "tumor does"
    
    # Supprimer points multiples
    text = re.sub(r"\.{2,}", ".", text)

    # Supprimer parenthèses vides
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\(\s*[\W_]+\s*\)", "", text)

    # Nettoyer retours ligne inutiles
    text = re.sub(r"\s*\n\s*", " ", text)

    # Ajouter retours ligne avant sections clés
    sections = [
        "DIAGNOSIS",
        "TISSUE DESCRIPTION",
        "Comment",
        "Key Pathological Findings",
        "Specimen type",
        "Clinical History",
        "Preoperative Diagnosis",
        "Gross Description",
        "Intraoperative Consultation"
    ]
    for sec in sections:
        text = re.sub(sec, f"\n\n{sec}", text, flags=re.I)

    # Espaces propres
    text = re.sub(r"\s+", " ", text)

    return text.strip()