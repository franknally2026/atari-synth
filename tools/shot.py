import os,re,sys,time,subprocess
REPO=os.path.expanduser("~/AltirraSDL")
SDK=REPO+"/src/AltirraSDL/AltirraBridge/sdk/python"
EMU=REPO+"/build/linux-release/src/AltirraSDL/AltirraSDL"
HERE=os.path.dirname(os.path.abspath(__file__))
XEX=os.path.abspath(HERE+"/../synth.xex"); SHOTS=os.path.abspath(HERE+"/../shots")
LOG=SHOTS+"/emu.log"; os.makedirs(SHOTS,exist_ok=True)
sys.path.insert(0,SDK)
from altirra_bridge import AltirraBridge
log=open(LOG,"w")
p=subprocess.Popen([EMU,"--bridge","--headless"],stdout=log,stderr=subprocess.STDOUT)
tok=None
for _ in range(200):
    try:
        m=re.search(r'token-file:\s*(\S+)',open(LOG).read())
        if m: tok=m.group(1); break
    except FileNotFoundError: pass
    time.sleep(0.05)
for _ in range(40):
    if tok and os.path.exists(tok): break
    time.sleep(0.05)
a=AltirraBridge.from_token_file(tok)
a.boot(XEX); a.frame(300)
out=sys.argv[1] if len(sys.argv)>1 else SHOTS+"/gr8_test.png"
a.screenshot(out); print("wrote",out)
p.kill(); p.wait()
