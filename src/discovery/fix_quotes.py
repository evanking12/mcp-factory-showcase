from pathlib import Path

files = ["src/discovery/pe_parse.py", "src/discovery/import_analyzer.py"]

for f in files:
    p = Path(f)
    if p.exists():
        content = p.read_text(encoding="utf-8")
        new_content = content.replace('\\"\\"\\"', '"""')
        p.write_text(new_content, encoding="utf-8")
        print(f"Fixed {f}")
