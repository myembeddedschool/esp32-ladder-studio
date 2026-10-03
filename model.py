"""Project validation, desktop simulation and the wire format."""
import re
import time

TAGS = [f"{a}{i}" for a, n in (("I", 4), ("Q", 4), ("M", 8), ("T", 4)) for i in range(n)]
COILS = [t for t in TAGS if t.startswith(("Q", "M"))]
TIMERS = [f"T{i}" for i in range(4)]

def validate(project):
    if not isinstance(project, dict) or project.get("version") not in (1, 2, 3):
        raise ValueError("Expected a version 1, 2 or 3 ladder project.")
    rungs = project.get("rungs")
    if not isinstance(rungs, list) or not 1 <= len(rungs) <= 16:
        raise ValueError("Use 1–16 rungs.")
    writers = set()
    for rung in rungs:
        if not isinstance(rung, dict) or rung.get("kind", "COIL") not in ("COIL", "TON"):
            raise ValueError("Use an output coil or a TON timer.")
        if rung.get("kind") == "TON":
            if project["version"] != 3 or rung.get("coil") not in TIMERS:
                raise ValueError("TON needs a T0–T3 target and project version 3.")
            if type(rung.get("preset_ms")) is not int or not 1 <= rung["preset_ms"] <= 3600000:
                raise ValueError("Timer preset must be 1–3600000 milliseconds.")
        elif rung.get("coil") not in COILS:
            raise ValueError("A coil must be Q0–Q3 or M0–M7.")
        if rung["coil"] in writers:
            raise ValueError("Each coil can appear as an output in only one rung.")
        writers.add(rung["coil"])
        prefix, suffix = rung.get("prefix", []), rung.get("suffix", [])
        if project["version"] == 1 and (prefix or suffix):
            raise ValueError("Shared contacts require project version 2.")
        for common in (prefix, suffix):
            if not isinstance(common, list) or len(common) > 7:
                raise ValueError("Use 0–7 common contacts before or after the branch.")
            check_contacts(common)
            if project["version"] < 3 and any(c["tag"].startswith("T") for c in common):
                raise ValueError("Timer contacts need project version 3.")
        branches = rung.get("branches")
        if not isinstance(branches, list) or not 1 <= len(branches) <= 4:
            raise ValueError("Each rung needs 1–4 parallel branches.")
        for branch in branches:
            if not isinstance(branch, list) or not 1 <= len(branch) <= 8:
                raise ValueError("Each branch needs 1–8 series contacts.")
            if len(prefix) + len(branch) + len(suffix) > 8:
                raise ValueError("Each complete path may contain at most eight contacts.")
            check_contacts(branch)
            if project["version"] < 3 and any(c["tag"].startswith("T") for c in branch):
                raise ValueError("Timer contacts need project version 3.")
    return project

def check_contacts(contacts):
    for contact in contacts:
        if (not isinstance(contact, dict) or contact.get("tag") not in TAGS
            or type(contact.get("nc")) is not bool):
            raise ValueError("Invalid contact tag or NO/NC setting.")

def paths(rung):
    # Distribute shared contacts for the existing ESP32 Boolean runtime.
    return [rung.get("prefix", []) + branch + rung.get("suffix", [])
            for branch in rung["branches"]]

def branch_around(project, rung_index, contact_index, added_contact):
    """Turn one series contact into a parallel group without bypassing neighbours."""
    import copy
    candidate = copy.deepcopy(project)
    r = candidate["rungs"][rung_index]
    if len(r["branches"]) != 1:
        raise ValueError("This version supports one parallel group per rung. Edit its branches instead.")
    original = r["branches"][0]
    if not 0 <= contact_index < len(original):
        raise ValueError("Select the contact to branch around.")
    r["prefix"] = r.get("prefix", []) + original[:contact_index]
    r["suffix"] = original[contact_index + 1:] + r.get("suffix", [])
    r["branches"] = [[original[contact_index]], [added_contact]]
    candidate["version"] = max(2, candidate["version"])
    if added_contact.get("tag", "").startswith("T"): candidate["version"] = 3
    return validate(candidate)

def parse_branch(text):
    tokens = re.split(r"\s*,\s*", text.strip())
    result = []
    for token in tokens:
        nc = token.startswith("!")
        tag = token[1:] if nc else token
        if tag not in TAGS:
            raise ValueError("Use I0–I3, Q0–Q3, M0–M7, T0–T3; prefix ! for NC.")
        result.append({"tag": tag, "nc": nc})
    if not 1 <= len(result) <= 8:
        raise ValueError("Use 1–8 contacts in a branch.")
    return result

def branch_text(branch):
    return ",".join(("!" if c["nc"] else "") + c["tag"] for c in branch)

def wire_rungs(project):
    validate(project)
    return [("T " + r["coil"] + " " + str(r["preset_ms"]) if r.get("kind") == "TON"
             else "R " + r["coil"]) + " " + ";".join(branch_text(b) for b in paths(r))
            for r in project["rungs"]]

def scan(project, bits, now_ms=None, timers=None):
    now_ms = int(time.monotonic()*1000 if now_ms is None else now_ms) & 0xffffffff
    for rung in project["rungs"]:
        enabled = any(all(bool(bits[c["tag"]]) != c["nc"] for c in b) for b in paths(rung))
        if rung.get("kind") == "TON":
            if timers is None: raise ValueError("Timer projects need persistent timer state.")
            state = timers.setdefault(rung["coil"], {"start": None, "elapsed": 0})
            if not enabled:
                state.update(start=None, elapsed=0)
                bits[rung["coil"]] = False
            else:
                if state["start"] is None: state["start"] = now_ms
                elapsed = (now_ms-state["start"]) & 0xffffffff
                bits[rung["coil"]] = bits[rung["coil"]] or elapsed >= rung["preset_ms"]
                state["elapsed"] = rung["preset_ms"] if bits[rung["coil"]] else min(elapsed, rung["preset_ms"])
        else:
            bits[rung["coil"]] = enabled

def stopped(bits, timers=None):
    for t in COILS + TIMERS:
        bits[t] = False
    if timers is not None: timers.clear()

def example():
    # START I0, STOP I1; Q0 contact creates a seal-in (holding) branch.
    return {"version": 1, "name": "Start-stop latch", "rungs": [
        {"coil": "Q0", "branches": [parse_branch("I0,!I1"), parse_branch("Q0,!I1")]},
        {"coil": "Q1", "branches": [parse_branch("Q0,I2")]}]}

def dol_example():
    # Screenshot layout: common NC STOP/overload before START and holding contact.
    return {"version": 2, "name": "DOL - branch around START only", "rungs": [
        {"coil": "Q0", "prefix": parse_branch("!I2,!I1"), "suffix": [],
         "branches": [parse_branch("I0"), parse_branch("Q0")]},
        {"coil": "Q1", "branches": [parse_branch("Q0")]}]}

def blink_example():
    return {"version": 3, "name": "LED blink - one second ON and OFF", "rungs": [
        {"kind": "TON", "coil": "T0", "preset_ms": 1000, "branches": [parse_branch("!T1")]},
        {"kind": "TON", "coil": "T1", "preset_ms": 1000, "branches": [parse_branch("T0")]},
        {"coil": "Q0", "branches": [parse_branch("T0,!T1")]}]}
