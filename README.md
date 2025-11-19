8d55100e-e330-4a09-8786-63dbf549d414



# Folder Structure Management Tool

A Python utility for capturing folder structures as JSON and reconstructing them elsewhere.

## Features

- **Capture folder structure** with file metadata (size, modification time)
- **Optional file hashing** for integrity verification
- **Reconstruct structure** in a new location
- **Copy or move files** according to the saved structure
- **Handles duplicate filenames** intelligently

## Files

- `folder_structure_capture.py` - Scans directories and saves structure to JSON
- `folder_structure_reconstruct.py` - Reads JSON and recreates folder structure

## Usage

### 1. Capture Folder Structure

Basic capture:
```bash
python folder_structure_capture.py /path/to/source -o structure.json
```

Capture with file hashes (for verification):
```bash
python folder_structure_capture.py /path/to/source -o structure.json --hash
```

### 2. Reconstruct Folder Structure

Create empty folder structure (directories only):
```bash
python folder_structure_reconstruct.py structure.json /path/to/target
```

Copy files to match structure:
```bash
python folder_structure_reconstruct.py structure.json /path/to/target -s /path/to/source
```

Move files (instead of copying):
```bash
python folder_structure_reconstruct.py structure.json /path/to/target -s /path/to/source -m move
```

Verify file integrity with hashes:
```bash
python folder_structure_reconstruct.py structure.json /path/to/target -s /path/to/source --verify
```

## Example Workflow

```bash
# Step 1: Capture the structure of your project
python folder_structure_capture.py ~/my_project -o project_structure.json --hash

# Step 2: Later, reconstruct it in a new location
python folder_structure_reconstruct.py project_structure.json ~/new_project -s ~/my_project

# Or move files to organize them according to the structure
python folder_structure_reconstruct.py project_structure.json ~/organized -s ~/messy_folder -m move
```

## JSON Structure Format

```json
{
  "root": "/absolute/path/to/scanned/directory",
  "captured_at": "2025-11-05T10:30:00",
  "include_hash": true,
  "tree": {
    "files": [
      {
        "name": "file.txt",
        "size": 1024,
        "modified": "2025-11-05T10:00:00",
        "hash": "5d41402abc4b2a76b9719d911017c592"
      }
    ],
    "directories": {
      "subfolder": {
        "files": [...],
        "directories": {...}
      }
    }
  }
}
```

## Use Cases

1. **Backup & Restore**: Capture folder structure and restore it later
2. **Migration**: Move projects between systems while preserving structure
3. **Organization**: Reorganize scattered files according to a defined structure
4. **Archival**: Document folder structures for long-term storage
5. **Synchronization**: Compare and sync folder structures across locations

## Command Line Options

### folder_structure_capture.py

```
positional arguments:
  source_dir            Directory to scan

optional arguments:
  -o, --output         Output JSON file (default: folder_structure.json)
  --hash               Include file hashes for verification
  --indent             JSON indentation level (default: 2)
```

### folder_structure_reconstruct.py

```
positional arguments:
  structure_file       JSON structure file
  target_dir          Target directory for reconstruction

optional arguments:
  -s, --source        Source directory containing files
  -m, --mode          Copy or move files (default: copy)
  --verify            Verify file integrity using hashes
  -q, --quiet         Suppress progress messages
```

## Python API Usage

### Capturing Structure

```python
from folder_structure_capture import save_structure, scan_directory

# Capture and save
save_structure('/path/to/source', 'output.json', include_hash=True)

# Or get structure as dict
structure = scan_directory('/path/to/source', include_hash=False)
```

### Reconstructing Structure

```python
from folder_structure_reconstruct import reconstruct_structure, FolderReconstructor

# Simple reconstruction
reconstruct_structure('structure.json', '/path/to/target', 
                     source_dir='/path/to/source', mode='copy')

# Advanced usage with custom class
reconstructor = FolderReconstructor('structure.json', verbose=True)
reconstructor.reconstruct_with_files('/source', '/target', mode='copy', verify_hash=True)
```

## Requirements

- Python 3.8+
- Standard library only (no external dependencies)

## Notes

- File hashing uses MD5 (fast but not cryptographically secure)
- Duplicate filenames are handled by matching hashes when available
- Permissions errors are caught and logged
- Symbolic links are not followed
- Binary files are fully supported

## License

MIT License - feel free to use and modify as needed.
