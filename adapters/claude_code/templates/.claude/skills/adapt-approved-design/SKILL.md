---
name: adapt-approved-design
description: Adapt an authoritative Design Contract only within declared free zones and tolerances.
---

# Adapt approved design

Use when `design_mode` is `adapt`.

1. Load the Design Contract and list `free_zones` and `tolerances`.
2. Refuse adaptations outside declared free zones.
3. Preserve mandatory text, elements, navigation and states — authoritative
   structure and content remain binding.
4. Record each adaptation with the contract tolerance rule that permits it.
   Every allowed adaptation cites a Design Contract rule.
5. Escalate design-system conflicts instead of choosing silently.
