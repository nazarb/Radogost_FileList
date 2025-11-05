"""
Example demonstration of folder structure capture and reconstruction.
This script creates a sample folder structure, captures it, and reconstructs it.
"""

import os
import tempfile
import shutil
from pathlib import Path
from folder_structure_capture import save_structure
from folder_structure_reconstruct import reconstruct_structure


def create_sample_structure(base_path: Path) -> None:
    """Create a sample folder structure for testing."""
    
    # Create directories
    (base_path / "documents").mkdir()
    (base_path / "documents" / "reports").mkdir()
    (base_path / "images").mkdir()
    (base_path / "code").mkdir()
    (base_path / "code" / "python").mkdir()
    (base_path / "code" / "tests").mkdir()
    
    # Create sample files
    files_to_create = {
        "README.md": "# Sample Project\n\nThis is a test project.",
        "documents/notes.txt": "Meeting notes from today.",
        "documents/reports/q3_report.txt": "Q3 Sales Report\n\nRevenue: $1M",
        "documents/reports/q4_report.txt": "Q4 Sales Report\n\nRevenue: $1.5M",
        "images/logo.txt": "[Placeholder for logo image]",
        "code/python/main.py": "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()",
        "code/python/utils.py": "def helper():\n    return 'Helper function'",
        "code/tests/test_main.py": "def test_main():\n    assert True",
    }
    
    for filepath, content in files_to_create.items():
        full_path = base_path / filepath
        full_path.write_text(content)
    
    print(f"✓ Created sample structure in {base_path}")


def demo_capture_and_reconstruct():
    """Demonstrate the complete workflow."""
    
    print("="*60)
    print("FOLDER STRUCTURE MANAGEMENT DEMO")
    print("="*60)
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Paths
        original_path = tmp_path / "original"
        reconstructed_path = tmp_path / "reconstructed"
        json_file = tmp_path / "structure.json"
        
        original_path.mkdir()
        
        print("\n1. Creating sample folder structure...")
        create_sample_structure(original_path)
        
        print("\n2. Scanning and capturing structure to JSON...")
        save_structure(str(original_path), str(json_file), include_hash=True)
        
        print(f"\n3. JSON structure saved to: {json_file}")
        print(f"   File size: {json_file.stat().st_size} bytes")
        
        print("\n4. Reconstructing structure in new location...")
        reconstruct_structure(
            str(json_file),
            str(reconstructed_path),
            source_dir=str(original_path),
            mode="copy",
            verify_hash=True
        )
        
        print("\n5. Verification - comparing original and reconstructed:")
        
        # Compare structures
        original_files = sorted([str(p.relative_to(original_path)) 
                                for p in original_path.rglob("*") if p.is_file()])
        reconstructed_files = sorted([str(p.relative_to(reconstructed_path)) 
                                     for p in reconstructed_path.rglob("*") if p.is_file()])
        
        print(f"\n   Original files ({len(original_files)}):")
        for f in original_files:
            print(f"     - {f}")
        
        print(f"\n   Reconstructed files ({len(reconstructed_files)}):")
        for f in reconstructed_files:
            print(f"     - {f}")
        
        if original_files == reconstructed_files:
            print("\n   ✓ SUCCESS: Structures match perfectly!")
        else:
            print("\n   ✗ ERROR: Structures don't match")
        
        # Show JSON preview
        print("\n6. JSON Structure Preview:")
        print("-" * 60)
        with open(json_file, 'r') as f:
            content = f.read()
            # Show first 500 characters
            print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 60)
    
    print("\n" + "="*60)
    print("DEMO COMPLETED")
    print("="*60)


def demo_empty_structure():
    """Demonstrate creating empty folder structure."""
    
    print("\n" + "="*60)
    print("EMPTY STRUCTURE DEMO")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Paths
        source_path = tmp_path / "source"
        empty_target = tmp_path / "empty_structure"
        json_file = tmp_path / "structure.json"
        
        source_path.mkdir()
        
        print("\n1. Creating sample structure...")
        create_sample_structure(source_path)
        
        print("\n2. Capturing structure...")
        save_structure(str(source_path), str(json_file), include_hash=False)
        
        print("\n3. Creating empty folder structure (no files)...")
        reconstruct_structure(str(json_file), str(empty_target), source_dir=None)
        
        print("\n4. Result - directories only:")
        for dirpath, dirnames, filenames in os.walk(empty_target):
            level = dirpath.replace(str(empty_target), '').count(os.sep)
            indent = ' ' * 2 * level
            print(f'{indent}{os.path.basename(dirpath)}/')
            subindent = ' ' * 2 * (level + 1)
            for dirname in sorted(dirnames):
                print(f'{subindent}{dirname}/')
    
    print("\n" + "="*60)


if __name__ == "__main__":
    # Run the main demo
    demo_capture_and_reconstruct()
    
    print("\n")
    
    # Run the empty structure demo
    demo_empty_structure()
    
    print("\n\nTo use these tools on your own folders:")
    print("  1. Capture: python folder_structure_capture.py /your/folder -o output.json")
    print("  2. Reconstruct: python folder_structure_reconstruct.py output.json /target/folder -s /your/folder")
