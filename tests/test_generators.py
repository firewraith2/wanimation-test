#!/usr/bin/env python3
"""
Test script for Wanimation Studio generators.

Tests the round-trip conversions (each tests multiple sprite modes):
- External Files Based: frames -> external files -> frames
- WAN Files Based: frames -> WAN -> frames

Sprite Modes Tested:
  - 4bpp: Standard 4-bit per pixel sprites
  - 4bpp+tiles: 4bpp with tiles mode enabled
  - 4bpp+base: 4bpp with base palette
  - 4bpp+tiles+base: 4bpp with tiles and base palette
  - 8bpp: 8-bit per pixel sprites (256 colors)
  - 8bpp+tiles: 8bpp with tiles mode enabled
  - 8bpp+base: 8bpp with base palette
  - 8bpp+tiles+base: 8bpp with tiles and base palette
  - 4bpp_base: Base sprite generation category
  - 4bpp_base+tiles: Base sprite category with tiles
  - 8bpp_base: Base sprite generation category

Usage:
    # Run all tests using default folder (tests/demo-frames)
    python tests/test_generators.py

    # Run tests using a custom folder
    python tests/test_generators.py tests/demo-frames

    # Run only external files based test (all modes)
    python tests/test_generators.py --test-files

    # Run only WAN files based test (all modes)
    python tests/test_generators.py --test-wan

    # Run only specific sprite modes
    python tests/test_generators.py --4bpp --8bpp-base --4bpp-base-sprite

    # Combine options (test only 4bpp mode for WAN files)
    python tests/test_generators.py --test-wan --4bpp

    # Keep output folders for manual inspection (skip cleanup)
    python tests/test_generators.py --keep-output

Test Data:
    The test uses demo frames from tests/demo-frames/ directory (default).
    Each subfolder represents a separate test case with PNG images and config.json.

Exit Codes:
    0 - All tests passed
    1 - One or more tests failed
"""

import sys
import time
import shutil
import argparse
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from generators import (
    sg_process_multiple_folder,
    sg_process_single_folder,
    fg_process_multiple_folder,
    fg_process_single_folder,
)
from data import read_file_to_bytes, read_json_file
from tests.utils import (
    SECTION_SEPARATOR,
    print_step_header,
    safe_remove_folder,
    get_subfolders,
)


def compare_images(img1_path: Path, img2_path: Path):
    try:
        with Image.open(img1_path) as img1, Image.open(img2_path) as img2:
            if img1.size != img2.size:
                return False

            if img1.mode != "P":
                img1 = img1.convert("P")
            if img2.mode != "P":
                img2 = img2.convert("P")

            arr1 = np.array(img1, dtype=np.uint8)
            arr2 = np.array(img2, dtype=np.uint8)
            if not np.array_equal(arr1, arr2):
                return False

            p1 = img1.getpalette()
            p2 = img2.getpalette()
            if p1 and p2:
                # Fail if generated palette is shorter than original
                if len(p2) < len(p1):
                    return False
                # Compare only up to validity of original palette (ignore padding)
                return p1 == p2[: len(p1)]
            return p1 == p2
    except Exception as e:
        print(f"    [ERROR] Failed to compare {img1_path} and {img2_path}: {e}")
        return False


def find_all_files(folder: Path, exclude_dirs=None):
    exclude_dirs = exclude_dirs or set()
    files = {}
    folder_path = folder

    if not folder_path.exists():
        return files

    for file_path in folder_path.rglob("*"):
        if file_path.is_file():
            # Check if file is inside any excluded directory
            relative_path = file_path.relative_to(folder_path)
            path_parts = relative_path.parts
            if any(excluded_dir in path_parts for excluded_dir in exclude_dirs):
                continue
            files[relative_path.as_posix()] = file_path

    return files


def compare_json_files(json1_path: Path, json2_path: Path):
    try:
        data1 = read_json_file(json1_path)
        data2 = read_json_file(json2_path)

        if data1 is None or data2 is None:
            return False

        if isinstance(data1, dict) and isinstance(data2, dict):
            data1_normalized = {k: v for k, v in data1.items() if k != "frames_folder"}
            data2_normalized = {k: v for k, v in data2.items() if k != "frames_folder"}
            return data1_normalized == data2_normalized

        return data1 == data2
    except Exception as e:
        print(
            f"    [ERROR] Failed to compare JSON files {json1_path} and {json2_path}: {e}"
        )
        return False


