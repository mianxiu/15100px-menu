import mouse
import keyboard
import dearpygui.dearpygui as dpg
import threading as thread
import time as time
import get_monitor_scale_factor

import win32gui
import win32process


SCALE_FACTOR = get_monitor_scale_factor.getMonitorScaleFactor()


def getMousePos():
    # get mouse position
    mousePos = mouse.get_position()
    print(mousePos)
    mouseX = mousePos[0]
    mouseY = mousePos[1]
    return [mouseX, mouseY]

FOCUS_PROGRAM_CLASSNAME = "Photoshop"
OPEN_HOTKEY = "tab"

CURRENT_MOUSE_POS = getMousePos()

DEFAULT_WIDTH = 250 * SCALE_FACTOR
DEFAULT_HEIGHT = 250 * SCALE_FACTOR

IS_ADD_TAB = False
FOREGROUNDWINDOW_HWND = 0
FOREGROUNDWINDOW_CLASSNAME = ""

def drawGui(*args):
    def save_callback(sender, data):
        print("Save Clicked")
        dpg.set_value(item="text001", value=time.localtime())

    dpg.create_context()

    # change global theme scale
    dpg.set_global_font_scale(SCALE_FACTOR)
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            itemSpacing = round(dpg.mvStyleVar_ItemSpacing)
            dpg.add_theme_style(
                dpg.mvStyleVar_ItemSpacing,
                itemSpacing,
                itemSpacing,
                category=dpg.mvThemeCat_Core,
            )
            itemInnerSpacing = dpg.mvStyleVar_ItemInnerSpacing
            dpg.add_theme_style(
                dpg.mvStyleVar_ItemInnerSpacing,
                itemInnerSpacing,
                itemInnerSpacing,
                category=dpg.mvThemeCat_Core,
            )
    dpg.bind_theme(global_theme)

    print(dpg.get_mouse_pos())

    dpg.create_viewport(
        title="Dear Pygui",
        decorated=False,
        vsync=True,
        clear_color=[0, 0, 0, 0],
        always_on_top=True,
        width=round(DEFAULT_WIDTH),
        height=round(DEFAULT_HEIGHT),
        x_pos=round(CURRENT_MOUSE_POS[0]),
        y_pos=round(CURRENT_MOUSE_POS[1]),
    )

    with dpg.window(label="MainWindow", tag="Primary Window"):
        dpg.add_text("Hello Word", tag="text001")
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


def windowFocusHook(*args):
    global FOREGROUNDWINDOW_HWND,FOREGROUNDWINDOW_CLASSNAME,FOCUS_PROGRAM_CLASSNAME
    def on_activate_tab():
            # hwnd = win32gui.GetForegroundWindow()

            # 获取窗口所属进程ID
            # pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            # className = win32gui.GetClassName(hwnd)
            # 获取进程名
            # print("激活窗口所属进程ID：", pid)            
            # print(className)
            # print(win32gui.GetCursorPos())

            if FOREGROUNDWINDOW_CLASSNAME == FOCUS_PROGRAM_CLASSNAME:
                # import pygetwindow as gw

                # print(gw.getActiveWindowTitle())

                rect = win32gui.GetWindowRect(FOREGROUNDWINDOW_HWND)

                x = rect[0]
                y = rect[1]
                maxX = rect[2]
                maxY = rect[3]
                w = rect[2] - x
                h = rect[3] - y

                print("\t    Size: (%d, %d)" % (w, h))

                mousePos = getMousePos()

                if (mousePos[0] > x and mousePos[0] < maxX) and (
                    mousePos[1] > y and mousePos[1] < maxY
                ):

                    mousePosX = (
                        mousePos[0]
                        if mousePos[0] + DEFAULT_WIDTH < maxX
                        else (maxX - DEFAULT_WIDTH)
                    )
                    mousePosY = (
                        mousePos[1]
                        if mousePos[1] + DEFAULT_HEIGHT < maxY
                        else (maxY - DEFAULT_HEIGHT)
                    )

                    dpg.set_viewport_pos((mousePosX, mousePosY))

                    # global OVERLAYER_IS_SHOW
                    # OVERLAYER_IS_SHOW = True if OVERLAYER_IS_SHOW is False else False

                    # if OVERLAYER_IS_SHOW is True:
                    dpg.set_viewport_height(DEFAULT_HEIGHT)
                    dpg.set_viewport_width(DEFAULT_WIDTH)
                        # print(OVERLAYER_IS_SHOW)
                    # else:
                    #     dpg.set_viewport_height(0)
                    #     dpg.set_viewport_width(0)
                        # print(OVERLAYER_IS_SHOW)
    
    
    import hook
    def callback():
        
        global IS_ADD_TAB,FOREGROUNDWINDOW_HWND,FOREGROUNDWINDOW_CLASSNAME,FOCUS_PROGRAM_CLASSNAME,OPEN_HOTKEY
        
        FOREGROUNDWINDOW_HWND =  win32gui.GetForegroundWindow()
        FOREGROUNDWINDOW_CLASSNAME = win32gui.GetClassName(FOREGROUNDWINDOW_HWND)
        
        if FOREGROUNDWINDOW_CLASSNAME == FOCUS_PROGRAM_CLASSNAME:
            if IS_ADD_TAB == False:
                keyboard.add_hotkey(OPEN_HOTKEY,on_activate_tab,suppress=True)
                IS_ADD_TAB = True
                print(OPEN_HOTKEY,"key is hook")
        else:
            if IS_ADD_TAB == True:
                keyboard.clear_hotkey(OPEN_HOTKEY)
                IS_ADD_TAB = False
                print(OPEN_HOTKEY,"tab key is clear")
    hook.hook(callback)



def startHookThread():
    t1 = HookThread(drawGui)
    t1.name="draw_gui"
    t1.start()
    t2 = HookThread(windowFocusHook)
    t2.name="window_focus_hook_key"
    t2.start()

# t1.join()


class HookThread(thread.Thread):
    def __init__(self, func, *args):
        thread.Thread.__init__(self)
        self.func = func
        self.args = args

    def run(self):
        self.func(*self.args)

        

# Theard()
if __name__ == "__main__":
    
    startHookThread()

    OVERLAYER_IS_SHOW = False

    # keyboard.add_hotkey("capslock",on_activate_tab)
    # keyboard.clear_hotkey("tab")
        

    # with keyboard.GlobalHotKeys({
    #         '<ctrl>+<alt>+h': on_activate_h,
    #         '<ctrl>+<alt>+i': on_activate_i,
    #         '<tab>':on_activate_tab
    #         }) as h:
    #                 h.join()
