"""Generate the workflow node reference from the authoritative registry.

The markdown written to ``docs/workflow-nodes.md`` is derived entirely from
``serialize_registry()`` (the same presentation-safe payload the frontend
consumes), so the reference can never drift from the code. A pytest guard
(``tests/test_workflow_docs.py``) fails whenever the committed file differs
from the generator output.

Usage:
    python -m studio.workflows.docs            # rewrite docs/workflow-nodes.md
    python -m studio.workflows.docs --check    # exit 1 if the file is stale
"""

from __future__ import annotations

import json
from pathlib import Path

from .registry import serialize_registry
from .templates import serialize_templates

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "workflow-nodes.md"

_CATEGORY_ORDER = [
    "input", "audio", "timing", "ai", "assets", "video", "output", "utility", "testing",
]

_HEADER = (
    "<!-- GENERATED FILE — DO NOT EDIT BY HAND.\n"
    "     Regenerate with: python -m studio.workflows.docs\n"
    "     Source of truth: studio/workflows/registry.py -->\n"
)


def _fmt_default(value: object) -> str:
    """Render a config default as a stable inline-code literal."""
    if value is None:
        return "—"
    return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"


def _field_constraints(field: dict) -> str:
    parts: list[str] = []
    if field.get("options_source"):
        parts.append(f"options from `{field['options_source']}`")
    elif field.get("options") is not None:
        rendered = ", ".join(f"`{option}`" for option in field["options"])
        parts.append(f"one of {rendered}")
    if field.get("min") is not None or field.get("max") is not None:
        low = field.get("min", "−∞")
        high = field.get("max", "∞")
        parts.append(f"range {low}–{high}")
    if field.get("integer"):
        parts.append("integer")
    if field.get("min_length") is not None:
        parts.append(f"min length {field['min_length']}")
    if field.get("max_length") is not None:
        parts.append(f"max length {field['max_length']}")
    if field.get("pattern"):
        parts.append(f"pattern `{field['pattern']}`")
    if field.get("accept"):
        rendered = ", ".join(f"`{ext}`" for ext in field["accept"])
        parts.append(f"file types {rendered}")
    if field.get("display_options"):
        conditions = []
        for mode in ("show", "hide"):
            for name, values in (field["display_options"].get(mode) or {}).items():
                rendered = " or ".join(f"`{json.dumps(v)}`" for v in values)
                verb = "shown when" if mode == "show" else "hidden when"
                conditions.append(f"{verb} `{name}` is {rendered}")
        parts.extend(conditions)
    return "; ".join(parts) if parts else "—"


def _port_rows(ports: list[dict], *, is_input: bool) -> list[str]:
    rows = []
    for port in ports:
        flags = []
        if is_input:
            flags.append("required" if port.get("required") else "optional")
            if port.get("multiple"):
                flags.append("multiple connections")
        if port.get("conditional"):
            flags.append("conditional branch")
        rows.append(f"| `{port['id']}` | `{port['type']}` | {', '.join(flags) if flags else '—'} |")
    return rows


def _capability_summary(capabilities: dict) -> str:
    labels = {
        "retry": "retry",
        "cancel": "cancel",
        "error_output": "error output",
        "skip_optional": "skip-optional",
        "cacheable": "cacheable",
    }
    granted = [label for key, label in labels.items() if capabilities.get(key)]
    denied = [label for key, label in labels.items() if key in capabilities and not capabilities.get(key)]
    parts = []
    if granted:
        parts.append("supports " + ", ".join(granted))
    if denied:
        parts.append("no " + ", ".join(denied))
    return "; ".join(parts) if parts else "—"


