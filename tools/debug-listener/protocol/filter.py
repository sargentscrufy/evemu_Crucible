"""
Smart filtering for EVE traffic.

The goal is to hide boring, high-volume, well-understood traffic while
keeping everything that is useful when implementing or debugging features.
"""

from dataclasses import dataclass, field
from typing import List, Set, Dict, Any
import re

from .macho import PyPacket


@dataclass
class FilterConfig:
    ignore_services: List[str] = field(default_factory=list)
    always_log_services: List[str] = field(default_factory=list)
    interesting_methods: List[str] = field(default_factory=list)
    ignore_if_contains: List[str] = field(default_factory=list)
    highlight_keywords: List[str] = field(default_factory=list)

    # Compiled patterns
    _ignore_re: List[re.Pattern] = field(default_factory=list, repr=False)
    _always_re: List[re.Pattern] = field(default_factory=list, repr=False)

    def compile(self):
        self._ignore_re = [re.compile(p, re.IGNORECASE) for p in self.ignore_services]
        self._always_re = [re.compile(p, re.IGNORECASE) for p in self.always_log_services]

    @classmethod
    def default(cls) -> "FilterConfig":
        cfg = cls(
            ignore_services=[
                "objectCaching",
                "bulkMgr",
                "photo",
                r".*Cache$",
                "config",
                "charMgr",          # very chatty during login
            ],
            always_log_services=[
                "marketProxy",
                "agentMgr",
                "beyonce",
                "dogma",
                "fleet",
                "LSC",
            ],
            interesting_methods=[
                "PlaceBuyOrder", "PlaceSellOrder", "GetOrders",
                "Activate", "Deactivate", "Overload", "Stop",
                "WarpTo", "WarpToBeacon", "Dock", "Undock",
                "GetMyJournalDetails", "AcceptMission", "CompleteMission",
            ],
            ignore_if_contains=[
                "GetInventory",
                "GetItem",
                "GetCachableObject",
                "GetAttributesForItem",
            ],
            highlight_keywords=["error", "exception", "fail"],
        )
        cfg.compile()
        return cfg


class PacketFilter:
    def __init__(self, config: FilterConfig):
        self.config = config
        config.compile()

    def should_log(self, pkt: PyPacket, raw_tree: Any = None) -> bool:
        service = (pkt.dest.service or "").lower() if pkt.dest else ""

        # Always log certain services
        for pat in self.config._always_re:
            if pat.search(service):
                return True

        # Explicit ignores
        for pat in self.config._ignore_re:
            if pat.search(service):
                return False

        method = (pkt.service_method() or "").lower()

        # Ignore if method contains boring patterns
        for boring in self.config.ignore_if_contains:
            if boring.lower() in method:
                return False

        # Interesting methods
        for interesting in self.config.interesting_methods:
            if interesting.lower() in method:
                return True

        # Default policy: log CALLs and NOTIFICATIONs that are not obviously cache
        if pkt.is_call or pkt.is_notification:
            # Suppress very common boring notifications
            if "on" in method and any(x in method for x in ["godma", "attribute", "cache"]):
                return False
            return True

        # Log errors and session changes by default
        if "error" in pkt.type_name.lower() or "session" in pkt.type_name.lower():
            return True

        # When in doubt for development, we can be more verbose.
        # For now: be conservative.
        return False

    def is_highlight(self, pkt: PyPacket) -> bool:
        text = (pkt.service_method() or "") + " " + pkt.type_name
        text = text.lower()
        return any(kw.lower() in text for kw in self.config.highlight_keywords)