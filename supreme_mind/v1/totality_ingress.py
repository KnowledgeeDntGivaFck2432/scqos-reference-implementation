import json, os, boto3
from totality_resolver import resolve

lambda_client=boto3.client("lambda")

HERE=os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE,"supreme_mind_manifest.json"),"r") as f:
    MANIFEST=json.load(f)

GOVERNOR=os.environ.get(
    "SUPREME_MIND_GOVERNOR",
    "supreme-mind-v1-governor"
)

preferred=("analyze","research","read","search","draft")
READ_ACTION=next(
    (x for x in preferred if x in MANIFEST.get("read_only_actions",[])),
    MANIFEST["read_only_actions"][0]
)

def _body(event):
    if isinstance(event,dict) and isinstance(event.get("body"),str):
        try:
            return json.loads(event["body"])
        except Exception:
            return {}
    return event if isinstance(event,dict) else {}

def lambda_handler(event,context):
    body=_body(event)
    objective=str(body.get("objective","")).strip()

    plan=resolve(objective, body.get("state") or {})

    if plan["state"]!="PERMIT":
        return {
          "statusCode":200,
          "headers":{
            "content-type":"application/json",
            "access-control-allow-origin":"https://supremecomputation.org"
          },
          "body":json.dumps(plan)
        }

    receipts=[]

    # Each selected faculty enters the EXISTING governor.
    # The resolver itself never bypasses SCQOS.
    for role in plan["roles"]:
        governed={
          "business_id":"supremecomputation.org",
          "principal_id":"SOVEREIGN_HUMAN",
          "role_id":role["role_id"],
          "intent":objective,

          # Initial organizational cognition is read-only.
          # Real mutations remain governed by registered tool contracts.
          "action":READ_ACTION,
          "arguments":{
            "objective":objective,
            "totality_plan":plan
          },
          "evidence_refs":[
            "supreme_mind/v1/supreme_mind_manifest.json",
            "supreme_mind/v1/tool_adapter_contract.json"
          ]
        }

        res=lambda_client.invoke(
          FunctionName=GOVERNOR,
          InvocationType="RequestResponse",
          Payload=json.dumps(governed).encode()
        )

        raw=res["Payload"].read()
        try:
            receipts.append(json.loads(raw))
        except Exception:
            receipts.append({"raw":raw.decode(errors="replace")})

    return {
      "statusCode":200,
      "headers":{
        "content-type":"application/json",
        "access-control-allow-origin":"https://supremecomputation.org"
      },
      "body":json.dumps({
        "organization":"SupremeComputation.org",
        "state":"PERMIT",
        "plan":plan,
        "governor_receipts":receipts
      })
    }
