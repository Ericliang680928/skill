---
name: template-skill
description: Replace with a description of what this skill does and when Claude should use it. Be specific about trigger phrases and inputs, since this text decides when the skill loads.
---

# Skill Name

One-paragraph summary of what the skill accomplishes.

## Inputs
- What the user must provide
- Optional inputs and their defaults

## Steps
1. First step (name any helper script in `scripts/`)
2. Second step
3. Report the result and anything imperfect

## Rules
- Approval gates: what to confirm before costly or irreversible actions
- Never commit secrets
- How to handle failures

## Layout
```
my-skill/
├── SKILL.md      # required: frontmatter (name, description) + instructions
├── scripts/      # optional: helper code Claude can run
└── references/   # optional: longer docs loaded only when needed
```
