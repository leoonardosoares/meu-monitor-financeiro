"""Sobe o app de demonstração e fotografa as telas: python shoot.py tema página [aba]."""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
tema, pagina = sys.argv[1], sys.argv[2]
aba = sys.argv[3] if len(sys.argv) > 3 else ""
altura = int(os.environ.get("ALTURA", "2000"))
porta = str(8600 + abs(hash((tema, pagina))) % 300)
env = dict(os.environ, DEMO_TEMA=tema, DEMO_PAGINA=pagina)
proc = subprocess.Popen(
    ["streamlit", "run", f"{D}/demo_app.py", "--server.port", porta,
     "--server.headless", "true", "--browser.gatherUsageStats", "false"],
    cwd=os.path.dirname(D), env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    time.sleep(6)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"))
        pg = b.new_page(viewport={"width": 1440, "height": altura})
        pg.goto(f"http://localhost:{porta}", wait_until="networkidle")
        time.sleep(7)
        if aba:
            pg.get_by_role("tab", name=aba).click()
            time.sleep(3)
        nome = f"{os.environ.get('SAIDA', D)}/shot_{tema}_{pagina[:8]}_{aba[:8]}.png".replace(" ", "_")
        pg.screenshot(path=nome)
        print(nome)
        b.close()
finally:
    proc.terminate()
    out = proc.stdout.read().decode(errors="ignore")
    erros = [l for l in out.splitlines() if "Error" in l or "Traceback" in l]
    if erros:
        print("\n".join(out.splitlines()[-30:]))
