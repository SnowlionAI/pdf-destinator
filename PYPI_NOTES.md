# PyPI Publishing Notes

Personal reference for publishing pdf-destinator to PyPI.

## Prerequisites

Install dev dependencies:
```bash
pip install -e ".[dev]"
```

This installs `build` and `twine`.

## Publishing Workflow

### 1. Bump Version

Edit `pyproject.toml` and update the version number:
```toml
version = "0.1.2"  # was "0.1.1"
```

Also update `pdf_destinator/__init__.py` if it has a `__version__`:
```python
__version__ = "0.1.2"
```

Version numbering convention:
- `0.1.x` - patch releases (bug fixes)
- `0.x.0` - minor releases (new features, backwards compatible)
- `x.0.0` - major releases (breaking changes)

### 2. Clean Previous Builds

```bash
rm -rf dist/ build/ *.egg-info/
```

### 3. Build the Package

```bash
python -m build
```

This creates:
- `dist/pdf_destinator-X.Y.Z.tar.gz` (source distribution)
- `dist/pdf_destinator-X.Y.Z-py3-none-any.whl` (wheel)

### 4. Upload to PyPI

**Test PyPI first (optional but recommended for new packages):**
```bash
python -m twine upload --repository testpypi dist/*
```

**Production PyPI:**
```bash
python -m twine upload dist/*
```

You'll be prompted for credentials. Use an API token (recommended):
- Username: `__token__`
- Password: `pypi-AgEI...` (your API token)

### 5. Verify

```bash
pip install --upgrade pdf-destinator
pdf-destinator --version
```

## API Token Setup

To avoid entering credentials each time, create `~/.pypirc`:
```ini
[pypi]
username = __token__
password = pypi-AgEIxxxxxxxxxxxxxxxx

[testpypi]
username = __token__
password = pypi-AgEIxxxxxxxxxxxxxxxx
```

Or use environment variables:
```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-AgEIxxxxxxxxxxxxxxxx
```

## Quick Reference

```bash
# Full release workflow
vim pyproject.toml                    # bump version
vim pdf_destinator/__init__.py        # bump __version__ if present
rm -rf dist/ build/ *.egg-info/
python -m build
python -m twine upload dist/*
git add -A && git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

## Links

- PyPI project: https://pypi.org/project/pdf-destinator/
- Test PyPI: https://test.pypi.org/project/pdf-destinator/
- API tokens: https://pypi.org/manage/account/token/
