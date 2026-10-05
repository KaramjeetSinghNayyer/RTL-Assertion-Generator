import os
import glob

def load_acsl_benchmarks(folder_path):
    """Loads raw C/ACSL files as text strings for the LLM to read."""
    benchmarks = {}
    search_path = os.path.join(folder_path, '*.c')
    
    for filepath in glob.glob(search_path):
        filename = os.path.basename(filepath)
        with open(filepath, 'r') as file:
            benchmarks[filename] = file.read()
            
    return benchmarks

if __name__ == "__main__":
    # Test that it works
    my_files = load_acsl_benchmarks("benchmarks")
    for name, code in my_files.items():
        print(f"--- Successfully Loaded: {name} ---")
        print(code[:50] + "...\n")
        