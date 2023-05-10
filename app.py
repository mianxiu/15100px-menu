
from pynput import mouse, keyboard
import dearpygui.dearpygui as dpg
import threading as thread
import time as time


def Worker():
    for i in range(10):
        print(i)
        time.sleep(1)
        
Worker()

def on_activate_h():
    print('<ctrl>+<alt>+h pressed')

def on_activate_i():
    print('<ctrl>+<alt>+i pressed')


with keyboard.GlobalHotKeys({
        '<ctrl>+<alt>+h': on_activate_h,
        '<ctrl>+<alt>+i': on_activate_i}) as h:
                h.join()



def save_callback(sender, data):
    print("Save Clicked")
    dpg.set_value(item="text001",value="21313")


# get monitor scale_factor
import ctypes
user32 = ctypes.windll.user32
O_Width = user32.GetSystemMetrics(0)
O_Height = user32.GetSystemMetrics(1)
user32.SetProcessDPIAware(2)
Width = user32.GetSystemMetrics(0)
Height = user32.GetSystemMetrics(1)
print(O_Width,O_Height,Width,Height,"Scale:",Width/O_Width)

SCALE_FACTOR = Width/O_Width


# get mouse position
mController = mouse.Controller()
print(mController.position)
mouseX = mController.position[0]
mouseY = mController.position[1]



dpg.create_context()

dpg.set_global_font_scale(SCALE_FACTOR)

print(dpg.get_mouse_pos())


# x_pos orignpos : scale 1:4 (may affected from monitor & scale)
dpg.create_viewport(title="Dear Pygui", clear_color=[0, 0, 0, 0],
                    always_on_top=True, height=round(250*SCALE_FACTOR), width=round(250*SCALE_FACTOR),x_pos=round(mouseX),y_pos=round(mouseY))



with dpg.window(label="MainWindow", tag="Primary Window"):
    dpg.add_text("Hello Word",label="text001")
    dpg.add_button(label="Save", callback=save_callback, tag="button1")
    with dpg.tooltip("button1"):
        dpg.add_text("i am a tips")
    dpg.add_input_text(label="string")
    dpg.add_slider_int(label="int")


    
    with dpg.popup(dpg.last_item()):
        dpg.add_text("A popup")




# def on_key_la(sender, app_data):
#     if dpg.is_key_down(dpg.mvKey_A):
#         print("Ctrl + A")
#         print("I'm hide")
#         print(dpg.get_all_items())
#         dpg.hide_item(21)
#         print(dpg.get_item_label(21))
#         dpg.set_viewport_height(0)
#         dpg.set_viewport_width(0)
        
            

        
# with dpg.handler_registry():
#     dpg.add_key_press_handler(dpg.mvKey_Control, callback=on_key_la)


dpg.show_style_editor()
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("Primary Window", True)
dpg.start_dearpygui()
dpg.destroy_context()


