#!/usr/bin/env python3
"""
Validator for Plants knowledge base.

Catches systematic data quality issues BEFORE they reach the public site:
1. Cross-reference breaks (rotation/water-req/facts ref a plant_id missing from plants.yaml)
2. i18n gaps (key in ru.yaml missing in en.yaml or he.yaml)
3. Hardcoded counts in docs/llms.txt, README.md, CLAUDE.md that drift from actual YAML
4. Duplicate function definitions in build.py
5. PWA path issues (absolute / paths in manifest/service-worker)
6. Image-map references to missing files in static/IMAGES/

Run before commit:
    python scripts/validate.py

Exit code 0 = clean, 1 = errors found.
Designed to be hook-able into build.py for fail-fast.
"""

import sys
import re
from pathlib import Path
from collections import defaultdict

import yaml

# Force UTF-8 stdout/stderr on Windows so error messages with Cyrillic/Hebrew don't crash the validator
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
I18N_DIR = DATA_DIR / 'i18n'
DOCS_DIR = ROOT / 'docs'
STATIC_DIR = ROOT / 'static'
TEMPLATES_DIR = ROOT / 'templates'
SCRIPTS_DIR = ROOT / 'scripts'


def load_yaml(path):
    if not path.exists():
        return {}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


# Each check returns list of error strings. Empty list = pass.

def check_cross_references():
    errors = []
    plants = load_yaml(DATA_DIR / 'plants.yaml').get('plants', {})
    plant_ids = set(plants.keys())

    # rotation-schedule.yaml -> plants
    rotation = load_yaml(DATA_DIR / 'rotation-schedule.yaml').get('rotation_schedule', {})
    for canister_key, canister in rotation.items():
        if not isinstance(canister, dict):
            continue
        for field in ['plant_ids', 'plant_ids_decorative', 'plant_ids_flowering',
                      'plant_ids_regular', 'plant_ids_succulents']:
            for pid in canister.get(field, []) or []:
                if pid not in plant_ids:
                    errors.append(
                        f'rotation-schedule.yaml: {canister_key}.{field} references missing plant_id: {pid}'
                    )

    # water-requirements.yaml individual_requirements -> plants
    water_req = load_yaml(DATA_DIR / 'water-requirements.yaml').get('water_requirements', {})
    for pid in (water_req.get('individual_requirements', {}) or {}).keys():
        if pid not in plant_ids:
            errors.append(
                f'water-requirements.yaml: individual_requirements references missing plant_id: {pid}'
            )

    # facts-problems.yaml plants -> plants
    fp = load_yaml(DATA_DIR / 'facts-problems.yaml').get('plants', {})
    for pid in fp.keys():
        if pid not in plant_ids:
            errors.append(
                f'facts-problems.yaml: plants section references missing plant_id: {pid}'
            )

    # image-map.yaml -> plants (and to actual files in static/IMAGES/)
    images = load_yaml(DATA_DIR / 'image-map.yaml').get('images', {})
    images_dir = STATIC_DIR / 'IMAGES'
    for pid, img_path in images.items():
        if pid not in plant_ids:
            errors.append(
                f'image-map.yaml: references plant_id not in plants.yaml: {pid}'
            )
        # Check file exists (path is relative to repo root e.g. IMAGES/foo.jpg)
        if img_path:
            file_path = ROOT / img_path
            alt_path = STATIC_DIR / img_path
            if not file_path.exists() and not alt_path.exists():
                errors.append(
                    f'image-map.yaml: {pid} -> file does not exist: {img_path}'
                )

    # plants.yaml soil.mix_number -> soil-mixes.yaml
    soil_mixes = load_yaml(DATA_DIR / 'soil-mixes.yaml').get('soil_mixes', {})
    valid_mix_numbers = set()
    for key, mix in soil_mixes.items():
        if isinstance(mix, dict) and 'number' in mix:
            valid_mix_numbers.add(mix['number'])
            valid_mix_numbers.add(str(mix['number']))
    for pid, p in plants.items():
        mix_num = p.get('soil', {}).get('mix_number')
        if mix_num is not None and mix_num not in valid_mix_numbers and str(mix_num) not in valid_mix_numbers:
            errors.append(
                f'plants.yaml: {pid} references missing soil mix number: {mix_num}'
            )

    return errors


