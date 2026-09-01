# Witness fixture — do not edit as framework product code

This directory is a **reproducible installed-project witness** for tests only.

To change framework behavior, edit `src/`, `adapters/`, etc. at the repository root,
then regenerate witnesses:

```bash
python tests/generate_witness_projects.py --write
```

See `tests/fixtures/projects/README.md`.
