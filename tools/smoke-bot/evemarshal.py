"""
EVE marshal codec (Crucible era) — encoder and decoder.

Self-contained implementation of the wire format spoken by EVEmu, derived
from the server source:

  - stream prelude:  0x7E header byte + uint32 map-count
    (EVEMarshal.cpp SaveStream; EVEmu always writes map-count 0 and does
    not implement saved-object references)
  - sizes: "SizeEx" = uint8, or 0xFF followed by uint32
  - dict entries marshal VALUE first, then KEY (EVEUnmarshal.cpp LoadDict)
  - PyObjectEx: header, list items until 0x2D terminator, then KEY/VALUE
    pairs until 0x2D (LoadObjectEx — note pair order differs from PyDict)
  - string table indices are 1-based (EVEMarshalStringTable.cpp)

Python type mapping:
  None/bool/int/float/bytes/str/tuple/list/dict map directly.
  WStr marks a string to encode as Op_PyWStringUTF8 (0x2E) — the packet
  XML distinguishes <string> from <wstring>.
  ObjectEx / PyObj wrap the object opcodes on decode.
"""

import struct
import zlib

MARSHAL_HEADER = 0x7E

# Opcodes (EVEMarshalOpcodes.h)
OP_NONE = 0x01
OP_TOKEN = 0x02
OP_LONGLONG = 0x03
OP_LONG = 0x04
OP_SIGNEDSHORT = 0x05
OP_BYTE = 0x06
OP_MINUSONE = 0x07
OP_ZEROINT = 0x08
OP_ONEINT = 0x09
OP_REAL = 0x0A
OP_ZEROREAL = 0x0B
OP_BUFFER = 0x0D
OP_EMPTYSTRING = 0x0E
OP_CHARSTRING = 0x0F
OP_SHORTSTRING = 0x10
OP_STRINGTABLE = 0x11
OP_WSTRINGUCS2 = 0x12
OP_LONGSTRING = 0x13
OP_TUPLE = 0x14
OP_LIST = 0x15
OP_DICT = 0x16
OP_OBJECT = 0x17
OP_SUBSTRUCT = 0x19
OP_SAVEDELEMENT = 0x1B
OP_CHECKSUMSTREAM = 0x1C
OP_TRUE = 0x1F
OP_FALSE = 0x20
OP_OBJECTEX1 = 0x22
OP_OBJECTEX2 = 0x23
OP_EMPTYTUPLE = 0x24
OP_ONETUPLE = 0x25
OP_EMPTYLIST = 0x26
OP_ONELIST = 0x27
OP_EMPTYWSTRING = 0x28
OP_WSTRINGUCS2CHAR = 0x29
OP_PACKEDROW = 0x2A
OP_SUBSTREAM = 0x2B
OP_TWOTUPLE = 0x2C
OP_PACKEDTERMINATOR = 0x2D
OP_WSTRINGUTF8 = 0x2E
OP_VARINTEGER = 0x2F

SAVE_MASK = 0x40  # "save this object" reference flag; masked off on decode