def check_i18n_coverage():
    """
    i18n is best-effort for one user (Yuri showed pages to colleagues occasionally,
    but not a hard requirement). So this check is a WARNING-level signal, not a blocker:
    it returns issues, but main() can downgrade to warnings if --strict is not set.

    Smart filter: en.yaml/he.yaml contain a "rosetta" pattern where keys are Russian
    source strings (from data/*.yaml) and values are translations. Those keys are NOT
    expected to exist in ru.yaml (Russian -> Russian is identity). We detect a key as
    rosetta if it contains Cyrillic or Hebrew characters.
    """
    errors = []
    langs = {}
    for lang in ['ru', 'en', 'he']:
        langs[lang] = load_yaml(I18N_DIR / f'{lang}.yaml')

    if not langs['ru']:
        errors.append('i18n: ru.yaml empty or missing — cannot validate other languages')
        return errors

    def collect_keys(d, prefix=''):
        keys = set()
        if isinstance(d, dict):
            for k, v in d.items():
                full = f'{prefix}.{k}' if prefix else k
                if isinstance(v, dict):
                    keys.update(collect_keys(v, full))
                else:
                    keys.add(full)
        return keys

    # Rosetta keys (containing Cyrillic/Hebrew) belong only to en.yaml/he.yaml — they
    # translate Russian source data, so they don't need a counterpart in ru.yaml.
    rosetta_re = re.compile(r'[Ѐ-ӿ֐-׿]')
    def is_rosetta(key):
        return bool(rosetta_re.search(key))

    ru_keys = collect_keys(langs['ru'])
    for lang in ['en', 'he']:
        lang_keys = collect_keys(langs[lang])
        # Interface keys missing in target language (real bug: target lang shows raw key)
        missing = {k for k in (ru_keys - lang_keys) if not is_rosetta(k)}
        if missing:
            sample = sorted(missing)[:10]
            errors.append(
                f'i18n: {len(missing)} interface keys present in ru.yaml but missing in {lang}.yaml. '
                f'First 10: {sample}'
            )
        # Interface keys present in target but missing in ru (real bug: ru shows raw key)
        extra_interface = {k for k in (lang_keys - ru_keys) if not is_rosetta(k)}
        if extra_interface:
            sample = sorted(extra_interface)[:10]
            errors.append(
                f'i18n: {len(extra_interface)} interface keys in {lang}.yaml without counterpart in ru.yaml. '
                f'First 10: {sample}'
            )

    return errors


def check_hardcoded_counts():
    """
    Files that describe the collection should NOT have hardcoded numbers
    that drift from actual YAML state.
    """
    errors = []
    plants = load_yaml(DATA_DIR / 'plants.yaml').get('plants', {})
    soil_mixes = load_yaml(DATA_DIR / 'soil-mixes.yaml').get('soil_mixes', {})
    fert = load_yaml(DATA_DIR / 'fertilizers.yaml').get('fertilizers', {})
    additives = fert.get('additives', {}) if isinstance(fert.get('additives'), dict) else {}

    actual = {
        'plant': len(plants),
        'mix': len(soil_mixes),
        'product': len(additives),
        'additive': len(additives),
    }

    # Patterns: "26 plants", "14 mixes", "8 products", "33 plants" etc.
    # Look for "<number> <noun>" where noun is plants/mixes/products/additives/растений/смесей/продуктов
    patterns = [
        (r'(\d+)\s+plants?\b', 'plant'),
        (r'(\d+)\s+(?:soil\s+)?mix(?:es|ов)?\b', 'mix'),
        (r'(\d+)\s+products?\b', 'product'),
        (r'(\d+)\s+additives?\b', 'additive'),
        (r'(\d+)\s+растени', 'plant'),
        (r'(\d+)\s+смес', 'mix'),
        (r'(\d+)\s+продукт', 'product'),
    ]

    files_to_check = []
    for p in [DOCS_DIR / 'llms.txt', ROOT / 'README.md', ROOT / 'CLAUDE.md']:
        if p.exists():
            files_to_check.append(p)

    # Strip text inside backticks (`...`) — those are explicit code examples in docs, not claims.
    code_inline_re = re.compile(r'`[^`\n]*`')

    for fpath in files_to_check:
        text = fpath.read_text(encoding='utf-8')
        for line_num, line in enumerate(text.splitlines(), 1):
            scrubbed = code_inline_re.sub('', line)
            for pat, kind in patterns:
                for m in re.finditer(pat, scrubbed, re.IGNORECASE):
                    n = int(m.group(1))
                    actual_n = actual.get(kind, 0)
                    if n != actual_n and actual_n > 0 and 1 < n < 1000:
                        errors.append(
                            f'{fpath.relative_to(ROOT)}:{line_num} hardcoded "{n} {kind}" '
                            f'but actual is {actual_n}'
                        )

    return errors


def check_duplicate_function_defs():
    errors = []
    build_py = SCRIPTS_DIR / 'build.py'
    if not build_py.exists():
        return errors
    text = build_py.read_text(encoding='utf-8')
    pattern = re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE)
    counts = defaultdict(list)
    for m in pattern.finditer(text):
        name = m.group(1)
        line = text[:m.start()].count('\n') + 1
        counts[name].append(line)
    for name, lines in counts.items():
        if len(lines) > 1:
            errors.append(
                f'build.py: function `{name}` defined {len(lines)} times at lines {lines}. '
                f'Second definition wins; first is dead code.'
            )
    return errors


