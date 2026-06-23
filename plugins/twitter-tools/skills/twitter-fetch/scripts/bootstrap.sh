#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="${SCRIPT_PATH%/*}"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_UV=0
INIT_RUNTIME=0
SYNC=0

usage() {
  printf '%s\n' \
    "Usage: bootstrap.sh [--check] [--init-runtime] [--sync] [--install-uv]" \
    "" \
    "Checks twitter-fetch runtime support. It does not install uv unless" \
    "--install-uv is passed explicitly."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      ;;
    --sync)
      SYNC=1
      ;;
    --init-runtime)
      INIT_RUNTIME=1
      ;;
    --install-uv)
      INSTALL_UV=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

RUNTIME_DIR="${TWITTER_FETCH_RUNTIME:-${HOME}/.twitter-fetch}"
COOKIE_EXAMPLE="${RUNTIME_DIR}/.cookies.example.json"
UV_PROJECT_ENVIRONMENT="${TWITTER_FETCH_VENV:-${RUNTIME_DIR}/venv}"
export UV_PROJECT_ENVIRONMENT

if [[ "${INIT_RUNTIME}" -eq 1 ]]; then
  mkdir -p "${RUNTIME_DIR}/cache" "${RUNTIME_DIR}/logs" "${RUNTIME_DIR}/tmp"
  if [[ ! -f "${COOKIE_EXAMPLE}" ]]; then
    printf '%s\n' \
      '{' \
      '  "auth_token": "",' \
      '  "ct0": ""' \
      '}' > "${COOKIE_EXAMPLE}"
    chmod 600 "${COOKIE_EXAMPLE}"
  fi
  echo "runtime: ${RUNTIME_DIR}"
  echo "runtime dirs: ok"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv: missing"
  if [[ "${INSTALL_UV}" -eq 0 ]]; then
    printf '%s\n' \
      "Install uv:" \
      "  curl -LsSf https://astral.sh/uv/install.sh | sh" \
      "" \
      "Or run:" \
      "  ${SKILL_DIR}/scripts/bootstrap.sh --install-uv"
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl: missing; cannot install uv" >&2
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "uv: $(uv --version)"
echo "project: ${SKILL_DIR}"

if [[ ! -f "${SKILL_DIR}/pyproject.toml" ]]; then
  echo "pyproject.toml: missing" >&2
  exit 1
fi
echo "pyproject.toml: ok"

COOKIE_PATH="${TWITTER_FETCH_COOKIES:-${RUNTIME_DIR}/.cookies.json}"
if [[ -f "${COOKIE_PATH}" ]]; then
  echo "cookies: ${COOKIE_PATH}"
else
  echo "cookies: missing (${COOKIE_PATH})"
fi

if [[ "${SYNC}" -eq 1 ]]; then
  uv sync --project "${SKILL_DIR}"
else
  echo "dependency sync: skipped (run with --sync)"
fi
