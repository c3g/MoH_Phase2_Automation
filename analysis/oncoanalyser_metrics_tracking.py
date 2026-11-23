#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
import sys
import glob
import logging
import gzip
from datetime import datetime, timedelta

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_FLAGS = {"PASS", "WARNING", "FAILED", "MISSING", "NOT_APPLICABLE"} # for metrics
UNFLAGGED_DELIVERABLE_FLAG = "NOT_APPLICABLE"   # to confirm
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# mappping NF to DB
# Nextflow trace status -> DB status
NEXTFLOW_TO_DB_STATUS = { # for tool jobs
    "COMPLETED": "COMPLETED",
    "CACHED": "COMPLETED",   # DB has no CACHED
    "FAILED": "FAILED",
    "ABORTED": "CANCELLED",
}
# head job status: see run_status() (same rule as oncoanalyser_post_run.sh)

# # # HOW THE RESULTS FOLDER IS SCTRUCTURED and linking it to job/process name # # #
# some results are per sample (alignments etc) and some are pair-level (amber etc)
# some results are under flat folder and some are under subfolders named after the sample (e.g. bamtools)
# process -> (which samples get a job, its results under results/<group>/ ; {s} = the job's sample)
N, T, R = "normal", "tumor", "rna"   # same words as the -t/--sample_type argument
PROCESSES = { # processes incldue all the unique job names in the execution traces
    # alignment
    "FASTP_SPLIT":          ((N, T), None),
    "BWAMEM2_ALIGN":        ((N, T), None),
    "REDUX":                ((N, T), "alignments/{s}"),
    "STAR_ALIGN":           ((R,),   None),
    "SAMTOOLS_SORT":        ((R,),   None),
    "GATK4_MARKDUPLICATES": ((R,),   "alignments/{s}"),
    # per sample
    "BAMTOOLS":             ((N, T), "bamtools/{s}"),
    "CIDER":                ((T, R), "cider"),   # flat folder
    "SAGE_APPEND_GERMLINE": ((N,),   "sage_append/{s}"),
    "SAGE_APPEND_SOMATIC":  ((T,),   "sage_append/{s}"),

    # tumor/normal pair -> on the tumor
    "AMBER":                ((T,), "amber"),
    "COBALT":               ((T,), "cobalt"),
    "SAGE_SOMATIC":         ((T,), "sage/somatic"),
    "SAGE_GERMLINE":        ((T,), "sage/germline"),
    "SAGE_VISUALISER":      ((T,), "sage/visualiser"),
    "PAVE_SOMATIC":         ((T,), "pave/somatic"),
    "PAVE_GERMLINE":        ((T,), "pave/germline"),
    "ESVEE":                ((T,), "esvee"),
    "PURPLE":               ((T,), "purple"),
    "LINX_SOMATIC":         ((T,), "linx/somatic_annotations"),
    "LINX_GERMLINE":        ((T,), "linx/germline_annotations"),
    "LINX_VISUALISER":      ((T,), "linx/somatic_plots"),
    "LINXREPORT":           ((T,), "linx/{s}_linx.html"),
    "CHORD":                ((T,), "chord"),
    "SIGS":                 ((T,), "sigs"),
    "LILAC":                ((T,), "lilac"),
    "TEAL_PREP":            ((T,), None),
    "TEAL_PIPELINE":        ((T,), "teal"),
    "VIRUSBREAKEND":        ((T,), "virusbreakend"),
    "VIRUSINTERPRETER":     ((T,), "virusinterpreter"),
    "CUPPA":                ((T,), "cuppa"),
    "NEO_FINDER":           ((T,), "neo/finder"),
    "NEO_ANNOTATE_FUSIONS": ((T,), "neo/annotated_fusions"),
    "NEO_SCORER":           ((T,), "neo/scorer"),
    "QSEE":                 ((T,), "qsee"),
    "ORANGE":               ((T,), "orange"),
    # others
    "PEACH":                ((N,), "peach"),
    "ISOFOX":               ((R,), "isofox"),                # files named after the tumor DNA
}
# processes that only run when the samplesheet has RNA (checked against onco 3.0.0)
RNA_PROCESSES = {
    "STAR_ALIGN", "SAMTOOLS_SORT", "GATK4_MARKDUPLICATES", "ISOFOX",
    "SAGE_APPEND_GERMLINE", "SAGE_APPEND_SOMATIC",
    "NEO_ANNOTATE_FUSIONS",
}
def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='oncoanalyser_metrics_tracking.py',
        description="Adds jobs and QC metrics of an oncoanalyser run (at any stage) to its project tracking json."        )
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
    
    parser.add_argument(
        '-r',
        '--readset',
        required=True,
        help="Readset to update (readset_name)."
        )

    parser.add_argument(
        '-s',
        '--sample',
        required=True,
        help="sample_id of that readset (samplesheet sample_id)."
        )
    parser.add_argument(
        '-t',
        '--sample_type',
        required=True,
        choices=["normal", "tumor", "rna"],
        help="Role of the sample: normal (DNA), tumor (DNA) or rna (tumor RNA)."
        )
    parser.add_argument(
        '-T',
        '--tumor_sample',
        required=True,
        help="sample_id of the tumor DNA of the run (QSEE and ISOFOX files are named after it)."
        )
    parser.add_argument(
        '--ffpe',
        choices=["yes", "no"],
        default=None,
        help="FFPE status of this readset's sample. Not given = treated as not FFPE."
        )
    return parser.parse_args()

