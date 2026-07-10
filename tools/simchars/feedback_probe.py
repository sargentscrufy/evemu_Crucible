#!/usr/bin/env python3
"""
FEEDBACK-1/2 validation: Sera joins Local, files a "bug report" in chat,
and verifies (a) the line lands in server_cache/feedback.log and (b) the
Deep Space Monitoring Team acknowledgment comes back on the channel.
Also sends a second message inside the throttle window to confirm only
one ack fires.

    python feedback_probe.py
"""

import subprocess
import sys
import time

from machoclient import MachoClient, CallError, log

sys.path.insert(0, __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__)),
    "..", "smoke-bot"))
from evemarshal import WStr  # noqa: E402

CHAR = 90000014
DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
REPORT = "BUG REPORT: testing the local feedback pipeline end to end"
ACK_SNIPPET = "Deep space monitoring team"


def filetime_now():
    return int((time.time() + 11644473600) * 10_000_000)


def send_and_count_acks(mch, local, text, seconds):
    """Send a local message and count acks that arrive from the moment the
    call goes out (the ack can land during the call's own recv loop)."""
    n0 = len(mch.notifications)
    mch.call("LSC", "SendMessage", local, WStr(text))
    end = time.time() + seconds
    while time.time() < end:
        mch.pump(2.0)
    return sum(1 for note in mch.notifications[n0:]
               if ACK_SNIPPET in repr(note))


def main():
    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    sess = mch.enter_world(CHAR)
    system_id = int(sess.get("solarsystemid2") or 0)
    log(f"in world, system {system_id}")

    local = (("solarsystemid2", system_id),)
    mch.call("LSC", "JoinChannels", [local], filetime_now())
    mch.pump(3)
    log("joined Local; filing report...")

    n_ack = send_and_count_acks(mch, local, REPORT, 8)
    log(f"acks after report #1: {n_ack}")

    n_ack2 = send_and_count_acks(mch, local, "second line, same report", 8)
    log(f"acks after report #2 (throttle window): {n_ack2}")

    out = subprocess.run(
        [DOCKER, "exec", "server", "sh", "-c",
         "tail -6 /app/server_cache/feedback.log"],
        capture_output=True, text=True, timeout=30)
    log("feedback.log tail:")
    for line in (out.stdout or out.stderr).strip().splitlines():
        log(f"  | {line}")

    ok = (n_ack == 1) and (n_ack2 == 0) and (REPORT in (out.stdout or ""))
    log("FEEDBACK VALIDATION " + ("PASS" if ok else
        f"ISSUES (ack1={n_ack} ack2={n_ack2} logged={REPORT in (out.stdout or '')})"))
    mch.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
