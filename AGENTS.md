# Effusive Agent Guidelines

## Scope

Effusive is a Python/MATLAB acquisition application for functional ultrasound
imaging on Verasonics Vantage hardware. Python provides the napari UI; MATLAB
configures and runs the acquisition. EchoFrame and Verasonics are external
runtime dependencies, not part of this repository.

This project is alpha. Prefer clear breaking changes over compatibility layers.

## Environment and Commands

- Use `uv` for every Python command. Start with `uv sync`.
- Copy `.env.template` to `.env` and set the machine-specific paths. Effusive
  also needs `ECHOFRAME_MEX_ROOT`, the directory containing the built
  `echoframe_mex` MEX file.
- Build EchoFrame in its own checkout, following its README. Use a prebuilt MEX
  matching the installed CUDA/MATLAB versions or build it there; never modify
  EchoFrame from this repository.
- Launch Effusive with `uv run --env-file .env effusive`.
- Build documentation with `just docs`; preview it with `just serve-docs`.
- Run `just pre-commit` before handing off substantial Python or documentation
  changes. It formats, lints, type-checks, spell-checks, and validates docstrings.
- There is no automated hardware test suite. For changes affecting acquisition,
  run the relevant hardware smoke flows: run/stop, freeze/resume, recording,
  crop, and z-stack. Add focused automated tests for new pure-Python logic.

## Python

- Target Python 3.11. Use Ruff formatting and linting, and keep `ty check src/`
  clean.
- Use absolute imports, `pathlib.Path` for paths, context managers for resources,
  and platformdirs for user-specific locations.
- Type all functions and methods. Use `numpy.typing` for arrays, `Literal` for
  closed string sets, and `TypedDict` for structured dictionaries crossing
  module boundaries.
- Use `snake_case` for functions and variables, `PascalCase` for classes, and
  `UPPER_CASE` for constants. Private names begin with `_` and are never imported
  across module boundaries.
- Every function and method, including private helpers, has a NumPy-style
  docstring. Document parameters, returns, raised exceptions, and each element
  of multi-value returns separately. Use single backticks and Markdown autolinks.
- Keep napari's widget module as orchestration. Put reusable panels, UI state,
  polling, and command handling in focused sibling modules.
- Validate external input early, raise specific exceptions, and preserve errors
  that prevent data loss.
- Comments explain non-obvious intent or constraints, end with periods, and use
  `TODO:` for incomplete work. Do not comment what the code already says.

## MATLAB

- Target MATLAB R2024a. Use `camelCase` functions and `+packageName` namespaces.
- Use argument blocks to validate public function inputs when practical.
- Keep configuration in named structs rather than loose values. Preserve the
  exact field names and types required by Verasonics and EchoFrame.
- Do not use `global`. Callback shared state belongs in the base workspace via
  `evalin('base', ...)` and `assignin('base', ...)`: group reads at the start of
  a function, identify their owner in a comment, and write changes back
  immediately.
- Base-workspace variables can be contracts with VSX or EchoFrame. Before
  renaming or removing one, search all references and perform the relevant
  acquisition smoke flows.
- Do not add hard-coded paths. Keep MATLAB path setup in the application entry
  point and use configured/environment-provided roots.
- Comments end with periods and explain why. Use `TODO:` for incomplete work.

## External Boundaries

- Do not edit EchoFrame or Verasonics/VSX files.
- Do not rename or restructure VSX structs (`Resource`, `Trans`, `TX`, `TW`,
  `Receive`, `Event`, `SeqControl`, and related structs) or EchoFrame structs.
- Treat acquisition, storage, and motor changes as hardware-sensitive: retain
  validation and error handling rather than simplifying them away.

## Documentation and Git

- Documentation uses Zensical and mkdocstrings for Python and MATLAB. Keep docs
  and docstrings current when code structure or behaviour changes.
- Do not commit generated acquisition data, MAT files, `data/`,
  `last_experiment_presets.json`, `.env`, or documentation build output.
- Use Conventional Commit messages, for example
  `fix(napari): disable stop recording while paused`.
