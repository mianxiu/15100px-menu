# get monitor scale_factor
def getMonitorScaleFactor():
    #fsdf
    import ctypes
    user32 = ctypes.windll.user32
    O_Width = user32.GetSystemMetrics(0)
    O_Height = user32.GetSystemMetrics(1)
    user32.SetProcessDPIAware(2)
    Width = user32.GetSystemMetrics(0)
    Height = user32.GetSystemMetrics(1)

    SCALE_FACTOR = Width/O_Width
    print(O_Width,O_Height,Width,Height,"Scale:",SCALE_FACTOR)
    return SCALE_FACTOR

    
    