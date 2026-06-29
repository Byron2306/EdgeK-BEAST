import os
import re

def get_mapping(kernel_dir):
    mapping = {}
    subdirs = ["adapters", "capability", "compute", "data_processing", "deployment", "execution", "governance", "local", "networking", "registry", "security", "storage"]
    for subdir in subdirs:
        subdir_path = os.path.join(kernel_dir, subdir)
        if os.path.exists(subdir_path):
            for file in os.listdir(subdir_path):
                if file.endswith(".py") and file != "__init__.py":
                    filename = file[:-3]
                    mapping[filename] = subdir
    return mapping

def fix_imports(root_dir, mapping, dry_run=True):
    # Files to check: all .py files in app/ and tests/
    files_to_check = []
    for root, dirs, files in os.walk(root_dir):
        if "app" in root or "tests" in root:
            for file in files:
                if file.endswith(".py"):
                    files_to_check.append(os.path.join(root, file))

    for file_path in files_to_check:
        with open(file_path, "r") as f:
            content = f.read()

        new_content = content
        for filename, subdir in mapping.items():
            # Match 'app.kernel.<filename>'
            # But NOT if it's already 'app.kernel.<subdir>.<filename>'
            
            # Pattern: app.kernel.<filename>
            # Negative lookahead: (?!.<subdir>)
            
            pattern = rf"app\.kernel\.{filename}(?!\.{filename})"
            
            # This is tricky, I need to make sure I don't replace if it is already right.
            # Example: app.kernel.compute.perceive
            # If I have app.kernel.perceive, I want to change it to app.kernel.compute.perceive.
            
            # Let's use a simpler regex and check.
            
            pattern = rf"app\.kernel\.{filename}"
            matches = re.finditer(pattern, new_content)
            
            for match in matches:
                # Check if it is already 'app.kernel.<subdir>.<filename>'
                # The match is at match.start() and match.end()
                
                # Check context
                start = match.start()
                end = match.end()
                
                # If content[end:end+1] is '.', it might be a sub-module.
                # If content[start-len(subdir)-1:start-1] is '<subdir>', it might be already fixed.
                
                already_fixed = False
                if start >= len(subdir) + 1:
                    if new_content[start-len(subdir)-1:start] == f".{subdir}.":
                        already_fixed = True
                
                if not already_fixed:
                    new_path = f"app.kernel.{subdir}.{filename}"
                    # Only replace if it's not already fixed (the above check)
                    # and not followed by a dot (that would be a sub-module)
                    # Wait, if it is followed by a dot, it is NOT the file itself.
                    # e.g., app.kernel.compute_ledger.some_attribute
                    
                    if not already_fixed:
                        # Need to be careful with replacing.
                        # Using re.sub with a callback or carefully crafted regex.
                        
                        # Let's look for: app.kernel.<filename>
                        # And ensure it's not app.kernel.<filename>.something (module)
                        
                        # Actually, if it's app.kernel.filename, it is the module itself.
                        # If it's app.kernel.filename.something, then it's a submodule or attribute.
                        
                        # If I replace, I'll get app.kernel.subdir.filename.something, which is correct!
                        
                        # What if it's already app.kernel.subdir.filename?
                        # I already checked that.
                        
                        # What if I have: app.kernel.compute.compute_ledger
                        # And I have filename: compute_ledger, subdir: compute
                        # pattern: app.kernel.compute_ledger
                        # If I match app.kernel.compute_ledger in app.kernel.compute.compute_ledger
                        # I'd get app.kernel.compute.compute_ledger.compute_ledger? No.
                        
                        pass
        # This is getting too complicated for a single script run.
        # Let's do it file by file, using `replace` tool.
