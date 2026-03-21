#!/usr/bin/env python3
"""Generates Plants site HTML from YAML data + Jinja2 templates."""

import sys
import json
import shutil
import argparse
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
I18N_DIR = DATA_DIR / 'i18n'
TEMPLATES_DIR = ROOT / 'templates'
SITE_DIR = ROOT / 'site'
STATIC_DIR = ROOT / 'static'

LANGUAGES = ['ru', 'en', 'he']

LIGHTING_THRESHOLDS = [
    {
        'key': 'low',
        'name': 'lighting_low_name',
        'max_optimal': 6000,
        'optimal_range': '4000-6000 lux',
        'min_range': '1000-3000 lux',
        'photoperiod': 'lighting_period_10_12',
    },
    {
        'key': 'medium',
        'name': 'lighting_medium_name',
        'max_optimal': 8000,
        'optimal_range': '8000 lux',
        'min_range': '3000 lux',
        'photoperiod': 'lighting_period_10_12',
    },
    {
        'key': 'bright',
        'name': 'lighting_bright_name',
        'max_optimal': 999999,
        'optimal_range': '9000-30000 lux',
        'min_range': '4000-10000 lux',
        'photoperiod': 'lighting_period_10_14',
    },
]

SCORE_COLORS = {
    1: '#2196F3',
    2: '#26A69A',
    3: '#4CAF50',
    4: '#66BB6A',
    5: '#8BC34A',
    6: '#CDDC39',
    7: '#FFC107',
    8: '#FF9800',
    9: '#FF5722',
    10: '#E91E63',
}


