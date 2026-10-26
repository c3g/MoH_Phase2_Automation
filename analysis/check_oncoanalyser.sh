#!/usr/bin/env bash
# Check that an oncoanalyser run finished and that its main outputs are there.

# ==========
# status:
#  COMPLETED: Nextflow finished with no failed task and all main outputs exist
#  INCOMPLETE: Nextflow finished, but some  outputs are missing
#  FAILED: Nextflow reported failed tasks
#  UNFINISHED: Nextflow has not finished (still running, or killed)

usage() {
  echo "Usage: $(basename "$0") -d <analysis_dir> -g <group>"
  exit 1
}

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

# Check that the run dir and samplesheet exist
if [ ! -d "$run_dir" ] || [ ! -f "$samplesheet" ]; then
  echo "ERROR: $run_dir or $samplesheet not found"
  exit 1
fi

# 1. Nextflow finished with no failed tasks
#    (the WorkflowStats line is only written when the run ends)
stats=$(grep "WorkflowStats" "$run_dir/.nextflow.log" 2>/dev/null | tail -1)
if [ -z "$stats" ]; then
  echo "UNFINISHED"
  exit 1
fi
if ! echo "$stats" | grep -q "failedCount=0"; then
  echo "FAILED"
  exit 1
fi

# 2. The final report exists (ORANGE is the last step)
if ! ls "$results"/orange/*.orange.pdf > /dev/null 2>&1; then
  echo "INCOMPLETE: no ORANGE report"
  exit 1
fi

echo "COMPLETED"

# TODO:
#  check other outputs (Purple, QSEE, BamTools)
#  check RNA outputs if RNA was run
#  check BAMs are not truncated (the bug that happend with a few 2.3.0 runs)