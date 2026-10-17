"""TkDND failed load must destroy the partially initialized default Tk root."""
import sys, types, tkinter as tk
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import startup
class Broken(tk.Tk):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        raise RuntimeError("tkdnd unavailable")
def main():
    previous=sys.modules.get("tkinterdnd2")
    fake=types.ModuleType("tkinterdnd2")
    fake.TkinterDnD=types.SimpleNamespace(Tk=Broken)
    sys.modules["tkinterdnd2"]=fake
    try:
        try: root=startup._create_root()
        except tk.TclError as e:
            print("SKIP missing display:",e);return
        try:
            assert type(root) is tk.Tk
            assert tk._default_root is root
            v=tk.StringVar()
            v.set("Мои пациенты")
            assert tk.Label(root,textvariable=v).cget("text")=="Мои пациенты"
        finally: root.destroy()
        old=tk._default_root
        try: startup._create_root(require_dnd=True)
        except RuntimeError: pass
        else: raise AssertionError("Required TkDND failure silently ignored")
        assert tk._default_root is old
    finally:
        if previous is None:sys.modules.pop("tkinterdnd2",None)
        else:sys.modules["tkinterdnd2"]=previous
    print("STARTUP FALLBACK ROOT OK")
if __name__=="__main__":main()
