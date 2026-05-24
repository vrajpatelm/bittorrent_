import os
from parser import bdncode_to_dict

def extract_files(torrent_path, bin_path, output_dir="extracted_downloads"):
    """
    Extracts the raw binary pieces from downloaded_file.bin and reconstructs 
    the actual files and folders based on the metadata inside the .torrent file.
    """
    with open(torrent_path, 'rb') as f:
        torrent_data = bdncode_to_dict(f.read())
    
    info = torrent_data[b'info']
    
    # Check if this is a single-file or multi-file torrent
    if b'files' not in info:
        # Single file torrent
        name = info[b'name'].decode('utf-8')
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, name)
        
        with open(bin_path, 'rb') as f_in, open(out_path, 'wb') as f_out:
            f_out.write(f_in.read())
        print(f"[OK] Extracted single file: {name}")
        return
        
    # Multi-file torrent
    base_folder_name = info[b'name'].decode('utf-8')
    base_dir = os.path.join(output_dir, base_folder_name)
    print(f"Creating folder structure for: {base_folder_name}")
    
    with open(bin_path, 'rb') as f_in:
        for file_info in info[b'files']:
            length = file_info[b'length']
            path_parts = [p.decode('utf-8') for p in file_info[b'path']]
            
            # Reconstruct the file's original directory path
            full_path = os.path.join(base_dir, *path_parts)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Read exact bytes for this specific file from the big binary blob
            file_data = f_in.read(length)
            
            # Write the file to disk
            with open(full_path, 'wb') as f_out:
                f_out.write(file_data)
            print(f"[OK] Extracted: {os.path.join(*path_parts)} ({length} bytes)")

if __name__ == "__main__":
    import sys
    torrent_file = "alicesadventures19033gut_archive.torrent"
    
    if len(sys.argv) > 1:
        torrent_file = sys.argv[1]
    elif not os.path.exists(torrent_file):
        # Fallback to parent dir or test.torrent
        if os.path.exists(os.path.join("..", torrent_file)):
            torrent_file = os.path.join("..", torrent_file)
        elif os.path.exists("test.torrent"):
            torrent_file = "test.torrent"
        elif os.path.exists(r"C:\Users\VRAJ\Downloads\test.torrent"):
            torrent_file = r"C:\Users\VRAJ\Downloads\test.torrent"
            
    bin_file = "downloaded_file.bin"
    if not os.path.exists(bin_file) and os.path.exists(os.path.join("..", bin_file)):
        bin_file = os.path.join("..", bin_file)
        
    if os.path.exists(bin_file) and os.path.exists(torrent_file):
        print(f"Extracting files from {bin_file} using {torrent_file}...")
        extract_files(torrent_file, bin_file)
        print("\nAll files extracted successfully! Check the 'extracted_downloads' folder.")
    else:
        print(f"Could not run extraction. bin_file exists: {os.path.exists(bin_file)}, torrent_file exists ({torrent_file}): {os.path.exists(torrent_file)}")

