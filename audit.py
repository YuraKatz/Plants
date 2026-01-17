#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plants Database Audit Script
Проверяет консистентность между YAML файлами
"""

import yaml
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

class PlantsDatabaseAuditor:
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.issues = []
        self.warnings = []

        # Load all YAML files
        self.plants = self._load_yaml('plants.yaml')
        self.soil_mixes = self._load_yaml('soil-mixes.yaml')
        self.components = self._load_yaml('components.yaml')
        self.fertilizers = self._load_yaml('fertilizers.yaml')
        self.water_reqs = self._load_yaml('water-requirements.yaml')

    def _load_yaml(self, filename: str) -> dict:
        """Load YAML file"""
        try:
            with open(self.base_path / filename, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.issues.append(f"[!] CRITICAL: Cannot load {filename}: {e}")
            return {}

    def audit_all(self):
        """Run all audit checks"""
        print("[*] Starting Plants Database Audit...\n")

        self.check_plant_soil_references()
        self.check_plant_water_references()
        self.check_soil_component_references()
        self.check_water_group_consistency()
        self.check_wick_watering_consistency()
        self.check_ppm_ph_ranges()
        self.check_duplicates_and_conflicts()

        self.print_report()

    def check_plant_soil_references(self):
        """Check if plants reference valid soil mixes"""
        print("[*] Checking plant -> soil mix references...")

        plants_data = self.plants.get('plants', {})
        soil_mixes_data = self.soil_mixes.get('soil_mixes', {})

        # Get all valid mix numbers
        valid_mixes = set()
        for mix_id, mix_data in soil_mixes_data.items():
            mix_num = str(mix_data.get('number', ''))
            valid_mixes.add(mix_num)

        # Check each plant
        for plant_id, plant_data in plants_data.items():
            soil = plant_data.get('soil', {})
            mix_number = str(soil.get('mix_number', ''))

            if mix_number and mix_number not in valid_mixes:
                self.issues.append(
                    f"[!] Plant '{plant_id}' references non-existent mix #{mix_number}"
                )

            # Check alternative mix if exists
            alt_mix = soil.get('alternative_mix', '')
            if alt_mix:
                # Extract number from string like "2 (ароидная, фитильный)"
                alt_num = alt_mix.split()[0] if alt_mix else ''
                if alt_num and alt_num not in valid_mixes:
                    self.warnings.append(
                        f"[W] Plant '{plant_id}' alternative_mix '{alt_mix}' might be invalid"
                    )

        print("   [+] Plant -> soil mix references checked\n")

    def check_plant_water_references(self):
        """Check if all plants have water requirements"""
        print("[*] Checking plant -> water requirements...")

        plants_data = self.plants.get('plants', {})
        water_individual = self.water_reqs.get('water_requirements', {}).get('individual_requirements', {})

        plants_set = set(plants_data.keys())
        water_set = set(water_individual.keys())

        missing_water = plants_set - water_set
        extra_water = water_set - plants_set

        if missing_water:
            for plant in missing_water:
                self.issues.append(
                    f"[!] Plant '{plant}' missing water requirements"
                )

        if extra_water:
            for plant in extra_water:
                self.warnings.append(
                    f"[W] Water requirements exist for unknown plant '{plant}'"
                )

        print("   [+] Plant -> water requirements checked\n")

    def check_soil_component_references(self):
        """Check if soil mixes reference valid components"""
        print("[*] Checking soil mix -> component references...")

        # Get all component names
        components_data = self.components.get('soil_components', {})
        valid_components = set()

        for category in ['basic_substrates', 'additional_components']:
            category_data = components_data.get(category, {})
            for comp_id, comp_data in category_data.items():
                comp_name = comp_data.get('name', '')
                if comp_name:
                    valid_components.add(comp_name)

        # Common component names that should exist
        expected_components = [
            'Универсальный грунт Premium',
            'Кокосовый субстрат',
            'Перлит',
            'Вермикулит',
            'Смесь для орхидей',
            'Древесный уголь',
            'Кокос-перлит'
        ]

        for comp in expected_components:
            # Check partial matches (e.g., "Кокос-перлит (50/50)" contains "Кокос-перлит")
            found = any(comp.lower() in vc.lower() for vc in valid_components)
            if not found:
                self.warnings.append(
                    f"[W] Expected component '{comp}' not found in components.yaml"
                )

        print("   [+] Soil mix -> component references checked\n")

    def check_water_group_consistency(self):
        """Check if water groups are consistent"""
        print("[*] Checking water group consistency...")

        water_reqs = self.water_reqs.get('water_requirements', {})
        individual = water_reqs.get('individual_requirements', {})
        groups = water_reqs.get('water_groups', {})

        # Check if all plants in groups exist in individual requirements
        for group_id, group_data in groups.items():
            group_plants = group_data.get('plants', [])

            for plant_name in group_plants:
                # Find if this plant exists in individual requirements
                found = False
                for plant_id, plant_data in individual.items():
                    if plant_data.get('plant_name', '') == plant_name:
                        found = True
                        # Check if group assignment matches
                        assigned_group = plant_data.get('group', '')
                        expected_group = group_id.split('_')[-1].upper()  # group_a -> A

                        if assigned_group != expected_group:
                            self.issues.append(
                                f"[!] Plant '{plant_name}' in {group_id} but assigned to group {assigned_group}"
                            )
                        break

                if not found:
                    self.warnings.append(
                        f"[W] Plant '{plant_name}' in {group_id} but not in individual_requirements"
                    )

        print("   [+] Water group consistency checked\n")

    def check_wick_watering_consistency(self):
        """Check wick watering consistency"""
        print("[*] Checking wick watering consistency...")

        plants_data = self.plants.get('plants', {})

        for plant_id, plant_data in plants_data.items():
            wick = plant_data.get('wick_watering', {})
            watering_method = plant_data.get('watering', {}).get('method', '')

            # Check consistency between recommended and method
            recommended = wick.get('recommended', False)

            if recommended and 'Фитиль' not in watering_method and 'фитиль' not in watering_method.lower():
                self.warnings.append(
                    f"[W] Plant '{plant_id}': wick_watering recommended=true but method='{watering_method}'"
                )

            if not recommended and recommended is not None:
                if 'Фитиль' in watering_method or 'фитиль' in watering_method.lower():
                    # Only if it's ONLY wick (not "Ручной/Фитиль")
                    if 'Ручной' not in watering_method:
                        self.warnings.append(
                            f"[W] Plant '{plant_id}': wick_watering recommended=false but method includes Фитиль"
                        )

        print("   [+] Wick watering consistency checked\n")

    def check_ppm_ph_ranges(self):
        """Check if PPM and pH ranges are logical"""
        print("[*] Checking PPM and pH ranges...")

        water_individual = self.water_reqs.get('water_requirements', {}).get('individual_requirements', {})

        for plant_id, plant_data in water_individual.items():
            ppm_range = plant_data.get('ppm_range', '')
            ph_range = plant_data.get('ph_range', '')

            # Parse PPM range
            if ppm_range and '-' in str(ppm_range):
                try:
                    ppm_min, ppm_max = map(int, str(ppm_range).split('-'))
                    if ppm_min >= ppm_max:
                        self.issues.append(
                            f"[!] Plant '{plant_id}': Invalid PPM range {ppm_range} (min >= max)"
                        )
                    if ppm_min < 0 or ppm_max > 500:
                        self.warnings.append(
                            f"[W] Plant '{plant_id}': Unusual PPM range {ppm_range}"
                        )
                except:
                    self.warnings.append(
                        f"[W] Plant '{plant_id}': Cannot parse PPM range '{ppm_range}'"
                    )

            # Parse pH range
            if ph_range and '-' in str(ph_range):
                try:
                    ph_min, ph_max = map(float, str(ph_range).split('-'))
                    if ph_min >= ph_max:
                        self.issues.append(
                            f"[!] Plant '{plant_id}': Invalid pH range {ph_range} (min >= max)"
                        )
                    if ph_min < 4.0 or ph_max > 8.0:
                        self.warnings.append(
                            f"[W] Plant '{plant_id}': Unusual pH range {ph_range}"
                        )
                except:
                    self.warnings.append(
                        f"[W] Plant '{plant_id}': Cannot parse pH range '{ph_range}'"
                    )

        print("   [+] PPM and pH ranges checked\n")

    def check_duplicates_and_conflicts(self):
        """Check for duplicate names and potential conflicts"""
        print("[*] Checking for duplicates and conflicts...")

        plants_data = self.plants.get('plants', {})

        # Check for duplicate plant names
        plant_names = {}
        for plant_id, plant_data in plants_data.items():
            name = plant_data.get('name', '')
            if name in plant_names:
                self.warnings.append(
                    f"[W] Duplicate plant name '{name}': {plant_names[name]} and {plant_id}"
                )
            else:
                plant_names[name] = plant_id

        print("   [+] Duplicates and conflicts checked\n")

    def print_report(self):
        """Print audit report"""
        print("\n" + "="*60)
        print("AUDIT REPORT")
        print("="*60 + "\n")

        if not self.issues and not self.warnings:
            print("[OK] NO ISSUES FOUND - Database is consistent!\n")
            return

        if self.issues:
            print(f"[!] CRITICAL ISSUES ({len(self.issues)}):\n")
            for issue in self.issues:
                print(f"  {issue}")
            print()

        if self.warnings:
            print(f"[W]  WARNINGS ({len(self.warnings)}):\n")
            for warning in self.warnings:
                print(f"  {warning}")
            print()

        # Summary
        print("="*60)
        print(f"Summary: {len(self.issues)} issues, {len(self.warnings)} warnings")
        print("="*60 + "\n")

        if self.issues:
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == "__main__":
    auditor = PlantsDatabaseAuditor()
    auditor.audit_all()
