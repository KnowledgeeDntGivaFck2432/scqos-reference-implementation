import json, re, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE/"supreme_mind_manifest.json").read_text())

def words(s):
    return set(re.findall(r"[a-z0-9_]+", str(s).lower()))

def resolve(objective, state=None):
    objective = (objective or "").strip()
    state = state or {}

    if not objective:
        return {
            "state":"REJECT",
            "reason":"OBJECTIVE_MISSING",
            "roles":[],
            "objective_sha256":None
        }

    ow = words(objective)
    scored=[]

    for r in MANIFEST["roles"]:
        corpus = " ".join([
            r.get("name",""),
            r.get("faculty",""),
            r.get("function",""),
            r.get("domain","")
        ])
        rw=words(corpus)
        score=len(ow & rw)

        # semantic anchors for the organization's present objective.
        domain=r.get("domain","").lower()
        faculty=r.get("faculty","").lower()
        function=r.get("function","").lower()
        text=(objective+" "+json.dumps(state)).lower()

        anchors={
          "financial":("finance","financial","bank","banking","account","payment",
                       "transaction","treasury","gekyume","capital","revenue"),
          "market":("customer","market","traction","adoption","demand","company",
                    "companies","prospect"),
          "relationships":("partner","partnership","relationship","stakeholder",
                           "investor","connector"),
          "social":("publish","marketing","social","content","audience"),
          "product":("website","site","app","api","product","demo"),
          "institutional_memory":("receipt","evidence","history","record","proof"),
          "governance":("govern","permit","hold","reject","authority","policy")
        }

        for key, terms in anchors.items():
            if any(t in text for t in terms):
                if key in domain or key in faculty or key in function:
                    score += 5

        if score:
            scored.append((score,r))

    scored.sort(key=lambda x:(-x[0],x[1]["role_id"]))

    # Tiger law: smallest sufficient composition.
    if not scored:
        return {
          "state":"HOLD",
          "reason":"NO_PROGRESSIVE_ROLE_MATCH",
          "roles":[],
          "objective_sha256":hashlib.sha256(objective.encode()).hexdigest()
        }

    top=scored[0][0]
    selected=[
        r for score,r in scored
        if score >= max(1, top-2)
    ][:8]

    return {
      "state":"PERMIT",
      "reason":"MINIMUM_CAUSAL_COMPOSITION",
      "objective":objective,
      "objective_sha256":hashlib.sha256(objective.encode()).hexdigest(),
      "roles":[{
        "role_id":r["role_id"],
        "name":r["name"],
        "faculty":r["faculty"],
        "domain":r["domain"],
        "function":r["function"],
        "autonomy":r["autonomy"]
      } for r in selected]
    }

if __name__=="__main__":
    import sys
    objective=" ".join(sys.argv[1:])
    print(json.dumps(resolve(objective),indent=2))
