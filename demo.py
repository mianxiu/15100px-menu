import win32gui
import win32con
import dearpygui.dearpygui as dpg

import ctypes
from ctypes import c_int
dwm = ctypes.windll.dwmapi

dpg.create_context()

p1 = [0,0]
p2 = [10,0]
p3 = [10,10]
p4 = [0,10]
p5 = [0,0]

class MARGINS(ctypes.Structure):
  _fields_ = [("cxLeftWidth", c_int),
              ("cxRightWidth", c_int),
              ("cyTopHeight", c_int),
              ("cyBottomHeight", c_int)
             ]


dpg.create_viewport(title='overlay',always_on_top=True,decorated=False,clear_color=[0.0,0.0,0.0,0.0])

dpg.set_viewport_always_top(True)
dpg.create_context()
dpg.setup_dearpygui()

with dpg.window(label="About2",no_background=True, tag='bg_win'):
	with dpg.draw_node() as root :
		dpg.draw_polygon([p1,p2,p3,p4,p5], color=[0,255,0,255],fill=[0,0,255,255])
		dpg.apply_transform(root,dpg.create_scale_matrix([6,6])*dpg.create_translation_matrix([5,5]))


with dpg.window(label="About3",no_background=False, tag='bg_wi2'):
	with dpg.draw_node() as root :
		dpg.draw_polygon([p1,p2,p3,p4,p5], color=[0,255,0,255],fill=[0,0,255,255])
		dpg.apply_transform(root,dpg.create_scale_matrix([6,6])*dpg.create_translation_matrix([5,5]))

dpg.show_viewport()
dpg.toggle_viewport_fullscreen()

hwnd = win32gui.FindWindow(None, "overlay")
margins = MARGINS(-1, -1,-1, -1)
dwm.DwmExtendFrameIntoClientArea(hwnd, margins)

#enable this for click through otherwise always overtop
#win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT )



dpg.start_dearpygui()
dpg.destroy_context()
