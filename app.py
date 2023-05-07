
from pynput import mouse, keyboard
import dearpygui.dearpygui as dpg



def save_callback():
    print("Save Clicked")

mController = mouse.Controller()
print(mController.position)
mouseX = mController.position[0]
mouseY = mController.position[1]

dpg.create_context()
# x_pos orignpos : scale 1:4 (may affected from monitor & scale)
dpg.create_viewport(title="Dear Pygui", clear_color=[0, 0, 0, 0],
                    always_on_top=True, height=150, width=250,x_pos=mouseX*4,y_pos=mouseY)
dpg.setup_dearpygui()

with dpg.window(label="Example Window", tag="Primary Window"):
    dpg.add_text("Hello world")
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

