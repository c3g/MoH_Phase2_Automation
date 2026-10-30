#!/usr/bin/env python3

import argparse
import csv
import json
import os
import sys
import glob
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
        help="Json to update (Default: <run folder>/<group>.oncoanalyser.json)."
        )
    return parser.parse_args()
 
 
def main():
    """ Main """
    args = parse_arguments()
 
    # the run folder is named after the group (launch script: ${MOH_DIR}/${CASE}/${GROUP})
    # one group = one tumor+ normal
    group = os.path.basename(os.path.normpath(args.input))
    samplesheet = os.path.join(args.input, f"{group}.samplesheet.csv")
    results_dir = os.path.join(args.input, "results")
    # the json lives in the run folder, so every step (launch, after the run) finds the same file
    output = args.output or os.path.join(args.input, f"{group}.oncoanalyser.json")
 
    jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, output)
 
 
def jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, output_json):
    """
    Add QC metrics to the project tracking json of the oncoanalyser run.
    1 set of metrics per sample_id (normal DNA, tumor DNA, tumor RNA if exists).
    """
    # Open the json made at launch (oncoanalyser2json.py)
    json_output = load_json_file(output_json)
    if json_output is None:
        # load_json_file() already logged why (missing or broken file)
        logger.error("No launch json to add metrics to - stopping.")
        sys.exit(1)

    # Sample ids of the run - normal/tumor DNA and tumor RNA (if exists)
    normal_dna, tumor_dna, tumor_rna = get_samples(samplesheet)
    #runs always have tumor + normal DNA (RNA is optional)
    if not normal_dna or not tumor_dna:
        logger.error(f"Samplesheet needs a normal and a tumor DNA sample: normal={normal_dna}, tumor={tumor_dna}. Stopping.")
        sys.exit(1)

    # QSEE
    qsee = extract_qsee(group, tumor_dna, results_dir)

    # QC metrics of each sample
    sample_metrics = {}
    sample_metrics[normal_dna] = qsee.get(normal_dna, []) + extract_bamtools(group, normal_dna, results_dir)
    sample_metrics[tumor_dna] = (qsee.get(tumor_dna, [])
                                 + extract_bamtools(group, tumor_dna, results_dir)
                                 + extract_purple(group, tumor_dna, results_dir))
    if tumor_rna:
        # **** ISOFOX files are named after the tumor DNA ****
        sample_metrics[tumor_rna] = extract_isofox(group, tumor_dna, results_dir)

    # Put them under each sample in the json
    for sample_id, metrics in sample_metrics.items():
        add_metrics(json_output, sample_id, metrics)

    # Save the json
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=4)
    logger.info(f"Json written: {output_json}")


def get_samples(samplesheet):
    """
    Normal DNA, tumor DNA and tumor RNA sample_ids of the run, is useful to find out output filenames.
    """
    normal_dna = tumor_dna = tumor_rna = None
    with open(samplesheet, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row["sample_type"] == "normal" and row["sequence_type"] == "dna":
                normal_dna = row["sample_id"]
            elif row["sample_type"] == "tumor" and row["sequence_type"] == "dna":
                tumor_dna = row["sample_id"]
            elif row["sample_type"] == "tumor" and row["sequence_type"] == "rna":
                tumor_rna = row["sample_id"]
    return normal_dna, tumor_dna, tumor_rna


def add_metrics(json_output, sample_id, metrics):
    """
    Put the metrics under the sample in the json.
     metrics are REPLACED when the script re-runs on the same json
    """
    # TODO: which field of the oncoanalyser2json.py json holds the samplesheet sample_id
    for sample in json_output["sample"]:
        if sample.get("sample_name") == sample_id or sample_id in sample.get("sample_alias", []):
            sample["metric"] = metrics
            return

    logger.warning(f"{sample_id} not found in the json, metrics not added")


def get_job_info(results_dir): # ------------------------IN PROGRESS - for now turnaround time for each job 
    """
    Status of every task of the run, from Nextflow's newest trace file
    """
    traces = sorted(glob.glob(os.path.join(results_dir, 'pipeline_info', 'execution_trace_*.txt')))
    if not traces:
        logger.warning(f"no trace file in {results_dir}/pipeline_info")
        return {}

    jobs = {}
    with open(traces[-1], encoding='utf-8') as f:   
        for row in csv.DictReader(f, delimiter='\t'):
            job_name = row["name"].split(':')[-1]
            jobs[job_name] = row["status"]             # a retried task: the later row wins
    return jobs


# currently 
# group:  group_id from the samplesheet (e.g. MoHQ-CQ-36-94).
#   onco writes all results of a run to results/<group>/. One group = one casetype/tumor (+ its normal, + RNA if any).
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
    qc_file = os.path.join(purple_dir, f'{sample}.purple.qc')
    purity_file = os.path.join(purple_dir, f'{sample}.purple.purity.tsv')

    for path in (qc_file, purity_file):
        if not os.path.exists(path):
            logger.warning(f"missing {path}")
            return []

    qc = {}
    # purple qc
    with open(qc_file, encoding='utf-8') as f:
        for line in f:
            name, value = line.rstrip('\n').split('\t')
            qc[name] = value

    # purity.tsv: header line + one value line
    with open(purity_file, encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
        values = f.readline().rstrip('\n').split('\t')
    purity_tsv = dict(zip(header, values))

    # metrics - for now: qc status (with flag), ploidy, sex_check (purity, contamination etc. come from QSEE)
    metrics = [
        {"metric_name": "purple_qc_status", "metric_value": qc["QCStatus"], "metric_flag": purple_flag(qc["QCStatus"]), "metric_deliverable": True},
        {"metric_name": "ploidy", "metric_value": purity_tsv["ploidy"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "sex_check", "metric_value": f'{qc["AmberGender"]}/{qc["CobaltGender"]}', "metric_flag": None, "metric_deliverable": True},
    ]
    return metrics


def purple_flag(qc_status): #------------------------IN PROGRESS
    """
    Flag from purples own QCStatus. Several problems are joined with commas,
    """
    parts = qc_status.split(',')
    if any(part.startswith('FAIL') for part in parts):
        return "FAILED"
    if any(part.startswith('WARN') for part in parts):
        return "WARNING"
    if qc_status == "PASS":
        return "PASS"
    logger.warning(f"unknown PURPLE QCStatus: {qc_status}")
    return None


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