#!/usr/bin/env python3
"""PURPLE somatic VCF of oncoanalyser -> MAF for the Djerba snv_indel plugin."""

import argparse
import gzip
import re
import sys

# PAVE effect -> MAF class, only effects Djerba count as exonic
EFFECT_TO_CLASS = {
    'missense_variant':                 'Missense_Mutation',
    'stop_gained':                      'Nonsense_Mutation',
    'stop_lost':                        'Nonstop_Mutation',
    'start_lost':                       'Translation_Start_Site',
    'frameshift_variant':               'Frame_Shift_Del',   # Ins set by length in classify()
    'inframe_deletion':                 'In_Frame_Del',
    'inframe_insertion':                'In_Frame_Ins',
    'synonymous_variant':               'Silent',
    'splice_acceptor_variant':          'Splice_Site',
    'splice_donor_variant':             'Splice_Site',
    'splice_region_variant':            'Splice_Region',
    'upstream_gene_variant':            "5'Flank",
}

# most to least severe
EFFECT_RANK = [
    'stop_gained', 'frameshift_variant', 'splice_acceptor_variant',
    'splice_donor_variant', 'start_lost', 'stop_lost', 'inframe_deletion',
    'inframe_insertion', 'missense_variant', 'splice_region_variant',
    'synonymous_variant', 'upstream_gene_variant',
]

# required by Djerba, left empty
GNOMAD_POP_COLUMNS = [
    'gnomAD_AFR_AF', 'gnomAD_AMR_AF', 'gnomAD_ASJ_AF', 'gnomAD_EAS_AF',
    'gnomAD_FIN_AF', 'gnomAD_NFE_AF', 'gnomAD_OTH_AF', 'gnomAD_SAS_AF',
]

MAF_COLUMNS = [
    'NCBI_Build',    # needed by oncokb-annotator
    'Hugo_Symbol', 'Chromosome', 'Start_Position', 'End_Position',
    'Reference_Allele', 'Allele', 'Tumor_Seq_Allele2',
    'Variant_Classification', 'Tumor_Sample_Barcode',
    'Matched_Norm_Sample_Barcode', 'FILTER', 't_depth', 't_alt_count',
    'gnomAD_AF', 'BIOTYPE', 'HGVSp_Short', 'HGVSc',
    'n_depth', 'n_alt_count',
] + GNOMAD_POP_COLUMNS

# frequency field, by version
GNOMAD_KEYS = ['GND_FREQ', 'GNOMAD_FREQ', 'gnomAD_AF']

def opener(path):
    return gzip.open(path, 'rt') if path.endswith('.gz') else open(path)


def parse_impact_header(header_lines):
    """Order of the INFO/IMPACT subfields, from the PAVE header."""
    for line in header_lines:
        if not line.startswith('##INFO=<ID=IMPACT'):
            continue
        m = re.search(r'Description="([^"]*)"', line)
        if not m:
            break
        # subfields separated by '|' or by ', '
        desc = m.group(1)
        parts = re.split(r'\s*\|\s*', desc) if '|' in desc else None
        if not parts:
            m2 = re.search(r'\[([^\]]*)\]', desc)
            parts = re.split(r'\s*,\s*', m2.group(1)) if m2 else None
        if parts:
            return [p.strip().strip("'\"").lower() for p in parts if p.strip()]
    return None


def field(impact, layout, *names):
    """First IMPACT subfield whose name contains one of the names."""
    for name in names:
        for i, key in enumerate(layout):
            if name in key and i < len(impact):
                return impact[i]
    return ''


def to_maf_coords(pos, ref, alt):
    """VCF to MAF coordinates."""
    pos = int(pos)
    if len(ref) == len(alt):                      # SNV or MNV
        return pos, pos + len(ref) - 1, ref, alt
    if len(ref) > len(alt) and ref.startswith(alt):   # deletion
        return pos + len(alt), pos + len(ref) - 1, ref[len(alt):], '-'
    if len(alt) > len(ref) and alt.startswith(ref):   # insertion
        return pos + len(ref) - 1, pos + len(ref), '-', alt[len(ref):]
    return pos, pos + len(ref) - 1, ref, alt      # complex: as is


def pick_effect(effects_raw):
    """Most severe of the effects PAVE joins with '&'."""
    effects = [e.strip() for e in re.split(r'[&,]', effects_raw) if e.strip()]
    for candidate in EFFECT_RANK:
        if candidate in effects:
            return candidate
    return effects[0] if effects else ''


def classify(effect, ref, alt):
    cls = EFFECT_TO_CLASS.get(effect)
    if cls == 'Frame_Shift_Del' and len(alt) > len(ref):
        cls = 'Frame_Shift_Ins'
    return cls


def read_column_header(line, header_lines, vcf_path, tumor_id, normal_id):
    """Sample columns, IMPACT layout and frequency field, at the #CHROM line."""
    samples = line.split('\t')[9:]
    layout = parse_impact_header(header_lines)
    if not layout:
        sys.exit(f'ERROR: no PAVE INFO/IMPACT header in {vcf_path}')
    gnomad_key = None
    for key in GNOMAD_KEYS:
        if any(h.startswith('##INFO=<ID=' + key + ',') for h in header_lines):
            gnomad_key = key
            break
    if tumor_id not in samples:
        sys.exit(f'ERROR: tumor {tumor_id} not in the VCF samples {samples}')
    if normal_id not in samples:
        sys.exit(f'ERROR: normal {normal_id} not in the VCF samples {samples}')
    return samples, layout, gnomad_key


