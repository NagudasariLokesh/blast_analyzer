# blast_analyzer

Static blast radius analyzer for Python codebases.

## What it does

- Parses Python source into a directed dependency graph.
- Accepts structured change intent.
- Computes direct and indirect impacts.
- Produces explainable JSON and Markdown reports.

## Change intent format

```json
{
  "change_type": "api_modification",
  "target": "function:api.user_api.post_user",
  "modification": "add_optional_field"
}
```

Supported `change_type` values:

- `api_modification`
- `function_logic_change`
- `validation_rule_change`
- `refactor_shared_method`
- `data_model_change`

## Run

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-json '{"change_type":"function_logic_change","target":"function:services.user_service.create_user","modification":"adjust validation flow"}'
```

Or with a file:

```bash
python3 blast_analyzer.py --project-path project --intent-file intent.json
```

Or run interactively (single-line input):

```bash
python3 blast_analyzer.py --project-path project
```

Interactive input accepts any one of:

```text
function_logic_change|function:services.user_service.create_user|adjust validation flow
function_logic_change function:services.user_service.create_user adjust validation flow
{"change_type":"function_logic_change","target":"function:services.user_service.create_user","modification":"adjust validation flow"}
```

To see valid target IDs before selecting:

```bash
python3 blast_analyzer.py --project-path project --list-targets
```

## OpenAI intent inference

You can infer the change intent from a client-side diff/change file using OpenAI.

Recommended: configure a local `.env` file (auto-loaded at runtime):

```bash
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_ORG_ID=
OPENAI_PROJECT_ID=
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_RETRIES=2
EOF
```

Run:

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-from-openai \
  --client-change-file client_change.diff
```

Optional debug output for raw model response:

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-from-openai \
  --client-change-file client_change.diff \
  --openai-debug
```

You can also export env vars directly in your shell instead of using `.env`.

## SQLite cache (for repeat changes)

OpenAI-backed runs are cached by:

- codebase hash
- client change file hash
- OpenAI model
- prompt/analyzer versions

Default cache DB: `.blast_cache.sqlite3`

Use a custom DB path:

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-from-openai \
  --client-change-file client_change.diff \
  --cache-db /tmp/blast_cache.sqlite3
```

Disable cache:

```bash
python3 blast_analyzer.py \
  --project-path project \
  --intent-from-openai \
  --client-change-file client_change.diff \
  --no-cache
```

Outputs:

- `blast_report.json`
- `blast_report.md`

## Test

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
