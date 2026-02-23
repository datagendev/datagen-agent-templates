# DataGen Agent Templates

Pre-built agent templates for [DataGen](https://datagen.dev). Each template is a self-contained agent kit -- agent definition, scripts, context docs, and setup guide -- ready to install and run with Claude Code.

## Available Templates

| Template | Category | Description |
|----------|----------|-------------|
| [linkedin-engagement](templates/linkedin-engagement/) | Sales | Monitor LinkedIn profiles, capture engagers, enrich contacts, export to CSV |

## Quick Start

### Using the DataGen plugin (recommended)

```bash
# List available templates
/datagen:fetch-agent

# Install a specific template
/datagen:fetch-agent linkedin-engagement
```

### Manual installation

1. Clone this repo
2. Copy the template files into your project:
   ```bash
   # Copy agent definition
   cp templates/linkedin-engagement/agent.md .claude/agents/linkedin-engagement.md

   # Copy supporting files
   cp -r templates/linkedin-engagement/scripts linkedin-engagement/scripts
   cp -r templates/linkedin-engagement/context linkedin-engagement/context
   cp -r templates/linkedin-engagement/learnings linkedin-engagement/learnings
   mkdir -p linkedin-engagement/tmp
   ```
3. Set required environment variables (see template README)
4. Connect required MCP servers at [app.datagen.dev/tools](https://app.datagen.dev/tools)

## Template Structure

Each template follows a standard layout:

```
templates/<agent-id>/
  manifest.json          # Machine-readable metadata
  README.md              # Human setup guide
  agent.md               # Claude Code agent definition
  mcps.md                # Required DataGen MCP servers
  scripts/               # Python scripts the agent runs
  context/               # Domain knowledge docs
  learnings/             # Failure logs (grows with use)
  tmp/                   # Intermediate outputs (gitignored)
```

## How Templates Work

Templates follow the **script-based output pattern** (RLM-aligned):

1. Scripts call DataGen tools and save results to `tmp/` as JSON
2. The agent reads `tmp/` outputs to review and decide next steps
3. This prevents context bloat and enables recovery from failures

Each agent definition (`agent.md`) uses relative paths, so it works wherever installed.

## Contributing

### Adding a new template

1. Create a directory under `templates/` with your agent ID
2. Follow the standard template structure above
3. Create a `manifest.json` validated against `schema/manifest.schema.json`
4. Add your template to `registry.json`
5. Submit a PR

### Manifest schema

All `manifest.json` files must conform to the JSON Schema at `schema/manifest.schema.json`. Validate with:

```bash
npx ajv validate -s schema/manifest.schema.json -d templates/your-agent/manifest.json
```

### Template guidelines

- Agent IDs must be lowercase with hyphens only (`my-agent-name`)
- Scripts should be standalone with their own argument/env handling
- Use `datagen-python-sdk` for tool execution, not raw API calls
- Include a preflight script that checks all prerequisites
- Document required MCP servers in `mcps.md`
- Start `learnings/common_failures_and_fix.md` with a header but no entries

## Shared Resources

The `_shared/` directory contains reusable components:

- `_shared/skills/datagen-setup/` -- Common skill for verifying DataGen is configured
- `_shared/scripts/preflight_base.py` -- Base preflight checks (API key, SDK, connectivity)

Templates can reference shared skills in their `manifest.json` via the `shared_skills` field.

## License

MIT
