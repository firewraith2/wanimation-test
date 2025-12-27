"""
WAN file I/O operations for extracting and generating WAN sprite files.
"""

from pathlib import Path
from typing import Union, Optional

from .sprite import BaseSprite
from data import read_file_to_bytes, write_bytes_to_file
from external_files import read_external_files, write_external_files
from .wan_parser import WANParser
from .wan_writer import WANWriter


def extract_wan(wan_file_path: Path, output_dir: Optional[Path] = None) -> BaseSprite:
    """
    Extract a WAN sprite file to a sprite object, optionally writing to directory.

    Args:
        wan_file_path: Path to the .wan file
        output_dir: Optional output directory path. If provided, writes XML, palette, and images.

    Returns:
        BaseSprite object that was extracted
    """
    rawdata = read_file_to_bytes(wan_file_path)
    parser = WANParser(rawdata)
    parser._read_headers()

    is_4bpp = not (parser.wan_img_data_info and parser.wan_img_data_info.is_8bpp_sprite)

    sprite = parser.parse(is_4bpp=is_4bpp)

    if output_dir is not None:
        write_external_files(sprite, output_dir)

    return sprite


def generate_wan(
    sprite_or_dir: Union[BaseSprite, Path], output_dir: Optional[Path] = None
) -> Optional[bytes]:
    """
    Generate WAN file bytes from a sprite object or directory structure.

    Args:
        sprite_or_dir: Either a BaseSprite object or a directory path containing sprite data
        output_dir: Optional output path for the WAN file. If provided, writes the WAN file to this path.

    Returns:
        WAN file as bytes if output_dir is None, otherwise None
    """
    if isinstance(sprite_or_dir, BaseSprite):
        sprite = sprite_or_dir
    else:
        sprite = read_external_files(sprite_or_dir)

    writer = WANWriter(sprite)
    wan_bytes = writer.write()

    if output_dir is not None:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_to_file(output_dir, wan_bytes)

    return wan_bytes
