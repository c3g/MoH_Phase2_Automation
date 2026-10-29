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
  echo "Usage: $(basename "$0") -d <analysis_dir> -g <group>"
  exit 1
}
# Read the options: -d run folder, -g group (both required)
while getopts 'hd:g:' OPTION; do
  case "$OPTION" in
    d) run_dir="$OPTARG" ;;
    g) group="$OPTARG" ;;
    *) usage ;;
  esac
done
[[ "$run_dir" && "$group" ]] || usage

samplesheet=$run_dir/$group.samplesheet.csv
results=$run_dir/results/$group
log=$run_dir/.nextflow.log

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
  | sed -E 's/.*Process `([^`]*)` terminated with an error exit status \(([0-9]+)\).*/  retried: \1  exit \2/'

# Check The orange report exists
if ! ls "$results"/orange/*.orange.pdf > /dev/null 2>&1; then
  echo "INCOMPLETE: no ORANGE report"
  exit 1
fi

echo "COMPLETED"

# TODO:
#  check other outputs (Purple, QSEE, BamTools)
#  check RNA outputs if RNA was run
#  check BAMs are not truncated (the bug that happend with a few 2.3.0 runs)