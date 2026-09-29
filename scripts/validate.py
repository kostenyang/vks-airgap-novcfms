import json, sys, time
sys.path.insert(0, "vks-airgap/scripts")
from installer_api import Api, flatten_errors
api = Api(); spec = json.load(open("vks-airgap/scripts/sddc-spec-3host.json"))
s, r = api.req("/v1/sddcs/validations", "POST", spec)
print("POST", s, r.get("id") if isinstance(r, dict) else r); vid = r["id"]
while True:
    time.sleep(20); s, r = api.req(f"/v1/sddcs/validations/{vid}")
    if r.get("executionStatus") != "IN_PROGRESS": break
print("execution:", r.get("executionStatus"), "result:", r.get("resultStatus"))
for c in r.get("validationChecks", []):
    print(f"  {c['description']:48} {c['resultStatus']}")
    for m in flatten_errors(c.get("errorResponse"))[:6]: print(f"       - {m[:220]}")
json.dump(r, open(f"vks-airgap/logs/03-validation-{vid[:8]}.json", "w"), indent=1)
