import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
svg = (root / "docs" / "icon.svg").read_text(encoding="utf-8")
html = ("<!doctype html><meta charset=\"utf-8\">\n<style>\n"
        "  html,body{margin:0;height:100%;background:transparent;\n"
        "    display:flex;align-items:center;justify-content:center}\n"
        "  svg{width:84%;height:84%;display:block}\n"
        "</style>\n" + svg)
(root / "docs" / "_icon_preview.html").write_text(html, encoding="utf-8")
print("wrote preview")
