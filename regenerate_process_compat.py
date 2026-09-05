#!/usr/bin/env python3
"""
Regenerate compatible_printers for Ratrig process profiles based on available
machine nozzle variants and layer height compatibility rules.
"""

import json
import re
from pathlib import Path

BASE_PATH = Path(__file__).parent / "resources" / "profiles" / "Ratrig"
MACHINE_PATH = BASE_PATH / "machine"
PROCESS_PATH = BASE_PATH / "process"

# Scan available machine nozzle variants
def get_available_machines():
    """Get all available machine nozzle variants."""
    machines = set()
    for f in MACHINE_PATH.glob("*.json"):
        with open(f, 'r', encoding='utf-8') as file:
            try:
                data = json.load(file)
                if data.get("type") == "machine" and data.get("instantiation") == "true":
                    machines.add(data.get("name"))
            except:
                pass
    return sorted(machines)

def get_nozzle_from_name(machine_name):
    """Extract nozzle size from machine name (e.g., '0.4' from 'RatRig V-Core 4 300 0.4 nozzle')"""
    match = re.search(r'(\d+\.\d+)\s+nozzle', machine_name)
    if match:
        return float(match.group(1))
    return None

def filter_machines_for_process(machines, process_name, layer_height):
    """Filter machines based on process profile name.
    
    If process name contains machine specification after @RatRig, match that exact spec.
    If process name has only generic @RatRig (no model/nozzle spec), include all V-Core 4
    machines based on layer height limits.
    """
    compatible = []
    
    # Extract the part after @RatRig from process name
    ratrig_part_match = re.search(r'@RatRig\s+(.+)$', process_name)
    if not ratrig_part_match:
        # Generic process for all machines?
        # Check if it's a generic profile
        if "@RatRig" in process_name and not re.search(r'@RatRig\s+[A-Z]', process_name):
            # Generic profile like "0.08mm Extra Fine @RatRig"
            # Include all V-Core 4 machines with valid layer height
            layer_height_val = float(layer_height)
            for machine in machines:
                nozzle_size = get_nozzle_from_name(machine)
                if nozzle_size and layer_height_val <= nozzle_size * 0.75:
                    compatible.append(machine)
        return compatible
    
    ratrig_spec = ratrig_part_match.group(1).strip()
    
    # Check if spec is empty or only whitespace
    if not ratrig_spec:
        # Generic profile, include all compatible machines
        layer_height_val = float(layer_height)
        for machine in machines:
            nozzle_size = get_nozzle_from_name(machine)
            if nozzle_size and layer_height_val <= nozzle_size * 0.75:
                compatible.append(machine)
        return compatible
    
    # Split into tokens for matching
    spec_tokens = ratrig_spec.split()  # e.g., ["V-Core", "4", "HYBRID", "0.4"]
    
    # Find machines that contain all spec tokens
    for machine in machines:
        # Machine names like "RatRig V-Core 4 300 0.4 nozzle"
        machine_upper = machine.upper()
        
        # Check if all spec tokens appear in machine name
        all_match = all(token.upper() in machine_upper for token in spec_tokens)
        
        if all_match:
            compatible.append(machine)
    
    return compatible

def update_process_profile(file_path, machines):
    """Update compatible_printers in a process profile based on profile name and layer height."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Skip if not a process profile
    if data.get("type") != "process" or data.get("instantiation") != "true":
        return False
    
    # Get layer height and profile name
    layer_height = data.get("layer_height")
    profile_name = data.get("name", "")
    if not layer_height:
        return False
    
    # Only process Ratrig profiles
    if "@RatRig" not in profile_name:
        return False
    
    # Filter compatible machines
    compatible = filter_machines_for_process(machines, profile_name, layer_height)
    
    if data.get("compatible_printers") != compatible:
        data["compatible_printers"] = compatible
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    
    return False

def main():
    print("🔄 Regenerating process compatible_printers...")
    
    # Get available machines
    machines = get_available_machines()
    print(f"Found {len(machines)} available machine variants")
    
    # Update process profiles
    print(f"\nProcessing process profiles...")
    process_files = sorted(PROCESS_PATH.glob("*.json"))
    updated = 0
    
    for f in process_files:
        if update_process_profile(f, machines):
            with open(f, 'r') as file:
                data = json.load(file)
                layer_height = data.get("layer_height", "?")
                compat_count = len(data.get("compatible_printers", []))
            print(f"  ✓ {f.name} (layer: {layer_height}mm, {compat_count} printers)")
            updated += 1
    
    print(f"\n✅ Updated {updated} process profiles")

if __name__ == "__main__":
    main()
