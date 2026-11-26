"""API for Proxmox Extended Sensors."""

from typing import Any, Optional
import asyncio
import logging
import requests
import time
from urllib.parse import urlencode
from proxmoxer import ProxmoxAPI
from proxmoxer.backends.https import ProxmoxHTTPAuth, ProxmoxHTTPAuthBase
from proxmoxer.core import AuthenticationError as ProxmoxerAuthenticationError

from .tls import CertificateNotPinned, is_fingerprint_mismatch, pin_session

LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when the API rejects the supplied credentials."""


class CannotConnect(Exception):
    """Raised when the API cannot be reached."""


SIDECAR_PORT = 9000
API_TIMEOUT = 30  # seconds per Proxmox API request


class SidecarAuthError(Exception):
    """The sidecar rejected the token (HTTP 401/403)."""


class SidecarCertificateError(Exception):
    """The sidecar no longer presents its pinned certificate.

    Deliberately not an AuthenticationError: the Proxmox API itself is fine,
    so this must not start the entry's reauth flow.
    """


class CertificateMismatchError(AuthenticationError):
    """The server no longer presents the pinned certificate.

    Subclasses AuthenticationError so setup raises ConfigEntryAuthFailed and
    Home Assistant offers the reauth flow, where the new certificate can be
    reviewed and accepted.
    """


class _TicketRejected(ProxmoxerAuthenticationError):
    """The /access/ticket login failed with this HTTP status."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _PinnedPasswordAuth(ProxmoxHTTPAuth):
    """proxmoxer password auth whose ticket requests go through a pinned session.

    proxmoxer's own ProxmoxHTTPAuth posts the password with a bare
    requests.post(), which no session adapter can pin, so the ticket request
    is reimplemented here on a session supplied by ProxmoxClient.
    """

    def __init__(self, username, password, base_url, session_factory, timeout):
        ProxmoxHTTPAuthBase.__init__(self, timeout=timeout, service="PVE", verify_ssl=False)
        self.base_url = base_url
        self.username = username
        self.pve_auth_ticket = ""
        self._session_factory = session_factory
        self._get_new_tokens(password=password)

    def _get_new_tokens(self, password=None, otp=None, otptype=None):
        if password is None:
            password = self.pve_auth_ticket
        with self._session_factory() as session:
            response = session.post(
                self.base_url + "/access/ticket",
                data={"username": self.username, "password": password},
                timeout=self.timeout,
            )
        if response.status_code != 200:
            raise _TicketRejected(
                f"Couldn't authenticate user: {self.username} code: {response.status_code}",
                response.status_code,
            )
        data = response.json()["data"]
        if data.get("NeedTFA") is not None:
            raise ProxmoxerAuthenticationError(
                "Two-factor authentication is not supported; use an API token"
            )
        self.birth_time = time.monotonic()
        self.pve_auth_ticket = data["ticket"]
        self.csrf_prevention_token = data["CSRFPreventionToken"]


class PermissionError(Exception):
    """Raised when credentials are valid but permissions are insufficient."""


def _raise_for_auth_or_permission(status_code: int | None, path: str) -> None:
    """Map only auth/permission statuses; other HTTP errors are not network errors."""
    if status_code == 401:
        raise AuthenticationError(f"Authentication failed for {path}")
    if status_code == 403:
        raise PermissionError(f"Permission denied for {path}")


def _extract_status_code(err: Exception) -> int | None:
    response = getattr(err, "response", None)
    if response is not None and getattr(response, "status_code", None):
        return response.status_code

    status_code = getattr(err, "status_code", None) or getattr(err, "status", None)
    if status_code:
        return int(status_code)

    # proxmoxer's own password login raises this with no status attached;
    # it only ever means the credentials (or 2FA) were refused.
    if isinstance(err, ProxmoxerAuthenticationError):
        return 401

    # No substring matching on str(err): any message that merely contains
    # "401" or "403" (a VMID, a port, a byte count) would read as an auth
    # failure and start a reauth flow.
    return None


