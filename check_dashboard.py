from internal.beast_economy_dashboard import build_dashboard
import json

report = build_dashboard()
print(json.dumps(report, indent=2))
