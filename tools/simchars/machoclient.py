"""
Macho-layer protocol client for sim characters.

Generalizes the session layer proven in tools/smoke-bot/aura_bot.py:
named-service calls, object binding, bound-object calls, notification
queue, session-change absorption. All packet shapes mirrored from live
client captures (tools/debug-listener/captures).

Wire shapes:
  service call : payload ((0, SubStream((1, method, args, kw))),)
                 dest = MachoAddress (8, serviceName, None)
  bind         : MachoBindObject((params...), call-or-None) on a service
                 rsp SubStruct SubStreams carry ('N=node:ref', timestamp)
  bound call   : payload ((1, SubStream((boundRef, method, args, kw))),)
                 dest = MachoAddress (1, nodeID, None, None)
"""

import os
import sys
import time

_SMOKE_BOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "smoke-bot")
if _SMOKE_BOT not in sys.path:
    sys.path.insert(0, _SMOKE_BOT)

import evemarshal                     # noqa: E402
from evemarshal import WStr, PyObj, SubStream, ObjectEx  # noqa: E402
import login as eve_login             # noqa: E402

NODE_ID = 888444  # EVEmu single-node id (proxy_nodeid 0xFFAA in handshake)


def log(msg):
    print(f"[simchar] {msg}", flush=True)


class CallError(RuntimeError):
    pass


class MachoClient:
    def __init__(self, host, port, user, password, verbose=False):
        self.verbose = verbose
        conn, info = eve_login.login(host, port, user, password,
                                     log=log if verbose else lambda m: None)
        self.conn = conn
        self.user_id = info.user_id
        self.call_id = 2
        self.notifications = []
        self.session = {}

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------- calls
    def call(self, service, method, *args, byname=None, timeout=30.0):
        dest = PyObj("macho.MachoAddress", (8, service, None))
        return self._call(dest, (0,), method, args, byname, timeout,
                          f"{service}.{method}")

    def call_bound(self, ref, method, *args, byname=None, timeout=30.0):
        dest = PyObj("macho.MachoAddress", (1, NODE_ID, None, None))
        return self._call(dest, (1,), method, args, byname, timeout,
                          f"{ref}.{method}", bound_ref=ref)

    def activate_module(self, dogma_ref, module_id, effect_name,
                        target_id=None, repeat=1000):
        """dogmaIM.Activate with the effect NAME sent as a WStr.

        COMP-C: the server's Activate dispatch only matches a WString for
        the effect name; a plain Python str silently matches no overload,
        the server logs an error, and the call still returns SUCCESS -- so
        the module never fires (this made combat bots shoot blanks).  Always
        route module activation through here.
        """
        return self.call_bound(dogma_ref, "Activate", int(module_id),
                               WStr(effect_name), target_id, int(repeat))

    def _call(self, dest, kind, method, args, byname, timeout, label,
              bound_ref=None):
        self.call_id += 1
        cid = self.call_id
        kw = {"machoVersion": 1}
        if byname:
            kw.update(byname)
        if bound_ref is None:
            inner = SubStream((1, method, tuple(args), kw))
        else:
            inner = SubStream((bound_ref, method, tuple(args), kw))
        req = PyObj("macho.CallReq", (
            6,
            PyObj("macho.MachoAddress", (2, 0, cid, None)),
            dest,
            self.user_id,
            ((kind[0], inner),),
            None, None,
        ))
        self.conn.send_rep(req)
        deadline = time.time() + timeout
        while time.time() < deadline:
            got = self._recv(remaining=deadline - time.time())
            if got is None:
                continue
            k, body = got
            if k == "callrsp" and body[0] == cid:
                return body[1]
            if k == "error" and body[0] == cid:
                raise CallError(f"{label} failed: {body[1]!r}")
        raise TimeoutError(f"no response to {label}")

    def bind(self, service, bind_params, call=None):
        """MachoBindObject; returns the bound-object ref string.

        `call` may be (method, args, kwargs) to piggyback a call; then
        returns (ref, call_result).
        """
        # bind params may be a tuple (locationID, groupID) or a bare int
        # (e.g. agent binds use just the agentID)
        bp = tuple(bind_params) if isinstance(bind_params, (tuple, list)) \
            else int(bind_params)
        arg = (bp,
               (call[0], tuple(call[1]), call[2]) if call else None)
        rsp = self.call(service, "MachoBindObject", *arg)
        refs = find_bound_refs(rsp)
        if not refs:
            raise CallError(f"no bound ref in MachoBindObject rsp: {rsp!r}")
        if call:
            return refs[0], rsp
        return refs[0]

    # --------------------------------------------------------- receiving
    def pump(self, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self._recv(remaining=deadline - time.time())

    def _recv(self, remaining=1.0):
        self.conn.sock.settimeout(max(0.1, min(remaining, 1.0)))
        try:
            rep = self.conn.recv_rep()
        except (TimeoutError, OSError):
            return None
        return self._classify(rep)

    def _classify(self, rep):
        if not isinstance(rep, PyObj):
            return ("other", rep)
        body, name = rep.state, rep.type_name
        if name == "macho.CallRsp" and isinstance(body, tuple):
            dst = body[2]
            cid = dst.state[2] if isinstance(dst, PyObj) else None
            return ("callrsp", (cid, body[4]))
        if name == "macho.ErrorResponse" and isinstance(body, tuple):
            dst = body[2]
            cid = dst.state[2] if isinstance(dst, PyObj) else None
            return ("error", (cid, body[4:]))
        if name == "macho.SessionChangeNotification":
            self._absorb_session(body)
            return ("session", body)
        if name == "macho.Notification":
            self.notifications.append(body)
            if self.verbose:
                log(f"NOTIFY {repr(body)[:300]}")
            return ("notify", body)
        if name == "macho.PingReq" and isinstance(body, tuple):
            try:
                self.conn.send_rep(
                    PyObj("macho.PingRsp", (21, body[2], body[1]) + body[3:]))
            except OSError:
                pass
            return ("ping", None)
        return ("other", rep)

    def _absorb_session(self, body):
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if (isinstance(k, str) and isinstance(v, tuple)
                            and len(v) == 2):
                        self.session[k] = v[1]
                    walk(v)
            elif isinstance(node, (tuple, list)):
                for el in node:
                    walk(el)
            elif isinstance(node, PyObj):
                walk(node.state)
            elif isinstance(node, SubStream):
                walk(node.obj)
            elif isinstance(node, ObjectEx):
                walk(node.header)
                walk(node.items)
                walk(node.kw)
        walk(body)

    # -------------------------------------------------------- world entry
    def enter_world(self, char_id, settle=3.0):
        self.call("charUnboundMgr", "SelectCharacterID", char_id, 0, None)
        self.pump(settle)
        return {k: self.session.get(k) for k in
                ("charid", "stationid", "solarsystemid2", "corpid",
                 "constellationid", "regionid")}


# ---------------------------------------------------------------- helpers

def find_bound_refs(tree):
    """Collect 'N=node:ref' strings from a bind/call response."""
    out = []

    def walk(node):
        if isinstance(node, str):
            if node.startswith("N=") and ":" in node:
                out.append(node)
        elif isinstance(node, (tuple, list)):
            for el in node:
                walk(el)
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, PyObj):
            walk(node.state)
        elif isinstance(node, SubStream):
            walk(node.obj)
        elif isinstance(node, ObjectEx):
            walk(node.header)
            walk(node.items)
            walk(node.kw)
    walk(tree)
    # de-dup preserving order
    seen, uniq = set(), []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq
