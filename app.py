
from pynput import mouse, keyboard
import dearpygui.dearpygui as dpg



def save_callback(sender, data):
    print("Save Clicked")
    dpg.set_value(item="text001",value="21313")



import ctypes
user32 = ctypes.windll.user32
O_Width = user32.GetSystemMetrics(0)
O_Height = user32.GetSystemMetrics(1)
user32.SetProcessDPIAware(2)
Width = user32.GetSystemMetrics(0)
Height = user32.GetSystemMetrics(1)
print(O_Width,O_Height,Width,Height,"Scale:",Width/O_Width)



mController = mouse.Controller()
print(mController.position)
mouseX = mController.position[0]
mouseY = mController.position[1]

SCALE_FACTOR = Width/O_Width

dpg.create_context()

dpg.set_global_font_scale(SCALE_FACTOR)

print(dpg.get_mouse_pos())
dpg.show_style_editor()

# x_pos orignpos : scale 1:4 (may affected from monitor & scale)
dpg.create_viewport(title="Dear Pygui", clear_color=[0, 0, 0, 0],
                    always_on_top=True, height=round(250*SCALE_FACTOR), width=round(250*SCALE_FACTOR),x_pos=round(mouseX),y_pos=round(mouseY))
dpg.setup_dearpygui()

with dpg.window(label="Example Window", tag="Primary Window"):
    dpg.add_text("Hello Word",label="text001")
    dpg.add_button(label="Save", callback=save_callback, tag="button1")
    with dpg.tooltip("button1"):
        dpg.add_text("i am a tips")
    dpg.add_input_text(label="string")
    dpg.add_slider_int(label="int")


    
    with dpg.popup(dpg.last_item()):
        dpg.add_text("A popup")

dpg.show_viewport()
dpg.set_primary_window("Primary Window", True)
dpg.start_dearpygui()
dpg.destroy_context()

