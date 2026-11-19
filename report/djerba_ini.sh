#!/usr/bin/env bash
# Djerba INI of one oncoanalyser sample, to stdout.
# Usage: djerba_ini.sh -t tumor -n normal [-c oncotree] <results_dir> <maf.gz> > sample.djerba.ini
# Env: APPENDIX (required), STUDY, AUTHOR, ISOFOX

set -euo pipefail

usage="Usage: $(basename "$0") -t tumor -n normal [-c oncotree] <results_dir> <maf.gz>"
tumor="" normal="" oncotree=""
while getopts 't:n:c:' OPTION; do
    case "$OPTION" in
        t) tumor="$OPTARG" ;;
        n) normal="$OPTARG" ;;
        c) oncotree="$OPTARG" ;;
        *) echo "$usage" >&2; exit 1 ;;
    esac
done
shift $((OPTIND - 1))
results=${1:?$usage}
maf=${2:?$usage}
study=${STUDY:-MOH}
author=${AUTHOR:-C3G}
appendix=${APPENDIX:?APPENDIX not set}

results=$(cd "$results" && pwd)
sample=$(basename "$results")
warn() { echo "WARNING: $*" >&2; }

if [ -z "$tumor" ] || [ -z "$normal" ]; then
    echo "$usage" >&2
    exit 1
fi

# ids must match the files Djerba reads
if [ ! -f "$results/purple/$tumor.purple.qc" ]; then
    echo "ERROR: $results/purple/$tumor.purple.qc not found, check the tumor id" >&2
    exit 1
fi
{ ls "$results"/amber/ "$results"/cobalt/ 2>/dev/null || true; } | grep -q "^$normal\." || warn "$normal not in amber/ or cobalt/, check the normal id"

[ -n "$oncotree" ] || warn "no OncoTree code"
[ -f "$maf" ] || warn "$maf not found"
[ -f "$results/chord/$tumor.chord.prediction.tsv" ] || warn "no CHORD output, no HRD in the report"

# PURPLE 4.3: header shorter then rows, empty CNV table
gene_tsv=$results/purple/$tumor.purple.cnv.gene.tsv
if [ -f "$gene_tsv" ]; then
    n_header=$(head -1 "$gene_tsv" | awk -F'\t' '{print NF}')
    n_row=$(sed -n 2p "$gene_tsv" | awk -F'\t' '{print NF}')
    [ "${n_row:-0}" -le "$n_header" ] || warn "$gene_tsv has a short header (PURPLE 4.3), empty CNV table"
fi

# TODO check Isofox 2 .tsv once hmf_djerba reads it
isofox=${ISOFOX:-$(ls "$results"/isofox/*.isf.pass_fusions.csv 2>/dev/null | head -1 || true)}
if [ -z "$isofox" ] && ls "$results"/isofox/*.isf.pass_fusions.tsv >/dev/null 2>&1; then
    warn "Isofox 2.0 fusions (.tsv) are not read, no fusions in the report"
fi

cat <<EOF
[core]
attributes = research
author = $author
report_id = $sample
report_version = 1

[case_overview]
assay = WGS
attributes = research
assay_description = Whole genome sequencing (WGS)
primary_cancer = Unknown
site_of_biopsy = Unknown
study = $study
patient_study_id = $sample
donor = $sample
tumour_id = $tumor
normal_id = $normal
requisition_approved = 0000-00-00

[hmf.wgts.snv_indel]
attributes = research
maf_path = $maf
oncotree_code = $oncotree
tumour_id = $tumor
normal_id = $normal
project = $study
whizbam_project = $study
apply cache = False
update cache = False
oncokb cache =

[hmf.genomic_landscape]
attributes = research
tumour_id = $tumor
oncotree_code = $oncotree
tcga_code = TCGA_ALL_TUMOR
msi_file = $results/purple/$tumor.purple.purity.tsv
hrd_path = $results/chord/$tumor.chord.prediction.tsv
apply cache = False
update cache = False
oncokb cache =

[hmf.wgts.cnv_purple]
attributes = research
tumour_id = $tumor
normal_id = $normal
oncotree_code = $oncotree
whizbam_project = $study
purple_dir = $results/purple

EOF

if [ -n "$isofox" ]; then cat <<EOF
[hmf.fusion]
attributes = research
isofox_path = $isofox
tumour_id = $tumor
oncotree_code = $oncotree
project = $study
whizbam_project = $study
apply cache = False
update cache = False
oncokb cache =

EOF
fi

cat <<EOF
[treatment_options_merger]
attributes = research,supplementary

[gene_information_merger]
attributes = research,supplementary

[supplement.body]
assay = WGS
attributes = research
template_dir = $appendix
EOF
