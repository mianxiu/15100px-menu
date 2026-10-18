// A presentation-only companion to a CLOSED preview menu. No input or PS calls.
class PreviewPendingHint {
    inline static HWND hint=nullptr,menu=nullptr,owner=nullptr,testForeground=nullptr;
    inline static HFONT font=nullptr;
    inline static Json state;
    inline static long long serial=-1;
    inline static LPARAM epoch=-1;
    inline static ULONGLONG renewed=0,changed=0,testNow=0;
    inline static bool active=false,dismissed=false;
    inline static bool testForegroundMissing=false;
    inline static int dpi=96,fontSize=11,paints=0;
    inline static POINT anchor{};
    inline static COLORREF background,text,border,accent;
    inline static std::string lastTrace;
    static void trace(const char* reason){
        std::string key=std::to_string(epoch)+":"+reason;
        if(key==lastTrace)return;lastTrace=key;
        std::cerr<<Json{{"type","preview.hint.trace"},{"reason",reason},{"epoch",epoch},{"serial",serial},
            {"tick_ms",GetTickCount64()},{"lease_age_ms",now()-renewed},
            {"foreground",reinterpret_cast<uintptr_t>(GetForegroundWindow())},
            {"owner",reinterpret_cast<uintptr_t>(owner)},{"menu_visible",bool(menu && IsWindowVisible(menu))},
            {"hint_visible",bool(hint && IsWindowVisible(hint))}}.dump()<<std::endl;
    }
    static ULONGLONG now(){return testNow?testNow:GetTickCount64();}
    static COLORREF color(const ImVec4& c){return RGB(int(c.x*255),int(c.y*255),int(c.z*255));}
    static std::wstring wide(const std::string& s){
        int n=MultiByteToWideChar(CP_UTF8,0,s.data(),int(s.size()),nullptr,0);
        std::wstring v(n,0);MultiByteToWideChar(CP_UTF8,0,s.data(),int(s.size()),v.data(),n);return v;
    }
    static std::wstring label(){
        auto stage=state.value("stage",std::string());
        std::string s=stage=="unknown"?"等待原操作最终结果":stage=="release"?"释放点击保护":stage=="read"?"读取图层":stage=="write"?"写入调整":stage=="verify"?"核验图层":
            stage=="redraw"?"刷新画布":stage=="restore"?"恢复原值":stage=="restore-verify"?"核验恢复结果":
            stage=="restore-redraw"?"刷新恢复后的画布":stage=="cancel-wait"?"取消中 · 等待当前步骤":
            stage=="move"?"移动图层":stage=="commit"?"确认调整":stage=="latest"?"应用最新调整":"等待预览收尾";
        int total=state.value("total",0),done=state.value("done",0);
        if(total>0 && done>=0 && done<=total && total<=256)s+=" · "+std::to_string(done)+"/"+std::to_string(total);
        if(now()-changed>3000)s+=" · 等待 Photoshop";
        if(now()-renewed>1800)s+=" · 状态连接中断";
        return wide(s);
    }
    static void paint(HWND hwnd,HDC dc){
        RECT r{};GetClientRect(hwnd,&r);
        auto fill=CreateSolidBrush(background);FillRect(dc,&r,fill);DeleteObject(fill);
        int pad=MulDiv(int(menuControlPadding),dpi,96),diameter=MulDiv(int(menuCheckSize),dpi,96);
        const int cx=pad+diameter/2,cy=r.bottom/2,radius=diameter/2;
        auto oldBrush=SelectObject(dc,GetStockObject(NULL_BRUSH));
        auto outline=CreatePen(PS_SOLID,std::max(1,MulDiv(1,dpi,96)),border);auto oldPen=SelectObject(dc,outline);
        int rounding=MulDiv(int(figmaCornerRadius*2),dpi,96);
        RoundRect(dc,0,0,r.right,r.bottom,rounding,rounding);
        const int stroke=int(std::lround(activity::stroke(float(radius),float(dpi)/96)));
        auto track=CreatePen(PS_SOLID,stroke,border);SelectObject(dc,track);
        Ellipse(dc,cx-radius,cy-radius,cx+radius,cy+radius);
        auto ink=CreatePen(PS_SOLID,stroke,accent);SelectObject(dc,ink);
        POINT points[activity::segments+1];for(int i=0;i<=activity::segments;++i){float a=activity::angle(now(),i);points[i]={cx+LONG(std::lround(cosf(a)*radius)),cy+LONG(std::lround(sinf(a)*radius))};}
        Polyline(dc,points,activity::segments+1);SelectObject(dc,oldPen);DeleteObject(outline);DeleteObject(track);DeleteObject(ink);SelectObject(dc,oldBrush);
        auto oldFont=SelectObject(dc,font);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,text);
        RECT bounds={pad*2+diameter,0,r.right-pad,r.bottom};auto s=label();
        DrawTextW(dc,s.c_str(),-1,&bounds,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS|DT_NOPREFIX);
        SelectObject(dc,oldFont);++paints;
    }
    static LRESULT CALLBACK procedure(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp){
        if(msg==WM_NCHITTEST)return HTTRANSPARENT;
        if(msg==WM_MOUSEACTIVATE)return MA_NOACTIVATE;
        if(msg==WM_TIMER){tick();return 0;}
        if(msg==WM_ERASEBKGND)return 1;
        if(msg==WM_PRINTCLIENT){paint(hwnd,reinterpret_cast<HDC>(wp));return 0;}
        if(msg==WM_PAINT){PAINTSTRUCT ps{};auto dc=BeginPaint(hwnd,&ps);paint(hwnd,dc);EndPaint(hwnd,&ps);return 0;}
        return DefWindowProcW(hwnd,msg,wp,lp);
    }
    static void hide(){if(hint){ShowWindow(hint,SW_HIDE);KillTimer(hint,1);}}
    static bool foregroundAllowed(HWND fg,DWORD expected,DWORD actual){
        // Photoshop may accept the activation only after its script yields.
        // Our own hidden menu is that handoff, not an external application.
        return expected && (expected==actual || (menu && fg==menu && !IsWindowVisible(menu)));
    }
    static void tick(){
        if(!active || !hint)return;
        // Missing progress is never a terminal result. Keep a truthful waiting
        // indicator until explicit completion, while foreground rules still apply.
        if(menu && IsWindowVisible(menu)){trace("menu-reopened");hide();return;}
        HWND fg=testForegroundMissing?nullptr:testForeground?testForeground:GetForegroundWindow();DWORD expected=0,actual=0;
        GetWindowThreadProcessId(owner,&expected);GetWindowThreadProcessId(fg,&actual);
        wchar_t ownerClass[64]{};GetClassNameW(owner,ownerClass,64);
        // Windows may report NULL while a foreground window loses activation.
        // Conceal the hint for that observation, but keep its timer/session so
        // a known PS foreground can recover it. Only an identified foreign
        // foreground latches dismissal for the remainder of this preview.
        if(IsWindow(owner) && expected && !IsIconic(owner) && (!fg || !actual)){
            trace("foreground-unavailable");ShowWindow(hint,SW_HIDE);return;
        }
        if(!IsWindow(owner) || IsIconic(owner) || !foregroundAllowed(fg,expected,actual) || (!testForeground && wcscmp(ownerClass,L"Photoshop")!=0)){trace(!fg?"foreground-unavailable":!IsWindow(owner)?"owner-invalid":IsIconic(owner)?"owner-minimized":"foreign-foreground");dismissed=true;hide();return;}
        if(dismissed)return;
        auto getDpi=reinterpret_cast<UINT(WINAPI*)(HWND)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetDpiForWindow"));
        int next=getDpi?int(getDpi(owner)):96;if(next<96)next=96;
        if(!font || next!=dpi){dpi=next;if(font)DeleteObject(font);font=CreateFontW(-MulDiv(fontSize,dpi,96),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Microsoft YaHei UI");}
        auto dc=GetDC(hint);auto old=SelectObject(dc,font);SIZE size{};auto s=label();GetTextExtentPoint32W(dc,s.c_str(),int(s.size()),&size);SelectObject(dc,old);ReleaseDC(hint,dc);
        int pad=MulDiv(int(menuControlPadding),dpi,96),diameter=MulDiv(int(menuCheckSize),dpi,96);
        int w=std::min(MulDiv(300,dpi,96),int(size.cx)+3*pad+diameter),h=std::max(MulDiv(int(menuControlHeight),dpi,96),int(size.cy)+2*pad);
        MONITORINFO info{sizeof(info)};GetMonitorInfoW(MonitorFromPoint(anchor,MONITOR_DEFAULTTONEAREST),&info);
        w=std::min(w,int(info.rcWork.right-info.rcWork.left));h=std::min(h,int(info.rcWork.bottom-info.rcWork.top));
        int x=std::clamp(int(anchor.x+diameter),int(info.rcWork.left),int(info.rcWork.right-w));
        int y=std::clamp(int(anchor.y+diameter),int(info.rcWork.top),int(info.rcWork.bottom-h));
        RECT previous{};GetWindowRect(hint,&previous);
        if(previous.right-previous.left!=w || previous.bottom-previous.top!=h){int radius=MulDiv(int(figmaCornerRadius*2),dpi,96);SetWindowRgn(hint,CreateRoundRectRgn(0,0,w+1,h+1,radius,radius),FALSE);}
        // This is the only show path. It must never activate or expose the menu.
        SetWindowPos(hint,HWND_TOPMOST,x,y,w,h,SWP_NOACTIVATE|SWP_SHOWWINDOW);
        trace(now()-renewed>1800?"producer-stale":"visible");
        InvalidateRect(hint,nullptr,FALSE);UpdateWindow(hint);
    }
public:
    static void update(const Json& v,HWND menuWindow,const ImGuiStyle& style,int logicalFont){
        auto next=v.value("serial",-1LL);if(next<=serial)return;serial=next;
        if(!v.value("active",false)){if(active)trace("producer-ended");active=false;hide();return;}
        auto nextEpoch=v.value("epoch",LPARAM(-1));auto phase=v.value("phase",std::string());
        if((phase!="commit" && phase!="cancel") || !v.contains("anchor") || v["anchor"].size()!=2)return;
        if(nextEpoch!=epoch)dismissed=false;
        if(!active || state.value("stage",std::string())!=v.value("stage",std::string()) || state.value("done",0)!=v.value("done",0) || state.value("frame",0)!=v.value("frame",0))changed=now();
        if(fontSize!=logicalFont && font){DeleteObject(font);font=nullptr;}
        fontSize=logicalFont;epoch=nextEpoch;state=v;menu=menuWindow;owner=reinterpret_cast<HWND>(v.value("owner",uintptr_t(0)));
        anchor={v["anchor"][0].get<LONG>(),v["anchor"][1].get<LONG>()};renewed=now();active=true;
        background=color(style.Colors[ImGuiCol_WindowBg]);text=color(style.Colors[ImGuiCol_Text]);border=color(style.Colors[ImGuiCol_Border]);accent=color(style.Colors[ImGuiCol_CheckMark]);
        if(!hint){
            WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"PhotoshopMenuPreviewPendingHint";RegisterClassW(&wc);
            hint=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOPMOST,wc.lpszClassName,L"Photoshop Menu preview pending",WS_POPUP|WS_DISABLED,0,0,1,1,nullptr,nullptr,wc.hInstance,nullptr);
            if(!hint)return;SetLayeredWindowAttributes(hint,0,230,LWA_ALPHA);
        }
        SetTimer(hint,1,50,nullptr);tick();
    }
    static void shutdown(){hide();if(hint){DestroyWindow(hint);hint=nullptr;}if(font){DeleteObject(font);font=nullptr;}active=false;testForeground=nullptr;testForegroundMissing=false;testNow=0;serial=-1;epoch=-1;lastTrace.clear();}
    static void selfTest(const char* name){
        HWND before=GetForegroundWindow();auto style=ImGui::GetStyle();
        WNDCLASSW wc{};wc.lpfnWndProc=DefWindowProcW;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"PhotoshopMenuPendingHintTest";RegisterClassW(&wc);
        HWND underneath=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,wc.lpszClassName,L"Pending hint test target",WS_POPUP,0,0,600,160,nullptr,nullptr,wc.hInstance,nullptr);
        testForeground=underneath;testNow=GetTickCount64()+1;
        Json v={{"serial",1},{"active",true},{"epoch",9},{"owner",reinterpret_cast<uintptr_t>(underneath)},{"anchor",{200,200}},
                {"phase","commit"},{"stage","verify"},{"frame",1},{"done",2},{"total",8}};
        update(v,nullptr,style,11);
        if(!IsWindowVisible(hint))throw std::runtime_error("Pending preview must be visible immediately after close");
        testForegroundMissing=true;tick();
        if(IsWindowVisible(hint) || dismissed || !active)throw std::runtime_error("Missing foreground ended or permanently dismissed the original preview hint");
        testForegroundMissing=false;tick();
        if(!IsWindowVisible(hint))throw std::runtime_error("Pending hint failed to recover after a transient missing foreground");
        testNow+=200;tick();RECT r{};GetWindowRect(hint,&r);
        SetWindowPos(underneath,hint,r.left,r.top,r.right-r.left,r.bottom-r.top,SWP_NOACTIVATE|SWP_SHOWWINDOW);
        tick();POINT point={r.left+10,r.top+10};
        if(!IsWindowVisible(hint) || !paints || IsWindowEnabled(hint) || GetForegroundWindow()!=before ||
           WindowFromPoint(point)!=underneath || SendMessageW(hint,WM_NCHITTEST,0,0)!=HTTRANSPARENT || SendMessageW(hint,WM_MOUSEACTIVATE,0,0)!=MA_NOACTIVATE)
            throw std::runtime_error("Pending hint must show content, preserve focus and pass clicks through");
        auto render=[&](const std::string& suffix){
            GetClientRect(hint,&r);BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=r.right;info.bmiHeader.biHeight=-r.bottom;
            info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
            void* pixels=nullptr;HDC dc=CreateCompatibleDC(nullptr);HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixels,nullptr,0);auto old=SelectObject(dc,bitmap);
            paint(hint,dc);std::vector<char> bytes(static_cast<char*>(pixels),static_cast<char*>(pixels)+r.right*r.bottom*4);
            if(const char* output=std::getenv("PS_MENU_PENDING_PREVIEW_DIR")){
                std::filesystem::create_directories(output);BITMAPFILEHEADER file{};file.bfType=0x4d42;file.bfOffBits=sizeof(file)+sizeof(info.bmiHeader);file.bfSize=file.bfOffBits+DWORD(bytes.size());
                std::ofstream stream(std::filesystem::path(output)/(std::string(name)+"-"+suffix+".bmp"),std::ios::binary);
                stream.write(reinterpret_cast<char*>(&file),sizeof(file));stream.write(reinterpret_cast<char*>(&info.bmiHeader),sizeof(info.bmiHeader));stream.write(bytes.data(),bytes.size());
            }
            SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);return bytes;
        };
        auto first=render("verify-0");testNow+=100;tick();auto next=render("verify-100");
        if(first==next)throw std::runtime_error("Pending spinner did not animate with unchanged progress");
        v["serial"]=2;v["phase"]="cancel";v["stage"]="restore-verify";update(v,nullptr,style,11);render("restore");
        // Showing a new full menu hides the companion; it cannot reopen that menu.
        v["serial"]=3;update(v,nullptr,style,11);
        HWND hiddenMenu=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,wc.lpszClassName,L"Hidden menu handoff test",WS_POPUP,0,0,1,1,nullptr,nullptr,wc.hInstance,nullptr);
        menu=hiddenMenu;
        if(!foregroundAllowed(hiddenMenu,1,2) || foregroundAllowed(underneath,1,2) || foregroundAllowed(hiddenMenu,0,2))
            throw std::runtime_error("Hidden menu handoff was mistaken for external focus");
        DestroyWindow(hiddenMenu);
        menu=underneath;tick();if(IsWindowVisible(hint))throw std::runtime_error("Pending hint overlapped reopened menu");menu=nullptr;
        testForeground=GetDesktopWindow();tick();testForeground=underneath;v["serial"]=4;update(v,nullptr,style,11);
        if(IsWindowVisible(hint))throw std::runtime_error("Pending hint returned after external focus dismissal");
        v["serial"]=5;v["epoch"]=10;update(v,nullptr,style,11);testNow+=200;tick();
        if(!IsWindowVisible(hint))throw std::runtime_error("New preview could not show its own pending feedback");
        testNow+=3001;v["serial"]=6;update(v,nullptr,style,11);render("waiting");
        if(label().find(L"Photoshop")==std::wstring::npos)throw std::runtime_error("Slow pending phase lost wait label");
        update(Json{{"serial",7},{"active",false}},nullptr,style,11);v["serial"]=6;update(v,nullptr,style,11);
        if(IsWindowVisible(hint))throw std::runtime_error("Terminal or late progress reopened pending feedback");
        v["serial"]=8;v["epoch"]=11;update(v,nullptr,style,11);testNow+=200;tick();testNow+=1801;tick();
        if(!IsWindowVisible(hint) || !active || label().find(L"状态连接中断")==std::wstring::npos)
            throw std::runtime_error("Missing progress masqueraded as a completed preview");
        update(Json{{"serial",9},{"active",false}},nullptr,style,11);
        if(IsWindowVisible(hint))throw std::runtime_error("Verified terminal did not clear stale waiting feedback");
        shutdown();DestroyWindow(underneath);
    }
};
