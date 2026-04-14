#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="${PLUGIN_DIR:-/home/deck/homebrew/plugins/decky-cloud-save}"

echo "Copying plugin files from ${WORKSPACE_DIR} to ${PLUGIN_DIR}"
mkdir -p "${PLUGIN_DIR}/dist" "${PLUGIN_DIR}/py_modules" "${PLUGIN_DIR}/defaults"

rsync -a --delete "${WORKSPACE_DIR}/dist/" "${PLUGIN_DIR}/dist/"
rsync -a --delete "${WORKSPACE_DIR}/py_modules/" "${PLUGIN_DIR}/py_modules/"
rsync -a --delete "${WORKSPACE_DIR}/defaults/" "${PLUGIN_DIR}/defaults/"

copy_file_if_writable() {
	local src="$1"
	local dest="$2"

	if [ -e "${dest}" ] && [ -w "${dest}" ]; then
		cat "${src}" > "${dest}"
	elif [ ! -e "${dest}" ]; then
		install -m 0644 "${src}" "${dest}"
	else
		echo "Skipping ${dest}: destination is not writable"
	fi
}

copy_file_if_writable "${WORKSPACE_DIR}/main.py" "${PLUGIN_DIR}/main.py"
copy_file_if_writable "${WORKSPACE_DIR}/plugin.json" "${PLUGIN_DIR}/plugin.json"
copy_file_if_writable "${WORKSPACE_DIR}/deck.json" "${PLUGIN_DIR}/deck.json"

if [ -f "${WORKSPACE_DIR}/openLastLog.sh" ]; then
	if [ -e "${PLUGIN_DIR}/openLastLog.sh" ] && [ -w "${PLUGIN_DIR}/openLastLog.sh" ]; then
		cat "${WORKSPACE_DIR}/openLastLog.sh" > "${PLUGIN_DIR}/openLastLog.sh"
		chmod 0755 "${PLUGIN_DIR}/openLastLog.sh"
	elif [ ! -e "${PLUGIN_DIR}/openLastLog.sh" ]; then
		install -m 0755 "${WORKSPACE_DIR}/openLastLog.sh" "${PLUGIN_DIR}/openLastLog.sh"
	else
		echo "Skipping ${PLUGIN_DIR}/openLastLog.sh: destination is not writable"
	fi
fi

echo "Local plugin copy complete"