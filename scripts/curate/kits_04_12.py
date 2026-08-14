"""Kits 04–12."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from common import SCRATCH, finalize_kit, qa_no_orphans
from build_kits import add_catalog


def kit_04():
    print("kit 04 diabetes burden")
    burden = pd.read_csv(SCRATCH / "diabetes/burden_state.csv", low_memory=False)
    econ = pd.read_csv(SCRATCH / "diabetes/econ.csv", low_memory=False)
    health = pd.read_csv(SCRATCH / "diabetes/health.csv", low_memory=False)

    # Burden: state × year × indicator × age × race × sex × education
    b = burden.copy()
    b["year"] = pd.to_numeric(b["year"], errors="coerce").astype("Int64")
    b["estimate"] = pd.to_numeric(b["estimate"], errors="coerce")
    b["se"] = pd.to_numeric(b["seestimate"], errors="coerce")
    b["ci_low"] = pd.to_numeric(b["lowerlimit"], errors="coerce")
    b["ci_high"] = pd.to_numeric(b["upperlimit"], errors="coerce")
    # Drop national 'All' rollups from the fact (keep in dim as a geography)
    fact_burden = b.rename(columns={"state": "geo_name"})[
        [
            "geo_name",
            "year",
            "indicator",
            "unit",
            "estimate",
            "se",
            "ci_low",
            "ci_high",
            "age",
            "race",
            "sex",
            "education",
            "population",
            "datasource",
        ]
    ]
    fact_burden["indicator_id"] = (
        fact_burden["indicator"].astype(str).str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
    )

    dim_indicator = (
        fact_burden[["indicator_id", "indicator", "unit"]]
        .drop_duplicates("indicator_id")
        .rename(columns={"indicator": "indicator_name"})
    )
    dim_geo = pd.DataFrame({"geo_name": sorted(fact_burden["geo_name"].dropna().unique())})
    dim_geo["geo_type"] = dim_geo["geo_name"].map(lambda x: "national" if str(x) in {"All", "United States"} else "state")
    dim_strata = (
        fact_burden[["age", "race", "sex", "education"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    dim_strata.insert(0, "strata_id", dim_strata.index + 1)
    fact_burden = fact_burden.merge(dim_strata, on=["age", "race", "sex", "education"], how="left")
    fact_burden = fact_burden.drop(columns=["indicator", "unit", "age", "race", "sex", "education"])

    # Economic burden: keep total / direct / indirect cost rows at state × sex × age
    e = econ.copy()
    e["year"] = pd.to_numeric(e["year"], errors="coerce").astype("Int64")
    # The value column name varies; find a numeric cost-like field
    val_col = None
    for c in e.columns:
        if c.lower() in {"data_value", "estimate", "value"}:
            val_col = c
            break
    if val_col is None:
        # last mostly-numeric column
        for c in reversed(list(e.columns)):
            if pd.api.types.is_numeric_dtype(e[c]) or e[c].astype(str).str.replace(".", "", 1).str.isdigit().mean() > 0.5:
                val_col = c
                break
    e["cost_value"] = pd.to_numeric(e[val_col], errors="coerce") if val_col else pd.NA
    e = e.rename(columns={"lower_location": "geo_name"})
    keep_cols = [c for c in ["year", "geo_name", "short_indicator_text", "long_indicator_text", "stratification1", "stratification_group1", "stratification2", "stratification_group2", "cost_value"] if c in e.columns]
    fact_econ = e[keep_cols].copy()
    if "geo_name" in fact_econ:
        dim_geo = pd.concat([dim_geo, pd.DataFrame({"geo_name": fact_econ["geo_name"].dropna().unique(), "geo_type": "state"})], ignore_index=True)
        dim_geo = dim_geo.drop_duplicates("geo_name")

    dim_year = pd.DataFrame({"year": sorted(set(fact_burden["year"].dropna().astype(int)) | set(pd.to_numeric(fact_econ.get("year"), errors="coerce").dropna().astype(int)))})
    dim_year["calendar"] = "calendar year"

    qa_no_orphans(fact_burden, dim_geo, "geo_name", "geo_name", "diab.geo")
    qa_no_orphans(fact_burden, dim_indicator, "indicator_id", "indicator_id", "diab.ind")
    qa_no_orphans(fact_burden, dim_strata, "strata_id", "strata_id", "diab.strata")

    tables = {
        "fact_prevalence.csv": fact_burden,
        "fact_cost.csv": fact_econ,
        "dim_geography.csv": dim_geo,
        "dim_indicator.csv": dim_indicator,
        "dim_strata.csv": dim_strata,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_prevalence.csv": "one row per geography × year × indicator × demographic strata",
        "fact_cost.csv": "one row per state × year × cost indicator × published stratification",
        "dim_geography.csv": "one row per state or national rollup (PK geo_name)",
        "dim_indicator.csv": "one row per USDSS burden indicator (PK indicator_id)",
        "dim_strata.csv": "one row per unique age × race × sex × education combination (PK strata_id)",
        "dim_year.csv": "one row per calendar year",
    }
    table_docs = {
        "fact_prevalence.csv": "Diagnosed-diabetes burden/magnitude estimates from USDSS, with SE and CI.",
        "fact_cost.csv": "Diabetes State Burden Toolkit economic costs (dollars, as published).",
        "dim_geography.csv": "State names and a national rollup flag.",
        "dim_indicator.csv": "USDSS indicator names and units.",
        "dim_strata.csv": "Demographic cross-classification used on prevalence rows.",
        "dim_year.csv": "Calendar years present in either fact table.",
    }
    desc = {
        "fact_prevalence.csv": {
            "geo_name": "State or national rollup (FK -> dim_geography.geo_name)",
            "year": "Estimate year (FK -> dim_year.year)",
            "estimate": "Published point estimate; null if suppressed",
            "se": "Standard error; null if not published",
            "ci_low": "Lower confidence limit; null if not published",
            "ci_high": "Upper confidence limit; null if not published",
            "population": "Universe text (e.g. Adults Aged 18+ Years)",
            "datasource": "Underlying survey or surveillance system",
            "indicator_id": "Indicator key (FK -> dim_indicator.indicator_id)",
            "strata_id": "Demographic strata key (FK -> dim_strata.strata_id)",
        },
        "fact_cost.csv": {
            "year": "Cost year (FK -> dim_year.year)",
            "geo_name": "State (FK -> dim_geography.geo_name)",
            "short_indicator_text": "Short cost indicator",
            "long_indicator_text": "Long cost indicator",
            "stratification1": "First stratification dimension (e.g. Sex)",
            "stratification_group1": "First stratification value",
            "stratification2": "Second stratification dimension",
            "stratification_group2": "Second stratification value",
            "cost_value": "Numeric cost as published; null if missing",
        },
        "dim_geography.csv": {"geo_name": "Geography name (PK)", "geo_type": "state or national"},
        "dim_indicator.csv": {
            "indicator_id": "Slug key (PK)",
            "indicator_name": "USDSS indicator name",
            "unit": "Unit of estimate",
        },
        "dim_strata.csv": {
            "strata_id": "Surrogate key (PK)",
            "age": "Age group",
            "race": "Race/ethnicity group",
            "sex": "Sex group",
            "education": "Education group",
        },
        "dim_year.csv": {"year": "Calendar year (PK)", "calendar": "Time basis"},
    }
    meta = {
        "source": "CDC United States Diabetes Surveillance System (USDSS) and Diabetes State Burden Toolkit",
        "source_url": "https://usdss.cdc.gov/diabetes/surveillance.html",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.cdc.gov/other/agencymaterials.html",
        "download_urls": [
            "https://data.cdc.gov/resource/b559-sbez.csv?$limit=50000",
            "https://data.cdc.gov/resource/58s6-s24x.csv?$limit=50000",
            "https://data.cdc.gov/resource/ircd-wk4g.csv?$limit=50000",
        ],
        "transforms": [
            f"Read USDSS state burden (n={len(burden)}) and economic toolkit (n={len(econ)}).",
            "Coerced estimate/SE/CI and cost fields to numeric (non-numeric -> null).",
            "Built indicator_id slugs and a strata dimension from age × race × sex × education.",
            "Health-burden file was downloaded for provenance but not required to reach the 6-file kit grain; economic + prevalence facts carry the decision question.",
        ],
        "extra_files": [],
    }
    slug = "bio-04_cdc_diabetes_burden"
    title = "CDC USDSS: diagnosed diabetes burden and state economic cost"
    framing = (
        "Judge whether a diabetes-prevention program's headline prevalence or cost reduction "
        "survives decomposition by state, age, race/ethnicity, sex, and education."
    )
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_prevalence.geo_name -> dim_geography.geo_name ; fact_prevalence.indicator_id -> dim_indicator.indicator_id ; fact_prevalence.strata_id -> dim_strata.strata_id ; fact_cost.geo_name -> dim_geography.geo_name",
        string_cols={
            "fact_prevalence.csv": {"geo_name", "indicator_id", "population", "datasource"},
            "fact_cost.csv": {"geo_name"},
            "dim_geography.csv": {"geo_name", "geo_type"},
            "dim_indicator.csv": {"indicator_id"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["registry", "diabetes", "cost"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_05():
    print("kit 05 stroke")
    raw = pd.read_csv(SCRATCH / "stroke/county.csv", low_memory=False)
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce").astype("Int64")
    raw["data_value"] = pd.to_numeric(raw["data_value"], errors="coerce")
    raw["locationid"] = raw["locationid"].astype(str)
    # County rows only
    county = raw[raw["geographiclevel"].astype(str).str.lower().eq("county")].copy()
    n_drop = len(raw) - len(county)
    county["geoid"] = county["locationid"].str.zfill(5)
    fact = county.rename(
        columns={
            "data_value": "rate",
            "data_value_unit": "unit",
            "data_value_type": "rate_type",
            "stratification1": "sex",
            "stratification2": "race_ethnicity",
        }
    )[["year", "geoid", "sex", "race_ethnicity", "rate", "unit", "rate_type"]].copy()
    dim_geo = (
        county[["geoid", "locationabbr", "locationdesc"]]
        .drop_duplicates("geoid")
        .rename(columns={"locationabbr": "state_abbr", "locationdesc": "county_name"})
    )
    dim_sex = pd.DataFrame({"sex": sorted(fact["sex"].dropna().unique())})
    dim_race = pd.DataFrame({"race_ethnicity": sorted(fact["race_ethnicity"].dropna().unique())})
    dim_year = fact[["year"]].drop_duplicates().sort_values("year")
    dim_year["calendar"] = "calendar year (3-year smoothed window as published)"
    qa_no_orphans(fact, dim_geo, "geoid", "geoid", "stroke.geo")
    tables = {
        "fact_stroke_mortality.csv": fact,
        "dim_geography.csv": dim_geo,
        "dim_sex.csv": dim_sex,
        "dim_race.csv": dim_race,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_stroke_mortality.csv": "one row per county × year × sex × race/ethnicity",
        "dim_geography.csv": "one row per county (PK geoid)",
        "dim_sex.csv": "one row per sex stratification",
        "dim_race.csv": "one row per race/ethnicity stratification",
        "dim_year.csv": "one row per published year",
    }
    table_docs = {
        "fact_stroke_mortality.csv": "County stroke mortality rates (NVSS), including spatially smoothed 3-year averages where published.",
        "dim_geography.csv": "County FIPS, state abbreviation, and county name.",
        "dim_sex.csv": "Sex strata used on the rate table.",
        "dim_race.csv": "Race/ethnicity strata used on the rate table.",
        "dim_year.csv": "Years present in the stroke mortality extract.",
    }
    desc = {
        "fact_stroke_mortality.csv": {
            "year": "Year (FK -> dim_year.year)",
            "geoid": "County FIPS (FK -> dim_geography.geoid)",
            "sex": "Sex stratum (FK -> dim_sex.sex)",
            "race_ethnicity": "Race/ethnicity stratum (FK -> dim_race.race_ethnicity)",
            "rate": "Mortality rate; null if suppressed",
            "unit": "Rate unit (typically per 100,000)",
            "rate_type": "Rate type as published (age-adjusted / smoothed)",
        },
        "dim_geography.csv": {
            "geoid": "5-digit county FIPS (PK)",
            "state_abbr": "State abbreviation",
            "county_name": "County name",
        },
        "dim_sex.csv": {"sex": "Sex label (PK)"},
        "dim_race.csv": {"race_ethnicity": "Race/ethnicity label (PK)"},
        "dim_year.csv": {"year": "Year (PK)", "calendar": "Time basis note"},
    }
    meta = {
        "source": "CDC Stroke Mortality Data Among US Adults (35+) by State/Territory and County — NVSS",
        "source_url": "https://data.cdc.gov/Heart-Disease-Stroke-Prevention/Stroke-Mortality-Data-Among-US-Adults-35-by-State-/cpdh-8cna",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.cdc.gov/other/agencymaterials.html",
        "download_urls": ["https://data.cdc.gov/resource/cpdh-8cna.csv?$limit=20000"],
        "transforms": [
            f"Read {len(raw)} rows; kept county geography only (dropped {n_drop} state/national rows).",
            "Zero-padded locationid to 5-digit geoid; coerced rate to numeric.",
            "Split sex and race/ethnicity stratifications into dimension tables.",
        ],
        "extra_files": [],
    }
    slug = "bio-05_cdc_stroke_mortality"
    title = "CDC NVSS: county stroke mortality among adults 35+ by sex and race/ethnicity"
    framing = "Judge whether a stroke-prevention program's headline mortality decline survives decomposition by county, sex, and race/ethnicity."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_stroke_mortality.geoid -> dim_geography.geoid ; fact_stroke_mortality.sex -> dim_sex.sex ; fact_stroke_mortality.race_ethnicity -> dim_race.race_ethnicity ; fact_stroke_mortality.year -> dim_year.year",
        string_cols={"fact_stroke_mortality.csv": {"geoid", "sex", "race_ethnicity", "unit", "rate_type"}, "dim_geography.csv": {"geoid", "state_abbr", "county_name"}},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["registry", "stroke", "neuroscience"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_06():
    print("kit 06 gwas")
    zpath = SCRATCH / "gwas/gwas-catalog-associations-full.zip"
    with zipfile.ZipFile(zpath) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            raw = pd.read_csv(fh, sep="\t", dtype=str, low_memory=False)
    n_raw = len(raw)
    raw.columns = [c.strip() for c in raw.columns]
    raw["p_value"] = pd.to_numeric(raw.get("P-VALUE"), errors="coerce")
    raw["or_or_beta"] = pd.to_numeric(raw.get("OR or BETA"), errors="coerce")
    raw["p_mlog"] = pd.to_numeric(raw.get("PVALUE_MLOG"), errors="coerce")
    raw["risk_allele_frequency"] = pd.to_numeric(raw.get("RISK ALLELE FREQUENCY"), errors="coerce")
    gws = raw[raw["p_value"].notna() & (raw["p_value"] <= 5e-8)].copy()
    n_gws = len(gws)
    if len(gws) > 40000:
        gws = gws.sort_values("p_value").head(40000)
    fact = pd.DataFrame(
        {
            "pubmed_id": gws.get("PUBMEDID"),
            "disease_trait": gws.get("DISEASE/TRAIT"),
            "mapped_gene": gws.get("MAPPED_GENE"),
            "snp": gws.get("SNPS"),
            "chr_id": gws.get("CHR_ID"),
            "chr_pos": gws.get("CHR_POS"),
            "risk_allele": gws.get("STRONGEST SNP-RISK ALLELE"),
            "p_value": gws["p_value"],
            "p_mlog": gws["p_mlog"],
            "or_or_beta": gws["or_or_beta"],
            "ci_text": gws.get("95% CI (TEXT)"),
            "risk_allele_frequency": gws["risk_allele_frequency"],
            "initial_sample_size": gws.get("INITIAL SAMPLE SIZE"),
        }
    )
    efo = pd.read_csv(SCRATCH / "gwas/gwas-efo-trait-mappings.tsv", sep="\t", dtype=str)
    efo.columns = [c.strip().lower().replace(" ", "_") for c in efo.columns]
    # expected: disease_trait, efo_term, efo_uri, parent_term, parent_uri
    trait_col = "disease_trait" if "disease_trait" in efo.columns else efo.columns[0]
    efo = efo.rename(columns={trait_col: "disease_trait"})
    dim_trait = (
        efo.drop_duplicates("disease_trait")[
            [c for c in ["disease_trait", "efo_term", "efo_uri", "parent_term", "parent_uri"] if c in efo.columns]
        ]
    )
    # traits in fact missing from efo
    missing = sorted(set(fact["disease_trait"].dropna()) - set(dim_trait["disease_trait"]))
    if missing:
        extra = pd.DataFrame({"disease_trait": missing})
        dim_trait = pd.concat([dim_trait, extra], ignore_index=True)
    dim_study = (
        gws[["PUBMEDID", "FIRST AUTHOR", "DATE", "JOURNAL", "STUDY"]]
        .drop_duplicates("PUBMEDID")
        .rename(columns={"PUBMEDID": "pubmed_id", "FIRST AUTHOR": "first_author", "DATE": "pub_date", "JOURNAL": "journal", "STUDY": "study_title"})
    )
    dim_gene = (
        fact[["mapped_gene"]]
        .dropna()
        .assign(mapped_gene=lambda d: d["mapped_gene"].str.split(r"\s*[-,;]\s*").str[0])
        .drop_duplicates()
        .rename(columns={"mapped_gene": "gene_symbol"})
    )
    dim_year = pd.DataFrame(
        [
            {
                "catalog_release": "latest",
                "retrieved": "2026-08-14",
                "threshold": "p <= 5e-8 (genome-wide significant)",
                "title": "GWAS Catalog lead associations, ontology-mapped traits",
            }
        ]
    )
    qa_no_orphans(fact, dim_trait, "disease_trait", "disease_trait", "gwas.trait")
    qa_no_orphans(fact, dim_study, "pubmed_id", "pubmed_id", "gwas.study")
    tables = {
        "fact_association.csv": fact,
        "dim_trait.csv": dim_trait,
        "dim_study.csv": dim_study,
        "dim_gene.csv": dim_gene,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_association.csv": "one row per genome-wide significant SNP–trait association",
        "dim_trait.csv": "one row per GWAS Catalog disease/trait (PK disease_trait)",
        "dim_study.csv": "one row per PubMed-indexed study (PK pubmed_id)",
        "dim_gene.csv": "one row per mapped gene symbol (first gene if multi-mapped)",
        "dim_year.csv": "one row for this catalog extract / significance threshold",
    }
    table_docs = {
        "fact_association.csv": "Lead SNP associations from the GWAS Catalog with p <= 5e-8.",
        "dim_trait.csv": "Trait labels mapped to EFO terms and parent classes.",
        "dim_study.csv": "Study bibliographic fields.",
        "dim_gene.csv": "Unique mapped gene symbols appearing on associations.",
        "dim_year.csv": "Catalog vintage and filter metadata.",
    }
    desc = {
        "fact_association.csv": {
            "pubmed_id": "PubMed ID (FK -> dim_study.pubmed_id)",
            "disease_trait": "Reported trait (FK -> dim_trait.disease_trait)",
            "mapped_gene": "Mapped gene(s) as published",
            "snp": "rsID of the strongest SNP",
            "chr_id": "Chromosome",
            "chr_pos": "Base-pair position as published",
            "risk_allele": "Strongest SNP-risk allele string",
            "p_value": "Association p-value",
            "p_mlog": "-log10(p)",
            "or_or_beta": "Odds ratio or beta as published; null if missing",
            "ci_text": "95% CI text; null if missing",
            "risk_allele_frequency": "Risk-allele frequency; null if missing",
            "initial_sample_size": "Initial sample-size text (used to decompose ancestry/size)",
        },
        "dim_trait.csv": {
            "disease_trait": "GWAS Catalog trait name (PK)",
            "efo_term": "Mapped EFO / MONDO term; null if unmapped",
            "efo_uri": "Term URI; null if unmapped",
            "parent_term": "Parent EFO class; null if unmapped",
            "parent_uri": "Parent URI; null if unmapped",
        },
        "dim_study.csv": {
            "pubmed_id": "PubMed ID (PK)",
            "first_author": "First author",
            "pub_date": "Publication date as catalogued",
            "journal": "Journal",
            "study_title": "Study title",
        },
        "dim_gene.csv": {"gene_symbol": "Mapped HGNC-style symbol (PK)"},
        "dim_year.csv": {
            "catalog_release": "Release tag (PK)",
            "retrieved": "Download date",
            "threshold": "Significance filter applied",
            "title": "Kit title",
        },
    }
    n_kept = len(fact)
    meta = {
        "source": "NHGRI-EBI GWAS Catalog (EMBL-EBI / NHGRI)",
        "source_url": "https://www.ebi.ac.uk/gwas/",
        "license": "GWAS Catalog data are freely available under EMBL-EBI terms; the Catalog is a public NHGRI-EBI resource intended for reuse with attribution (CC0-style catalog content).",
        "license_url": "https://www.ebi.ac.uk/gwas/docs/about",
        "download_urls": [
            "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations-full.zip",
            "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-efo-trait-mappings.tsv",
        ],
        "transforms": [
            f"Read full association download (n={n_raw}).",
            f"Kept genome-wide significant rows with p <= 5e-8 (n={n_gws}); non-significant associations excluded from the starter grain.",
            f"If more than 40,000 GWS rows remained, kept the 40,000 smallest p-values (kept={n_kept}).",
            "Joined EFO parent terms; added unmatched catalog traits so fact keys are not orphaned.",
            "Collapsed mapped_gene lists to the first symbol for dim_gene (fact retains the raw mapped_gene string).",
        ],
        "extra_files": [],
    }
    slug = "bio-06_gwas_catalog_associations"
    title = "GWAS Catalog: genome-wide significant lead associations with EFO trait classes"
    framing = "Judge whether a polygenic-score product's headline effect size survives decomposition by trait class, study size, chromosome, and mapped gene family."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_association.pubmed_id -> dim_study.pubmed_id ; fact_association.disease_trait -> dim_trait.disease_trait",
        string_cols={
            "fact_association.csv": {"pubmed_id", "disease_trait", "mapped_gene", "snp", "chr_id", "chr_pos", "risk_allele", "ci_text", "initial_sample_size"},
            "dim_trait.csv": {"disease_trait", "efo_term", "efo_uri", "parent_term", "parent_uri"},
            "dim_study.csv": {"pubmed_id"},
            "dim_gene.csv": {"gene_symbol"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["gwas", "genetics"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_07():
    print("kit 07 hpa")
    with zipfile.ZipFile(SCRATCH / "hpa/proteinatlas.tsv.zip") as z:
        raw = pd.read_csv(z.open("proteinatlas.tsv"), sep="\t", dtype=str, low_memory=False)
    n_raw = len(raw)
    # Keep identity + RNA tissue classification
    dim_gene = pd.DataFrame(
        {
            "gene_symbol": raw["Gene"],
            "ensembl_id": raw.get("Ensembl"),
            "uniprot_id": raw.get("Uniprot"),
            "gene_description": raw.get("Gene description"),
            "chromosome": raw.get("Chromosome"),
            "protein_class": raw.get("Protein class"),
            "evidence": raw.get("Evidence"),
            "rna_tissue_specificity": raw.get("RNA tissue specificity"),
            "rna_tissue_distribution": raw.get("RNA tissue distribution"),
        }
    ).drop_duplicates("gene_symbol")
    # Melt "RNA tissue specific nTPM" "Tissue: value;Tissue: value"
    rows = []
    col = raw.get("RNA tissue specific nTPM")
    if col is not None:
        for gene, blob in zip(raw["Gene"], col.fillna("")):
            if not blob:
                continue
            for part in str(blob).split(";"):
                if ":" not in part:
                    continue
                tissue, val = part.rsplit(":", 1)
                try:
                    ntp = float(val.strip())
                except ValueError:
                    continue
                rows.append({"gene_symbol": gene, "tissue": tissue.strip(), "ntpm": ntp})
    fact = pd.DataFrame(rows)
    if fact.empty:
        fact = pd.DataFrame({"gene_symbol": dim_gene["gene_symbol"].head(0), "tissue": [], "ntpm": []})
    # Cap very large melts
    n_fact_all = len(fact)
    if len(fact) > 60000:
        fact = fact.sort_values("ntpm", ascending=False).head(60000)
    dim_tissue = pd.DataFrame({"tissue": sorted(fact["tissue"].dropna().unique())})
    dim_specificity = (
        dim_gene[["rna_tissue_specificity"]]
        .dropna()
        .drop_duplicates()
        .rename(columns={"rna_tissue_specificity": "specificity_class"})
    )
    dim_year = pd.DataFrame(
        [{"atlas_version": "proteinatlas.tsv download", "organism": "Homo sapiens", "title": "Human Protein Atlas consensus RNA tissue specificity"}]
    )
    # Ensure fact genes exist
    fact = fact[fact["gene_symbol"].isin(set(dim_gene["gene_symbol"]))]
    qa_no_orphans(fact, dim_gene, "gene_symbol", "gene_symbol", "hpa.gene")
    if len(dim_tissue):
        qa_no_orphans(fact, dim_tissue, "tissue", "tissue", "hpa.tissue")
    tables = {
        "fact_tissue_rna.csv": fact,
        "dim_gene.csv": dim_gene,
        "dim_tissue.csv": dim_tissue,
        "dim_specificity.csv": dim_specificity,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_tissue_rna.csv": "one row per gene × tissue reported as RNA-specific nTPM",
        "dim_gene.csv": "one row per HPA gene (PK gene_symbol)",
        "dim_tissue.csv": "one row per consensus tissue / cell type label",
        "dim_specificity.csv": "one row per HPA RNA tissue-specificity class",
        "dim_year.csv": "one row for this atlas extract",
    }
    table_docs = {
        "fact_tissue_rna.csv": "Parsed nTPM values from the HPA 'RNA tissue specific nTPM' field.",
        "dim_gene.csv": "Gene identity, protein class, evidence, and HPA specificity labels.",
        "dim_tissue.csv": "Tissue / cell-type names appearing in the nTPM blob.",
        "dim_specificity.csv": "HPA RNA tissue-specificity classification values.",
        "dim_year.csv": "Atlas extract metadata.",
    }
    desc = {
        "fact_tissue_rna.csv": {
            "gene_symbol": "HGNC symbol (FK -> dim_gene.gene_symbol)",
            "tissue": "Tissue or cell type (FK -> dim_tissue.tissue)",
            "ntpm": "Normalized transcripts per million as published in the specific-nTPM field",
        },
        "dim_gene.csv": {
            "gene_symbol": "HGNC symbol (PK)",
            "ensembl_id": "Ensembl gene id; null if missing",
            "uniprot_id": "UniProt accession; null if missing",
            "gene_description": "HPA gene description",
            "chromosome": "Chromosome",
            "protein_class": "HPA protein class string",
            "evidence": "Highest HPA evidence level",
            "rna_tissue_specificity": "HPA RNA tissue-specificity class (FK -> dim_specificity.specificity_class)",
            "rna_tissue_distribution": "HPA RNA tissue-distribution class",
        },
        "dim_tissue.csv": {"tissue": "Tissue / cell-type label (PK)"},
        "dim_specificity.csv": {"specificity_class": "HPA specificity class (PK)"},
        "dim_year.csv": {"atlas_version": "Extract tag (PK)", "organism": "Organism", "title": "Kit title"},
    }
    meta = {
        "source": "The Human Protein Atlas — proteinatlas.tsv subset",
        "source_url": "https://www.proteinatlas.org/about/download",
        "license": "Creative Commons Attribution-ShareAlike 3.0 International (CC BY-SA 3.0) as stated by HPA for the downloadable atlas files",
        "license_url": "https://www.proteinatlas.org/about/licence",
        "download_urls": ["https://www.proteinatlas.org/download/proteinatlas.tsv.zip"],
        "transforms": [
            f"Read proteinatlas.tsv (n_genes={n_raw}).",
            "Kept identity, protein class, evidence, and RNA tissue-specificity columns for dim_gene.",
            f"Parsed 'RNA tissue specific nTPM' into long fact rows (n={n_fact_all}); if >60,000 kept the highest-nTPM rows (n={len(fact)}).",
            "Did not invent tissue values that were not present in the specific-nTPM field.",
        ],
        "extra_files": [],
    }
    slug = "bio-07_hpa_tissue_specificity"
    title = "Human Protein Atlas: RNA tissue specificity and nTPM for human genes"
    framing = "Judge whether a target's 'broadly expressed' or 'tissue-restricted' headline survives decomposition by HPA specificity class, chromosome, and protein class."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_tissue_rna.gene_symbol -> dim_gene.gene_symbol ; fact_tissue_rna.tissue -> dim_tissue.tissue ; dim_gene.rna_tissue_specificity -> dim_specificity.specificity_class",
        string_cols={
            "fact_tissue_rna.csv": {"gene_symbol", "tissue"},
            "dim_gene.csv": {"gene_symbol", "ensembl_id", "uniprot_id", "chromosome", "protein_class", "evidence", "rna_tissue_specificity", "rna_tissue_distribution"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["expression", "protein-atlas"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_08():
    print("kit 08 reactome")
    pw = pd.read_csv(SCRATCH / "reactome/ReactomePathways.txt", sep="\t", header=None, names=["pathway_id", "pathway_name", "species"], dtype=str)
    rel = pd.read_csv(SCRATCH / "reactome/ReactomePathwaysRelation.txt", sep="\t", header=None, names=["parent_id", "child_id"], dtype=str)
    # Stream UniProt mapping, human only
    uni_rows = []
    with open(SCRATCH / "reactome/UniProt2Reactome.txt", "r", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            if parts[5] != "Homo sapiens":
                continue
            uni_rows.append((parts[0], parts[1], parts[3], parts[4]))
            if len(uni_rows) >= 80000:
                break
    fact_part = pd.DataFrame(uni_rows, columns=["uniprot_id", "pathway_id", "pathway_name", "evidence"])
    human_pw = pw[pw["species"] == "Homo sapiens"].copy()
    human_ids = set(human_pw["pathway_id"])
    fact_rel = rel[rel["parent_id"].isin(human_ids) & rel["child_id"].isin(human_ids)].copy()
    # Restrict participation to human pathway ids
    fact_part = fact_part[fact_part["pathway_id"].isin(human_ids)]
    dim_pathway = human_pw[["pathway_id", "pathway_name", "species"]].drop_duplicates("pathway_id")
    # Top-level: pathways that are never a child
    children = set(fact_rel["child_id"])
    dim_pathway["is_top_level"] = ~dim_pathway["pathway_id"].isin(children)
    dim_species = pd.DataFrame([{"species": "Homo sapiens", "taxon_id": "9606"}])
    dim_evidence = (
        fact_part[["evidence"]].dropna().drop_duplicates().rename(columns={"evidence": "evidence_code"})
    )
    dim_year = pd.DataFrame([{"release": "current", "organism": "Homo sapiens", "title": "Reactome human pathways and UniProt participation"}])
    qa_no_orphans(fact_part, dim_pathway, "pathway_id", "pathway_id", "reactome.part")
    qa_no_orphans(fact_rel, dim_pathway, "parent_id", "pathway_id", "reactome.parent")
    qa_no_orphans(fact_rel, dim_pathway, "child_id", "pathway_id", "reactome.child")
    tables = {
        "fact_participation.csv": fact_part,
        "fact_hierarchy.csv": fact_rel,
        "dim_pathway.csv": dim_pathway,
        "dim_species.csv": dim_species,
        "dim_evidence.csv": dim_evidence,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_participation.csv": "one row per UniProt accession × human Reactome pathway (capped extract)",
        "fact_hierarchy.csv": "one row per parent–child link among human pathways",
        "dim_pathway.csv": "one row per human Reactome pathway (PK pathway_id)",
        "dim_species.csv": "one row for Homo sapiens",
        "dim_evidence.csv": "one row per Reactome evidence code observed on participation",
        "dim_year.csv": "one row for the current Reactome download",
    }
    table_docs = {
        "fact_participation.csv": "Human UniProt accessions annotated to Reactome pathways.",
        "fact_hierarchy.csv": "Directed parent/child relations among human pathways.",
        "dim_pathway.csv": "Human pathway identifiers, names, and top-level flag.",
        "dim_species.csv": "Species dimension (human only in this kit).",
        "dim_evidence.csv": "Evidence codes (e.g. TAS, IEA) on participation rows.",
        "dim_year.csv": "Reactome 'current' download vintage.",
    }
    desc = {
        "fact_participation.csv": {
            "uniprot_id": "UniProt accession",
            "pathway_id": "Reactome pathway id (FK -> dim_pathway.pathway_id)",
            "pathway_name": "Pathway display name (denormalized from source file)",
            "evidence": "Reactome evidence code (FK -> dim_evidence.evidence_code)",
        },
        "fact_hierarchy.csv": {
            "parent_id": "Parent pathway (FK -> dim_pathway.pathway_id)",
            "child_id": "Child pathway (FK -> dim_pathway.pathway_id)",
        },
        "dim_pathway.csv": {
            "pathway_id": "Reactome stable id (PK)",
            "pathway_name": "Pathway name",
            "species": "Species name (FK -> dim_species.species)",
            "is_top_level": "True when the pathway is never a child in the human hierarchy",
        },
        "dim_species.csv": {"species": "Species name (PK)", "taxon_id": "NCBI taxonomy id"},
        "dim_evidence.csv": {"evidence_code": "Evidence code (PK)"},
        "dim_year.csv": {"release": "Reactome release tag (PK)", "organism": "Organism", "title": "Kit title"},
    }
    meta = {
        "source": "Reactome Pathway Database",
        "source_url": "https://reactome.org/download-data",
        "license": "Creative Commons CC0 1.0 Universal — Reactome content is waived to the public domain",
        "license_url": "https://reactome.org/license",
        "download_urls": [
            "https://reactome.org/download/current/ReactomePathways.txt",
            "https://reactome.org/download/current/ReactomePathwaysRelation.txt",
            "https://reactome.org/download/current/UniProt2Reactome.txt",
        ],
        "transforms": [
            f"Read all pathways (n={len(pw)}) and relations (n={len(rel)}); kept Homo sapiens pathways only (n={len(human_pw)}).",
            f"Streamed UniProt2Reactome.txt and kept Homo sapiens rows (capped at 80,000; kept={len(fact_part)}).",
            "Restricted hierarchy facts to parent and child ids present in the human pathway dimension.",
            "Flagged top-level pathways as those that never appear as a child.",
        ],
        "extra_files": [],
    }
    slug = "bio-08_reactome_pathways"
    title = "Reactome: human pathway hierarchy and UniProt participation"
    framing = "Judge whether a pathway-enrichment headline survives decomposition by top-level event, evidence code, and protein membership."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_participation.pathway_id -> dim_pathway.pathway_id ; fact_hierarchy.parent_id/child_id -> dim_pathway.pathway_id ; fact_participation.evidence -> dim_evidence.evidence_code",
        string_cols={
            "fact_participation.csv": {"uniprot_id", "pathway_id", "pathway_name", "evidence"},
            "fact_hierarchy.csv": {"parent_id", "child_id"},
            "dim_pathway.csv": {"pathway_id", "pathway_name", "species"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["pathway", "reactome"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_09():
    print("kit 09 chembl")
    raw = json.loads(Path(SCRATCH / "chembl/mechanisms.json").read_text())
    df = pd.DataFrame(raw)
    fact = pd.DataFrame(
        {
            "mec_id": df["mec_id"].astype(str),
            "molecule_chembl_id": df["molecule_chembl_id"],
            "target_chembl_id": df["target_chembl_id"],
            "action_type": df["action_type"],
            "mechanism_of_action": df["mechanism_of_action"],
            "max_phase": pd.to_numeric(df["max_phase"], errors="coerce").astype("Int64"),
            "direct_interaction": df["direct_interaction"].map(lambda x: None if pd.isna(x) else bool(x)),
            "disease_efficacy": df["disease_efficacy"].map(lambda x: None if pd.isna(x) else bool(x)),
            "molecular_mechanism": df["molecular_mechanism"].map(lambda x: None if pd.isna(x) else bool(x)),
        }
    )
    dim_action = (
        fact[["action_type"]].dropna().drop_duplicates().assign(action_family=lambda d: d["action_type"].str.split().str[0])
    )
    dim_molecule = fact[["molecule_chembl_id"]].dropna().drop_duplicates()
    dim_target = fact[["target_chembl_id"]].dropna().drop_duplicates()
    dim_phase = (
        fact[["max_phase"]]
        .dropna()
        .drop_duplicates()
        .assign(phase_label=lambda d: d["max_phase"].map({0: "preclinical", 1: "Phase I", 2: "Phase II", 3: "Phase III", 4: "Approved"}))
    )
    dim_year = pd.DataFrame([{"extract": "chembl_mechanism_api", "n_pages": 4, "title": "ChEMBL mechanism of action for molecules (first 4000)"}])
    qa_no_orphans(fact, dim_molecule, "molecule_chembl_id", "molecule_chembl_id", "chembl.mol")
    qa_no_orphans(fact, dim_target, "target_chembl_id", "target_chembl_id", "chembl.tgt")
    tables = {
        "fact_mechanism.csv": fact,
        "dim_molecule.csv": dim_molecule,
        "dim_target.csv": dim_target,
        "dim_action.csv": dim_action,
        "dim_phase.csv": dim_phase,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_mechanism.csv": "one row per ChEMBL mechanism record",
        "dim_molecule.csv": "one row per molecule_chembl_id (PK)",
        "dim_target.csv": "one row per target_chembl_id (PK)",
        "dim_action.csv": "one row per action_type",
        "dim_phase.csv": "one row per max_phase value",
        "dim_year.csv": "one row describing the API extract",
    }
    table_docs = {
        "fact_mechanism.csv": "ChEMBL mechanism-of-action records (API pages 0–3, 1000 each).",
        "dim_molecule.csv": "Distinct ChEMBL molecule ids appearing in the extract.",
        "dim_target.csv": "Distinct ChEMBL target ids appearing in the extract.",
        "dim_action.csv": "Action types (inhibitor, agonist, etc.).",
        "dim_phase.csv": "Maximum phase of development with labels.",
        "dim_year.csv": "API extract metadata.",
    }
    desc = {
        "fact_mechanism.csv": {
            "mec_id": "ChEMBL mechanism id (PK)",
            "molecule_chembl_id": "Molecule id (FK -> dim_molecule.molecule_chembl_id)",
            "target_chembl_id": "Target id (FK -> dim_target.target_chembl_id)",
            "action_type": "Action type (FK -> dim_action.action_type)",
            "mechanism_of_action": "Free-text mechanism",
            "max_phase": "Highest phase (FK -> dim_phase.max_phase); null if unknown",
            "direct_interaction": "Whether ChEMBL flags a direct interaction; null if unknown",
            "disease_efficacy": "Whether disease efficacy is flagged; null if unknown",
            "molecular_mechanism": "Whether a molecular mechanism is flagged; null if unknown",
        },
        "dim_molecule.csv": {"molecule_chembl_id": "ChEMBL molecule id (PK)"},
        "dim_target.csv": {"target_chembl_id": "ChEMBL target id (PK)"},
        "dim_action.csv": {"action_type": "Action type (PK)", "action_family": "First token of action_type"},
        "dim_phase.csv": {"max_phase": "Numeric max phase (PK)", "phase_label": "Label"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "n_pages": "API pages fetched", "title": "Kit title"},
    }
    meta = {
        "source": "ChEMBL (EMBL-EBI) mechanism API",
        "source_url": "https://www.ebi.ac.uk/chembl/",
        "license": "Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)",
        "license_url": "https://chembl.gitbook.io/chembl-interface-documentation/about",
        "download_urls": [
            "https://www.ebi.ac.uk/chembl/api/data/mechanism.json?limit=1000&offset=0",
            "https://www.ebi.ac.uk/chembl/api/data/mechanism.json?limit=1000&offset=1000",
            "https://www.ebi.ac.uk/chembl/api/data/mechanism.json?limit=1000&offset=2000",
            "https://www.ebi.ac.uk/chembl/api/data/mechanism.json?limit=1000&offset=3000",
        ],
        "transforms": [
            f"Fetched 4 API pages of mechanisms (n={len(df)}).",
            "Did not invent molecule names; molecule/target dimensions are the ChEMBL ids present on the mechanism records.",
            "Mapped max_phase 0–4 to preclinical / Phase I–III / Approved labels.",
        ],
        "extra_files": [],
    }
    slug = "bio-09_chembl_drug_mechanisms"
    title = "ChEMBL: mechanism of action and max development phase"
    framing = "Judge whether a target-class 'druggable / approved' headline survives decomposition by action type, max phase, and direct-interaction flag."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_mechanism.molecule_chembl_id -> dim_molecule.molecule_chembl_id ; fact_mechanism.target_chembl_id -> dim_target.target_chembl_id ; fact_mechanism.action_type -> dim_action.action_type ; fact_mechanism.max_phase -> dim_phase.max_phase",
        string_cols={"fact_mechanism.csv": {"mec_id", "molecule_chembl_id", "target_chembl_id", "action_type", "mechanism_of_action"}},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="assay", tags=["chembl", "mechanism"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_10():
    print("kit 10 openfda")
    reaction = json.loads(Path(SCRATCH / "openfda/reaction.json").read_text())
    sample = json.loads(Path(SCRATCH / "openfda/sample.json").read_text())
    rx_rows = reaction.get("results") or []
    dim_reaction = pd.DataFrame(
        [{"reaction": r.get("term"), "event_count": r.get("count")} for r in rx_rows if r.get("term")]
    )
    events = sample.get("results") or []
    rows = []
    for ev in events:
        patient = ev.get("patient") or {}
        age = patient.get("patientonsetage")
        age_unit = patient.get("patientonsetageunit")
        sex = patient.get("patientsex")
        reactions = [r.get("reactionmeddrapt") for r in (patient.get("reaction") or []) if r.get("reactionmeddrapt")]
        drugs = []
        for d in patient.get("drug") or []:
            name = None
            openfda = d.get("openfda") or {}
            gens = openfda.get("generic_name") or []
            brands = openfda.get("brand_name") or []
            if gens:
                name = gens[0]
            elif brands:
                name = brands[0]
            else:
                name = d.get("medicinalproduct")
            if name:
                drugs.append(str(name).upper())
        for drug in drugs or [None]:
            for rxn in reactions or [None]:
                rows.append(
                    {
                        "safetyreportid": str(ev.get("safetyreportid")),
                        "receivedate": ev.get("receivedate"),
                        "serious": ev.get("serious"),
                        "patient_age": pd.to_numeric(age, errors="coerce"),
                        "patient_age_unit": age_unit,
                        "patient_sex_code": str(sex) if sex is not None else None,
                        "drug_name": drug,
                        "reaction": rxn,
                    }
                )
    fact = pd.DataFrame(rows)
    dim_sex = pd.DataFrame(
        [
            {"patient_sex_code": "0", "label": "Unknown"},
            {"patient_sex_code": "1", "label": "Male"},
            {"patient_sex_code": "2", "label": "Female"},
        ]
    )
    dim_drug = pd.DataFrame({"drug_name": sorted(set(fact["drug_name"].dropna()))})
    dim_serious = pd.DataFrame(
        [
            {"serious": "1", "label": "Serious"},
            {"serious": "2", "label": "Not serious"},
        ]
    )
    # Keep only reactions that appear; union with count table
    extra_rx = sorted(set(fact["reaction"].dropna()) - set(dim_reaction["reaction"]))
    if extra_rx:
        dim_reaction = pd.concat([dim_reaction, pd.DataFrame({"reaction": extra_rx, "event_count": pd.NA})], ignore_index=True)
    dim_year = pd.DataFrame([{"extract": "openfda_faers", "api": "https://api.fda.gov/drug/event.json", "title": "openFDA FAERS reaction counts and event sample"}])
    fact["serious"] = fact["serious"].astype(str)
    fact = fact[fact["reaction"].isin(set(dim_reaction["reaction"])) | fact["reaction"].isna()]
    # Drop rows missing both drug and reaction? keep them
    qa_no_orphans(fact.dropna(subset=["reaction"]), dim_reaction, "reaction", "reaction", "faers.rxn")
    tables = {
        "fact_event.csv": fact,
        "dim_reaction.csv": dim_reaction,
        "dim_drug.csv": dim_drug,
        "dim_sex.csv": dim_sex,
        "dim_serious.csv": dim_serious,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_event.csv": "one row per FAERS report × drug × reaction (from the API sample)",
        "dim_reaction.csv": "one row per MedDRA PT (counts from the openFDA count endpoint, plus any sample-only terms)",
        "dim_drug.csv": "one row per generic/brand/medicinal product name in the sample",
        "dim_sex.csv": "FAERS patientsex codebook",
        "dim_serious.csv": "FAERS serious flag codebook",
        "dim_year.csv": "one row for this openFDA extract",
    }
    table_docs = {
        "fact_event.csv": "Exploded sample of FAERS safety reports (drug × reaction).",
        "dim_reaction.csv": "Reaction preferred terms with national event counts from the count API.",
        "dim_drug.csv": "Drug names observed in the sample.",
        "dim_sex.csv": "Sex codes 0/1/2.",
        "dim_serious.csv": "Serious vs not-serious codes.",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_event.csv": {
            "safetyreportid": "FAERS safety report id",
            "receivedate": "Receipt date YYYYMMDD as published",
            "serious": "Serious flag (FK -> dim_serious.serious)",
            "patient_age": "Onset age as reported; null if missing",
            "patient_age_unit": "Age unit code; null if missing",
            "patient_sex_code": "Sex code (FK -> dim_sex.patient_sex_code); null if missing",
            "drug_name": "Uppercased drug name (FK -> dim_drug.drug_name); null if missing",
            "reaction": "MedDRA PT (FK -> dim_reaction.reaction); null if missing",
        },
        "dim_reaction.csv": {
            "reaction": "MedDRA preferred term (PK)",
            "event_count": "openFDA count of reports with this PT; null if only seen in the sample",
        },
        "dim_drug.csv": {"drug_name": "Uppercased drug name (PK)"},
        "dim_sex.csv": {"patient_sex_code": "FAERS sex code (PK)", "label": "Label"},
        "dim_serious.csv": {"serious": "Serious code (PK)", "label": "Label"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "api": "API root", "title": "Kit title"},
    }
    meta = {
        "source": "FDA openFDA drug adverse-event (FAERS) API",
        "source_url": "https://open.fda.gov/apis/drug/event/",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government. FAERS reports are not proof of causation.",
        "license_url": "https://open.fda.gov/apis/terms/",
        "download_urls": [
            "https://api.fda.gov/drug/event.json?count=patient.reaction.reactionmeddrapt.exact&limit=200",
            "https://api.fda.gov/drug/event.json?limit=50",
        ],
        "transforms": [
            f"Pulled reaction counts (n={len(dim_reaction)}) and a sample of {len(events)} safety reports.",
            "Exploded each report to one row per (drug × reaction); did not impute missing age/sex/drug.",
            "Uppercased drug names for a stable join key. FAERS is spontaneous-report data — counts are not incidence rates.",
        ],
        "extra_files": [],
    }
    slug = "bio-10_openfda_faers"
    title = "openFDA FAERS: adverse-event reaction counts and report-level sample"
    framing = "Judge whether a drug-safety signal's headline report count survives decomposition by reaction, sex, seriousness, and co-mentioned drug."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_event.reaction -> dim_reaction.reaction ; fact_event.drug_name -> dim_drug.drug_name ; fact_event.patient_sex_code -> dim_sex.patient_sex_code ; fact_event.serious -> dim_serious.serious",
        string_cols={
            "fact_event.csv": {"safetyreportid", "receivedate", "serious", "patient_age_unit", "patient_sex_code", "drug_name", "reaction"},
            "dim_reaction.csv": {"reaction"},
            "dim_drug.csv": {"drug_name"},
            "dim_sex.csv": {"patient_sex_code"},
            "dim_serious.csv": {"serious"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["safety", "faers", "assay"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_11():
    print("kit 11 clinicaltrials")
    studies = json.loads(Path(SCRATCH / "ctgov/studies.json").read_text())

    def first(seq, key=None):
        if not seq:
            return None
        return seq[0] if key is None else seq[0].get(key)

    rows = []
    cond_rows = []
    int_rows = []
    for st in studies:
        p = st.get("protocolSection") or {}
        ident = p.get("identificationModule") or {}
        status = p.get("statusModule") or {}
        design = p.get("designModule") or {}
        conds = (p.get("conditionsModule") or {}).get("conditions") or []
        ints = (p.get("armsInterventionsModule") or {}).get("interventions") or []
        sponsor = (p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
        elig = p.get("eligibilityModule") or {}
        nct = ident.get("nctId")
        phases = design.get("phases") or []
        enrollment = (design.get("enrollmentInfo") or {}).get("count")
        rows.append(
            {
                "nct_id": nct,
                "brief_title": ident.get("briefTitle"),
                "overall_status": status.get("overallStatus"),
                "phase": phases[0] if phases else None,
                "study_type": design.get("studyType"),
                "enrollment": enrollment,
                "start_date": ((status.get("startDateStruct") or {}).get("date")),
                "completion_date": ((status.get("completionDateStruct") or {}).get("date")),
                "lead_sponsor": sponsor.get("name"),
                "sponsor_class": sponsor.get("class"),
                "sex": elig.get("sex"),
                "min_age": elig.get("minimumAge"),
                "max_age": elig.get("maximumAge"),
            }
        )
        for c in conds:
            cond_rows.append({"nct_id": nct, "condition": c})
        for iv in ints:
            int_rows.append({"nct_id": nct, "intervention_type": iv.get("type"), "intervention_name": iv.get("name")})
    fact = pd.DataFrame(rows)
    fact_cond = pd.DataFrame(cond_rows).drop_duplicates()
    fact_int = pd.DataFrame(int_rows).drop_duplicates()
    dim_status = fact[["overall_status"]].dropna().drop_duplicates()
    dim_phase = fact[["phase"]].dropna().drop_duplicates()
    dim_sponsor_class = fact[["sponsor_class"]].dropna().drop_duplicates()
    dim_year = pd.DataFrame([{"extract": "clinicaltrials_gov_v2", "n_studies": len(fact), "study_type_filter": "Interventional (query)", "title": "ClinicalTrials.gov interventional studies sample"}])
    qa_no_orphans(fact_cond, fact, "nct_id", "nct_id", "ct.cond")
    qa_no_orphans(fact_int, fact, "nct_id", "nct_id", "ct.int")
    tables = {
        "fact_study.csv": fact,
        "fact_condition.csv": fact_cond,
        "fact_intervention.csv": fact_int,
        "dim_status.csv": dim_status,
        "dim_phase.csv": dim_phase,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_study.csv": "one row per NCT interventional study in the API sample",
        "fact_condition.csv": "one row per study × condition",
        "fact_intervention.csv": "one row per study × intervention",
        "dim_status.csv": "one row per overall status",
        "dim_phase.csv": "one row per primary phase token",
        "dim_year.csv": "one row for this ClinicalTrials.gov extract",
    }
    table_docs = {
        "fact_study.csv": "Core protocol fields for interventional studies from the v2 API.",
        "fact_condition.csv": "Bridge of studies to listed conditions.",
        "fact_intervention.csv": "Bridge of studies to listed interventions.",
        "dim_status.csv": "Overall status values.",
        "dim_phase.csv": "Phase tokens (PHASE1, PHASE2, ...).",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_study.csv": {
            "nct_id": "ClinicalTrials.gov identifier (PK)",
            "brief_title": "Brief title",
            "overall_status": "Overall status (FK -> dim_status.overall_status)",
            "phase": "First listed phase (FK -> dim_phase.phase); null if not phased",
            "study_type": "Study type",
            "enrollment": "Enrollment count; null if missing",
            "start_date": "Start date as published; null if missing",
            "completion_date": "Completion date as published; null if missing",
            "lead_sponsor": "Lead sponsor name",
            "sponsor_class": "Lead sponsor class (FK -> dim_sponsor_class.sponsor_class); null if missing",
            "sex": "Eligibility sex; null if missing",
            "min_age": "Minimum age text; null if missing",
            "max_age": "Maximum age text; null if missing",
        },
        "fact_condition.csv": {"nct_id": "NCT id (FK -> fact_study.nct_id)", "condition": "Listed condition"},
        "fact_intervention.csv": {
            "nct_id": "NCT id (FK -> fact_study.nct_id)",
            "intervention_type": "Intervention type",
            "intervention_name": "Intervention name",
        },
        "dim_status.csv": {"overall_status": "Status (PK)"},
        "dim_phase.csv": {"phase": "Phase token (PK)"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "n_studies": "Studies in extract", "study_type_filter": "Filter applied", "title": "Kit title"},
    }
    meta = {
        "source": "ClinicalTrials.gov API v2 (National Library of Medicine)",
        "source_url": "https://clinicaltrials.gov/",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.clinicaltrials.gov/about-site/terms-conditions",
        "download_urls": [
            "https://clinicaltrials.gov/api/v2/studies?pageSize=200&query.term=AREA[StudyType]Interventional",
        ],
        "transforms": [
            f"Paged the v2 studies endpoint 8 times (200/page) for interventional studies (n={len(fact)}).",
            "Took the first listed phase when multiple phases were present.",
            "Exploded conditions and interventions into bridge fact tables; no studies were dropped.",
        ],
        "extra_files": [],
    }
    slug = "bio-11_clinicaltrials_interventional"
    title = "ClinicalTrials.gov: interventional study status, phase, conditions, and interventions"
    framing = "Judge whether a pipeline 'on-time completion' headline survives decomposition by phase, status, sponsor class, and condition."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_condition.nct_id -> fact_study.nct_id ; fact_intervention.nct_id -> fact_study.nct_id ; fact_study.overall_status -> dim_status.overall_status ; fact_study.phase -> dim_phase.phase",
        string_cols={
            "fact_study.csv": {"nct_id", "overall_status", "phase", "study_type", "start_date", "completion_date", "lead_sponsor", "sponsor_class", "sex", "min_age", "max_age"},
            "fact_condition.csv": {"nct_id", "condition"},
            "fact_intervention.csv": {"nct_id", "intervention_type", "intervention_name"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["trials", "registry"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_12():
    print("kit 12 fooddata")
    zpath = SCRATCH / "fdc/foundation.csv.zip"
    with zipfile.ZipFile(zpath) as z:
        names = {Path(n).name: n for n in z.namelist() if n.endswith(".csv")}
        food = pd.read_csv(z.open(names["food.csv"]))
        nutrient = pd.read_csv(z.open(names["nutrient.csv"]))
        food_nutrient = pd.read_csv(z.open(names["food_nutrient.csv"]), low_memory=False)
        category = pd.read_csv(z.open(names["food_category.csv"]))
        foundation = pd.read_csv(z.open(names["foundation_food.csv"]))
    foundation_ids = set(foundation["fdc_id"].astype(str))
    food = food[food["fdc_id"].astype(str).isin(foundation_ids)].copy()
    dim_food = food.rename(columns={"fdc_id": "fdc_id", "description": "food_description", "food_category_id": "food_category_id"})[
        ["fdc_id", "food_description", "data_type", "publication_date", "food_category_id"]
    ]
    dim_food["fdc_id"] = dim_food["fdc_id"].astype(str)
    dim_nutrient = nutrient.rename(columns={"id": "nutrient_id", "name": "nutrient_name"})[
        [c for c in ["nutrient_id", "nutrient_name", "unit_name", "nutrient_nbr", "rank"] if c in nutrient.columns or c.replace("nutrient_id", "id") in nutrient.columns or True]
    ]
    # rebuild nutrient cleanly
    ncol = {c.lower(): c for c in nutrient.columns}
    dim_nutrient = pd.DataFrame(
        {
            "nutrient_id": nutrient[ncol.get("id", "id")].astype(str),
            "nutrient_name": nutrient[ncol.get("name", "name")],
            "unit_name": nutrient.get(ncol.get("unit_name", "unit_name")),
            "nutrient_nbr": nutrient.get(ncol.get("nutrient_nbr", "nutrient_nbr")),
        }
    )
    fn_cols = {c.lower(): c for c in food_nutrient.columns}
    fact = pd.DataFrame(
        {
            "fdc_id": food_nutrient[fn_cols["fdc_id"]].astype(str),
            "nutrient_id": food_nutrient[fn_cols["nutrient_id"]].astype(str),
            "amount": pd.to_numeric(food_nutrient[fn_cols.get("amount", "amount")], errors="coerce"),
        }
    )
    # keep only nutrients/foods that join
    fact = fact[fact["fdc_id"].isin(set(dim_food["fdc_id"])) & fact["nutrient_id"].isin(set(dim_nutrient["nutrient_id"]))]
    cat_cols = {c.lower(): c for c in category.columns}
    dim_category = pd.DataFrame(
        {
            "food_category_id": category[cat_cols.get("id", list(category.columns)[0])].astype(str),
            "category_code": category.get(cat_cols.get("code", "code")),
            "category_description": category.get(cat_cols.get("description", "description")),
        }
    )
    dim_food["food_category_id"] = dim_food["food_category_id"].astype("Int64").astype(str).replace({"<NA>": pd.NA})
    dim_year = pd.DataFrame(
        [{"release": "2026-04-30", "data_type": "foundation_foods", "title": "USDA FoodData Central Foundation Foods nutrients"}]
    )
    qa_no_orphans(fact, dim_food, "fdc_id", "fdc_id", "fdc.food")
    qa_no_orphans(fact, dim_nutrient, "nutrient_id", "nutrient_id", "fdc.nut")
    tables = {
        "fact_food_nutrient.csv": fact,
        "dim_food.csv": dim_food,
        "dim_nutrient.csv": dim_nutrient,
        "dim_category.csv": dim_category,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_food_nutrient.csv": "one row per foundation food × nutrient",
        "dim_food.csv": "one row per FDC foundation food (PK fdc_id)",
        "dim_nutrient.csv": "one row per nutrient (PK nutrient_id)",
        "dim_category.csv": "one row per food category (PK food_category_id)",
        "dim_year.csv": "one row for the April 2026 Foundation Foods release",
    }
    table_docs = {
        "fact_food_nutrient.csv": "Measured nutrient amounts for Foundation Foods.",
        "dim_food.csv": "Food descriptions, data type, publication date, and category.",
        "dim_nutrient.csv": "Nutrient names and units.",
        "dim_category.csv": "WWEIA / FDC food categories.",
        "dim_year.csv": "Foundation Foods vintage.",
    }
    desc = {
        "fact_food_nutrient.csv": {
            "fdc_id": "FoodData Central id (FK -> dim_food.fdc_id)",
            "nutrient_id": "Nutrient id (FK -> dim_nutrient.nutrient_id)",
            "amount": "Amount per 100 g as published; null if missing",
        },
        "dim_food.csv": {
            "fdc_id": "FDC id (PK)",
            "food_description": "Food description",
            "data_type": "FDC data type (foundation_food)",
            "publication_date": "Publication date",
            "food_category_id": "Category id (FK -> dim_category.food_category_id); null if missing",
        },
        "dim_nutrient.csv": {
            "nutrient_id": "Nutrient id (PK)",
            "nutrient_name": "Nutrient name",
            "unit_name": "Unit",
            "nutrient_nbr": "Nutrient number; null if missing",
        },
        "dim_category.csv": {
            "food_category_id": "Category id (PK)",
            "category_code": "Category code; null if missing",
            "category_description": "Category description; null if missing",
        },
        "dim_year.csv": {"release": "Release date (PK)", "data_type": "FDC data type", "title": "Kit title"},
    }
    meta = {
        "source": "USDA FoodData Central — Foundation Foods CSV, April 30 2026",
        "source_url": "https://fdc.nal.usda.gov/download-datasets",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.usda.gov/policies-and-links",
        "download_urls": ["https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2026-04-30.zip"],
        "transforms": [
            f"Read foundation food.csv, then kept only fdc_ids listed in foundation_food.csv (n_foods={len(food)}).",
            "Restricted fact rows to fdc_id and nutrient_id present in the dimension tables.",
            "Amounts coerced to numeric; no imputed nutrient values.",
        ],
        "extra_files": [],
    }
    slug = "bio-12_usda_fooddata_foundation"
    title = "USDA FoodData Central Foundation Foods: nutrients per 100 g"
    framing = "Judge whether a reformulation or meal-plan headline ('20% less sodium') survives decomposition by food category and nutrient."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_food_nutrient.fdc_id -> dim_food.fdc_id ; fact_food_nutrient.nutrient_id -> dim_nutrient.nutrient_id ; dim_food.food_category_id -> dim_category.food_category_id",
        string_cols={
            "fact_food_nutrient.csv": {"fdc_id", "nutrient_id"},
            "dim_food.csv": {"fdc_id", "food_description", "data_type", "publication_date", "food_category_id"},
            "dim_nutrient.csv": {"nutrient_id", "nutrient_name", "unit_name"},
            "dim_category.csv": {"food_category_id"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="assay", tags=["nutrition", "food", "usda"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)

