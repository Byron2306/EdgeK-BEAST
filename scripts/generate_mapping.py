import os
import json

kernel_root = "/home/byron/Hivenance/edgek_beast_gateway/edgek-beast/app/kernel"
file_mapping = {}

subdirs = ["adapters", "capability", "compute", "data_processing", "deployment", "execution", "governance", "local", "networking", "registry", "security", "storage"]

for subdir in subdirs:
    subdir_path = os.path.join(kernel_root, subdir)
    if os.path.exists(subdir_path):
        for file in os.listdir(subdir_path):
            if file.endswith(".py") and file != "__init__.py":
                file_name = file[:-3]
                file_mapping[file_name] = subdir

print(json.dumps(file_mapping, indent=4))
