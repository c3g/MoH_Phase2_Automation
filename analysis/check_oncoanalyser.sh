#!/usr/bin/env bash
# Check that an oncoanalyser run finished and that its main outputs are there.

# ==========
# status: based on WorkflowStats line in .nextflow.log 
# - COMPLETED: Nextflow ended the run itself and all main outputs exist.
# In the log: "Pipeline completed successfully"; (Tasks that failed but worked on a retry are still counted)
# - FAILED: Nextflow ended the run itself. In the log: "Pipeline completed with errors"
# - RUNNING: no WorkflowStats line yet, and the log was written recently.
# - STALLED: no WorkflowStats line, and the log has been quiet for more than 2 hours.
# - INCOMPLETE: completed successfully, but some main outputs are missing.




usage() {
  echo "Usage: $(basename "$0") -d <analysis_dir> [-g <group>]   (default group: run folder name)"
  exit 1
}
# Read the options: -d run folder (required), -g group (optional)
while getopts 'hd:g:' OPTION; do
  case "$OPTION" in
    d) run_dir="$OPTARG" ;;
    g) group="$OPTARG" ;;
    *) usage ;;
  esac
done
[[ "$run_dir" ]] || usage
group=${group:-$(basename "$run_dir")}   # default: run folder name

# newest samplesheet, else old locations
samplesheet=$(ls -1 "$run_dir"/samplesheets/*/"$group".samplesheet.csv 2>/dev/null | sort | tail -1)
[ -z "$samplesheet" ] && samplesheet=$run_dir/$group.samplesheet.csv
[ -f "$samplesheet" ] || samplesheet=$run_dir/samplesheet.csv

results=$run_dir/results/$group
log=$run_dir/.nextflow.log

# CHECK LOGS

if [ ! -d "$run_dir" ] || [ ! -f "$samplesheet" ]; then
  echo "ERROR: $run_dir or $samplesheet not found"
  exit 1
fi

# No log yet: the run has not started
if [ ! -f "$log" ]; then
  echo "NOT STARTED: no .nextflow.log"
  exit 1
fi

# Check the log for the WorkflowStats line
if grep -q "Pipeline completed successfully" "$log"; then
  :

elif grep -q "Pipeline completed with errors" "$log"; then
  echo "FAILED"
  echo "  failed step: $(grep "Error executing process" "$log" | tail -1 | sed 's/.*Error executing process > //')"
  echo "  reason:      $(grep -A1 "^Caused by:" "$log" | grep -v -e "^Caused by:" -e "^--" | tail -1 | sed 's/^ *//')"
  exit 1

else
  #still running, or stalled (killed or stuck) if the log is quiet
  minutes_since=$(( ( $(date +%s) - $(stat -c %Y "$log") ) / 60 ))
  if [ "$minutes_since" -gt 120 ]; then
    echo "STALLED: .nextflow.log not updated for $minutes_since min (killed or stuck, resubmit)"
  else
    echo "RUNNING"
  fi
  exit 1
fi

#  (maybe) list tasks that were retried for future reference
grep "Execution is retried" "$log" \
  | sed -E 's/.*Process `([^`]*)` terminated with an error exit status \(([0-9]+)\).*/  retried: \1  exit \2/'


# CHECK OUTPUTS

# Sample ids from the samplesheet to find output directories.
normal_dna=$(awk -F, '$4=="normal" && $5=="dna" {print $3; exit}' "$samplesheet")
tumor_dna=$(awk -F, '$4=="tumor" && $5=="dna" {print $3; exit}' "$samplesheet")
tumor_rna=$(awk -F, '$4=="tumor" && $5=="rna" {print $3; exit}' "$samplesheet")

# main outputs that must exist (TO BE UPDATED BAES ON DELIVERABLES IF NEEDED)--------------------------------------------
expected=(
    # redux bams
    "$results/alignments/$tumor_dna/$tumor_dna.redux.bam"
    "$results/alignments/$tumor_dna/$tumor_dna.redux.bam.bai"
    "$results/alignments/$normal_dna/$normal_dna.redux.bam"
    "$results/alignments/$normal_dna/$normal_dna.redux.bam.bai"
    
    #bamtools
    "$results/bamtools/$normal_dna/$normal_dna.bam_metric.summary.tsv"
    "$results/bamtools/$tumor_dna/$tumor_dna.bam_metric.summary.tsv"


    "$results/purple/$tumor_dna.purple.purity.tsv"
    "$results/purple/$tumor_dna.purple.qc"
    "$results/qsee/$tumor_dna.qsee.status.tsv.gz"
    "$results/orange/$tumor_dna.orange.pdf"

)

# RNA (if exists)
if [ -n "$tumor_rna" ]; then
  expected+=("$results/alignments/$tumor_rna/$tumor_rna.md.bam")
  expected+=("$results/isofox/$tumor_dna.isf.summary.tsv")
fi

for f in "${expected[@]}"; do
  if [ ! -s "$f" ]; then
    echo "INCOMPLETE: missing $f"
    exit 1
  fi
done

# CALL TO ONCOANALYSER2JSON
# FILL THE JSON: jobs + metrics + files
timestamp=$(basename "$(dirname "$samplesheet")")     # samplesheets/<timestamp>/<group>.samplesheet.csv
json=$run_dir/$group.oncoanalyser.json

if ! python3 ~/MoH_Phase2_Automation/analysis/oncoanalyser2json.py \
        -i "$run_dir" -t "$timestamp" -g "$group" -o "$json" >&2; then
  echo "ERROR: oncoanalyser2json.py failed for $group"
  exit 1
fi

echo "COMPLETED"
