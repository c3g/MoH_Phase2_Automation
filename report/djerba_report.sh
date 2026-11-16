#!/usr/bin/env bash
# Djerba report of one oncoanalyser run: HTML and PDF in <run_dir>/djerba/.
# Usage: djerba_report.sh -d <run_dir> [-g <group>] [-c <oncotree>]

set -uo pipefail
umask 007

SCRIPTS=~/MoH_Phase2_Automation/report
DJERBA_MODULES="mugqic/hmf_djerba/0.0.5 mugqic/wkhtmltopdf/0.12.6"
SUPPORT=/project/60007/analyste_dev/software/djerba/supporting_files
APPENDIX=/project/60007/julian3/djerba-oncoanalyser/apendice   # TODO move to final location
PT_CLI="pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q"

usage() {
    echo "Usage: $(basename "$0") -d <run_dir> [-g <group>] [-c <oncotree>]   (default group: run folder name)"
    exit 1
}
oncotree_set=false
while getopts 'hd:g:c:' OPTION; do
    case "$OPTION" in
        d) run_dir="$OPTARG" ;;
        g) group="$OPTARG" ;;
        c) oncotree="$OPTARG"; oncotree_set=true ;;
        *) usage ;;
    esac
done
[[ "${run_dir:-}" ]] || usage
run_dir=$(realpath "$run_dir")
group=${group:-$(basename "$run_dir")}   # default: run folder name
results=$run_dir/results/$group
out=$run_dir/djerba

reason=""
fail() {
    reason="$*"
    echo "ERROR: $*"
    exit 1
}

# rc 1: pt-cli failed, 2: unreadable reply, 3: not one live record
oncotree_from_db() {
    local reply found
    # TODO check route, field and sample name (CaseType?)
    reply=$($PT_CLI route "/project/MOH-Q/samples?json={\"sample_name\":\"$1\"}" 2>/dev/null) || return 1
    found=$(jq -r --arg s "$1" '[.DB_ACTION_OUTPUT[] | select(.name == $s and (.deleted | not) and (.deprecated | not))]
        | "\(length) \(.[0].oncotree_code // .[0].sample_oncotree_code // "")"' <<< "$reply" 2>/dev/null) || return 2
    [ "${found%% *}" = 1 ] || return 3
    oncotree=$(tr -d '[:space:]' <<< "${found#* }")
}

# 1. tumor/normal DNA from newest samplesheet (as check_oncoanalyser.sh)
samplesheet=$(ls -1 "$run_dir"/samplesheets/*/"$group".samplesheet.csv 2>/dev/null | sort | tail -1)
[ -z "$samplesheet" ] && samplesheet=$run_dir/$group.samplesheet.csv
[ -f "$samplesheet" ] || samplesheet=$run_dir/samplesheet.csv
[ -f "$samplesheet" ] || fail "no samplesheet for $group in $run_dir"
tumor_dna=$(awk -F, '$4=="tumor" && $5=="dna" {print $3; exit}' "$samplesheet")
normal_dna=$(awk -F, '$4=="normal" && $5=="dna" {print $3; exit}' "$samplesheet")
[ -n "$tumor_dna" ] && [ -n "$normal_dna" ] || fail "tumor or normal DNA missing in $samplesheet"

# 2. OncoTree
oncotree_source=none
if [ "$oncotree_set" = true ]; then
    [ -n "$oncotree" ] && oncotree_source=option
else
    [ -f ~/project_tracking_cli/.venv/bin/activate ] && source ~/project_tracking_cli/.venv/bin/activate
    oncotree=""
    oncotree_from_db "$tumor_dna"
    case $? in
        1) fail "DB query for the OncoTree code of $tumor_dna failed (pt-cli error), no report written" ;;
        2) fail "DB query for the OncoTree code of $tumor_dna failed (unreadable reply or no DB_ACTION_OUTPUT), no report written" ;;
        3) fail "DB query for the OncoTree code of $tumor_dna failed (not exactly one live sample with that name), no report written" ;;
    esac
    [ -n "$oncotree" ] && oncotree_source=database
fi

[ -d "$APPENDIX" ] || fail "no appendix in $APPENDIX"

# 3. replace previous report
rm -rf "$out"
mkdir -p "$out/work"

# status.txt on exit
status=FAILED
write_status() {
    {
        echo "status: $status"
        [ -n "$reason" ] && echo "reason: $reason"
        echo "group: $group"
        echo "tumor_dna: $tumor_dna"
        echo "normal_dna: $normal_dna"
        echo "oncotree: ${oncotree:-}"
        echo "oncotree_source: $oncotree_source"
        n_warnings=$(grep -c . "$out/warnings.txt" 2>/dev/null)
        echo "warnings: ${n_warnings:-0}"
        echo "date: $(date +%FT%H.%M.%S)"
    } > "$out/status.txt"
    rm -rf "$out/.tmp"
}
trap write_status EXIT

vcf=$results/purple/$tumor_dna.purple.somatic.vcf.gz
[ -f "$vcf" ] || fail "$vcf not found"

# 4. Djerba env
export TMPDIR=$out/.tmp MPLCONFIGDIR=$out/.tmp/mpl XDG_CACHE_HOME=$out/.tmp/cache
mkdir -p "$MPLCONFIGDIR" "$XDG_CACHE_HOME"
export MUGQIC_INSTALL_HOME=/cvmfs/soft.mugqic/CentOS6
module use $MUGQIC_INSTALL_HOME/modulefiles || fail "module use $MUGQIC_INSTALL_HOME/modulefiles failed"
module load $DJERBA_MODULES || fail "module load $DJERBA_MODULES failed"
export DJERBA_TRACKING_DIR=$out
export DJERBA_CORE_HTML_DIR=$SUPPORT/custom_formatting/McGill_html
export ONCOKB_TOKEN=$SUPPORT/oncokb_tokens/oncokb_token.txt
export FONTCONFIG_PATH=/etc/fonts

# 5. MAF
maf=$out/$tumor_dna.maf
python3 "$SCRIPTS"/pave_to_maf.py --vcf "$vcf" --tumor "$tumor_dna" --normal "$normal_dna" --out "$maf" \
    > "$out/work/maf.log" 2>&1 || fail "MAF conversion failed, see $out/work/maf.log"
gzip "$maf" || fail "gzip of $maf failed"

# 6. INI
ini=$out/$group.djerba.ini
if ! APPENDIX=$APPENDIX "$SCRIPTS"/djerba_ini.sh -t "$tumor_dna" -n "$normal_dna" -c "${oncotree:-}" \
        "$results" "$maf.gz" > "$ini" 2> "$out/warnings.txt"; then
    cat "$out/warnings.txt"
    fail "INI not written"
fi

# 7. report
echo "Djerba report for $group (tumor $tumor_dna, normal $normal_dna, oncotree ${oncotree:-none})"
(cd "$out" && djerba.py report -i "$ini" -o "$out" -w "$out/work" -p --no-archive) > "$out/djerba.log" 2>&1
if [ $? -ne 0 ] || ! ls "$out"/*.pdf >/dev/null 2>&1; then
    tail -5 "$out/djerba.log"
    fail "Djerba failed, see $out/djerba.log"
fi

status=OK
echo "Report: $(ls "$out"/*.pdf)"
exit 0
