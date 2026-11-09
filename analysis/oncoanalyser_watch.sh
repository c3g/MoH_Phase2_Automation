#!/usr/bin/env bash

# SCRATCH FOR TRIGGER

# Called periodically
# whose last launch ended OK and that hasn't been handled yet.
# # To redo a run's post-run: delete <run>/<group>.post_run.submitted (next call submits it again).

MOH_DIR=/project/60007/MOH_PHASE2
SCRIPTS=~/MoH_Phase2_Automation/analysis

for run_dir in "$MOH_DIR"/*/*/; do
    run_dir=${run_dir%/}
    group=$(basename "$run_dir")
    history=$run_dir/.nextflow/history
    marker=$run_dir/$group.post_run.submitted

    [ -f "$history" ] || continue                               # never launched
    [ "$(tail -1 "$history" | cut -f4)" = "OK" ] || continue    # running or failed
    [ "$marker" -nt "$history" ] && continue                    # this run already submitted

    sbatch --output="$run_dir/$group.post_run_%j.out" "$SCRIPTS"/oncoanalyser_post_run.sh -d "$run_dir" \
        && touch "$marker" && echo "post-run submitted for $group"
done