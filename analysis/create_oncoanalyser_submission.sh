#!/usr/bin/env bash

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-g group] [-d analysis_dir]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -g <group>                       Sample group for which to construct submission script. Sample sheet must already exist"
    echo " -d <analysis_dir>                Analysis directory where to write submission script."
    echo " -t <timestamp>                   Timestamp for analysis. (Default: current date and time)."
    exit 1                      
}

while getopts 'hg::d::t:' OPTION; do
    case "$OPTION" in
        g)
            GROUP="$OPTARG"
            ;;
        d)
            ANALYSIS_DIR="$OPTARG"
            ;;
        t)
            TIMESTAMP="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done

# mandatory arguments
if [[ ! "$GROUP" && ! "$ANALYSIS_DIR" ]]; then
    echo -e "ERROR: Missing mandatory argument -g or -d.\n"
    usage
fi

# mandatory arguments
if [[ ! "$TIMESTAMP" ]]; then
    TIMESTAMP=$(date +%FT%H.%M.%S)
fi

SAMPLESHEET=${ANALYSIS_DIR}/samplesheets/${TIMESTAMP}/${GROUP}.samplesheet.csv
if [ ! -f "$SAMPLESHEET" ]; then
    echo "Samplesheet is missing. Please run create_samplesheet.sh and try again."
    exit 1
fi

ONCOANALYSER_HOME=/cvmfs/soft.mugqic/CentOS6/software/oncoanalyser/oncoanalyser-3.0.0/pipeline/
ONCOANALYSER_CONFIGS=/cvmfs/soft.mugqic/CentOS6/software/oncoanalyser/oncoanalyser-3.0.0/config
MOH_DIR=/project/60007/MOH_PHASE2
ONCO_SITE_DIR=${MOH_DIR}/oncoanalyser_prod/config

echo """#!/bin/bash
#SBATCH --job-name=oncoanalyser_${GROUP}
#SBATCH --time=72:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH -o ${ANALYSIS_DIR}/${GROUP}.oncoanalyser_${TIMESTAMP}.out

umask 007
module use /cvmfs/soft.mugqic/CentOS6/modulefiles
module purge && module load mugqic/oncoanalyser/3.0.0

export NXF_HOME=${MOH_DIR}/oncoanalyser_prod/nxf_home
export ONCO_SITE_DIR=$ONCO_SITE_DIR

export NXF_OPTS="\$NXF_OPTS -Xms4g -Xmx12g"
export APPTAINER_TMPDIR=$ANALYSIS_DIR/tmp
mkdir -p \$APPTAINER_TMPDIR

cd $ANALYSIS_DIR && \\
nextflow run $ONCOANALYSER_HOME -profile singularity \\
  -c ${ONCOANALYSER_CONFIGS}/onco.config,${ONCO_SITE_DIR}/cardinal_site.config \\
  --mode wgts --genome GRCh38_hmf \\
  --input ${SAMPLESHEET} --outdir results \\
  -resume
""" > ${ANALYSIS_DIR}/${GROUP}.oncoanalyser_${TIMESTAMP}.submit

# create submission config trace
module purge && module load mugqic/oncoanalyser/3.0.0
nextflow -q -c ${ONCOANALYSER_CONFIGS}/onco.config -c ${ONCO_SITE_DIR}/cardinal_site.config config -show-profiles > ${ANALYSIS_DIR}/Oncoanalyser_${TIMESTAMP}.trace.config

echo "Oncoanalyser submission script created for group ${GROUP}."
