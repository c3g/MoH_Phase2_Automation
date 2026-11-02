#!/usr/bin/env python3

import argparse
import csv
import json
import os
import sys
import glob
import logging
import gzip
from datetime import datetime

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_FLAGS = {"PASS", "WARNING", "FAILED", "MISSING", "NOT_APPLICABLE"} # for metrics
UNFLAGGED_DELIVERABLE_FLAG = "NOT_APPLICABLE"   # to confirm

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
        '-j',
        '--json',
        required=True,
        help="Json to update in place (made by oncoanalyser2json.py)."
        )
    return parser.parse_args()


def load_json_file(path):
    """Load a json file. Return None if missing"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Can't read {path}: {e}")
        return None


def save_json_file(path, data):
    """Write the json."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.info(f"Json written: {path}")

def find_samplesheet(run_dir, group):
    """
    Newest samplesheet of the run: <run>/samplesheets/<timestamp>/<group>.samplesheet.csv
    """
    found = sorted(glob.glob(os.path.join(run_dir, 'samplesheets', '*', f'{group}.samplesheet.csv')))
    if found:
        return found[-1]

    for name in (f'{group}.samplesheet.csv', 'samplesheet.csv'):
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            logger.warning(f"using old samplesheet location: {path}")
            return path

    logger.error(f"no samplesheet found in {run_dir}")
    sys.exit(1)




def read_samplesheet(samplesheet):
    """
    Sample id + readsets (library_id in the info column) of each sample.
    Return: {"normal_dna": {"sample_id", "readsets"}, "tumor_dna": {...}, "tumor_rna": {...} or None}
    """
    roles = { # all accepted combinations for sample_id
    ("normal", "dna"): "normal_dna",
    ("tumor", "dna"): "tumor_dna",
    ("tumor", "rna"): "tumor_rna",
    }
    samples = {"normal_dna": None, "tumor_dna": None, "tumor_rna": None}

    with open(samplesheet, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            role = roles.get((row["sample_type"], row["sequence_type"]))
            if role is None:
                continue

            info = dict(part.split(":", 1) for part in row["info"].split(";") if ":" in part)
            readset = info.get("library_id")
            if not readset:
                logger.error(f"no library_id for {row['sample_id']}: {row['info']}")
                sys.exit(1)

            #collect all readsets for each sample_id
            if samples[role] is None:
                samples[role] = {"sample_id": row["sample_id"], "readsets": []}
            elif samples[role]["sample_id"] != row["sample_id"]:
                logger.error(f"two {role} samples: {samples[role]['sample_id']}, {row['sample_id']}")
                sys.exit(1)

            if readset not in samples[role]["readsets"]:
                samples[role]["readsets"].append(readset)

    if not samples["normal_dna"] or not samples["tumor_dna"]:
        logger.error(f"need a normal and a tumor DNA sample: {samplesheet}")
        sys.exit(1)

    return samples

def make_job(tool, sample_id, metrics):
    """One job = one tool for one sample, with its metrics."""
    for m in metrics:
        if m["metric_flag"] is not None and m["metric_flag"] not in ALLOWED_FLAGS:
            logger.warning(f"{tool} {m['metric_name']}: unknown flag {m['metric_flag']}")
            m["metric_flag"] = None
        if m["metric_deliverable"] and m["metric_flag"] is None: # the metric is deliverable but doesnt have a flag 
            m["metric_flag"] = UNFLAGGED_DELIVERABLE_FLAG

    return {
        "job_name": f"{tool}.{sample_id}",   # per sample-id, so normal/tumor metrics don't overwrite each other
        "job_start": None,                   # TODO:-------------------------------------------------------------------- from the trace
        "job_stop": None,
        "job_status": "COMPLETED",           # script only runs on  runs that are compelted
        "metric": metrics,
    }

def main():
    """ Main """
    args = parse_arguments()
 
    # the run folder is named after the group (launch script: ${MOH_DIR}/${CASE}/${GROUP})
    # one group = one tumor+ normal
    group = os.path.basename(os.path.normpath(args.input))
    samplesheet = find_samplesheet(args.input, group)
    results_dir = os.path.join(args.input, "results")
    jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, args.json)
 
def jsonify_oncoanalyser_metrics(group, samplesheet, results_dir, output_json):
    """
    Add QC metrics to the project tracking json of the oncoanalyser run:
    one job per tool per sample, under every readset of that sample.
    """
    # Open the json made at launch (oncoanalyser2json.py)
    json_output = load_json_file(output_json)
    if json_output is None:
        # load_json_file() already logged why (missing or broken file)
        logger.error("No launch json to add metrics to - stopping.")
        sys.exit(1)

    
    # Samples of the run + their readsets (normal/tumor DNA, tumor RNA if exists)
    samples = read_samplesheet(samplesheet)
    normal_dna = samples["normal_dna"]["sample_id"]
    tumor_dna = samples["tumor_dna"]["sample_id"]
    tumor_rna = samples["tumor_rna"]["sample_id"] if samples["tumor_rna"] else None

    # QSEE
    qsee = extract_qsee(group, tumor_dna, results_dir)

    # metrics per sample, per tool (each tool = one job)
    sample_tools = {
        normal_dna: {
            "qsee": qsee.get(normal_dna, []),
            "bamtools": extract_bamtools(group, normal_dna, results_dir),
        },
        tumor_dna: {
            "qsee": qsee.get(tumor_dna, []),
            "bamtools": extract_bamtools(group, tumor_dna, results_dir),
            "purple": extract_purple(group, tumor_dna, results_dir),
        },
    }
    if tumor_rna:
        # ISOFOX files are named after the tumor DNA
        sample_tools[tumor_rna] = {"isofox": extract_isofox(group, tumor_dna, results_dir)}

    readsets = {s["sample_id"]: s["readsets"] for s in samples.values() if s}

    for sample_id, tools in sample_tools.items():
        jobs = [make_job(tool, sample_id, metrics) for tool, metrics in tools.items() if metrics]
        add_jobs(json_output, sample_id, readsets[sample_id], jobs)

    json_output["operation_status"] = "COMPLETED"
    save_json_file(output_json, json_output)




def add_jobs(json_output, sample_id, readsets, jobs):
    """Put the jobs under every readset of the sample. Same job name = replaced (rerun)."""
    samples = json_output.setdefault("sample", [])
    sample = next((s for s in samples if s.get("sample_name") == sample_id), None)
    if sample is None:
        logger.warning(f"{sample_id} not in the json, adding it")
        sample = {"sample_name": sample_id, "readset": []}
        samples.append(sample)
    sample.pop("metric", None)  # remove old metrics if any

    #put jobs under each readset
    new_names = {j["job_name"] for j in jobs} 
    for name in readsets:
        readset = next((r for r in sample.setdefault("readset", []) if r["readset_name"] == name), None)
        if readset is None:
            readset = {"readset_name": name, "job": []}
            sample["readset"].append(readset) # adds all readsets from one sample_id
        readset["job"] = [j for j in readset.get("job", []) if j["job_name"] not in new_names] + jobs #replaces the old job list with any new jobs -remove old ones


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