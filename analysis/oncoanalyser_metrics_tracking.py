#!/usr/bin/env python3

import argparse
import csv
import json
import os
import logging

import gzip

from oncoanalyser2json import load_json_file
 
logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

 
 
def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='oncoanalyser_metrics_tracking.py',
        description="Adds QC metrics of a finished oncoanalyser run to its project tracking json."
        )
    parser.add_argument(
        '-i',
        '--input',
        required=True,
        help="Folder of the analysis to be parsed."
        )
    parser.add_argument(
        '-o',
        '--output',
        default=None,
        help="Output json filename (Default: <group>.oncoanalyser.json)."
        )
    return parser.parse_args()
 
 
def main():
    """ Main """
    args = parse_arguments()
 
    # the run folder is named after the group (launch script: ${MOH_DIR}/${CASE}/${GROUP})
    group = os.path.basename(os.path.normpath(args.input))
    samplesheet = os.path.join(args.input, f"{group}.samplesheet.csv")
    results_dir = os.path.join(args.input, "results")
    output = args.output or f"{group}.oncoanalyser.json"   # same name as oncoanalyser2json.py
 
    jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, output)
 
 
def jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, output_json):
    """
    Add QC metrics to the project tracking json of the oncoanalyser run.
    """
    # Open the json made at launch (oncoanalyser2json.py)
    json_output = load_json_file(output_json)
 
    # Samples of the run (step 2)
    # samples = get_sample_dict(samplesheet)
    # normal_dna = find_sample(samples, "normal", "dna")
    # tumor_dna = find_sample(samples, "tumor", "dna")
    # tumor_rna = find_sample(samples, "tumor", "rna")   # None if DNA-only
 
    # QC metrics (values + flags) under each sample (step 4)
    # extract_qsee(), extract_purple(), extract_bamtools(), extract_isofox()
 
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=4)
    logger.info(f"Json written: {output_json}")
 
 

def get_sample_dict(samplesheet):

    pass

def get_job_info(results_dir):

    pass


# currently 
# group:  group_id from the samplesheet (e.g. MoHQ-CQ-36-94).
#   onco writes all results of a run to results/<group>/.
# sample: sample_id from the samplesheet: one normal DNA, tumor DNA or tumor RNA sample
#  (e.g. MoHQ-CQ-36-94-TEP087-1FDT). onco names its output files after it.

# IMPORTANT: some RNA results are named after the tumor DNA