# 1-based marshal string table (EVEMarshalStringTable.cpp, Crucible)
STRING_TABLE = [
    "*corpid", "*locationid", "age", "Asteroid", "authentication", "ballID",
    "beyonce", "bloodlineID", "capacity", "categoryID", "character",
    "characterID", "characterName", "characterType", "charID", "chatx",
    "clientID", "config", "contraband", "corporationDateTime",
    "corporationID", "createDateTime", "customInfo", "description",
    "divisionID", "DoDestinyUpdate", "dogmaIM", "EVE System", "flag",
    "foo.SlimItem", "gangID", "Gemini", "gender", "graphicID", "groupID",
    "header", "idName", "invbroker", "itemID", "items", "jumps", "line",
    "lines", "locationID", "locationName", "macho.CallReq", "macho.CallRsp",
    "macho.MachoAddress", "macho.Notification",
    "macho.SessionChangeNotification", "modules", "name", "objectCaching",
    "objectCaching.CachedObject", "OnChatJoin", "OnChatLeave", "OnChatSpeak",
    "OnGodmaShipEffect", "OnItemChange", "OnModuleAttributeChange",
    "OnMultiEvent", "orbitID", "ownerID", "ownerName", "quantity", "raceID",
    "RowClass", "securityStatus", "Sentry Gun", "sessionchange", "singleton",
    "skillEffect", "squadronID", "typeID", "used", "userID",
    "util.CachedObject", "util.IndexRowset", "util.Moniker", "util.Row",
    "util.Rowset", "*multicastID", "AddBalls", "AttackHit3", "AttackHit3R",
    "AttackHit4R", "DoDestinyUpdates", "GetLocationsEx",
    "InvalidateCachedObjects", "JoinChannel", "LSC", "LaunchMissile",
    "LeaveChannel", "OID+", "OID-", "OnAggressionChange", "OnCharGangChange",
    "OnCharNoLongerInStation", "OnCharNowInStation", "OnDamageMessage",
    "OnDamageStateChange", "OnEffectHit", "OnGangDamageStateChange", "OnLSC",
    "OnSpecialFX", "OnTarget", "RemoveBalls", "SendMessage", "SetMaxSpeed",
    "SetSpeedFraction", "TerminalExplosion", "address", "alert",
    "allianceID", "allianceid", "bid", "bookmark", "bounty", "channel",
    "charid", "constellationid", "corpID", "corpid", "corprole", "damage",
    "duration", "effects.Laser", "gangid", "gangrole", "hqID", "issued",
    "jit", "languageID", "locationid", "machoVersion", "marketProxy",
    "minVolume", "orderID", "price", "range", "regionID", "regionid", "role",
    "rolesAtAll", "rolesAtBase", "rolesAtHQ", "rolesAtOther", "shipid", "sn",
    "solarSystemID", "solarsystemid", "solarsystemid2", "source", "splash",
    "stationID", "stationid", "target", "userType", "userid", "volEntered",
    "volRemaining", "weapon",
    "agent.missionTemplatizedContent_BasicKillMission",
    "agent.missionTemplatizedContent_ResearchKillMission",
    "agent.missionTemplatizedContent_StorylineKillMission",
    "agent.missionTemplatizedContent_GenericStorylineKillMission",
    "agent.missionTemplatizedContent_BasicCourierMission",
    "agent.missionTemplatizedContent_ResearchCourierMission",
    "agent.missionTemplatizedContent_StorylineCourierMission",
    "agent.missionTemplatizedContent_GenericStorylineCourierMission",
    "agent.missionTemplatizedContent_BasicTradeMission",
    "agent.missionTemplatizedContent_ResearchTradeMission",
    "agent.missionTemplatizedContent_StorylineTradeMission",
    "agent.missionTemplatizedContent_GenericStorylineTradeMission",
    "agent.offerTemplatizedContent_BasicExchangeOffer",
    "agent.offerTemplatizedContent_BasicExchangeOffer_ContrabandDemand",
    "agent.offerTemplatizedContent_BasicExchangeOffer_Crafting",
    "agent.LoyaltyPoints", "agent.ResearchPoints", "agent.Credits",
    "agent.Item", "agent.Entity", "agent.Objective", "agent.FetchObjective",
    "agent.EncounterObjective", "agent.DungeonObjective",
    "agent.TransportObjective", "agent.Reward", "agent.TimeBonusReward",
    "agent.MissionReferral", "agent.Location",
    "agent.StandardMissionDetails", "agent.OfferDetails",
    "agent.ResearchMissionDetails", "agent.StorylineMissionDetails",
]


class WStr(str):
    """A str that encodes as Op_PyWStringUTF8 (packet-XML <wstring>)."""


class Token(str):
    """A str that encodes as Op_PyToken."""


class SubStream:
    """Nested marshal stream (Op_PySubStream)."""

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return f"SubStream({self.obj!r})"


class PyObj:
    """Op_PyObject: (type_name, state)."""

    def __init__(self, type_name, state):
        self.type_name = type_name
        self.state = state

    def __repr__(self):
        return f"PyObj({self.type_name!r}, {self.state!r})"


class ObjectEx:
    """Op_PyObjectEx1/2: header + list + dict."""

    def __init__(self, is_type2, header, items=None, kw=None):
        self.is_type2 = is_type2
        self.header = header
        self.items = items or []
        self.kw = kw or {}

    def __repr__(self):
        return (f"ObjectEx(type2={self.is_type2}, header={self.header!r}, "
                f"items={self.items!r}, kw={self.kw!r})")


