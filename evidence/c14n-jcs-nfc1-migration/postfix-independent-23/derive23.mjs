import fs from "node:fs";
import crypto from "node:crypto";

function rejectInvalidUnicode(s, path) {
  for (let i = 0; i < s.length; i++) {
    const a = s.charCodeAt(i);

    if (a >= 0xD800 && a <= 0xDBFF) {
      if (i + 1 >= s.length)
        throw new Error(`${path}: INVALID_UNICODE`);

      const b = s.charCodeAt(i + 1);
      if (!(b >= 0xDC00 && b <= 0xDFFF))
        throw new Error(`${path}: INVALID_UNICODE`);

      i++;
    } else if (a >= 0xDC00 && a <= 0xDFFF) {
      throw new Error(`${path}: INVALID_UNICODE`);
    }
  }
}

function normalize(v, path="payload") {
  if (v === null || typeof v === "boolean")
    return v;

  if (typeof v === "number") {
    if (!Number.isFinite(v))
      throw new Error(`${path}: NON_FINITE_REJECTED`);

    if (Object.is(v, -0))
      throw new Error(`${path}: NEGATIVE_ZERO_REJECTED`);

    return v;
  }

  if (typeof v === "string") {
    rejectInvalidUnicode(v, path);
    const n = v.normalize("NFC");
    rejectInvalidUnicode(n, path);
    return n;
  }

  if (Array.isArray(v))
    return v.map((x,i) => normalize(x, `${path}[${i}]`));

  if (typeof v === "object") {
    const map = new Map();

    for (const original of Object.keys(v)) {
      rejectInvalidUnicode(original, `${path}.<key>`);

      const key = original.normalize("NFC");

      if (map.has(key) && map.get(key).original !== original)
        throw new Error(`${path}: NFC_PROPERTY_NAME_COLLISION`);

      map.set(key, {
        original,
        value: normalize(v[original], `${path}.${key}`)
      });
    }

    return {
      __scqos_object__: true,
      entries: [...map.entries()]
        .sort((a,b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)
        .map(([k,x]) => [k,x.value])
    };
  }

  throw new Error(`${path}: UNSUPPORTED_TYPE`);
}

function serializeNormalized(v) {
  if (
    v !== null &&
    typeof v === "object" &&
    v.__scqos_object__ === true
  ) {
    return "{" + v.entries.map(
      ([k,x]) => JSON.stringify(k) + ":" + serializeNormalized(x)
    ).join(",") + "}";
  }

  if (Array.isArray(v))
    return "[" + v.map(serializeNormalized).join(",") + "]";

  return JSON.stringify(v);
}

function canonical(v) {
  return serializeNormalized(normalize(v));
}

function digest(canonicalText) {
  return "sha256:" +
    crypto.createHash("sha256")
      .update(Buffer.from(canonicalText, "utf8"))
      .digest("hex");
}

function vector(id, description, descriptor, builder) {
  try {
    const c = canonical(builder());

    return {
      id,
      description,
      input_descriptor: descriptor,
      status: "ACCEPT",
      canonical: c,
      digest: digest(c)
    };
  } catch (e) {
    return {
      id,
      description,
      input_descriptor: descriptor,
      status: "REJECT",
      reason: e.message
    };
  }
}

/*
 EXACTLY 23 vectors.
*/
const definitions = [
  ["B01","NFC string","nfc-string",()=>({k:"é"})],
  ["B02","NFD string folds to NFC","nfd-string",()=>({k:"e\u0301"})],
  ["B03","NFC property name","nfc-key",()=>({"é":1})],
  ["B04","NFD property name folds to NFC","nfd-key",()=>({"e\u0301":1})],
  ["B05","NFC property collision rejects","nfc-collision",()=>({"é":1,"e\u0301":2})],
  ["B06","Negative zero rejects","negative-zero",()=>({z:-0})],
  ["B07","Positive zero accepts","positive-zero",()=>({z:0})],
  ["B08","Integer one","integer-one",()=>({n:1})],
  ["B09","Float-source one converges","float-one",()=>({n:1.0})],
  ["B10","RFC number 333333333.3333333","num-333",()=>({n:333333333.3333333})],
  ["B11","RFC number 1e30","num-1e30",()=>({n:1e30})],
  ["B12","RFC number 4.5","num-4.5",()=>({n:4.5})],
  ["B13","RFC number 0.002","num-.002",()=>({n:0.002})],
  ["B14","RFC number 1e-27","num-1e-27",()=>({n:1e-27})],
  ["B15","Exponent formatting 1e-7","num-1e-7",()=>({n:1e-7})],
  ["B16","UTF-16 key ordering","utf16-order",()=>({"\uFF3A":1,"\u{1F600}":2})],
  ["B17","Array order preserved","array",()=>({a:[3,2,1]})],
  ["B18","Nested recursive object","nested",()=>({z:3,a:{z:2,a:1},b:[{y:2,x:1}]})],
  ["B19","JSON literals","literals",()=>({n:null,t:true,f:false})],
  ["B20","String escaping","escaping",()=>({s:"quote:\" slash:\\ newline:\n"})],
  ["B21","Invalid Unicode rejects","invalid-unicode",()=>({s:"\uD800"})],
  ["B22","NaN rejects","nan",()=>({n:NaN})],
  ["B23","Positive infinity rejects","infinity",()=>({n:Infinity})]
];

if (definitions.length !== 23)
  throw new Error(`VECTOR_COUNT=${definitions.length}`);

const results = {};

for (const [id,desc,input,builder] of definitions)
  results[id] = vector(id,desc,input,builder);

/*
 RFC 8785 numeric anchors.
*/
const anchors = {
  B10: '{"n":333333333.3333333}',
  B11: '{"n":1e+30}',
  B12: '{"n":4.5}',
  B13: '{"n":0.002}',
  B14: '{"n":1e-27}'
};

for (const [id, expected] of Object.entries(anchors)) {
  if (results[id].canonical !== expected) {
    throw new Error(
      `RFC8785_NUMERIC_ANCHOR_FAILURE ${id}: ` +
      `${results[id].canonical} != ${expected}`
    );
  }
}

const artifact = {
  artifact_id:
    "SCQOS-C14N-JCS-NFC-1-POSTFIX-CROSS-SUBSTRATE-23",

  artifact_class:
    "post-fix cross-substrate conformance oracle",

  normative_basis: [
    "SCQOS-C14N-JCS-NFC-1",
    "RFC 8785",
    "Unicode UAX #15 NFC",
    "FIPS 180-4 SHA-256"
  ],

  oracle_language: "JavaScript",
  oracle_runtime: process.version,
  reference_implementation_imported: false,

  vector_count: definitions.length,

  historical_boundary:
    "Created after implementation repair; does not replace Nikolai Nedovodin's earlier pre-registered artifact.",

  vectors: results
};

const raw = JSON.stringify(artifact,null,2) + "\n";

fs.writeFileSync(
  "evidence/c14n-jcs-nfc1-migration/postfix-independent-23/derived-23.json",
  raw
);

const hash = crypto.createHash("sha256")
  .update(Buffer.from(raw))
  .digest("hex");

fs.writeFileSync(
  "evidence/c14n-jcs-nfc1-migration/postfix-independent-23/derived-23.sha256",
  `${hash}  derived-23.json\n`
);

console.log("✅ EXACT VECTOR COUNT:", definitions.length);
console.log("✅ ARTIFACT FROZEN");
console.log("✅ ARTIFACT SHA-256:", hash);
