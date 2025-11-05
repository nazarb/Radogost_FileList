"""
Download files from enhanced FileList JSON
Uses URL information to download files and recreate folder structure
"""

import json
import requests
from pathlib import Path
from typing import Dict, Optional
import time
from urllib.parse import urlparse


class FileDownloader:
    """Download files from URLs in enhanced FileList.json."""
    
    def __init__(self, json_file: str, verbose: bool = True):
        """
        Initialize the downloader.
        
        Args:
            json_file: Path to enhanced FileList.json with URLs
            verbose: Whether to print progress messages
        """
        self.json_file = json_file
        self.verbose = verbose
        self.structure = self._load_structure()
        self.stats = {
            "files_downloaded": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "bytes_downloaded": 0
        }
    
    def _load_structure(self) -> Dict:
        """Load the JSON structure."""
        with open(self.json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    def download_all(self, target_dir: str, skip_existing: bool = True,
                    delay: float = 0.5) -> None:
        """
        Download all files from the structure.
        
        Args:
            target_dir: Target directory for downloads
            skip_existing: Skip files that already exist
            delay: Delay between downloads (seconds)
        """
        target_path = Path(target_dir).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        
        self._log(f"Downloading files to: {target_path}")
        self._log(f"Skip existing files: {skip_existing}")
        self._log("")
        
        # Download files
        self._download_tree_recursive(
            target_path, self.structure['tree'], skip_existing, delay
        )
        
        # Print statistics
        self._print_stats()
    
    def _download_tree_recursive(self, base_path: Path, tree: Dict,
                                 skip_existing: bool, delay: float) -> None:
        """Recursively download files from tree."""
        
        # Process files in current directory
        for file_info in tree.get('files', []):
            filename = file_info['name']
            file_path = base_path / filename
            
            # Check if URL exists
            if 'url' not in file_info:
                self._log(f"  ⚠ Skipping {filename} - no URL available")
                self.stats['files_skipped'] += 1
                continue
            
            # Skip if file exists and skip_existing is True
            if skip_existing and file_path.exists():
                self._log(f"  ⊙ Skipping {filename} - already exists")
                self.stats['files_skipped'] += 1
                continue
            
            # Download the file
            success = self._download_file(
                file_info['url'],
                file_path,
                file_info
            )
            
            if success:
                self.stats['files_downloaded'] += 1
            else:
                self.stats['files_failed'] += 1
            
            # Delay between downloads
            if delay > 0:
                time.sleep(delay)
        
        # Process subdirectories recursively
        for dir_name, subtree in tree.get('directories', {}).items():
            subdir_path = base_path / dir_name
            subdir_path.mkdir(exist_ok=True)
            
            self._download_tree_recursive(
                subdir_path, subtree, skip_existing, delay
            )
    
    def _download_file(self, url: str, file_path: Path,
                      file_info: Dict) -> bool:
        """
        Download a single file.
        
        Args:
            url: URL to download from
            file_path: Local path to save to
            file_info: File metadata dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._log(f"  ↓ Downloading {file_info['name']}...")
            
            # Make request with timeout
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Write file in chunks
            total_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            self.stats['bytes_downloaded'] += total_size
            
            # Verify size if available
            expected_size = file_info.get('size')
            if expected_size and total_size != expected_size:
                self._log(f"    ⚠ Size mismatch: expected {expected_size}, got {total_size}")
            
            self._log(f"    ✓ Downloaded {self._format_size(total_size)}")
            return True
            
        except requests.exceptions.RequestException as e:
            self._log(f"    ✗ Failed: {e}")
            return False
        except Exception as e:
            self._log(f"    ✗ Error: {e}")
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _print_stats(self) -> None:
        """Print download statistics."""
        self._log("\n" + "="*60)
        self._log("DOWNLOAD STATISTICS")
        self._log("="*60)
        self._log(f"Files downloaded:     {self.stats['files_downloaded']}")
        self._log(f"Files skipped:        {self.stats['files_skipped']}")
        self._log(f"Files failed:         {self.stats['files_failed']}")
        self._log(f"Total downloaded:     {self._format_size(self.stats['bytes_downloaded'])}")
        self._log("="*60)


def download_files(json_file: str, target_dir: str,
                   skip_existing: bool = True,
                   delay: float = 0.5,
                   verbose: bool = True) -> None:
    """
    Convenience function to download files from enhanced JSON.
    
    Args:
        json_file: Path to enhanced FileList.json with URLs
        target_dir: Target directory for downloads
        skip_existing: Skip files that already exist
        delay: Delay between downloads in seconds
        verbose: Print progress messages
    """
    downloader = FileDownloader(json_file, verbose)
    downloader.download_all(target_dir, skip_existing, delay)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Download files from enhanced FileList.json"
    )
    parser.add_argument(
        "json_file",
        help="Path to enhanced FileList.json with URLs"
    )
    parser.add_argument(
        "target_dir",
        help="Target directory for downloads"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-download existing files"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between downloads in seconds (default: 0.5)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )
    
    args = parser.parse_args()
    
    try:
        download_files(
            args.json_file,
            args.target_dir,
            skip_existing=not args.no_skip,
            delay=args.delay,
            verbose=not args.quiet
        )
        print("\n✓ Download process completed!")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
