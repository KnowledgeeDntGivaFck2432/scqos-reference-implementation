#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STACK="${SCQOS_STACK_NAME:-scqos-public-execution-challenge-v1}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

for tool in aws python3 zip curl; do command -v "$tool" >/dev/null || { echo "Missing required command: $tool" >&2; exit 2; }; done
IDENTITY="$(aws sts get-caller-identity --region "$REGION" --output json)"
ACCOUNT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["Account"])' <<<"$IDENTITY")"
COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
BUCKET="scqos-public-challenge-${ACCOUNT}-${REGION}"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

cp "$HERE/runtime.py" "$HERE/contract.json" "$HERE/index.html" "$ROOT/scqos_supreme_stack.py" "$BUILD/"
python3 -m pip install --quiet --disable-pip-version-check --target "$BUILD" 'rfc8785==0.1.4'
SCQOS_TEST_MODE=1 PYTHONPATH="$BUILD:$ROOT" python3 "$HERE/test_runtime.py"
(cd "$BUILD" && zip -qr function.zip . -x 'function.zip')
ZIP_SHA="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$BUILD/function.zip")"
KEY="releases/${COMMIT}/${ZIP_SHA}.zip"

if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  if [[ "$REGION" == "us-east-1" ]]; then aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  else aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null; fi
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null
fi
aws s3 cp "$BUILD/function.zip" "s3://${BUCKET}/${KEY}" --only-show-errors
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" --template-file "$HERE/cloudformation.yaml" --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset --parameter-overrides "ArtifactBucket=$BUCKET" "ArtifactKey=$KEY" "SourceCommit=$COMMIT"
URL="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query 'Stacks[0].Outputs[?OutputKey==`PublicUrl`].OutputValue' --output text)"
curl -fsS "${URL}v1/health" | python3 -m json.tool
curl -fsS -X POST -H 'content-type: application/json' -d '{}' "${URL}v1/run-matrix" | tee "$BUILD/matrix.json" | python3 -m json.tool
python3 - "$BUILD/matrix.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["all_pass"] and x["passed"] == x["total"] == 6, x
PY
echo "PUBLIC_CHALLENGE_URL=$URL"
