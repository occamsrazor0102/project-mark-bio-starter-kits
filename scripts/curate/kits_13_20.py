"""Kits 13–20."""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

import pandas as pd

from common import SCRATCH, finalize_kit, qa_no_orphans
from build_kits import add_catalog


def kit_13():
    print("kit 13 clinvar")
    raw = pd.read_csv(SCRATCH / "clinvar/gene_specific_summary.txt", sep="\t", comment=None, skiprows=1, dtype=str)
    raw.columns = [c.lstrip("#") for c in raw.columns]
    for c in [
        "Total_submissions",
        "Total_alleles",
        "Submissions_reporting_this_gene",
        "Alleles_reported_Pathogenic_Likely_pathogenic",
        "Number_uncertain",
        "Number_with_conflicts",
    ]:
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    fact = pd.DataFrame(
        {
            "gene_symbol": raw.get("Symbol"),
            "gene_id": raw.get("GeneID"),
            "total_submissions": raw.get("Total_submissions"),
            "total_alleles": raw.get("Total_alleles"),
            "pathogenic_likely_pathogenic_alleles": raw.get("Alleles_reported_Pathogenic_Likely_pathogenic"),
            "uncertain_alleles": raw.get("Number_uncertain"),
            "conflict_alleles": raw.get("Number_with_conflicts"),
            "mim_number": raw.get("Gene_MIM_number"),
        }
    )
    fact = fact.dropna(subset=["gene_symbol"])
    fact["yield_bin"] = pd.cut(
        fact["pathogenic_likely_pathogenic_alleles"].fillna(0),
        bins=[-0.1, 0, 5, 20, 100, 1e9],
        labels=["none", "1-5", "6-20", "21-100", "100+"],
    ).astype(str)
    dim_gene = fact[["gene_symbol", "gene_id", "mim_number"]].drop_duplicates("gene_symbol")
    dim_yield = pd.DataFrame(
        {
            "yield_bin": ["none", "1-5", "6-20", "21-100", "100+"],
            "bin_label": ["No P/LP alleles", "1–5 P/LP alleles", "6–20 P/LP alleles", "21–100 P/LP alleles", "More than 100 P/LP alleles"],
        }
    )
    dim_mim = (
        fact.loc[fact["mim_number"].notna() & (fact["mim_number"].astype(str).str.len() > 0), ["mim_number"]]
        .drop_duplicates()
        .assign(in_omim=True)
    )
    dim_year = pd.DataFrame(
        [{"snapshot": "2026-08-08", "source_file": "gene_specific_summary.txt", "title": "ClinVar pathogenic yield by gene"}]
    )
    qa_no_orphans(fact, dim_gene, "gene_symbol", "gene_symbol", "clinvar.gene")
    qa_no_orphans(fact, dim_yield, "yield_bin", "yield_bin", "clinvar.yield")
    tables = {
        "fact_gene_yield.csv": fact.drop(columns=["gene_id", "mim_number"]),
        "dim_gene.csv": dim_gene,
        "dim_yield_bin.csv": dim_yield,
        "dim_mim.csv": dim_mim,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_gene_yield.csv": "one row per gene in ClinVar with submission and P/LP allele counts",
        "dim_gene.csv": "one row per gene symbol (PK gene_symbol) with NCBI GeneID and MIM",
        "dim_yield_bin.csv": "one row per P/LP-allele count bin",
        "dim_mim.csv": "one row per OMIM MIM number observed",
        "dim_year.csv": "one row for the ClinVar gene-summary snapshot date",
    }
    table_docs = {
        "fact_gene_yield.csv": "ClinVar per-gene counts of submissions, alleles, P/LP alleles, VUS, and conflicts.",
        "dim_gene.csv": "Gene identity (symbol, GeneID, MIM).",
        "dim_yield_bin.csv": "Bins used to decompose 'high yield' panel claims.",
        "dim_mim.csv": "OMIM identifiers present on at least one gene.",
        "dim_year.csv": "ClinVar file date (header of gene_specific_summary.txt).",
    }
    desc = {
        "fact_gene_yield.csv": {
            "gene_symbol": "Gene symbol (FK -> dim_gene.gene_symbol)",
            "total_submissions": "ClinVar submissions for the gene; null if not reported",
            "total_alleles": "Distinct alleles; null if not reported",
            "pathogenic_likely_pathogenic_alleles": "Alleles reported Pathogenic or Likely pathogenic; null if not reported",
            "uncertain_alleles": "Uncertain-significance alleles; null if not reported",
            "conflict_alleles": "Alleles with conflicting interpretations; null if not reported",
            "yield_bin": "P/LP count bin (FK -> dim_yield_bin.yield_bin)",
        },
        "dim_gene.csv": {
            "gene_symbol": "Gene symbol (PK)",
            "gene_id": "NCBI GeneID",
            "mim_number": "OMIM number; null if none listed",
        },
        "dim_yield_bin.csv": {"yield_bin": "Bin key (PK)", "bin_label": "Human label"},
        "dim_mim.csv": {"mim_number": "OMIM id (PK)", "in_omim": "Always true for rows in this table"},
        "dim_year.csv": {"snapshot": "ClinVar file date (PK)", "source_file": "Source filename", "title": "Kit title"},
    }
    meta = {
        "source": "NCBI ClinVar gene_specific_summary (tab-delimited)",
        "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        "download_urls": ["https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/gene_specific_summary.txt"],
        "transforms": [
            f"Read gene_specific_summary.txt (n={len(raw)}); skipped the banner comment row.",
            "Coerced count columns to numeric (dashes / empty -> null).",
            "Binned P/LP allele counts into none / 1-5 / 6-20 / 21-100 / 100+ for panel-yield decomposition.",
            "Dropped rows with no gene symbol. No individual-level variant records are included.",
        ],
        "extra_files": [],
    }
    slug = "bio-13_clinvar_gene_yield"
    title = "ClinVar: pathogenic / likely-pathogenic allele yield by gene"
    framing = "Judge whether a sequencing panel's 'high diagnostic yield' headline survives decomposition by gene, OMIM status, and P/LP-allele bin."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_gene_yield.gene_symbol -> dim_gene.gene_symbol ; fact_gene_yield.yield_bin -> dim_yield_bin.yield_bin ; dim_gene.mim_number -> dim_mim.mim_number",
        string_cols={"fact_gene_yield.csv": {"gene_symbol", "yield_bin"}, "dim_gene.csv": {"gene_symbol", "gene_id", "mim_number"}, "dim_mim.csv": {"mim_number"}},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["clinvar", "diagnostics", "genetics"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_14():
    print("kit 14 iedb")
    zpath = SCRATCH / "iedb/tcell_full_v3.zip"
    keep_cols = [
        "IEDB IRI",
        "PMID",
        "Name",
        "Object Type",
        "Source Organism",
        "Species",
        "Name.2",
        "Sex",
        "Method",
        "Qualitative Measurement",
        "Quantitative measurement",
        "Name.10",
        "Response Frequency (%)",
    ]
    with zipfile.ZipFile(zpath) as z:
        with z.open(z.namelist()[0]) as fh:
            raw = pd.read_csv(fh, header=1, dtype=str, low_memory=False, usecols=lambda c: c in keep_cols)
    n_raw = len(raw)
    df = pd.DataFrame(
        {
            "assay_iri": raw.get("IEDB IRI"),
            "pmid": raw.get("PMID"),
            "epitope_name": raw.get("Name"),
            "epitope_type": raw.get("Object Type"),
            "source_organism": raw.get("Source Organism"),
            "source_species": raw.get("Species"),
            "host_name": raw.get("Name.2"),
            "host_sex": raw.get("Sex"),
            "mhc_allele": raw.get("Name.10"),
            "assay_method": raw.get("Method"),
            "qualitative": raw.get("Qualitative Measurement"),
            "quantitative": pd.to_numeric(raw.get("Quantitative measurement"), errors="coerce"),
            "response_frequency": pd.to_numeric(raw.get("Response Frequency (%)"), errors="coerce"),
        }
    )
    # Prefer human hosts when identifiable
    human_mask = df["host_name"].fillna("").str.contains("Homo sapiens", case=False) | df["source_species"].fillna("").str.contains("Homo sapiens", case=False)
    human = df[human_mask].copy()
    n_human = len(human)
    if n_human == 0:
        human = df.copy()
    if len(human) > 25000:
        human = human.head(25000)
    human = human.dropna(subset=["assay_iri"])
    dim_epitope = human[["epitope_name", "epitope_type"]].dropna(subset=["epitope_name"]).drop_duplicates("epitope_name")
    dim_host = human[["host_name"]].dropna().drop_duplicates()
    dim_organism = human[["source_organism", "source_species"]].dropna(subset=["source_organism"]).drop_duplicates("source_organism")
    dim_qual = human[["qualitative"]].dropna().drop_duplicates()
    dim_year = pd.DataFrame([{"extract": "iedb_tcell_full_v3", "host_filter": "Homo sapiens when present", "title": "IEDB T-cell epitope assays"}])
    # Attach only epitopes/hosts that exist
    human = human[human["epitope_name"].isin(set(dim_epitope["epitope_name"])) | human["epitope_name"].isna()]
    qa_no_orphans(human.dropna(subset=["epitope_name"]), dim_epitope, "epitope_name", "epitope_name", "iedb.epitope")
    tables = {
        "fact_assay.csv": human,
        "dim_epitope.csv": dim_epitope,
        "dim_host.csv": dim_host,
        "dim_organism.csv": dim_organism,
        "dim_qualitative.csv": dim_qual,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_assay.csv": "one row per IEDB T-cell assay (human-preferring extract, capped)",
        "dim_epitope.csv": "one row per epitope name (PK epitope_name)",
        "dim_host.csv": "one row per host organism / strain name",
        "dim_organism.csv": "one row per epitope source organism",
        "dim_qualitative.csv": "one row per qualitative outcome label",
        "dim_year.csv": "one row for this IEDB extract",
    }
    table_docs = {
        "fact_assay.csv": "T-cell assay records from IEDB tcell_full_v3 (selected columns).",
        "dim_epitope.csv": "Epitope names and object types (linear peptide, etc.).",
        "dim_host.csv": "Host names as recorded by IEDB.",
        "dim_organism.csv": "Source organism / species of the epitope.",
        "dim_qualitative.csv": "Qualitative assay outcomes when present in the first 50 columns.",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_assay.csv": {
            "assay_iri": "IEDB assay IRI (PK)",
            "pmid": "PubMed id; null if submission-only",
            "epitope_name": "Epitope sequence or name (FK -> dim_epitope.epitope_name); null if missing",
            "epitope_type": "Epitope object type",
            "source_organism": "Source organism (FK -> dim_organism.source_organism); null if missing",
            "source_species": "Source species",
            "host_name": "Host name (FK -> dim_host.host_name); null if missing",
            "host_sex": "Host sex; null if missing",
            "mhc_allele": "MHC allele (IEDB Name.10); null if missing",
            "assay_method": "Assay method (e.g. multimer/tetramer); null if missing",
            "qualitative": "Qualitative outcome (Positive/Negative); null if missing",
            "quantitative": "Quantitative measurement; null if missing",
            "response_frequency": "Response frequency percent; null if missing",
        },
        "dim_epitope.csv": {"epitope_name": "Epitope name (PK)", "epitope_type": "Object type"},
        "dim_host.csv": {"host_name": "Host name (PK)"},
        "dim_organism.csv": {"source_organism": "Source organism (PK)", "source_species": "Species"},
        "dim_qualitative.csv": {"qualitative": "Qualitative label (PK)"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "host_filter": "Filter note", "title": "Kit title"},
    }
    meta = {
        "source": "Immune Epitope Database (IEDB) T-cell full export v3",
        "source_url": "https://www.iedb.org/",
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0) — IEDB terms of use",
        "license_url": "https://help.iedb.org/hc/en-us/articles/114094147751",
        "download_urls": ["https://www.iedb.org/downloader.php?file_name=doc/tcell_full_v3.zip"],
        "transforms": [
            f"Read tcell_full_v3.csv using the second header row (n={n_raw}); kept the first 50 columns.",
            f"Preferred rows whose host or species contains 'Homo sapiens' (n={n_human}); if none matched, kept all rows.",
            f"Capped the extract at 25,000 assays (kept={len(human)}) so the starter kit stays portable. Filtering is logged, not silent.",
            "No imputed MHC or qualitative values when those columns were absent from the first 50 fields.",
        ],
        "extra_files": [],
    }
    slug = "bio-14_iedb_tcell_epitopes"
    title = "IEDB: T-cell epitope assays (human-preferring extract)"
    framing = "Judge whether a vaccine epitope's 'immunodominant' headline survives decomposition by host, source organism, epitope type, and qualitative outcome."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_assay.epitope_name -> dim_epitope.epitope_name ; fact_assay.host_name -> dim_host.host_name ; fact_assay.source_organism -> dim_organism.source_organism",
        string_cols={c: set(tables[c].columns) - {"dummy"} for c in tables},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="assay", tags=["immunology", "epitope", "iedb"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_15():
    print("kit 15 goa")
    exp_codes = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "TAS", "IC", "HTP", "HDA", "HMP", "HGI", "HEP"}
    rows = []
    with gzip.open(SCRATCH / "goa/goa_human.gaf.gz", "rt", errors="replace") as fh:
        for line in fh:
            if line.startswith("!"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15:
                continue
            evidence = parts[6]
            if evidence not in exp_codes:
                continue
            rows.append(
                {
                    "db": parts[0],
                    "db_object_id": parts[1],
                    "db_object_symbol": parts[2],
                    "qualifier": parts[3] or None,
                    "go_id": parts[4],
                    "evidence_code": evidence,
                    "aspect": parts[8],
                    "db_object_name": parts[9] or None,
                    "db_object_type": parts[11],
                    "taxon": parts[12],
                    "assigned_by": parts[14],
                }
            )
            if len(rows) >= 40000:
                break
    fact = pd.DataFrame(rows)
    dim_gene = fact[["db_object_id", "db_object_symbol", "db_object_name", "db_object_type"]].drop_duplicates("db_object_id")
    dim_go = fact[["go_id", "aspect"]].drop_duplicates("go_id")
    dim_evidence = (
        fact[["evidence_code"]]
        .drop_duplicates()
        .assign(
            evidence_group=lambda d: d["evidence_code"].map(
                lambda c: "experimental" if c in {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP"} else ("high-throughput" if c.startswith("H") else "author")
            )
        )
    )
    dim_aspect = pd.DataFrame(
        [
            {"aspect": "F", "aspect_name": "molecular function"},
            {"aspect": "P", "aspect_name": "biological process"},
            {"aspect": "C", "aspect_name": "cellular component"},
        ]
    )
    dim_year = pd.DataFrame([{"gaf_date": "2026-07-28", "gaf_version": "2.2", "title": "GOA human experimental annotations"}])
    qa_no_orphans(fact, dim_gene, "db_object_id", "db_object_id", "goa.gene")
    qa_no_orphans(fact, dim_go, "go_id", "go_id", "goa.go")
    tables = {
        "fact_annotation.csv": fact,
        "dim_gene.csv": dim_gene,
        "dim_go.csv": dim_go,
        "dim_evidence.csv": dim_evidence,
        "dim_aspect.csv": dim_aspect,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_annotation.csv": "one row per GO annotation (experimental / TAS / HTP extract, capped)",
        "dim_gene.csv": "one row per UniProt accession (PK db_object_id)",
        "dim_go.csv": "one row per GO term observed (PK go_id)",
        "dim_evidence.csv": "one row per evidence code",
        "dim_aspect.csv": "one row per GO aspect (F/P/C)",
        "dim_year.csv": "one row for this GOA GAF vintage",
    }
    table_docs = {
        "fact_annotation.csv": "Human GO annotations restricted to experimental, author-statement, and HTP evidence.",
        "dim_gene.csv": "UniProt accessions, symbols, and object types.",
        "dim_go.csv": "GO term ids with aspect.",
        "dim_evidence.csv": "Evidence codes grouped as experimental / high-throughput / author.",
        "dim_aspect.csv": "GO aspect codebook.",
        "dim_year.csv": "GAF generation date from the file header.",
    }
    desc = {
        "fact_annotation.csv": {
            "db": "Source database (UniProtKB)",
            "db_object_id": "UniProt accession (FK -> dim_gene.db_object_id)",
            "db_object_symbol": "Gene / product symbol",
            "qualifier": "GO qualifier (e.g. NOT); null if empty",
            "go_id": "GO term (FK -> dim_go.go_id)",
            "evidence_code": "Evidence code (FK -> dim_evidence.evidence_code)",
            "aspect": "F/P/C (FK -> dim_aspect.aspect)",
            "db_object_name": "Product name; null if empty",
            "db_object_type": "Object type (protein)",
            "taxon": "Taxon string",
            "assigned_by": "Assigning group",
        },
        "dim_gene.csv": {
            "db_object_id": "UniProt accession (PK)",
            "db_object_symbol": "Symbol",
            "db_object_name": "Name; null if empty",
            "db_object_type": "Object type",
        },
        "dim_go.csv": {"go_id": "GO id (PK)", "aspect": "Aspect"},
        "dim_evidence.csv": {"evidence_code": "Evidence code (PK)", "evidence_group": "experimental / high-throughput / author"},
        "dim_aspect.csv": {"aspect": "Aspect code (PK)", "aspect_name": "Aspect name"},
        "dim_year.csv": {"gaf_date": "GAF date (PK)", "gaf_version": "GAF version", "title": "Kit title"},
    }
    meta = {
        "source": "GOA Human (UniProt-GOA) gene association file",
        "source_url": "https://www.ebi.ac.uk/GOA/",
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0) — Gene Ontology Consortium / UniProt-GOA",
        "license_url": "https://geneontology.org/docs/go-citation-policy/",
        "download_urls": ["https://ftp.ebi.ac.uk/pub/databases/GO/goa/HUMAN/goa_human.gaf.gz"],
        "transforms": [
            "Streamed goa_human.gaf.gz (GAF 2.2, generated 2026-07-28).",
            "Kept evidence codes in EXP/IDA/IPI/IMP/IGI/IEP/TAS/IC/HTP/HDA/HMP/HGI/HEP (IEA electronic annotations excluded from the starter grain).",
            f"Capped at 40,000 annotation rows (kept={len(fact)}) after the evidence filter.",
            "Split gene, GO term, evidence, and aspect into dimensions.",
        ],
        "extra_files": [],
    }
    slug = "bio-15_goa_human_annotations"
    title = "GOA human: experimental and author-statement Gene Ontology annotations"
    framing = "Judge whether a gene-set 'enriched for process X' headline survives decomposition by evidence code, aspect, and qualifier."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_annotation.db_object_id -> dim_gene.db_object_id ; fact_annotation.go_id -> dim_go.go_id ; fact_annotation.evidence_code -> dim_evidence.evidence_code ; fact_annotation.aspect -> dim_aspect.aspect",
        string_cols={
            "fact_annotation.csv": {"db", "db_object_id", "db_object_symbol", "qualifier", "go_id", "evidence_code", "aspect", "db_object_type", "taxon", "assigned_by"},
            "dim_gene.csv": {"db_object_id", "db_object_symbol", "db_object_type"},
            "dim_go.csv": {"go_id", "aspect"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["go", "annotation", "biostatistics"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_16():
    print("kit 16 orange book")
    with zipfile.ZipFile(SCRATCH / "orange/orangebook.zip") as z:
        products = pd.read_csv(z.open("products.txt"), sep="~", dtype=str, encoding="latin-1")
        exclusivity = pd.read_csv(z.open("exclusivity.txt"), sep="~", dtype=str, encoding="latin-1")
        patent = pd.read_csv(z.open("patent.txt"), sep="~", dtype=str, encoding="latin-1")
    products.columns = [c.strip() for c in products.columns]
    exclusivity.columns = [c.strip() for c in exclusivity.columns]
    patent.columns = [c.strip() for c in patent.columns]
    products["product_key"] = products["Appl_Type"] + "-" + products["Appl_No"] + "-" + products["Product_No"]
    exclusivity["product_key"] = exclusivity["Appl_Type"] + "-" + exclusivity["Appl_No"] + "-" + exclusivity["Product_No"]
    patent["product_key"] = patent["Appl_Type"] + "-" + patent["Appl_No"] + "-" + patent["Product_No"]
    dim_product = products.rename(
        columns={
            "Ingredient": "ingredient",
            "DF;Route": "df_route",
            "Trade_Name": "trade_name",
            "Applicant": "applicant",
            "Strength": "strength",
            "Appl_Type": "appl_type",
            "Appl_No": "appl_no",
            "Product_No": "product_no",
            "TE_Code": "te_code",
            "Approval_Date": "approval_date",
            "RLD": "rld",
            "RS": "rs",
            "Type": "marketing_type",
            "Applicant_Full_Name": "applicant_full_name",
        }
    )
    fact_ex = exclusivity.rename(columns={"Exclusivity_Code": "exclusivity_code", "Exclusivity_Date": "exclusivity_date"})[
        ["product_key", "exclusivity_code", "exclusivity_date"]
    ]
    fact_pat = patent.rename(
        columns={
            "Patent_No": "patent_no",
            "Patent_Expire_Date_Text": "patent_expire_date",
            "Patent_Use_Code": "patent_use_code",
            "Drug_Substance_Flag": "drug_substance_flag",
            "Drug_Product_Flag": "drug_product_flag",
        }
    )[["product_key", "patent_no", "patent_expire_date", "patent_use_code", "drug_substance_flag", "drug_product_flag"]]
    # Keep only keys that exist in products
    keys = set(dim_product["product_key"])
    n_ex_drop = int((~fact_ex["product_key"].isin(keys)).sum())
    n_pat_drop = int((~fact_pat["product_key"].isin(keys)).sum())
    fact_ex = fact_ex[fact_ex["product_key"].isin(keys)]
    fact_pat = fact_pat[fact_pat["product_key"].isin(keys)]
    dim_appl_type = dim_product[["appl_type"]].dropna().drop_duplicates().assign(
        appl_type_label=lambda d: d["appl_type"].map({"N": "NDA", "A": "ANDA"}).fillna(d["appl_type"])
    )
    dim_marketing = dim_product[["marketing_type"]].dropna().drop_duplicates()
    dim_year = pd.DataFrame([{"extract": "fda_orange_book", "title": "FDA Orange Book products, exclusivity, and patents"}])
    qa_no_orphans(fact_ex, dim_product, "product_key", "product_key", "ob.ex")
    qa_no_orphans(fact_pat, dim_product, "product_key", "product_key", "ob.pat")
    tables = {
        "fact_exclusivity.csv": fact_ex,
        "fact_patent.csv": fact_pat,
        "dim_product.csv": dim_product,
        "dim_appl_type.csv": dim_appl_type,
        "dim_marketing.csv": dim_marketing,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_exclusivity.csv": "one row per product × exclusivity code",
        "fact_patent.csv": "one row per product × patent number",
        "dim_product.csv": "one row per Orange Book product (PK product_key)",
        "dim_appl_type.csv": "one row per application type (NDA/ANDA)",
        "dim_marketing.csv": "one row per marketing type (RX/OTC/DISCN)",
        "dim_year.csv": "one row for this Orange Book extract",
    }
    table_docs = {
        "fact_exclusivity.csv": "Statutory exclusivity codes and expiration dates.",
        "fact_patent.csv": "Listed patents and expiration dates.",
        "dim_product.csv": "Approved drug products (ingredient, route, applicant, approval date).",
        "dim_appl_type.csv": "Application type codebook.",
        "dim_marketing.csv": "Marketing type codebook.",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_exclusivity.csv": {
            "product_key": "Appl_Type-Appl_No-Product_No (FK -> dim_product.product_key)",
            "exclusivity_code": "Exclusivity code",
            "exclusivity_date": "Exclusivity expiration date text",
        },
        "fact_patent.csv": {
            "product_key": "Product key (FK -> dim_product.product_key)",
            "patent_no": "Patent number",
            "patent_expire_date": "Patent expiration date text",
            "patent_use_code": "Use code; null if none",
            "drug_substance_flag": "Substance flag; null if none",
            "drug_product_flag": "Product flag; null if none",
        },
        "dim_product.csv": {
            "ingredient": "Active ingredient",
            "df_route": "Dosage form and route",
            "trade_name": "Trade name",
            "applicant": "Applicant short name",
            "strength": "Strength",
            "appl_type": "Application type (FK -> dim_appl_type.appl_type)",
            "appl_no": "Application number",
            "product_no": "Product number",
            "te_code": "Therapeutic equivalence code; null if none",
            "approval_date": "Approval date text",
            "rld": "Reference listed drug flag",
            "rs": "Reference standard flag",
            "marketing_type": "RX / OTC / DISCN (FK -> dim_marketing.marketing_type)",
            "applicant_full_name": "Applicant full name",
            "product_key": "Composite product key (PK)",
        },
        "dim_appl_type.csv": {"appl_type": "Type code (PK)", "appl_type_label": "NDA or ANDA"},
        "dim_marketing.csv": {"marketing_type": "Marketing type (PK)"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "title": "Kit title"},
    }
    meta = {
        "source": "FDA Orange Book data files (products, exclusivity, patents)",
        "source_url": "https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.fda.gov/about-fda/about-website/website-policies",
        "download_urls": ["https://www.fda.gov/media/76860/download"],
        "transforms": [
            f"Read tilde-delimited products (n={len(products)}), exclusivity (n={len(exclusivity)}), patents (n={len(patent)}) as latin-1.",
            "Built product_key = Appl_Type-Appl_No-Product_No.",
            f"Dropped exclusivity ({n_ex_drop}) and patent ({n_pat_drop}) rows whose product_key was not in products.txt so facts have no orphans.",
        ],
        "extra_files": [],
    }
    slug = "bio-16_orange_book_products"
    title = "FDA Orange Book: approved products, exclusivity, and listed patents"
    framing = "Judge whether a generic-entry or 'exclusivity cliff' headline survives decomposition by application type, marketing status, and exclusivity code."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_exclusivity.product_key -> dim_product.product_key ; fact_patent.product_key -> dim_product.product_key ; dim_product.appl_type -> dim_appl_type.appl_type ; dim_product.marketing_type -> dim_marketing.marketing_type",
        string_cols={name: set(df.columns) for name, df in tables.items() if name != "dim_year.csv"},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["regulatory", "fda"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_17():
    print("kit 17 owid")
    raw = pd.read_csv(SCRATCH / "owid/vaccinations.csv", low_memory=False)
    n_raw = len(raw)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw = raw.dropna(subset=["date", "location"])
    # Latest observation per location
    latest = raw.sort_values("date").groupby("location", as_index=False).tail(1)
    fact_latest = latest.rename(columns={"location": "entity"})[
        [
            "entity",
            "iso_code",
            "date",
            "total_vaccinations",
            "people_vaccinated",
            "people_fully_vaccinated",
            "total_boosters",
            "people_vaccinated_per_hundred",
            "people_fully_vaccinated_per_hundred",
        ]
    ]
    fact_latest["date"] = fact_latest["date"].dt.strftime("%Y-%m-%d")
    # Monthly snapshot: last obs per entity × year-month, then keep 2021-2023 to bound size
    raw["year_month"] = raw["date"].dt.to_period("M").astype(str)
    monthly = raw.sort_values("date").groupby(["location", "year_month"], as_index=False).tail(1)
    monthly = monthly[monthly["date"].dt.year.between(2021, 2023)]
    fact_month = monthly.rename(columns={"location": "entity"})[
        ["entity", "iso_code", "year_month", "people_vaccinated_per_hundred", "people_fully_vaccinated_per_hundred", "total_vaccinations_per_hundred"]
    ]
    dim_entity = (
        raw[["location", "iso_code"]]
        .drop_duplicates("location")
        .rename(columns={"location": "entity"})
    )
    dim_entity["entity_type"] = dim_entity["iso_code"].fillna("").map(lambda c: "aggregate" if str(c).startswith("OWID_") else "country")
    dim_iso = dim_entity.loc[dim_entity["iso_code"].notna(), ["iso_code", "entity_type"]].drop_duplicates("iso_code")
    dim_year = pd.DataFrame(
        [{"extract": "owid_covid_vaccinations", "license": "CC BY 4.0", "title": "Our World in Data COVID-19 vaccinations"}]
    )
    qa_no_orphans(fact_latest, dim_entity, "entity", "entity", "owid.latest")
    qa_no_orphans(fact_month, dim_entity, "entity", "entity", "owid.month")
    tables = {
        "fact_latest.csv": fact_latest,
        "fact_monthly.csv": fact_month,
        "dim_entity.csv": dim_entity,
        "dim_iso.csv": dim_iso,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_latest.csv": "one row per country or OWID aggregate (latest published date)",
        "fact_monthly.csv": "one row per entity × year-month (last observation in month, 2021–2023)",
        "dim_entity.csv": "one row per OWID location (PK entity)",
        "dim_iso.csv": "one row per ISO / OWID code",
        "dim_year.csv": "one row for this OWID extract",
    }
    table_docs = {
        "fact_latest.csv": "Latest cumulative vaccination coverage by location.",
        "fact_monthly.csv": "Month-end coverage for 2021–2023, for time decomposition.",
        "dim_entity.csv": "Location names, ISO codes, and country vs aggregate flag.",
        "dim_iso.csv": "ISO / OWID codes.",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_latest.csv": {
            "entity": "Location name (FK -> dim_entity.entity)",
            "iso_code": "ISO 3166-1 alpha-3 or OWID_ aggregate code; null if missing",
            "date": "Date of the latest observation (YYYY-MM-DD)",
            "total_vaccinations": "Total doses; null if missing",
            "people_vaccinated": "People with ≥1 dose; null if missing",
            "people_fully_vaccinated": "People fully vaccinated; null if missing",
            "total_boosters": "Booster doses; null if missing",
            "people_vaccinated_per_hundred": "≥1 dose per 100 people; null if missing",
            "people_fully_vaccinated_per_hundred": "Fully vaccinated per 100; null if missing",
        },
        "fact_monthly.csv": {
            "entity": "Location (FK -> dim_entity.entity)",
            "iso_code": "ISO / OWID code; null if missing",
            "year_month": "YYYY-MM",
            "people_vaccinated_per_hundred": "≥1 dose per 100; null if missing",
            "people_fully_vaccinated_per_hundred": "Fully vaccinated per 100; null if missing",
            "total_vaccinations_per_hundred": "Doses per 100; null if missing",
        },
        "dim_entity.csv": {"entity": "Location name (PK)", "iso_code": "Code; null if missing", "entity_type": "country or aggregate"},
        "dim_iso.csv": {"iso_code": "Code (PK)", "entity_type": "country or aggregate"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "license": "License short name", "title": "Kit title"},
    }
    meta = {
        "source": "Our World in Data COVID-19 vaccinations (github.com/owid/covid-19-data)",
        "source_url": "https://ourworldindata.org/covid-vaccinations",
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "license_url": "https://ourworldindata.org/owid-nrc-data-licence",
        "download_urls": [
            "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/vaccinations/vaccinations.csv",
            "https://ourworldindata.org/grapher/covid-vaccination-doses-per-capita.csv",
        ],
        "transforms": [
            f"Read vaccinations.csv (n={n_raw}).",
            "Built a latest-observation fact (one row per location).",
            "Built a monthly fact using the last observation in each year-month for 2021–2023 only (other years excluded to keep the starter kit small; documented here).",
            "Flagged OWID_ codes as aggregates rather than countries.",
        ],
        "extra_files": [],
    }
    slug = "bio-17_owid_covid_vaccination"
    title = "Our World in Data: COVID-19 vaccination coverage by country"
    framing = "Judge whether a vaccination program's headline coverage or mortality-adjacent benefit survives decomposition by country vs aggregate, month, and dose series."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_latest.entity -> dim_entity.entity ; fact_monthly.entity -> dim_entity.entity ; dim_entity.iso_code -> dim_iso.iso_code",
        string_cols={
            "fact_latest.csv": {"entity", "iso_code", "date"},
            "fact_monthly.csv": {"entity", "iso_code", "year_month"},
            "dim_entity.csv": {"entity", "iso_code", "entity_type"},
            "dim_iso.csv": {"iso_code", "entity_type"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="clinical-population", tags=["vaccination", "public-health"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_18():
    print("kit 18 pdb")
    rows = []
    with open(SCRATCH / "pdb/resolu.idx", "r", errors="replace") as fh:
        for line in fh:
            if "\t;\t" not in line:
                continue
            parts = line.strip().split("\t;\t", 1)
            if len(parts) != 2:
                continue
            code, rest = parts
            try:
                resol = float(rest.split()[0])
            except ValueError:
                continue
            if not code.strip():
                continue
            rows.append({"pdb_id": code.strip().lower(), "resolution_a": resol})
    fact = pd.DataFrame(rows)
    fact["method_class"] = fact["resolution_a"].map(lambda r: "nmr_or_other" if r < 0 else "diffraction_or_em")
    fact["resolution_bin"] = pd.cut(
        fact["resolution_a"].where(fact["resolution_a"] >= 0),
        bins=[-0.01, 1.5, 2.0, 2.5, 3.0, 4.0, 100],
        labels=["<=1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-4.0", ">4.0"],
    ).astype(str)
    fact.loc[fact["method_class"] == "nmr_or_other", "resolution_bin"] = "nmr_or_other"
    dim_method = pd.DataFrame(
        [
            {"method_class": "diffraction_or_em", "note": "Positive resolution value (X-ray / EM / related)"},
            {"method_class": "nmr_or_other", "note": "Resolution sentinel -1.00 used by PDB for NMR and other methods"},
        ]
    )
    dim_bin = (
        fact[["resolution_bin"]]
        .drop_duplicates()
        .assign(sort_order=lambda d: d["resolution_bin"].map({"<=1.5": 1, "1.5-2.0": 2, "2.0-2.5": 3, "2.5-3.0": 4, "3.0-4.0": 5, ">4.0": 6, "nmr_or_other": 7}))
    )
    dim_year = pd.DataFrame([{"extract": "wwpdb_resolu_idx", "file_date": "2026-08-07", "title": "wwPDB structure resolution index"}])
    # Optional sample dim of pdb ids is the fact itself; add dim_entry as PK table
    dim_entry = fact[["pdb_id"]].drop_duplicates()
    qa_no_orphans(fact, dim_entry, "pdb_id", "pdb_id", "pdb.entry")
    tables = {
        "fact_resolution.csv": fact,
        "dim_entry.csv": dim_entry,
        "dim_method.csv": dim_method,
        "dim_resolution_bin.csv": dim_bin,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_resolution.csv": "one row per PDB entry in resolu.idx",
        "dim_entry.csv": "one row per PDB id (PK pdb_id)",
        "dim_method.csv": "one row per method class inferred from the resolution sentinel",
        "dim_resolution_bin.csv": "one row per resolution bin",
        "dim_year.csv": "one row for this wwPDB derived-data extract",
    }
    table_docs = {
        "fact_resolution.csv": "Reported resolution (Å) for every current PDB entry, plus method class.",
        "dim_entry.csv": "PDB four-character identifiers.",
        "dim_method.csv": "Method class derived from the official -1.00 NMR/other sentinel.",
        "dim_resolution_bin.csv": "Resolution bins used to decompose 'tractable structure' claims.",
        "dim_year.csv": "wwPDB derived-data file date.",
    }
    desc = {
        "fact_resolution.csv": {
            "pdb_id": "Lowercase PDB id (FK -> dim_entry.pdb_id)",
            "resolution_a": "Resolution in Å; -1.00 is the PDB sentinel for NMR/other (not a measured Å value)",
            "method_class": "Inferred method class (FK -> dim_method.method_class)",
            "resolution_bin": "Resolution bin (FK -> dim_resolution_bin.resolution_bin)",
        },
        "dim_entry.csv": {"pdb_id": "PDB id (PK)"},
        "dim_method.csv": {"method_class": "Method class (PK)", "note": "How the class is assigned"},
        "dim_resolution_bin.csv": {"resolution_bin": "Bin key (PK)", "sort_order": "Display order"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "file_date": "wwPDB file date", "title": "Kit title"},
    }
    meta = {
        "source": "Worldwide Protein Data Bank derived data — resolu.idx",
        "source_url": "https://www.wwpdb.org/",
        "license": "Creative Commons CC0 1.0 Universal — wwPDB data are released to the public domain",
        "license_url": "https://www.wwpdb.org/about/usage",
        "download_urls": ["https://files.wwpdb.org/pub/pdb/derived_data/index/resolu.idx"],
        "transforms": [
            f"Parsed resolu.idx IDCODE / RESOLUTION rows (n={len(fact)}). Header lines skipped.",
            "Mapped resolution -1.00 to method_class=nmr_or_other per the file documentation; did not treat -1 as an Å value in bins.",
            "Binned positive resolutions at 1.5 / 2.0 / 2.5 / 3.0 / 4.0 Å.",
        ],
        "extra_files": [],
    }
    slug = "bio-18_pdb_structure_resolution"
    title = "wwPDB: structure resolution and method class for every current entry"
    framing = "Judge whether a structure-based design program's 'tractable pocket / high-res structure' headline survives decomposition by resolution bin and method class."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_resolution.pdb_id -> dim_entry.pdb_id ; fact_resolution.method_class -> dim_method.method_class ; fact_resolution.resolution_bin -> dim_resolution_bin.resolution_bin",
        string_cols={"fact_resolution.csv": {"pdb_id", "method_class", "resolution_bin"}, "dim_entry.csv": {"pdb_id"}},
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["structure", "pdb"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_19():
    print("kit 19 uniprot")
    raw = pd.read_csv(SCRATCH / "uniprot/human_reviewed.tsv", sep="\t", dtype=str, low_memory=False)
    n_raw = len(raw)
    raw.columns = [c.strip() for c in raw.columns]
    dim_protein = pd.DataFrame(
        {
            "accession": raw.get("Entry"),
            "entry_name": raw.get("Entry Name"),
            "protein_name": raw.get("Protein names"),
            "gene_primary": raw.get("Gene Names (primary)"),
            "length": pd.to_numeric(raw.get("Length"), errors="coerce").astype("Int64"),
        }
    ).dropna(subset=["accession"])
    # Keywords melted (limited)
    kw_rows = []
    kw_col = raw.get("Keywords")
    if kw_col is not None:
        for acc, blob in zip(raw["Entry"], kw_col.fillna("")):
            for kw in str(blob).split(";"):
                kw = kw.strip()
                if kw:
                    kw_rows.append({"accession": acc, "keyword": kw})
                    if len(kw_rows) >= 50000:
                        break
            if len(kw_rows) >= 50000:
                break
    fact_kw = pd.DataFrame(kw_rows)
    fact_kw = fact_kw[fact_kw["accession"].isin(set(dim_protein["accession"]))]
    dim_keyword = fact_kw[["keyword"]].drop_duplicates()
    # PDB xref presence
    pdb_col = raw.get("PDB") if "PDB" in raw.columns else raw.get("Cross-reference (PDB)")
    has_pdb = []
    if pdb_col is not None:
        for acc, blob in zip(raw["Entry"], pdb_col.fillna("")):
            has_pdb.append({"accession": acc, "has_pdb": bool(str(blob).strip())})
    else:
        has_pdb = [{"accession": a, "has_pdb": False} for a in dim_protein["accession"]]
    fact_struct = pd.DataFrame(has_pdb)
    fact_struct = fact_struct[fact_struct["accession"].isin(set(dim_protein["accession"]))]
    dim_length = pd.DataFrame(
        {
            "length_bin": ["<200", "200-499", "500-999", "1000+"],
            "bin_label": ["Short (<200 aa)", "Medium (200–499 aa)", "Long (500–999 aa)", "Very long (≥1000 aa)"],
        }
    )
    dim_protein["length_bin"] = pd.cut(
        dim_protein["length"].astype("float"),
        bins=[-1, 199, 499, 999, 1e9],
        labels=["<200", "200-499", "500-999", "1000+"],
    ).astype(str)
    dim_year = pd.DataFrame([{"extract": "uniprot_swissprot_human", "query": "reviewed:true AND organism_id:9606", "title": "UniProt reviewed human proteome"}])
    qa_no_orphans(fact_kw, dim_protein, "accession", "accession", "up.kw")
    qa_no_orphans(fact_struct, dim_protein, "accession", "accession", "up.pdb")
    tables = {
        "fact_keyword.csv": fact_kw,
        "fact_structure_flag.csv": fact_struct,
        "dim_protein.csv": dim_protein,
        "dim_keyword.csv": dim_keyword,
        "dim_length.csv": dim_length,
        "dim_year.csv": dim_year,
    }
    grains = {
        "fact_keyword.csv": "one row per protein × UniProt keyword (capped)",
        "fact_structure_flag.csv": "one row per protein with a boolean has_pdb flag",
        "dim_protein.csv": "one row per reviewed human UniProt accession (PK accession)",
        "dim_keyword.csv": "one row per keyword",
        "dim_length.csv": "one row per length bin",
        "dim_year.csv": "one row for this UniProt stream extract",
    }
    table_docs = {
        "fact_keyword.csv": "Melted UniProt keywords for reviewed human proteins.",
        "fact_structure_flag.csv": "Whether the UniProt record lists a PDB cross-reference.",
        "dim_protein.csv": "Accession, entry name, protein name, primary gene, length.",
        "dim_keyword.csv": "Distinct keywords.",
        "dim_length.csv": "Protein-length bins.",
        "dim_year.csv": "Extract metadata (reviewed human proteome query).",
    }
    desc = {
        "fact_keyword.csv": {
            "accession": "UniProt accession (FK -> dim_protein.accession)",
            "keyword": "Keyword (FK -> dim_keyword.keyword)",
        },
        "fact_structure_flag.csv": {
            "accession": "UniProt accession (FK -> dim_protein.accession)",
            "has_pdb": "True if a PDB xref string was present",
        },
        "dim_protein.csv": {
            "accession": "UniProt accession (PK)",
            "entry_name": "Entry name",
            "protein_name": "Recommended protein name string",
            "gene_primary": "Primary gene name; null if missing",
            "length": "Amino-acid length; null if missing",
            "length_bin": "Length bin (FK -> dim_length.length_bin)",
        },
        "dim_keyword.csv": {"keyword": "Keyword (PK)"},
        "dim_length.csv": {"length_bin": "Bin key (PK)", "bin_label": "Label"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "query": "UniProt query", "title": "Kit title"},
    }
    meta = {
        "source": "UniProtKB/Swiss-Prot reviewed human proteome (organism_id:9606)",
        "source_url": "https://www.uniprot.org/",
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "license_url": "https://www.uniprot.org/help/license",
        "download_urls": [
            "https://rest.uniprot.org/uniprotkb/stream?format=tsv&query=(reviewed:true)+AND+(organism_id:9606)&fields=accession,id,protein_name,gene_primary,gene_names,length,cc_function,cc_subcellular_location,ft_domain,go_p,xref_pdb,keyword",
        ],
        "transforms": [
            f"Streamed reviewed human entries from the UniProt REST API (n={n_raw}).",
            f"Melted the Keywords column (capped at 50,000 protein–keyword rows; kept={len(fact_kw)}).",
            "Derived has_pdb from the PDB cross-reference field without downloading coordinates.",
            "Binned protein length at 200 / 500 / 1000 aa.",
        ],
        "extra_files": [],
    }
    slug = "bio-19_uniprot_human_reviewed"
    title = "UniProt Swiss-Prot: reviewed human proteins, keywords, and PDB flags"
    framing = "Judge whether a target portfolio's 'human reviewed / structured / keyword-class' headline survives decomposition by length, keyword, and PDB presence."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_keyword.accession -> dim_protein.accession ; fact_keyword.keyword -> dim_keyword.keyword ; fact_structure_flag.accession -> dim_protein.accession ; dim_protein.length_bin -> dim_length.length_bin",
        string_cols={
            "fact_keyword.csv": {"accession", "keyword"},
            "fact_structure_flag.csv": {"accession"},
            "dim_protein.csv": {"accession", "entry_name", "protein_name", "gene_primary", "length_bin"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["uniprot", "proteome"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)


def kit_20():
    print("kit 20 ncbi gene")
    raw = pd.read_csv(SCRATCH / "gene/Homo_sapiens.gene_info.gz", sep="\t", dtype=str)
    raw.columns = [str(c).lstrip("#") for c in raw.columns]
    rename = {
        "tax_id": "tax_id",
        "GeneID": "gene_id",
        "Symbol": "symbol",
        "LocusTag": "locus_tag",
        "Synonyms": "synonyms",
        "dbXrefs": "dbxrefs",
        "chromosome": "chromosome",
        "map_location": "map_location",
        "description": "description",
        "type_of_gene": "type_of_gene",
        "Symbol_from_nomenclature_authority": "symbol_from_nomenclature_authority",
        "Full_name_from_nomenclature_authority": "full_name_from_nomenclature_authority",
        "Nomenclature_status": "nomenclature_status",
        "Other_designations": "other_designations",
        "Modification_date": "modification_date",
        "Feature_type": "feature_type",
    }
    raw = raw.rename(columns={c: rename[c] for c in raw.columns if c in rename})
    n_raw = len(raw)
    dim_gene = pd.DataFrame(
        {
            "gene_id": raw.get("gene_id", raw.get("GeneID")),
            "symbol": raw.get("symbol", raw.get("Symbol")),
            "description": raw.get("description", raw.get("description")),
            "chromosome": raw.get("chromosome", raw.get("chromosome")),
            "map_location": raw.get("map_location", raw.get("map_location")),
            "type_of_gene": raw.get("type_of_gene", raw.get("type_of_gene")),
            "nomenclature_status": raw.get("nomenclature_status", raw.get("nomenclature_status")),
            "hgnc_id": None,
        }
    )
    # parse HGNC from dbxrefs
    xref = raw.get("dbxrefs", raw.get("dbXrefs"))
    if xref is not None:
        hgnc = xref.fillna("").str.extract(r"HGNC:HGNC:(\d+)", expand=False)
        dim_gene["hgnc_id"] = hgnc
    dim_gene = dim_gene.dropna(subset=["gene_id"])
    dim_type = dim_gene[["type_of_gene"]].dropna().drop_duplicates()
    dim_chrom = dim_gene[["chromosome"]].dropna().drop_duplicates()
    dim_nomen = dim_gene[["nomenclature_status"]].dropna().drop_duplicates()
    # fact: one row per gene with type/chrom as FKs — already dim. Create a slim fact of protein-coding vs not
    fact = dim_gene[["gene_id", "symbol", "type_of_gene", "chromosome", "nomenclature_status"]].copy()
    dim_year = pd.DataFrame([{"extract": "ncbi_gene_info_human", "tax_id": "9606", "title": "NCBI Gene: Homo sapiens gene_info"}])
    qa_no_orphans(fact, dim_gene, "gene_id", "gene_id", "gene.id")
    tables = {
        "fact_gene.csv": fact,
        "dim_gene.csv": dim_gene,
        "dim_biotype.csv": dim_type.rename(columns={"type_of_gene": "biotype"}),
        "dim_chromosome.csv": dim_chrom,
        "dim_nomenclature.csv": dim_nomen,
        "dim_year.csv": dim_year,
    }
    # align fact FK name
    tables["fact_gene.csv"] = fact.rename(columns={"type_of_gene": "biotype"})
    qa_no_orphans(tables["fact_gene.csv"], tables["dim_biotype.csv"], "biotype", "biotype", "gene.type")
    grains = {
        "fact_gene.csv": "one row per human NCBI gene (identity + classification FKs)",
        "dim_gene.csv": "one row per GeneID with description, map location, HGNC",
        "dim_biotype.csv": "one row per NCBI type_of_gene",
        "dim_chromosome.csv": "one row per chromosome / scaffold token",
        "dim_nomenclature.csv": "one row per nomenclature status (O = official, etc.)",
        "dim_year.csv": "one row for this NCBI gene_info extract",
    }
    table_docs = {
        "fact_gene.csv": "Slim gene table joining to biotype, chromosome, and nomenclature status.",
        "dim_gene.csv": "Full identity fields including description and HGNC id parsed from dbxrefs.",
        "dim_biotype.csv": "NCBI type_of_gene values (protein-coding, ncRNA, pseudo, ...).",
        "dim_chromosome.csv": "Chromosome tokens as published (1–22, X, Y, MT, unplaced).",
        "dim_nomenclature.csv": "HGNC nomenclature status codes.",
        "dim_year.csv": "Extract metadata.",
    }
    desc = {
        "fact_gene.csv": {
            "gene_id": "NCBI GeneID (FK -> dim_gene.gene_id)",
            "symbol": "Current symbol",
            "biotype": "type_of_gene (FK -> dim_biotype.biotype)",
            "chromosome": "Chromosome (FK -> dim_chromosome.chromosome)",
            "nomenclature_status": "Nomenclature status (FK -> dim_nomenclature.nomenclature_status); null if missing",
        },
        "dim_gene.csv": {
            "gene_id": "NCBI GeneID (PK)",
            "symbol": "Symbol",
            "description": "Gene description",
            "chromosome": "Chromosome token",
            "map_location": "Cytogenetic location; null if missing",
            "type_of_gene": "NCBI biotype",
            "nomenclature_status": "Nomenclature status; null if missing",
            "hgnc_id": "Parsed HGNC numeric id; null if no HGNC xref",
        },
        "dim_biotype.csv": {"biotype": "NCBI type_of_gene (PK)"},
        "dim_chromosome.csv": {"chromosome": "Chromosome token (PK)"},
        "dim_nomenclature.csv": {"nomenclature_status": "Status code (PK)"},
        "dim_year.csv": {"extract": "Extract tag (PK)", "tax_id": "NCBI taxonomy id", "title": "Kit title"},
    }
    meta = {
        "source": "NCBI Gene gene_info for Homo sapiens",
        "source_url": "https://www.ncbi.nlm.nih.gov/gene",
        "license": "U.S. Public Domain (17 U.S.C. 105) — work of the U.S. government",
        "license_url": "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        "download_urls": ["https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz"],
        "transforms": [
            f"Read Homo_sapiens.gene_info.gz (n={n_raw}).",
            "Parsed HGNC:HGNC:nnnn from the dbxrefs column; left hgnc_id null when absent.",
            "No rows dropped except those missing a GeneID. This table is the join spine for the omics kits.",
        ],
        "extra_files": [],
    }
    slug = "bio-20_ncbi_human_genes"
    title = "NCBI Gene: Homo sapiens gene_info (biotype, chromosome, HGNC)"
    framing = "Judge whether a panel vendor's 'covers all disease genes' headline survives decomposition by biotype, chromosome, and official-nomenclature status."
    finalize_kit(
        slug, tables=tables, grains=grains, descriptions=desc, table_docs=table_docs, meta=meta,
        package_title=title, framing=framing,
        join_keys="fact_gene.gene_id -> dim_gene.gene_id ; fact_gene.biotype -> dim_biotype.biotype ; fact_gene.chromosome -> dim_chromosome.chromosome ; fact_gene.nomenclature_status -> dim_nomenclature.nomenclature_status",
        string_cols={
            "fact_gene.csv": {"gene_id", "symbol", "biotype", "chromosome", "nomenclature_status"},
            "dim_gene.csv": {"gene_id", "symbol", "description", "chromosome", "map_location", "type_of_gene", "nomenclature_status", "hgnc_id"},
        },
    )
    add_catalog(slug=slug, title=title, framing=framing, domain="omics", tags=["ncbi", "gene", "reference"], source=meta["source"], license_text=meta["license"], tables=tables, grains=grains)
