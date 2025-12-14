#!/usr/bin/env python3
"""
Test script for Object Studio generators.

Tests the round-trip conversion: frames -> objects -> frames
"""

import os
import sys
import shutil
import json
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from generators import og_process_multiple_folder, fg_process_multiple_folder


EXCLUDED_DIRS = {"object", "frames", "DEBUG"}
STEP_SEPARATOR = "-" * 70
SECTION_SEPARATOR = "=" * 70


def print_step_header(step_num, title):
    print(STEP_SEPARATOR)
    print(f"[STEP {step_num}] {title}...")
    print(STEP_SEPARATOR)
    print()


def safe_remove_folder(folder_path, description=""):
    if not folder_path.exists():
        return False

    try:
        shutil.rmtree(str(folder_path))
        if description:
            print(f"[OK] Removed {description}")
        return True
    except Exception as e:
        if description:
            print(f"[WARNING] Failed to remove {description}: {e}")
        return False


def get_subfolders(base_dir, exclude=None):
    exclude = exclude or set()
    with os.scandir(str(base_dir)) as entries:
        subfolders = [
            entry.name
            for entry in entries
            if entry.is_dir() and entry.name not in exclude
        ]
    return sorted(subfolders)


def compare_images(img1_path, img2_path):
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

            return img1.getpalette() == img2.getpalette()
    except Exception as e:
        print(f"    [ERROR] Failed to compare {img1_path} and {img2_path}: {e}")
        return False


def find_all_files(folder):
    files = {}
    folder_path = Path(folder)

    if not folder_path.exists():
        return files

    for file_path in folder_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(folder_path)
            files[str(relative_path).replace("\\", "/")] = str(file_path)

    return files


def compare_json_files(json1_path, json2_path):
    try:
        with open(json1_path, "r") as f1, open(json2_path, "r") as f2:
            data1 = json.load(f1)
            data2 = json.load(f2)

            if isinstance(data1, dict) and isinstance(data2, dict):
                data1_normalized = {
                    k: v for k, v in data1.items() if k != "frames_folder"
                }
                data2_normalized = {
                    k: v for k, v in data2.items() if k != "frames_folder"
                }
                return data1_normalized == data2_normalized

            return data1 == data2
    except Exception as e:
        print(
            f"    [ERROR] Failed to compare JSON files {json1_path} and {json2_path}: {e}"
        )
        return False


def compare_file(original_path, generated_path, relative_path):
    ext = relative_path.lower()

    if ext.endswith(".png"):
        matches = compare_images(original_path, generated_path)
    elif ext.endswith(".json"):
        matches = compare_json_files(original_path, generated_path)
    else:
        try:
            with open(original_path, "rb") as f1, open(generated_path, "rb") as f2:
                matches = f1.read() == f2.read()
        except Exception as e:
            return False, f"    [ERROR] Failed to compare {relative_path}: {e}"

    status = "matches" if matches else "does not match"
    return matches, f"    [{'OK' if matches else 'FAIL'}] {relative_path} {status}"


def compare_folders(original_folder, generated_folder, folder_name):
    original_files = find_all_files(original_folder)
    generated_files = find_all_files(generated_folder)

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


def run_tests():
    test_dir = Path(__file__).parent
    frames_files_dir = test_dir / "frames-files"

    if not frames_files_dir.exists():
        print(f"[ERROR] Test directory not found: {frames_files_dir}")
        return False

    print(SECTION_SEPARATOR)
    print("Testing Generators...")
    print(SECTION_SEPARATOR)
    print()

    print_step_header(1, "Generating objects from frames")

    if not run_process_with_error_handling(
        og_process_multiple_folder,
        str(frames_files_dir),
        error_message="Object generation failed",
    ):
        return False

    print()

    print_step_header(2, "Cleaning up DEBUG folders")

    subfolders_for_cleanup = get_subfolders(frames_files_dir)

    for subfolder_name in subfolders_for_cleanup:
        debug_folder = frames_files_dir / subfolder_name / "DEBUG"
        safe_remove_folder(debug_folder, f"DEBUG folder from {subfolder_name}")

    print()

    print_step_header(3, "Moving object folders to separate location")

    subfolders = get_subfolders(frames_files_dir, exclude=EXCLUDED_DIRS)
    if not subfolders:
        print("[ERROR] No subfolders found in frames-files")
        return False

    generated_objects_dir = test_dir / "generated-objects"

    if generated_objects_dir.exists():
        print(f"[INFO] Cleaning up existing {generated_objects_dir}...")
        safe_remove_folder(generated_objects_dir)

    generated_objects_dir.mkdir(parents=True, exist_ok=True)

    moved_folders = []
    for subfolder_name in subfolders:
        source_object_folder = frames_files_dir / subfolder_name / "object"
        dest_object_folder = generated_objects_dir / subfolder_name

        if source_object_folder.exists():
            print(
                f"[INFO] Moving {subfolder_name}/object to generated-objects/{subfolder_name}..."
            )
            shutil.move(str(source_object_folder), str(dest_object_folder))
            moved_folders.append(subfolder_name)
        else:
            print(
                f"    [WARNING] Object folder not found for {subfolder_name}, skipping..."
            )

    if not moved_folders:
        print("[ERROR] No object folders were moved")
        return False

    print(
        f"[OK] Moved {len(moved_folders)} object folder(s) to {generated_objects_dir}"
    )
    print()

    print_step_header(4, "Generating frames from objects")

    if not run_process_with_error_handling(
        fg_process_multiple_folder,
        str(generated_objects_dir),
        error_message="Frame generation failed",
    ):
        return False

    print()

    print_step_header(5, "Comparing generated frames with original frames")

    all_tests_passed = True
    test_results = []

    for subfolder_name in sorted(moved_folders):
        print(f"[TEST] Testing {subfolder_name}...")

        original_folder = frames_files_dir / subfolder_name
        generated_frames_folder = generated_objects_dir / subfolder_name / "frames"

        if not generated_frames_folder.exists():
            print(
                f"    [ERROR] Generated frames folder not found: {generated_frames_folder}"
            )
            all_tests_passed = False
            test_results.append(
                (subfolder_name, False, ["Generated frames folder not found"])
            )
            continue

        success, details = compare_folders(
            str(original_folder), str(generated_frames_folder), subfolder_name
        )

        for detail in details:
            print(detail)

        status_msg = "All Files Match!" if success else "Files Do Not Match"
        print(
            f"    [{'SUCCESS' if success else 'FAIL'}] {subfolder_name} - {status_msg}"
        )

        if not success:
            all_tests_passed = False

        test_results.append((subfolder_name, success, details))

    print()
    print_step_header(6, "Cleaning up generated-objects folder")

    if not safe_remove_folder(generated_objects_dir, str(generated_objects_dir)):
        print(f"[INFO] {generated_objects_dir} does not exist, skipping cleanup")

    print()

    print(SECTION_SEPARATOR)
    print("Test Summary")
    print(SECTION_SEPARATOR)

    passed_count = sum(1 for _, success, _ in test_results if success)
    total_count = len(test_results)

    for subfolder_name, success, _ in test_results:
        status = "PASS" if success else "FAIL"
        print(f"  {status}: {subfolder_name}")

    print()
    print(f"Results: {passed_count}/{total_count} tests passed")

    if all_tests_passed:
        print("[SUCCESS] All tests passed!")
        return True
    else:
        print("[FAIL] Some tests failed")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
