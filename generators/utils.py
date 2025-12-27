from wan_files import extract_wan
from external_files import read_external_files
from pathlib import Path


def validate_external_input(
    folder_or_wan_path: Path,
    raise_on_errors: bool = True,
):
    """Validate and load sprite from external files or WAN file.

    Args:
        folder_or_wan_path: Path to folder (with external files) or .wan file
        raise_on_errors: If True, raise exception on validation errors

    Returns:
        Tuple of (sprite, validation_info) where validation_info is a dict with:
        is_image_base, is_animation_base, requires_base_sprite
    """
    print("[VALIDATING] Validating files...\n")

    sprite = None

    if folder_or_wan_path.is_file():
        sprite = extract_wan(folder_or_wan_path)
        print(f"[OK] Loaded sprite from WAN file: {folder_or_wan_path}\n")
    else:
        sprite = read_external_files(folder_or_wan_path)
        print(f"[OK] Loaded sprite from external files\n")

    validation_info = sprite.validate(raise_on_errors=raise_on_errors)

    return sprite, validation_info
