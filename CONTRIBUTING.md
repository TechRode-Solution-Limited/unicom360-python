# Contributing

Thanks for helping. Issues and pull requests are welcome at
<https://github.com/TechRode-Solution-Limited/unicom360-python>. Report security problems
privately instead: see [SECURITY.md](SECURITY.md).

Two rules apply to everything in this repository (code, comments, docs, commit messages):
never write the em dash character, and add no AI attribution lines to commits or pull requests.

## Set up

Python 3.9 or later, and pip 25.1 or later (for dependency groups).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . --group dev
```

## Checks

CI runs all of these; run them before you push:

```sh
.venv/bin/ruff format --check
.venv/bin/ruff check
.venv/bin/mypy                 # strict, over src, tests and examples
.venv/bin/pytest               # the unit tests and the whole conformance suite
grep -rn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=dist $'\xe2\x80\x94' . && echo "em dash found"
```

### Other Python versions

CI tests Python 3.9 to 3.14. To run one locally without installing it, use its Docker image
(the source is copied, so the container never writes to your checkout):

```sh
docker run --rm -v "$PWD":/src:ro python:3.14-slim sh -c '
  cp -r /src /work && cd /work && rm -rf .venv &&
  pip install -q --upgrade pip && pip install -q -e . --group dev && pytest -q'
```

### The contract test

`tests/test_contract_prism.py` sends every call in `tests/conformance/requests.json` to a
[Prism](https://stoplight.io/open-source/prism) mock of `openapi.yaml` and fails on any request
Prism finds invalid. It is not part of the default run:

```sh
docker run --rm -p 4011:4010 -v /path/to/unicom360-openapi:/spec:ro stoplight/prism:5 \
  mock -h 0.0.0.0 --multiprocess=false /spec/openapi.yaml
UNICOM360_PRISM_URL=http://127.0.0.1:4011 .venv/bin/pytest -m contract
```

(`--multiprocess=false` avoids a crash of the Prism 5 image at start-up.)

## The conformance fixtures

`tests/conformance/` is a vendored copy of `conformance/` from
[unicom360-openapi](https://github.com/TechRode-Solution-Limited/unicom360-openapi), pinned by
the tag and sha256 in `tests/conformance/VERSION`. Never edit it by hand: the suite recomputes the
sha256 and fails on any change. To move to a new contract version:

```sh
cd ../unicom360-openapi && git checkout vX.Y.Z
scripts/sync-conformance ../unicom360-python/tests/conformance
scripts/sync-conformance --check ../unicom360-python/tests/conformance
```

Then update `CONTRACT_VERSION` in `src/unicom360/_version.py`, make the suite pass, update the
README's "targets" line and Known differences, and commit the fixtures with the code. The
fixtures never ship in the wheel or the sdist (CI checks both file lists).

Every vector of every fixture file runs through the public API; a vector the harness does not
understand fails, it is never skipped. When the contract adds a rule, extend `tests/harness.py`
rather than filtering vectors.

## Releasing

1. Update `__version__` in `src/unicom360/_version.py`.
2. In `CHANGELOG.md`, give the version's section today's date
   (`## [X.Y.Z] - YYYY-MM-DD`) and add the link at the bottom.
3. Commit, then tag and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

4. `release.yml` checks that the tag matches `__version__` and that the CHANGELOG has the
   section, runs every check on Python 3.9 to 3.14, builds the sdist and wheel, publishes them
   to PyPI with trusted publishing (the `pypi` environment), and creates the GitHub Release
   with the CHANGELOG section as its notes.

One-time PyPI setup: add a trusted publisher on PyPI for project `unicom360`, owner
`TechRode-Solution-Limited`, repository `unicom360-python`, workflow `release.yml`, environment
`pypi` (a "pending" publisher works before the first release). In the GitHub repository,
create the `pypi` environment.

### Publishing without GitHub Actions

When Actions is unavailable, publish from a clean checkout of the tag with Docker. `twine`
asks for your PyPI API token (user name `__token__`):

```sh
git checkout vX.Y.Z
docker run --rm -it -v "$PWD":/src -w /src python:3.13-slim sh -c "pip install build twine && python -m build && twine check dist/* && twine upload dist/*"
```

Then create the GitHub Release by hand from the CHANGELOG section.
