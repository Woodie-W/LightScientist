---
name: fuzz-setup
description: Set up a fuzzing experiment environment. Clones and builds the fuzzer source locally, compiles targets with instrumentation, prepares seed corpora, and validates with a smoke test. Use when starting a new experiment or switching targets.
---

# Fuzz Setup

Prepare everything needed to run a fuzzing experiment: fuzzer source code, target compilation, seed corpus, and smoke test. Everything runs locally (the entire project runs inside a container with all dependencies pre-installed).

## Inputs

The caller (user, first-layer controller, or current stage supervisor) provides:

- **Target**: source code path or project name (e.g., `libxml2`, `openssl`)
- **Fuzzer**: which fuzzer to use (e.g., `aflpp`, `libfuzzer`, `honggfuzz`)
- **Idea description**: what modification is being tested
- **Base config**: optional path to a fuzzer config YAML in `configs/fuzzers/`

If any of these are missing, ask the user.

## Procedure

### 1. Set Up Fuzzer Source Code

The fuzzer source code lives in `fuzzers/<name>/` — this is the codebase the agent will **read and modify** during research.

**If `fuzzers/aflpp/` does not exist** (first time setup):

```bash
bash fuzzers/setup-aflpp.sh

git add fuzzers/aflpp/
git commit -m "add AFL++ source (baseline for experiments)"
```

**If `fuzzers/aflpp/` already exists**: verify it builds cleanly:

```bash
cd fuzzers/aflpp && make -j$(nproc) source-only
```

The locally-built fuzzer binary is at `fuzzers/aflpp/afl-fuzz`, and the compiler wrapper is at `fuzzers/aflpp/afl-clang-fast`. Always use these local paths.

### 2. Read Fuzzer Source (Critical!)

Before any experiment, **deeply read the fuzzer source code** relevant to the research direction. For AFL++, the key files are:

| File | Purpose |
|------|---------|
| `fuzzers/aflpp/src/afl-fuzz-one.c` | Mutation strategies: havoc, splice, deterministic |
| `fuzzers/aflpp/src/afl-fuzz-queue.c` | Seed queue management, scheduling, calibration |
| `fuzzers/aflpp/src/afl-fuzz-bitmap.c` | Coverage bitmap, edge counting, novelty detection |
| `fuzzers/aflpp/src/afl-fuzz-run.c` | Target execution, fork server, timeout handling |
| `fuzzers/aflpp/src/afl-fuzz-state.c` | Global state, initialization, configuration |
| `fuzzers/aflpp/include/afl-fuzz.h` | Main data structures (`afl_state_t`, `queue_entry`) |

Understanding the source is essential for generating meaningful improvements.

### 3. Load Fuzzer Config

Load the adapter config from `configs/fuzzers/<fuzzer>.yaml` for default flags and metric mappings:

```bash
FUZZER_DIR="$(pwd)/fuzzers/aflpp"
export AFL_PATH="$FUZZER_DIR"
export PATH="$FUZZER_DIR:$PATH"
```

### 4. Prepare Target

```bash
mkdir -p phase2-experiment/targets
```

**If target is a known benchmark** (listed in `configs/benchmarks/`):
- Follow the benchmark config to download/build the target
- Use the benchmark's seed corpus

**If target is local source**:
- Read the build system (Makefile, CMakeLists.txt, configure, etc.)
- Compile with the locally-built fuzzer's compiler:
  ```bash
  export CC="$(pwd)/fuzzers/aflpp/afl-clang-fast"
  export CXX="$(pwd)/fuzzers/aflpp/afl-clang-fast++"
  export CFLAGS="-fsanitize=address,undefined -g"
  export CXXFLAGS="$CFLAGS"
  ```
- Place the instrumented binary in `phase2-experiment/targets/`

If a target requires libraries not yet installed, install them with `apt-get install`.

### 5. Prepare Seed Corpus

```bash
mkdir -p phase2-experiment/seeds
```

- If the target has a test corpus, copy it to `phase2-experiment/seeds/`
- If no seeds exist, create minimal valid inputs for the target's input format
- Minimize the corpus if the fuzzer supports it:
  ```bash
  fuzzers/aflpp/afl-cmin -i raw_seeds/ -o phase2-experiment/seeds/ -- ./target @@
  ```

### 6. Create Experiment Script

Generate `phase2-experiment/fuzz_experiment.sh` from the template `templates/fuzz_experiment.sh.tmpl`, or write it directly. The script MUST:

- Accept `--duration`, `--output-dir`, `--trial-id` arguments
- Set `set -euo pipefail`
- Run the fuzzer with the configured arguments
- Output `METRIC` lines at the end:
  ```
  METRIC branch_cov=<number>
  METRIC unique_crashes=<number>
  METRIC throughput_execs_per_sec=<number>
  ```
- Collect coverage data using `python3 tools/coverage.py` after the run
- Collect crash data using `python3 tools/crash.py` after the run

### 7. Smoke Test

Run a 60-second sanity check:

```bash
cd phase2-experiment
bash fuzz_experiment.sh --duration 60s --output-dir smoke-test --trial-id 0
```

Verify:
- Exit code is 0
- METRIC lines are present in the output
- Coverage data was collected
- The fuzzer actually ran (check for bitmap/coverage files)

If the smoke test fails, diagnose and fix before proceeding. Common issues:
- Missing shared libraries → `apt-get install`
- Incorrect harness → fix the fuzzing harness
- Permission errors → adjust file permissions

### 8. Report Setup Complete

Create or update `phase2-experiment/SETUP_COMPLETE.md`:

```markdown
# Experiment Setup

- **Target**: <name> (<path>)
- **Fuzzer**: <name> (<version>)
- **Instrumentation**: <compiler flags>
- **Seed corpus**: <count> files, <total size>
- **Smoke test**: PASSED (<coverage> edges in 60s)
- **Experiment script**: `fuzz_experiment.sh`
- **Timestamp**: <ISO timestamp>
```

Commit all setup artifacts:

```bash
git add -A
git commit -m "fuzz-setup: configure <fuzzer> for <target>

Instrumented binary, seed corpus, and experiment script ready.
Smoke test passed: <N> edges covered in 60s."
```

## Output

- `phase2-experiment/targets/` — instrumented binaries
- `phase2-experiment/seeds/` — minimized seed corpus
- `phase2-experiment/fuzz_experiment.sh` — experiment runner script
- `phase2-experiment/SETUP_COMPLETE.md` — setup validation report

The experiment is now ready for `fuzz-loop` to begin iterating.
