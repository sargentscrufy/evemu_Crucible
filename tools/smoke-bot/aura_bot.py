#!/usr/bin/env python3
"""
Aura Vasanen — proof-of-concept NPC player character.

Logs into EVEmu as a real protocol client, ensures her character exists
(Civire Mercs, Science and Trade Institute), enters the world, joins a
Local channel, and chats: incoming Local messages are answered by a
local ollama model (default `caldari-captain`).

Packet shapes are mirrored from live client captures
(tools/debug-listener/captures), e.g.:

  PyObj('macho.CallReq', (6,
      PyObj('macho.MachoAddress', (2, 0, <callID>, None)),   # client src
      PyObj('macho.MachoAddress', (8, '<service>', None)),   # dest by name
      <userid>,
      ((0, SubStream((1, '<method>', <args>, {'machoVersion': 1}))),),
      None, None))

Usage:
    python aura_bot.py [--host 127.0.0.1] [--port 26000]
                       [--user aura] [--password aura]
                       [--channel-system 30001392]
                       [--model caldari-captain] [--debug]

This is a demo, not the bot framework: one connection, one character,
one channel, best-effort parsing. See plan.md Phase 3 for the real one.
"""

import argparse
import json
import os
import time
import urllib.request

# GetCharactersToSelect returns a PackedRow rowset whose fixed fields this
# demo does not unpack, so we remember our character's ID here instead of
# re-parsing it each run (avoids a name-collision recreate on restart).
CHAR_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "aura_char.json")

import evemarshal
from evemarshal import WStr, Token, PyObj, SubStream, ObjectEx
import login as eve_login


# The server's CharacterAppearance/Portrait Build() read every doll field
# with no null checks (an empty doll segfaults the server), so we must send
# a fully-populated, valid doll. Values are cosmetic; structure is not.

def _keyval(d):
    return PyObj("util.KeyVal", d)


def _appearance_objectex(hair_darkness=0.5):
    # PyObjectEx_Type2::GetArgs() = header[0]; Build reads args[1] as float.
    args = (Token("_"), float(hair_darkness))
    return ObjectEx(True, (args, {}), items=[], kw={})


def character_info():
    # colors/modifiers/sculpts iterate ObjectEx entries — empty lists are
    # fine; appearance is dereferenced directly and must be a Type2 ObjectEx.
    return _keyval({
        "colors": [],
        "appearance": _appearance_objectex(),
        "modifiers": [],
        "sculpts": [],
    })


def portrait_info():
    pose_floats = [
        "BrowLeftCurl", "BrowLeftUpDown", "BrowLeftTighten",
        "BrowRightCurl", "BrowRightUpDown", "BrowRightTighten",
        "SquintLeft", "SmileLeft", "FrownLeft",
        "SquintRight", "SmileRight", "FrownRight",
        "JawUp", "JawSideways", "HeadTilt", "EyeClose",
        "EyesLookHorizontal", "EyesLookVertical",
        "OrientChar", "PortraitPoseNumber", "PuckerLips",
    ]
    pose = {k: 0.0 for k in pose_floats}
    pose["HeadLookTarget"] = (0.0, 0.0, 1.0)
    return _keyval({
        "backgroundID": 0,
        "lightColorID": 0,
        "lightID": 0,
        "cameraFieldOfView": 0.5,
        "lightIntensity": 1.0,
        "cameraPoi": (0.0, 0.0, 0.0),
        "cameraPosition": (0.0, 0.0, 1.0),
        "poseData": pose,
    })

CHAR_NAME = "Aura Vasanen"
BLOODLINE_CIVIRE = 2
GENDER_FEMALE = 0
ANCESTRY_MERCS = 8
SCHOOL_STI = 18

OLLAMA_URL = "http://localhost:11434/api/chat"


def log(msg):
    print(f"[aura] {msg}", flush=True)


