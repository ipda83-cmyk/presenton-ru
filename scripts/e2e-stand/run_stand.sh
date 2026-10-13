#!/usr/bin/env sh
# E2E stand: Presenton on 127.0.0.1:5057 with sign-in on, talking to fake upstreams
# (OpenAI-compatible LLM and the arckep image API, 127.0.0.1:9056). Nothing is paid for.
# Needs a built frontend (servers/nextjs/.next-build) and the presenton image.
set -e
HERE=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))
ROOT=$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))
DATA=${E2E_APP_DATA:-"$HERE/.appdata"}
IMAGE=${PRESENTON_IMAGE:-ghcr.io/presenton/presenton:latest}
export MSYS_NO_PATHCONV=1

mkdir -p "$DATA"
docker network create presenton-e2e >/dev/null 2>&1 || true
docker rm -f presenton-e2e-fake presenton-e2e >/dev/null 2>&1 || true

docker run -d --name presenton-e2e-fake --network presenton-e2e -p 127.0.0.1:9056:9000 \
  -v "$HERE:/e2e" --entrypoint /opt/venv/bin/python "$IMAGE" /e2e/fake_upstream.py >/dev/null

docker run -d --name presenton-e2e --network presenton-e2e -p 127.0.0.1:5057:80 \
  -v "$ROOT/servers/fastapi:/app/servers/fastapi" \
  -v "$ROOT/servers/nextjs/.next-build/standalone:/app/servers/nextjs" \
  -v "$ROOT/servers/nextjs/.next-build/static:/app/servers/nextjs/.next-build/static" \
  -v "$ROOT/servers/nextjs/public:/app/servers/nextjs/public" \
  -v "$DATA:/app_data" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e LLM=custom -e CUSTOM_LLM_URL=http://presenton-e2e-fake:9000/v1 -e CUSTOM_MODEL=fake-model -e CUSTOM_LLM_API_KEY=e2e-test \
  -e STUDIO_API_KEY=e2e-test -e STUDIO_BASE_URL=http://presenton-e2e-fake:9000/api/v1 \
  -e DISABLE_IMAGE_GENERATION=true -e WEB_GROUNDING=false \
  "$IMAGE" >/dev/null

printf "waiting for the stand"
for _ in $(seq 1 60); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5057/api/v1/auth/status)" = "200" ]; then
    echo " - up: http://127.0.0.1:5057"
    exit 0
  fi
  printf "."
  sleep 3
done
echo " - did not start; see: docker logs presenton-e2e"
exit 1
