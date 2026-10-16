"""Small/scaled screens must retain access to the main create button."""
import os
import tempfile
import tkinter as tk

def find_text_widget(root,needle):
    stack=[root]
    while stack:
        widget=stack.pop()
        try:
            if widget.winfo_class()=="Canvas":
                for item in widget.find_all():
                    if widget.type(item)=="text" and needle in str(widget.itemcget(item,"text")): return widget
            t=widget.cget("text") if "text" in widget.keys() else ""
            if needle in str(t): return widget
        except tk.TclError: pass
        stack.extend(widget.winfo_children())
    return None

def main():
    os.environ.setdefault("APPDATA",tempfile.mkdtemp(prefix="small-screen-"))
    from app_initialization import usable_screen_size
    assert usable_screen_size(1920,1080)==(1904,1024)
    w,h=usable_screen_size(911,512)
    assert w<=911 and h<=472
    try:
        from startup import _create_root
        root=_create_root(require_dnd=False)
    except Exception as exc:
        print(f"SKIP live check: {exc}")
        return
    root.winfo_screenwidth=lambda:911
    root.winfo_screenheight=lambda:512
    try:
        from app import CombinedMedicalDiaryApp
        app=CombinedMedicalDiaryApp(root)
        for _ in range(20):root.update()
        assert root.winfo_height()<=472,root.winfo_height()
        mw,mh=root.minsize()
        assert mh<=472 and mw<=911,(mw,mh)
        viewport=app._main_viewport
        target=find_text_widget(root,"Создать и сохранить")
        assert target is not None,"create button not found"
        viewport.yview_moveto(1.0)
        for _ in range(10):root.update()
        top=viewport.winfo_rooty()
        bottom=top+viewport.winfo_height()
        ty=target.winfo_rooty()
        assert top<=ty and ty+target.winfo_height()<=bottom+2,(top,bottom,ty,target.winfo_height())
        assert app._main_viewport_scrollbar.winfo_ismapped()
    finally:root.destroy()
    print("MAIN WINDOW SMALL SCREEN REGRESSION OK")

if __name__=="__main__":main()
