"""
Folder Structure Reconstruction Tool
Reads a JSON structure file and recreates the folder structure, 
optionally moving/copying files from a source location.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Set
import hashlib
from datetime import datetime


class FolderReconstructor:
    """Class to handle folder structure reconstruction from JSON."""
    
    def __init__(self, structure_file: str, verbose: bool = True):
        """
        Initialize the reconstructor.
        
        Args:
            structure_file: Path to the JSON structure file
            verbose: Whether to print progress messages
        """
        self.verbose = verbose
        self.structure = self._load_structure(structure_file)
        self.stats = {
            "dirs_created": 0,
            "files_copied": 0,
            "files_moved": 0,
            "errors": 0
        }
    
    def _load_structure(self, structure_file: str) -> Dict:
        """Load the JSON structure file."""
        with open(structure_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    def create_empty_structure(self, target_dir: str) -> None:
        """
        Create the folder structure without files.
        
        Args:
            target_dir: Target directory where structure will be created
        """
        target_path = Path(target_dir).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        
        self._log(f"Creating folder structure in: {target_path}")
        self._create_dirs_recursive(target_path, self.structure["tree"])
        self._log(f"✓ Created {self.stats['dirs_created']} directories")
    
    def _create_dirs_recursive(self, base_path: Path, tree: Dict) -> None:
        """Recursively create directory structure."""
        for dir_name, subtree in tree["directories"].items():
            dir_path = base_path / dir_name
            dir_path.mkdir(exist_ok=True)
            self.stats["dirs_created"] += 1
            self._create_dirs_recursive(dir_path, subtree)
    
    def reconstruct_with_files(self, source_dir: str, target_dir: str, 
                               mode: str = "copy", verify_hash: bool = False) -> None:
        """
        Recreate folder structure and copy/move files from source.
        
        Args:
            source_dir: Source directory containing the files
            target_dir: Target directory for the new structure
            mode: 'copy' or 'move' files
            verify_hash: Verify file integrity using hashes (requires hashes in JSON)
        """
        if mode not in ["copy", "move"]:
            raise ValueError("Mode must be 'copy' or 'move'")
        
        if verify_hash and not self.structure.get("include_hash", False):
            raise ValueError("Cannot verify hashes - structure was captured without hashes")
        
        source_path = Path(source_dir).resolve()
        target_path = Path(target_dir).resolve()
        
        if not source_path.exists():
            raise ValueError(f"Source directory does not exist: {source_path}")
        
        target_path.mkdir(parents=True, exist_ok=True)
        
        self._log(f"{'Copying' if mode == 'copy' else 'Moving'} files from {source_path} to {target_path}")
        
        # Build file mapping
        file_map = self._build_file_map(source_path)
        
        # Process the structure
        self._process_tree_recursive(
            source_path, target_path, self.structure["tree"], 
            file_map, mode, verify_hash
        )
        
        # Print statistics
        self._print_stats(mode)
    
    def _build_file_map(self, source_path: Path) -> Dict[str, Path]:
        """
        Build a mapping of filename -> full path for all files in source.
        Handles duplicate filenames by storing them in a list.
        """
        file_map = {}
        
        for root, _, files in os.walk(source_path):
            for filename in files:
                filepath = Path(root) / filename
                
                if filename not in file_map:
                    file_map[filename] = []
                file_map[filename].append(filepath)
        
        return file_map
    
    def _process_tree_recursive(self, source_base: Path, target_base: Path, 
                                tree: Dict, file_map: Dict, mode: str, 
                                verify_hash: bool) -> None:
        """Recursively process the tree and handle files."""
        
        # Process files in current directory
        for file_info in tree["files"]:
            filename = file_info["Filename"]
            target_file = target_base / filename
            
            # Find source file
            source_file = self._find_matching_file(
                filename, file_info, file_map, verify_hash
            )
            
            if source_file:
                try:
                    # Create parent directory if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy or move file
                    if mode == "copy":
                        shutil.copy2(source_file, target_file)
                        self.stats["files_copied"] += 1
                    else:  # move
                        shutil.move(str(source_file), str(target_file))
                        self.stats["files_moved"] += 1
                    
                    self._log(f"  {mode}: {filename}")
                    
                except Exception as e:
                    self._log(f"  Error processing {filename}: {e}")
                    self.stats["errors"] += 1
            else:
                self._log(f"  Warning: File not found in source: {filename}")
                self.stats["errors"] += 1
        
        # Process subdirectories
        for dir_name, subtree in tree["directories"].items():
            target_subdir = target_base / dir_name
            target_subdir.mkdir(exist_ok=True)
            self.stats["dirs_created"] += 1
            
            self._process_tree_recursive(
                source_base, target_subdir, subtree, file_map, mode, verify_hash
            )
    
    def _find_matching_file(self, filename: str, file_info: Dict, 
                           file_map: Dict, verify_hash: bool) -> Optional[Path]:
        """
        Find the matching source file for a given filename.
        Uses hash verification if enabled.
        """
        if filename not in file_map:
            return None
        
        candidates = file_map[filename]
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Multiple files with same name - use hash if available
        if verify_hash and "hash" in file_info:
            target_hash = file_info["hash"]
            
            for candidate in candidates:
                if self._get_file_hash(candidate) == target_hash:
                    return candidate
        
        # Otherwise return first match (with warning if multiple)
        if len(candidates) > 1:
            self._log(f"  Warning: Multiple matches for {filename}, using first")
        
        return candidates[0]
    
    def _get_file_hash(self, filepath: Path) -> Optional[str]:
        """Calculate MD5 hash of a file."""
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (PermissionError, OSError):
            return None
    
    def _print_stats(self, mode: str) -> None:
        """Print operation statistics."""
        self._log("\n" + "="*50)
        self._log("Operation Summary:")
        self._log(f"  Directories created: {self.stats['dirs_created']}")
        
        if mode == "copy":
            self._log(f"  Files copied: {self.stats['files_copied']}")
        else:
            self._log(f"  Files moved: {self.stats['files_moved']}")
        
        if self.stats["errors"] > 0:
            self._log(f"  Errors: {self.stats['errors']}")
        
        self._log("="*50)


def reconstruct_structure(structure_file: str, target_dir: str, 
                         source_dir: Optional[str] = None,
                         mode: str = "copy", verify_hash: bool = False,
                         verbose: bool = True) -> None:
    """
    Main function to reconstruct folder structure.
    
    Args:
        structure_file: Path to JSON structure file
        target_dir: Target directory for reconstruction
        source_dir: Source directory with files (if None, creates empty structure)
        mode: 'copy' or 'move' files
        verify_hash: Verify file integrity using hashes
        verbose: Print progress messages
    """
    reconstructor = FolderReconstructor(structure_file, verbose)
    
    if source_dir is None:
        # Create empty structure only
        reconstructor.create_empty_structure(target_dir)
    else:
        # Reconstruct with files
        reconstructor.reconstruct_with_files(
            source_dir, target_dir, mode, verify_hash
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Reconstruct folder structure from JSON"
    )
    parser.add_argument(
        "structure_file",
        help="JSON structure file"
    )
    parser.add_argument(
        "target_dir",
        help="Target directory for reconstruction"
    )
    parser.add_argument(
        "-s", "--source",
        help="Source directory containing files (omit for empty structure)"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["copy", "move"],
        default="copy",
        help="Copy or move files (default: copy)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify file integrity using hashes"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )
    
    args = parser.parse_args()
    
    try:
        reconstruct_structure(
            args.structure_file,
            args.target_dir,
            source_dir=args.source,
            mode=args.mode,
            verify_hash=args.verify,
            verbose=not args.quiet
        )
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
