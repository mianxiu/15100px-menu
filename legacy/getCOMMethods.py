import win32com.client
import pythoncom

ProgID = "someProgramID"
com_object = win32com.client.Dispatch("Photoshop.Application")

for key in dir(com_object):
    method = getattr(com_object, key)
    if str(type(method)) == "<type 'instance'>":
        print(key)
        for sub_method in dir(method):
            if not sub_method.startswith("_") and not "clsid" in sub_method.lower():
                print(sub_method)
    else:
        print(method)
