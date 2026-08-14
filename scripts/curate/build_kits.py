#!/usr/bin/env python3
"""Build 20 biology starter kits from downloaded public sources."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pandas as pd

from common import (
    PACKAGES,
    PUBLIC_PACKAGES,
    ROOT,
    SCRATCH,
    catalog_entry,
    ensure_dir,
    finalize_kit,
    qa_no_orphans,
)

CATALOG: list[dict] = []


def add_catalog(**kwargs):
    CATALOG.append(catalog_entry(**kwargs))


# ---------------------------------------------------------------------------
# 01 NHANES cardiometabolic
# ---------------------------------------------------------------------------
def kit_01():
    print("kit 01 nhanes")
    demo = pd.read_sas(SCRATCH / "nhanes/DEMO_J.xpt", format="xport")
    bmx = pd.read_sas(SCRATCH / "nhanes/BMX_J.xpt", format="xport")
    ghb = pd.read_sas(SCRATCH / "nhanes/GHB_J.xpt", format="xport")
    tchol = pd.read_sas(SCRATCH / "nhanes/TCHOL_J.xpt", format="xport")
    hdl = pd.read_sas(SCRATCH / "nhanes/HDL_J.xpt", format="xport")
    glu = pd.read_sas(SCRATCH / "nhanes/GLU_J.xpt", format="xport")
    bpx = pd.read_sas(SCRATCH / "nhanes/BPXO_J.xpt", format="xport")

    def seqn(s):
        return s.astype("Int64").astype(str)

    demo["seqn"] = seqn(demo["SEQN"])
    for d in (bmx, ghb, tchol, hdl, glu, bpx):
        d["seqn"] = seqn(d["SEQN"])

    # Keep MEC-examined adults 18+ for the program-feasibility grain
    adult = demo[(demo["RIDAGEYR"] >= 18) & (demo["RIDSTATR"] == 2)].copy()
    n_raw_demo = len(demo)
    n_adult = len(adult)

    dim_participant = pd.DataFrame(
        {
            "seqn": adult["seqn"],
            "age_years": adult["RIDAGEYR"].astype("Int64"),
            "sex_code": adult["RIAGENDR"].astype("Int64").astype(str),
            "race_code": adult["RIDRETH3"].astype("Int64").astype(str),
            "education_code": adult["DMDEDUC2"].where(~adult["DMDEDUC2"].isin([7, 9])).astype("Int64").astype(str),
            "income_code": adult["INDHHIN2"].where(~adult["INDHHIN2"].isin([77, 99])).astype("Int64").astype(str),
            "poverty_ratio": adult["INDFMPIR"].where(adult["INDFMPIR"] < 10),
            "interview_weight": adult["WTINT2YR"],
            "exam_weight": adult["WTMEC2YR"],
            "strata": adult["SDMVSTRA"].astype("Int64").astype(str),
            "psu": adult["SDMVPSU"].astype("Int64").astype(str),
        }
    )
    dim_participant["education_code"] = dim_participant["education_code"].replace({"<NA>": pd.NA})
    dim_participant["income_code"] = dim_participant["income_code"].replace({"<NA>": pd.NA})

    exam = adult[["seqn"]].merge(bmx[["seqn", "BMXBMI", "BMXWT", "BMXHT", "BMXWAIST"]], on="seqn", how="left")
    exam = exam.merge(bpx[["seqn", "BPXOSY1", "BPXODI1"]], on="seqn", how="left")
    fact_exam = pd.DataFrame(
        {
            "seqn": exam["seqn"],
            "bmi": exam["BMXBMI"],
            "weight_kg": exam["BMXWT"],
            "height_cm": exam["BMXHT"],
            "waist_cm": exam["BMXWAIST"],
            "systolic_mmhg": exam["BPXOSY1"],
            "diastolic_mmhg": exam["BPXODI1"],
        }
    )

    analyte = pd.DataFrame(
        [
            {"analyte_code": "GHB", "analyte_name": "Glycohemoglobin (HbA1c)", "unit": "%", "loinc": "4548-4"},
            {"analyte_code": "TC", "analyte_name": "Total cholesterol", "unit": "mg/dL", "loinc": "2093-3"},
            {"analyte_code": "HDL", "analyte_name": "Direct HDL cholesterol", "unit": "mg/dL", "loinc": "2085-9"},
            {"analyte_code": "GLU", "analyte_name": "Fasting plasma glucose", "unit": "mg/dL", "loinc": "1558-2"},
        ]
    )
    lab_parts = [
        ghb.rename(columns={"LBXGH": "value"}).assign(analyte_code="GHB")[["seqn", "analyte_code", "value"]],
        tchol.rename(columns={"LBXTC": "value"}).assign(analyte_code="TC")[["seqn", "analyte_code", "value"]],
        hdl.rename(columns={"LBDHDD": "value"}).assign(analyte_code="HDL")[["seqn", "analyte_code", "value"]],
        glu.rename(columns={"LBXGLU": "value"}).assign(analyte_code="GLU")[["seqn", "analyte_code", "value"]],
    ]
    fact_lab = pd.concat(lab_parts, ignore_index=True)
    fact_lab = fact_lab[fact_lab["seqn"].isin(dim_participant["seqn"])]
    fact_lab = fact_lab.dropna(subset=["value"])

    dim_code = pd.DataFrame(
        [
            {"code_type": "sex", "code": "1", "label": "Male"},
            {"code_type": "sex", "code": "2", "label": "Female"},
            {"code_type": "race", "code": "1", "label": "Mexican American"},
            {"code_type": "race", "code": "2", "label": "Other Hispanic"},
            {"code_type": "race", "code": "3", "label": "Non-Hispanic White"},
            {"code_type": "race", "code": "4", "label": "Non-Hispanic Black"},
            {"code_type": "race", "code": "6", "label": "Non-Hispanic Asian"},
            {"code_type": "race", "code": "7", "label": "Other Race — Including Multi-Racial"},
            {"code_type": "education", "code": "1", "label": "Less than 9th grade"},
            {"code_type": "education", "code": "2", "label": "9–11th grade (no diploma)"},
            {"code_type": "education", "code": "3", "label": "High school graduate / GED"},
            {"code_type": "education", "code": "4", "label": "Some college or AA degree"},
            {"code_type": "education", "code": "5", "label": "College graduate or above"},
            {"code_type": "income", "code": "1", "label": "$0–$4,999"},
            {"code_type": "income", "code": "2", "label": "$5,000–$9,999"},
            {"code_type": "income", "code": "3", "label": "$10,000–$14,999"},
            {"code_type": "income", "code": "4", "label": "$15,000–$19,999"},
            {"code_type": "income", "code": "5", "label": "$20,000–$24,999"},
            {"code_type": "income", "code": "6", "label": "$25,000–$34,999"},
            {"code_type": "income", "code": "7", "label": "$35,000–$44,999"},
            {"code_type": "income", "code": "8", "label": "$45,000–$54,999"},
            {"code_type": "income", "code": "9", "label": "$55,000–$64,999"},
            {"code_type": "income", "code": "10", "label": "$65,000–$74,999"},
            {"code_type": "income", "code": "12", "label": "$20,000 and over (unspecified)"},
            {"code_type": "income", "code": "13", "label": "Under $20,000 (unspecified)"},
            {"code_type": "income", "code": "14", "label": "$75,000–$99,999"},
            {"code_type": "income", "code": "15", "label": "$100,000 and over"},
        ]
    )
    dim_year = pd.DataFrame(
        [
            {
                "cycle": "2017-2018",
                "survey": "NHANES",
                "file_suffix": "J",
                "universe": "U.S. civilian noninstitutionalized population, MEC-examined adults 18+",
                "title": "National Health and Nutrition Examination Survey 2017–2018 cardiometabolic exam + labs",
            }
        ]
    )

    qa_no_orphans(fact_exam, dim_participant, "seqn", "seqn", "exam.seqn")
    qa_no_orphans(fact_lab, dim_participant, "seqn", "seqn", "lab.seqn")
    qa_no_orphans(fact_lab, analyte, "analyte_code", "analyte_code", "lab.analyte")

    tables = {
        "fact_exam.csv": fact_exam,
        "fact_lab.csv": fact_lab,
        "dim_participant.csv": dim_participant,
        "dim_analyte.csv": analyte,
        "dim_code.csv": dim_code,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_exam.csv": "one row per MEC-examined adult participant",
        "fact_lab.csv": "one row per adult participant × laboratory analyte",
        "dim_participant.csv": "one row per adult participant (PK seqn)",
        "dim_analyte.csv": "one row per laboratory analyte (PK analyte_code)",
        "dim_code.csv": "one row per codebook value (sex / race / education / income)",
        "dim_year.csv": "one row describing the 2017–2018 NHANES vintage",
    }
    table_docs = {
        "fact_exam.csv": "Anthropometry and first-reading oscillometric blood pressure for MEC-examined adults.",
        "fact_lab.csv": "Tidy laboratory results (HbA1c, lipids, fasting glucose) for the same adults.",
        "dim_participant.csv": "Survey demographics, poverty ratio, and design weights. Grain: one examined adult.",
        "dim_analyte.csv": "Analyte codebook with units and LOINC.",
        "dim_code.csv": "Labels for sex, race/ethnicity, education, and household income codes.",
        "dim_year.csv": "Survey cycle metadata (vintage, universe, title).",
    }
    desc = {
        "fact_exam.csv": {
            "seqn": "Respondent sequence number (FK -> dim_participant.seqn)",
            "bmi": "Body mass index (kg/m2); null if not measured",
            "weight_kg": "Body weight in kilograms; null if not measured",
            "height_cm": "Standing height in centimetres; null if not measured",
            "waist_cm": "Waist circumference in centimetres; null if not measured",
            "systolic_mmhg": "First oscillometric systolic BP (mm Hg); null if not measured",
            "diastolic_mmhg": "First oscillometric diastolic BP (mm Hg); null if not measured",
        },
        "fact_lab.csv": {
            "seqn": "Respondent sequence number (FK -> dim_participant.seqn)",
            "analyte_code": "Analyte key (FK -> dim_analyte.analyte_code)",
            "value": "Numeric laboratory result in dim_analyte.unit; rows with missing values dropped",
        },
        "dim_participant.csv": {
            "seqn": "Respondent sequence number (PK)",
            "age_years": "Age at screening in years",
            "sex_code": "Sex (FK -> dim_code.code where code_type=sex)",
            "race_code": "Race/ethnicity RIDRETH3 (FK -> dim_code.code where code_type=race)",
            "education_code": "Adult education DMDEDUC2; 7/9 (refused/don't know) nulled (FK -> dim_code)",
            "income_code": "Household income INDHHIN2; 77/99 nulled (FK -> dim_code)",
            "poverty_ratio": "Family income-to-poverty ratio (INDFMPIR); values >=10 treated as missing",
            "interview_weight": "Full-sample 2-year interview weight WTINT2YR",
            "exam_weight": "Full-sample 2-year MEC exam weight WTMEC2YR",
            "strata": "Masked variance unit stratum SDMVSTRA",
            "psu": "Masked variance unit PSU SDMVPSU",
        },
        "dim_analyte.csv": {
            "analyte_code": "Short analyte key (PK)",
            "analyte_name": "Laboratory test name",
            "unit": "Reporting unit",
            "loinc": "LOINC code for the analyte",
        },
        "dim_code.csv": {
            "code_type": "Code family: sex, race, education, or income",
            "code": "Source codebook value (PK with code_type)",
            "label": "Human-readable label from the NHANES codebook",
        },
        "dim_year.csv": {
            "cycle": "NHANES data cycle (PK)",
            "survey": "Survey program name",
            "file_suffix": "NCHS file letter for this cycle (J = 2017–2018)",
            "universe": "Analytic universe after filters",
            "title": "Kit title",
        },
    }
    meta = {
        "source": "CDC / NCHS National Health and Nutrition Examination Survey (NHANES) 2017–2018",
        "source_url": "https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.cdc.gov/nchs/data_access/restrictions.htm",
        "download_urls": [
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BMX_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/GHB_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/TCHOL_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/HDL_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/GLU_J.xpt",
            "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BPXO_J.xpt",
        ],
        "transforms": [
            f"Read SAS XPORT files for DEMO/BMX/GHB/TCHOL/HDL/GLU/BPXO (DEMO n={n_raw_demo}).",
            f"Restricted dim_participant and facts to MEC-examined adults RIDAGEYR>=18 and RIDSTATR=2 (n={n_adult}); interview-only and age<18 rows excluded from the analytic universe and logged here.",
            "Nulled DMDEDUC2 in {7,9} and INDHHIN2 in {77,99} (refused / don't know). Nulled INDFMPIR >= 10.",
            "Melted four lab files into fact_lab (one row per participant × analyte) and dropped rows with missing numeric values.",
            "Joined first oscillometric BP reading (BPXOSY1/BPXODI1) and body measures onto fact_exam.",
            "Attached published NHANES codebook labels for sex, RIDRETH3, DMDEDUC2, INDHHIN2.",
        ],
        "extra_files": [],
    }
    slug = "bio-01_nhanes_cardiometabolic"
    title = "NHANES 2017–2018: cardiometabolic exam, HbA1c, lipids, and glucose"
    framing = (
        "Judge whether a cardiometabolic screening or fitness-benefit program's headline "
        "A1c / LDL / BMI change still holds after decomposing by age, sex, race/ethnicity, education, and income."
    )
    finalize_kit(
        slug,
        tables=tables,
        grains=grains,
        descriptions=desc,
        table_docs=table_docs,
        meta=meta,
        package_title=title,
        framing=framing,
        join_keys="fact_exam.seqn -> dim_participant.seqn ; fact_lab.seqn -> dim_participant.seqn ; fact_lab.analyte_code -> dim_analyte.analyte_code ; dim_participant.sex_code/race_code/education_code/income_code -> dim_code.code",
        string_cols={
            "fact_exam.csv": {"seqn"},
            "fact_lab.csv": {"seqn", "analyte_code"},
            "dim_participant.csv": {"seqn", "sex_code", "race_code", "education_code", "income_code", "strata", "psu"},
            "dim_analyte.csv": {"analyte_code", "analyte_name", "unit", "loinc"},
            "dim_code.csv": {"code_type", "code", "label"},
        },
    )
    add_catalog(
        slug=slug,
        title=title,
        framing=framing,
        domain="clinical-population",
        tags=["assay", "cohort", "nhanes"],
        source=meta["source"],
        license_text=meta["license"],
        tables=tables,
        grains=grains,
    )


# ---------------------------------------------------------------------------
# 02 CDC PLACES county
# ---------------------------------------------------------------------------
def kit_02():
    print("kit 02 places")
    raw = pd.read_csv(SCRATCH / "places/county_2024.csv", low_memory=False)
    n_raw = len(raw)
    raw["locationid"] = raw["locationid"].astype(str).str.zfill(5)
    # Keep crude prevalence (one value type) so grain is county × measure × year
    keep = raw[raw["datavaluetypeid"].astype(str) == "CrdPrv"].copy()
    n_filt = n_raw - len(keep)
    fact = keep[
        [
            "year",
            "locationid",
            "measureid",
            "data_value",
            "low_confidence_limit",
            "high_confidence_limit",
            "totalpopulation",
            "totalpop18plus",
        ]
    ].rename(
        columns={
            "locationid": "geoid",
            "measureid": "measure_id",
            "low_confidence_limit": "ci_low",
            "high_confidence_limit": "ci_high",
            "totalpopulation": "population",
            "totalpop18plus": "population_18plus",
        }
    )
    fact["year"] = fact["year"].astype("Int64")
    dim_geo = (
        keep[["locationid", "stateabbr", "statedesc", "locationname"]]
        .drop_duplicates("locationid")
        .rename(columns={"locationid": "geoid", "stateabbr": "state_abbr", "statedesc": "state_name", "locationname": "county_name"})
    )
    dim_geo["geoid"] = dim_geo["geoid"].astype(str).str.zfill(5)
    dim_measure = (
        keep[["measureid", "measure", "category", "categoryid", "short_question_text", "data_value_unit", "datasource"]]
        .drop_duplicates("measureid")
        .rename(
            columns={
                "measureid": "measure_id",
                "categoryid": "category_id",
                "short_question_text": "short_label",
                "data_value_unit": "unit",
            }
        )
    )
    dim_category = (
        keep[["categoryid", "category"]]
        .drop_duplicates("categoryid")
        .rename(columns={"categoryid": "category_id", "category": "category_name"})
    )
    dim_year = pd.DataFrame(
        [
            {
                "release": "2024",
                "measure_year": int(keep["year"].dropna().astype(int).mode().iloc[0]) if keep["year"].notna().any() else 2022,
                "program": "PLACES: Local Data for Better Health",
                "title": "County crude prevalence of chronic-disease and prevention indicators",
            }
        ]
    )
    qa_no_orphans(fact, dim_geo, "geoid", "geoid", "places.geoid")
    qa_no_orphans(fact, dim_measure, "measure_id", "measure_id", "places.measure")
    tables = {
        "fact_prevalence.csv": fact,
        "dim_geography.csv": dim_geo,
        "dim_measure.csv": dim_measure,
        "dim_category.csv": dim_category,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_prevalence.csv": "one row per county × measure × year (crude prevalence)",
        "dim_geography.csv": "one row per county (PK geoid = 5-digit FIPS)",
        "dim_measure.csv": "one row per PLACES measure (PK measure_id)",
        "dim_category.csv": "one row per PLACES category (PK category_id)",
        "dim_year.csv": "one row for the 2024 PLACES release vintage",
    }
    table_docs = {
        "fact_prevalence.csv": "County-level crude prevalence estimates from CDC PLACES 2024.",
        "dim_geography.csv": "County names, state, and 5-digit FIPS.",
        "dim_measure.csv": "Measure labels, units, source survey, and parent category.",
        "dim_category.csv": "PLACES topic categories (outcomes, prevention, unhealthy behaviors, etc.).",
        "dim_year.csv": "Release vintage metadata.",
    }
    desc = {
        "fact_prevalence.csv": {
            "year": "Estimate year",
            "geoid": "County FIPS, zero-padded (FK -> dim_geography.geoid)",
            "measure_id": "PLACES measure id (FK -> dim_measure.measure_id)",
            "data_value": "Crude prevalence (percent or rate); null when suppressed",
            "ci_low": "Lower 95% confidence limit; null when suppressed",
            "ci_high": "Upper 95% confidence limit; null when suppressed",
            "population": "Total county population used as the denominator context",
            "population_18plus": "Adult (18+) county population",
        },
        "dim_geography.csv": {
            "geoid": "5-digit county FIPS (PK)",
            "state_abbr": "Two-letter state abbreviation",
            "state_name": "State name",
            "county_name": "County name",
        },
        "dim_measure.csv": {
            "measure_id": "PLACES measure identifier (PK)",
            "measure": "Full measure text",
            "category": "Category label",
            "category_id": "Category key (FK -> dim_category.category_id)",
            "short_label": "Short question text",
            "unit": "Unit of data_value (usually %)",
            "datasource": "Underlying survey (typically BRFSS)",
        },
        "dim_category.csv": {
            "category_id": "Category key (PK)",
            "category_name": "Category name",
        },
        "dim_year.csv": {
            "release": "PLACES release year (PK)",
            "measure_year": "Primary estimate year in this extract",
            "program": "Program name",
            "title": "Kit title",
        },
    }
    meta = {
        "source": "CDC PLACES: Local Data for Better Health, County Data 2024 release",
        "source_url": "https://data.cdc.gov/500-Cities-Places/PLACES-Local-Data-for-Better-Health-County-Data-20/fu4u-a9bh",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.cdc.gov/other/agencymaterials.html",
        "download_urls": ["https://data.cdc.gov/resource/fu4u-a9bh.csv?$limit=50000"],
        "transforms": [
            f"Downloaded county 2024 release (n={n_raw}).",
            f"Kept only crude prevalence (datavaluetypeid=CrdPrv), dropping age-adjusted duplicates ({n_filt} rows) so grain is county × measure × year.",
            "Zero-padded locationid to 5-digit FIPS geoid.",
            "Split geography, measure, and category into dimension tables.",
        ],
        "extra_files": [],
    }
    slug = "bio-02_cdc_places_county"
    title = "CDC PLACES 2024: county crude prevalence of chronic disease and prevention indicators"
    framing = (
        "Judge whether a county wellness or insurer-embedded fitness program's headline "
        "outcome still holds after decomposing by measure family, state, and county size."
    )
    finalize_kit(
        slug,
        tables=tables,
        grains=grains,
        descriptions=desc,
        table_docs=table_docs,
        meta=meta,
        package_title=title,
        framing=framing,
        join_keys="fact_prevalence.geoid -> dim_geography.geoid ; fact_prevalence.measure_id -> dim_measure.measure_id ; dim_measure.category_id -> dim_category.category_id",
        string_cols={
            "fact_prevalence.csv": {"geoid", "measure_id"},
            "dim_geography.csv": {"geoid", "state_abbr", "state_name", "county_name"},
            "dim_measure.csv": {"measure_id", "category_id"},
            "dim_category.csv": {"category_id"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["registry", "county", "brfss"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


# ---------------------------------------------------------------------------
# 03 NCHS leading causes
# ---------------------------------------------------------------------------
def kit_03():
    print("kit 03 leading causes")
    raw = pd.read_csv(SCRATCH / "nchs/leading_causes.csv")
    raw["year"] = raw["year"].astype("Int64")
    raw["deaths"] = pd.to_numeric(raw["deaths"], errors="coerce")
    raw["aadr"] = pd.to_numeric(raw["aadr"], errors="coerce")
    dim_cause = (
        raw[["cause_name", "_113_cause_name"]]
        .drop_duplicates("cause_name")
        .rename(columns={"_113_cause_name": "cause_113_label"})
        .reset_index(drop=True)
    )
    dim_cause.insert(0, "cause_id", dim_cause["cause_name"].str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_"))
    dim_state = pd.DataFrame({"state_name": sorted(raw["state"].dropna().unique())})
    dim_state["state_name"] = dim_state["state_name"].astype(str)
    cause_map = dict(zip(dim_cause["cause_name"], dim_cause["cause_id"]))
    fact = raw.rename(columns={"state": "state_name", "aadr": "age_adjusted_rate"})[
        ["year", "state_name", "cause_name", "deaths", "age_adjusted_rate"]
    ].copy()
    fact["cause_id"] = fact["cause_name"].map(cause_map)
    fact = fact.drop(columns=["cause_name"])
    dim_year = (
        fact[["year"]]
        .drop_duplicates()
        .sort_values("year")
        .assign(calendar="calendar year", source_table="NCHS Leading Causes of Death, United States")
    )
    qa_no_orphans(fact, dim_cause, "cause_id", "cause_id", "cause")
    qa_no_orphans(fact, dim_state, "state_name", "state_name", "state")
    tables = {
        "fact_deaths.csv": fact,
        "dim_cause.csv": dim_cause,
        "dim_state.csv": dim_state,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_deaths.csv": "one row per state × cause × year",
        "dim_cause.csv": "one row per NCHS 113-cause grouping (PK cause_id)",
        "dim_state.csv": "one row per state or United States total",
        "dim_year.csv": "one row per calendar year present in the series",
    }
    table_docs = {
        "fact_deaths.csv": "Counts and age-adjusted death rates for leading causes by state and year.",
        "dim_cause.csv": "NCHS 113-cause short name and full ICD grouping label.",
        "dim_state.csv": "State names as published (includes United States).",
        "dim_year.csv": "Calendar years covered by the NCHS leading-causes series.",
    }
    desc = {
        "fact_deaths.csv": {
            "year": "Calendar year (FK -> dim_year.year)",
            "state_name": "State or United States (FK -> dim_state.state_name)",
            "deaths": "Number of deaths; null if not reported",
            "age_adjusted_rate": "Age-adjusted death rate per 100,000 (2000 U.S. standard); null if not reported",
            "cause_id": "Cause key (FK -> dim_cause.cause_id)",
        },
        "dim_cause.csv": {
            "cause_id": "Slug key derived from cause_name (PK)",
            "cause_name": "Short NCHS cause name",
            "cause_113_label": "Full 113-cause title with ICD codes",
        },
        "dim_state.csv": {"state_name": "State or national total name (PK)"},
        "dim_year.csv": {
            "year": "Calendar year (PK)",
            "calendar": "Time basis",
            "source_table": "Source table name",
        },
    }
    meta = {
        "source": "NCHS Leading Causes of Death, United States (data.cdc.gov)",
        "source_url": "https://data.cdc.gov/NCHS/NCHS-Leading-Causes-of-Death-United-States/bi63-dtpu",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.cdc.gov/nchs/data_access/restrictions.htm",
        "download_urls": ["https://data.cdc.gov/resource/bi63-dtpu.csv?$limit=50000"],
        "transforms": [
            f"Read {len(raw)} published state-year-cause rows; no rows dropped.",
            "Parsed deaths and age-adjusted rates as numeric.",
            "Derived cause_id slugs from cause_name and split cause/state/year dimensions.",
        ],
        "extra_files": [],
    }
    slug = "bio-03_nchs_leading_causes"
    title = "NCHS leading causes of death by state and year"
    framing = "Judge whether a prevention program's headline mortality drop survives decomposition by cause, state, and year."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_deaths.cause_id -> dim_cause.cause_id ; fact_deaths.state_name -> dim_state.state_name ; fact_deaths.year -> dim_year.year",
        string_cols={"fact_deaths.csv": {"state_name", "cause_id"}, "dim_cause.csv": {"cause_id", "cause_name", "cause_113_label"}, "dim_state.csv": {"state_name"}},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["registry", "mortality"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)
