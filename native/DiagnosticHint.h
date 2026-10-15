// Presentation only. No controls, input hooks, PS calls or activation requests.
class DiagnosticHint {
    inline static HWND hint=nullptr;
    inline static HFONT font=nullptr;
    inline static Json state;
    inline static ULONGLONG deadline=0,expires=0;
    inline static int lastSecond=-1,paintCount=0,dpi=96;
    inline static std::wstring title,detail;
    inline static HWND testTarget=nullptr;
    static std::wstring wide(const std::string& text) {
        int size=MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),nullptr,0);
        std::wstring out(size,0);MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),out.data(),size);return out;
    }
    static void paint(HWND hwnd,HDC dc) {
        RECT r{};GetClientRect(hwnd,&r);
        auto brush=CreateSolidBrush(RGB(25,25,25));FillRect(dc,&r,brush);DeleteObject(brush);
        auto old=SelectObject(dc,font);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(245,245,245));
        int pad=MulDiv(int(menuControlPadding),dpi,96),line=MulDiv(int(menuControlHeight),dpi,96);
        RECT first={pad,pad,r.right-pad,pad+line};DrawTextW(dc,title.c_str(),-1,&first,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);
        SetTextColor(dc,RGB(210,210,210));RECT second={pad,pad+line,r.right-pad,r.bottom-pad};
        DrawTextW(dc,detail.c_str(),-1,&second,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);
        SelectObject(dc,old);++paintCount;
    }
    static LRESULT CALLBACK procedure(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp) {
        if(msg==WM_NCHITTEST)return HTTRANSPARENT;
        if(msg==WM_MOUSEACTIVATE)return MA_NOACTIVATE;
        if(msg==WM_TIMER){tick();return 0;}
        if(msg==WM_ERASEBKGND)return 1;
        if(msg==WM_PRINTCLIENT){paint(hwnd,reinterpret_cast<HDC>(wp));return 0;}
        if(msg==WM_PAINT){PAINTSTRUCT ps{};auto dc=BeginPaint(hwnd,&ps);paint(hwnd,dc);EndPaint(hwnd,&ps);return 0;}
        return DefWindowProcW(hwnd,msg,wp,lp);
    }
    static HWND foreground() {
        if(testTarget)return testTarget;
        HWND fg=GetForegroundWindow();wchar_t name[64]{};GetClassNameW(fg,name,64);
        if(wcscmp(name,L"Photoshop")==0 || wcscmp(name,L"OWL.Dock")==0 || wcscmp(name,L"OWL.DocumentWindow")==0 ||
           wcscmp(name,L"PhotoshopMenuImGui")==0)return fg;
        return nullptr;
    }
    static void tick() {
        if(!hint)return;
        auto now=GetTickCount64();
        if(now>=expires){ShowWindow(hint,SW_HIDE);KillTimer(hint,1);return;}
        HWND fg=foreground();if(!fg){ShowWindow(hint,SW_HIDE);return;}
        MONITORINFO info{sizeof(info)};GetMonitorInfoW(MonitorFromWindow(fg,MONITOR_DEFAULTTONEAREST),&info);
        auto getDpi=reinterpret_cast<UINT(WINAPI*)(HWND)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetDpiForWindow"));
        int nextDpi=getDpi?int(getDpi(fg)):96;if(nextDpi<96)nextDpi=96;
        if(!font || nextDpi!=dpi){dpi=nextDpi;if(font)DeleteObject(font);font=CreateFontW(-MulDiv(13,dpi,96),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Microsoft YaHei UI");}
        const auto stage=state.value("stage",std::string());
        bool english=state.value("language",std::string())=="en";
        int seconds=now<deadline?int((deadline-now+999)/1000):0;
        std::wstring nextTitle=wide(state.value("message",std::string()));
        if(stage=="prepare")nextTitle=seconds?L"准备切回 Photoshop":L"正在开始采集";
        if(stage=="sampling")nextTitle=seconds?L"正在采集":L"正在等待采集结束";
        if(english){
            if(stage=="prepare")nextTitle=seconds?L"Get ready: switch to Photoshop":L"Starting sampling";
            else if(stage=="sampling")nextTitle=seconds?L"Collecting":L"Waiting for sampling to finish";
            else if(stage=="processing")nextTitle=L"Preparing diagnostic report";
            else if(stage=="completed")nextTitle=L"Diagnostic report ready";
            else if(stage=="failed")nextTitle=L"Diagnostic failed; check backend";
            else nextTitle=L"Starting read-only checks";
        }
        if(seconds)nextTitle+=L"  "+std::to_wstring(seconds)+(english?L" s":L" 秒");
        const std::wstring nextDetail=stage=="prepare" || stage=="sampling"?
            (english?L"Click Layers, press ":L"点击图层列表，按 ")+wide(state.value("trigger",std::string("CapsLock"))):
            stage=="completed"?(english?L"Export the full JSON in the backend":L"回后台导出完整 JSON 报告"):(english?L"Keep Photoshop in front":L"请保持 Photoshop 前台");
        bool changed=nextTitle!=title || nextDetail!=detail || seconds!=lastSecond;
        title=nextTitle;detail=nextDetail;lastSecond=seconds;
        int w=MulDiv(320,dpi,96),h=MulDiv(int(2*menuControlHeight+2*menuControlPadding),dpi,96),gap=MulDiv(12,dpi,96);
        w=std::min(w,int(info.rcWork.right-info.rcWork.left));
        int x=info.rcWork.left+(info.rcWork.right-info.rcWork.left-w)/2,y=info.rcWork.top+MulDiv(48,dpi,96);
        RECT current{};GetWindowRect(hint,&current);
        if(current.left!=x || current.top!=y || current.right-current.left!=w || current.bottom-current.top!=h){
            SetWindowPos(hint,HWND_TOPMOST,x,y,w,h,SWP_NOACTIVATE);
            int radius=MulDiv(int(figmaCornerRadius*2),dpi,96);
            SetWindowRgn(hint,CreateRoundRectRgn(0,0,w+1,h+1,radius,radius),TRUE);changed=true;
        }
        SetWindowPos(hint,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW);
        if(changed){InvalidateRect(hint,nullptr,FALSE);UpdateWindow(hint);}
    }
public:
    static void update(const Json& value) {
        if(value.value("phase",std::string())=="cancelled"){shutdown();return;}
        state=value;auto now=GetTickCount64();deadline=now+std::max(0,value.value("remaining_ms",0));
        expires=now+(value.value("phase",std::string())=="collecting"?40000:4000);
        if(!hint){
            WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"PhotoshopMenuDiagnosticHint";RegisterClassW(&wc);
            hint=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOPMOST,wc.lpszClassName,L"Photoshop Menu diagnostic countdown",WS_POPUP|WS_DISABLED,0,0,320,60,nullptr,nullptr,wc.hInstance,nullptr);
            if(!hint)return;
            SetLayeredWindowAttributes(hint,0,218,LWA_ALPHA);
        }
        SetTimer(hint,1,200,nullptr);tick();
    }
    static void shutdown(){if(hint){DestroyWindow(hint);hint=nullptr;}if(font){DeleteObject(font);font=nullptr;}testTarget=nullptr;}
    static void selfTest(){
        HWND before=GetForegroundWindow();
        WNDCLASSW wc{};wc.lpfnWndProc=DefWindowProcW;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"PhotoshopMenuHintTestTarget";RegisterClassW(&wc);
        testTarget=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_TOPMOST,wc.lpszClassName,L"Countdown click-through target",WS_POPUP,0,0,320,100,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        update(Json{{"phase","collecting"},{"stage","prepare"},{"remaining_ms",5000},{"trigger","Shift+Z"}});
        RECT r{};GetWindowRect(hint,&r);
        SetWindowPos(testTarget,hint,r.left,r.top,r.right-r.left,r.bottom-r.top,SWP_NOACTIVATE|SWP_SHOWWINDOW);
        tick();UpdateWindow(hint);
        POINT point={r.left+20,r.top+20};
        if(!IsWindowVisible(hint) || !paintCount || GetForegroundWindow()!=before || IsWindowEnabled(hint) || WindowFromPoint(point)!=testTarget || SendMessageW(hint,WM_NCHITTEST,0,0)!=HTTRANSPARENT)
            throw std::runtime_error("Diagnostic hint validation: visible="+std::to_string(IsWindowVisible(hint))+" paints="+std::to_string(paintCount)+" sameFocus="+std::to_string(GetForegroundWindow()==before)+" enabled="+std::to_string(IsWindowEnabled(hint))+" through="+std::to_string(WindowFromPoint(point)==testTarget));
        auto dc=GetDC(hint);COLORREF bg=GetPixel(dc,10,10);ReleaseDC(hint,dc);
        if(bg==CLR_INVALID)throw std::runtime_error("Diagnostic hint has no visible drawing surface");
        HWND test=testTarget;shutdown();DestroyWindow(test);
    }
};
