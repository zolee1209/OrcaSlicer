#!/usr/bin/env python3
"""
Fix Ratrig profile linkages to use generic filament profiles and update
compatible_printers after removing V-Cast, V-Core 3, and V-Minion models.
"""

import json
import re
from pathlib import Path

# Base paths
BASE_PATH = Path(__file__).parent / "resources" / "profiles" / "Ratrig"
MACHINE_PATH = BASE_PATH / "machine"
PROCESS_PATH = BASE_PATH / "process"
FILAMENT_PATH = BASE_PATH / "filament"

# Mapping from Ratrig-specific filaments to generic fdm_filament profiles
FILAMENT_MAPPING = {
    "RatRig Generic ABS": "fdm_filament_abs",
    "RatRig Generic ASA": "fdm_filament_asa",
    "RatRig Generic PA": "fdm_filament_pa",
    "RatRig Generic PA-CF": "fdm_filament_pa",
    "RatRig Generic PC": "fdm_filament_pc",
    "RatRig Generic PCTG": "fdm_filament_pet",
    "RatRig Generic PETG": "fdm_filament_pet",
    "RatRig Generic PLA": "fdm_filament_pla",
    "RatRig Generic PLA-CF": "fdm_filament_pla",
    "RatRig Generic PVA": "fdm_filament_pva",
    "RatRig Generic TPU": "fdm_filament_tpu",
}

# Deleted printer nozzle variants to remove from compatible_printers
DELETED_PRINTERS = {
    "RatRig V-Core 3 200 0.4 nozzle",
    "RatRig V-Core 3 300 0.4 nozzle",
    "RatRig V-Core 3 400 0.4 nozzle",
    "RatRig V-Core 3 500 0.4 nozzle",
    "RatRig V-Minion 0.4 nozzle",
    "RatRig V-Cast 0.4 nozzle",
    "RatRig V-Cast 0.6 nozzle",
}

def fix_machine_default_materials(file_path):
    """Convert Ratrig-specific filaments to generic fdm_filament profiles in machine files."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if "default_materials" not in data:
        return False
    
    materials = data["default_materials"]
    if isinstance(materials, str):
        # Split by semicolon, map each, and rejoin
        material_list = [m.strip() for m in materials.split(";")]
        new_list = []
        for material in material_list:
            if material in FILAMENT_MAPPING:
                new_list.append(FILAMENT_MAPPING[material])
            else:
                new_list.append(material)
        
        if new_list != material_list:
            data["default_materials"] = ";".join(new_list)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
    
    return False

def fix_compatible_printers(file_path):
    """Remove deleted printer nozzle variants from compatible_printers list."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if "compatible_printers" not in data:
        return False
    
    printers = data["compatible_printers"]
    if isinstance(printers, list):
        original_count = len(printers)
        printers[:] = [p for p in printers if p not in DELETED_PRINTERS]
        
        if len(printers) < original_count:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
    
    return False

def main():
    print("🔧 Fixing Ratrig profiles...")
    
    # Fix machine profiles
    print("\n📋 Processing machine profiles...")
    machine_files = list(MACHINE_PATH.glob("RatRig V-Core 4*.json"))
    machine_changed = 0
    
    for f in sorted(machine_files):
        if fix_machine_default_materials(f):
            print(f"  ✓ Updated {f.name}")
            machine_changed += 1
    
    print(f"  → {machine_changed} machine profiles updated")
    
    # Fix process profiles
    print("\n🔄 Processing process profiles...")
    process_files = list(PROCESS_PATH.glob("*.json"))
    process_changed = 0
    
    for f in sorted(process_files):
        if fix_compatible_printers(f):
            print(f"  ✓ Updated {f.name}")
            process_changed += 1
    
    print(f"  → {process_changed} process profiles updated")
    
    # Fix filament profiles
    print("\n💧 Processing filament profiles...")
    filament_files = list(FILAMENT_PATH.glob("RatRig*.json"))
    filament_changed = 0
    
    for f in sorted(filament_files):
        if fix_compatible_printers(f):
            print(f"  ✓ Updated {f.name}")
            filament_changed += 1
    
    print(f"  → {filament_changed} filament profiles updated")
    
    print("\n✅ Done!")
    print(f"Total changes: {machine_changed + process_changed + filament_changed}")

if __name__ == "__main__":
    main()
