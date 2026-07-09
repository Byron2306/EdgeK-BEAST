from app.kernel.compute.compute_ledger import ComputeLedger

ledger = ComputeLedger()
try:
    metrics = ledger.metrics(limit=500)
    print(metrics)
except Exception as e:
    print(f"Error: {e}")
