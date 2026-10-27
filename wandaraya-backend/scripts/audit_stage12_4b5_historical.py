"""Offline verification of NASA POWER historical files; no DB or network access."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPORT = Path('data/reports')
PARAMS = {'T2M': (-90, 65, 'C'), 'T2M_MIN': (-90, 65, 'C'),
          'T2M_MAX': (-90, 65, 'C'), 'PRECTOTCORR': (0, 2000, 'mm/day'),
          'RH2M': (0, 100, '%'), 'WS10M': (0, 150, 'm/s'),
          'ALLSKY_SFC_SW_DWN': (0, 50, 'MJ/m^2/day')}
START, END = date(2010, 1, 1), date(2025, 12, 31)
EXPECTED = {(START + timedelta(days=i)).strftime('%Y%m%d') for i in range((END-START).days+1)}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def decode_acquisition_output(path: Path) -> dict:
    text = path.read_text(encoding='utf-8-sig')
    marker = text.index('--execute-acquisition')
    payload, _ = json.JSONDecoder().raw_decode(text[text.index('{', marker):])
    if payload.get('status') != 'ACQUISITION_COMPLETED_NO_DATABASE_PERSISTENCE':
        raise ValueError('recovered output does not show a completed acquisition')
    rows = payload.get('results', [])
    ids = [r.get('sample_id') for r in rows]
    if len(rows) != 25 or len(set(ids)) != 25 or any(r.get('status') != 'VALIDATED' for r in rows):
        raise ValueError('recovered output must contain 25 unique validated samples')
    return payload


def write_report(name: str, value: dict) -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def audit_sample(sample: dict, original_hash: str) -> dict:
    raw = Path(sample['raw_file']).read_bytes()
    current = digest(raw)
    if current != original_hash:
        raise ValueError(f"checksum mismatch: {sample['sample_id']}")
    obj = json.loads(raw, object_pairs_hook=unique_object)
    h, params = obj['header'], obj['properties']['parameter']
    errors = []
    if h.get('api', {}).get('version') != 'v2.10.0' or h.get('time_standard') != 'UTC':
        errors.append('unexpected_provider_version_or_time_standard')
    if h.get('start') != '20100101' or h.get('end') != '20251231':
        errors.append('unexpected_date_range')
    report = {}
    for name, (low, high, units) in PARAMS.items():
        series = params.get(name, {})
        keys = set(series)
        values = [v for v in series.values() if v is not None and v != h.get('fill_value', -999)]
        numeric = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
        invalid = len(values) - len(numeric) + sum(not low <= v <= high for v in numeric)
        missing = len(EXPECTED) - sum(k in EXPECTED and v is not None and v != h.get('fill_value', -999) for k, v in series.items())
        if keys != EXPECTED: errors.append(f'{name}:date_coverage_mismatch')
        if obj.get('parameters', {}).get(name, {}).get('units') != units: errors.append(f'{name}:unexpected_units')
        report[name] = {'expected': len(EXPECTED), 'available': len(values), 'missing': missing,
                        'missing_percent': round(missing*100/len(EXPECTED), 4),
                        'min': min(numeric) if numeric else None, 'max': max(numeric) if numeric else None,
                        'mean': sum(numeric)/len(numeric) if numeric else None, 'invalid': invalid,
                        'distinct_dates': len(keys), 'duplicate_dates': 0, 'unit': units}
    tmin, tmax = params.get('T2M_MIN', {}), params.get('T2M_MAX', {})
    fill = h.get('fill_value', -999)
    inconsistent = sum(a is not None and b is not None and a != fill and b != fill and a > b
                       for day in EXPECTED for a, b in [(tmin.get(day), tmax.get(day))])
    return {'sample_id': sample['sample_id'], 'raw_file': sample['raw_file'], 'original_sha256': original_hash,
            'verification_sha256': current, 'checksum_match': True, 'header': h,
            'returned_coordinates': obj.get('geometry', {}).get('coordinates'),
            'structural_errors': errors, 'temperature_min_exceeds_max': inconsistent, 'parameters': report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--acquisition-output', required=True, type=Path)
    args = parser.parse_args()
    source = args.acquisition_output.read_bytes()
    acquisition = decode_acquisition_output(args.acquisition_output)
    recovered = {row['sample_id']: row['checksum_sha256'] for row in acquisition['results']}
    b1 = json.loads(Path('data/reports/stage12_4b3_historical_manifest.json').read_text(encoding='utf-8'))
    b2 = json.loads(Path('data/reports/stage12_4b4_batch02_manifest.json').read_text(encoding='utf-8'))
    if set(recovered) != {s['sample_id'] for s in b2['samples']}:
        raise ValueError('recovered sample IDs differ from Batch 02 manifest')
    timestamp = datetime.now(timezone.utc).isoformat()
    provenance = []
    quality = []
    for batch, samples in [('batch01', b1['samples']), ('batch02', b2['samples'])]:
        for sample in samples:
            original = sample['checksum_sha256'] if batch == 'batch01' else recovered[sample['sample_id']]
            result = audit_sample(sample, original)
            quality.append(result)
            provenance.append({'batch': batch, 'sample_id': sample['sample_id'], 'raw_file': sample['raw_file'],
                               'original_acquisition_sha256': original, 'current_verification_sha256': result['verification_sha256'],
                               'match': result['checksum_match'], 'verification_time_utc': timestamp,
                               'evidence': 'batch01 recorded manifest' if batch == 'batch01' else 'user-supplied acquisition terminal output',
                               'evidence_sha256': digest(source) if batch == 'batch02' else None})
    if any(x['structural_errors'] for x in quality):
        raise ValueError('structural validation errors; no successful audit reports written')
    summary = {'samples': len(quality), 'batch01_records': 3*len(EXPECTED), 'batch02_records': 25*len(EXPECTED),
               'expected_records': len(quality)*len(EXPECTED), 'checksum_matches': sum(x['checksum_match'] for x in quality),
               'structural_errors': sum(len(x['structural_errors']) for x in quality),
               'parameter_invalid_values': {p: sum(x['parameters'][p]['invalid'] for x in quality) for p in PARAMS},
               'parameter_missing_values': {p: sum(x['parameters'][p]['missing'] for x in quality) for p in PARAMS},
               'temperature_min_exceeds_max': sum(x['temperature_min_exceeds_max'] for x in quality),
               'network_requests': 0, 'postgresql_writes': False, 'qdrant_writes': False}
    evidence = REPORT / 'stage12_4b5_recovered_acquisition_output.txt'
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if evidence.exists() and digest(evidence.read_bytes()) != digest(source):
        raise ValueError('refusing to replace different recovered acquisition evidence')
    if not evidence.exists():
        evidence.write_bytes(source)
    write_report('stage12_4b5_source_provenance.json', {'evidence_file': str(evidence), 'evidence_sha256': digest(source), 'verification_time_utc': timestamp, 'samples': provenance})
    write_report('stage12_4b5_parameter_quality.json', {'samples': quality, 'summary': summary})
    write_report('stage12_4b5_historical_integrity.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
