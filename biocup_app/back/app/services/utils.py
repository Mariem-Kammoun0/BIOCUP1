from datetime import datetime, time, date

def clean(s: str) -> str:
    return " ".join(
        s.replace("\r", " ")
         .replace("\n", " ")
         .split()
    )

def date_to_datetime(d: date | None) -> datetime | None:
    if d is None:
        return None
    return datetime.combine(d, time.min)
