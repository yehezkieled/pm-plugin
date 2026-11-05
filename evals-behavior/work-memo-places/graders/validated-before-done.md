---
type: tool_used
tool: Agent
input_match: '"subagent_type":\s*"pm:validator"'
min: 1
---
---
type: tool_used
tool: Bash
input_match: 'pm\.py validated .*--verdict pass'
min: 1
---