# for now: same rule as post run script
def run_status(run_dir, group, tumor_dna):
    """
    Run status, SAME RULE AS oncoanalyser_post_run.sh:
    COMPLETED = log says completed successfully AND the ORANGE pdf exists
    FAILED    = log says completed with errors, or success without ORANGE
    RUNNING   = no end line yet (running, killed or stuck)
    """
    log = os.path.join(run_dir, '.nextflow.log')
    if not os.path.exists(log):
        return "PENDING"
    success = errors = False
    with open(log, encoding='utf-8', errors='replace') as f:
        for line in f:
            if "Pipeline completed successfully" in line:   # also matches "..., but with errored process(es)" (ignored LILAC)
                success = True
            elif "Pipeline completed with errors" in line:
                errors = True
    if success:
        orange = os.path.join(run_dir, 'results', group, 'orange', f'{tumor_dna}.orange.pdf')
        if os.path.isfile(orange) and os.path.getsize(orange) > 0:
            return "COMPLETED"
        logger.warning(f"log says completed but {orange} is missing: FAILED")
        return "FAILED"
    if errors:
        return "FAILED"
    return "RUNNING"

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




def run_has_rna(samplesheet):
    """True if the run has a tumor RNA sample (RNA-only processes only run then)."""
    with open(samplesheet, encoding='utf-8') as f:
        return any(row["sequence_type"] == "rna" for row in csv.DictReader(f))


def main():
    """ Main """
    args = parse_arguments()
    json_output = load_json_file(args.json)
    if json_output is None:
        logger.error("No launch json to add metrics to - stopping.")
        sys.exit(1)

    group = os.path.basename(os.path.normpath(args.input))
    results_dir = os.path.join(args.input, "results")
    jobs = jsonify_oncoanalyser_metrics(args.input, group, results_dir, args.json,
                                        args.readset, args.sample, args.sample_type, args.tumor_sample,
                                        ffpe={"yes": True, "no": False}.get(args.ffpe))   # not given FOR NOW: None
    add_jobs(json_output, args.sample, [args.readset], jobs)
    json_output["operation_status"] = jobs[0]["job_status"]
    save_json_file(args.json, json_output)

