"""
EVEmu login handshake (Crucible v1.6.5 build 360229).

Sequence (EVESession.cpp state machine + Client.cpp verify handlers):

  server -> VersionExchangeServer   tuple(birthday, macho, users,
                                          version, build, project, None)
  client -> VersionExchangeClient   tuple(birthday, macho, users,
                                          version, build, project)
  client -> NetCommand_VK           (None, "VK", vipKey)   [any key accepted]
  client -> CryptoRequestPacket     ("placebo", {})
  server -> "OK CC"
  client -> CryptoChallengePacket   (clientChallenge, {boot info + creds})
  server -> PyInt(2)                              [password-version notice]
  server -> CryptoServerHandshake   tuple(...)    [or GPSTransportClosed]
  client -> CryptoHandshakeResult   (challenge_responsehash,
                                     func_output, func_result)
  server -> CryptoHandshakeAck      dict(live_updates, session_init)
  ... then macho PyPacket mode (session change notification follows)

Auth uses the plain-password path (Client::_VerifyLogin) — non-empty
user_password compares against the account table directly, and accounts
are auto-created when sConfig.account.autoAccountRole > 0.
"""

from dataclasses import dataclass, field

import evemarshal
from evemarshal import WStr, ObjectEx, SubStream
from netclient import EVEConnection

# EVEVersion.h
EVE_BIRTHDAY = 170472
MACHONET_VERSION = 320
EVE_VERSION_NUMBER = 7.31
EVE_BUILD_VERSION = 360229
EVE_PROJECT_VERSION = "EVE-EVE-TRANQUILITY@ccp"
EVE_PROJECT_CODENAME = "EVE-EVE-TRANQUILITY"
EVE_PROJECT_REGION = "ccp"


class LoginError(Exception):
    pass


class LoginRefused(LoginError):
    """Server refused credentials (GPSTransportClosed)."""


@dataclass
class SessionInfo:
    user_id: int = 0
    client_id: int = 0
    role: int = 0
    cluster_usercount: int = 0
    live_update_count: int = 0
    raw_ack: dict = field(default_factory=dict)


def _is_exception(rep) -> bool:
    return isinstance(rep, ObjectEx)


def _exception_text(rep) -> str:
    # GPSTransportClosed reason lives in the header tree; render it whole.
    return repr(rep)


def login(host: str, port: int, username: str, password: str,
          timeout: float = 15.0, log=print) -> tuple:
    """Perform the full login handshake. Returns (conn, SessionInfo).

    The returned connection is live and in PyPacket mode; caller owns it.
    """
    conn = EVEConnection(host, port, timeout=timeout)
    try:
        info = _login(conn, username, password, log)
        return conn, info
    except BaseException:
        conn.close()
        raise


def _login(conn: EVEConnection, username: str, password: str,
           log) -> SessionInfo:
    info = SessionInfo()

    # 1. VersionExchangeServer
    ve = conn.recv_rep()
    if not (isinstance(ve, tuple) and len(ve) == 7):
        raise LoginError(f"unexpected version exchange: {ve!r}")
    log(f"[<-] version exchange: build {ve[4]}, {ve[2]} users online")
    if ve[4] != EVE_BUILD_VERSION:
        log(f"[!!] server build {ve[4]} != expected {EVE_BUILD_VERSION}")

    # 2. VersionExchangeClient (echo our pinned identity)
    conn.send_rep((EVE_BIRTHDAY, MACHONET_VERSION, ve[2],
                   EVE_VERSION_NUMBER, EVE_BUILD_VERSION,
                   EVE_PROJECT_VERSION))

    # 3. NetCommand_VK — any vipKey accepted (Client::_VerifyVIPKey)
    conn.send_rep((None, "VK", "smoke-bot"))

    # 4. Placebo crypto request -> "OK CC"
    conn.send_rep(("placebo", {}))
    ok = conn.recv_rep()
    if ok != "OK CC":
        raise LoginError(f"crypto request refused: {ok!r}")
    log("[<-] crypto: OK CC")

    # 5. CryptoChallengePacket. Plain-password path: user_password set,
    #    user_password_hash empty (Client::_VerifyLogin).
    challenge = (
        "",  # clientChallenge (none_marker="")
        {
            "macho_version": MACHONET_VERSION,
            "boot_version": EVE_VERSION_NUMBER,
            "boot_build": EVE_BUILD_VERSION,
            "boot_codename": EVE_PROJECT_CODENAME,
            "boot_region": EVE_PROJECT_REGION,
            "user_name": WStr(username),
            "user_password": WStr(password),
            "user_password_hash": "",
            "user_languageid": WStr("EN"),
            "user_affiliateid": 0,
        },
    )
    conn.send_rep(challenge)

    # Server sends PyInt(2) (password-version notice), then either the
    # CryptoServerHandshake tuple or a GPSTransportClosed exception.
    rep = conn.recv_rep()
    if rep == 2 or rep == 1:
        rep = conn.recv_rep()
    if _is_exception(rep):
        raise LoginRefused(_exception_text(rep))
    if not isinstance(rep, tuple):
        raise LoginError(f"unexpected handshake response: {rep!r}")
    shake_meta = rep[3] if len(rep) >= 4 and isinstance(rep[3], dict) else {}
    info.cluster_usercount = shake_meta.get("cluster_usercount", 0)
    log(f"[<-] server handshake: cluster users "
        f"{info.cluster_usercount}, queue pos "
        f"{shake_meta.get('user_logonqueueposition')}")

    # 6. CryptoHandshakeResult. Server ignores contents
    #    (Client::_VerifyFuncResult just decodes and acks).
    conn.send_rep(("55087", "", None))

    # 7. CryptoHandshakeAck: dict with live_updates + session_init
    ack = conn.recv_rep()
    if _is_exception(ack):
        raise LoginRefused(_exception_text(ack))
    if not isinstance(ack, dict):
        raise LoginError(f"unexpected handshake ack: {ack!r}")
    session_init = ack.get("session_init", {}) or {}
    info.user_id = session_init.get("userid", 0)
    # user_clientid sits in the outer ack dict (CryptoHandshakeAck XML)
    info.client_id = ack.get("user_clientid",
                             session_init.get("user_clientid", 0))
    info.role = session_init.get("role", 0)
    updates = ack.get("live_updates", [])
    info.live_update_count = len(updates) if isinstance(updates, list) else 0
    info.raw_ack = ack
    log(f"[<-] handshake ack: userid={info.user_id} "
        f"clientid={info.client_id} role=0x{info.role:X} "
        f"live_updates={info.live_update_count}")
    return info