def check_pwa_paths():
    """
    PWA artifacts should not have absolute paths from `/`,
    because GitHub Pages serves under a subpath like /Plants/.
    """
    errors = []

    manifest = STATIC_DIR / 'manifest.json'
    if manifest.exists():
        text = manifest.read_text(encoding='utf-8')
        # start_url, shortcuts[].url should not begin with '/'
        for m in re.finditer(r'"(start_url|url)"\s*:\s*"(/[^"]*)"', text):
            errors.append(
                f'manifest.json: {m.group(1)} = "{m.group(2)}" is absolute. '
                f'Use "./{m.group(2).lstrip("/")}" for subpath safety.'
            )

    sw = STATIC_DIR / 'service-worker.js'
    if sw.exists():
        text = sw.read_text(encoding='utf-8')
        # Look for STATIC_FILES list entries starting with '/'
        for m in re.finditer(r"^\s*'(/[^']*)',?\s*$", text, re.MULTILINE):
            errors.append(
                f'service-worker.js: cached path "{m.group(1)}" is absolute. '
                f'Use relative path for subpath safety.'
            )

    return errors


def check_schema_alignment():
    """
    Spot-check that build.py reads fields that actually exist in YAML.
    Currently checks the most fragile area: water_groups.
    """
    errors = []
    water_req = load_yaml(DATA_DIR / 'water-requirements.yaml').get('water_requirements', {})
    groups = water_req.get('water_groups', {})

    # Required fields per group (used by build.py and api/water-groups.json)
    required_fields = ['name', 'after_calmag_ppm', 'after_fertilizer_ppm', 'ph_target']
    for gkey, gdef in groups.items():
        for field in required_fields:
            if field not in gdef:
                errors.append(
                    f'water-requirements.yaml: {gkey} missing required field "{field}"'
                )

    # build.py should NOT READ deprecated/non-existent fields from water_groups defs.
    # Detect only actual reads (gdef.get('x') / gdef['x']) — output dict keys with same name are fine.
    build_text = (SCRIPTS_DIR / 'build.py').read_text(encoding='utf-8')
    deprecated_field_names = {
        'target_ppm': 'water groups no longer have target_ppm; use after_calmag_ppm/after_fertilizer_ppm',
        'allowed_deviation': 'water groups no longer have allowed_deviation',
        'ph_range': 'water groups field is `ph_target`, not `ph_range`',
    }
    # Match: gdef.get('field') OR gdef['field'] OR group_defs['x'].get('field')
    read_pattern = re.compile(r"\b(?:gdef|group_def\w*)\b\s*(?:\.get\(\s*['\"](\w+)['\"]|\[\s*['\"](\w+)['\"]\s*\])")
    for ln, line in enumerate(build_text.splitlines(), 1):
        for m in read_pattern.finditer(line):
            field = m.group(1) or m.group(2)
            if field in deprecated_field_names:
                errors.append(
                    f'build.py:{ln} reads deprecated water_groups field "{field}" — '
                    f'{deprecated_field_names[field]}'
                )

    return errors


def check_garden_pesticides_loaded():
    """garden-pesticides.yaml should be loaded by build.py if file exists."""
    errors = []
    pest_file = DATA_DIR / 'garden' / 'garden-pesticides.yaml'
    if not pest_file.exists():
        return errors
    build_text = (SCRIPTS_DIR / 'build.py').read_text(encoding='utf-8')
    if 'garden-pesticides.yaml' not in build_text:
        errors.append(
            'build.py: data/garden/garden-pesticides.yaml exists but is not loaded by build.py — '
            'data is invisible to the site and API.'
        )
    return errors


CHECKS = [
    ('Cross-references', check_cross_references),
    ('i18n coverage', check_i18n_coverage),
    ('Hardcoded counts in docs', check_hardcoded_counts),
    ('Duplicate function defs', check_duplicate_function_defs),
    ('PWA paths (subpath safety)', check_pwa_paths),
    ('Schema alignment (build.py vs YAML)', check_schema_alignment),
    ('Garden pesticides loaded', check_garden_pesticides_loaded),
]


def main():
    total_errors = 0
    print('Validating Plants knowledge base...')
    print()
    for name, check in CHECKS:
        errors = check()
        status = 'OK' if not errors else f'{len(errors)} issue(s)'
        print(f'[{status}] {name}')
        for e in errors:
            print(f'    - {e}')
        total_errors += len(errors)
        print()

    if total_errors == 0:
        print('All checks passed.')
        return 0
    else:
        print(f'Found {total_errors} issue(s) total. Fix them before commit/build.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