def compare_file(original_path: Path, generated_path: Path, relative_path: str):
    ext = relative_path.lower()

    if ext.endswith(".png"):
        matches = compare_images(original_path, generated_path)
    elif ext.endswith(".json"):
        matches = compare_json_files(original_path, generated_path)
    else:
        try:
            matches = read_file_to_bytes(original_path) == read_file_to_bytes(
                generated_path
            )
        except Exception as e:
            return False, f"    [ERROR] Failed to compare {relative_path}: {e}"

    status = "matches" if matches else "does not match"
    return matches, f"    [{'OK' if matches else 'FAIL'}] {relative_path} {status}"


def compare_folders(original_folder: Path, generated_folder: Path, folder_name):
    # Exclude DEBUG folders from comparison
    original_files = find_all_files(original_folder, exclude_dirs={"DEBUG"})
    generated_files = find_all_files(generated_folder, exclude_dirs={"DEBUG"})

    details = []
    all_match = True

    original_keys = set(original_files.keys())
    generated_keys = set(generated_files.keys())

    missing_in_generated = original_keys - generated_keys
    extra_in_generated = generated_keys - original_keys

    if missing_in_generated:
        details.append(
            f"    [ERROR] Missing files in generated: {sorted(missing_in_generated)}"
        )
        all_match = False

    if extra_in_generated:
        details.append(
            f"    [WARNING] Extra files in generated: {sorted(extra_in_generated)}"
        )

    common_files = original_keys & generated_keys
    details.append(f"    [INFO] Comparing {len(common_files)} Files")

    for relative_path in sorted(common_files):
        matches, message = compare_file(
            original_files[relative_path], generated_files[relative_path], relative_path
        )
        details.append(message)
        if not matches:
            all_match = False

    return all_match, details


def run_process_with_error_handling(
    process_func, *args, error_message="Process failed", **kwargs
):
    try:
        process_func(*args, **kwargs)
        return True
    except Exception as e:
        print(f"[ERROR] {error_message}: {e}")
        return False


# Test mode configurations: (mode_name, sprite_category, use_tiles_mode, used_base_palette)
# Each standalone category has 4 combinations: tiles_mode x used_base_palette
TEST_MODE_CONFIGS = [
    # 4bpp_standalone combinations
    ("4bpp", "4bpp_standalone", False, False),
    ("4bpp+tiles", "4bpp_standalone", True, False),
    ("4bpp+base", "4bpp_standalone", False, True),
    ("4bpp+tiles+base", "4bpp_standalone", True, True),
    # 8bpp_standalone combinations
    ("8bpp", "8bpp_standalone", False, False),
    ("8bpp+tiles", "8bpp_standalone", True, False),
    ("8bpp+base", "8bpp_standalone", False, True),
    ("8bpp+tiles+base", "8bpp_standalone", True, True),
    # Base sprite modes
    ("4bpp_base", "4bpp_base", False, True),
    ("4bpp_base+tiles", "4bpp_base", True, True),
    ("8bpp_base", "8bpp_base", True, True),
]

# All available test mode names (derived from TEST_MODE_CONFIGS)
ALL_MODES = [m[0] for m in TEST_MODE_CONFIGS]


def mode_uses_base_palette(mode_config):
    """Check if mode uses base palette."""
    return mode_config[3]  # used_base_palette is the 4th element


def is_base_category(mode_config):
    """Check if the mode category is a base sprite category."""
    return mode_config[1].endswith("_base")


def get_base_category(mode_config):
    """Get the corresponding base category for a mode.

    4bpp_standalone -> 4bpp_base
    8bpp_standalone -> 8bpp_base
    """
    sprite_category = mode_config[1]
    if sprite_category == "4bpp_standalone":
        return "4bpp_base"
    elif sprite_category == "8bpp_standalone":
        return "8bpp_base"
    return None


def get_sprite_properties(mode_config):
    """Convert mode config tuple to sprite_properties dict.

    Only properties that are None in the category config can be customized.
    - tiles_mode: customizable for 4bpp/8bpp standalone
    - used_base_palette: customizable for standalone categories
    """
    mode_name, sprite_category, use_tiles_mode, used_base_palette = mode_config
    return {
        "sprite_category": sprite_category,
        "use_tiles_mode": use_tiles_mode,
        "used_base_palette": used_base_palette,
    }


