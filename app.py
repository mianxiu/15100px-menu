

import mouse
import keyboard
import dearpygui.dearpygui as dpg
import threading as thread
import time as time
import get_monitor_scale_factor

import win32gui

import win32gui
import win32process

# 获取激活窗口句柄
hwnd = win32gui.GetForegroundWindow()

# 获取窗口所属进程ID
pid = win32process.GetWindowThreadProcessId(hwnd)[1]

# 获取进程名

print("激活窗口所属进程ID：", pid)


SCALE_FACTOR = get_monitor_scale_factor.getMonitorScaleFactor()


def getMousePos():
    # get mouse position
    mousePos = mouse.get_position()
    print(mousePos)
    mouseX = mousePos[0]
    mouseY = mousePos[1]
    return [mouseX,mouseY]

CURRENT_MOUSE_POS = getMousePos()

DEFAULT_WIDTH = 250*SCALE_FACTOR
DEFAULT_HEIGHT = 250*SCALE_FACTOR



def drawGui(*args):
    
        def save_callback(sender, data):
            print("Save Clicked")
            dpg.set_value(item="text001",value=time.localtime())
    
        dpg.create_context()
        
        # change global theme scale
        dpg.set_global_font_scale(SCALE_FACTOR)
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                itemSpacing = round(dpg.mvStyleVar_ItemSpacing)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,itemSpacing,itemSpacing, category=dpg.mvThemeCat_Core)
                itemInnerSpacing = dpg.mvStyleVar_ItemInnerSpacing
                dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing,itemInnerSpacing,itemInnerSpacing ,category=dpg.mvThemeCat_Core)
        dpg.bind_theme(global_theme)


        print(dpg.get_mouse_pos())


        dpg.create_viewport(title="Dear Pygui", decorated=False,
                            clear_color=[0, 0, 0, 0], always_on_top=True, width=round(DEFAULT_WIDTH),height=round(DEFAULT_HEIGHT), x_pos=round(CURRENT_MOUSE_POS[0]),y_pos=round(CURRENT_MOUSE_POS[1]))

        with dpg.window(label="MainWindow", tag="Primary Window"):
            dpg.add_text("Hello Word",tag="text001")
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


def startGuiThread():
    t1 = GuiThread(drawGui)
    t1.start()
   #t1.join()

class GuiThread(thread.Thread):
    def __init__(self,func,*args):
        thread.Thread.__init__(self)
        self.func = func
        self.args = args
        
    def run(self):
        self.func(*self.args)
    

# Theard()
if __name__ == '__main__':
    
    startGuiThread()
    

    
    
    def on_activate_tab():
        print('caps lock')
        dpg.set_viewport_pos(getMousePos())
        
        dpg.set_viewport_height(DEFAULT_HEIGHT)
        dpg.set_viewport_width(DEFAULT_WIDTH)
        
        
        import pygetwindow as gw
        print(gw.getActiveWindowTitle())

 
    
    def on_activate_h():
        print('<ctrl>+<alt>+h pressed')       
        print(dpg.get_all_items())
        dpg.show_debug()
        #dpg.show_item("Primary Window")

        
        dpg.set_viewport_pos(getMousePos())

    def on_activate_i():
        print('<ctrl>+<alt>+i pressed')
        #dpg.hide_item("Primary Window")
        dpg.set_viewport_height(0)
        dpg.set_viewport_width(0)
        
    keyboard.add_hotkey("tab",on_activate_tab,suppress=True)
    #keyboard.add_hotkey("capslock",on_activate_tab)
    keyboard.add_hotkey('ctrl+alt+h',on_activate_h)
    
    keyboard.add_hotkey('ctrl+alt+i',on_activate_i)

    # with keyboard.GlobalHotKeys({
    #         '<ctrl>+<alt>+h': on_activate_h,
    #         '<ctrl>+<alt>+i': on_activate_i,
    #         '<tab>':on_activate_tab
    #         }) as h:
    #                 h.join()


    







