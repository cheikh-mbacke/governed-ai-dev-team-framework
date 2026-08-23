# Adopter checklist

Before using the framework on a real project:

- [ ] Install the framework into the repository.
- [ ] Fill project ID/name and repository type.
- [ ] Fill source/test/config roots in `.ai-team/project-profile.yaml`.
- [ ] Fill setup/build/lint/typecheck/test commands.
- [ ] Identify human authorities for product, Constitution, production release and final acceptance.
- [ ] Add product material under `docs/product/` or register its actual locations.
- [ ] Register every authoritative source in `.ai-team/sources/source-registry.yaml`.
- [ ] Review and customize risk/staffing defaults.
- [ ] Review and customize permission rules and blocked command classes.
- [ ] Configure protected branch / required CI checks outside Cursor.
- [ ] Configure CODEOWNERS or equivalent for Constitution and security configuration.
- [ ] Ensure production credentials are not available to ordinary developer agents.
- [ ] Run `python scripts/ai-team/validate.py`.
- [ ] Run `/compile-project` and inspect G0/G1 before allowing implementation.
