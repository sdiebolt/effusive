# Effusive Agent Guidelines

This file guides AI coding agents working in this repository.

## What is Effusive

Effusive is a Python/MATLAB acquisition application for functional ultrasound imaging
on Verasonics Vantage hardware. Python provides the napari UI; MATLAB configures and
runs acquisition. EchoFrame and Verasonics/VSX are external runtime dependencies, not
part of this repository.

This is an **alpha application** under rapid iteration. Backward compatibility is not a
concern — prefer clear breaking changes over compatibility layers.

## Hardware and External Boundaries

- Do not edit EchoFrame or Verasonics/VSX files from this repository.
- Do not rename or restructure VSX structs (`Resource`, `Trans`, `TX`, `TW`,
  `Receive`, `Event`, `SeqControl`, and related structs) or EchoFrame structs.
- Treat acquisition, storage, and motor changes as hardware-sensitive: keep validation
  and error handling that prevents data loss or unsafe motion.
- Base-workspace MATLAB variables may be contracts with VSX or EchoFrame. Before
  renaming/removing one, search all references and run the relevant hardware smoke flow.

## Commands

Uses [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just).

```bash
uv sync                              # install dependencies
cp .env.template .env                # then set machine-specific paths
uv run --env-file .env effusive      # launch the application
just test                            # run tests with pytest --mpl
just test-verbose                    # run tests verbosely
just pre-commit                      # ruff, ty, codespell, docstring checks
just docs                            # build docs (Zensical)
just serve-docs                      # serve docs locally
```

Effusive also needs `ECHOFRAME_MEX_ROOT`, the directory containing the built
`echoframe_mex` MEX file. Build EchoFrame in its own checkout, following its README.
Use a prebuilt MEX matching the installed CUDA/MATLAB versions or build it there.

There is no automated hardware test suite. For acquisition changes, run the relevant
hardware smoke flows: run/stop, freeze/resume, recording, crop, and z-stack.

## Code Architecture

```text
src/effusive/        # Python package, CLI, config, MATLAB worker, napari plugin
src/effusive/napari/ # UI panels, commands, runtime state, UDP control, worker logic
src/effusive/assets/ # icons and packaged UI assets
+effusive/           # MATLAB package used by VSX/acquisition
+effusive/+bids/     # BIDS names, directories, tables
+effusive/+control/  # runtime control handling
+effusive/+echoframe/# EchoFrame setup and struct translation
+effusive/+motor/    # motor backends and movement helpers
+effusive/+napari/   # MATLAB-side napari callbacks/state helpers
+effusive/+rf/       # RF ensemble processing/storage
+effusive/+sequences/# Verasonics sequence/resource configuration
+effusive/+util/     # MATLAB utilities
+effusive/+vantage/  # Vantage hardware helpers
```

Keep napari's widget module as orchestration. Put reusable panels, UI state, polling,
and command handling in focused sibling modules.

## Python Conventions

- Target Python 3.11. Use `uv` for Python commands.
- Use absolute imports, `pathlib.Path` for paths, context managers for resources, and
  platformdirs for user-specific locations.
- Type all functions and methods. Use `numpy.typing` for arrays, `Literal` for closed
  string sets, and `TypedDict` for structured dictionaries crossing module boundaries.
- Use `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants,
  and leading `_` for private names. Never import private names across modules.
- Validate external input early; raise specific exceptions and preserve errors that
  prevent data loss.
- Use NumPy-style docstrings for all functions/methods, public and private. Use single
  backticks and Markdown autolinks.
- Comments explain non-obvious intent or constraints, end with periods, and use `TODO:`
  for incomplete work.

## MATLAB Conventions

- Target MATLAB R2024a. Use `camelCase` functions and `+packageName` namespaces.
- Use argument blocks to validate public function inputs when practical.
- Keep configuration in named structs, preserving exact field names/types required by
  Verasonics and EchoFrame.
- Do not use `global`. Callback shared state belongs in the base workspace via
  `evalin('base', ...)` and `assignin('base', ...)`; group reads at the start of a
  function and write changes back immediately.
- Do not add hard-coded paths. Keep MATLAB path setup in the application entry point and
  use configured/environment-provided roots.
- Comments end with periods and explain why.

## Tests and Docs

- Add focused automated tests for new pure-Python logic.
- For hardware-facing changes, document the manual smoke flow run.
- Documentation uses Zensical and mkdocstrings for Python and MATLAB. Keep docs and
  docstrings current when code structure or behavior changes.

## Git

- Do not commit generated acquisition data, MAT files, `data/`,
  `last_experiment_presets.json`, `.env`, or documentation build output.
- Commit messages follow Conventional Commits, e.g.
  `fix(napari): disable stop recording while paused`.
