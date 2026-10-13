#!/usr/bin/env sh
# Runs every attack against a started stand (run_stand.sh). Exit code 1 if anything failed.
cd "$(dirname "$0")"
export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8
status=0

python setup_accounts.py >/dev/null || exit 1
for script in attack_studio.py attack_photos.py attack_roles.py attack_billing.py; do
  echo "== $script"
  python "$script" > .last.log 2>&1 || status=1
  grep -v '^PASS' .last.log
done

python -c "from common import png; open('hero.png', 'wb').write(png((800, 1000), (70, 90, 160), 'HERO'))"
docker exec presenton-e2e mkdir -p /tmp/e2e
for file in ui_e2e.cjs billing_ui.cjs mobile.cjs anon.cjs accounts.json hero.png; do
  docker cp "$file" "presenton-e2e:/tmp/e2e/$file" >/dev/null
done
for script in ui_e2e.cjs billing_ui.cjs mobile.cjs anon.cjs; do
  echo "== $script (headless Chromium inside the stand)"
  docker exec -w /tmp/e2e -e NODE_PATH=/app/presentation-export/node_modules presenton-e2e node "$script" > .last.log 2>&1 || status=1
  grep -v '^PASS' .last.log
done
[ "$status" = "0" ] && echo "ALL PASSED" || echo "SOME CHECKS FAILED"
exit $status
