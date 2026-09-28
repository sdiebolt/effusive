set windows-shell := ["pwsh.exe", "-c"]

# Print the help message.
@help:
    echo "Usage: just [RECIPE]\n"
    just --list

# Build documentation.
docs:
    uv run zensical build --strict

# Serve documentation locally for development.
serve-docs:
    uv run zensical serve

# Clean documentation build artifacts.
[unix]
clean-docs: 
    rm -rf .cache/ site/

# Clean documentation build artifacts.
[windows]
clean-docs:
    foreach ($p in '.cache', 'site') { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }

# Run all tests.
test:
    uv run pytest tests/ --mpl

# Run tests with verbose output.
test-verbose:
    uv run pytest tests/ -v --mpl

# Run all pre-commit hooks.
pre-commit:
    uv run prek run --all-files

# Aliases
alias d := docs
alias cd := clean-docs
alias sd := serve-docs
alias t := test
alias tv := test-verbose
alias pc := pre-commit
