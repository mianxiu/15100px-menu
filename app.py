import mouse, keyboard
import dearpygui.dearpygui as dpg
import threading as thread, time


import get_monitor_scale_factor

import ctypes, win32gui
from ctypes import c_int

SCALE_FACTOR = get_monitor_scale_factor.getMonitorScaleFactor()

IS_SHOW_LOG = True


def getMousePos():
    # get mouse position
    mousePos = mouse.get_position()
    mouseX = mousePos[0]
    mouseY = mousePos[1]
    return [mouseX, mouseY]


PROGRAM_TITLE = "1500px menu"
FOCUS_PROGRAM_CLASSNAME = "Photoshop"
OPEN_HOTKEY = "tab"

CURRENT_MOUSE_POS = getMousePos()

DEFAULT_VIEWPORT_PADDING = 10

DEFAULT_VIEWPORT_WIDTH = 750
DEFAULT_VIEWPORT_HEIGHT = 600


DEFAULT_LEFT_PANEL_WIDTH = 400
DEFAULT_LEFT_PANEL_HEIGHT = 400

DEFAULT_RIGHT_PANEL_WIDTH = 300
DEFAULT_RIGHT_PANEL_HEIGHT = 600


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

    global PROGRAM_TITLE
    dpg.create_viewport(
        title=PROGRAM_TITLE,
        vsync=True,
        always_on_top=True,
        clear_color=[0.0, 0.0, 0.0, 0.0],
        decorated=False,
        # width=round(DEFAULT_WIDTH),
        # height=round(DEFAULT_HEIGHT),
        x_pos=round(CURRENT_MOUSE_POS[0]),
        y_pos=round(CURRENT_MOUSE_POS[1]),
    )

    with dpg.window(
        label="MainWindow",
        tag="right_panel",
        no_title_bar=True,
        width=DEFAULT_RIGHT_PANEL_WIDTH,
        height=DEFAULT_RIGHT_PANEL_HEIGHT,
        pos=(0, 0),
        no_move=True,
    ):
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

    with dpg.window(
        tag="left_panel",
        pos=(350, 0),
        no_title_bar=True,
        width=DEFAULT_LEFT_PANEL_WIDTH,
        height=DEFAULT_LEFT_PANEL_HEIGHT,
        no_move=True,
    ):
        dpg.add_color_picker(tag="pick")

    dpg.set_viewport_width(round(DEFAULT_VIEWPORT_WIDTH))
    dpg.set_viewport_height(round(DEFAULT_VIEWPORT_HEIGHT))
    # dpg.show_style_editor()
    dpg.setup_dearpygui()
    dpg.show_viewport()

    # make background transparent
    dwm = ctypes.windll.dwmapi

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", c_int),
            ("cxRightWidth", c_int),
            ("cyTopHeight", c_int),
            ("cyBottomHeight", c_int),
        ]

    hwnd = win32gui.FindWindow(None, PROGRAM_TITLE)
    margins = MARGINS(-1, -1, -1, -1)
    dwm.DwmExtendFrameIntoClientArea(hwnd, margins)

    # dpg.set_primary_window("Primary Window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()


def windowFocusHook(*args):
    global FOREGROUNDWINDOW_HWND, FOREGROUNDWINDOW_CLASSNAME, FOCUS_PROGRAM_CLASSNAME

    def show_overlay():
        if FOREGROUNDWINDOW_CLASSNAME == FOCUS_PROGRAM_CLASSNAME:
            rect = win32gui.GetWindowRect(FOREGROUNDWINDOW_HWND)

            x = rect[0]
            y = rect[1]
            maxX = rect[2]
            maxY = rect[3]
            w = rect[2] - x
            h = rect[3] - y

            TITTLE_HEIGHT = ctypes.windll.user32.GetSystemMetrics(4)

            if IS_SHOW_LOG:
                print("Program rect: ", rect)
                print("Size: (%d, %d)" % (w, h))
                print("Title bar height: ", TITTLE_HEIGHT)

            mousePos = getMousePos()

            if (mousePos[0] > x and mousePos[0] < maxX) and (
                mousePos[1] > y and mousePos[1] < maxY
            ):
                mousePosX = (
                    mousePos[0]
                    if mousePos[0] + DEFAULT_VIEWPORT_WIDTH < maxX
                    else (maxX - DEFAULT_VIEWPORT_WIDTH)
                )
                mousePosY = (
                    mousePos[1] + TITTLE_HEIGHT
                    if mousePos[1] + DEFAULT_VIEWPORT_HEIGHT < maxY
                    else (maxY - DEFAULT_VIEWPORT_HEIGHT)
                )

                dpg.set_viewport_pos((mousePosX, mousePosY))

                dpg.set_viewport_height(DEFAULT_VIEWPORT_HEIGHT)
                dpg.set_viewport_width(DEFAULT_VIEWPORT_WIDTH)

    def hide_overlay():
        dpg.set_viewport_height(0)
        dpg.set_viewport_width(0)

    import hook

    def keyCallback():
        global IS_ADD_TAB, FOREGROUNDWINDOW_HWND, FOREGROUNDWINDOW_CLASSNAME, FOCUS_PROGRAM_CLASSNAME, OPEN_HOTKEY

        FOREGROUNDWINDOW_HWND = win32gui.GetForegroundWindow()
        FOREGROUNDWINDOW_CLASSNAME = win32gui.GetClassName(FOREGROUNDWINDOW_HWND)

        if FOREGROUNDWINDOW_CLASSNAME == FOCUS_PROGRAM_CLASSNAME:
            if IS_ADD_TAB == False:
                keyboard.add_hotkey(OPEN_HOTKEY, show_overlay, suppress=True)
                mouse.on_right_click(hide_overlay)
                IS_ADD_TAB = True

                #
                if IS_SHOW_LOG:
                    print(OPEN_HOTKEY, "key is hook")
        else:
            if IS_ADD_TAB == True:
                keyboard.clear_hotkey(OPEN_HOTKEY)
                mouse.unhook_all()
                IS_ADD_TAB = False

                #
                if IS_SHOW_LOG:
                    print(OPEN_HOTKEY, "tab key is clear")

    hook.hook(keyCallback)


def startHookThread():
    t1 = HookThread(drawGui)
    t1.name = "draw_gui"
    t1.start()
    t2 = HookThread(windowFocusHook)
    t2.name = "window_focus_hook_key"
    t2.start()


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