def extract_qsee(group, tumour_sample, results_dir):
    """
    QSEE QC metrics (value + flag) for the tumour and normal samples
    QSEE flags are already calculated based on the qsee thresholds file (in configs). 
    Return: dict (sample name -> list of metrics)
    """

    # pro for qsee: already has pass/fail flags for each metric, though it doesn't include all the metrics 
    # and we are already giving it qsee thresholds, which we can update manually
    # maybe need a fallback though in case qsee is missing or we're using older onco 


    flags = {"PASS": "PASS", "WARN": "WARNING", "FAIL": "FAILED"} # to match genpipes

    qsee_file = os.path.join(results_dir, group, 'qsee', f'{tumour_sample}.qsee.status.tsv.gz')

    if not os.path.exists(qsee_file):
        logger.warning(f"missing {qsee_file}")
        return {}

    metrics = {}
    with gzip.open(qsee_file, 'rt', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            metric = {
                "metric_name": row["FeatureName"].lower(),
                "metric_value": row["FeatureValue"],
                "metric_flag": flags.get(row["QcStatus"], row["QcStatus"]),
                "metric_deliverable": True
            }
            metrics.setdefault(row["SampleId"], []).append(metric) # normal and tumor have different SampleIds
    return metrics

def extract_purple(group, sample, results_dir):
    """
    Purple QC metrics (tumor) that QSEE doesn't cover.
    Return: list
    """
    #todo: add flags 

    purple_dir = os.path.join(results_dir, group, 'purple')

    qc = {}
    # purple qc
    with open(os.path.join(purple_dir, f'{sample}.purple.qc'), encoding='utf-8') as f:
        for line in f:
            name, value = line.rstrip('\n').split('\t')
            qc[name] = value

    # purity.tsv: header line + one value line
    with open(os.path.join(purple_dir, f'{sample}.purple.purity.tsv'), encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
        values = f.readline().rstrip('\n').split('\t')
    purity_tsv = dict(zip(header, values))

    # metrics - for now: qc status, purity,ploidy, contamination, sex_check (flags to be added later)
    metrics = [
        {"metric_name": "purple_qc_status", "metric_value": qc["QCStatus"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "ploidy", "metric_value": purity_tsv["ploidy"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "sex_check", "metric_value": f'{qc["AmberGender"]}/{qc["CobaltGender"]}', "metric_flag": None, "metric_deliverable": True},
    ]
    return metrics



def extract_bamtools(group, sample, results_dir):
    """
    Bamtools metrics that QSEE does not report.
    Return: list
    """

    #todo: add flags 


    bamtools_dir = os.path.join(results_dir, group, 'bamtools', sample)
    summary_file = os.path.join(bamtools_dir, f'{sample}.bam_metric.summary.tsv')
    frag_file = os.path.join(bamtools_dir, f'{sample}.bam_metric.frag_length.tsv')

    if not os.path.exists(summary_file):
        logger.warning(f"missing {summary_file}")
        return []

    # summary.tsv for coverage metrics
    with open(summary_file, encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
        values = f.readline().rstrip('\n').split('\t')
    summary = dict(zip(header, values))

    metrics = [
        {"metric_name": "total_reads", "metric_value": summary["TotalReads"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "duplicate_reads_count", "metric_value": summary["DuplicateReads"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "median_coverage", "metric_value": summary["MedianCoverage"], "metric_flag": None, "metric_deliverable": True},
    ]

    # frag_length.tsv: mean insert size, computed from the histogram (length, count)
    if os.path.exists(frag_file):
        total = 0
        weighted = 0
        with open(frag_file, encoding='utf-8') as f:
            next(f)  # skip header
            for line in f:
                length, count = line.rstrip('\n').split('\t')
                total += int(count)
                weighted += int(length) * int(count)

        metrics.append({"metric_name": "mean_insert_size", "metric_value": f'{weighted / total:.1f}', "metric_flag": None, "metric_deliverable": True})
    else:
        logger.warning(f"missing {frag_file}")

    return metrics

def extract_isofox(group, sample, results_dir):
    """
    Isofox RNA QC metrics.
    The summary file is named after the tumour DNA sample, not the RNA sample.
    Return: list
    """

    # todo: add flags 


    flags = {"PASS": "PASS", "WARN": "WARNING", "FAIL": "FAILED"}  # to match genpipes??? 

    summary_file = os.path.join(results_dir, group, 'isofox', f'{sample}.isf.summary.tsv')

    if not os.path.exists(summary_file):
        logger.warning(f"missing {summary_file}")
        return []

    # summary.tsv
    with open(summary_file, encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
        values = f.readline().rstrip('\n').split('\t')
    summary = dict(zip(header, values))

    metrics = [
        {"metric_name": "isofox_qc_status", "metric_value": summary["QcStatus"], "metric_flag": flags.get(summary["QcStatus"], summary["QcStatus"]), "metric_deliverable": True},
        {"metric_name": "total_fragments", "metric_value": summary["TotalFragments"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "duplicate_fragments", "metric_value": summary["DuplicateFragments"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "spliced_fragment_perc", "metric_value": summary["SplicedFragmentPerc"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "chimeric_fragment_perc", "metric_value": summary["ChimericFragmentPerc"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "spliced_gene_count", "metric_value": summary["SplicedGeneCount"], "metric_flag": None, "metric_deliverable": True},
    ]
    return metrics

if __name__ == '__main__':
    main()