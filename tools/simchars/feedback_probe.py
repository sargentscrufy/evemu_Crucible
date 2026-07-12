#!/usr/bin/env python3
"""
FEEDBACK-3 validation: local chat is only captured as a dev report when the
line carries the uppercase token "BUG".

Sequence (single char in Local):
  1. a plain line with no BUG token  -> NOT logged, NO ack
  2. a line containing BUG           -> logged to feedback.log + one ack
  3. a second BUG line in the throttle window -> logged, but NO extra ack

    python feedback_probe.py
"""

import os
import subprocess
import sys
import time

from machoclient import MachoClient, CallError, log

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "smoke-bot"))
from evemarshal import WStr  # noqa: E402

CHAR = 90000014
DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
ACK_SNIPPET = "Deep space monitoring team"
TAG = str(int(time.time()))                       # unique marker for this run
PLAIN = f"the gate feels slow today {TAG}"        # no BUG token -> ignored
REPORT = f"BUG the undock bounce is back {TAG}"   # BUG token -> captured
REPORT2 = f"BUG and the map is off too {TAG}"     # second BUG -> throttled ack


def filetime_now():
    return int((time.time() + 11644473600) * 10_000_000)


def send_and_count_acks(mch, local, text, seconds):
    """Send a local message; count acks arriving from the moment we send."""
    n0 = len(mch.notifications)
    mch.call("LSC", "SendMessage", local, WStr(text))
    end = time.time() + seconds
    while time.time() < end:
        mch.pump(2.0)
    return sum(1 for note in mch.notifications[n0:] if ACK_SNIPPET in repr(note))


def feedback_log():
    out = subprocess.run(
        [DOCKER, "exec", "server", "sh", "-c", "tail -40 /app/server_cache/feedback.log"],
        capture_output=True, text=True, timeout=30)
    return out.stdout or out.stderr or ""


def main():
    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    sess = mch.enter_world(CHAR)
    system_id = int(sess.get("solarsystemid2") or 0)
    log(f"in world, system {system_id}")

    local = (("solarsystemid2", system_id),)
    mch.call("LSC", "JoinChannels", [local], filetime_now())
    mch.pump(3)

    log("1) plain line (no BUG token)")
    ack_plain = send_and_count_acks(mch, local, PLAIN, 8)
    log(f"   acks: {ack_plain}  (expect 0)")

    log("2) BUG line")
    ack_bug = send_and_count_acks(mch, local, REPORT, 8)
    log(f"   acks: {ack_bug}  (expect 1)")

    log("3) second BUG line inside throttle window")
    ack_bug2 = send_and_count_acks(mch, local, REPORT2, 8)
    log(f"   acks: {ack_bug2}  (expect 0 -- throttled)")

    logtxt = feedback_log()
    plain_logged = PLAIN in logtxt
    bug_logged = REPORT in logtxt
    bug2_logged = REPORT2 in logtxt
    log("feedback.log (this run's lines):")
    for line in logtxt.splitlines():
        if TAG in line:
            log(f"  | {line}")

    ok = (ack_plain == 0 and ack_bug == 1 and ack_bug2 == 0
          and not plain_logged and bug_logged and bug2_logged)
    log("=== VERDICT ===")
    log(f"  plain line: ack={ack_plain} logged={plain_logged} (want ack=0 logged=False)")
    log(f"  BUG line:   ack={ack_bug} logged={bug_logged} (want ack=1 logged=True)")
    log(f"  BUG line 2: ack={ack_bug2} logged={bug2_logged} (want ack=0 logged=True)")
    log("  >>> FEEDBACK-3 " + ("PASS" if ok else "FAIL"))
    mch.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
