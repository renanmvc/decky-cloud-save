#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="${PLUGIN_DIR:-/home/deck/homebrew/plugins/decky-cloud-save}"
RCLONE_VERSION="${RCLONE_VERSION:-1.73.4}"

echo "Copying plugin files from ${WORKSPACE_DIR} to ${PLUGIN_DIR}"
mkdir -p "${PLUGIN_DIR}/bin" "${PLUGIN_DIR}/dist" "${PLUGIN_DIR}/py_modules" "${PLUGIN_DIR}/defaults"

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
		echo "Skipping ${dest}: destination is not writable (run: sudo chown -R deck:deck ${PLUGIN_DIR} && sudo chmod -R u+rwX,go+rX ${PLUGIN_DIR})"
	fi
}

copy_file_if_writable "${WORKSPACE_DIR}/main.py" "${PLUGIN_DIR}/main.py"
copy_file_if_writable "${WORKSPACE_DIR}/plugin.json" "${PLUGIN_DIR}/plugin.json"
copy_file_if_writable "${WORKSPACE_DIR}/package.json" "${PLUGIN_DIR}/package.json"
copy_file_if_writable "${WORKSPACE_DIR}/deck.json" "${PLUGIN_DIR}/deck.json"
copy_file_if_writable "${WORKSPACE_DIR}/backend/rcloneLauncher" "${PLUGIN_DIR}/bin/rcloneLauncher"

if [ -e "${PLUGIN_DIR}/bin/rcloneLauncher" ]; then
	chmod 0755 "${PLUGIN_DIR}/bin/rcloneLauncher"
fi

if [ -f "${WORKSPACE_DIR}/backend/openLastLog.sh" ]; then
	if [ -e "${PLUGIN_DIR}/openLastLog.sh" ] && [ -w "${PLUGIN_DIR}/openLastLog.sh" ]; then
		cat "${WORKSPACE_DIR}/backend/openLastLog.sh" > "${PLUGIN_DIR}/openLastLog.sh"
		chmod 0755 "${PLUGIN_DIR}/openLastLog.sh"
	elif [ ! -e "${PLUGIN_DIR}/openLastLog.sh" ]; then
		install -m 0755 "${WORKSPACE_DIR}/backend/openLastLog.sh" "${PLUGIN_DIR}/openLastLog.sh"
	else
		echo "Skipping ${PLUGIN_DIR}/openLastLog.sh: destination is not writable"
	fi
fi

ensure_rclone() {
	local arch
	local archive_name
	local download_url
	local tmp_dir

	if [ -x "${PLUGIN_DIR}/bin/rclone" ]; then
		return
	fi

	case "$(uname -m)" in
		x86_64)
			arch="amd64"
			;;
		aarch64|arm64)
			arch="arm64"
			;;
		*)
			echo "Unsupported architecture for automatic rclone download: $(uname -m)"
			return 1
			;;
	esac

	archive_name="rclone-v${RCLONE_VERSION}-linux-${arch}.zip"
	download_url="https://downloads.rclone.org/v${RCLONE_VERSION}/${archive_name}"
	tmp_dir="$(mktemp -d)"
	trap 'rm -rf "${tmp_dir}"' RETURN

	echo "rclone binary not found in ${PLUGIN_DIR}/bin, downloading ${archive_name}"
	if command -v curl >/dev/null 2>&1; then
		curl -fsSL "${download_url}" -o "${tmp_dir}/${archive_name}"
	elif command -v wget >/dev/null 2>&1; then
		wget -qO "${tmp_dir}/${archive_name}" "${download_url}"
	else
		echo "Neither curl nor wget is available to download rclone"
		return 1
	fi

	bsdtar -xf "${tmp_dir}/${archive_name}" -C "${tmp_dir}"
	install -m 0755 "${tmp_dir}/rclone-v${RCLONE_VERSION}-linux-${arch}/rclone" "${PLUGIN_DIR}/bin/rclone"
}

ensure_rclone

echo "Local plugin copy complete"