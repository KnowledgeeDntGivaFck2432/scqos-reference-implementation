#!/usr/bin/env bash
set +e
export AWS_PAGER=""
BUCKET="supremecomputation.org"
REGION="us-east-1"
DOMAIN="supremecomputation.org"
HERE="$(cd "$(dirname "$0")" && pwd)"
BACKUP="$HOME/supreme-site-before-premium-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
echo "=== BACKUP ==="
aws s3 sync "s3://$BUCKET" "$BACKUP" >/dev/null 2>&1
echo "=== DEPLOY ==="
aws s3 sync "$HERE" "s3://$BUCKET" --exclude "deploy.sh" --delete --cache-control "no-cache, no-store, must-revalidate" --region "$REGION"
echo "=== VERIFY ==="
FAIL=0
for p in "" build.html enterprise.html proof.html now.html learn.html style.css app.js assets/south-mountain.jpg assets/welcome-phoenix.jpg assets/phoenix-mural.jpg; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://$DOMAIN/$p")
  printf "%s  http://%s/%s\n" "$code" "$DOMAIN" "$p"
  [ "$code" = "200" ] || FAIL=1
done
if [ "$FAIL" = "0" ]; then
  echo "✅ DEPLOYED AND ALL ROUTES RETURN 200"
  echo "🌐 http://$DOMAIN"
  echo "🧾 Backup: $BACKUP"
else
  echo "❌ DEPLOYED BUT ONE OR MORE ROUTES FAILED — DO NOT CALL COMPLETE"
fi