class MachoSession:
    """Minimal macho-layer client on top of the login connection."""

    def __init__(self, conn, user_id, debug=False):
        self.conn = conn
        self.user_id = user_id
        self.call_id = 2
        self.debug = debug
        self.notifications = []
        self.session_values = {}

    # ---------------------------------------------------------- calls
    def call(self, service, method, *args, timeout=30.0):
        self.call_id += 1
        cid = self.call_id
        req = PyObj("macho.CallReq", (
            6,
            PyObj("macho.MachoAddress", (2, 0, cid, None)),
            PyObj("macho.MachoAddress", (8, service, None)),
            self.user_id,
            ((0, SubStream((1, method, tuple(args),
                            {"machoVersion": 1}))),),
            None, None,
        ))
        self.conn.send_rep(req)
        deadline = time.time() + timeout
        while time.time() < deadline:
            rep = self._recv(remaining=deadline - time.time())
            if rep is None:
                continue
            kind, body = rep
            if kind == "callrsp" and body[0] == cid:
                return body[1]
            if kind == "error" and body[0] == cid:
                raise RuntimeError(f"{service}.{method} failed: {body[1]!r}")
        raise TimeoutError(f"no response to {service}.{method}")

    # ------------------------------------------------------- receiving
    def pump(self, seconds):
        """Receive packets for a while; queue notifications."""
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
        if isinstance(rep, PyObj):
            body = rep.state
            name = rep.type_name
            if name == "macho.CallRsp" and isinstance(body, tuple):
                # dest address carries our callID
                dst = body[2]
                cid = dst.state[2] if isinstance(dst, PyObj) else None
                payload = body[4]
                return ("callrsp", (cid, payload))
            if name == "macho.ErrorResponse" and isinstance(body, tuple):
                dst = body[2]
                cid = dst.state[2] if isinstance(dst, PyObj) else None
                return ("error", (cid, body[4:]))
            if name == "macho.SessionChangeNotification":
                self._absorb_session(body)
                return ("session", body)
            if name == "macho.Notification":
                self.notifications.append(body)
                if self.debug:
                    log(f"NOTIFY {repr(body)[:400]}")
                return ("notify", body)
            if name == "macho.PingReq" and isinstance(body, tuple):
                # echo back as PingRsp with src/dst swapped
                pong = PyObj("macho.PingRsp",
                             (21, body[2], body[1]) + body[3:])
                try:
                    self.conn.send_rep(pong)
                except OSError:
                    pass
                return ("ping", None)
        return ("other", rep)

    def _absorb_session(self, body):
        # session change carries {key: (old, new)} dicts; keep the news
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if (isinstance(k, str) and isinstance(v, tuple)
                            and len(v) == 2):
                        self.session_values[k] = v[1]
                    walk(v)
            elif isinstance(node, (tuple, list)):
                for el in node:
                    walk(el)
            elif isinstance(node, (PyObj,)):
                walk(node.state)
            elif isinstance(node, SubStream):
                walk(node.obj)
            elif isinstance(node, ObjectEx):
                walk(node.header)
                walk(node.items)
                walk(node.kw)
        walk(body)


# ------------------------------------------------------------- helpers

def find_ints(tree, lo, hi):
    """All ints within [lo, hi] anywhere in a decoded tree."""
    out = []

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, int) and lo <= node <= hi:
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
    return out


def find_strings(tree):
    out = []

    def walk(node):
        if isinstance(node, str):
            out.append(str(node))
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
    return out


def filetime_now():
    return int((time.time() + 11644473600) * 10000000)


# --------------------------------------------------------------- ollama