def get_base_sprite_properties(mode_config):
    """Get sprite_properties for generating base sprite.

    Uses the base category (4bpp_base or 8bpp_base) with same tiles mode.
    """
    mode_name, sprite_category, use_tiles_mode, _ = mode_config
    base_category = get_base_category(mode_config)
    return {
        "sprite_category": base_category,
        "use_tiles_mode": use_tiles_mode,
    }


def get_output_dir_name(mode_name: str, export_as_wan: bool) -> str:
    """Get the output directory name for a mode."""
    safe_name = mode_name.replace("+", "_")
    prefix = "isolated_wan" if export_as_wan else "generated_sprites"
    return f"{prefix}_{safe_name}"


def get_sprite_output_name(
    subfolder_name: str, mode_config, export_as_wan: bool
) -> str:
    """Get the expected output name for a sprite (file or folder).

    Returns the base name without extension for WAN files.
    """
    sprite_category = mode_config[1]
    if sprite_category == "8bpp_base":
        # 8bpp_base generates split outputs - return animation_base as primary
        return f"{subfolder_name}_animation_base"
    else:
        return f"{subfolder_name}_sprite"


def cleanup_or_keep(output_dir: Path, mode_name: str, keep_output: bool, step_num: int):
    """Handle cleanup or keep-output logic."""
    if keep_output:
        print_step_header(
            step_num + 1,
            f"Skipping cleanup of {mode_name} folder (--keep-output)",
        )
        print(f"[INFO] Keeping {output_dir} for manual inspection")
    else:
        print_step_header(step_num + 1, f"Cleaning up {mode_name} folder")
        if not safe_remove_folder(output_dir, str(output_dir)):
            print(f"[INFO] {output_dir} does not exist, skipping cleanup")


def generate_base_sprites(
    subfolders: list,
    frames_dir: Path,
    output_dir: Path,
    mode_config,
    export_as_wan: bool,
) -> dict:
    """Generate base sprites for modes that use base palette.

    Returns: dict mapping subfolder_name to base sprite path
    """
    base_sprite_paths = {}
    base_sprite_props = get_base_sprite_properties(mode_config)
    base_category = get_base_category(mode_config)
    ext = ".wan" if export_as_wan else ""

    for subfolder_name in subfolders:
        subfolder_path = frames_dir / subfolder_name
        if not run_process_with_error_handling(
            sg_process_single_folder,
            subfolder_path,
            export_as_wan=export_as_wan,
            sprite_properties=base_sprite_props,
            error_message=f"Base sprite generation failed for {subfolder_name}",
        ):
            continue

        # Move base sprite to output_dir
        # 4bpp_base generates: {name}_sprite[.wan]
        # 8bpp_base generates: {name}_image_base[.wan] + {name}_animation_base[.wan]
        if base_category == "4bpp_base":
            src = subfolder_path / f"{subfolder_name}_sprite{ext}"
            dest = (
                output_dir
                / f"{subfolder_name}_base{ext if export_as_wan else '_sprite'}"
            )
            if src.exists():
                shutil.move(src, dest)
                base_sprite_paths[subfolder_name] = dest
                print(f"[INFO] Generated base sprite: {dest.name}")
        else:  # 8bpp_base
            # Move both image and animation base
            for suffix in ["_image_base", "_animation_base"]:
                src = subfolder_path / f"{subfolder_name}{suffix}{ext}"
                dest = output_dir / f"{subfolder_name}{suffix}{ext}"
                if src.exists():
                    shutil.move(src, dest)
                    if suffix == "_image_base":
                        base_sprite_paths[subfolder_name] = dest
                    print(f"[INFO] Generated base sprite: {dest.name}")

        # Cleanup DEBUG folder
        debug_folder = subfolder_path / "DEBUG"
        safe_remove_folder(debug_folder, f"DEBUG from {subfolder_name}")

    return base_sprite_paths