def generate_node_reference() -> str:
    registry = serialize_registry()
    node_types = registry["node_types"]
    categories = registry["categories"]

    lines: list[str] = [_HEADER]
    lines.append("# Workflow Node Reference")
    lines.append("")
    lines.append(
        f"Registry version **{registry['registry_version']}** — "
        f"{len(node_types)} node types across {len(categories)} categories."
    )
    lines.append("")
    lines.append(
        "Connections require the source and target port to have the **same** type; "
        "there are no implicit conversions. `control` ports carry execution order "
        "only and never data. Dynamic ports (`stub.input`, `stub.output`, "
        "`workflow.output`) take the type chosen in the node's `port_type` setting."
    )
    lines.append("")

    # Port type vocabulary.
    lines.append("## Port types")
    lines.append("")
    lines.append("| Type |")
    lines.append("|---|")
    for port_type in registry["port_types"]:
        lines.append(f"| `{port_type}` |")
    lines.append("")

    # Category index.
    lines.append("## Categories")
    lines.append("")
    lines.append("| Category | Label | Color |")
    lines.append("|---|---|---|")
    for key in _CATEGORY_ORDER:
        info = categories[key]
        lines.append(f"| `{key}` | {info['label']} | `{info['color']}` |")
    lines.append("")

    # Nodes grouped by category, in registry order inside each category.
    for category_key in _CATEGORY_ORDER:
        members = [
            (type_key, definition)
            for type_key, definition in node_types.items()
            if definition["category"] == category_key
        ]
        if not members:
            continue
        lines.append(f"## {categories[category_key]['label']} nodes")
        lines.append("")
        for type_key, definition in members:
            lines.append(f"### {definition['display_name']} (`{type_key}`)")
            lines.append("")
            lines.append(f"{definition['description']}")
            lines.append("")
            lines.append(
                f"- **Type version:** {definition['type_version']}"
            )
            lines.append(f"- **Capabilities:** {_capability_summary(definition.get('capabilities', {}))}")
            lines.append("")
            inputs = definition.get("inputs", [])
            if inputs:
                lines.append("**Inputs**")
                lines.append("")
                lines.append("| Port | Type | Notes |")
                lines.append("|---|---|---|")
                lines.extend(_port_rows(inputs, is_input=True))
                lines.append("")
            else:
                lines.append("**Inputs:** none")
                lines.append("")
            outputs = definition.get("outputs", [])
            if outputs:
                lines.append("**Outputs**")
                lines.append("")
                lines.append("| Port | Type | Notes |")
                lines.append("|---|---|---|")
                lines.extend(_port_rows(outputs, is_input=False))
                lines.append("")
            else:
                lines.append("**Outputs:** none")
                lines.append("")
            fields = definition.get("config_schema", [])
            if fields:
                lines.append("**Configuration**")
                lines.append("")
                lines.append("| Field | Label | Widget | Default | Required | Constraints |")
                lines.append("|---|---|---|---|---|---|")
                for field in fields:
                    lines.append(
                        f"| `{field['name']}` | {field['label']} | `{field['type']}` "
                        f"| {_fmt_default(field.get('default'))} "
                        f"| {'yes' if field.get('required') else 'no'} "
                        f"| {_field_constraints(field)} |"
                    )
                lines.append("")
            else:
                lines.append("**Configuration:** none")
                lines.append("")

    # Built-in templates, generated from the same validated source.
    lines.append("## Built-in templates")
    lines.append("")
    lines.append("| Template | Name | Nodes | Description |")
    lines.append("|---|---|---|---|")
    for entry in serialize_templates():
        workflow = entry["workflow"]
        node_list = ", ".join(f"`{node['type']}`" for node in workflow["nodes"])
        lines.append(
            f"| `{entry['template_id']}` | {workflow['name']} "
            f"| {node_list} | {workflow.get('description', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate docs/workflow-nodes.md from the node registry.")
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="output markdown path")
    args = parser.parse_args(argv)

    content = generate_node_reference()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != content:
            print(f"STALE: {args.output} does not match the registry. "
                  "Run: python -m studio.workflows.docs")
            return 1
        print(f"OK: {args.output} matches the registry.")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