def jsonify_oncoanalyser_metrics(run_dir, group, results_dir, output_json, readset, sample_id, role, tumor_dna, ffpe=None):
    """
    Jobs of ONE readset for the project tracking json (called by oncoanalyser2json.py once the run has started, in practice from post_run):
    - the head job oncoanalyser.<group> (status from .nextflow.log + ORANGE, like the post-run; times from traces + .nextflow/history)
    - one job per process this sample owns (status + times from the latest Nextflow trace)
    - QC metrics on the qsee, bamtools, purple, isofox jobs
    - result files (+ md5) of the COMPLETED jobs, once the run has ended (COMPLETED or FAILED)
    (the manual main() also sets operation_status = head job status)
    ffpe: True / False = FFPE status of this readset's sample; None (default) = not given, treated as not FFPE
    """

    has_rna = run_has_rna(find_samplesheet(run_dir, group))
    head = head_job(run_dir, group, tumor_dna)        # updates the head job made at launch
    trace_rows = read_traces(results_dir)

    # files for each COMPLETED job, once the run has stopped (mid-run outputs may still be copying)
    run_stopped = head["job_status"] in ("COMPLETED", "FAILED")

    # 1. one job per process this sample owns (status + times from the trace; PENDING if not run yet)
    jobs = {}
    for process, (owners, _) in PROCESSES.items():
        if role not in owners or (process in RNA_PROCESSES and not has_rna):
            continue
        job = make_job(process, sample_id, group, trace_rows)
        if run_stopped and job["job_status"] == "COMPLETED":
            job["file"] = job_files(process, sample_id, group, results_dir)
        jobs[process] = job

    # 2. metrics of this sample, read only once the tool's job is COMPLETED
    def done(process):
        return make_job(process, sample_id, group, trace_rows)["job_status"] == "COMPLETED"

    metrics = {}
    if role in (N, T):
        # QSEE runs once on the pair: one file named after the tumor, with normal + tumor rows
        if done("QSEE"):
            metrics["QSEE"] = extract_qsee(group, tumor_dna, results_dir).get(sample_id, [])
        if done("BAMTOOLS"):
            metrics["BAMTOOLS"] = extract_bamtools(group, sample_id, results_dir, ffpe)
    if role == T and done("PURPLE"):
        metrics["PURPLE"] = extract_purple(group, sample_id, results_dir)
    if role == R and done("ISOFOX"):
        metrics["ISOFOX"] = extract_isofox(group, tumor_dna, results_dir)   # files named after the tumor DNA

    for process, sample_metrics in metrics.items():
        if not sample_metrics:
            continue
        # the normal has no QSEE job of its own (QSEE belongs to the tumor): made here for its metrics
        job = jobs.get(process) or make_job(process, sample_id, group, trace_rows)
        job["metric"] = set_db_flags(sample_metrics)
        jobs[process] = job

    # 3. into the json, under this readset
    return [head] + list(jobs.values())     # this readset's job list: head job first

def parse_duration(text): #needed because onco history doesnt show end time, so we calculate it 
    """Nextflow duration convert to timedelta."""
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}
    seconds = 0
    for part in text.split():
        num = part.rstrip("smhd")
        seconds += float(num) * units[part[len(num):]]
    return timedelta(seconds=seconds)