class ProxmoxClient:
    def __init__(
        self,
        host: str,
        user: str,
        password: Optional[str] = None,
        token_id: Optional[str] = None,
        token_secret: Optional[str] = None,
        server_type: str = "PVE",
        port: Optional[int] = None,
        verify_ssl: bool = True,
        cert_fingerprint: Optional[str] = None,
        sidecar_token: Optional[str] = None,
        sidecar_fingerprint: Optional[str] = None,
    ):
        self._host = host
        self._user = user
        self._password = password
        self._token_id = token_id
        self._token_secret = token_secret
        self._server_type = server_type
        self._port = port
        self._verify_ssl = verify_ssl
        self._cert_fingerprint = cert_fingerprint
        self._sidecar_token = sidecar_token
        self._sidecar_fingerprint = sidecar_fingerprint
        # Result of the latest sidecar response: None (secure), "insecure"
        # (legacy plain HTTP), "certificate_changed" or "auth_failed".
        self.sidecar_problem: str | None = None
        self._proxmox: Optional[ProxmoxAPI] = None
        self._build_error: Exception | None = None
        # Set once a pinned certificate mismatch is seen; the coordinators turn
        # it into ConfigEntryAuthFailed so the user is asked to review it.
        self.certificate_mismatch = False

    def _new_session(self) -> requests.Session:
        """A requests session that verifies TLS one way or the other, never neither."""
        session = requests.Session()
        if self._verify_ssl:
            session.verify = True
            return session
        if not self._cert_fingerprint:
            session.close()
            raise CertificateNotPinned(
                f"Certificate verification is off for {self._host} and no "
                "certificate fingerprint has been confirmed"
            )
        return pin_session(session, self._cert_fingerprint)

    def _tls_error(self, err: BaseException) -> CertificateMismatchError | None:
        if not is_fingerprint_mismatch(err):
            return None
        self.certificate_mismatch = True
        return CertificateMismatchError(
            f"The certificate presented by {self._host} does not match the pinned fingerprint"
        )

    def _build_client_sync(self):
        if self._server_type in ("PBS", "PDM"):
            return
        self._build_error = None
        try:
            self._proxmox = self._new_proxmox_api(self._port or 8006, API_TIMEOUT)
        except Exception as err:
            self._build_error = self._tls_error(err) or err
            LOGGER.error(
                "Failed to initialize Proxmoxer client on %s: %s",
                self._host, self._build_error,
            )
            self._proxmox = None

    def _new_proxmox_api(self, port: int, timeout: int) -> ProxmoxAPI:
        """A ProxmoxAPI for the configured sign-in, pinned when verification is off."""
        pinned = not self._verify_ssl
        if pinned and not self._cert_fingerprint:
            raise CertificateNotPinned(
                f"Refusing to connect to {self._host}: certificate verification "
                "is off and no certificate fingerprint has been confirmed"
            )
        if self._token_id and self._token_secret:
            api = ProxmoxAPI(
                self._host,
                user=self._user,
                token_name=self._token_id,
                token_value=self._token_secret,
                verify_ssl=self._verify_ssl,
                port=port,
                timeout=timeout,
            )
        elif pinned:
            api = self._pinned_password_api(port, timeout)
        else:
            api = ProxmoxAPI(
                self._host,
                user=self._user,
                password=self._password,
                verify_ssl=True,
                port=port,
                timeout=timeout,
            )
        if pinned:
            pin_session(api._store["session"], self._cert_fingerprint)
        return api

    def _pinned_password_api(self, port: int, timeout: int) -> ProxmoxAPI:
        """Password sign-in whose ticket request goes through the pinned session."""
        # Token auth makes no request at construction; the placeholder
        # is replaced with pinned password auth before any request.
        api = ProxmoxAPI(
            self._host,
            user=self._user,
            token_name="pinned-login-placeholder",
            token_value="unused",
            verify_ssl=False,
            port=port,
            timeout=timeout,
        )
        auth = _PinnedPasswordAuth(
            self._user,
            self._password,
            base_url=api._store["base_url"],
            session_factory=self._new_session,
            timeout=timeout,
        )
        api._backend.auth = auth
        api._store["session"].auth = auth
        return api

    async def get_api_client(self, hass):
        if self._server_type in ("PBS", "PDM"):
            return None

        if self._proxmox is None:
            await hass.async_add_executor_job(self._build_client_sync)

        return self._proxmox

    async def get(self, hass, path: str, raise_errors: bool = False) -> Any:
        if self._server_type == "PBS":
            return await hass.async_add_executor_job(
                self._pbs_request, "GET", path, None, raise_errors
            )
        if self._server_type == "PDM":
            return await hass.async_add_executor_job(
                self._pdm_request, "GET", path, None, raise_errors
            )

        proxmox = await self.get_api_client(hass)
        if proxmox is None:
            if raise_errors:
                self._raise_build_error(path)
            return None

        try:
            return await hass.async_add_executor_job(proxmox.get, path)

        except Exception as err:
            if mismatch := self._tls_error(err):
                if raise_errors:
                    raise mismatch from err
                LOGGER.error("%s", mismatch)
                return None
            if raise_errors:
                status_code = _extract_status_code(err)
                if status_code is not None:
                    _raise_for_auth_or_permission(status_code, path)
                    raise CannotConnect(
                        f"PVE HTTP {status_code} while requesting {path}"
                    ) from err

                if isinstance(err, requests.exceptions.RequestException):
                    raise CannotConnect(f"PVE request failed for {path}") from err

                raise

            # Connection failures are expected when a node is powered off.
            if isinstance(
                err,
                (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ConnectTimeout,
                    requests.exceptions.Timeout,
                ),
            ):
                LOGGER.debug("PVE node unreachable while requesting %s: %s", path, err)
                return None

            status_code = _extract_status_code(err)
            if status_code == 403 and path.endswith("/apt/update"):
                LOGGER.debug(
                    "PVE update check unavailable due to missing Sys.Modify permission: %s",
                    path,
                )
                return None

            LOGGER.error("PVE GET error on %s: %s", path, err)
            return None

    def _raise_build_error(self, path: str) -> None:
        err = self._build_error
        if isinstance(err, (CertificateMismatchError, CertificateNotPinned)):
            raise err
        status_code = _extract_status_code(err) if err is not None else None
        if status_code is not None:
            _raise_for_auth_or_permission(status_code, path)
        raise CannotConnect(f"Unable to initialize client for {path}") from err

    async def post(self, hass, path: str, data=None) -> Any:
        if self._server_type == "PDM":
            return None
        proxmox = await self.get_api_client(hass)
        if proxmox is None:
            return None

        def _do_post():
            return proxmox.post(path, **(data or {}))

        try:
            return await hass.async_add_executor_job(_do_post)
        except Exception as err:
            LOGGER.error("PVE POST error on %s: %s", path, self._tls_error(err) or err)
            return None

    async def get_cluster_resources(self, hass, raise_errors: bool = False):
        return await self.get(
            hass, "cluster/resources", raise_errors=raise_errors
        ) or []

    async def get_cluster_replication(self, hass) -> list:
        """Return replication configuration, preserving empty success vs failure."""
        data = await self.get(hass, "cluster/replication", raise_errors=True)
        if not isinstance(data, list):
            raise ValueError("Invalid cluster replication response: expected a list")
        return data

    async def get_node_replication(self, hass, node: str) -> list:
        """Return a complete runtime snapshot; an empty list is a success."""
        data = await self.get(hass, f"nodes/{node}/replication", raise_errors=True)
        if not isinstance(data, list):
            raise ValueError("Invalid node replication response: expected a list")
        return data

    async def get_cluster_tasks(self, hass, raise_errors: bool = False):
        return await self.get(
            hass, "cluster/tasks", raise_errors=raise_errors
        ) or []

    async def get_running_node_tasks(self, hass, node: str) -> list:
        data = await self.get(
            hass, f"nodes/{node}/tasks?source=active", raise_errors=True
        )
        if not isinstance(data, list) or not all(
            isinstance(task, dict) for task in data
        ):
            raise ValueError("Invalid running node tasks response: expected a list")
        return data

    async def wait_for_task(self, hass, upid: str, timeout: float = 3600, poll_interval: float = 2):
        """Wait for a Proxmox task identified by its exact UPID."""
        if not isinstance(upid, str) or not upid.strip():
            raise ValueError("Invalid task UPID")
        deadline = time.monotonic() + timeout
        while True:
            tasks = await self.get_cluster_tasks(hass, raise_errors=True) or []
            for task in tasks:
                if isinstance(task, dict) and task.get("upid") == upid:
                    if task.get("endtime") is not None:
                        return task
                    break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for task {upid}")
            await asyncio.sleep(min(poll_interval, remaining))

    async def get_backup_jobs(self, hass, raise_errors: bool = False):
        return await self.get(
            hass, "cluster/backup", raise_errors=raise_errors
        ) or []

    async def get_nodes(self, hass):
        """Return nodes in cluster."""
        data = await self.get(hass, "nodes")
        return data or []

    async def get_node_ip(self, hass, node):
        """Get primary IPv4 of a node"""
        net = await self.get_node_network(hass, node)

        for iface in net or []:
            addr = iface.get("address")

            if addr and not addr.startswith("127.") and ":" not in addr:
                return addr

        return None

    async def get_node_status(self, hass, node: str):
        return await self.get(hass, f"nodes/{node}/status")

    async def get_node_updates(self, hass, node: str):
        return await self.get(hass, f"nodes/{node}/apt/update")

    async def get_node_network(self, hass, node: str):
        return await self.get(hass, f"nodes/{node}/network") or []

    async def get_vms(self, hass, node: str, raise_errors: bool = False):
        return (
            await self.get(
                hass, f"nodes/{node}/qemu", raise_errors=raise_errors
            )
            or []
        )

    async def get_containers(self, hass, node: str, raise_errors: bool = False):
        return (
            await self.get(
                hass, f"nodes/{node}/lxc", raise_errors=raise_errors
            )
            or []
        )

    async def get_vm_config(self, hass, node: str, vmid):
        """Fetch a VM's config (includes 'onboot'); not present in the list
        endpoint, so this is a separate, per-guest call."""
        return await self.get(hass, f"nodes/{node}/qemu/{vmid}/config") or {}

    async def get_vm_fsinfo(self, hass, node: str, vmid) -> list:
        """Return QEMU Guest Agent filesystem information for one VM."""
        data = await self.get(
            hass,
            f"nodes/{node}/qemu/{vmid}/agent/get-fsinfo",
            raise_errors=True,
        )
        if isinstance(data, dict) and isinstance(data.get("result"), list):
            data = data["result"]
        if not isinstance(data, list):
            raise ValueError("Invalid Guest Agent get-fsinfo response: expected a list")
        return data

    async def get_ct_config(self, hass, node: str, vmid):
        """Fetch a CT's config (includes 'onboot'); not present in the list
        endpoint, so this is a separate, per-guest call."""
        return await self.get(hass, f"nodes/{node}/lxc/{vmid}/config") or {}

    async def get_container_status(self, hass, node: str, vmid: str):
        return await self.get(hass, f"nodes/{node}/lxc/{vmid}/status/current")

    async def get_qemu_status(self, hass, node: str, vmid: str):
        return await self.get(hass, f"nodes/{node}/qemu/{vmid}/status/current")

    async def get_lxc_status(self, hass, node: str, vmid: str):
        return await self.get(hass, f"nodes/{node}/lxc/{vmid}/status/current")

    async def get_vm_type(self, hass, node: str, vmid: str) -> str:
        vms = await self.get_vms(hass, node)
        if isinstance(vms, list):
            for vm in vms:
                if str(vm.get("vmid")) == str(vmid):
                    return "qemu"

        containers = await self.get_containers(hass, node)
        if isinstance(containers, list):
            for ct in containers:
                if str(ct.get("vmid")) == str(vmid):
                    return "lxc"

        return "unknown"

    async def get_vm_status(self, hass, node: str, vmid: str):
        vmtype = await self.get_vm_type(hass, node, vmid)
        if vmtype == "qemu":
            return await self.get_qemu_status(hass, node, vmid)
        if vmtype == "lxc":
            return await self.get_lxc_status(hass, node, vmid)
        return None

    async def get_storages(self, hass, node: str, raise_errors: bool = False):
        return (
            await self.get(
                hass, f"nodes/{node}/storage", raise_errors=raise_errors
            )
            or []
        )

    async def get_disks(self, hass, node: str, raise_errors: bool = False):
        # skipsmart=1: without it PVE runs `smartctl -H` on every disk for each
        # call, which wakes spun down HDDs on every poll. The health/wearout
        # fields it adds are not used; SMART comes from get_smart_data_http.
        disks = await self.get(
            hass, f"nodes/{node}/disks/list?skipsmart=1",
            raise_errors=raise_errors,
        )
        if (not isinstance(disks, list)
                or any(not isinstance(disk, dict)
                       or not isinstance(disk.get("devpath"), str)
                       or not disk["devpath"].startswith("/dev/")
                       for disk in disks)
                or len({disk["devpath"] for disk in disks}) != len(disks)):
            if raise_errors:
                raise ValueError("PVE disk inventory is malformed")
            return []
        return disks

    async def control_vm(self, hass, node: str, vmid: str, command: str):
        valid_vm_commands = [
            "start",
            "stop",
            "shutdown",
            "reboot",
            "reset",
            "suspend",
            "resume",
            "hibernate",
            "pause",
        ]
        if command not in valid_vm_commands:
            LOGGER.error(f"Invalid VM command: {command}")
            return False

        if command == "hibernate":
            path = f"nodes/{node}/qemu/{vmid}/status/suspend"
            data = {"todisk": 1}
        elif command == "pause":
            path = f"nodes/{node}/qemu/{vmid}/status/suspend"
            data = {}
        else:
            path = f"nodes/{node}/qemu/{vmid}/status/{command}"
            data = {}

        if command in ["shutdown", "reboot"]:
            data["timeout"] = 60

        result = await self.post(hass, path, data)

        return result

    async def execute_vm_command(self, hass, node: str, vmid: str, command: str):
        return await self.control_vm(hass, node, vmid, command)

    async def execute_ct_command(self, hass, node: str, vmid: str, command: str):
        return await self.control_container(hass, node, vmid, command)

    async def execute_node_command(self, hass, node: str, command: str):
        if command == "reboot":
            return await self.reboot_node(hass, node)
        elif command == "shutdown":
            return await self.shutdown_node(hass, node)
        else:
            LOGGER.error(f"Invalid node command: {command}")
            return False

    async def control_container(self, hass, node: str, vmid: str, command: str):
        valid_ct_commands = ["start", "stop", "shutdown", "reboot"]
        if command not in valid_ct_commands:
            LOGGER.error(
                f"Invalid CT command: {command}. Valid commands: {valid_ct_commands}"
            )
            return False

        path = f"nodes/{node}/lxc/{vmid}/status/{command}"
        data = {}

        if command in ["shutdown", "reboot"]:
            data["timeout"] = 60

        result = await self.post(hass, path, data)

        return result

    async def shutdown_node(self, hass, node: str):
        path = f"nodes/{node}/status"
        data = {"command": "shutdown"}
        return await self.post(hass, path, data)

    async def reboot_node(self, hass, node: str):
        path = f"nodes/{node}/status"
        data = {"command": "reboot"}
        return await self.post(hass, path, data)

    # ----- hardware sidecar (pve-sensors-api.py on the node, port 9000) -----

    def _sidecar_fetch(self, endpoint: str, timeout: float):
        """GET one sidecar endpoint and return the decoded JSON (raises on failure).

        With a sidecar token configured the request goes over HTTPS to the
        pinned sidecar certificate and carries the token; nothing is sent if
        the certificate differs. Without a token the sidecar is in its legacy
        plain-HTTP mode, which ``sidecar_problem`` reports as "insecure".
        """
        if not self._sidecar_token:
            response = requests.get(
                f"http://{self._host}:{SIDECAR_PORT}{endpoint}", timeout=timeout
            )
            response.raise_for_status()
            payload = response.json()
            self.sidecar_problem = "insecure"
            return payload
        if not self._sidecar_fingerprint:
            raise CertificateNotPinned("The sidecar token is set but no certificate is pinned")
        with pin_session(requests.Session(), self._sidecar_fingerprint) as session:
            try:
                response = session.get(
                    f"https://{self._host}:{SIDECAR_PORT}{endpoint}",
                    timeout=timeout,
                    headers={"Authorization": f"Bearer {self._sidecar_token}"},
                )
            except requests.exceptions.SSLError as err:
                if is_fingerprint_mismatch(err):
                    self.sidecar_problem = "certificate_changed"
                    raise SidecarCertificateError(
                        f"The sidecar on {self._host} presented a different certificate"
                    ) from err
                raise
        if response.status_code in (401, 403):
            self.sidecar_problem = "auth_failed"
            raise SidecarAuthError(f"The sidecar on {self._host} rejected the request")
        response.raise_for_status()
        payload = response.json()
        self.sidecar_problem = None
        return payload

    async def _sidecar_get(self, hass, endpoint, timeout, raise_errors, fallback,
                           validate=None):
        def _fetch():
            try:
                payload = self._sidecar_fetch(endpoint, timeout)
                if validate is not None and not validate(payload):
                    raise ValueError(f"Invalid sidecar response from {endpoint}")
                return payload
            except Exception:
                if raise_errors:
                    raise
                return fallback() if callable(fallback) else fallback

        return await hass.async_add_executor_job(_fetch)

    async def check_sidecar(self, hass):
        """Validate the sidecar settings against /health; raises on any failure."""
        return await hass.async_add_executor_job(self._sidecar_fetch, "/health", 10)

    async def get_lm_sensors_http(
        self, hass, node: str, raise_errors: bool = False
    ):
        return await self._sidecar_get(hass, "/sensors", 5, raise_errors, dict)

    async def get_smart_data_http(
        self, hass, node: str, raise_errors: bool = False
    ):
        return await self._sidecar_get(hass, "/smart", 15, raise_errors, dict)

    async def get_smart_disk_http(
        self, hass, node: str, path: str, protect: bool, raise_errors: bool = False
    ):
        query = urlencode({"path": path, "protect": int(protect)})
        return await self._sidecar_get(
            hass, f"/smart-disk?{query}", 9, raise_errors, lambda: {"status": "error"},
            validate=lambda payload: isinstance(payload, dict) and payload.get("status") in (
                "ok", "standby", "unsupported", "error"
            ),
        )

    async def get_memory_http(self, hass, node: str, raise_errors: bool = False):
        return await self._sidecar_get(hass, "/memory", 15, raise_errors, dict)

    async def get_ksm_http(self, hass, node: str, raise_errors: bool = False):
        """Get the sidecar's fixed KSM snapshot."""
        return await self._sidecar_get(hass, "/ksm", 5, raise_errors, dict)

    async def get_mounts(self, hass, node, raise_errors: bool = False):
        return await self._sidecar_get(hass, "/mounts", 15, raise_errors, dict)

    async def get_zfs_pools(self, hass, node, raise_errors: bool = False):
        return (
            await self.get(
                hass, f"nodes/{node}/disks/zfs", raise_errors=raise_errors
            )
            or []
        )

    async def start_vzdump(
        self,
        hass,
        node: str,
        vmid: str,
        storage: str,
        notes: str = None,
        mode: str = "snapshot",
        compress: str = "zstd",
    ):
        if not node or not vmid or not storage:
            raise ValueError("node, vmid, and storage are required to start a backup")

        path = f"nodes/{node}/vzdump"
        if compress == "none":
            compress = "0"

        valid_modes = ["snapshot", "suspend", "stop"]
        if mode not in valid_modes:
            raise ValueError(
                f"Invalid mode: {mode}. Must be one of: {', '.join(valid_modes)}"
            )

        valid_compress = ["0", "1", "lzo", "gzip", "zstd", "none"]
        if compress not in valid_compress:
            raise ValueError(
                f"Invalid compression: {compress}. Must be one of: {', '.join(valid_compress)}"
            )

        data = {
            "vmid": vmid,
            "storage": storage,
            "mode": mode,
            "compress": compress,
        }

        if notes:
            data["notes-template"] = notes

        result = await self.post(hass, path, data)

        return result

    async def get_cluster_status(self, hass, raise_errors: bool = False):
        """Return cluster status (name, quorum, version)."""
        data = await self.get(
            hass, "cluster/status", raise_errors=raise_errors
        ) or []
        # The API returns a list; extract the item with type=="cluster"
        for item in data:
            if isinstance(item, dict) and item.get("type") == "cluster":
                return item
        return {}

    async def get_cluster_ha_status(self, hass, raise_errors: bool = False):
        """Return current HA manager status."""
        return await self.get(
            hass, "cluster/ha/status/current", raise_errors=raise_errors
        ) or {}

    async def get_cluster_firewall_options(self, hass, raise_errors: bool = False):
        """Return cluster firewall options."""
        return await self.get(
            hass, "cluster/firewall/options", raise_errors=raise_errors
        ) or {}

    async def get_cluster_qdevice(self, hass, raise_errors: bool = False):
        """Return the Corosync QDevice configuration and status."""
        data = await self.get(
            hass, "cluster/config/qdevice", raise_errors=raise_errors
        )
        if not isinstance(data, dict):
            raise ValueError("Invalid QDevice response: expected a mapping")
        return data

    def _pdm_request(
        self, method: str, path: str, data=None, raise_errors: bool = False
    ):
        if method != "GET":
            if raise_errors:
                raise ValueError("The PDM client is read-only")
            return None
        port = self._port or 8443
        clean_host = (
            self._host.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split(":")[0]
        )
        url = f"https://{clean_host}:{port}/api2/json/{path}"
        if not self._user or not self._token_id or not self._token_secret:
            if raise_errors:
                raise AuthenticationError("PDM token authentication is incomplete")
            return None
        token_full = (
            self._token_id
            if "!" in self._token_id
            else f"{self._user}!{self._token_id}"
        )
        headers = {
            "Authorization": f"PDMAPIToken {token_full}:{self._token_secret}",
            "Accept": "application/json",
        }
        try:
            with self._new_session() as session:
                response = session.get(url, headers=headers, timeout=15)
            if response.status_code >= 400:
                if raise_errors:
                    _raise_for_auth_or_permission(response.status_code, path)
                    raise CannotConnect(
                        f"PDM HTTP {response.status_code} while requesting {path}"
                    )
                return None
            payload = response.json()
            if not isinstance(payload, dict) or "data" not in payload:
                raise ValueError("Invalid PDM API response envelope")
            return payload["data"]
        except CertificateNotPinned as err:
            if raise_errors:
                raise
            LOGGER.error("%s", err)
            return None
        except (AuthenticationError, PermissionError, CannotConnect):
            raise
        except requests.exceptions.RequestException as err:
            if mismatch := self._tls_error(err):
                if raise_errors:
                    raise mismatch from err
                return None
            if raise_errors:
                raise CannotConnect(f"PDM request failed for {path}") from err
            return None
        except Exception:
            if raise_errors:
                raise
            return None

    async def get_pdm_version(self, hass):
        data = await self.get(hass, "version", raise_errors=True)
        if not isinstance(data, dict):
            raise ValueError("Invalid PDM version response")
        return data

    async def get_pdm_remotes(self, hass):
        from .logic.pdm import validate_pdm_remote_inventory

        return validate_pdm_remote_inventory(
            await self.get(hass, "remotes/remote", raise_errors=True)
        )

    async def get_pdm_resources(self, hass):
        from .logic.pdm import validate_pdm_resource_groups

        return validate_pdm_resource_groups(
            await self.get(hass, "resources/list", raise_errors=True)
        )

    async def get_pdm_status(self, hass):
        from .logic.pdm import validate_pdm_status

        return validate_pdm_status(
            await self.get(hass, "resources/status", raise_errors=True)
        )

    async def get_pdm_subscriptions(self, hass):
        from .logic.pdm import validate_pdm_subscriptions

        return validate_pdm_subscriptions(
            await self.get(hass, "resources/subscription", raise_errors=True)
        )

    async def get_pdm_updates(self, hass):
        from .logic.pdm import validate_pdm_updates_envelope

        return validate_pdm_updates_envelope(
            await self.get(hass, "remotes/updates/summary", raise_errors=True)
        )

    def _pbs_request(
        self, method: str, path: str, data=None, raise_errors: bool = False
    ):
        port = self._port or 8007

        clean_host = (
            self._host.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split(":")[0]
        )
        url = f"https://{clean_host}:{port}/api2/json/{path}"

        if not self._user or not self._token_secret:
            LOGGER.error("PBS token authentication requires user and token_secret")
            if raise_errors:
                raise AuthenticationError("PBS token authentication is incomplete")
            return None

        if self._token_id:
            if "!" in self._token_id:
                token_full = self._token_id
            else:
                token_full = f"{self._user}!{self._token_id}"
        else:
            LOGGER.error("PBS token_id is missing")
            if raise_errors:
                raise AuthenticationError("PBS token_id is missing")
            return None

        auth_header = f"PBSAPIToken {token_full}:{self._token_secret}"
        headers = {"Authorization": auth_header, "Accept": "application/json"}

        try:
            with self._new_session() as session:
                if method == "GET":
                    r = session.get(url, headers=headers, timeout=15)
                else:
                    r = session.post(url, headers=headers, json=(data or {}), timeout=15)

            if method == "GET" and path == "nodes/localhost/identity" and r.status_code == 404:
                LOGGER.debug("PBS instance identity endpoint unavailable on %s", clean_host)
                return None

            if raise_errors and r.status_code >= 400:
                _raise_for_auth_or_permission(r.status_code, path)
                raise CannotConnect(
                    f"PBS HTTP {r.status_code} while requesting {path}"
                )

            if r.status_code == 403:
                return None

            if r.status_code >= 400:
                LOGGER.error("PBS HTTP %s on %s: %s", r.status_code, path, r.text)
                return None

            return r.json().get("data")

        except CertificateNotPinned as err:
            if raise_errors:
                raise
            LOGGER.error("%s", err)
            return None
        except (AuthenticationError, PermissionError, CannotConnect):
            raise
        except requests.exceptions.RequestException as err:
            if mismatch := self._tls_error(err):
                if raise_errors:
                    raise mismatch from err
                LOGGER.error("%s", mismatch)
                return None
            if raise_errors:
                raise CannotConnect(f"PBS request failed for {path}") from err
            return None
        except Exception as err:
            if raise_errors:
                LOGGER.debug(
                    "PBS validation endpoint %s failed with %s: %s",
                    path,
                    type(err).__name__,
                    err,
                )
                raise
            return None

    async def pbs_get(self, hass, path: str, raise_errors: bool = False) -> Any:
        return await hass.async_add_executor_job(
            self._pbs_request, "GET", path, None, raise_errors
        )

    async def pbs_post(self, hass, path: str, data=None) -> Any:
        return await hass.async_add_executor_job(
            self._pbs_request, "POST", path, data or {}
        )

    async def get_pbs_datastores(self, hass, raise_errors: bool = False):
        data = await self.pbs_get(hass, "admin/datastore", raise_errors=raise_errors)
        return (
            [d["store"] for d in data if isinstance(d, dict) and "store" in d]
            if data
            else []
        )

    async def get_pbs_hostname(self, hass):
        """Get PBS hostname from status endpoint."""
        data = await self.pbs_get(hass, "status")

        if isinstance(data, dict):
            return data.get("hostname")

        return None

    async def get_pbs_instance_id(self, hass, raise_errors: bool = False):
        """Get stable PBS instance identity when supported by the server."""
        data = await self.pbs_get(
            hass, "nodes/localhost/identity", raise_errors=raise_errors
        )

        if isinstance(data, dict):
            return data.get("pbs-instance-id") or data.get("pbs_instance_id")

        return None

    async def get_pbs_datastore_status(
        self, hass, store: str, raise_errors: bool = False
    ):
        return (
            await self.pbs_get(
                hass, f"admin/datastore/{store}/status", raise_errors=raise_errors
            )
            or {}
        )

    async def get_pbs_datastore_usage(
        self, hass, store: str, raise_errors: bool = False
    ):
        return (
            await self.pbs_get(
                hass, f"admin/datastore/{store}/gc", raise_errors=raise_errors
            )
            or {}
        )

    async def get_pbs_tasks(self, hass, raise_errors: bool = False):
        tasks = await self.pbs_get(
            hass, "nodes/localhost/tasks", raise_errors=raise_errors
        )
        if raise_errors and (
            not isinstance(tasks, list)
            or not all(isinstance(task, dict) for task in tasks)
        ):
            raise ValueError("Invalid PBS tasks response: expected a list")
        return tasks or []

    async def get_pbs_prune_jobs(self, hass, raise_errors: bool = False):
        """Get configured PBS prune jobs."""
        return await self.pbs_get(hass, "admin/prune", raise_errors=raise_errors) or []

    async def get_pbs_verify_jobs(self, hass, raise_errors: bool = False):
        """Get configured PBS verify jobs."""
        return await self.pbs_get(hass, "admin/verify", raise_errors=raise_errors) or []

    async def get_pbs_sync_jobs(self, hass, raise_errors: bool = False):
        """Get configured PBS sync jobs."""
        return await self.pbs_get(hass, "admin/sync", raise_errors=raise_errors) or []

    async def get_pbs_version(self, hass, raise_errors: bool = False):
        return await self.pbs_get(hass, "version", raise_errors=raise_errors) or {}

    async def _get_pbs_snapshots_with_namespaces(
        self, hass, store: str, raise_errors: bool = False
    ):
        """Return root and visible namespace snapshots for one datastore."""
        snapshots = await self.pbs_get(
            hass, f"admin/datastore/{store}/snapshots", raise_errors=raise_errors
        ) or []

        if not isinstance(snapshots, list):
            return snapshots

        namespace_path = (
            f"admin/datastore/{store}/namespace?"
            f"{urlencode({'max-depth': 7})}"
        )
        try:
            namespaces = await self.pbs_get(hass, namespace_path, raise_errors=True)
        except AuthenticationError:
            raise
        except Exception as err:
            LOGGER.warning("PBS namespaces unavailable for datastore %s: %s", store, err)
            return snapshots

        if not isinstance(namespaces, list):
            return snapshots

        merged = list(snapshots)
        for namespace_item in namespaces:
            namespace = (
                namespace_item.get("ns")
                if isinstance(namespace_item, dict)
                else namespace_item
            )
            if not isinstance(namespace, str) or not namespace:
                continue

            snapshot_path = (
                f"admin/datastore/{store}/snapshots?{urlencode({'ns': namespace})}"
            )
            try:
                namespace_snapshots = await self.pbs_get(
                    hass, snapshot_path, raise_errors=True
                ) or []
            except AuthenticationError:
                raise
            except Exception as err:
                LOGGER.warning(
                    "PBS namespace snapshots unavailable for datastore %s namespace %s: %s",
                    store,
                    namespace,
                    err,
                )
                continue

            if not isinstance(namespace_snapshots, list):
                continue
            for snapshot in namespace_snapshots:
                if isinstance(snapshot, dict):
                    snapshot = dict(snapshot)
                    snapshot.setdefault("namespace", namespace)
                merged.append(snapshot)

        return merged

    async def get_pbs_backup_list(
        self, hass, store: str, raise_errors: bool = False
    ):
        return await self._get_pbs_snapshots_with_namespaces(
            hass, store, raise_errors=raise_errors
        )

    async def get_pbs_node_status(self, hass, raise_errors: bool = False):
        return (
            await self.pbs_get(
                hass, "nodes/localhost/status", raise_errors=raise_errors
            )
            or {}
        )

    async def get_pbs_gc(self, hass, store: str, raise_errors: bool = False):
        return (
            await self.pbs_get(
                hass, f"admin/datastore/{store}/gc", raise_errors=raise_errors
            )
            or {}
        )

    async def get_pbs_snapshots(self, hass, store: str, raise_errors: bool = False):
        return await self._get_pbs_snapshots_with_namespaces(
            hass, store, raise_errors=raise_errors
        )

    async def execute_pbs_node_command(self, hass, node, command):
        """Execute a command on PBS node (shutdown/reboot)."""
        try:
            path = f"nodes/{node}/status"
            data = {"command": command}

            await hass.async_add_executor_job(
                self._pbs_request, "POST", path, data, True
            )
            return True
        except Exception as e:
            LOGGER.error(
                "Error executing PBS node command %s on %s: %s: %s",
                command, node, type(e).__name__, e,
            )
            return False
