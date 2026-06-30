"""
convert_excel_questions.py

Converts Excel question bank (data/שאלות לסמסים ניסן פג) to per-tractate JSON files.
Run once after updating the Excel files.
"""
import json
import os
from pathlib import Path
import openpyxl

EXCEL_FOLDER = Path(__file__).parent / "data" / "שאלות לסמסים ניסן פג"
DATA_DIR = Path(__file__).parent / "data"

COLUMNS = {
    "מסכת": 0,
    "דף": 1,
    "סוג שאלה": 2,
    "תוכן שאלה": 3,
}


def load_all_rows():
    rows = []
    for xlsx_file in sorted(EXCEL_FOLDER.glob("*.xlsx")):
        wb = openpyxl.load_workbook(xlsx_file)
        ws = wb.active
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                header = list(row)
                continue
            tractate = row[COLUMNS["מסכת"]]
            daf = row[COLUMNS["דף"]]
            q_type = row[COLUMNS["סוג שאלה"]]
            text = row[COLUMNS["תוכן שאלה"]]
            if not tractate or not text:
                continue
            rows.append({
                "tractate": str(tractate).strip(),
                "daf": str(daf).strip() if daf else "",
                "question_type": str(q_type).strip() if q_type else "",
                "text": str(text).strip(),
            })
    return rows


def build_tractate_jsons(rows):
    tractates: dict[str, list] = {}
    counters: dict[str, int] = {}

    for row in rows:
        t = row["tractate"]
        if t not in tractates:
            tractates[t] = []
            counters[t] = 0
        counters[t] += 1
        q_id = f"{t}_{counters[t]}"
        tractates[t].append({
            "id": q_id,
            "text": row["text"],
            "question_type": row["question_type"],
            "daf": {"daf": row["daf"], "amud": None},
        })

    return tractates


def save_jsons(tractates: dict):
    for tractate_name, questions in tractates.items():
        out = {
            "title": f"שאלות {tractate_name}",
            "questions": questions,
        }
        out_path = DATA_DIR / f"{tractate_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  {tractate_name}: {len(questions)} שאלות → {out_path.name}")


if __name__ == "__main__":
    print("קורא קבצי Excel...")
    rows = load_all_rows()
    print(f"סה\"כ {len(rows)} שאלות נטענו")

    tractates = build_tractate_jsons(rows)
    print(f"\nמסכתות שנמצאו ({len(tractates)}):")

    save_jsons(tractates)
    print("\nסיום. הרץ init_tractates() כדי לרשום ב-DB.")
