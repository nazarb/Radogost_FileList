"""
Merge CSV attributes into FileList JSON
Adds URL and openAccess information from a CSV file to the file entries in FileList.json
"""

import json
import csv
from pathlib import Path
from typing import Dict, List


class FileListEnhancer:
    """Enhance FileList.json with additional attributes from CSV."""
    
    def __init__(self, csv_file: str, json_file: str):
        """
        Initialize the enhancer.
        
        Args:
            csv_file: Path to CSV file with file URLs and attributes
            json_file: Path to FileList.json structure
        """
        self.csv_file = csv_file
        self.json_file = json_file
        self.url_mapping = {}
        self.stats = {
            "files_matched": 0,
            "files_unmatched": 0,
            "csv_entries_unused": 0
        }
    
    def load_csv_data(self) -> Dict[str, Dict]:
        """
        Load CSV data and create a mapping of filename -> attributes.
        
        Returns:
            Dictionary mapping filename to its attributes
        """
        print(f"Loading CSV data from: {self.csv_file}")
        
        with open(self.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                filename = row.get('Filename', '').strip()
                if filename:
                    self.url_mapping[filename] = {
                        'url': row.get('url', '').strip(),
                        'openAccess': row.get('openAccess', '').strip().lower() == 'true'
                    }
        
        print(f"✓ Loaded {len(self.url_mapping)} entries from CSV")
        return self.url_mapping
    
    def load_json_structure(self) -> Dict:
        """Load the FileList.json structure."""
        print(f"Loading JSON structure from: {self.json_file}")
        
        with open(self.json_file, 'r', encoding='utf-8') as f:
            structure = json.load(f)
        
        print(f"✓ Loaded JSON structure")
        return structure
    
    def enhance_tree(self, tree: Dict, used_files: set) -> None:
        """
        Recursively enhance the tree with CSV attributes.
        
        Args:
            tree: The tree dictionary to enhance
            used_files: Set to track which CSV entries have been used
        """
        # Process files in current directory
        for file_info in tree.get('files', []):
            filename = file_info['Filename']
            
            if filename in self.url_mapping:
                # Add the new attributes
                file_info['url'] = self.url_mapping[filename]['url']
                file_info['openAccess'] = self.url_mapping[filename]['openAccess']
                
                self.stats['files_matched'] += 1
                used_files.add(filename)
                print(f"  ✓ Enhanced: {filename}")
            else:
                self.stats['files_unmatched'] += 1
                print(f"  ⚠ No URL found for: {filename}")
        
        # Process subdirectories recursively
        for dir_name, subtree in tree.get('directories', {}).items():
            self.enhance_tree(subtree, used_files)
    
    def merge(self, output_file: str = None) -> Dict:
        """
        Main method to merge CSV data into JSON structure.
        
        Args:
            output_file: Path for output file (if None, overwrites original)
            
        Returns:
            Enhanced structure dictionary
        """
        # Load data
        self.load_csv_data()
        structure = self.load_json_structure()
        
        print("\nEnhancing file entries...")
        
        # Track which CSV entries are used
        used_files = set()
        
        # Enhance the tree
        self.enhance_tree(structure['tree'], used_files)
        
        # Calculate unused CSV entries
        self.stats['csv_entries_unused'] = len(self.url_mapping) - len(used_files)
        
        # Determine output file
        if output_file is None:
            output_file = self.json_file
        
        # Save enhanced structure
        print(f"\nSaving enhanced structure to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        
        # Print statistics
        self._print_stats(used_files)
        
        return structure
    
    def _print_stats(self, used_files: set) -> None:
        """Print merge statistics."""
        print("\n" + "="*60)
        print("MERGE STATISTICS")
        print("="*60)
        print(f"Files matched and enhanced:  {self.stats['files_matched']}")
        print(f"Files without URL match:     {self.stats['files_unmatched']}")
        print(f"CSV entries used:            {len(used_files)}")
        print(f"CSV entries unused:          {self.stats['csv_entries_unused']}")
        
        # Show unused CSV entries if any
        if self.stats['csv_entries_unused'] > 0:
            unused = set(self.url_mapping.keys()) - used_files
            print(f"\nUnused CSV entries:")
            for filename in sorted(unused):
                print(f"  - {filename}")
        
        print("="*60)


def merge_csv_to_json(csv_file: str, json_file: str, output_file: str = None) -> Dict:
    """
    Convenience function to merge CSV attributes into JSON structure.
    
    Args:
        csv_file: Path to CSV file with URLs and attributes
        json_file: Path to FileList.json
        output_file: Path for output (if None, overwrites json_file)
        
    Returns:
        Enhanced structure dictionary
    """
    enhancer = FileListEnhancer(csv_file, json_file)
    return enhancer.merge(output_file)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Merge CSV attributes (URLs, openAccess) into FileList.json"
    )
    parser.add_argument(
        "csv_file",
        help="Path to CSV file with file URLs"
    )
    parser.add_argument(
        "json_file",
        help="Path to FileList.json structure"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: overwrites json_file)"
    )
    
    args = parser.parse_args()
    
    try:
        merge_csv_to_json(args.csv_file, args.json_file, args.output)
        print("\n✓ Merge completed successfully!")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
