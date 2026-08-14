#!/usr/bin/env python3
"""
Download and package bio-01 NHANES 2017-2018 into star-schema for Project Mark.
Requires: pandas, pyreadstat, requests
Run: python download_and_process_bio01.py
"""
import requests
from pathlib import Path
import pyreadstat
import pandas as pd

BASE = Path("PACKAGES/bio-01_clinical_exercise_glycemic")
RAW = BASE / "raw"
PROC = BASE / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

FILES = {
    "DEMO_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt",
    "GHB_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/GHB_J.xpt",
    "BMX_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BMX_J.xpt",
    "DIQ_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DIQ_J.xpt",
    "PAQ_J.xpt": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/PAQ_J.xpt",
}

def download():
    for name, url in FILES.items():
        path = RAW / name
        if path.exists() and path.stat().st_size > 10000:
            print(f"Exists: {name}")
            continue
        print(f"Downloading {name}...")
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
        print(f"  {path.stat().st_size} bytes")

def process():
    demo, _ = pyreadstat.read_xport(RAW / "DEMO_J.xpt")
    ghb, _ = pyreadstat.read_xport(RAW / "GHB_J.xpt")
    bmx, _ = pyreadstat.read_xport(RAW / "BMX_J.xpt")
    diq, _ = pyreadstat.read_xport(RAW / "DIQ_J.xpt")
    paq, _ = pyreadstat.read_xport(RAW / "PAQ_J.xpt")

    demo_cols = ["SEQN", "SDDSRVYR", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "WTMEC2YR", "SDMVPSU", "SDMVSTRA", "INDFMPIR", "DMDEDUC2"]
    fact = demo[[c for c in demo_cols if c in demo.columns]].copy()
    fact = fact.merge(ghb[["SEQN", "LBXGH"]], on="SEQN", how="left")
    fact = fact.merge(bmx[[c for c in ["SEQN", "BMXBMI", "BMXWT", "BMXHT"] if c in bmx.columns]], on="SEQN", how="left")
    fact = fact.merge(diq[[c for c in ["SEQN", "DIQ010", "DIQ050", "DIQ070", "DID040"] if c in diq.columns]], on="SEQN", how="left")
    fact = fact.merge(paq[[c for c in ["SEQN", "PAQ605", "PAQ620", "PAQ650", "PAQ665", "PAD680"] if c in paq.columns]], on="SEQN", how="left")

    fact.to_csv(PROC / "fact_participant_glycemic.csv", index=False)
    print("Wrote fact,", fact.shape)

    pd.DataFrame({"gender_code": [1,2], "gender_label": ["Male", "Female"]}).to_csv(PROC / "dim_gender.csv", index=False)
    race = {1: "Mexican American", 2: "Other Hispanic", 3: "Non-Hispanic White", 4: "Non-Hispanic Black", 6: "Non-Hispanic Asian", 7: "Other Race - Including Multi-Racial"}
    pd.DataFrame({"race_code": list(race.keys()), "race_label": list(race.values())}).to_csv(PROC / "dim_race.csv", index=False)
    pd.DataFrame({"cycle_code": [10], "cycle_label": ["2017-2018"], "begin_year": [2017], "end_year": [2018]}).to_csv(PROC / "dim_cycle.csv", index=False)
    print("Wrote dims")

if __name__ == "__main__":
    download()
    process()
    print("Done. See PACKAGES/bio-01_clinical_exercise_glycemic/processed/")
