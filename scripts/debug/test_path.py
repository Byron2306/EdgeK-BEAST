from pathlib import Path
p = Path('/home/byron/Hivenance/edgek_beast_gateway/edgek-beast/app/kernel/compute/compute_ledger.py')
print(p.resolve().parents[0])
print(p.resolve().parents[1])
print(p.resolve().parents[2])
