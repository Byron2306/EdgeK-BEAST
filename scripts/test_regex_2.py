import re

filename = "compute_ledger"
subdir = "compute"
content = "from app.kernel.compute.compute_ledger import ComputeLedger\nfrom app.kernel.compute.compute_ledger import ComputeLedger"

# Regex: app\.kernel\.(?!compute\.)compute_ledger
pattern = re.compile(rf'app\.kernel\.(?!{subdir}\.){filename}')

new_content = pattern.sub(f"app.kernel.{subdir}.{filename}", content)
print(new_content)
