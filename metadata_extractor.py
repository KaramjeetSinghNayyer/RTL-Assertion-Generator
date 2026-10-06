#!/usr/bin/env python3
"""
Extracts HLS metadata (the shape defined in metadata/schema.json) directly from
a Bambu-generated RTL file plus its ACSL-annotated C source -- no Bambu re-run
needed. Mirrors the by-hand derivation used for metadata/abs.meta.json:
  - top module port list -> C-name <-> RTL-signal mapping, bit widths
  - controller_<fn> FSM   -> reset polarity, start/done handshake, latency

Usage:
    python3 metadata_extractor.py [function ...]   # default: add max min
    python3 metadata_extractor.py abs --check       # validate only, no write
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = REPO_ROOT / "metadata" / "schema.json"

# Longest-first so "unsigned int" isn't mistakenly matched as "int".
C_TYPES = ["unsigned int", "int", "long", "float", "double"]
C_TYPE_RE = "|".join(re.escape(t) for t in C_TYPES)


def is_signed_c_type(c_type: str) -> bool:
    return "unsigned" not in c_type


def expected_bit_width(c_type: str):
    return 32 if c_type in ("int", "unsigned int") else None


def parse_acsl_contract(c_path: Path) -> dict:
    text = c_path.read_text()
    m = re.search(r"/\*@(.*?)\*/", text, re.DOTALL)
    if not m:
        raise ValueError(f"no ACSL contract (/*@ ... */) found in {c_path}")
    body = m.group(1)
    clauses = {"requires": [], "ensures": [], "assigns": []}
    for kw, clause in re.findall(r"\b(requires|ensures|assigns)\b\s*(.*?);", body, re.DOTALL):
        clauses[kw].append(" ".join(clause.split()))
    return clauses


def parse_c_signature(c_path: Path, expected_fn: str) -> dict:
    text = c_path.read_text()
    code = re.sub(r"/\*@.*?\*/", "", text, flags=re.DOTALL)  # drop the ACSL block first
    m = re.search(
        r"\b(%s)\s+(\w+)\s*\(([^)]*)\)\s*\{" % C_TYPE_RE, code
    )
    if not m:
        raise ValueError(f"could not find a function signature in {c_path}")
    ret_type, fn_name, params_str = m.groups()
    if fn_name != expected_fn:
        raise ValueError(f"expected function '{expected_fn}' in {c_path}, found '{fn_name}'")
    params = []
    params_str = params_str.strip()
    if params_str and params_str != "void":
        for p in params_str.split(","):
            ptype, pname = p.strip().rsplit(None, 1)
            params.append((ptype.strip(), pname.strip().lstrip("*")))
    return {"return_type": ret_type.strip(), "parameters": params}


def find_top_module(rtl_text: str, fn_name: str):
    """Returns (module_text, escaped) for the outermost module named fn_name."""
    escaped_m = re.search(r"module\s+\\" + re.escape(fn_name) + r"\s*\(", rtl_text)
    plain_m = re.search(r"module\s+" + re.escape(fn_name) + r"\s*\(", rtl_text)
    if escaped_m:
        start, escaped = escaped_m.start(), True
    elif plain_m:
        start, escaped = plain_m.start(), False
    else:
        raise ValueError(f"could not find top module '{fn_name}'")
    end = rtl_text.index("endmodule", start) + len("endmodule")
    return rtl_text[start:end], escaped


def parse_ports(module_text: str):
    """Returns (inputs, outputs), each {port_name: bit_width}, in declaration order."""
    inputs, outputs = {}, {}
    for direction, width, names in re.findall(
        r"\b(input|output)\s+(?:\[(\d+):0\]\s+)?([\w\\, ]+);", module_text
    ):
        bit_width = int(width) + 1 if width else 1
        target = inputs if direction == "input" else outputs
        for name in names.split(","):
            name = name.strip()
            if name:
                target[name] = bit_width
    return inputs, outputs


def analyze_latency(controller_text: str) -> dict:
    states = sorted(set(re.findall(r"parameter\s*\[\d+:0\]\s*(S_\d+)\s*=", controller_text)))
    if len(states) == 1:
        s = states[0]
        same_cycle = re.search(
            re.escape(s) + r"\s*:\s*if\s*\(\s*start_port\s*==\s*1'b1\s*\)\s*begin\s*"
            r"_next_state\s*=\s*" + re.escape(s) + r"\s*;\s*done_port\s*=\s*1'b1\s*;",
            controller_text,
        )
        if same_cycle:
            return {
                "latency_type": "fixed",
                "fixed_cycles": 0,
                "evidence": (
                    f"controller has a single FSM state ({s}); done_port is driven to 1'b1 "
                    "combinationally in that same state when start_port==1'b1, with no state "
                    "transition -- so the result is valid in the same cycle start_port is asserted."
                ),
            }
    return {
        "latency_type": "unknown",
        "fixed_cycles": None,
        "evidence": (
            f"controller has {len(states)} FSM state(s); the same-cycle done_port pattern "
            "could not be confirmed automatically -- needs manual trace or simulation."
        ),
    }


def detect_reset_polarity(controller_text: str) -> str:
    if re.search(r"reset\s*==\s*1'b0", controller_text):
        return "active_low"
    if re.search(r"reset\s*==\s*1'b1", controller_text):
        return "active_high"
    raise ValueError("could not determine reset polarity from controller FSM")


def parse_provenance(rtl_text: str) -> dict:
    m_ver = re.search(
        r"Version:\s*(PandA\s*[\d.]+)\s*-\s*Revision\s+(\S+)\s*-\s*Date\s+(\S+)", rtl_text
    )
    version, revision, generated_at = m_ver.groups() if m_ver else ("unknown", "unknown", "unknown")
    m_cmd = re.search(r"Bambu executed with:\s*(.+)", rtl_text)
    raw_cmd = m_cmd.group(1).strip() if m_cmd else ""
    command = re.sub(r"^.*/(bambu\b)", r"\1", raw_cmd)  # drop the temp AppImage mount path
    return {
        "hls_tool": f"Bambu ({version}, rev {revision})",
        "command": command,
        "generated_at": generated_at,
        "extraction_method": (
            "automated static parse (metadata_extractor.py) of the top module port list "
            "for signal mapping and the controller FSM for latency/handshake; no Bambu "
            "scheduling report was available in this environment."
        ),
    }


def extract_metadata(fn_name: str) -> dict:
    c_path = REPO_ROOT / "benchmarks" / f"{fn_name}.c"
    v_path = REPO_ROOT / f"{fn_name}.v"
    rtl_text = v_path.read_text()

    contract = parse_acsl_contract(c_path)
    sig = parse_c_signature(c_path, fn_name)

    module_text, escaped = find_top_module(rtl_text, fn_name)
    inputs, outputs = parse_ports(module_text)

    for required in ("clock", "reset", "start_port"):
        if required not in inputs:
            raise ValueError(f"top module is missing expected input '{required}'")
    if "done_port" not in outputs:
        raise ValueError("top module is missing expected output 'done_port'")

    return_candidates = [n for n in outputs if n != "done_port"]
    if len(return_candidates) != 1:
        raise ValueError(f"expected exactly one non-done_port output, found {return_candidates}")
    return_port = return_candidates[0]

    remaining_inputs = [n for n in inputs if n not in ("clock", "reset", "start_port")]
    parameters = []
    for ctype, pname in sig["parameters"]:
        rtl_port = pname if pname in inputs else (
            remaining_inputs[len(parameters)] if len(parameters) < len(remaining_inputs) else None
        )
        if rtl_port is None:
            raise ValueError(f"could not map C parameter '{pname}' to an RTL port")
        bit_width = inputs[rtl_port]
        expected = expected_bit_width(ctype)
        if expected is not None and bit_width != expected:
            raise ValueError(
                f"parameter '{pname}': RTL width {bit_width} != expected {expected} for type '{ctype}'"
            )
        parameters.append({
            "c_name": pname,
            "c_type": ctype,
            "rtl_port": rtl_port,
            "bit_width": bit_width,
            "signed": is_signed_c_type(ctype),
            "kind": "scalar",
        })

    controller_m = re.search(
        r"module\s+controller_%s\b.*?endmodule" % re.escape(fn_name), rtl_text, re.DOTALL
    )
    if not controller_m:
        raise ValueError(f"could not find controller_{fn_name} module")
    controller_text = controller_m.group(0)

    return {
        "function": fn_name,
        "source_file": f"benchmarks/{fn_name}.c",
        "rtl_file": f"{fn_name}.v",
        "top_module": {"verilog_name": fn_name, "escaped": escaped},
        "contract": contract,
        "clock_reset": {
            "clock": "clock",
            "reset": "reset",
            "reset_polarity": detect_reset_polarity(controller_text),
        },
        "handshake": {"protocol": "start_done", "start": "start_port", "done": "done_port"},
        "timing": analyze_latency(controller_text),
        "parameters": parameters,
        "return": {
            "c_type": sig["return_type"],
            "rtl_port": return_port,
            "bit_width": outputs[return_port],
            "signed": is_signed_c_type(sig["return_type"]),
        },
        "memory": [],
        "provenance": parse_provenance(rtl_text),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("functions", nargs="*", default=["add", "max", "min"])
    ap.add_argument("--check", action="store_true", help="validate only, do not write files")
    args = ap.parse_args()

    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    out_dir = REPO_ROOT / "metadata"
    out_dir.mkdir(exist_ok=True)

    exit_code = 0
    for fn in args.functions:
        v_path, c_path = REPO_ROOT / f"{fn}.v", REPO_ROOT / "benchmarks" / f"{fn}.c"
        if not v_path.exists():
            print(f"[skip] {fn}: {v_path.name} not found (not synthesized yet)")
            continue
        if not c_path.exists():
            print(f"[skip] {fn}: benchmarks/{fn}.c not found")
            continue
        try:
            metadata = extract_metadata(fn)
            jsonschema.validate(instance=metadata, schema=schema)
        except Exception as e:
            print(f"[error] {fn}: {e}")
            exit_code = 1
            continue
        out_path = out_dir / f"{fn}.meta.json"
        if args.check:
            print(f"[ok] {fn}: valid (not written, --check)")
        else:
            out_path.write_text(json.dumps(metadata, indent=2) + "\n")
            print(f"[ok] {fn}: wrote {out_path.relative_to(REPO_ROOT)}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