class PackedRow:
    """Op_PyPackedRow: descriptor + RLE-packed fixed fields + string reps."""

    def __init__(self, header, raw, trailing=None):
        self.header = header
        self.raw = raw
        self.trailing = trailing or []

    def __repr__(self):
        return (f"PackedRow(header={self.header!r}, raw={len(self.raw)} "
                f"bytes, trailing={self.trailing!r})")


# DBTYPE codes whose values trail the packed buffer as normal reps
DBTYPE_BYTES, DBTYPE_STR, DBTYPE_WSTR = 128, 129, 130


def _count_string_columns(descriptor) -> int:
    """Count BYTES/STR/WSTR columns in a blue.DBRowDescriptor header.

    Descriptor shape: ObjectEx(header=(Token('blue.DBRowDescriptor'),
    ((name, dbtype), ...),)) — navigate defensively and treat anything
    unrecognized as zero string columns.
    """
    try:
        args = descriptor.header[1]
        columns = args[0]
        return sum(1 for col in columns
                   if isinstance(col, tuple) and len(col) == 2
                   and col[1] in (DBTYPE_BYTES, DBTYPE_STR, DBTYPE_WSTR))
    except (AttributeError, IndexError, TypeError):
        return 0


class MarshalError(Exception):
    pass


# ---------------------------------------------------------------- encoder

class Marshaler:
    def __init__(self):
        self.out = bytearray()

    def dumps(self, obj) -> bytes:
        self.out = bytearray()
        self.out.append(MARSHAL_HEADER)
        self.out += struct.pack("<I", 0)  # map-count: saves unsupported
        self._encode(obj)
        return bytes(self.out)

    def _size_ex(self, n: int):
        if n < 0xFF:
            self.out.append(n)
        else:
            self.out.append(0xFF)
            self.out += struct.pack("<I", n)

    def _encode(self, obj):
        if obj is None:
            self.out.append(OP_NONE)
        elif obj is True:
            self.out.append(OP_TRUE)
        elif obj is False:
            self.out.append(OP_FALSE)
        elif isinstance(obj, Token):
            self.out.append(OP_TOKEN)
            raw = obj.encode("utf-8")
            self.out.append(len(raw))
            self.out += raw
        elif isinstance(obj, WStr):
            self.out.append(OP_WSTRINGUTF8)
            raw = obj.encode("utf-8")
            self._size_ex(len(raw))
            self.out += raw
        elif isinstance(obj, str):
            self._encode_str(obj)
        elif isinstance(obj, int):
            self._encode_int(obj)
        elif isinstance(obj, float):
            if obj == 0.0:
                self.out.append(OP_ZEROREAL)
            else:
                self.out.append(OP_REAL)
                self.out += struct.pack("<d", obj)
        elif isinstance(obj, (bytes, bytearray)):
            self.out.append(OP_BUFFER)
            self._size_ex(len(obj))
            self.out += obj
        elif isinstance(obj, tuple):
            self._encode_tuple(obj)
        elif isinstance(obj, list):
            if not obj:
                self.out.append(OP_EMPTYLIST)
            elif len(obj) == 1:
                self.out.append(OP_ONELIST)
                self._encode(obj[0])
            else:
                self.out.append(OP_LIST)
                self._size_ex(len(obj))
                for el in obj:
                    self._encode(el)
        elif isinstance(obj, dict):
            self.out.append(OP_DICT)
            self._size_ex(len(obj))
            for k, v in obj.items():
                self._encode(v)  # value FIRST (LoadDict)
                self._encode(k)
        elif isinstance(obj, SubStream):
            inner = Marshaler().dumps(obj.obj)
            self.out.append(OP_SUBSTREAM)
            self._size_ex(len(inner))
            self.out += inner
        elif isinstance(obj, PyObj):
            self.out.append(OP_OBJECT)
            self._encode_str(obj.type_name)
            self._encode(obj.state)
        elif isinstance(obj, ObjectEx):
            self.out.append(OP_OBJECTEX2 if obj.is_type2 else OP_OBJECTEX1)
            self._encode(obj.header)
            for el in obj.items:
                self._encode(el)
            self.out.append(OP_PACKEDTERMINATOR)
            for k, v in obj.kw.items():
                self._encode(k)  # ObjectEx dict is key FIRST (LoadObjectEx)
                self._encode(v)
            self.out.append(OP_PACKEDTERMINATOR)
        else:
            raise MarshalError(f"cannot marshal {type(obj).__name__}: {obj!r}")

    def _encode_tuple(self, obj: tuple):
        if not obj:
            self.out.append(OP_EMPTYTUPLE)
        elif len(obj) == 1:
            self.out.append(OP_ONETUPLE)
            self._encode(obj[0])
        elif len(obj) == 2:
            self.out.append(OP_TWOTUPLE)
            self._encode(obj[0])
            self._encode(obj[1])
        else:
            self.out.append(OP_TUPLE)
            self._size_ex(len(obj))
            for el in obj:
                self._encode(el)

    def _encode_int(self, val: int):
        if val == -1:
            self.out.append(OP_MINUSONE)
        elif val == 0:
            self.out.append(OP_ZEROINT)
        elif val == 1:
            self.out.append(OP_ONEINT)
        elif -0x80 <= val <= 0x7F:
            self.out.append(OP_BYTE)
            self.out += struct.pack("<b", val)
        elif -0x8000 <= val <= 0x7FFF:
            self.out.append(OP_SIGNEDSHORT)
            self.out += struct.pack("<h", val)
        elif -0x80000000 <= val <= 0x7FFFFFFF:
            self.out.append(OP_LONG)
            self.out += struct.pack("<i", val)
        elif -0x8000000000000000 <= val <= 0x7FFFFFFFFFFFFFFF:
            self.out.append(OP_LONGLONG)
            self.out += struct.pack("<q", val)
        else:
            raw = val.to_bytes((val.bit_length() + 8) // 8, "little",
                               signed=True)
            self.out.append(OP_VARINTEGER)
            self._size_ex(len(raw))
            self.out += raw

    def _encode_str(self, s: str):
        raw = s.encode("utf-8")
        if not raw:
            self.out.append(OP_EMPTYSTRING)
        elif len(raw) == 1:
            self.out.append(OP_CHARSTRING)
            self.out += raw
        else:
            # Op_PyLongString with SizeEx covers all lengths; the server
            # itself no longer emits ShortString (EVEMarshal.cpp comment).
            self.out.append(OP_LONGSTRING)
            self._size_ex(len(raw))
            self.out += raw


