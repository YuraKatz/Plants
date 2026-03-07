#!/usr/bin/env python3
"""Generates Plants site HTML from YAML data + Jinja2 templates."""

import sys
import json
import argparse
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent

LANGUAGES = ['ru', 'en', 'he']

LIGHTING_THRESHOLDS = [
    {
        'key': 'low',
        'name': 'Low Light - Теневыносливые',
        'max_optimal': 6000,
        'optimal_range': '4000-6000 lux',
        'min_range': '1000-3000 lux',
        'photoperiod': '10-12 ч',
    },
    {
        'key': 'medium',
        'name': 'Medium Light - Средний свет',
        'max_optimal': 8000,
        'optimal_range': '8000 lux',
        'min_range': '3000 lux',
        'photoperiod': '10-12 ч',
    },
    {
        'key': 'bright',
        'name': 'Bright Light - Яркий свет',
        'max_optimal': 999999,
        'optimal_range': '9000-30000 lux',
        'min_range': '4000-10000 lux',
        'photoperiod': '10-14 ч',
    },
]

MIX_SUBTITLES = {
    'mix_1': 'Для ароидных растений с ручным поливом',
    'mix_2': 'Для ароидных растений на фитиле',
    'mix_3': 'Для марантовых растений с ручным поливом',
    'mix_4': 'Для марантовых растений на фитиле',
    'mix_5': 'Для драцен и кротона',
    'mix_5f': 'Для драцен и кротона на фитиле',
    'mix_6': 'Для пальм с ручным поливом',
    'mix_7': 'Для бромелиевых растений',
    'mix_8': 'Для бегоний и фиалок',
    'mix_9': 'Субстрат для эпифитных орхидей',
    'mix_10': 'Влагоёмкая смесь для папоротников',
    'mix_11': 'Быстросохнущая смесь с отличным дренажом',
    'mix_12': 'Очень воздушный, крупнофракционный субстрат',
    'mix_carnivorous': 'БЕЗ УДОБРЕНИЙ! Только чистый субстрат',
}


def load_yaml(filename):
    path = ROOT / filename
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
            loader=FileSystemLoader(ROOT / 'templates'),
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

        fert_raw = load_yaml('fertilizers.yaml')
        self.fertilizers = fert_raw.get('fertilizers', {})
        self.feeding_matrix = fert_raw.get('feeding_matrix', {})
        self.fert_settings = fert_raw.get('settings', {})

        self._load_i18n()
        self._index_plants_by_mix()
        return self

    def _load_i18n(self):
        i18n_dir = ROOT / 'i18n'
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
            by_mix.setdefault(mix_num, []).append(self._plant_entry(pid, p))
        self._plants_by_mix = by_mix

    def _plant_entry(self, pid, p):
        img = self.images.get(pid, '')
        if img and self._current_lang != 'ru':
            img = '../' + img
        return {
            'id': pid,
            'name': p.get('name', pid),
            'latin_name': p.get('latin_name', ''),
            'image': img,
        }

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
            # Re-index plants with correct image paths for this language
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
                self._build_lighting_groups()
                self._build_plants_catalog()
                self._build_feeding_guide()
                self._build_water_mixer()
                self._build_my_products()
                self._build_plant_problems()
                self._build_seasonal_care()
                self._build_propagation()
                self._build_watering_tracker()
                self._build_pests_diseases()

    def _build_soil_groups(self):
        ordered = []
        for key, mix in self.soil_mixes.items():
            entry = dict(mix)
            entry['_key'] = key
            entry['subtitle'] = MIX_SUBTITLES.get(key, '')
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

        groups = []
        for gkey, letter in [('group_a', 'A'), ('group_b', 'B'), ('group_c', 'C')]:
            gdef = group_defs.get(gkey, {})
            plants = []
            for pid, preq in individual.items():
                if preq.get('group') == letter:
                    plants.append(self._plant_entry(pid, self._current_plants.get(pid, {})))
            groups.append({
                'key': gkey,
                'letter': letter,
                'name': gdef.get('name', ''),
                'ppm_range': gdef.get('ppm_range', ''),
                'ppm_target': gdef.get('ppm_target', ''),
                'ph_range': gdef.get('ph_range', ''),
                'plants': plants,
            })

        dionaea = self._current_plants.get('dionaea')
        if dionaea:
            groups.append({
                'key': 'special',
                'letter': 'special',
                'name': self._current_t.get('water_pure_ro', 'ТОЛЬКО чистый RO'),
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
        groups = [dict(g, plants=[]) for g in LIGHTING_THRESHOLDS]

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

    def _build_plants_catalog(self):
        individual = self.water_req.get('individual_requirements', {})
        canister_map = {}
        for pid, preq in individual.items():
            canister_map[pid] = preq.get('group', '')

        ctx = self._base_ctx('plants-catalog.html')
        ctx['plants_json'] = json.dumps({
            'settings': self.fert_settings,
            'feeding_matrix': self.feeding_matrix,
            'plants': self._current_plants,
        }, ensure_ascii=False, indent=2)
        ctx['images_json'] = json.dumps(self._images_for_lang(), ensure_ascii=False, indent=2)
        ctx['canister_json'] = json.dumps(canister_map, ensure_ascii=False, indent=2)
        html = self.env.get_template('pages/plants-catalog.html').render(**ctx)
        self._write('plants-catalog.html', html)

    def _build_feeding_guide(self):
        plants_feeding = {}
        for pid, p in self._current_plants.items():
            plants_feeding[pid] = {
                'name': p.get('name', pid),
                'latin': p.get('latin_name', ''),
                'group': p.get('feeding_group', ''),
                'wick': p.get('wick_watering', {}).get('recommended', False),
            }

        ctx = self._base_ctx('feeding-guide.html')
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
        html = self.env.get_template('pages/water-mixer.html').render(**ctx)
        self._write('water-mixer.html', html)

    def _build_my_products(self):
        ctx = self._base_ctx('my-products.html')
        html = self.env.get_template('pages/my-products.html').render(**ctx)
        self._write('my-products.html', html)

    def _build_plant_problems(self):
        ctx = self._base_ctx('plant-problems.html')
        ctx['images'] = self._images_for_lang()
        html = self.env.get_template('pages/plant-problems.html').render(**ctx)
        self._write('plant-problems.html', html)

    def _build_seasonal_care(self):
        ctx = self._base_ctx('seasonal-care.html')
        html = self.env.get_template('pages/seasonal-care.html').render(**ctx)
        self._write('seasonal-care.html', html)

    def _build_propagation(self):
        ctx = self._base_ctx('propagation.html')
        html = self.env.get_template('pages/propagation.html').render(**ctx)
        self._write('propagation.html', html)

    def _build_watering_tracker(self):
        ctx = self._base_ctx('watering-tracker.html')
        html = self.env.get_template('pages/watering-tracker.html').render(**ctx)
        self._write('watering-tracker.html', html)

    def _build_pests_diseases(self):
        ctx = self._base_ctx('pests-diseases.html')
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
            path = ROOT / name
        else:
            path = ROOT / self._current_lang / name
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
    print('Done.')


if __name__ == '__main__':
    main()
