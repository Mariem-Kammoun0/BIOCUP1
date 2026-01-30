from .utils import clean

def build_patient_report(case_id: str, form: dict) -> str:
    # simple, lisible, sections stables
    ihc = form.get("ihc", {}) or {}
    ihc_lines = []
    for k, v in ihc.items():
        if v:
            ihc_lines.append(f"{k}: {v}")

    metastasis = form.get("metastasis_sites", []) or []
    metastasis_txt = ", ".join(metastasis) if metastasis else "Not specified"

    parts = []

    parts.append(f"[case_id={case_id} | section=DIAGNOSIS]\n"
                 f"Histology: {form.get('histology') or 'Not specified'}.\n"
                 f"Metastasis sites: {metastasis_txt}.\n"
                 f"Primary tumor site not identified.\n")

    parts.append(f"[case_id={case_id} | section=LYMPH_NODES]\n"
                 f"{form.get('lymph_nodes_summary') or 'No lymph node information provided.'}\n")

    parts.append(f"[case_id={case_id} | section=IHC]\n"
                 f"{('Immunohistochemistry: ' + '; '.join(ihc_lines)) if ihc_lines else 'No IHC provided.'}\n")

    parts.append(f"[case_id={case_id} | section=TNM]\n"
                 f"{form.get('tnm') or 'TNM not provided.'}\n")

    parts.append(f"[case_id={case_id} | section=COMMENT]\n"
                 f"{form.get('notes') or 'No additional comments.'}\n")

    return clean("\n".join(parts))