def first_task_start(results_dir):
    """Earliest task start over all launches traces, which we use to set the start time of the head job"""
    starts = []
    for trace in glob.glob(os.path.join(results_dir, 'pipeline_info', 'execution_trace_*.txt')):
        with open(trace, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row.get("name"):
                    start = task_times(row)[0]
                    if start:
                        starts.append(start)
    return min(starts, default=None)


def head_job(run_dir, group, tumor_dna):
    """
    Head job oncoanalyser.<group> (same name as oncoanalyser2json.py).
    status = run_status() (same rule as oncoanalyser_post_run.sh)
    start  = first task that ran, over all launches (traces)
    stop   = end of the latest launch (.nextflow/history)
    """
    job = {"job_name": f"oncoanalyser.{group}", "job_start": None, "job_stop": None,
           "job_status": run_status(run_dir, group, tumor_dna)}

    history = os.path.join(run_dir, '.nextflow', 'history')
    if not os.path.exists(history):
        return job  # not started yet

    # columns: start, duration, run name, status, revision, session id, command
    with open(history, encoding='utf-8') as f:
        launches = [line.rstrip('\n').split('\t', 6) for line in f if line.count('\t') >= 6]
    if not launches:
        return job

    first, last = launches[0], launches[-1]
    # start = first task that launched (if not, first ever launch from hist)
    job["job_start"] = first_task_start(os.path.join(run_dir, 'results')) or first[0][:19]
    #these next lines would be useful if we want the start to be the first try of this run
    # same_run = [launch for launch in launches if launch[6] == last[6]]
    #job["job_start"] = same_run[0][0][:19]
    if last[1] != "-" and job["job_status"] != "RUNNING":   # no stop time while still running
        end = datetime.strptime(last[0][:19], DATE_FMT) + parse_duration(last[1])
        job["job_stop"] = end.strftime(DATE_FMT)
    return job

def read_traces(results_dir):
    """Task rows of the latest launch (newest execution_trace_*.txt). A retried task keeps its last row."""
    traces = sorted(glob.glob(os.path.join(results_dir, 'pipeline_info', 'execution_trace_*.txt')))
    if not traces:
        return []  # not started yet

    rows = {}
    with open(traces[-1], encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            if row.get("name"):  # skip a half-written last line
                rows[row["name"]] = row
    return list(rows.values())

def make_job(process, sample_id, group, trace_rows):
    """
    Makes a job dict for each job that can be ingested into the json
    Job <process>.<sample_id>: status + start/end from that process's tasks in the trace.
    """
    job = {"job_name": f"{process.lower()}.{sample_id}", "job_start": None, "job_stop": None, "job_status": "PENDING"}

    rows = []
    for r in trace_rows: #goes through all trace rows to find matching with the process name and add them to the list
        name, _, tag = r["name"].rstrip(")").partition(" (")
        if name.split(":")[-1] != process:
            continue
        # tag is group + pair task or group + sample +[_lane...] (per-sample task)
        rest = tag.removeprefix(f"{group}_")
        if tag == group or rest == sample_id or rest.startswith(f"{sample_id}_"):
            rows.append(r)

    if not rows:
        return job  # nothing finished yet

    statuses = [NEXTFLOW_TO_DB_STATUS.get(r["status"], "FAILED") for r in rows]
    if "FAILED" in statuses:
        job["job_status"] = "FAILED"
    elif "CANCELLED" in statuses:
        job["job_status"] = "CANCELLED"
    else:
        job["job_status"] = "COMPLETED"

    starts, stops = zip(*[task_times(r) for r in rows])
    job["job_start"] = min((t for t in starts if t), default=None)
    job["job_stop"] = max((t for t in stops if t), default=None)
    return job

def task_times(row):
    """(start, stop) of one trace row. Real start/complete columns if present else computed."""
    try:
        start, stop = row.get("start") or "-", row.get("complete") or "-"
        if start != "-" and stop != "-":
            return start[:19], stop[:19]
        # older traces: end = submit + duration, start = end - realtime
        end = datetime.strptime(row["submit"][:19], DATE_FMT) + parse_duration(row["duration"])
        begin = end - parse_duration(row["realtime"])
        return begin.strftime(DATE_FMT), end.strftime(DATE_FMT)
    except (TypeError, ValueError, KeyError):
        return None, None

def add_jobs(json_output, sample_id, readsets, jobs):
    """Put the jobs under every readset of the sample. Same job name = updated in place (rerun)."""
    samples = json_output.setdefault("sample", [])
    sample = next((s for s in samples if s.get("sample_name") == sample_id), None)
    if sample is None:
        logger.warning(f"{sample_id} not in the json, adding it")
        sample = {"sample_name": sample_id, "readset": []}
        samples.append(sample)
    sample.pop("metric", None)  # remove old metrics if any

    # put the jobs under each readset of the sample
    for name in readsets:
        readset = next((r for r in sample.setdefault("readset", []) if r["readset_name"] == name), None)
        if readset is None:
            readset = {"readset_name": name, "job": []}
            sample["readset"].append(readset)

        existing = {j["job_name"]: j for j in readset.setdefault("job", [])}
        for job in jobs:
            if job["job_name"] in existing:
                existing[job["job_name"]].update(job)   # write into the existing job (incl. the head job)
            else:
                readset["job"].append(job)

def set_db_flags(metrics):
    """Make flags DB-safe: unknown flag -> None (warning), no flag -> UNFLAGGED_DELIVERABLE_FLAG (the DB rejects a null flag)."""
    for m in metrics:
        if m["metric_flag"] not in ALLOWED_FLAGS:
            if m["metric_flag"] is not None:   # None = no threshold.  anything else= unexpected
                logger.warning(f"{m['metric_name']}: unknown flag {m['metric_flag']}, set to None")
            m["metric_flag"] = None
        if m["metric_flag"] is None:           # any metric, deliverable or not: never send a null flag
            m["metric_flag"] = UNFLAGGED_DELIVERABLE_FLAG
    return metrics

def md5sum(path):
    """md5 of a file, read in 8 MB chunks for bams"""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def job_files(process, sample_id, group, results_dir):
    """Result files of one process for one sample (folder from PROCESSES), with md5."""
    path = PROCESSES[process][1]
    if path is None:                       # process has no results folder (e.g. FASTP_SPLIT)
        return []
    path = os.path.join(results_dir, group, path.format(s=sample_id))
    if os.path.isfile(path):              
        paths = [path]
    else:                                  # a folder: take every file in it subfolders too
        paths = sorted(p for p in glob.glob(os.path.join(path, "**"), recursive=True) if os.path.isfile(p))
    if process == "CIDER":                 # exception: flat folder:  one cider/ folder for tumor DNA and RNA: keep this sample's files
        paths = [p for p in paths if os.path.basename(p).startswith(sample_id)]
    return [{
        "file_name": os.path.basename(p),
        "location_uri": f"cardinal://{os.path.abspath(p)}",  # same cardinal://<full path> format as transfer2json.py
        "file_md5sum": md5sum(p),
        "file_deliverable": True,
    } for p in paths]

# group:  group_id from the samplesheet = run folder name (e.g. MoHQ-CQ-36-94_G0).
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
                "metric_flag": status_flag(row["QcStatus"]),
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

    # metrics: qc status (with flag), ploidy, purity_gate.
    # QSEE still reports purity (with PURPLE's own 0.20 WARN) and contamination;
    # purity_gate is the separate consortium gate (MOHCCN: purity >= 30%).
    metrics = [
        {"metric_name": "purple_qc_status", "metric_value": qc["QCStatus"], "metric_flag": status_flag(qc["QCStatus"]), "metric_deliverable": True},
        {"metric_name": "ploidy", "metric_value": purity_tsv["ploidy"], "metric_flag": None, "metric_deliverable": True},
    ]

    # purity_gate: < 0.30 -> WARNING, else PASS
    try:
        purity_flag = "WARNING" if float(purity_tsv["purity"]) < 0.30 else "PASS"
    except (KeyError, ValueError):
        purity_flag = "MISSING"
    metrics.append({"metric_name": "purity_gate", "metric_value": purity_tsv.get("purity"),
                    "metric_flag": purity_flag, "metric_deliverable": True})
    return metrics


def status_flag(status):
    """Tool QC status -> DB flag. Handles PASS, WARN*, FAIL* and comma-joined like PURPLE)."""
    parts = status.split(',')
    if any(p.startswith('FAIL') for p in parts):
        return "FAILED"
    if any(p.startswith('WARN') for p in parts):
        return "WARNING"
    if status == "PASS":
        return "PASS"
    logger.warning(f"unknown QC status: {status}")
    return None


def extract_bamtools(group, sample, results_dir, ffpe=None):
    """
    Bamtools metrics that QSEE does not report.
    ffpe: True / False / None (not given = not FFPE). uses insert_size_flags().
    Return: list
    """

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

    # frag_length.tsv: mean + median insert size, computed from the histogram (length, count)
    if os.path.exists(frag_file):
        hist = []
        with open(frag_file, encoding='utf-8') as f:
            next(f)  # skip header
            for line in f:
                length, count = line.rstrip('\n').split('\t')
                hist.append((int(length), int(count)))
        hist.sort()
        total = sum(count for _, count in hist)
        if total == 0:
            logger.warning(f"empty {frag_file}")
            return metrics
        weighted = sum(length * count for length, count in hist)

        # median = first length where the running count reaches half the reads
        running = 0
        for median, count in hist:
            running += count
            if running >= total / 2:
                break
        mean = weighted / total
        mean_flag, median_flag = insert_size_flags(mean, median, ffpe)

        metrics.append({"metric_name": "mean_insert_size", "metric_value": f'{mean:.1f}', "metric_flag": mean_flag, "metric_deliverable": True})
        metrics.append({"metric_name": "median_insert_size", "metric_value": str(median), "metric_flag": median_flag, "metric_deliverable": True})
    else:
        logger.warning(f"missing {frag_file}")

    return metrics

def insert_size_flags(mean, median, ffpe=None):
    # DNA insert size flags to mean_flag, median_flag
    # mean < 150 WARNING, else PASS
    # median: FFPE -> no flag; not FFPE or unknown < 250 WARNING, else PASS
    mean_flag = "WARNING" if mean < 150 else "PASS"
    median_flag = None if ffpe else ("WARNING" if median < 250 else "PASS")
    return mean_flag, median_flag

def extract_isofox(group, sample, results_dir):
    """
    Isofox RNA QC metrics.
    The summary file is named after the tumour DNA sample, not the RNA sample.
    Return: list
    """

    summary_file = os.path.join(results_dir, group, 'isofox', f'{sample}.isf.summary.tsv')

    if not os.path.exists(summary_file):
        logger.warning(f"missing {summary_file}")
        return []

    # summary.tsv
    with open(summary_file, encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
        values = f.readline().rstrip('\n').split('\t')
    summary = dict(zip(header, values))

    # total_fragments
    # Isofox counts genic fragments only (lower than sequenced clusters)  
    # the real gate is raw_clusters (run processing).
    try:
        fragments_flag = "WARNING" if float(summary["TotalFragments"]) < 80_000_000 else "PASS"
    except (KeyError, ValueError):
        fragments_flag = "MISSING"

    metrics = [
        {"metric_name": "isofox_qc_status", "metric_value": summary["QcStatus"], "metric_flag": status_flag(summary["QcStatus"]), "metric_deliverable": True},
        {"metric_name": "total_fragments", "metric_value": summary.get("TotalFragments"), "metric_flag": fragments_flag, "metric_deliverable": True},
        {"metric_name": "duplicate_fragments", "metric_value": summary["DuplicateFragments"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "spliced_fragment_perc", "metric_value": summary["SplicedFragmentPerc"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "chimeric_fragment_perc", "metric_value": summary["ChimericFragmentPerc"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "spliced_gene_count", "metric_value": summary["SplicedGeneCount"], "metric_flag": None, "metric_deliverable": True},
        {"metric_name": "rna_fragment_length_median", "metric_value": summary.get("FragLength50th"), "metric_flag": None, "metric_deliverable": True},
    ]
    return metrics

if __name__ == '__main__':
    main()