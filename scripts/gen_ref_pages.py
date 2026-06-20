"""Generate API reference pages."""

from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

root = Path(__file__).parent.parent
package = "mast_transfer_tools"

for path in sorted((root / package).rglob("*.py")):
    module_path = path.relative_to(root).with_suffix("")
    parts = tuple(module_path.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = Path(*parts, "index.md")
    elif parts[-1] == "__main__":
        continue
    else:
        doc_path = Path(*parts).with_suffix(".md")

    if not parts:
        raise RuntimeError(f"Refusing to generate blank mkdocstrings identifier for {path}")

    ident = ".".join(parts)
    full_doc_path = Path("reference", doc_path)

    nav[parts] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(f"::: {ident}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(root))