def move_generated_outputs(
    subfolders: list,
    frames_dir: Path,
    output_dir: Path,
    mode_config,
    export_as_wan: bool,
    results_list: list,
) -> tuple:
    """Move generated sprite outputs to isolated directory.

    Returns: (list of moved subfolder names, all_passed flag)
    """
    moved = []
    all_passed = True
    mode_name = mode_config[0]
    sprite_category = mode_config[1]
    ext = ".wan" if export_as_wan else ""

    for subfolder_name in subfolders:
        # Handle 8bpp_base split outputs
        if sprite_category == "8bpp_base":
            success = True
            for suffix in ["_image_base", "_animation_base"]:
                src = frames_dir / subfolder_name / f"{subfolder_name}{suffix}{ext}"
                dest = output_dir / f"{subfolder_name}{suffix}{ext}"
                if src.exists():
                    shutil.move(src, dest)
                else:
                    success = False

            if success:
                print(
                    f"[INFO] Moved base {'files' if export_as_wan else 'folders'} for {subfolder_name} to {output_dir.name}"
                )
                moved.append(subfolder_name)
            else:
                print(f"    [FAIL] 8bpp base outputs not found for {subfolder_name}")
                all_passed = False
                results_list.append(
                    (
                        f"{subfolder_name} ({mode_name})",
                        False,
                        ["Base outputs not generated"],
                    )
                )
        else:
            # Standard sprite output
            src = frames_dir / subfolder_name / f"{subfolder_name}_sprite{ext}"
            dest = output_dir / f"{subfolder_name}_sprite{ext}"

            if src.exists():
                shutil.move(src, dest)
                print(f"[INFO] Moved {subfolder_name}_sprite{ext} to {output_dir.name}")
                moved.append(subfolder_name)
            else:
                print(f"    [FAIL] Sprite output not found for {subfolder_name}")
                all_passed = False
                results_list.append(
                    (
                        f"{subfolder_name} ({mode_name})",
                        False,
                        ["Sprite output not generated"],
                    )
                )

    return moved, all_passed


def generate_frames_from_outputs(
    moved_items: list,
    output_dir: Path,
    base_paths: dict,
    mode_config,
    export_as_wan: bool,
):
    """Generate frames from sprite outputs.

    Handles 8bpp_base split files, base palette modes, and standard modes.
    """
    sprite_category = mode_config[1]
    uses_base = mode_uses_base_palette(mode_config)
    ext = ".wan" if export_as_wan else ""

    # 8bpp_base: use animation_base as input, image_base as base sprite
    if sprite_category == "8bpp_base":
        for subfolder_name in moved_items:
            input_path = output_dir / f"{subfolder_name}_animation_base{ext}"
            base_path = output_dir / f"{subfolder_name}_image_base{ext}"
            run_process_with_error_handling(
                fg_process_single_folder,
                input_path,
                base_sprite_path=base_path,
                error_message=f"Frame generation failed for {subfolder_name}",
            )
    # Modes that use a separate base sprite
    elif uses_base and not is_base_category(mode_config):
        for subfolder_name in moved_items:
            input_path = output_dir / f"{subfolder_name}_sprite{ext}"
            base_path = base_paths.get(subfolder_name)
            run_process_with_error_handling(
                fg_process_single_folder,
                input_path,
                base_sprite_path=base_path,
                error_message=f"Frame generation failed for {subfolder_name}",
            )
    # Standard modes
    else:
        run_process_with_error_handling(
            fg_process_multiple_folder,
            output_dir,
            error_message=f"Frame generation failed",
        )


def compare_and_record(
    moved_items: list,
    frames_dir: Path,
    output_dir: Path,
    mode_config,
    export_as_wan: bool,
    results_list: list,
) -> bool:
    """Compare generated frames with originals and record results.

    Returns: all_passed flag
    """
    all_passed = True
    mode_name = mode_config[0]
    sprite_category = mode_config[1]
    ext = ".wan" if export_as_wan else ""

    for subfolder_name in sorted(moved_items):
        test_type = "WAN round-trip" if export_as_wan else "External Files"
        print(f"[TEST] Testing {test_type} for {subfolder_name} ({mode_name})...")

        original_folder = frames_dir / subfolder_name

        # Determine generated frames folder location
        if sprite_category == "8bpp_base":
            sprite_name = f"{subfolder_name}_animation_base"
        else:
            sprite_name = f"{subfolder_name}_sprite"

        if export_as_wan:
            # WAN: frames folder is sibling to WAN file
            generated_frames_folder = output_dir / f"{sprite_name}_frames"
        else:
            # External: frames folder is inside sprite folder
            generated_frames_folder = output_dir / sprite_name / f"{sprite_name}_frames"

        if not generated_frames_folder.exists():
            print(
                f"    [ERROR] Generated frames folder not found: {generated_frames_folder}"
            )
            all_passed = False
            results_list.append(
                (
                    f"{subfolder_name} ({mode_name})",
                    False,
                    ["Generated frames folder not found"],
                )
            )
            continue

        success, details = compare_folders(
            original_folder, generated_frames_folder, subfolder_name
        )

        for detail in details:
            print(detail)

        status_msg = "All Files Match!" if success else "Files Do Not Match"
        print(
            f"    [{'SUCCESS' if success else 'FAIL'}] {subfolder_name} ({mode_name}) - {status_msg}"
        )

        if not success:
            all_passed = False

        results_list.append((f"{subfolder_name} ({mode_name})", success, details))

    return all_passed


