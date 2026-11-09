#!/usr/bin/env bash
#SBATCH --job-name=oncoanalyser_delivery
#SBATCH --time=12:00:00
#SBATCH --mem=4G

# Deliver one finished oncoanalyser run: copy results/<group>/ to <dest>/<group>/
# Usage: oncoanalyser_delivery.sh -d <run_dir> -o <dest>

set -eo pipefail
umask 007

usage() {
    echo "Usage: $(basename "$0") -d <run_dir> -o <dest> [-g <group>]   (default group: run folder name)"
        exit 1
}
while getopts 'hd:o:g:' OPTION; do
    case "$OPTION" in
        d) run_dir="$OPTARG" ;;
        o) dest="$OPTARG" ;;
        g) group="$OPTARG" ;;
        *) usage ;;
    esac
done

[[ "$run_dir" && "$dest" ]] || usage

group=${group:-$(basename "$run_dir")}   # default: run folder name 
src=$run_dir/results/$group

# only deliver finished and complete runs
   if ! ~/MoH_Phase2_Automation/analysis/check_oncoanalyser.sh -d "$run_dir" -g "$group"; then
       echo "ERROR: $group is not COMPLETED. Nothing copied."
       exit 1
   fi

mkdir -p "$dest"
cp -r "$src" "$dest/"

# copy must have the same total size as the source
if [ "$(du -sb "$src" | cut -f1)" != "$(du -sb "$dest/$group" | cut -f1)" ]; then
    echo "ERROR: $dest/$group size differs from $src"
    exit 1
fi
echo "Delivered $group to $dest/$group"

#  LATER: record the delivery in the DB ? -------------------------------------------------------------------------------------------------
# TOdo: files registered first (metrics script -f, then pt-cli ingest analysis),
