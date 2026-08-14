# Project Mark — Biology starter kits

Twenty star-schema starter kits for decomposing headline effects in
experimental, clinical-population, and omics analysis.

**Every value in these packages is copied from a real public download.**
Nothing is synthetic, simulated, interpolated, or invented. Some kits are
*capped extracts* of a larger official file (the first N real rows after
documented filters) — those caps are noted below and in each
`data_dictionary.json`.

The previous placeholder (`PACKAGES/bio-01_clinical_exercise_glycemic`,
four NHANES rows) has been replaced by the full adult cardiometabolic kit.

## What's in a kit

```
PACKAGES/<prefix>-<nn>_<slug>/
  fact_*.csv              # measurements at a stated grain
  dim_*.csv               # lookup tables the facts join to
  data_dictionary.json    # source, license, download URLs, transforms, field types
  overview.xlsx           # one-page cover (package, framing, row counts, joins)
```

`catalog.json` is the machine-readable index used by the Strata browser.

## Kits

| ID | Title | Source | Fact rows | Notes |
|---|---|---|---:|---|
| [bio-01](PACKAGES/bio-01_nhanes_cardiometabolic) | NHANES 2017–2018 cardiometabolic exam + labs | CDC / NCHS | 23,683 | MEC-examined adults 18+ |
| [bio-02](PACKAGES/bio-02_cdc_places_county) | CDC PLACES 2024 county crude prevalence | CDC PLACES | 25,112 | |
| [bio-03](PACKAGES/bio-03_nchs_leading_causes) | NCHS leading causes of death by state/year | NCHS / data.cdc.gov | 10,868 | |
| [bio-04](PACKAGES/bio-04_cdc_diabetes_burden) | USDSS diabetes burden + state economic cost | CDC USDSS | 74,752 | prevalence extract capped at 50,000 real rows |
| [bio-05](PACKAGES/bio-05_cdc_stroke_mortality) | County stroke mortality, adults 35+ | CDC NVSS | 19,592 | |
| [bio-06](PACKAGES/bio-06_gwas_catalog_associations) | GWAS Catalog genome-wide significant associations | NHGRI-EBI | 40,000 | capped extract of real catalog rows |
| [bio-07](PACKAGES/bio-07_hpa_tissue_specificity) | Human Protein Atlas RNA tissue specificity | HPA | 17,870 | CC BY-SA 3.0 |
| [bio-08](PACKAGES/bio-08_reactome_pathways) | Reactome human pathway hierarchy + participation | Reactome | 57,598 | participation extract capped |
| [bio-09](PACKAGES/bio-09_chembl_drug_mechanisms) | ChEMBL mechanism of action + max phase | ChEMBL / EMBL-EBI | 4,000 | API extract of real mechanism records; CC BY-SA 3.0 |
| [bio-10](PACKAGES/bio-10_openfda_faers) | openFDA FAERS reaction counts + report sample | FDA openFDA | 694 | real FAERS API sample (not causation) |
| [bio-11](PACKAGES/bio-11_clinicaltrials_interventional) | ClinicalTrials.gov interventional studies | NLM | 7,473 | real API sample of 1,600 studies |
| [bio-12](PACKAGES/bio-12_usda_fooddata_foundation) | USDA FoodData Central Foundation Foods | USDA | 16,975 | |
| [bio-13](PACKAGES/bio-13_clinvar_gene_yield) | ClinVar P/LP allele yield by gene | NCBI ClinVar | 92,949 | |
| [bio-14](PACKAGES/bio-14_iedb_tcell_epitopes) | IEDB T-cell epitope assays | IEDB | 25,000 | human-preferring extract, capped |
| [bio-15](PACKAGES/bio-15_goa_human_annotations) | GOA human experimental GO annotations | UniProt-GOA | 40,000 | experimental / TAS / HTP extract, capped |
| [bio-16](PACKAGES/bio-16_orange_book_products) | FDA Orange Book products, exclusivity, patents | FDA | 24,472 | |
| [bio-17](PACKAGES/bio-17_owid_covid_vaccination) | OWID COVID-19 vaccination coverage | Our World in Data | 6,691 | CC BY 4.0 |
| [bio-18](PACKAGES/bio-18_pdb_structure_resolution) | wwPDB structure resolution index | wwPDB | 258,167 | full current `resolu.idx` |
| [bio-19](PACKAGES/bio-19_uniprot_human_reviewed) | UniProt Swiss-Prot reviewed human proteome | UniProt | 70,431 | keyword extract capped at 50,000 |
| [bio-20](PACKAGES/bio-20_ncbi_human_genes) | NCBI Gene *Homo sapiens* gene_info | NCBI Gene | 193,884 | full human gene_info |

## Provenance

Each `data_dictionary.json` records:

- publishing agency / program
- landing-page URL
- license + license URL
- the exact download URLs that were fetched
- every transform, in order (filters, sentinel-nulling, melts, caps)

Spot-checks against the raw files (NHANES XPT SEQN 93705 BMI/HbA1c,
NCBI GeneID 1 = A1BG, wwPDB `100D;1.9`, OWID Falkland Islands 2021-04-14
totals, NCHS Vermont 2012 kidney deaths = 21) match the packaged CSVs
exactly.

## Licenses

Packaging code under `scripts/` is available for reuse with the kits.

**The data itself keeps its source license.** Do not treat the whole
repository as a single permissive dump:

| License | Kits |
|---|---|
| U.S. Public Domain (17 U.S.C. 105) | bio-01, 02, 03, 04, 05, 10, 11, 12, 13, 16, 20 |
| CC0 1.0 | bio-08 (Reactome), bio-18 (wwPDB); bio-06 catalog content is CC0-style |
| CC BY 4.0 | bio-14 (IEDB), bio-15 (GOA), bio-17 (OWID), bio-19 (UniProt) |
| CC BY-SA 3.0 | bio-07 (Human Protein Atlas), bio-09 (ChEMBL) |

Attribute those sources if you redistribute. FAERS rows (bio-10) are
spontaneous reports, not proof of causation.

## Rebuild

Raw bulk files are not checked in. To regenerate from source:

```bash
# 1. Download the URLs listed in each kit's data_dictionary.json["meta"]["download_urls"]
#    into scratch/<source>/ as expected by scripts/curate/*.py
# 2. From a machine with pandas + openpyxl:
python scripts/curate/run_all.py
```

`scripts/curate/` is the recorder of how each star schema was built.
It never fabricates values; it only reads, filters, melts, and writes.