# ---------------------------------------------------------------- decoder

class Unmarshaler:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def loads(self):
        if not self.data:
            raise MarshalError("empty buffer")
        if self.data[0] != MARSHAL_HEADER:
            raise MarshalError(
                f"bad marshal header 0x{self.data[0]:02X} (expected 0x7E)")
        self.pos = 1
        map_count = self._u32()
        if map_count:
            # EVEmu's server never emits saved references (map-count 0).
            raise MarshalError(f"map-count {map_count} not supported")
        return self._decode()

    # -- primitives
    def _read(self, n):
        if self.pos + n > len(self.data):
            raise MarshalError("unexpected end of stream")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def _u8(self):
        return self._read(1)[0]

    def _u32(self):
        return struct.unpack("<I", self._read(4))[0]

    def _size_ex(self):
        n = self._u8()
        if n == 0xFF:
            n = self._u32()
        return n

    def _peek(self):
        if self.pos >= len(self.data):
            raise MarshalError("unexpected end of stream")
        return self.data[self.pos]

    def _str(self, n):
        raw = self._read(n)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    # -- tree
    def _decode(self):
        op = self._u8()
        op &= ~SAVE_MASK  # tolerate save flag; references never re-used here

        if op == OP_NONE:
            return None
        if op == OP_TRUE:
            return True
        if op == OP_FALSE:
            return False
        if op == OP_MINUSONE:
            return -1
        if op == OP_ZEROINT:
            return 0
        if op == OP_ONEINT:
            return 1
        if op == OP_BYTE:
            return struct.unpack("<b", self._read(1))[0]
        if op == OP_SIGNEDSHORT:
            return struct.unpack("<h", self._read(2))[0]
        if op == OP_LONG:
            return struct.unpack("<i", self._read(4))[0]
        if op == OP_LONGLONG:
            return struct.unpack("<q", self._read(8))[0]
        if op == OP_VARINTEGER:
            n = self._size_ex()
            return int.from_bytes(self._read(n), "little", signed=True)
        if op == OP_REAL:
            return struct.unpack("<d", self._read(8))[0]
        if op == OP_ZEROREAL:
            return 0.0
        if op == OP_BUFFER:
            return bytes(self._read(self._size_ex()))
        if op == OP_EMPTYSTRING:
            return ""
        if op == OP_CHARSTRING:
            return self._str(1)
        if op == OP_SHORTSTRING:
            return self._str(self._u8())
        if op == OP_LONGSTRING:
            return self._str(self._size_ex())
        if op == OP_TOKEN:
            return Token(self._str(self._u8()))
        if op == OP_STRINGTABLE:
            idx = self._u8()
            if 1 <= idx <= len(STRING_TABLE):
                return STRING_TABLE[idx - 1]
            raise MarshalError(f"string table index {idx} out of range")
        if op == OP_WSTRINGUTF8:
            return WStr(self._str(self._size_ex()))
        if op == OP_EMPTYWSTRING:
            return WStr("")
        if op == OP_WSTRINGUCS2:
            n = self._size_ex()
            return WStr(self._read(2 * n).decode("utf-16-le"))
        if op == OP_WSTRINGUCS2CHAR:
            return WStr(self._read(2).decode("utf-16-le"))
        if op == OP_EMPTYTUPLE:
            return ()
        if op == OP_ONETUPLE:
            return (self._decode(),)
        if op == OP_TWOTUPLE:
            return (self._decode(), self._decode())
        if op == OP_TUPLE:
            return tuple(self._decode() for _ in range(self._size_ex()))
        if op == OP_EMPTYLIST:
            return []
        if op == OP_ONELIST:
            return [self._decode()]
        if op == OP_LIST:
            return [self._decode() for _ in range(self._size_ex())]
        if op == OP_DICT:
            n = self._size_ex()
            d = {}
            for _ in range(n):
                value = self._decode()  # value FIRST (LoadDict)
                key = self._decode()
                d[key] = value
            return d
        if op == OP_OBJECT:
            type_name = self._decode()
            state = self._decode()
            return PyObj(type_name, state)
        if op in (OP_OBJECTEX1, OP_OBJECTEX2):
            header = self._decode()
            items = []
            while self._peek() != OP_PACKEDTERMINATOR:
                items.append(self._decode())
            self._u8()
            kw = {}
            while self._peek() != OP_PACKEDTERMINATOR:
                key = self._decode()  # key FIRST here (LoadObjectEx)
                kw[key] = self._decode()
            self._u8()
            return ObjectEx(op == OP_OBJECTEX2, header, items, kw)
        if op == OP_SUBSTREAM:
            n = self._size_ex()
            raw = bytes(self._read(n))
            try:
                return SubStream(Unmarshaler(raw).loads())
            except MarshalError:
                return SubStream(raw)
        if op == OP_SUBSTRUCT:
            return ("SubStruct", self._decode())
        if op == OP_CHECKSUMSTREAM:
            self._read(4)  # adler32; ignored
            return self._decode()
        if op == OP_PACKEDROW:
            # LoadPackedRow: descriptor rep, RLE buffer (SizeEx length),
            # then one trailing rep per BYTES/STR/WSTR column. The fixed
            # fields aren't unpacked here — not needed yet — but the row
            # is consumed exactly, keeping the stream in sync.
            header = self._decode()
            raw = bytes(self._read(self._size_ex()))
            trailing = [self._decode()
                        for _ in range(_count_string_columns(header))]
            return PackedRow(header, raw, trailing)

        raise MarshalError(f"unhandled opcode 0x{op:02X} at {self.pos - 1}")


# ---------------------------------------------------------------- helpers

def dumps(obj) -> bytes:
    """Marshal obj to a complete EVE stream (0x7E-prefixed)."""
    return Marshaler().dumps(obj)


def loads(data: bytes):
    """Unmarshal a complete EVE stream, inflating zlib if needed."""
    if data[:1] == b"\x78":  # zlib
        data = zlib.decompress(data)
    return Unmarshaler(data).loads()
