#!/usr/bin/env python3
"""Reproduce native C checks, concurrent SVA simulation, and RTL SAT proofs.

Build products live in a temporary directory. Reports and Yosys scripts are
the only outputs written to the repository. Original source files are read only.
"""
import ctypes
import hashlib
import json
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'formal' / 'reports'
READY = ('abs', 'add', 'max', 'min')
MIN, MAX = -(2**31), 2**31 - 1


def run(command, log, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed ({result.returncode}); see {log}')
    return result.stdout


def samples(name):
    edge = [MIN, MIN + 1, -1, 0, 1, MAX - 1, MAX]
    rng = random.Random(20261006)
    if name == 'add':
        result = [(0, 0), (MAX, 0), (0, MAX), (MAX - 1, 1), (1, MAX - 1)]
        for _ in range(64):
            x = rng.randint(0, MAX)
            result.append((x, rng.randint(0, MAX - x)))
        return result
    if name in ('max', 'min'):
        return [(x, y) for x in edge for y in edge] + [
            (rng.randint(MIN, MAX), rng.randint(MIN, MAX)) for _ in range(64)]
    result = [(x,) for x in edge if name != 'abs' or x != MIN]
    return result + [(rng.randint(MIN + int(name == 'abs'), MAX),) for _ in range(64)]


def expected(name, args):
    if name == 'abs':
        return abs(args[0])
    if name == 'add':
        return sum(args)
    if name == 'max':
        return max(args)
    if name == 'min':
        return min(args)
    return (args[0] > 0) - (args[0] < 0)


def c_vectors(name, work):
    library = work / f'{name}.dylib'
    run(['cc', '-shared', '-fPIC', '-O0', '-fno-builtin',
         f'-D{name}=benchmark_{name}', str(ROOT / 'benchmarks' / f'{name}.c'),
         '-o', str(library)], REPORTS / f'{name}_c_compile.log')
    dll = ctypes.CDLL(str(library))
    function = getattr(dll, f'benchmark_{name}')
    vectors = samples(name)
    function.argtypes = [ctypes.c_int] * len(vectors[0])
    function.restype = ctypes.c_int
    records = []
    for args in vectors:
        value = function(*args)
        if value != expected(name, args):
            raise RuntimeError(f'{name}{args}: C returned {value}')
        records.append({'inputs': list(args), 'result': value})
    (REPORTS / f'{name}_vectors.json').write_text(json.dumps(records, indent=2) + '\n')
    return records


def simulate(name, vectors, work):
    meta = json.loads((ROOT / 'metadata' / f'{name}.meta.json').read_text())
    params = [p['rtl_port'] for p in meta['parameters']]
    module = ('\\' + name + ' ') if meta['top_module']['escaped'] else name
    signals = ['clock', 'reset', 'start_port', 'done_port'] + params + ['return_port']
    lines = ['`timescale 1ns/1ps', f'module {name}_tb;',
             "reg clock = 0, reset = 0, start_port = 0;", 'wire done_port;',
             'wire [31:0] return_port;']
    lines += [f'reg [31:0] {p} = 0;' for p in params]
    lines += [f'{module} dut (' + ', '.join(f'.{p}({p})' for p in signals) + ');',
              'initial begin', '#5; clock = 1; #5; clock = 0; reset = 1;']
    for record in vectors:
        lines += ['start_port = 1;']
        lines += [f"{p} = 32'h{value & 0xffffffff:08x};" for p, value in zip(params, record['inputs'])]
        lines += ['#5; clock = 1; #1;',
                  f"if (done_port !== 1'b1 || return_port !== 32'h{record['result'] & 0xffffffff:08x})",
                  '    $fatal(1, "RTL differs from native C result");',
                  '#4; clock = 0; start_port = 0; #5; clock = 1; #1;',
                  'if (done_port !== 0) $fatal(1, "idle handshake failed");', '#4; clock = 0;']
    lines += [f'$display("PASS: {name}, {len(vectors)} C/RTL vectors, concurrent SVA enabled");',
              '$finish;', 'end', 'endmodule', '']
    tb = work / f'{name}_tb.sv'
    tb.write_text('\n'.join(lines))
    build = work / f'{name}_build'
    run(['verilator', '--binary', '--timing', '--assert', '-Wno-fatal',
         '--top-module', f'{name}_tb', '--Mdir', str(build), '-o', 'simulation',
         str(ROOT / f'{name}.v'), str(ROOT / 'sva' / f'{name}_acsl.sv'),
         str(ROOT / 'sva' / f'{name}_bind.sv'), str(tb)], REPORTS / f'{name}_sva_build.log')
    output = run([str(build / 'simulation')], REPORTS / f'{name}_sva_simulation.log')
    if f'PASS: {name}' not in output:
        raise RuntimeError(f'{name}: simulation did not finish its checks')


def preparation(name, harness=None):
    # chformal -lower is needed for current Yosys $check cells.
    return (f'read_verilog -formal -sv -D YOSYS {name}.v sva/{name}_acsl.sv '
            f'{harness or f"formal/{name}_formal.sv"};\n'
            f'prep -top {name}_formal -flatten;\n'
            'chformal -lower;\nchformal -cover -remove;\n')


def yosys_script(name, task, script):
    path = ROOT / 'formal' / f'{name}_{task}.ys'
    path.write_text(script)
    return run(['yosys', '-Q', '-T', '-s', str(path)], REPORTS / f'{name}_{task}.log')


def prove(name, work):
    base = preparation(name)
    output = yosys_script(name, 'prove', base +
        'sat -seq 2 -tempinduct -maxsteps 8 -set-assumes -set-def-inputs '
        '-prove-asserts -verify;\n')
    if 'Induction step proven: SUCCESS!' not in output:
        raise RuntimeError(f'{name}: no successful unbounded induction proof')
    output = yosys_script(name, 'cover', base +
        'sat -seq 2 -set-assumes -set-def-inputs '
        '-set-at 2 reset 1 -set-at 2 start_port 1 '
        '-prove acsl_checker.transaction_witness 0 -prove-skip 1 -falsify '
        f'-show-inputs -show return_port -dump_json formal/reports/{name}_transaction.json;\n')
    if 'model found: FAIL!' not in output:
        raise RuntimeError(f'{name}: no reachable valid transaction')

    # A one-bit corruption must produce a counterexample. Keep mutated harnesses
    # outside the repository; never modify the DUT or its generated checkers.
    harness = (ROOT / 'formal' / f'{name}_formal.sv').read_text()
    old = f'{name}_acsl_sva acsl_checker ('
    split = harness.index(old)
    harness = harness[:split] + harness[split:].replace(
        '.return_port(return_port)', ".return_port(return_port ^ 32'h00000001)")
    mutant = work / f'{name}_mutant.sv'
    mutant.write_text(harness)
    # Use a quoted path because users may have spaces in their temporary root.
    script = preparation(name, '"' + str(mutant) + '"') + (
        'sat -seq 2 -set-assumes -set-def-inputs -set-at 2 reset 1 '
        '-set-at 2 start_port 1 -prove-asserts -prove-skip 1 -falsify;\n')
    # This task is transient; the repository should contain only reproducible paths.
    output = run(['yosys', '-Q', '-T', '-p', script], REPORTS / f'{name}_mutation.log')
    if 'model found: FAIL!' not in output:
        raise RuntimeError(f'{name}: assertions missed corrupted output')
    if name in ('abs', 'add'):
        constraint = '-set-at 2 x 2147483648' if name == 'abs' else '-set-at 2 x 2147483647 -set-at 2 y 1'
        output = yosys_script(name, 'excluded_input', base +
            'sat -seq 2 -set-assumes -set-def-inputs -set-at 2 reset 1 '
            f'-set-at 2 start_port 1 {constraint};\n')
        if 'no model found' not in output:
            raise RuntimeError(f'{name}: preconditions admitted an invalid input')


def main():
    REPORTS.mkdir(exist_ok=True)
    for tool in ('cc', 'verilator', 'yosys'):
        if not shutil.which(tool):
            raise SystemExit(f'Missing required tool: {tool}')
    summary = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
               'tools': {t: subprocess.check_output([t, '--version' if t != 'yosys' else '-V'], text=True).strip()
                         for t in ('verilator', 'yosys')}, 'results': {}}
    run([sys.executable, '-B', 'formal/generate_sva.py'], REPORTS / 'generation.log')
    with tempfile.TemporaryDirectory(prefix='rtl-acsl-') as directory:
        work = Path(directory)
        for name in (*READY, 'sign'):
            vectors = c_vectors(name, work)
            result = {'c_vectors_passed': len(vectors)}
            if name in READY:
                simulate(name, vectors, work)
                prove(name, work)
                result.update(sva_simulation='PASS', formal_induction='PASS',
                              valid_transaction_reachable=True, corrupt_output_detected=True)
                if name in ('abs', 'add'):
                    result['invalid_input_excluded'] = True
            else:
                run(['verilator', '--lint-only', '--assert', '-Wno-fatal',
                     '--top-module', 'sign_acsl_sva', 'sva/sign_acsl.sv'], REPORTS / 'sign_sva_lint.log')
                result.update(sva_lint='PASS', formal_induction='PENDING: no sign.v or sign metadata')
            summary['results'][name] = result
            print(f'{name}: {result}', flush=True)
    baseline = json.loads((REPORTS / 'original_files.sha256.json').read_text())
    changed = [p for p, digest in baseline.items() if not (ROOT / p).exists() or
               hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
    if changed:
        raise RuntimeError(f'Original files changed: {changed}')
    summary['original_files_unchanged'] = True
    (REPORTS / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('All four available RTL designs proved; sign awaits RTL and metadata.')


if __name__ == '__main__':
    main()
