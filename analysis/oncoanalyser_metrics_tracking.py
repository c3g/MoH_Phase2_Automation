#!/usr/bin/env python3

import argparse
import csv
import json
import os
import logging

from compression import gzip

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

def extract_purple(patient, sample, results_dir): # currently, patient is group_id
    """
    Purple QC metrics (tumor).
    Return: list
    """
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
        {"metric_name": "purity", "metric_value": purity_tsv["purity"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "ploidy", "metric_value": purity_tsv["ploidy"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "contamination", "metric_value": qc["Contamination"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "sex_check", "metric_value": f'{qc["AmberGender"]}/{qc["CobaltGender"]}', "metric_flag": None, "metric_deliverable": True},
    ]
    return metrics

def extract_qsee(patient, tumour_sample, results_dir):
    """
    QSEE QC metrics (value + flag) for the tumour and normal samples.
    Return: dict (sample name -> list of metrics)
    """

    # todo : remove purity and contamination, either from qsee or from purple extract
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


def extract_bamtools(patient, sample, results_dir): #todo

    return []

def extract_isofox(patient, sample, results_dir): # todo

    return []

if __name__ == '__main__':
    main()