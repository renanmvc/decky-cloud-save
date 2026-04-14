import asyncio
from asyncio.subprocess import Process, create_subprocess_exec
import os
from pathlib import Path
import re
import decky_plugin
import plugin_config

_AUTH_URL_RE = re.compile(r"(https?://(?:127\.0\.0\.1|localhost):\d+/auth\?state=[^\s\"']+)")

async def _kill_previous_spawn(process: Process):
    """
    Kills the previous spawned process.

    Parameters:
    process (asyncio.subprocess.Process): The process to be killed.
    """
    if process and process.returncode is None:
        decky_plugin.logger.warn("Killing previous Process")
        
        process.kill()

        await asyncio.sleep(0.1)  # Give time for OS to clear up the port

def _is_port_in_use(port: int) -> bool:
    """
    Checks if a given port is in use.

    Parameters:
    port (int): The port number to check.

    Returns:
    bool: True if the port is in use, False otherwise.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0
    
async def _get_url_from_rclone_process(process: asyncio.subprocess.Process):
    """
    Extracts the URL from the stderr of the rclone process.

    Parameters:
    process (asyncio.subprocess.Process): The rclone process.

    Returns:
    str: The URL extracted from the process output.
    """
    streams = [stream for stream in (process.stdout, process.stderr) if stream]
    read_tasks: dict[asyncio.Task[bytes], asyncio.StreamReader] = {
        asyncio.create_task(stream.readline()): stream for stream in streams
    }
    last_lines: list[str] = []

    try:
        while read_tasks:
            done, _ = await asyncio.wait(read_tasks.keys(), return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                stream = read_tasks.pop(task)
                raw = task.result()

                if not raw:
                    continue

                line = raw.decode(errors="ignore").strip()
                if line:
                    last_lines.append(line)
                    last_lines = last_lines[-10:]

                url_re_match = _AUTH_URL_RE.search(line)
                if url_re_match:
                    return url_re_match.group(1)

                read_tasks[asyncio.create_task(stream.readline())] = stream
    finally:
        for pending_task in read_tasks:
            pending_task.cancel()

    recent_output = "\n".join(last_lines) if last_lines else "(no output)"
    raise Exception(f"RCLONE_AUTH_URL_NOT_FOUND\n{recent_output}")

class RcloneSetupManager:
    current_spawn: Process | None = None

    def _backend_exists(self, backend_name: str = "backend") -> bool:
        if not Path(plugin_config.rclone_cfg).is_file():
            return False

        try:
            with open(plugin_config.rclone_cfg, "r") as f:
                content = f.read()
                return f"[{backend_name}]" in content
        except Exception:
            return False

    async def spawn(self, backend_type: str):
        """
        Spawns a new rclone process with the specified backend type.

        Parameters:
        backend_type (str): The type of backend to use.

        Returns:
        str: The URL for authentication.
        """
        decky_plugin.logger.info("Updating rclone.conf")

        await _kill_previous_spawn(self.current_spawn)
        if _is_port_in_use(53682):
            raise Exception('RCLONE_PORT_IN_USE')

        # If the remote already exists, update it instead of create to avoid
        # failures that never print an OAuth URL.
        onedrive_args = ["drive_type", "personal", "drive_id", "me"] if backend_type == "onedrive" else []

        if self._backend_exists("backend"):
            # update syntax is: config update <name> <key value>...
            command_args = ["config", "update", "backend", "type", backend_type, "config_is_local", "true", *onedrive_args]
        else:
            # create syntax is: config create <name> <type> <key value>...
            command_args = ["config", "create", "backend", backend_type, "config_is_local", "true", *onedrive_args]

        self.current_spawn = await create_subprocess_exec(
            *plugin_config.rclone_command(*command_args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        url = await asyncio.wait_for(_get_url_from_rclone_process(self.current_spawn), timeout=45)
        decky_plugin.logger.info("Login URL: %s", url)

        return url
    
    async def probe(self):
        """
        Checks if the current rclone process is running.

        Returns:
        int: The return code of the rclone process.
        """
        if not self.current_spawn:
            return 0

        return self.current_spawn.returncode

    async def get_backend_type(self):
        """
        Retrieves the current backend type from the rclone configuration.

        Returns:
        str: The current backend type.
        """
        with open(plugin_config.rclone_cfg, "r") as f:
            l = f.readlines()
            return l[1]

    async def get_syncpaths(self, file: str):
        """
        Retrieves sync paths from the specified file.

        Parameters:
        file (str): The file from which to retrieve sync paths.

        Returns:
        list: A list of sync paths.
        """
        file = plugin_config.cfg_syncpath_excludes_file if file == "excludes" else plugin_config.cfg_syncpath_includes_file
        with open(file, "r") as f:
            return f.readlines()

    async def test_syncpath(self, path: str):
        """
        Tests a sync path to determine if it's a file or a directory.

        Parameters:
        path (str): The path to test.

        Returns:
        int | str: The number of files if it's a directory, '9000+' if it exceeds the limit, or 0 if it's a file.
        """
        if not path.startswith(plugin_config.get_config_item("sync_root", "/")):
            raise Exception("Selection is outside of sync root.")

        if path.endswith("/**"):
            scan_single_dir = False
            path = path[:-3]
        elif path.endswith("/*"):
            scan_single_dir = True
            path = path[:-2]
        else:
            return int(Path(path).is_file())

        count = 0
        for root, os_dirs, os_files in os.walk(path, followlinks=True):
            decky_plugin.logger.debug("%s %s %s", root, os_dirs, os_files)
            count += len(os_files)
            if count > 9000:
                return "9000+"
            if scan_single_dir:
                break

        return count

    async def add_syncpath(self, path: str, file: str):
        """
        Adds a sync path to the specified file.

        Parameters:
        path (str): The path to add.
        file (str): The file to add the path to.
        """
        decky_plugin.logger.info("Adding Path to Sync: '%s', %s", path, file)

        # Replace the beginning of path to replace the root.
        path = path.replace(plugin_config.get_config_item("sync_root", "/"), "/", 1)

        file = plugin_config.cfg_syncpath_excludes_file if file == "excludes" else plugin_config.cfg_syncpath_includes_file

        with open(file, "r") as f:
            lines = f.readlines()
        for line in lines:
            if line.strip("\n") == path:
                return
        lines += [f"{path}\n"]
        with open(file, "w") as f:
            for line in lines:
                f.write(line)

        plugin_config.regenerate_filter_file()

    async def remove_syncpath(self, path: str, file: str):
        """
        Removes a sync path from the specified file.

        Parameters:
        path (str): The path to remove.
        file (str): The file to remove the path from.
        """
        decky_plugin.logger.info("Removing Path from Sync: '%s', %s", path, file)

        file = plugin_config.cfg_syncpath_excludes_file if file == "excludes" else plugin_config.cfg_syncpath_includes_file
        with open(file, "r") as f:
            lines = f.readlines()
        with open(file, "w") as f:
            for line in lines:
                if line.strip("\n") != path:
                    f.write(line)

        plugin_config.regenerate_filter_file()

    def cleanup(self):
        """
        Cleans up the resources.
        """
        if self.current_spawn and self.current_spawn.returncode is None:
            self.current_spawn.kill()
