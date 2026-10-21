#!/usr/bin/env python3

import argparse
import csv
import json
import os
import logging

import gzip

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(prog=os.path.basename(__file__), description="Creates the project tracking json for an oncoanalyser run.")

    # instead of direct paths?
    parser.add_argument('-r', '--results', required=True, help="Results folder of the oncoanalyser run.")
    parser.add_argument('-s', '--samplesheet', required=False, help="Samplesheet used for the oncoanalyser run.")
    parser.add_argument('-o', '--output', required=True, help="Output json filename.")
    args = parser.parse_args()

    jsonify_oncoanalyser(args.results, args.output)

def jsonify_oncoanalyser(results_dir, output_json):
    """
    Create the json file for the oncoanalyser run.
    """
    # Run info: 
    json_output = {
        "project_name": "MOH-Q",
        "operation_config_name": "oncoanalyser_config",
        "operation_config_version": "3.0.0",
        "operation_config_md5sum": None,     # TODO once conf is decided
        "operation_config_data": None,       # TODO
        "operation_platform": "cardinal", 
        "operation_cmd_line": None,        # TODO:
        "operation_name": "oncoanalyser",
        "sample": []            #todo
        }

    # Samples and readsets (from the samplesheet)
    #  get_sample_dict()

    #Jobs (start/stop/status)
    # get_job_info()

    #  QC metrics (values + flags)
    #  extract_purple(), extract_bamtools(), extract_isofox()

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=4)
    logger.info(f"Json written: {output_json}") #maybe remove

def get_sample_dict(samplesheet):

    pass

def get_job_info(results_dir):

    pass


def extract_qsee(patient, tumour_sample, results_dir):
    """
    QSEE QC metrics (value + flag) for the tumour and normal samples
    QSEE flags are already calculated based on the qsee thresholds file (in configs). 
    Return: dict (sample name -> list of metrics)
    """

    # pro for qsee: already has pass/fail flags for each metric, though it doesn't include all the metrics 
    # and we are already giving it qsee thresholds, which we can update manually
    # maybe need a fallback though in case qsee is missing or we're using older onco 


    flags = {"PASS": "PASS", "WARN": "WARNING", "FAIL": "FAILED"} # to match genpipes

    qsee_file = os.path.join(results_dir, patient, 'qsee', f'{tumour_sample}.qsee.status.tsv.gz')

    if not os.path.exists(qsee_file):
        print(f"WARNING: missing {qsee_file}")
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

def extract_purple(patient, sample, results_dir):
    """
    Purple QC metrics (tumor) that QSEE doesn't cover.
    Return: list
    """
    #todo: add flags 

    purple_dir = os.path.join(results_dir, patient, 'purple')

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



def extract_bamtools(patient, sample, results_dir):
    """
    Bamtools metrics that QSEE does not report.
    Return: list
    """

    #todo: add flags 


    bamtools_dir = os.path.join(results_dir, patient, 'bamtools', sample)
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

def extract_isofox(patient, sample, results_dir): # todo

    return []

if __name__ == '__main__':
    main()