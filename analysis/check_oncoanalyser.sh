#!/usr/bin/env bash
# Check that an oncoanalyser run finished and that its main outputs are there.

# ==========
# status:
#  COMPLETED: Nextflow finished with no failed task and all main outputs exist
#  INCOMPLETE: Nextflow finished, but some  outputs are missing
#  FAILED: Nextflow reported failed tasks
#  UNFINISHED: Nextflow has not finished (still running, or killed)

run_dir=$1

# 1. Nextflow finished with no failed tasks
#    (the WorkflowStats line is only written when the run ends)
stats=$(grep "WorkflowStats" "$run_dir/.nextflow.log" | tail -1)
if [ -z "$stats" ]; then
  echo "UNFINISHED"
  exit 1
fi
if ! echo "$stats" | grep -q "failedCount=0"; then
  echo "FAILED"
  exit 1
fi

# 2. The final report exists (ORANGE is the last step)
if ! ls "$run_dir"/results/*/orange/*.orange.pdf > /dev/null 2>&1; then
  echo "INCOMPLETE: no ORANGE report"
  exit 1
fi

echo "COMPLETED"

# TODO:
#  check other outputs (Purple, QSEE, BamTools)
#  check RNA outputs if RNA was run
#  check BAMs are not truncated (the bug that happend with a few 2.3.0 runs)