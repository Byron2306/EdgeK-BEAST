import os
import re

subdirs = ["adapters", "capability", "data_processing", "deployment", "execution", "governance", "local", "networking", "registry", "security", "storage"]
pattern = re.compile(rf'app\.kernel\.compute\.({"|".join(subdirs)})')

def fix_file(file_path):
    try:
        with open(file_path, 'r', errors='ignore') as f:
            content = f.read()
        
        new_content = pattern.sub(r'app.kernel.\1', content)
        
        if new_content != content:
            with open(file_path, 'w') as f:
                f.write(new_content)
            return True
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
    return False

# Find all python files
files_fixed = 0
for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".py"):
            file_path = os.path.join(root, file)
            if fix_file(file_path):
                files_fixed += 1
                print(f"Fixed {file_path}")

print(f"Fixed {files_fixed} files.")
