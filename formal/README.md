# ACSL to SVA and formal verification

This directory adds verification around the existing project. The original C,
Verilog, metadata, Python programs, and synthesis scripts are unchanged.

## Run

Requirements: Python 3, a C compiler (`cc`), Verilator, and Yosys with
`chformal -lower` support. The recorded run used Verilator 5.052 and Yosys 0.69.
No Vivado, Bambu, external SMT solver, or Python package is required by this
verification runner.

From the repository root:

```sh
python3 -B formal/generate_sva.py
python3 -B formal/run_verification.py
```

The runner regenerates only the new verification files, compiles the original
C sources into temporary libraries, and uses their outputs as reference vectors
for the original RTL. Verilator compiles the concurrent SVA and the `bind` files
with assertions enabled, then simulates boundary values, signed values, and
deterministic random inputs. Temporary libraries, testbenches, and build products
are deleted after the run. Logs and results stay in `formal/reports/`.

For an individual formal proof:

```sh
yosys -Q -T -s formal/abs_prove.ys
yosys -Q -T -s formal/add_prove.ys
yosys -Q -T -s formal/max_prove.ys
yosys -Q -T -s formal/min_prove.ys
```

The committed scripts use repository-relative paths. Run them from the root.

## Translation rules

| ACSL / metadata | Checker behavior |
| --- | --- |
| `requires` | One labeled assumption per clause, active when `reset && start_port` |
| `ensures` | One labeled assertion per clause, active when `reset && done_port` |
| `\result` | The metadata return port (`return_port`) |
| Signed C `int` | Sign-extend each 32-bit port into a signed 64-bit expression |
| `==>` inside an ACSL expression | Boolean implication: `!antecedent || consequent` |
| `assigns \nothing` | No C-visible memory side effects; these scalar DUTs have no memory interface |
| Active-low reset | Concurrent checks use `disable iff (!reset)` |
| Fixed latency of zero cycles | Overlapping, same-sample implication (`|->`); no `$past` or added delay |
| Start/done interface | Additional assertion: `done_port == start_port` outside reset |

Widening expressions matters: the `add` precondition checks the mathematical
sum against `2147483647` before any 32-bit wraparound. The `abs` precondition
excludes `INT_MIN`, whose positive counterpart is not representable as a C int.
All arithmetic in the current contracts fits the signed 64-bit intermediate
range. This is a restricted translator for the current scalar benchmarks, not
a full ACSL parser or a general mathematical-integer implementation. Unsupported
tokens, signatures, memory contracts, and nonzero/unknown latencies are rejected.

`assigns \nothing` does not mean that hardware controller registers or an idle
combinational output must remain constant. No such assertion is introduced.

The generator reads each C contract and validates stored metadata against a
fresh extraction from its RTL. It records input hashes and clause mappings in
`translation_manifest.json`. Each checker has comments containing the original
ACSL clauses and labels `requires_N_assume` and `ensures_N_assert`.

## What the proofs establish

The four integrated designs are `abs`, `add`, `max`, and `min`. Each formal
harness instantiates the actual original top module and its checker without
editing the RTL. All input values are symbolic. The assumptions restrict only
launched transactions to the C preconditions; reset and start are otherwise
unconstrained. The explicit FSM initialization in the original RTL is retained.

Yosys's built-in SAT solver proves all postconditions and the handshake by
temporal induction, including the base case. A successful induction proves
these properties for arbitrary execution length under the recorded assumptions;
it is not merely a two-cycle bounded test. Each SAT step represents one active
edge of the single clock. Inputs are defined two-state values; analog delay,
metastability, physical timing closure, and four-state simulation behavior are
outside this proof.

The concurrent `assert property`/`assume property` form is compiled and exercised
by Verilator. The Yosys frontend uses a conditional immediate-assertion form
of the same named Boolean predicates (`-D YOSYS`). For these zero-cycle
combinational designs, checking those predicates at every formal step establishes
the sampled concurrent properties. Yosys is not claimed to parse the concurrent
SVA or bind syntax. The formal harness instantiates checkers explicitly; the
simulation uses the separate bind files.

The runner also checks:

- A reachable transaction with reset deasserted, start and done asserted, and
  all preconditions satisfied, to guard against a vacuous proof.
- A one-bit corruption of the value observed by the checker produces a formal
  counterexample for every integrated design.
- `abs(INT_MIN)` and `add(INT_MAX, 1)` are excluded by their preconditions.
- Every original tracked file still matches its pre-work SHA-256 digest.

The `*_cover.ys` scripts use `-falsify` to find a witness contradicting
`transaction_witness == 0`. Their logs deliberately say `model found: FAIL!`:
here that means the requested valid transaction **was found**, not that an ACSL
postcondition failed. The mutation logs also intentionally contain `FAIL!`,
showing that the assertions caught the corrupt value. Only `*_prove.log` records
the genuine property proofs. `summary.json` distinguishes these outcomes.

## Files and current scope

- `sva/*_acsl.sv`: checker modules for all five C contracts.
- `sva/*_bind.sv`: four bind files targeting the exact RTL module names,
  including escaped identifiers for `abs`, `max`, and `min`.
- `formal/*_formal.sv`: four formal harnesses.
- `formal/*_prove.ys`: induction proof scripts.
- `formal/*_cover.ys`: transaction reachability scripts and witness JSON files.
- `formal/*_excluded_input.ys`: precondition exclusion checks for `abs` and `add`.
- `formal/reports/summary.json`: machine-readable outcomes and tool versions.
- `formal/reports/*_vectors.json`: native C input/output samples used in simulation.
- `formal/reports/original_files.sha256.json`: integrity baseline for all original files.

`sign.c` has a translated and syntax-checked checker and native C tests, but
there is no `sign.v` or sign metadata in the repository. Its checker therefore
exposes `clock`, `contract_valid`, `x`, and `result_value` as an integration
interface, without guessing a DUT mapping, latency, or reset polarity. It has
no bind, formal harness, or claimed hardware proof. Once Bambu RTL and metadata
are supplied, regenerate the checkers and extend the runner's `READY` list.

## Tool references

- [Yosys SAT proof and induction options](https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/sat.html)
- [Verilator assertion and build options](https://verilator.org/guide/latest/exe_verilator.html)
