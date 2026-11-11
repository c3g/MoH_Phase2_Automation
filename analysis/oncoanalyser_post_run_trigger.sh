#!/usr/bin/env bash
#SBATCH --job-name=oncoanalyser_post_run
#SBATCH --time=24:00:00
#SBATCH --mem=4G
# After a run finished: if COMPLETED, add metrics + result files to the DB, write the Djerba report, then deliver.
# Submitted by oncoanalyser_watch.sh. Usage: oncoanalyser_post_run.sh -d <run_dir> [-n]
# Run folder name = group (same rule as the metrics script).

set -eo pipefail
umask 007

SCRIPTS=~/MoH_Phase2_Automation/analysis
DELIVERY_DIR=""     # TODO-----------------------------------------------------------------------------------------------------------------------------
PT_CLI="pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q"

usage() {
    echo "Usage: $(basename "$0") -d <run_dir> [-n]   (-n: no pt-cli ingest, for tests)"
    exit 1
}
while getopts 'hd:n' OPTION; do
    case "$OPTION" in
        d) run_dir="$OPTARG" ;;
        n) no_ingest=true ;;
        *) usage ;;
    esac
done
[[ "$run_dir" ]] || usage

group=$(basename "$run_dir")
json=$run_dir/$group.oncoanalyser.json

# 1. only finished, complete runs
if ! "$SCRIPTS"/check_oncoanalyser.sh -d "$run_dir" -g "$group"; then
    echo "$group is not COMPLETED: nothing done."
    exit 0
fi

# 2. metrics + result files (md5) -> DB (metrics script exits 1 if no file was added: no ingest then)
source ~/project_tracking_cli/.venv/bin/activate
python3 "$SCRIPTS"/oncoanalyser_metrics_tracking.py -i "$run_dir" -j "$json" -f
if [ "$no_ingest" = true ]; then
    echo "-n: skipping pt-cli ingest analysis"
else
    $PT_CLI ingest analysis --input-json "$json"
fi

# 3. Djerba report (failure does not stop delivery)
~/MoH_Phase2_Automation/report/djerba_report.sh -d "$run_dir" -g "$group" \
    || echo "WARNING: no Djerba report for $group (see the error above)"

# 4. deliver
if [ -z "$DELIVERY_DIR" ]; then
    echo "DELIVERY_DIR not set: $group not delivered."
    exit 0
fi
"$SCRIPTS"/oncoanalyser_delivery.sh -d "$run_dir" -o "$DELIVERY_DIR"