def run_single_mode_test(
    mode_config,
    frames_dir: Path,
    test_dir: Path,
    export_as_wan: bool,
    keep_output: bool,
    results_list: list,
    timing_dict: dict = None,
) -> bool:
    """Run a single mode test (either WAN or External Files based).

    Args:
        mode_config: Tuple of (mode_name, sprite_category, use_tiles_mode, used_base_palette)
        frames_dir: Path to frames directory
        test_dir: Path to test directory (for output)
        export_as_wan: True for WAN test, False for External Files test
        keep_output: Whether to keep output folders
        results_list: List to append test results to

    Returns: True if all tests passed for this mode
    """
    mode_start_time = time.perf_counter()
    mode_name = mode_config[0]
    uses_base = mode_uses_base_palette(mode_config)
    step_num = 0
    all_passed = True

    # Test type label
    test_type = "WAN" if export_as_wan else "External Files"

    print(SECTION_SEPARATOR)
    print(
        f"Testing {test_type} Round-Trip [{mode_name}]: frames -> {'WAN' if export_as_wan else 'files'} -> frames"
    )
    print(SECTION_SEPARATOR)
    print()

    subfolders = get_subfolders(frames_dir)
    if not subfolders:
        print("[ERROR] No subfolders found in frames directory")
        return False

    # Create output directory
    output_dir = test_dir / get_output_dir_name(mode_name, export_as_wan)
    if output_dir.exists():
        print(f"[INFO] Cleaning up existing {output_dir}...")
        safe_remove_folder(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate base sprites (if needed)
    base_paths = {}
    if uses_base and not is_base_category(mode_config):
        step_num += 1
        print_step_header(step_num, f"Generating base sprites ({mode_name})")
        base_paths = generate_base_sprites(
            subfolders, frames_dir, output_dir, mode_config, export_as_wan
        )
        print()

    # Step 2: Generate main sprites
    step_num += 1
    output_type = "WAN Files" if export_as_wan else "external files"
    print_step_header(step_num, f"Generating {output_type} from frames ({mode_name})")

    if not run_process_with_error_handling(
        sg_process_multiple_folder,
        frames_dir,
        export_as_wan=export_as_wan,
        sprite_properties=get_sprite_properties(mode_config),
        error_message=f"Sprite generation failed ({mode_name})",
    ):
        return False
    print()

    # Step 3: Cleanup DEBUG folders
    step_num += 1
    print_step_header(step_num, "Cleaning up DEBUG folders")
    for subfolder_name in get_subfolders(frames_dir):
        debug_folder = frames_dir / subfolder_name / "DEBUG"
        safe_remove_folder(debug_folder, f"DEBUG folder from {subfolder_name}")
    print()

    # Step 4: Move outputs to isolated folder
    step_num += 1
    print_step_header(step_num, f"Moving outputs to isolated folder ({mode_name})")
    moved, move_passed = move_generated_outputs(
        subfolders, frames_dir, output_dir, mode_config, export_as_wan, results_list
    )
    if not move_passed:
        all_passed = False

    if not moved:
        print(f"[ERROR] No outputs were moved for {mode_name}")
        return False

    print(f"[OK] Moved {len(moved)} output(s) to {output_dir}")
    print()

    # Step 5: Generate frames from outputs
    step_num += 1
    print_step_header(step_num, f"Generating frames from {output_type} ({mode_name})")
    generate_frames_from_outputs(
        moved, output_dir, base_paths, mode_config, export_as_wan
    )
    print()

    # Step 6: Compare with originals
    step_num += 1
    print_step_header(
        step_num, f"Comparing generated frames with originals ({mode_name})"
    )
    compare_passed = compare_and_record(
        moved, frames_dir, output_dir, mode_config, export_as_wan, results_list
    )
    if not compare_passed:
        all_passed = False
    print()

    # Step 7: Cleanup
    cleanup_or_keep(output_dir, mode_name, keep_output, step_num)
    print()

    # Record timing
    mode_duration = time.perf_counter() - mode_start_time
    if timing_dict is not None:
        test_type = "wan" if export_as_wan else "files"
        timing_dict[f"{mode_name} ({test_type})"] = mode_duration

    return all_passed


def run_tests(
    keep_output=False,
    test_files=True,
    test_wan=True,
    modes_to_test=None,
    frames_dir=None,
):
    if modes_to_test is None:
        modes_to_test = ALL_MODES
    test_dir = Path(__file__).parent
    frames_files_dir = frames_dir if frames_dir else test_dir / "demo-frames"

    if not frames_files_dir.exists():
        print(f"[ERROR] Test directory not found: {frames_files_dir}")
        return False

    print(SECTION_SEPARATOR)
    print("Testing Generators...")
    print(SECTION_SEPARATOR)
    print()

    # Start overall timing
    overall_start_time = time.perf_counter()

    # Initialize result tracking
    test_results = []
    wan_test_results = []
    timing_results = {}
    all_files_tests_passed = True
    all_wan_tests_passed = True

    # Filter to only requested modes
    test_modes = [m for m in TEST_MODE_CONFIGS if m[0] in modes_to_test]

    # ===================================================================
    # External Files Based Round-Trip Test: frames -> external files -> frames
    # ===================================================================
    if test_files:
        for mode_config in test_modes:
            passed = run_single_mode_test(
                mode_config,
                frames_files_dir,
                test_dir,
                export_as_wan=False,
                keep_output=keep_output,
                results_list=test_results,
                timing_dict=timing_results,
            )
            if not passed:
                all_files_tests_passed = False

    # ===================================================================
    # WAN Files Based Round-Trip Test: frames -> WAN -> frames
    # ===================================================================
    if test_wan:
        for mode_config in test_modes:
            passed = run_single_mode_test(
                mode_config,
                frames_files_dir,
                test_dir,
                export_as_wan=True,
                keep_output=keep_output,
                results_list=wan_test_results,
                timing_dict=timing_results,
            )
            if not passed:
                all_wan_tests_passed = False

    # Calculate overall duration
    overall_duration = time.perf_counter() - overall_start_time

    # ===================================================================
    # Final Test Summary
    # ===================================================================
    print(SECTION_SEPARATOR)
    print("Test Summary")
    print(SECTION_SEPARATOR)

    all_tests_passed = True
    total_passed = 0
    total_tests = 0

    # External Files Based test results
    if test_files:
        passed_count = sum(1 for _, success, _ in test_results if success)
        total_count = len(test_results)

        print("\nExternal Files Based Round-Trip (frames -> external files -> frames):")
        for subfolder_name, success, _ in test_results:
            status = "PASS" if success else "FAIL"
            print(f"  {status}: {subfolder_name}")

        print(f"\nResults: {passed_count}/{total_count} tests passed")

        if not all_files_tests_passed:
            all_tests_passed = False
        total_passed += passed_count
        total_tests += total_count

    # WAN Files Based test results
    if test_wan:
        wan_passed_count = sum(1 for _, success, _ in wan_test_results if success)
        wan_total_count = len(wan_test_results)

        print("\nWAN Files Based Round-Trip (frames -> WAN -> frames):")
        for subfolder_name, success, _ in wan_test_results:
            status = "PASS" if success else "FAIL"
            print(f"  {status}: {subfolder_name}")

        print(f"\nResults: {wan_passed_count}/{wan_total_count} tests passed")

        if not all_wan_tests_passed:
            all_tests_passed = False
        total_passed += wan_passed_count
        total_tests += wan_total_count

    print()

    print(f"Overall Results: {total_passed}/{total_tests} tests passed")

    # Print timing summary
    if timing_results:
        print("\nTiming Summary:")
        for mode_key, duration in timing_results.items():
            print(f"  {mode_key}: {duration:.2f}s")
        print(f"\nTotal Time: {overall_duration:.2f}s")

    # Fail if no tests were run
    if total_tests == 0:
        print("[FAIL] No tests were run")
        return False

    if all_tests_passed:
        print("[SUCCESS] All tests passed!")
        return True
    else:
        print("[FAIL] Some tests failed")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test script for Wanimation Studio generators. Tests round-trip conversions."
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Keep generated output folders (generated-sprites and isolated_wan_files) for manual inspection. Skips cleanup steps.",
    )
    parser.add_argument(
        "--test-files",
        action="store_true",
        help="Run only the external files based test (frames -> external files -> frames).",
    )
    parser.add_argument(
        "--test-wan",
        action="store_true",
        help="Run only the WAN files based test (frames -> WAN -> frames).",
    )
    # Mode argument mappings: (cli_flag, dest_attr, mode_name, help_text)
    MODE_ARG_MAP = [
        ("--4bpp", "mode_4bpp", "4bpp", "Test 4bpp mode (standard 4-bit sprites)."),
        (
            "--4bpp-tiles",
            "mode_4bpp_tiles",
            "4bpp+tiles",
            "Test 4bpp+tiles mode (4bpp with tiles mode enabled).",
        ),
        (
            "--4bpp-base",
            "mode_4bpp_base",
            "4bpp+base",
            "Test 4bpp+base mode (4bpp with base palette).",
        ),
        (
            "--4bpp-tiles-base",
            "mode_4bpp_tiles_base",
            "4bpp+tiles+base",
            "Test 4bpp+tiles+base mode (4bpp with tiles and base palette).",
        ),
        ("--8bpp", "mode_8bpp", "8bpp", "Test 8bpp mode (256 color sprites)."),
        (
            "--8bpp-tiles",
            "mode_8bpp_tiles",
            "8bpp+tiles",
            "Test 8bpp+tiles mode (8bpp with tiles mode enabled).",
        ),
        (
            "--8bpp-base",
            "mode_8bpp_base",
            "8bpp+base",
            "Test 8bpp+base mode (8bpp with base palette).",
        ),
        (
            "--8bpp-tiles-base",
            "mode_8bpp_tiles_base",
            "8bpp+tiles+base",
            "Test 8bpp+tiles+base mode (8bpp with tiles and base palette).",
        ),
        (
            "--4bpp-base-sprite",
            "mode_4bpp_base_sprite",
            "4bpp_base",
            "Test 4bpp_base mode (Base sprite generation category).",
        ),
        (
            "--4bpp-tiles-base-sprite",
            "mode_4bpp_tiles_base_sprite",
            "4bpp_base+tiles",
            "Test 4bpp_base+tiles mode (Base sprite category with tiles).",
        ),
        (
            "--8bpp-base-sprite",
            "mode_8bpp_base_sprite",
            "8bpp_base",
            "Test 8bpp_base mode (Base sprite generation category).",
        ),
    ]

    # Add mode arguments dynamically
    for flag, dest, _, help_text in MODE_ARG_MAP:
        parser.add_argument(flag, dest=dest, action="store_true", help=help_text)

    parser.add_argument(
        "folder",
        nargs="?",
        help="Optional folder path containing demo frames. If not specified, uses tests/demo-frames",
    )
    args = parser.parse_args()

    # If neither --test-files nor --test-wan is specified, run both
    if not args.test_files and not args.test_wan:
        run_files = True
        run_wan = True
    else:
        run_files = args.test_files
        run_wan = args.test_wan

    # Build modes list from flags (default is all if none specified)
    modes = [mode_name for _, dest, mode_name, _ in MODE_ARG_MAP if getattr(args, dest)]
    if not modes:
        modes = ALL_MODES

    # Determine frames directory
    frames_dir = None
    if args.folder:
        frames_dir = Path(args.folder).resolve()
        if not frames_dir.exists():
            print(f"Directory not found: {frames_dir}")
            sys.exit(1)

    success = run_tests(
        keep_output=args.keep_output,
        test_files=run_files,
        test_wan=run_wan,
        modes_to_test=modes,
        frames_dir=frames_dir,
    )
    sys.exit(0 if success else 1)
