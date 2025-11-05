"""
Folder Structure Capture Tool
Scans a directory and saves its structure to JSON format.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Union
import hashlib
from datetime import datetime


def get_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """
    Calculate MD5 hash of a file for verification purposes.
    
    Args:
        filepath: Path to the file
        chunk_size: Size of chunks to read at a time
        
    Returns:
        MD5 hash as hexadecimal string
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return None


def scan_directory(root_path: str, include_hash: bool = False) -> Dict:
    """
    Recursively scan directory and create a structure representation.
    
    Args:
        root_path: Root directory to scan
        include_hash: Whether to include file hashes (slower but verifiable)
        
    Returns:
        Dictionary representing the folder structure
    """
    root_path = Path(root_path).resolve()
    
    if not root_path.exists():
        raise ValueError(f"Path does not exist: {root_path}")
    
    if not root_path.is_dir():
        raise ValueError(f"Path is not a directory: {root_path}")
    
    structure = {
        "root": str(root_path),
        "captured_at": datetime.now().isoformat(),
        "include_hash": include_hash,
        "tree": _scan_recursive(root_path, include_hash)
    }
    
    return structure


def _scan_recursive(path: Path, include_hash: bool) -> Dict:
    """
    Recursively scan a directory path.
    
    Args:
        path: Path object to scan
        include_hash: Whether to include file hashes
        
    Returns:
        Dictionary with 'files' and 'directories' keys
    """
    result = {
        "files": [],
        "directories": {}
    }
    
    try:
        items = sorted(path.iterdir())
    except PermissionError:
        return result
    
    for item in items:
        try:
            if item.is_file():
                file_info = {
                    "name": item.name,
                    "size": item.stat().st_size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                }
                
                if include_hash:
                    file_info["hash"] = get_file_hash(str(item))
                
                result["files"].append(file_info)
                
            elif item.is_dir():
                result["directories"][item.name] = _scan_recursive(item, include_hash)
                
        except (PermissionError, OSError) as e:
            print(f"Warning: Could not access {item}: {e}")
            continue
    
    return result


def save_structure(root_path: str, output_file: str, include_hash: bool = False, 
                   indent: int = 2) -> None:
    """
    Scan directory and save structure to JSON file.
    
    Args:
        root_path: Root directory to scan
        output_file: Output JSON file path
        include_hash: Whether to include file hashes
        indent: JSON indentation level
    """
    print(f"Scanning directory: {root_path}")
    structure = scan_directory(root_path, include_hash)
    
    print(f"Saving structure to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(structure, f, indent=indent, ensure_ascii=False)
    
    # Count files and directories
    file_count = count_files(structure["tree"])
    dir_count = count_directories(structure["tree"])
    
    print(f"✓ Captured {file_count} files and {dir_count} directories")


def count_files(tree: Dict) -> int:
    """Count total number of files in the tree."""
    count = len(tree["files"])
    for subdir in tree["directories"].values():
        count += count_files(subdir)
    return count


def count_directories(tree: Dict) -> int:
    """Count total number of directories in the tree."""
    count = len(tree["directories"])
    for subdir in tree["directories"].values():
        count += count_directories(subdir)
    return count


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Capture folder structure and save to JSON"
    )
    parser.add_argument(
        "source_dir",
        help="Directory to scan"
    )
    parser.add_argument(
        "-o", "--output",
        default="folder_structure.json",
        help="Output JSON file (default: folder_structure.json)"
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Include file hashes (slower but enables verification)"
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level (default: 2)"
    )
    
    args = parser.parse_args()
    
    try:
        save_structure(
            args.source_dir,
            args.output,
            include_hash=args.hash,
            indent=args.indent
        )
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
