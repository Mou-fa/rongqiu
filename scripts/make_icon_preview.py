import pathlib, sys
root = pathlib.Path(__file__).resolve().parents[1]
name = sys.argv[1] if len(sys.argv) > 1 else "icon.svg"
svg = (root / "docs" / name).read_text(encoding="utf-8")
html = ("<!doctype html><meta charset=\"utf-8\">\n<style>\n"
        "  html,body{margin:0;height:100%;background:transparent;\n"
        "    display:flex;align-items:center;justify-content:center}\n"
        "  svg{width:88%;height:88%;display:block}\n"
        "</style>\n" + svg)
out = root / "docs" / ("_preview_" + name.replace(".svg", ".html"))
out.write_text(html, encoding="utf-8")
print("wrote", out)
