"""
Enhanced Dataset Downloader with DOI Support
Downloads complete datasets from repository URLs including DOI landing pages.
Automatically extracts FileList.json URLs from DOI pages.
"""

import json
import requests
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import time
import argparse
import sys
from urllib.parse import urlparse, urljoin
import re
from html.parser import HTMLParser


class DataverseHTMLParser(HTMLParser):
    """Parse Dataverse HTML pages to extract file download links."""
    
    def __init__(self):
        super().__init__()
        self.file_links = []
        self.current_tag = None
        self.current_attrs = {}
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        self.current_attrs = dict(attrs)
        
        # Look for download links
        if tag == 'a':
            href = self.current_attrs.get('href', '')
            # Check for file download URLs
            if '/api/access/datafile/' in href:
                self.file_links.append(href)
    
    def get_filelist_url(self) -> Optional[str]:
        """Try to find FileList.json download URL."""
        for link in self.file_links:
            if 'filelist' in link.lower() or '18890' in link:
                return link
        return None


class DatasetDownloader:
    """Download complete datasets from repository URLs including DOI."""
    
    def __init__(self, verbose: bool = True):
        """
        Initialize the downloader.
        
        Args:
            verbose: Whether to print progress messages
        """
        self.verbose = verbose
        self.structure = None
        self.stats = {
            "files_downloaded": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "bytes_downloaded": 0
        }
    
    def _log(self, message: str, level: str = "info") -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            if level == "error":
                print(f"✗ {message}")
            elif level == "warning":
                print(f"⚠ {message}")
            elif level == "success":
                print(f"✓ {message}")
            else:
                print(message)
    
    def resolve_doi_url(self, doi_url: str) -> Optional[str]:
        """
        Resolve DOI URL to get FileList.json download URL.
        
        Args:
            doi_url: DOI URL (e.g., https://doi.org/10.58132/MGOHM8)
            
        Returns:
            Direct FileList.json download URL or None
        """
        self._log(f"Resolving DOI URL: {doi_url}")
        
        try:
            # Follow DOI redirect to get to the dataset page
            response = requests.get(doi_url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            final_url = response.url
            self._log(f"DOI resolved to: {final_url}")
            
            # Parse HTML to find FileList download link
            parser = DataverseHTMLParser()
            parser.feed(response.text)
            
            # Try to find FileList.json link
            filelist_url = parser.get_filelist_url()
            
            if filelist_url:
                # Make absolute URL if relative
                if filelist_url.startswith('/'):
                    parsed = urlparse(final_url)
                    filelist_url = f"{parsed.scheme}://{parsed.netloc}{filelist_url}"
                
                self._log(f"Found FileList URL: {filelist_url}", "success")
                return filelist_url
            
            # If not found in HTML, try common patterns
            self._log("FileList link not found in HTML, trying common patterns...")
            
            # Parse the final URL to get scheme and netloc
            parsed = urlparse(final_url)
            
            # Try to construct URL based on dataset ID
            if 'dataset.xhtml' in final_url:
                # Extract dataset ID
                match = re.search(r'persistentId=doi:([^&]+)', final_url)
                if match:
                    doi_id = match.group(1)
                    self._log(f"Dataset DOI ID: {doi_id}")
                
                # Look for FileList.json specifically in the HTML
                filelist_matches = re.findall(r'FileList\.json[^"]*?"[^"]*?(\d+)', response.text)
                if filelist_matches:
                    file_id = filelist_matches[0]
                    test_url = f"{parsed.scheme}://{parsed.netloc}/api/access/datafile/{file_id}"
                    self._log(f"Found FileList.json reference: {test_url}", "success")
                    return test_url
                
                # Look for file IDs in the page
                file_ids = re.findall(r'/api/access/datafile/(\d+)', response.text)
                if file_ids:
                    self._log(f"Found {len(file_ids)} file references")
                    
                    # Try to find the FileList by testing each file
                    for file_id in sorted(set(file_ids), reverse=True):
                        test_url = f"{parsed.scheme}://{parsed.netloc}/api/access/datafile/{file_id}"
                        
                        # Quick check if it's JSON
                        try:
                            self._log(f"Testing: {test_url}")
                            test_response = requests.head(test_url, timeout=10)
                            content_type = test_response.headers.get('Content-Type', '')
                            content_disp = test_response.headers.get('Content-Disposition', '')
                            
                            # Check if it's FileList.json
                            if 'FileList.json' in content_disp or 'filelist.json' in content_disp.lower():
                                self._log(f"Found FileList.json: {test_url}", "success")
                                return test_url
                            
                            # Otherwise check if it's JSON
                            if 'json' in content_type.lower() or 'application/json' in content_type:
                                self._log(f"Found JSON file: {test_url}", "success")
                                return test_url
                        except Exception as e:
                            continue
            
            self._log("Could not automatically resolve FileList URL", "warning")
            self._log("You may need to provide the direct FileList URL with -u option", "warning")
            return None
            
        except requests.exceptions.RequestException as e:
            self._log(f"Failed to resolve DOI: {e}", "error")
            return None
    
    def download_filelist(self, url: str, output_path: Optional[str] = None, 
                         is_doi: bool = False) -> Dict:
        """
        Download FileList.json from a URL.
        
        Args:
            url: URL to download FileList.json from (can be DOI)
            output_path: Optional path to save the downloaded JSON
            is_doi: Whether the URL is a DOI
            
        Returns:
            Loaded JSON structure
        """
        # If it's a DOI URL, resolve it first
        if is_doi or 'doi.org' in url.lower():
            self._log("Detected DOI URL, resolving...")
            resolved_url = self.resolve_doi_url(url)
            
            if not resolved_url:
                raise ValueError(
                    "Could not automatically resolve DOI to FileList URL.\n"
                    "Please use the direct FileList URL with -u option:\n"
                    "  python dataset_downloader.py -u 'https://...api/access/datafile/18890' -o ./output"
                )
            
            url = resolved_url
        
        self._log(f"Downloading FileList.json from: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse JSON
            structure = response.json()
            
            # Save to file if path provided
            if output_path:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(structure, f, indent=2, ensure_ascii=False)
                
                self._log(f"Saved FileList.json to: {output_file}", "success")
            
            self.structure = structure
            self._log(f"FileList.json loaded successfully", "success")
            
            return structure
            
        except requests.exceptions.RequestException as e:
            self._log(f"Failed to download FileList.json: {e}", "error")
            raise
        except json.JSONDecodeError as e:
            self._log(f"Failed to parse JSON: {e}", "error")
            raise
    
    def load_local_filelist(self, filepath: str) -> Dict:
        """
        Load FileList.json from a local file.
        
        Args:
            filepath: Path to local FileList.json
            
        Returns:
            Loaded JSON structure
        """
        self._log(f"Loading FileList.json from: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                structure = json.load(f)
            
            self.structure = structure
            self._log(f"FileList.json loaded successfully", "success")
            
            return structure
            
        except Exception as e:
            self._log(f"Failed to load FileList.json: {e}", "error")
            raise
    
    def download_dataset(self, target_dir: str, skip_existing: bool = True,
                        delay: float = 0.5, create_structure: bool = True) -> None:
        """
        Download all files from the loaded structure.
        
        Args:
            target_dir: Target directory for downloads
            skip_existing: Skip files that already exist
            delay: Delay between downloads (seconds)
            create_structure: Create folder structure from JSON
        """
        if self.structure is None:
            raise ValueError("No FileList loaded. Call download_filelist() or load_local_filelist() first.")
        
        target_path = Path(target_dir).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        
        self._log("")
        self._log("="*70)
        self._log(f"Downloading dataset to: {target_path}")
        self._log(f"Skip existing files: {skip_existing}")
        self._log(f"Create folder structure: {create_structure}")
        self._log("="*70)
        self._log("")
        
        # Count total files
        total_files = self._count_files(self.structure['tree'])
        self._log(f"Total files to process: {total_files}")
        self._log("")
        
        # Download files
        current_file = [0]  # Use list to allow modification in nested function
        self._download_tree_recursive(
            target_path, 
            self.structure['tree'], 
            skip_existing, 
            delay,
            create_structure,
            total_files,
            current_file
        )
        
        # Print statistics
        self._print_stats()
    
    def _count_files(self, tree: Dict) -> int:
        """Count total number of files in the tree."""
        count = len(tree.get('files', []))
        for subtree in tree.get('directories', {}).values():
            count += self._count_files(subtree)
        return count
    
    def _download_tree_recursive(self, base_path: Path, tree: Dict,
                                 skip_existing: bool, delay: float,
                                 create_structure: bool, total_files: int,
                                 current_file: List[int]) -> None:
        """Recursively download files from tree."""
        
        # Process files in current directory
        for file_info in tree.get('files', []):
            current_file[0] += 1
            
            # Support both 'name' and 'Filename' keys
            filename = file_info.get('name') or file_info.get('Filename')
            if not filename:
                self._log("Skipping file with no name/Filename", "warning")
                continue
            
            file_path = base_path / filename
            
            # Check if URL exists
            if 'url' not in file_info:
                self._log(f"[{current_file[0]}/{total_files}] ⚠ Skipping {filename} - no URL available", "warning")
                self.stats['files_skipped'] += 1
                continue
            
            # Skip if file exists and skip_existing is True
            if skip_existing and file_path.exists():
                self._log(f"[{current_file[0]}/{total_files}] ⊙ Skipping {filename} - already exists")
                self.stats['files_skipped'] += 1
                continue
            
            # Download the file
            success = self._download_file(
                file_info['url'],
                file_path,
                file_info,
                current_file[0],
                total_files
            )
            
            if success:
                self.stats['files_downloaded'] += 1
            else:
                self.stats['files_failed'] += 1
            
            # Delay between downloads
            if delay > 0 and current_file[0] < total_files:
                time.sleep(delay)
        
        # Process subdirectories recursively
        if create_structure:
            for dir_name, subtree in tree.get('directories', {}).items():
                subdir_path = base_path / dir_name
                subdir_path.mkdir(exist_ok=True)
                
                self._download_tree_recursive(
                    subdir_path, subtree, skip_existing, delay,
                    create_structure, total_files, current_file
                )
    
    def _download_file(self, url: str, file_path: Path,
                      file_info: Dict, current: int, total: int) -> bool:
        """
        Download a single file.
        
        Args:
            url: URL to download from
            file_path: Local path to save to
            file_info: File metadata dictionary
            current: Current file number
            total: Total number of files
            
        Returns:
            True if successful, False otherwise
        """
        filename = file_info.get('name') or file_info.get('Filename')
        
        try:
            self._log(f"[{current}/{total}] ↓ Downloading {filename}...")
            
            # Make request with timeout
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
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
                self._log(f"           ⚠ Size mismatch: expected {self._format_size(expected_size)}, "
                         f"got {self._format_size(total_size)}", "warning")
            else:
                self._log(f"           ✓ {self._format_size(total_size)}", "success")
            
            return True
            
        except requests.exceptions.RequestException as e:
            self._log(f"           ✗ Failed: {e}", "error")
            return False
        except Exception as e:
            self._log(f"           ✗ Error: {e}", "error")
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
        self._log("\n" + "="*70)
        self._log("DOWNLOAD SUMMARY")
        self._log("="*70)
        self._log(f"Files downloaded:     {self.stats['files_downloaded']}")
        self._log(f"Files skipped:        {self.stats['files_skipped']}")
        self._log(f"Files failed:         {self.stats['files_failed']}")
        self._log(f"Total downloaded:     {self._format_size(self.stats['bytes_downloaded'])}")
        self._log("="*70)


def download_complete_dataset(filelist_url: Optional[str] = None,
                              filelist_path: Optional[str] = None,
                              target_dir: str = "./downloaded_dataset",
                              save_filelist: bool = True,
                              skip_existing: bool = True,
                              delay: float = 0.5,
                              create_structure: bool = True,
                              is_doi: bool = False,
                              verbose: bool = True) -> None:
    """
    Download a complete dataset from a repository.
    
    Args:
        filelist_url: URL to download FileList.json from (can be DOI)
        filelist_path: Path to local FileList.json (if not downloading)
        target_dir: Target directory for downloads
        save_filelist: Save downloaded FileList.json locally
        skip_existing: Skip files that already exist
        delay: Delay between downloads in seconds
        create_structure: Create folder structure from JSON
        is_doi: Whether the URL is a DOI
        verbose: Print progress messages
    """
    downloader = DatasetDownloader(verbose=verbose)
    
    # Load FileList
    if filelist_url:
        filelist_save_path = None
        if save_filelist:
            filelist_save_path = str(Path(target_dir) / "FileList.json")
        
        downloader.download_filelist(filelist_url, filelist_save_path, is_doi=is_doi)
    elif filelist_path:
        downloader.load_local_filelist(filelist_path)
    else:
        raise ValueError("Either filelist_url or filelist_path must be provided")
    
    # Download all files
    downloader.download_dataset(
        target_dir,
        skip_existing=skip_existing,
        delay=delay,
        create_structure=create_structure
    )


def main():
    """Main entry point for command-line usage."""
    
    parser = argparse.ArgumentParser(
        description="Download complete dataset from repository (supports DOI URLs)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download from DOI URL
  python dataset_downloader.py -d "https://doi.org/10.58132/MGOHM8" -o ./data
  
  # Download from FileList URL
  python dataset_downloader.py -u "https://example.com/api/access/datafile/18890" -o ./data
  
  # Download from local FileList
  python dataset_downloader.py -f FileList.json -o ./data
  
  # Download without folder structure
  python dataset_downloader.py -u "https://example.com/filelist" -o ./data --no-structure
        """
    )
    
    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-d", "--doi",
        help="DOI URL (e.g., https://doi.org/10.58132/MGOHM8)"
    )
    input_group.add_argument(
        "-u", "--url",
        help="Direct URL to download FileList.json from"
    )
    input_group.add_argument(
        "-f", "--file",
        help="Path to local FileList.json"
    )
    
    # Output options
    parser.add_argument(
        "-o", "--output",
        default="./downloaded_dataset",
        help="Target directory for downloads (default: ./downloaded_dataset)"
    )
    
    # Download options
    parser.add_argument(
        "--no-save-filelist",
        action="store_true",
        help="Don't save downloaded FileList.json locally"
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
        "--no-structure",
        action="store_true",
        help="Download all files to output directory without creating subdirectories"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )
    
    args = parser.parse_args()
    
    try:
        # Determine the URL and whether it's a DOI
        url = args.doi or args.url
        is_doi = args.doi is not None
        
        download_complete_dataset(
            filelist_url=url,
            filelist_path=args.file,
            target_dir=args.output,
            save_filelist=not args.no_save_filelist,
            skip_existing=not args.no_skip,
            delay=args.delay,
            create_structure=not args.no_structure,
            is_doi=is_doi,
            verbose=not args.quiet
        )
        
        print("\n✓ Dataset download completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        if not args.quiet:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