def sample_values(f, samples, sample_id):
    """FORMAT values of one sample in a VCF record."""
    fmt = f[8].split(':') if len(f) > 8 else []
    col = f[9 + samples.index(sample_id)] if len(f) > 9 else ''
    return dict(zip(fmt, col.split(':')))


def depth_and_alt(vals, alt_default):
    """Depth and alt allele count, from DP and AD."""
    ad = vals.get('AD', '')
    alt = ad.split(',')[1] if ',' in ad else alt_default
    depth = vals.get('DP', '')
    if not depth and ',' in ad:
        depth = str(sum(int(x) for x in ad.split(',') if x.isdigit()))
    return depth, alt


def parse_info(info):
    kv = {}
    for item in info.split(';'):
        if '=' in item:
            k, v = item.split('=', 1)
            kv[k] = v
    return kv


def maf_row(f, samples, layout, gnomad_key, tumor_id, normal_id, build):
    """MAF row, or (None, reason)."""
    chrom, pos, ref, alt, filt, info = f[0], f[1], f[3], f[4], f[6], f[7]
    vals = sample_values(f, samples, tumor_id)
    nvals = sample_values(f, samples, normal_id)

    kv = parse_info(info)
    if 'IMPACT' not in kv:
        return None, None
    impact = kv['IMPACT'].split(',') if ',' in kv['IMPACT'] else kv['IMPACT'].split('|')

    gene = field(impact, layout, 'gene')
    if not gene or gene == '.':
        return None, 'no_gene'
    effect = pick_effect(field(impact, layout, 'effect', 'consequence'))
    var_class = classify(effect, ref, alt)
    if not var_class:
        return None, 'no_class'

    t_depth, t_alt = depth_and_alt(vals, '')
    n_depth, n_alt = depth_and_alt(nvals, '0')

    start, end, maf_ref, maf_alt = to_maf_coords(pos, ref, alt)
    row = {
        'NCBI_Build': build,
        'Hugo_Symbol': gene,
        'Chromosome': chrom,
        'Start_Position': str(start),
        'End_Position': str(end),
        'Reference_Allele': maf_ref,
        'Allele': maf_alt,                # read by Djerba
        'Tumor_Seq_Allele2': maf_alt,     # read by OncoKB
        'Variant_Classification': var_class,
        'Tumor_Sample_Barcode': tumor_id,
        'Matched_Norm_Sample_Barcode': normal_id,
        'FILTER': filt,
        't_depth': t_depth,
        't_alt_count': t_alt,
        'gnomAD_AF': kv.get(gnomad_key, '') if gnomad_key else '',
        'BIOTYPE': 'protein_coding',      # PAVE: coding only
        # 'coding' alone also matches CanonicalCodingEffect
        'HGVSp_Short': field(impact, layout, 'hgvsprotein', 'hgvs_protein'),
        'HGVSc': field(impact, layout, 'hgvscoding', 'hgvs_coding'),
        'n_depth': n_depth or '0',
        'n_alt_count': n_alt or '0',
    }
    for column in GNOMAD_POP_COLUMNS:
        row[column] = ''
    return row, None


def convert(vcf_path, tumor_id, normal_id, out_path, build):
    header_lines = []
    samples = []
    layout = None
    gnomad_key = None
    written = 0
    skipped = {'no_gene': 0, 'no_class': 0}

    with opener(vcf_path) as vcf, open(out_path, 'w') as out:
        print('\t'.join(MAF_COLUMNS), file=out)
        for line in vcf:
            line = line.rstrip('\n')
            if line.startswith('##'):
                header_lines.append(line)
            elif line.startswith('#CHROM'):
                samples, layout, gnomad_key = read_column_header(
                    line, header_lines, vcf_path, tumor_id, normal_id)
            else:
                if layout is None:
                    sys.exit(f'ERROR: no #CHROM header in {vcf_path}')
                row, reason = maf_row(line.split('\t'), samples, layout, gnomad_key,
                                      tumor_id, normal_id, build)
                if row is None:
                    if reason:
                        skipped[reason] += 1
                    continue
                print('\t'.join(row[c] for c in MAF_COLUMNS), file=out)
                written += 1
    if layout is None:
        sys.exit(f'ERROR: no #CHROM header in {vcf_path}')

    return written, skipped['no_gene'], skipped['no_class'], layout, gnomad_key


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--vcf', required=True, help='purple.somatic.vcf.gz')
    parser.add_argument('--tumor', required=True, help='tumor sample id in the VCF')
    parser.add_argument('--normal', required=True, help='normal sample id in the VCF')
    parser.add_argument('--out', required=True, help='output MAF')
    parser.add_argument('--build', default='GRCh38', help='reference genome (Default: GRCh38)')
    args = parser.parse_args()

    n, no_gene, no_class, layout, gnomad_key = convert(
        args.vcf, args.tumor, args.normal, args.out, args.build)
    print(f"IMPACT subfields: {', '.join(layout)}")
    print(f"frequency field: {gnomad_key or 'none, gnomAD_AF left empty'}")
    print(f"rows written: {n}, skipped without gene: {no_gene}, without class: {no_class}")
    print(f"MAF: {args.out}")


if __name__ == '__main__':
    main()
