# BioCUP — Search Summary
**Collection:** `biocup_chunks`  

## Top predicted primary sites
| Site | Probability |
|---|---:|
| lung | 31.38% |
| liver | 18.59% |
| colon | 13.21% |
| prostate | 10.85% |
| ovary | 10.15% |
| pancreas | 9.47% |
| breast | 6.35% |

## LLM explanation (evidence-based)
> This explanation is generated using retrieved evidence only.

A) The top predicted primary site, lung, is most supported due to its highest cumulative score of 0.0898, derived from multiple relevant sections, particularly IHC. This score is significantly higher than the next sites, indicating stronger evidence for lung involvement (BIOCUP_00035, IHC).

B) To separate lung (top-1) from liver (top-2):
- Specific IHC markers or phrases indicating lung pathology.
- Higher scores from lung-specific sections compared to liver-specific sections.

C) To separate lung (top-1) from colon (top-3):
- Distinct IHC markers or phrases that are unique to lung conditions.
- Evidence from lung-focused diagnostic sections that surpass colon-related findings.

D) Generic phrases to treat as weak evidence:
- "IHC" without specific context or markers.
- "Diagnosis" without specifying the organ or condition.

E) There is uncertainty regarding the specificity of the markers and phrases used in the context, which may affect the interpretation of the evidence. Further details on the specific markers would enhance clarity.

## Evidence examples (no scores shown)

### lung
- **(BIOCUP_00035, IHC)** 
- **(BIOCUP_00029, SYNOPTIC)** 
- **(BIOCUP_00001, IHC)** 

### liver
- **(BIOCUP_00390, DIAGNOSIS)** 
- **(BIOCUP_00367, IHC)** 
- **(BIOCUP_00418, IHC)** 

### colon
- **(BIOCUP_00067, IHC)** 
- **(BIOCUP_00119, DIAGNOSIS)** 
- **(BIOCUP_00065, DIAGNOSIS)** 

---
_Note: This tool supports retrieval review only and does not provide medical advice._
