#!/usr/bin/env python3
"""
Test WAN files with round-trip checksum verification.

This script tests WAN file integrity by:
1. Extracting WAN -> external files folder (batch)
2. Moving extracted folders to isolated location
3. Regenerating WAN from external files (batch)
4. Comparing checksums (original vs regenerated)

Usage:
    # Test all WAN files in tests/demo-wans/
    python tests/test_wan_files.py

    # Test WAN files in a custom folder
    python tests/test_wan_files.py tests/demo-wans

    # Test specific WAN file(s) from default folder
    python tests/test_wan_files.py d51p41a2.wan

Test Data:
    WAN files should be placed in tests/demo-wans/ directory (default).
    The test creates temporary folders that are auto-cleaned after testing.

Exit Codes:
    0 - All tests passed (checksums match)
    1 - One or more tests failed (checksums differ)
"""

import sys
import shutil
import argparse
from pathlib import Path

script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import wan_transform_process_multiple, wan_transform_process_single
from tests.utils import (
    SECTION_SEPARATOR,
    print_step_header,
    safe_remove_folder,
    get_file_checksum,
)


def run_tests(test_data_dir: Path, specific_files: list = None) -> dict:
    """Run WAN round-trip tests with step-wise processing."""
    isolated_dir = script_dir / "isolated_extracted"

    results = {}

    try:
        # Get WAN files to test
        if specific_files:
            wan_files = [
                test_data_dir / f
                for f in specific_files
                if (test_data_dir / f).exists()
            ]
            missing = [f for f in specific_files if not (test_data_dir / f).exists()]
            for f in missing:
                print(f"[WARNING] File not found: {test_data_dir / f}")
                results[f] = False
        else:
            wan_files = sorted(test_data_dir.glob("*.wan"))

        if not wan_files:
            print(f"[ERROR] No WAN files found in {test_data_dir}")
            return results

        print(SECTION_SEPARATOR)
        print(f"Testing {len(wan_files)} WAN file(s)")
        print(SECTION_SEPARATOR)
        print()

        # Cleanup any existing isolated folder
        safe_remove_folder(isolated_dir)

        # ===================================================================
        # STEP 1: Extract WAN files to folders
        # ===================================================================
        print_step_header(1, "Extracting WAN files to folders")

        if specific_files:
            # Extract only specific files
            for wan_file in wan_files:
                wan_transform_process_single(wan_file, generate=False)
        else:
            # Extract all files in directory
            wan_transform_process_multiple(test_data_dir, generate=False)

        print()

        # ===================================================================
        # STEP 2: Move extracted folders to isolated location
        # ===================================================================
        print_step_header(2, "Moving extracted folders to isolated location")

        isolated_dir.mkdir(parents=True, exist_ok=True)

        expected_folders = {f"{wf.stem}_extracted" for wf in wan_files}
        extracted_folders = sorted(
            f for f in test_data_dir.glob("*_extracted") if f.name in expected_folders
        )
        moved_folders = []

        for folder in extracted_folders:
            dest_folder = isolated_dir / folder.name
            shutil.move(folder, dest_folder)
            moved_folders.append(folder.name)
            print(f"[OK] Moved {folder.name}")

        print(f"\n[INFO] Moved {len(moved_folders)} folder(s) to {isolated_dir.name}")
        print()

        # ===================================================================
        # STEP 3: Regenerate WAN files from extracted folders (batch)
        # ===================================================================
        print_step_header(3, "Regenerating WAN files from folders")

        wan_transform_process_multiple(isolated_dir, generate=True)

        print()

        # ===================================================================
        # STEP 4: Compare checksums
        # ===================================================================
        print_step_header(4, "Comparing checksums")

        for wan_file in wan_files:
            wan_name = wan_file.name
            wan_stem = wan_file.stem

            # Regenerated WAN is inside {stem}_extracted/{stem}_extracted.wan
            folder = isolated_dir / f"{wan_stem}_extracted"
            regenerated_wan = folder / f"{folder.name}.wan"

            if not regenerated_wan.exists():
                print(f"[FAIL] {wan_name} - Regenerated WAN not found")
                results[wan_name] = False
                continue

            orig_hash = get_file_checksum(wan_file)
            gen_hash = get_file_checksum(regenerated_wan)

            if orig_hash == gen_hash:
                print(f"[PASS] {wan_name}")
                results[wan_name] = True
            else:
                print(f"[FAIL] {wan_name} - Checksum mismatch")
                results[wan_name] = False

        print()

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        # ===================================================================
        # STEP 5: Cleanup
        # ===================================================================
        print_step_header(5, "Cleaning up isolated folder")
        safe_remove_folder(isolated_dir, str(isolated_dir))
        print()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test WAN files with round-trip checksum verification"
    )
    parser.add_argument(
        "folder_or_files",
        nargs="*",
        help="Folder path or specific WAN files to test. If a directory is given, tests all WAN files in it. If not specified, uses tests/demo-wans",
    )

    args = parser.parse_args()

    # Determine test data directory and files to test
    test_data_dir = script_dir / "demo-wans"  # default
    specific_files = []

    if args.folder_or_files:
        first_arg = Path(args.folder_or_files[0]).resolve()
        if first_arg.is_dir():
            # First arg is a directory - use it as test data dir
            test_data_dir = first_arg
            # Remaining args (if any) are specific files within that dir
            specific_files = args.folder_or_files[1:]
        else:
            # Args are file names to test in default directory
            specific_files = args.folder_or_files

    if not test_data_dir.exists():
        print(f"Directory not found: {test_data_dir}")
        sys.exit(1)

    results = run_tests(test_data_dir, specific_files if specific_files else None)

    # ===================================================================
    # Summary
    # ===================================================================
    print(SECTION_SEPARATOR)
    print("Test Summary")
    print(SECTION_SEPARATOR)

    passed = sum(1 for r in results.values() if r)
    total = len(results)
    print(f"\nResults: {passed}/{total} tests passed")

    if total <= 20:
        for name, result in results.items():
            status = "PASS" if result else "FAIL"
            print(f"  {status}: {name}")
    else:
        failed = [name for name, result in results.items() if not result]
        if failed:
            print("\nFailed files:")
            for name in failed:
                print(f"  FAIL: {name}")

    print()
    sys.exit(0 if passed == total else 1)