class Captain:
    def __init__(self, model):
        self.model = model
        self.history = []

    def reply(self, sender, text):
        self.history.append(
            {"role": "user", "content": f"{sender} says in Local: {text}"})
        self.history = self.history[-12:]
        body = json.dumps({
            "model": self.model,
            "messages": self.history,
            "stream": False,
            "options": {"num_predict": 120},
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        answer = data.get("message", {}).get("content", "").strip()
        answer = " ".join(answer.split())  # single line for chat
        if len(answer) > 240:
            answer = answer[:237] + "..."
        self.history.append({"role": "assistant", "content": answer})
        return answer


# ----------------------------------------------------------------- main

def ensure_character(mch):
    # cached from a previous run?
    if os.path.exists(CHAR_CACHE):
        with open(CHAR_CACHE) as f:
            cid = json.load(f).get("char_id")
        if cid:
            log(f"using cached character {cid}")
            return cid

    log(f"creating character {CHAR_NAME!r} "
        f"(Civire/Mercs, Science and Trade Institute)")
    try:
        rsp = mch.call(
            "charUnboundMgr", "CreateCharacterWithDoll",
            WStr(CHAR_NAME), BLOODLINE_CIVIRE, GENDER_FEMALE, ANCESTRY_MERCS,
            character_info(), portrait_info(), SCHOOL_STI)
    except RuntimeError as e:
        if "CharNameInvalidTaken" in str(e):
            raise RuntimeError(
                f"{CHAR_NAME!r} already exists but no {CHAR_CACHE} cache. "
                f"Delete the character or write its ID to the cache file "
                f'as {{"char_id": <id>}}.') from e
        raise
    chars = find_ints(rsp, 90000000, 98000000)
    if not chars:
        raise RuntimeError(f"character creation failed: {rsp!r}")
    with open(CHAR_CACHE, "w") as f:
        json.dump({"char_id": chars[0], "name": CHAR_NAME}, f)
    log(f"created character {chars[0]} (cached to {CHAR_CACHE})")
    return chars[0]


def _iter_sendmessage_tuples(node):
    """Yield LSC broadcast tuples of the shape (from captures):
        (channel, seq, 'SendMessage',
         (None, ownerID, [charID, name, corpID], ...), (text,))
    """
    if isinstance(node, tuple):
        if len(node) >= 5 and node[2] == "SendMessage":
            yield node
        for el in node:
            yield from _iter_sendmessage_tuples(el)
    elif isinstance(node, list):
        for el in node:
            yield from _iter_sendmessage_tuples(el)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_sendmessage_tuples(v)
    elif isinstance(node, PyObj):
        yield from _iter_sendmessage_tuples(node.state)
    elif isinstance(node, SubStream):
        yield from _iter_sendmessage_tuples(node.obj)
    elif isinstance(node, ObjectEx):
        yield from _iter_sendmessage_tuples(node.header)
        yield from _iter_sendmessage_tuples(node.items)


def parse_local_chat(notification, self_char_id):
    """Extract (senderName, text) from an OnLSC SendMessage, or None.

    Skips our own messages and the 'EVE System' broadcaster (charID 1).
    """
    for msg in _iter_sendmessage_tuples(notification):
        sender_info = msg[3]
        text_tuple = msg[4]
        try:
            char_block = sender_info[2]      # [charID, name, corpID]
            sender_id = char_block[0]
            sender_name = str(char_block[1])
            text = str(text_tuple[0])
        except (IndexError, TypeError):
            continue
        if sender_id in (1, self_char_id):   # EVE System / self
            continue
        # strip the server MOTD which also arrives as SendMessage
        if text.startswith("<br>"):
            continue
        return sender_name, text
    return None


def main():
    ap = argparse.ArgumentParser(description="Aura Vasanen chat bot")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", default="aura")
    ap.add_argument("--password", default="aura")
    ap.add_argument("--channel-system", type=int, default=30001392,
                    help="solarSystemID whose Local to join (default Amsen)")
    ap.add_argument("--model", default="caldari-captain")
    ap.add_argument("--greeting", default=(
        "Aura Vasanen, formerly of the State Navy. Someone said this "
        "system needed better conversation."))
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    log(f"logging in as {args.user!r}")
    conn, info = eve_login.login(args.host, args.port,
                                 args.user, args.password, log=log)
    mch = MachoSession(conn, info.user_id, debug=args.debug)

    char_id = ensure_character(mch)
    log("selecting character")
    mch.call("charUnboundMgr", "SelectCharacterID", char_id, 0, None)
    mch.pump(3.0)  # let session change + godma spam settle
    log(f"session: { {k: v for k, v in mch.session_values.items() if k in ('solarsystemid2', 'stationid', 'corpid', 'charid')} }")

    corp_id = mch.session_values.get("corpid", 0)
    system_id = args.channel_system
    channels = [((("solarsystemid2", system_id),),)]
    # join own corp channel too, mirrors real client behavior
    join_list = [(("solarsystemid2", system_id),)]
    if corp_id:
        join_list.append((("corpid", corp_id),))
    log(f"joining Local of system {system_id}")
    mch.call("LSC", "JoinChannels", join_list, filetime_now())

    captain = Captain(args.model)
    local = ((("solarsystemid2", system_id),),)
    mch.call("LSC", "SendMessage", local[0], args.greeting)
    log(f"greeted Local: {args.greeting!r}")

    last_keepalive = time.time()
    last_reply = 0.0
    log("chat loop running — Ctrl+C to stop")
    while True:
        mch.pump(1.0)
        while mch.notifications:
            note = mch.notifications.pop(0)
            parsed = parse_local_chat(note, char_id)
            if not parsed:
                continue
            sender, text = parsed
            log(f"heard {sender}: {text!r}")
            try:
                answer = captain.reply(str(sender), text)
            except Exception as e:
                log(f"ollama error: {e}")
                answer = "*comms static* Say again?"
            if answer:
                mch.call("LSC", "SendMessage", local[0], answer)
                last_reply = time.time()
                log(f"replied: {answer!r}")
        if time.time() - last_keepalive > 60:
            try:
                mch.call("machoNet", "GetTime")
            except Exception as e:
                log(f"keepalive failed: {e}")
            last_keepalive = time.time()


if __name__ == "__main__":
    main()