def load_yaml(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def mix_sort_key(number):
    """Sort mix numbers naturally: 1, 2, ..., 5-Ф after 5, unnumbered last."""
    if number is None:
        return (999, '')
    s = str(number)
    digits = ''
    for i, ch in enumerate(s):
        if ch.isdigit():
            digits += ch
        else:
            return (int(digits) if digits else 999, s[i:])
    return (int(digits) if digits else 999, '')


class SiteBuilder:

    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.plants = {}
        self.images = {}
        self.soil_mixes = {}
        self._plants_by_mix = {}
        self.i18n = {}
        self._current_lang = 'ru'
        self._current_t = {}
        self._current_plants = {}

    def load(self):
        self.plants = load_yaml('plants.yaml').get('plants', {})
        self.images = load_yaml('image-map.yaml').get('images', {})

        soil_raw = load_yaml('soil-mixes.yaml')
        self.soil_mixes = soil_raw.get('soil_mixes', {})
        self.soil_principles = soil_raw.get('general_principles', {})

        self.water_req = load_yaml('water-requirements.yaml').get('water_requirements', {})
        facts_problems_raw = load_yaml('facts-problems.yaml')
        self.common_symptoms = facts_problems_raw.get('common_symptoms', {})
        self.facts_problems = facts_problems_raw.get('plants', {})

        fert_raw = load_yaml('fertilizers.yaml')
        self.fertilizers = fert_raw.get('fertilizers', {})
        self.feeding_matrix = fert_raw.get('feeding_matrix', {})
        self.fert_settings = fert_raw.get('settings', {})
        self.ppm_limits = fert_raw.get('ppm_limits', {})
        self.default_feeding = fert_raw.get('default_feeding', {})
        self.stop_conditions = fert_raw.get('stop_conditions', [])

        self.care_data = load_yaml('care-data.yaml')

        self._load_i18n()
        return self

    def _load_i18n(self):
        i18n_dir = I18N_DIR
        if not i18n_dir.exists():
            return
        for lang_file in i18n_dir.glob('*.yaml'):
            lang = lang_file.stem
            with open(lang_file, encoding='utf-8') as f:
                self.i18n[lang] = yaml.safe_load(f) or {}

    def _translate_plants(self):
        """Translate plant data fields for current language."""
        if self._current_lang == 'ru':
            return self.plants
        t = self._current_t
        maps = {
            'name': t.get('plant_names') or {},
            'type': t.get('plant_types') or {},
            'humidity_level': t.get('humidity_levels') or {},
            'watering_freq': t.get('watering_frequencies') or {},
            'watering_method': t.get('watering_methods') or {},
            'care_note': t.get('care_notes') or {},
            'risk': t.get('risks') or {},
        }
        result = {}
        for pid, p in self.plants.items():
            e = dict(p)
            
            # Translate facts and problems if exist
            if pid in self.facts_problems:
                fp = self.facts_problems[pid]
                e['facts'] = [t.get(f, f) for f in fp.get('facts', [])]
                e['problems'] = [t.get(p_text, p_text) for p_text in fp.get('problems', [])]

            name = e.get('name', '')
            if name in maps['name']:
                e['name'] = maps['name'][name]
            ptype = e.get('type', '')
            if ptype in maps['type']:
                e['type'] = maps['type'][ptype]
            hum = dict(e.get('humidity') or {})
            lvl = hum.get('level', '')
            if lvl in maps['humidity_level']:
                hum['level'] = maps['humidity_level'][lvl]
            e['humidity'] = hum
            wat = dict(e.get('watering') or {})
            meth = wat.get('method', '')
            if meth in maps['watering_method']:
                wat['method'] = maps['watering_method'][meth]
            freq = wat.get('frequency', '')
            if freq in maps['watering_freq']:
                wat['frequency'] = maps['watering_freq'][freq]
            e['watering'] = wat
            notes = e.get('care_notes')
            if notes:
                e['care_notes'] = [maps['care_note'].get(n, n) for n in notes]
            risks = e.get('risks')
            if risks:
                e['risks'] = [maps['risk'].get(r, r) for r in risks]
            result[pid] = e
        return result

    def _index_plants_by_mix(self):
        by_mix = {}
        for pid, p in self._current_plants.items():
            mix_num = p.get('soil', {}).get('mix_number')
            if mix_num is None:
                continue
            entry = self._plant_entry(pid, p)
            by_mix.setdefault(mix_num, []).append(entry)
            # Also index by alternative_mix so wick variants show plants too
            alt = p.get('soil', {}).get('alternative_mix', '')
            if alt:
                # Extract mix number from "4 (марантовые, фитильный)" -> 4 or "5-Ф"
                alt_str = str(alt).split('(')[0].strip().split()[0]
                try:
                    alt_key = int(alt_str)
                except ValueError:
                    alt_key = alt_str
                by_mix.setdefault(alt_key, []).append(entry)
        self._plants_by_mix = by_mix

    def _plant_entry(self, pid, p):
        t = self._current_t
        if t is None:
            t = self.i18n.get(self._current_lang, {})
        if t is None:
            t = {}
        
        # Ensure we have nested dicts to avoid attribute errors
        w_methods = t.get('watering_methods') or {}
        w_freqs = t.get('watering_frequencies') or {}
        c_notes = t.get('care_notes') or {}
        h_levels = t.get('humidity_levels') or {}
        p_types = t.get('plant_types') or {}
        risk_map = t.get('risks') or {}

        img = self.images.get(pid, '')
        if img and self._current_lang != 'ru':
            img = '../' + img
            
        # Deep translate plant entry for direct usage in templates/macros
        res = dict(p)
        res['id'] = pid
        res['name'] = t.get(p.get('name', ''), p.get('name', ''))
        res['latin_name'] = p.get('latin_name', '')
        res['type'] = p_types.get(p.get('type', ''), p.get('type', ''))
        
        if 'watering' in res:
            res['watering'] = dict(res['watering'])
            res['watering']['method'] = w_methods.get(p['watering'].get('method', ''), p['watering'].get('method', ''))
            res['watering']['frequency'] = w_freqs.get(p['watering'].get('frequency', ''), p['watering'].get('frequency', ''))
            res['watering']['notes'] = c_notes.get(p['watering'].get('notes', ''), p['watering'].get('notes', ''))
            
        if 'humidity' in res:
            res['humidity'] = dict(res['humidity'])
            res['humidity']['level'] = h_levels.get(p['humidity'].get('level', ''), p['humidity'].get('level', ''))
            
        if 'risks' in res:
            res['risks'] = [risk_map.get(r, r) for r in p.get('risks', [])]
            
        res['image'] = img
        
        # Prepare search keywords from translated fields
        search_parts = [res['name'], res['latin_name'], res['type']]
        if 'watering' in res:
            search_parts.extend([res['watering']['method'], res['watering']['frequency']])
        res['search_keywords'] = ' '.join([s.lower() for s in search_parts if s])
        
        return res

    def _resolve_plants(self, mix):
        """Get plant cards for a mix: by mix_number, then by explicit plant_ids."""
        plants = list(self._plants_by_mix.get(mix.get('number'), []))
        for pid in mix.get('plant_ids', []):
            if pid in self._current_plants and not any(p['id'] == pid for p in plants):
                plants.append(self._plant_entry(pid, self._current_plants[pid]))
        return plants

    def _search_keywords(self, mix, plants):
        parts = [mix.get('name', '').lower()]
        for sf in mix.get('suitable_for', []):
            parts.append(sf.lower())
        for p in plants:
            parts.append(p['name'].lower())
        return ' '.join(parts)

    def _lang_links(self, page_name):
        """Build language switcher links for a page."""
        if self._current_lang == 'ru':
            return {
                'ru': page_name,
                'en': 'en/' + page_name,
                'he': 'he/' + page_name,
            }
        else:
            return {
                'ru': '../' + page_name,
                'en': '../en/' + page_name,
                'he': '../he/' + page_name,
            }

    def _base_ctx(self, page_name):
        """Common template context for all pages."""
        return {
            't': self._current_t,
            't_json': json.dumps(self._current_t, ensure_ascii=False),
            'lang': self._current_lang,
            'dir': 'rtl' if self._current_lang == 'he' else '',
            'lang_links': self._lang_links(page_name),
            'current_page': page_name,
        }

    def _images_for_lang(self):
        """Return images dict with paths adjusted for current language."""
        if self._current_lang == 'ru':
            return dict(self.images)
        adjusted = {}
        for pid, path in self.images.items():
            adjusted[pid] = '../' + path
        return adjusted

    # -- Page builders --

    def build(self, page=None, lang=None):
        languages = [lang] if lang else LANGUAGES
        for current_lang in languages:
            self._current_lang = current_lang
            self._current_t = self.i18n.get(current_lang, self.i18n.get('ru', {}))
            self._current_plants = self._translate_plants()
            
            # Re-index plants AFTER setting current context
            self._index_plants_by_mix()

            if page:
                method = getattr(self, f'_build_{page.replace("-", "_")}', None)
                if not method:
                    print(f'Unknown page: {page}', file=sys.stderr)
                    sys.exit(1)
                method()
            else:
                self._build_index()
                self._build_soil_groups()
                self._build_water_groups()
                self._build_humidity_groups()
                self._build_lighting_score()
                self._build_plants_catalog()
                self._build_feeding_guide()
                self._build_water_mixer()
                self._build_my_products()
                self._build_plant_problems()
                self._build_seasonal_care()
                self._build_propagation()
                # self._build_watering_tracker()  # disabled per user request
                self._build_pests_diseases()

    def _build_soil_groups(self):
        ordered = []
        t = self._current_t
        for key, mix in self.soil_mixes.items():
            entry = dict(mix)
            entry['_key'] = key
            
            # Translate name
            name = entry.get('name', '')
            if 'soil_names' in t and name in t['soil_names']:
                entry['name'] = t['soil_names'][name]
                
            # Translate subtitle
            entry['subtitle'] = t.get('soil_subtitles', {}).get(key, '')
            
            # Translate suitable_for
            sf = entry.get('suitable_for', [])
            if sf and 'plant_types' in t:
                entry['suitable_for'] = [t['plant_types'].get(item, item) for item in sf]

            # Translate composition
            comp = entry.get('composition', [])
            if comp and 'components' in t:
                new_comp = []
                for item in comp:
                    ni = dict(item)
                    cname = ni.get('component', '')
                    if cname in t['components']:
                        ni['component'] = t['components'][cname]
                    new_comp.append(ni)
                entry['composition'] = new_comp

            # Translate variants
            variants = entry.get('variants', {})
            if variants:
                translated_variants = {}
                for vkey, v in variants.items():
                    nv = dict(v)
                    vname = nv.get('name', '')
                    if 'soil_variants' in t and vname in t['soil_variants']:
                        nv['name'] = t['soil_variants'][vname]
                    
                    # Also translate components within variants
                    vcomp = nv.get('composition', [])
                    if vcomp and 'components' in t:
                        new_vcomp = []
                        for item in vcomp:
                            nvi = dict(item)
                            vcname = nvi.get('component', '')
                            if vcname in t['components']:
                                nvi['component'] = t['components'][vcname]
                            new_vcomp.append(nvi)
                        nv['composition'] = new_vcomp
                    translated_variants[vkey] = nv
                entry['variants'] = translated_variants

            # Translate notes
            notes = entry.get('notes', [])
            if notes and 'soil_notes' in t:
                entry['notes'] = [t['soil_notes'].get(n, n) for n in notes]

            entry['plants'] = self._resolve_plants(mix)
            entry['search_keywords'] = self._search_keywords(mix, entry['plants'])
            ordered.append(entry)

        ordered.sort(key=lambda m: mix_sort_key(m.get('number')))
        ctx = self._base_ctx('soil-groups.html')
        ctx['mixes'] = ordered
        html = self.env.get_template('pages/soil-groups.html').render(**ctx)
        self._write('soil-groups.html', html)

    def _build_water_groups(self):
        individual = self.water_req.get('individual_requirements', {})
        group_defs = self.water_req.get('water_groups', {})
        t = self._current_t

        groups = []
        for gkey, letter in [('group_a', 'A'), ('group_b', 'B'), ('group_c', 'C')]:
            gdef = group_defs.get(gkey, {})
            plants = []
            for pid, preq in individual.items():
                if preq.get('group') == letter:
                    plants.append(self._plant_entry(pid, self._current_plants.get(pid, {})))
            
            gname_key = f'water_group_{letter.lower()}'
            gname = t.get(gname_key, f'Group {letter} - {gdef.get("name", "")}')

            target_ppm = gdef.get('target_ppm', '')
            deviation = gdef.get('allowed_deviation', 0)
            ppm_range = f'{target_ppm} ± {deviation}' if target_ppm else ''

            groups.append({
                'key': gkey,
                'letter': letter,
                'name': gname,
                'ppm_range': ppm_range,
                'ppm_target': target_ppm,
                'ph_range': gdef.get('ph_range', ''),
                'plants': plants,
            })

        dionaea = self._current_plants.get('dionaea')
        if dionaea:
            groups.append({
                'key': 'special',
                'letter': 'special',
                'name': t.get('water_group_special', t.get('water_pure_ro', 'ТОЛЬКО чистый RO')),
                'ppm_range': '< 10',
                'ppm_target': 0,
                'ph_range': '',
                'plants': [self._plant_entry('dionaea', dionaea)],
            })

        ctx = self._base_ctx('water-groups.html')
        ctx['groups'] = groups
        html = self.env.get_template('pages/water-groups.html').render(**ctx)
        self._write('water-groups.html', html)

    def _build_lighting_groups(self):
        t = self._current_t
        groups = []
        for g in LIGHTING_THRESHOLDS:
            ng = dict(g)
            ng['name'] = t.get(g['name'], g['name'])
            ng['photoperiod'] = t.get(g['photoperiod'], g['photoperiod'])
            ng['plants'] = []
            groups.append(ng)

        for pid, p in self._current_plants.items():
            lux_opt = p.get('lighting', {}).get('lux_optimal', 0)
            entry = self._plant_entry(pid, p)
            entry['lux_optimal'] = lux_opt
            for g in groups:
                if lux_opt <= g['max_optimal']:
                    g['plants'].append(entry)
                    break

        for g in groups:
            g['plants'].sort(key=lambda x: x['lux_optimal'])

        ctx = self._base_ctx('lighting-groups.html')
        ctx['groups'] = groups
        html = self.env.get_template('pages/lighting-groups.html').render(**ctx)
        self._write('lighting-groups.html', html)

    def _build_humidity_groups(self):
        t = self._current_t
        groups = []
        for score in range(10, 0, -1):
            plants = []
            for pid, p in self._current_plants.items():
                if p.get('humidity_score') == score:
                    entry = self._plant_entry(pid, p)
                    entry['humidity_score'] = score
                    entry['humidity_level'] = entry.get('humidity', {}).get('level', '')
                    entry['lighting_score'] = p.get('lighting_score', 0)
                    entry['lux_optimal'] = p.get('lighting', {}).get('lux_optimal', 0)
                    plants.append(entry)
            if plants:
                plants.sort(key=lambda x: x['name'])
                groups.append({
                    'score': score,
                    'color': SCORE_COLORS.get(score, '#999'),
                    'plants': plants,
                    'plant_count': len(plants),
                })

        ctx = self._base_ctx('humidity-groups.html')
        ctx['groups'] = groups
        ctx['colors'] = SCORE_COLORS
        html = self.env.get_template('pages/humidity-groups.html').render(**ctx)
        self._write('humidity-groups.html', html)

    def _build_lighting_score(self):
        t = self._current_t
        groups = []
        for score in range(10, 0, -1):
            plants = []
            for pid, p in self._current_plants.items():
                if p.get('lighting_score') == score:
                    entry = self._plant_entry(pid, p)
                    entry['lighting_score'] = score
                    entry['lux_optimal'] = p.get('lighting', {}).get('lux_optimal', 0)
                    entry['humidity_score'] = p.get('humidity_score', 0)
                    entry['humidity_level'] = entry.get('humidity', {}).get('level', '')
                    plants.append(entry)
            if plants:
                plants.sort(key=lambda x: x['name'])
                groups.append({
                    'score': score,
                    'color': SCORE_COLORS.get(score, '#999'),
                    'plants': plants,
                    'plant_count': len(plants),
                })

        ctx = self._base_ctx('lighting-score.html')
        ctx['groups'] = groups
        ctx['colors'] = SCORE_COLORS
        html = self.env.get_template('pages/lighting-score.html').render(**ctx)
        self._write('lighting-score.html', html)

    def _build_plants_catalog(self):
        individual = self.water_req.get('individual_requirements', {})
        canister_map = {}
        for pid, preq in individual.items():
            canister_map[pid] = preq.get('group', '')

        # Translate plants for catalog JSON
        catalog_plants = {}
        for pid, p in self._current_plants.items():
            catalog_plants[pid] = self._plant_entry(pid, p)

        ctx = self._base_ctx('plants-catalog.html')
        ctx['plants_json'] = json.dumps({
            'settings': self.fert_settings,
            'feeding_matrix': self.feeding_matrix,
            'plants': catalog_plants,
        }, ensure_ascii=False, indent=2)
        ctx['images_json'] = json.dumps(self._images_for_lang(), ensure_ascii=False, indent=2)
        ctx['canister_json'] = json.dumps(canister_map, ensure_ascii=False, indent=2)
        html = self.env.get_template('pages/plants-catalog.html').render(**ctx)
        self._write('plants-catalog.html', html)

    def _build_feeding_guide(self):
        ctx = self._base_ctx('feeding-guide.html')
        t = self._current_t
        
        # Translate fertilizers data
        translated_fert = {}
        for fkey, f in self.fertilizers.items():
            nf = dict(f)
            nf['name'] = t.get('fert_names', {}).get(f.get('name', ''), f.get('name', ''))
            nf['description'] = t.get('fert_descs', {}).get(f.get('description', ''), f.get('description', ''))
            nf['type'] = t.get(f.get('type', ''), f.get('type', ''))
            translated_fert[fkey] = nf
        
        plants_feeding = {}
        for pid, p in self._current_plants.items():
            plants_feeding[pid] = {
                'name': p.get('name', pid),
                'latin': p.get('latin_name', ''),
                'group': p.get('feeding_group', ''),
                'wick': p.get('wick_watering', {}).get('recommended', False),
            }

        ctx['fertilizers'] = translated_fert
        ctx['plants_json'] = json.dumps({
            'settings': self.fert_settings,
            'feeding_matrix': self.feeding_matrix,
            'plants': plants_feeding,
        }, ensure_ascii=False, indent=2)
        ctx['images_json'] = json.dumps(self._images_for_lang(), ensure_ascii=False, indent=2)
        html = self.env.get_template('pages/feeding-guide.html').render(**ctx)
        self._write('feeding-guide.html', html)

    def _build_water_mixer(self):
        ctx = self._base_ctx('water-mixer.html')
        ctx['images'] = self._images_for_lang()
        ctx['water_groups'] = self.water_req.get('water_groups', {})
        ctx['ppm_limits'] = self.ppm_limits
        ctx['default_feeding'] = self.default_feeding
        ctx['stop_conditions'] = self.stop_conditions
        ctx['calmag_protocol'] = self.water_req.get('calmag_protocol', {})
        html = self.env.get_template('pages/water-mixer.html').render(**ctx)
        self._write('water-mixer.html', html)

    def _build_my_products(self):
        ctx = self._base_ctx('my-products.html')
        t = self._current_t
        
        # Translate fertilizers data
        translated_fert = {}
        for fkey, f in self.fertilizers.items():
            nf = dict(f)
            nf['name'] = t.get('fert_names', {}).get(f.get('name', ''), f.get('name', ''))
            nf['description'] = t.get('fert_descs', {}).get(f.get('description', ''), f.get('description', ''))
            nf['type'] = t.get(f.get('type', ''), f.get('type', ''))
            
            if 'stats' in nf:
                ns = {}
                for sk, sv in nf['stats'].items():
                    ns[t.get(sk, sk)] = t.get(sv, sv)
                nf['stats'] = ns
            
            translated_fert[fkey] = nf
        
        ctx['fertilizers'] = translated_fert
        html = self.env.get_template('pages/my-products.html').render(**ctx)
        self._write('my-products.html', html)

    def _build_pests_diseases(self):
        ctx = self._base_ctx('pests-diseases.html')
        t = self._current_t
        
        pests_raw = load_yaml('pests-diseases.yaml')
        translated_pests = []
        for p in pests_raw.get('pests', []):
            np = dict(p)
            np['name'] = t.get('pest_data', {}).get(p.get('name', ''), p.get('name', ''))
            np['symptoms'] = t.get('pest_data', {}).get(p.get('symptoms', ''), p.get('symptoms', ''))
            np['treatment'] = t.get('pest_data', {}).get(p.get('treatment', ''), p.get('treatment', ''))
            np['prevention'] = t.get('pest_data', {}).get(p.get('prevention', ''), p.get('prevention', ''))
            translated_pests.append(np)
            
        translated_diseases = []
        for d in pests_raw.get('diseases', []):
            nd = dict(d)
            nd['name'] = t.get('pest_data', {}).get(d.get('name', ''), d.get('name', ''))
            nd['symptoms'] = t.get('pest_data', {}).get(d.get('symptoms', ''), d.get('symptoms', ''))
            nd['treatment'] = t.get('pest_data', {}).get(d.get('treatment', ''), d.get('treatment', ''))
            nd['prevention'] = t.get('pest_data', {}).get(d.get('prevention', ''), d.get('prevention', ''))
            translated_diseases.append(nd)
            
        ctx['pests'] = translated_pests
        ctx['diseases'] = translated_diseases
        html = self.env.get_template('pages/pests-diseases.html').render(**ctx)
        self._write('pests-diseases.html', html)

    def _build_plant_problems(self):
        ctx = self._base_ctx('plant-problems.html')

        # Translate plants for selection JSON (needed for searchable names in each lang)
        problem_plants = {}
        for pid, p in self._current_plants.items():
            problem_plants[pid] = self._plant_entry(pid, p)

        # Build diagnostics data from facts-problems.yaml, only for plants in plants.yaml
        diagnostics = {}
        for pid in self._current_plants:
            fp = self.facts_problems.get(pid)
            if not fp:
                continue
            facts = fp.get('facts', [])
            raw_diags = fp.get('diagnostics', [])
            diag_list = []
            for d in raw_diags:
                symptom_key = d.get('symptom', '')
                # Resolve symptom description: use per-diagnostic 'description',
                # else look up in common_symptoms, else use the symptom key
                desc = d.get('description', '')
                if not desc:
                    common = self.common_symptoms.get(symptom_key, {})
                    desc = common.get('description', symptom_key)
                actions = d.get('actions', [])
                severity = d.get('severity', 'medium')
                diag_list.append({
                    'symptom_desc': desc,
                    'actions': actions,
                    'severity': severity,
                })
            diagnostics[pid] = {
                'facts': facts,
                'diagnostics': diag_list,
            }

        ctx['plants_json'] = json.dumps(problem_plants, ensure_ascii=False, indent=2)
        ctx['images_json'] = json.dumps(self._images_for_lang(), ensure_ascii=False, indent=2)
        ctx['diagnostics_json'] = json.dumps(diagnostics, ensure_ascii=False, indent=2)
        html = self.env.get_template('pages/plant-problems.html').render(**ctx)
        self._write('plant-problems.html', html)

    def _build_seasonal_care(self):
        ctx = self._base_ctx('seasonal-care.html')
        t = self._current_t
        
        raw_seasons = self.care_data.get('seasonal_care', {})
        seasons = {}
        for skey, sval in raw_seasons.items():
            seasons[skey] = {
                'months': t.get(sval['months'], sval['months']),
                'cards': []
            }
            for card in sval.get('cards', []):
                seasons[skey]['cards'].append({
                    'icon': card['icon'],
                    'title': t.get(card['title'], card['title']),
                    'desc': t.get(card['desc'], card['desc']),
                    'tips': [t.get(tip, tip) for tip in card.get('tips', [])]
                })
        
        ctx['seasons'] = seasons
        html = self.env.get_template('pages/seasonal-care.html').render(**ctx)
        self._write('seasonal-care.html', html)

    def _build_propagation(self):
        ctx = self._base_ctx('propagation.html')
        t = self._current_t
        
        raw_methods = self.care_data.get('propagation_methods', {})
        methods = {}
        for mkey, mval in raw_methods.items():
            methods[mkey] = {
                'tab': t.get(mval['tab'], mval['tab']),
                'icon': mval['icon'],
                'desc': t.get(mval['desc'], mval['desc']),
                'steps': [t.get(s, s) for s in mval.get('steps', [])],
                'tips': [t.get(tip, tip) for tip in mval.get('tips', [])],
                'plants': []
            }
            for pid in mval.get('plants', []):
                if pid in self._current_plants:
                    methods[mkey]['plants'].append(self._plant_entry(pid, self._current_plants[pid]))
        
        ctx['methods'] = methods
        html = self.env.get_template('pages/propagation.html').render(**ctx)
        self._write('propagation.html', html)

    def _build_watering_tracker(self):
        ctx = self._base_ctx('watering-tracker.html')
        t = self._current_t
        
        # Pass translated units and labels
        ctx['units'] = {
            'ml': t.get('unit_ml', 'мл'),
            'l': t.get('unit_l', 'л'),
        }
        
        # Prepare translated plants for tracker JS
        tracker_plants = {}
        for pid, p in self._current_plants.items():
            tracker_plants[pid] = self._plant_entry(pid, p)
            
        ctx['plants_json'] = json.dumps(tracker_plants, ensure_ascii=False, indent=2)
        ctx['t_json'] = json.dumps(t, ensure_ascii=False, indent=2)
        
        html = self.env.get_template('pages/watering-tracker.html').render(**ctx)
        self._write('watering-tracker.html', html)

    def _build_pests_diseases(self):
        ctx = self._base_ctx('pests-diseases.html')
        t = self._current_t
        pests_data = load_yaml('pests-diseases.yaml')
        
        translated_pests = []
        for p in pests_data.get('pests', []):
            np = dict(p)
            for field in ['name', 'symptoms', 'treatment', 'prevention']:
                val = np.get(field, '')
                if 'pest_data' in t and val in t['pest_data']:
                    np[field] = t['pest_data'][val]
            translated_pests.append(np)
            
        translated_diseases = []
        for d in pests_data.get('diseases', []):
            nd = dict(d)
            for field in ['name', 'symptoms', 'treatment', 'prevention']:
                val = nd.get(field, '')
                if 'pest_data' in t and val in t['pest_data']:
                    nd[field] = t['pest_data'][val]
            translated_diseases.append(nd)
            
        ctx['pests'] = translated_pests
        ctx['diseases'] = translated_diseases
        html = self.env.get_template('pages/pests-diseases.html').render(**ctx)
        self._write('pests-diseases.html', html)

    def _build_index(self):
        ctx = self._base_ctx('index.html')
        ctx['plant_count'] = len(self.plants)
        ctx['soil_mix_count'] = len(self.soil_mixes)
        ctx['water_group_count'] = len(self.water_req.get('water_groups', {})) + 1
        html = self.env.get_template('pages/index.html').render(**ctx)
        self._write('index.html', html)

    def _write(self, name, content):
        if self._current_lang == 'ru':
            path = SITE_DIR / name
        else:
            path = SITE_DIR / self._current_lang / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        print(f'  [OK] {self._current_lang}/{name}')


def main():
    ap = argparse.ArgumentParser(description='Build Plants site from YAML + Jinja2')
    ap.add_argument('--page', help='Build specific page')
    ap.add_argument('--lang', help='Build specific language (ru, en, he)')
    args = ap.parse_args()

    print('Building Plants site...')
    SiteBuilder().load().build(args.page, args.lang)

    # Copy static assets (IMAGES, icons, manifest.json, service-worker.js)
    if STATIC_DIR.exists():
        for item in STATIC_DIR.iterdir():
            dest = SITE_DIR / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            print(f'  [OK] static/{item.name}')

    # Copy llms.txt for AI context sharing
    llms_src = ROOT / 'docs' / 'llms.txt'
    if llms_src.exists():
        shutil.copy2(llms_src, SITE_DIR / 'llms.txt')
        print('  [OK] llms.txt')

    # Generate machine-readable JSON for AI agents
    builder = SiteBuilder().load()
    _generate_api_json(builder)

    print('Done.')


def _generate_api_json(b):
    """Generate JSON endpoints for AI agent consumption."""
    api_dir = SITE_DIR / 'api'
    api_dir.mkdir(exist_ok=True)

    def write_json(name, data):
        (api_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        print(f'  [OK] api/{name}')

    # --- index.json: directory of available endpoints ---
    write_json('index.json', {
        '_description': 'Machine-readable API for Plants Care Database. All data from YAML sources.',
        '_base_url': 'https://yurakatz.github.io/Plants/api/',
        'endpoints': {
            'catalog.json': 'All 26 plants with full care data',
            'soil-mixes.json': '14 soil mix recipes with components',
            'water-groups.json': 'Water chemistry groups A/B/C with plant assignments',
            'feeding.json': 'Feeding matrix, fertilizer products, doses',
            'diagnostics.json': 'Per-plant symptom → cause → action',
        }
    })

    # --- catalog.json: all plants with care data ---
    catalog = {}
    for pid, p in b.plants.items():
        entry = dict(p)
        entry['id'] = pid
        # Add water group details
        wg = p.get('water_group', '')
        group_defs = b.water_req.get('water_groups', {})
        if wg in group_defs:
            gdef = group_defs[wg]
            entry['water_details'] = {
                'group': wg,
                'target_ppm': gdef.get('target_ppm'),
                'deviation': gdef.get('allowed_deviation'),
                'ph_range': gdef.get('ph_range'),
            }
        # Add individual water sensitivity
        ind = b.water_req.get('individual_requirements', {}).get(pid, {})
        if ind:
            entry['water_sensitivity'] = ind.get('sensitivity', '')
            entry['water_notes'] = ind.get('notes', '')
        # Add diagnostics
        diag = b.facts_problems.get(pid, {})
        if diag:
            entry['diagnostics'] = diag.get('diagnostics', [])
            entry['fun_facts'] = diag.get('facts', [])
        catalog[pid] = entry

    write_json('catalog.json', {
        '_description': 'Complete plant care catalog. Primary source of truth.',
        'plant_count': len(catalog),
        'plants': catalog,
    })

    # --- soil-mixes.json ---
    mixes = {}
    for key, mix in b.soil_mixes.items():
        mixes[key] = dict(mix)
    write_json('soil-mixes.json', {
        '_description': '14 soil mix recipes with component percentages and variants.',
        'mix_count': len(mixes),
        'mixes': mixes,
    })

    # --- water-groups.json ---
    groups = {}
    group_defs = b.water_req.get('water_groups', {})
    individual = b.water_req.get('individual_requirements', {})
    for gkey in ['group_a', 'group_b', 'group_c']:
        gdef = group_defs.get(gkey, {})
        letter = gkey[-1].upper()
        plants_in_group = [
            {'id': pid, 'name': pr.get('plant_name', pid), 'sensitivity': pr.get('sensitivity', '')}
            for pid, pr in individual.items() if pr.get('group') == letter
        ]
        groups[gkey] = {
            'letter': letter,
            'name': gdef.get('name', ''),
            'target_ppm': gdef.get('target_ppm'),
            'allowed_deviation': gdef.get('allowed_deviation'),
            'ph_range': gdef.get('ph_range', ''),
            'plants': plants_in_group,
        }
    write_json('water-groups.json', {
        '_description': 'Water chemistry groups with PPM/pH targets and plant assignments.',
        'groups': groups,
        'protocol': b.water_req.get('calmag_protocol', {}),
    })

    # --- feeding.json ---
    write_json('feeding.json', {
        '_description': 'Feeding matrix, fertilizer products, and dosing rules.',
        'feeding_matrix': b.feeding_matrix,
        'settings': b.fert_settings,
        'ppm_limits': b.ppm_limits,
        'default_feeding': b.default_feeding,
        'stop_conditions': b.stop_conditions,
    })

    # --- diagnostics.json ---
    diag_data = {}
    for pid, data in b.facts_problems.items():
        if pid in b.plants:
            diag_data[pid] = {
                'plant_name': b.plants[pid].get('name', pid),
                'facts': data.get('facts', []),
                'diagnostics': data.get('diagnostics', []),
            }
    write_json('diagnostics.json', {
        '_description': 'Per-plant diagnostics: symptom → cause → action. Plus fun facts.',
        'common_symptoms': b.common_symptoms,
        'plants': diag_data,
    })


if __name__ == '__main__':
    main()
