import pythoncom
from win32com.shell import shell, shellcon
import win32com.server.policy

# Identificatore univoco universale per l'interfaccia IDropTarget
IID_IDropTarget = "{00000122-0000-0000-C000-000000000046}"

class DropTarget:
    _com_interfaces_ = [IID_IDropTarget]
    _public_methods_ = ['DragEnter', 'DragOver', 'DragLeave', 'Drop']

    def __init__(self, callback):
        self.callback = callback

    def DragEnter(self, data_object, key_state, point, effect):
        return shellcon.DROPEFFECT_COPY

    def DragOver(self, key_state, point, effect):
        return shellcon.DROPEFFECT_COPY

    def DragLeave(self):
        return 0

    def Drop(self, data_object, key_state, point, effect):
        try:
            format_etc = (shellcon.CF_HDROP, None, pythoncom.DVASPECT_CONTENT, -1, pythoncom.TYMED_HGLOBAL)
            stg_medium = data_object.GetData(format_etc)
            files = shell.DragQueryFile(stg_medium.data)
            if files:
                self.callback(files)
        except Exception as e:
            print(f"Errore Drop: {e}")
        return shellcon.DROPEFFECT_COPY

def register_drop_target(widget, callback):
    try:
        pythoncom.OleInitialize()
    except:
        pass # Già inizializzato
        
    hwnd = widget.winfo_id()
    target_raw = DropTarget(callback)
    target_com = win32com.server.policy.CreateWrapper(target_raw, IID_IDropTarget)
    shell.RegisterDragDrop(hwnd, target_com)
    return target_com