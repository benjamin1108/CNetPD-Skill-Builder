# CNetPD-Skill-Builder Agent Rules

## Source Of Truth

All skill capabilities must be implemented in the builder source, templates, or runtime source under `src/cnetpd_skill_builder/`.

Do not hand-edit generated skill outputs as the source of truth:

- `skills/CNetPD-Skill/`
- `dist/CNetPD-Skill/`
- `dist/CNetPD-Skill.zip`
- `dist/CNetPD-Skill.skill`

When changing skill behavior, update the builder first, then regenerate with:

```bash
python3 tools/build_cnetpd_skill.py
```

Generated output changes are acceptable only when they are produced by the builder.
