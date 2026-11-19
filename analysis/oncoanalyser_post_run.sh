#!/usr/bin/env bash
# Run after an oncoanalyser run has ended (by the trigger). could be completed,failed, cancelled.
# 1. Check run status
# 2. COMPLETED or FAILED: build the json ( call oncoanalyser2json.py)
# 3. ingest the json into the DB
# THE REST: DJERBA + DELIVERY

# Usage: oncoanalyser_post_run.sh -d <run_dir>

# ==========
# status: based on WorkflowStats line in .nextflow.log

set -eo pipefail
umask 007

SCRIPTS=~/MoH_Phase2_Automation/analysis
PT_CLI="pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q"

usage() {
  echo "Usage: $(basename "$0") -d <run_dir>"
  exit 1
}

while getopts 'hd:' OPTION; do
  case "$OPTION" in
    d) run_dir="$OPTARG" ;;
    *) usage ;;
  esac
done
[[ "$run_dir" ]] || usage
group=$(basename "$run_dir")

# newest samplesheet: samplesheets/<timestamp>/<group>.samplesheet.csv
samplesheet=""
for f in "$run_dir"/samplesheets/*/"$group".samplesheet.csv; do
  [ -f "$f" ] && samplesheet=$f
done
if [ ! -d "$run_dir" ] || [ -z "$samplesheet" ]; then
  echo "ERROR: $run_dir or samplesheets/<timestamp>/$group.samplesheet.csv not found"
  exit 1
fi
timestamp=$(basename "$(dirname "$samplesheet")")   # launch timestamp, needed for the json

results=$run_dir/results/$group
log=$run_dir/.nextflow.log
json=$run_dir/$group.oncoanalyser.json 
out=$run_dir/$group.oncoanalyser_$timestamp.out


# 1. CHECK THE RUN

# NOT STARTED: no Slurm .out for the latest launch
if [ ! -f "$out" ]; then
  echo "NOT STARTED: no $(basename "$out")."
  exit 
fi

# COMPLETED
if grep -q "Pipeline completed successfully" "$log"; then
  # check the orange report exists
  tumor_dna=$(awk -F, '$4=="tumor" && $5=="dna" {print $3; exit}' "$samplesheet")
  orange=$results/orange/$tumor_dna.orange.pdf
  if [ ! -s "$orange" ]; then
    status=FAILED
    echo "FAILED: missing $orange."
  else
    status=COMPLETED
  fi

# FAILED
elif grep -q "Pipeline completed with errors" "$log"; then
  status=FAILED
  failed_step=$(grep "Error executing process" "$log" | tail -1 | sed 's/.*Error executing process > //')
  reason=$(grep -A1 "^Caused by:" "$log" | grep -v -e "^Caused by:" -e "^--" | tail -1 | sed 's/^ *//')
  echo "  failed step: $failed_step"
  echo "  reason:      $reason"

else
  echo "NOT ENDED: no WorkflowStats line in .nextflow.log (could be running, killed or stuck)."
  exit 1
fi
echo "$status"

# 2. UPDATE JSON
if ! python3 "$SCRIPTS"/oncoanalyser2json.py -i "$run_dir" -t "$timestamp" -g "$group" -o "$json"; then
  echo "ERROR: oncoanalyser2json.py failed for $group"
  exit 1
fi

# 3. INGEST
source ~/project_tracking_cli/.venv/bin/activate
$PT_CLI ingest analysis --input-json "$json"
echo "$group ($status) ingested. (post-oncoanalyser run)"

# 4. DJERBA CALL  (TBD)
# "$SCRIPTS"/analysis/djerba_report.sh -d "$run_dir" -g "$group"

# 5. DELIVERY
# "$SCRIPTS"/delivery/oncoanalyser_delivery.sh -i "$run_dir" -g "$group"
# echo "$group delivered."

# 6. RELAUNCH if the group has readsets this run did not use
"$SCRIPTS"/analysis/oncoanalyser_launch.sh -g "$group"