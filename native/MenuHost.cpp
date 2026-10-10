#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#ifndef WS_EX_NOREDIRECTIONBITMAP
#define WS_EX_NOREDIRECTIONBITMAP 0x00200000L
#endif
#include <d3d11.h>
#include <dxgi1_3.h>
#include <dcomp.h>
#include <wincodec.h>
#include <shellapi.h>
#include <array>
#include <string>
#include <thread>
#include <iostream>
#include <memory>
#include <algorithm>
#include <cmath>
#include <vector>
#include <sstream>
#include <filesystem>
#include "vendor/json/json.hpp"
#include "imgui.h"
#include "imgui_internal.h"
#include "backends/imgui_impl_win32.h"
#include "backends/imgui_impl_dx11.h"
#include "MenuGlyphs.h"

using Json=nlohmann::json;
static HWND window;
static void (*platformShowWindow)(ImGuiViewport*)=nullptr;
static void showPopupWindow(ImGuiViewport* viewport) {
    if (IsWindowVisible(window)) platformShowWindow(viewport);
}
static DWORD backendParent=0;
static ID3D11Device* device;
static ID3D11DeviceContext* context;
static IDXGISwapChain* swapChain;
static HANDLE frameLatency=nullptr;
static bool frameGranted=false;
static IDCompositionDevice* composition;
static IDCompositionTarget* compositionTarget;
static IDCompositionVisual* compositionVisual;
static IDCompositionEffectGroup* compositionEffect;
static float compositionOpacity=-1;
static ID3D11RenderTargetView* target;
static bool running=true,opened=false,contextMode=false,focusSearch=false;
static bool allowed=false,capable=false,rightHide=false;
static std::string document="连接中…",notice;
static bool taskBusy=false,taskFailed=false;
static ULONGLONG taskStarted=0;
static std::string taskName;
static std::string taskStatus() {
    if (taskBusy) return "执行中："+(taskName.empty()?std::string("Photoshop 操作"):taskName)+
        " · "+std::to_string((GetTickCount64()-taskStarted)/1000)+" 秒";
    if (!notice.empty()) return taskFailed?"最近操作失败 · 请查看后台日志":"空闲 · 最近操作已完成";
    return "空闲 · 无菜单任务运行";
}
static void updateBusy(bool busy) {
    if (busy && !taskBusy) taskStarted=GetTickCount64();
    taskBusy=busy;allowed=capable&&!busy;
}
static std::array<std::string,4> shortcuts={"CapsLock + A","CapsLock + C","CapsLock + W","CapsLock + S"};
static const char* actions[]={"select","color","moveToTop","moveToBottom"};
static const char* labels[]={"选择组内图层","橙色图层标签","移到顶部","移到底部"};
static const char* keywords[]={"select group layers","orange color tag","move top","move bottom"};
static char search[256]{};
static int selection=0;
static bool holdMode=false;
static std::array<RECT,4> holdRows{};
static POINT holdOrigin{};
static bool holdMoved=false;
static ImVec2 pieCenter{};
static bool pieReady=false;
static bool holdFinished=false;
static bool pinned=false;
static LPARAM menuEpoch=0;
static ULONGLONG pieStarted=0;
static bool pieAnimating=false;
static float previewAnimationMs=-1;
static float pieAnimation(float elapsedMs,bool reduced=false) {
    return reduced?1.f:std::clamp(elapsedMs/60.f,0.f,1.f);
}
struct LabelColor {const char* id;const char* name;ImU32 color;};
static const std::array<LabelColor,8> labelColors={{{"none","无颜色 / 清除标签",IM_COL32(105,109,117,255)},
    {"red","红色",IM_COL32(224,91,88,255)},{"orange","橙色",IM_COL32(229,151,63,255)},
    {"yellowColor","黄色",IM_COL32(226,201,83,255)},{"grain","绿色",IM_COL32(110,176,99,255)},
    {"blue","蓝色",IM_COL32(88,144,213,255)},{"violet","紫色",IM_COL32(169,125,207,255)},
    {"gray","灰色",IM_COL32(169,172,180,255)}}};
static std::array<RECT,8> labelRows{};

// Backend resolves editor identity outside the hook and sends it synchronously
// before showing the popup: 0 generic, 1 canvas, 2 layers, 3 text input.
static int panelKind=0;
static bool inputFocused=false;
static bool canExecute() {return allowed && !inputFocused && panelKind!=3;}
static const char* panelTitle() {
    return panelKind==1?"画布操作":panelKind==2?"图层操作":panelKind==3?"输入控件":"通用操作";
}
static bool rowVisible(int i) {return panelKind!=3 && (panelKind!=1 || i<2);}
static float scale=1;
static std::string uiTheme="dark";
static std::string uiFontSize="small";
static bool fontDirty=false;
static ImFontGlyphRangesBuilder requiredGlyphs;
static ImFont* menuFonts[3]{};
static unsigned fontBuilds=0;
static int fontIndex() {return uiFontSize=="large"?2:uiFontSize=="medium"?1:0;}
static void requireText(const std::string& text) {
    const char* p=text.c_str();
    while (*p) {
        unsigned int c=0;int n=ImTextCharFromUtf8(&c,p,nullptr);
        if (n<=0) break;p+=n;
        if (c<=IM_UNICODE_CODEPOINT_MAX && !requiredGlyphs.GetBit(c)) {
            requiredGlyphs.AddChar(static_cast<ImWchar>(c));fontDirty=true;
        }
    }
}
static void theme();
static ImU32 tint(ImGuiCol role) {return ImGui::GetColorU32(role);}
static bool knownTheme(const std::string& value) {
    return value=="light" || value=="light-gray" || value=="dark-gray" || value=="dark";
}
static unsigned renderedFrames=0;
static std::wstring preview;
static std::string previewKind="menu";
static bool previewLifecycle=false;
static bool previewLive=false;
static bool selfTest=false;
static std::vector<std::string> testedActions;
static size_t labelTestActionCount=0;
static ImVec2 bottomRow;
static void send(const char* action) {
    if (selfTest) {testedActions.emplace_back(action);return;}
    // The foreground menu grants its own backend permission to return focus
    // to PS when it hides. Do not loosen foreground restrictions globally.
    if (backendParent) AllowSetForegroundWindow(backendParent);
    Json event={{"type","action"},{"action",action},{"session",menuEpoch}};
    std::cout<<event.dump()<<std::endl;
}
static std::string normalized(std::string value) {
    std::string result;
    for (unsigned char c:value) if (!isspace(c)) result+=static_cast<char>(tolower(c));
    return result;
}
static bool matches(int i,const std::string& query) {
    std::string haystack=normalized(std::string(labels[i])+" "+keywords[i]+" "+shortcuts[i]);
    std::istringstream words(query);std::string word;
    while (words>>word) if (haystack.find(normalized(word))==std::string::npos) return false;
    return true;
}
static void releaseTarget() { if (target) { target->Release();target=nullptr; } }
static bool createTarget() {
    ID3D11Texture2D* buffer=nullptr;
    if (FAILED(swapChain->GetBuffer(0,IID_PPV_ARGS(&buffer)))) return false;
    HRESULT result=device->CreateRenderTargetView(buffer,nullptr,&target); buffer->Release();
    return SUCCEEDED(result);
}
static void setOpacity(float opacity) {
    if (compositionVisual && opacity!=compositionOpacity) {
        compositionEffect->SetOpacity(opacity);composition->Commit();compositionOpacity=opacity;
    }
}
static bool createDevice(HWND hwnd) {
    D3D_FEATURE_LEVEL levels[]={D3D_FEATURE_LEVEL_11_0,D3D_FEATURE_LEVEL_10_0},level;
    HRESULT result=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        levels,2,D3D11_SDK_VERSION,&device,&level,&context);
    if (FAILED(result)) result=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        levels,2,D3D11_SDK_VERSION,&device,&level,&context);
    if (FAILED(result)) return false;
    IDXGIDevice* dxgi=nullptr;IDXGIAdapter* adapter=nullptr;IDXGIFactory2* factory=nullptr;IDXGISwapChain1* chain=nullptr;
    result=device->QueryInterface(IID_PPV_ARGS(&dxgi));
    if (SUCCEEDED(result)) result=dxgi->GetAdapter(&adapter);
    if (SUCCEEDED(result)) result=adapter->GetParent(IID_PPV_ARGS(&factory));
    RECT bounds{};GetClientRect(hwnd,&bounds);
    DXGI_SWAP_CHAIN_DESC1 desc{};
    desc.Width=std::max<LONG>(1,bounds.right);desc.Height=std::max<LONG>(1,bounds.bottom);
    desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;
    desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;desc.BufferCount=2;
    desc.SwapEffect=DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;desc.AlphaMode=DXGI_ALPHA_MODE_PREMULTIPLIED;
    desc.Flags=DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;
    if (SUCCEEDED(result)) result=factory->CreateSwapChainForComposition(device,&desc,nullptr,&chain);
    if (SUCCEEDED(result)) {
        IDXGISwapChain2* lowLatency=nullptr;
        result=chain->QueryInterface(IID_PPV_ARGS(&lowLatency));
        if (SUCCEEDED(result)) {
            result=lowLatency->SetMaximumFrameLatency(1);
            if (SUCCEEDED(result)) frameLatency=lowLatency->GetFrameLatencyWaitableObject();
            lowLatency->Release();
        }
        if (SUCCEEDED(result) && !frameLatency) result=E_FAIL;
        if (FAILED(result)) {chain->Release();chain=nullptr;}
    }
    if (SUCCEEDED(result)) {swapChain=chain;result=DCompositionCreateDevice(dxgi,__uuidof(IDCompositionDevice),reinterpret_cast<void**>(&composition));}
    if (SUCCEEDED(result)) result=composition->CreateTargetForHwnd(hwnd,TRUE,&compositionTarget);
    if (SUCCEEDED(result)) result=composition->CreateVisual(&compositionVisual);
    if (SUCCEEDED(result)) result=composition->CreateEffectGroup(&compositionEffect);
    if (SUCCEEDED(result)) result=compositionVisual->SetEffect(compositionEffect);
    if (SUCCEEDED(result)) result=compositionVisual->SetContent(swapChain);
    if (SUCCEEDED(result)) result=compositionTarget->SetRoot(compositionVisual);
    if (SUCCEEDED(result)) result=composition->Commit();
    if (factory) factory->Release();if (adapter) adapter->Release();if (dxgi) dxgi->Release();
    compositionOpacity=-1;
    frameGranted=false;
    return SUCCEEDED(result) && createTarget();
}
static void releaseDevice() {
    releaseTarget();
    if (frameLatency) {CloseHandle(frameLatency);frameLatency=nullptr;}
    frameGranted=false;
    if (compositionEffect) {compositionEffect->Release();compositionEffect=nullptr;}
    if (compositionVisual) {compositionVisual->Release();compositionVisual=nullptr;}
    if (compositionTarget) {compositionTarget->Release();compositionTarget=nullptr;}
    if (composition) {composition->Release();composition=nullptr;}
    if (swapChain) {swapChain->Release();swapChain=nullptr;}
    if (context) {context->Release();context=nullptr;}
    if (device) {device->Release();device=nullptr;}
}
static bool recoverRenderer() {
    // A Photoshop/GPU restart can invalidate this process's D3D device too.
    // Keep the CPU font atlas and rebuild the renderer on a fresh device.
    ImGui_ImplDX11_Shutdown();
    // DX11 shutdown destroys platform data for ALL viewports, including the
    // main one. Reinitialize Win32 too, while retaining our owned HWND.
    ImGui_ImplWin32_Shutdown();releaseDevice();
    if (!createDevice(window)) return false;
    if (!ImGui_ImplWin32_Init(window)) return false;
    platformShowWindow=ImGui::GetPlatformIO().Platform_ShowWindow;
    ImGui::GetPlatformIO().Platform_ShowWindow=showPopupWindow;
    if (!ImGui_ImplDX11_Init(device,context)) return false;
    return ImGui_ImplDX11_CreateDeviceObjects();
}
static void resetMenu() {
    search[0]=0;selection=0;focusSearch=!contextMode;
    holdRows={};
    labelRows={};
    pieReady=false;
    if (ImGui::GetCurrentContext()) { ImGui::GetCurrentContext()->OpenPopupStack.clear(); }
}
static void closePopups() {
    if (!ImGui::GetCurrentContext()) return;
    ImGui::GetCurrentContext()->OpenPopupStack.clear();
    // Destroy only secondary viewports. Their handles must be recreated when
    // the same submenu is opened again; preserve the main Win32 backend data.
    auto& platform=ImGui::GetPlatformIO();
    for (int i=1;i<platform.Viewports.Size;++i) {
        ImGui::DestroyPlatformWindow(static_cast<ImGuiViewportP*>(platform.Viewports[i]));
    }
}
static void finishPlatformFrame() {
    // This is mandatory for EVERY ended frame, even if ShowWindow hid the
    // main HWND during Present. Skipping it asserts on the next NewFrame.
    ImGui::UpdatePlatformWindows();
    if (IsWindowVisible(window)) ImGui::RenderPlatformWindowsDefault();
    if (!IsWindowVisible(window)) closePopups();
}
static std::string shortcut(const std::string& raw) {
    std::string result;size_t start=0;
    while (start<raw.size()) {
        size_t end=raw.find('+',start); std::string word=raw.substr(start,end==std::string::npos?end:end-start);
        if (word=="capslock") word="CapsLock";
        else if (word=="ctrl") word="Ctrl";
        else if (word=="shift") word="Shift";
        else if (word=="alt") word="Alt";
        else if (!word.empty()) word[0]=static_cast<char>(toupper(static_cast<unsigned char>(word[0])));
        if (!result.empty()) result+=" + "; result+=word;
        if (end==std::string::npos) break;start=end+1;
    }
    return result;
}
static void accept(const Json& event) {
    std::string type=event.value("type","");
    if (type=="status") {
        const auto& data=event.at("data"); const auto& ps=data.at("photoshop");
        const std::string nextTheme=ps.value("ui_theme",uiTheme);
        if (knownTheme(nextTheme) && nextTheme!=uiTheme) {uiTheme=nextTheme;theme();}
        const std::string nextFont=ps.value("ui_font_size",uiFontSize);
        if ((nextFont=="small" || nextFont=="medium" || nextFont=="large") && nextFont!=uiFontSize) {
            uiFontSize=nextFont;
        }
        capable=ps.value("connected",capable) && data.at("settings").value("enabled",true);
        if (ps.contains("document")) capable=capable && ps["document"].is_string();
        updateBusy(ps.value("busy",false));
        document=ps.contains("document") && ps["document"].is_string()?ps["document"].get<std::string>():ps.value("message","Photoshop 未连接");
        const auto& settings=data.at("settings");rightHide=settings.value("right_click_hide",false);
        for (int i=0;i<4;++i) shortcuts[i]=shortcut(settings.at("shortcuts").value(actions[i],""));
    } else if (type=="operation") {
        if (event.value("busy",false) && event.contains("action")) {
            std::string action=event.value("action","");taskName=action;
            for (int i=0;i<4;++i) if (action==actions[i]) taskName=labels[i];
            for (const auto& label:labelColors) if (action==std::string("label.")+label.id) taskName=label.name;
            notice.clear();taskFailed=false;
        }
        updateBusy(event.value("busy",false));
    }
    else if (type=="notice") {notice=event.value("message","");taskFailed=!event.value("ok",true);}
    else if (type=="popup.prepare") { contextMode=event.value("mode","quick")=="context";resetMenu(); }
}
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND,UINT,WPARAM,LPARAM);
static int holdActionAt(POINT point) {
    if (!holdMode || !pieReady || holdFinished || pieAnimating || !canExecute()) return -1;
    float dx=point.x-pieCenter.x,dy=point.y-pieCenter.y;
    float ox=static_cast<float>(point.x-holdOrigin.x),oy=static_cast<float>(point.y-holdOrigin.y);
    // Edge clamping may put the invocation point on top of a swatch. Protect
    // an untouched press, but don't leave an invisible hole after a gesture.
    if (ox*ox+oy*oy>=12*12*scale*scale) holdMoved=true;
    if (dx*dx+dy*dy<12*12*scale*scale || (!pinned && !holdMoved)) return -1;
    RECT bounds{};GetWindowRect(window,&bounds);
    if (!PtInRect(&bounds,point)) return -1;
    for (int i=0;i<8;++i) if (!pieAnimating && rowVisible(1) && PtInRect(&labelRows[i],point)) return 4+i;
    for (int i=0;i<4;++i) if (rowVisible(i) && PtInRect(&holdRows[i],point)) return i==1?-1:i;
    // Only visible cards/swatches commit. Blank radial sectors are neutral.
    return -1;
}
static void setHoldMode(bool enabled) {
    holdMode=enabled;holdFinished=false;pinned=false;holdMoved=false;resetMenu();focusSearch=false;
    pieStarted=0;pieAnimating=enabled;
    // The compositor retains the last presented surface while hidden. Never
    // expose that old, fully expanded pie before the new zero-alpha frame.
    setOpacity(enabled?0.f:1.f);
    if (enabled) GetCursorPos(&holdOrigin);
}
static void finishHold(POINT point) {
    if (!holdMode || holdFinished || pinned) return;
    int chosen=holdActionAt(point);
    holdFinished=true;pieReady=false;
    setOpacity(0.f);
    if (chosen>=4) send((std::string("label.")+labelColors[chosen-4].id).c_str());
    else send(chosen<0?"hide":actions[chosen]);
}
static LRESULT CALLBACK procedure(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp) {
    if (msg==WM_APP+11) return renderedFrames;
    // Read-only diagnostic used by the real SetWindowPos lifecycle regression.
    if (msg==WM_APP+18) return static_cast<LRESULT>(std::lround(compositionOpacity*1000));
    // One synchronous transition: no intermediate layout or repeated round trips.
    if (msg==WM_APP+17) {
        panelKind=static_cast<int>(wp&3);inputFocused=(wp&4)!=0;
        contextMode=(wp&8)!=0;menuEpoch=lp;setHoldMode((wp&16)!=0);
        return 0;
    }
    if (msg==WM_APP+13) {menuEpoch=lp;setHoldMode(wp!=0);return 0;}
    if (msg==WM_APP+16) {pinned=wp!=0;return 0;}
    if (msg==WM_APP+14) {
        POINT point{};
        if (IsWindowVisible(hwnd) && GetCursorPos(&point)) finishHold(point);
        return 0;
    }
    if (msg==WM_APP+12) {panelKind=wp<=3?static_cast<int>(wp):0;inputFocused=lp!=0;resetMenu();return 0;}
    if (msg==WM_APP) {
        std::unique_ptr<Json> event(reinterpret_cast<Json*>(lp));
        try { accept(*event); } catch (const std::exception& error) { notice=error.what(); }
        return 0;
    }
    if (msg==WM_APP+10) { contextMode=wp!=0;resetMenu();return 0; }
    if (msg==WM_SHOWWINDOW) {
        opened=wp!=0;
        if (opened) {
            resetMenu();pieStarted=0;setOpacity(holdMode?0.f:1.f);
        } else {
            // Keep the composition surface attached while the HWND hides.
            // The next frame selects transparent pie or opaque regular mode.
            holdFinished=true;pieReady=false;holdRows={};labelRows={};closePopups();
            setOpacity(0.f);
        }
    }
    if (ImGui_ImplWin32_WndProcHandler(hwnd,msg,wp,lp)) return true;
    switch (msg) {
    case WM_SIZE:
        if (device && wp!=SIZE_MINIMIZED) {
            DXGI_SWAP_CHAIN_DESC desc{};
            if (SUCCEEDED(swapChain->GetDesc(&desc)) &&
                desc.BufferDesc.Width==LOWORD(lp) && desc.BufferDesc.Height==HIWORD(lp)) return 0;
            context->OMSetRenderTargets(0,nullptr,nullptr);
            releaseTarget();
            if (SUCCEEDED(swapChain->ResizeBuffers(0,LOWORD(lp),HIWORD(lp),DXGI_FORMAT_UNKNOWN,
                DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT))) createTarget();
        }
        return 0;
    case WM_DPICHANGED: {
        RECT* rect=reinterpret_cast<RECT*>(lp); SetWindowPos(hwnd,nullptr,rect->left,rect->top,
            rect->right-rect->left,rect->bottom-rect->top,SWP_NOZORDER|SWP_NOACTIVATE); return 0;
    }
    case WM_SYSCOMMAND: if ((wp&0xfff0)==SC_KEYMENU) return 0;break;
    case WM_CLOSE: DestroyWindow(hwnd);return 0;
    case WM_DESTROY: running=false;PostQuitMessage(0);return 0;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}
static void theme() {
    // Photoshop's four brightness presets, lightest to darkest. Widget tones
    // match the shipped UIColors.txt; label swatch hues are semantic and fixed.
    int i=uiTheme=="light"?0:uiTheme=="light-gray"?1:uiTheme=="dark-gray"?2:3;
    auto& style=ImGui::GetStyle();style=ImGuiStyle();
    if (i<2) ImGui::StyleColorsLight();else ImGui::StyleColorsDark();
    auto gray=[](int v){float f=v/255.f;return ImVec4(f,f,f,1);};
    const int background[]={240,184,83,50},fill[]={252,209,69,41},pressed[]={191,128,56,31};
    const int text[]={41,15,240,225},muted[]={84,56,214,173},disabled[]={168,128,135,115};
    const int border[]={204,148,102,71},divider[]={217,153,62,38};
    auto& c=style.Colors;
    c[ImGuiCol_WindowBg]=c[ImGuiCol_PopupBg]=gray(background[i]);
    c[ImGuiCol_Text]=gray(text[i]);c[ImGuiCol_TextDisabled]=gray(disabled[i]);
    c[ImGuiCol_Border]=gray(border[i]);c[ImGuiCol_Separator]=gray(divider[i]);
    c[ImGuiCol_FrameBg]=c[ImGuiCol_Button]=gray(fill[i]);
    c[ImGuiCol_FrameBgHovered]=c[ImGuiCol_ButtonHovered]=c[ImGuiCol_HeaderHovered]=gray(pressed[i]);
    c[ImGuiCol_FrameBgActive]=c[ImGuiCol_ButtonActive]=c[ImGuiCol_HeaderActive]=gray(pressed[i]);
    c[ImGuiCol_Header]=gray(pressed[i]);
    // Reuse PlotLines for secondary labels; all hand-drawn UI uses this palette.
    c[ImGuiCol_PlotLines]=gray(muted[i]);
    c[ImGuiCol_CheckMark]=c[ImGuiCol_NavHighlight]=i<2?ImVec4(.08f,.45f,.90f,1):ImVec4(.30f,.65f,1,1);
    c[ImGuiCol_SliderGrab]=c[ImGuiCol_SliderGrabActive]=c[ImGuiCol_CheckMark];
    style.WindowPadding={10,10};style.FramePadding={7,5};style.ItemSpacing={6,5};
    style.WindowRounding=5;style.PopupRounding=5;style.FrameRounding=3;style.WindowBorderSize=1;
    style.ScaleAllSizes(scale);
}

static void icon(int index,ImVec2 pos) {
    auto* draw=ImGui::GetWindowDrawList();ImU32 grey=tint(ImGuiCol_Text);
    pos.y+=5*scale;
    if (index==0) {
        draw->AddRect({pos.x+2*scale,pos.y+5*scale},{pos.x+13*scale,pos.y+16*scale},grey,scale);
        draw->AddRect({pos.x+5*scale,pos.y+2*scale},{pos.x+16*scale,pos.y+13*scale},grey,scale);
    } else if (index==1) {
        draw->AddRectFilled({pos.x+2*scale,pos.y+4*scale},{pos.x+15*scale,pos.y+14*scale},IM_COL32(220,141,54,255),2*scale);
    } else {
        float tip=pos.y+(index==2?3:16)*scale,tail=pos.y+(index==2?16:3)*scale;
        draw->AddLine({pos.x+9*scale,tail},{pos.x+9*scale,tip},grey,1.5f*scale);
        float y=tip+(index==2?4:-4)*scale;
        draw->AddLine({pos.x+9*scale,tip},{pos.x+5*scale,y},grey,1.5f*scale);
        draw->AddLine({pos.x+9*scale,tip},{pos.x+13*scale,y},grey,1.5f*scale);
    }
}
static void layoutLabels(ImVec2 pos) {
    for (int i=0;i<8;++i) {
        float x=pos.x+(i%4)*36*scale,y=pos.y+(i/4)*36*scale;
        labelRows[i]={static_cast<LONG>(x),static_cast<LONG>(y),
            static_cast<LONG>(pos.x+(i%4+1)*36*scale),static_cast<LONG>(pos.y+(i/4+1)*36*scale)};
    }
}
static void commitLabel(int index) {
    if (!canExecute() || (holdMode && holdFinished)) return;
    if (holdMode) {holdFinished=true;pieReady=false;}
    send((std::string("label.")+labelColors[index].id).c_str());
}
static void drawLabels() {
    auto* draw=ImGui::GetWindowDrawList();POINT cursor{};GetCursorPos(&cursor);
    ImVec2 saved=ImGui::GetCursorScreenPos();
    ImGui::PushItemFlag(ImGuiItemFlags_NoNav,true);
    ImGui::BeginDisabled(!canExecute() || (holdMode && (holdFinished || pieAnimating)));
    for (int i=0;i<8;++i) {
        auto r=labelRows[i];ImVec2 a={static_cast<float>(r.left),static_cast<float>(r.top)},b={static_cast<float>(r.right),static_cast<float>(r.bottom)};
        ImGui::PushID(100+i);ImGui::SetCursorScreenPos(a);
        bool active=canExecute() && (holdMode?holdActionAt(cursor)==4+i:PtInRect(&r,cursor));
        if (ImGui::InvisibleButton("##label",{b.x-a.x,b.y-a.y})) commitLabel(i);
        ImU32 color=labelColors[i].color;
        if (!canExecute()) color=(color&0x00ffffff)|0x66000000;
        draw->AddRectFilled(a,b,color);
        if (active) draw->AddRect({a.x+scale,a.y+scale},{b.x-scale,b.y-scale},tint(ImGuiCol_CheckMark),0,0,2*scale);
        if (i==0) {
            float inset=(b.x-a.x)*.2f;
            draw->AddLine({a.x+inset,b.y-inset},{b.x-inset,a.y+inset},IM_COL32(237,237,241,255),1.5f*scale);
        }
        // Swatches are icon-only, including hover; no detached color tooltip.
        ImGui::PopID();
    }
    ImGui::EndDisabled();ImGui::PopItemFlag();ImGui::SetCursorScreenPos(saved);
}
static void colorGrid() {
    layoutLabels(ImGui::GetCursorScreenPos());drawLabels();ImGui::Dummy({144*scale,72*scale});
}
static void contextItems() {
    ImGui::TextDisabled("%s",panelTitle());ImGui::Separator();
    if (panelKind==3) {
        ImGui::TextWrapped("正在编辑输入框，请退出输入后执行操作。");
        if (ImGui::MenuItem("后台管理…")) send("control");
        if (ImGui::MenuItem("关闭菜单","Esc")) send("hide");
        return;
    }
    if (panelKind==1) {
        colorGrid();ImGui::Separator();
        if (ImGui::BeginMenu("图层操作")) {
            for (int i=0;i<4;++i) if (ImGui::MenuItem(labels[i],shortcuts[i].c_str(),false,canExecute())) send(actions[i]);
            ImGui::EndMenu();
        }
        ImGui::Separator();
        if (ImGui::MenuItem("后台管理…")) send("control");
        if (ImGui::MenuItem("关闭菜单","Esc")) send("hide");
        return;
    }
    if (ImGui::MenuItem(labels[0],shortcuts[0].c_str(),false,canExecute())) send(actions[0]);
    colorGrid();
    if (ImGui::BeginMenu("图层排序")) {
        for (int i=2;i<4;++i) if (ImGui::MenuItem(labels[i],shortcuts[i].c_str(),false,canExecute())) send(actions[i]);
        ImGui::EndMenu();
    }
    ImGui::Separator();
    if (ImGui::MenuItem("后台管理…")) send("control");
    if (ImGui::MenuItem("关闭菜单","Esc")) send("hide");
}
static void drawPie() {
    auto* draw=ImGui::GetWindowDrawList();
    ImVec2 pos=ImGui::GetWindowPos(),size=ImGui::GetWindowSize();
    pieCenter={pos.x+size.x*.5f,pos.y+size.y*.5f};
    if (!pieStarted) pieStarted=GetTickCount64();
    float elapsed=previewAnimationMs>=0?previewAnimationMs:selfTest?60.f:float(GetTickCount64()-pieStarted);
    const float fac=pieAnimation(elapsed);
    pieAnimating=fac<1;
    // A sent hide/release may arrive during rendering. A late draw must not
    // restore opacity after that transition while the backend closes HWND.
    // SetWindowPos(SWP_SHOWWINDOW), our production entry, need not deliver
    // WM_SHOWWINDOW. Query the HWND instead of relying on that message's cache.
    setOpacity(IsWindowVisible(window) && !holdFinished?fac:0.f);
    // Blender 5.2 defaults: 20-unit widgets, pie rows 1.5 widgets high,
    // 100-unit radius to the inner edge, roundness .4 of a widget.
    const float rowHeight=30*scale,padding=5*scale,rounding=8*scale;
    const char* hints[]={"4","","8","2"};
    const ImGuiKey numberKeys[]={ImGuiKey_4,ImGuiKey_None,ImGuiKey_8,ImGuiKey_2};
    const ImGuiKey keypadKeys[]={ImGuiKey_Keypad4,ImGuiKey_None,ImGuiKey_Keypad8,ImGuiKey_Keypad2};
    // Direction accelerators are local to an open pie, never global PS keys.
    if (canExecute() && !holdFinished && !ImGui::GetIO().KeyCtrl &&
        !ImGui::GetIO().KeyAlt && !ImGui::GetIO().KeyShift && !ImGui::GetIO().KeySuper) {
        for (int i:{0,2,3}) if (rowVisible(i) &&
            (ImGui::IsKeyPressed(numberKeys[i],false) || ImGui::IsKeyPressed(keypadKeys[i],false))) {
            holdFinished=true;send(actions[i]);break;
        }
    }
    std::array<ImVec2,4> offsets{};
    holdRows={};labelRows={};
    for (int i=0;i<4;++i) {
        if (!rowVisible(i)) continue;
        float width=i==1?98*scale:ImGui::CalcTextSize(labels[i]).x+60*scale;
        float height=i==1?56*scale:rowHeight;
        float radius=100*scale;
        if (i<2) radius=std::min(radius,std::max(20*scale,size.x*.5f-width-8*scale));
        offsets[i]=i==0?ImVec2(-radius-width*.5f,0):i==1?ImVec2(radius+width*.5f,0):
            i==2?ImVec2(0,-radius-height*.5f):ImVec2(0,radius+height*.5f);
        ImVec2 a={pieCenter.x+offsets[i].x-width*.5f,pieCenter.y+offsets[i].y-height*.5f};
        holdRows[i]={LONG(a.x),LONG(a.y),LONG(a.x+width),LONG(a.y+height)};
    }
    if (rowVisible(1)) {
        auto r=holdRows[1];
        for (int i=0;i<8;++i) labelRows[i]={LONG(r.left+(7+(i%4)*21)*scale),LONG(r.top+(7+(i/4)*21)*scale),
            LONG(r.left+(7+(i%4+1)*21)*scale),LONG(r.top+(7+(i/4+1)*21)*scale)};
    }
    pieReady=!holdFinished;
    POINT cursor{};GetCursorPos(&cursor);int selected=holdActionAt(cursor);
    auto caption=[&](const char* text,float y) {
        auto extent=ImGui::CalcTextSize(text);
        ImVec2 at={roundf(pieCenter.x-extent.x*.5f),roundf(y)};
        // A theme-colored second copy looks embossed on a transparent HWND.
        // Draw once with the same contrast as action labels.
        draw->AddText(at,tint(ImGuiCol_Text),text);
    };
    caption(panelTitle(),pieCenter.y-40*scale);
    // Blender's centre is a 12..19-unit annulus with a direction segment.
    draw->AddCircle(pieCenter,15.5f*scale,tint(ImGuiCol_WindowBg),40,7*scale);
    if (selected>=0) {
        float angle=atan2f(float(cursor.y)-pieCenter.y,float(cursor.x)-pieCenter.x);
        draw->PathArcTo(pieCenter,15.5f*scale,angle-.785398f,angle+.785398f,10);
        draw->PathStroke(tint(ImGuiCol_CheckMark),0,7*scale);
    }
    draw->AddCircle(pieCenter,12*scale,tint(ImGuiCol_Border),40,scale);
    draw->AddCircle(pieCenter,19*scale,tint(ImGuiCol_Border),40,scale);
    for (int i=0;i<4;++i) {
        if (!rowVisible(i)) continue;
        int vertexStart=draw->VtxBuffer.Size;
        ImVec2 a={float(holdRows[i].left),float(holdRows[i].top)},b={float(holdRows[i].right),float(holdRows[i].bottom)};
        bool active=i==selected || (i==1 && selected>=4);
        if (pinned && i!=1 && !pieAnimating && canExecute() && !holdFinished) {
            ImGui::SetCursorScreenPos(a);ImGui::PushID(200+i);
            if (ImGui::InvisibleButton("##pinned-action",{b.x-a.x,b.y-a.y})) {holdFinished=true;send(actions[i]);}
            ImGui::PopID();
        }
        draw->AddRectFilled(a,b,active?tint(ImGuiCol_HeaderHovered):tint(ImGuiCol_WindowBg),rounding);
        draw->AddRect(a,b,active?tint(ImGuiCol_CheckMark):tint(ImGuiCol_Border),rounding,0,scale);
        if (i==1) {
            drawLabels();
        } else {
            icon(i,{a.x+padding,a.y+(rowHeight-28*scale)*.5f});
            float textY=roundf(a.y+(rowHeight-ImGui::GetFontSize())*.5f);
            draw->AddText({roundf(a.x+25*scale),textY},canExecute()?tint(ImGuiCol_Text):tint(ImGuiCol_TextDisabled),labels[i]);
            float hintWidth=ImGui::CalcTextSize(hints[i]).x;
            draw->AddText({roundf(b.x-padding-hintWidth),textY},tint(ImGuiCol_PlotLines),hints[i]);
        }
        // Keep hit regions at their final positions so fast gestures don't
        // accidentally select a different card while visual cards overlap.
        for (int v=vertexStart;v<draw->VtxBuffer.Size;++v) {
            draw->VtxBuffer[v].pos.x+=roundf(offsets[i].x*(fac-1));
            draw->VtxBuffer[v].pos.y+=roundf(offsets[i].y*(fac-1));
        }
    }
    caption(taskStatus().c_str(),pieCenter.y+45*scale);
    // Only show exceptional state; the normal pie has no tutorial banner.
    const char* hint=pinned?"已固定 · 右键 / Esc 关闭":panelKind==3 || inputFocused?"输入框编辑中":!canExecute()?"当前不可执行":nullptr;
    if (hint) caption(hint,pieCenter.y+65*scale);
}
static void drawMenu() {
    ImGui::SetNextWindowPos(ImGui::GetMainViewport()->Pos);
    ImGui::SetNextWindowSize(ImGui::GetMainViewport()->Size);
    ImGui::SetNextWindowViewport(ImGui::GetMainViewport()->ID);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize,holdMode?0.f:scale);
    ImGui::Begin("##menu",nullptr,ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoSavedSettings|(holdMode?ImGuiWindowFlags_NoBackground:0));
    ImGui::PopStyleVar();
    if (holdMode) {drawPie();ImGui::End();return;}
    ImGui::TextWrapped("%s",taskStatus().c_str());
    if (contextMode) {
        contextItems();ImGui::Separator();ImGui::TextDisabled("点击外部 / Esc 关闭");
    } else {
        ImGui::TextDisabled("%s",panelTitle());ImGui::SameLine();ImGui::TextDisabled("QUICK MENU");
        if (holdMode) ImGui::TextDisabled("移动鼠标选择 · 松开执行 · 空白处取消");
        if (panelKind!=3 && !holdMode) {
            ImGui::SetNextItemWidth(-1);
            if (focusSearch) {ImGui::SetKeyboardFocusHere();focusSearch=false;}
            if (ImGui::InputTextWithHint("##search","搜索操作…",search,sizeof(search))) selection=0;
        }
        ImGui::Separator();std::array<int,4> results{};int count=0;
        for (int i=0;i<4;++i) {
            if (rowVisible(i) && matches(i,search)) results[count++]=i;
        }
        if (count && !holdMode) {
            if (ImGui::IsKeyPressed(ImGuiKey_DownArrow)) selection=(selection+1)%count;
            if (ImGui::IsKeyPressed(ImGuiKey_UpArrow)) selection=(selection+count-1)%count;
            selection=std::clamp(selection,0,count-1);
        }
        bool popupOpen=ImGui::IsPopupOpen("context");
        if (!holdMode && count && canExecute() && !popupOpen && ImGui::IsKeyPressed(ImGuiKey_Enter,false)) send(actions[results[selection]]);
        // Quick-menu keyboard navigation is explicit. Letting Selectable also
        // receive ImGui nav activation can dispatch a second, different row.
        ImGui::PushItemFlag(ImGuiItemFlags_NoNav,true);
        ImGui::BeginDisabled(!canExecute());
        holdRows={};
        for (int r=0;r<count;++r) {
            int i=results[r];ImVec2 pos=ImGui::GetCursorScreenPos();
            ImGui::PushID(i);
            POINT cursor{};GetCursorPos(&cursor);
            RECT row={static_cast<LONG>(pos.x),static_cast<LONG>(pos.y),
                static_cast<LONG>(pos.x+ImGui::GetContentRegionAvail().x),static_cast<LONG>(pos.y+27*scale)};
            bool highlighted=holdMode?PtInRect(&row,cursor):selection==r;
            if (ImGui::Selectable("##row",highlighted,0,{0,27*scale}) && !holdMode) send(actions[i]);
            ImVec2 minimum=ImGui::GetItemRectMin(),maximum=ImGui::GetItemRectMax();
            holdRows[i]={static_cast<LONG>(minimum.x),static_cast<LONG>(minimum.y),static_cast<LONG>(maximum.x),static_cast<LONG>(maximum.y)};
            if (i==3) bottomRow={pos.x+70*scale,pos.y+13*scale};
            if (!holdMode && ImGui::IsItemHovered() && (ImGui::GetIO().MouseDelta.x!=0 || ImGui::GetIO().MouseDelta.y!=0)) selection=r;
            icon(i,pos);auto* draw=ImGui::GetWindowDrawList();
            draw->AddText({pos.x+27*scale,pos.y+4*scale},ImGui::GetColorU32(ImGuiCol_Text),labels[i]);
            float width=ImGui::CalcTextSize(shortcuts[i].c_str()).x;
            draw->AddText({ImGui::GetWindowPos().x+ImGui::GetWindowWidth()-width-12*scale,pos.y+4*scale},tint(ImGuiCol_PlotLines),shortcuts[i].c_str());
            ImGui::PopID();
        }
        ImGui::EndDisabled();
        if (!count) ImGui::TextDisabled(panelKind==3?"输入框编辑中，图层操作已暂停":"没有匹配的操作");
        if (inputFocused && panelKind!=3) ImGui::TextDisabled("输入框仍有焦点，图层操作已暂停");
        if (panelKind==1 && !holdMode) {ImGui::Separator();ImGui::TextDisabled("右键展开图层操作");}
        ImGui::Separator();if (!holdMode && ImGui::MenuItem("后台管理…")) send("control");
        ImGui::PopItemFlag();
        ImGui::TextDisabled(panelKind==3?"Esc 关闭":holdMode?"空白处松开取消    Esc 关闭":"↑ ↓ 选择    Enter 执行    Esc 关闭");
        ImGui::TextDisabled("%s",document.c_str());
        if (!notice.empty()) { ImGui::PushTextWrapPos();ImGui::TextColored({.94f,.65f,.35f,1},"%s",notice.c_str());ImGui::PopTextWrapPos(); }
        if (!holdMode && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
            if (rightHide) send("hide");else ImGui::OpenPopup("context");
        }
        if (ImGui::BeginPopup("context")) {contextItems();ImGui::EndPopup();}
    }
    if (contextMode && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) send("hide");
    ImGui::End();
}
static void screenshot(const std::wstring& path) {
    ID3D11Texture2D *buffer=nullptr,*staging=nullptr;
    if (FAILED(swapChain->GetBuffer(0,IID_PPV_ARGS(&buffer)))) throw std::runtime_error("Preview buffer unavailable");
    D3D11_TEXTURE2D_DESC desc;buffer->GetDesc(&desc);desc.Usage=D3D11_USAGE_STAGING;
    desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
    HRESULT result=device->CreateTexture2D(&desc,nullptr,&staging);
    if (FAILED(result)) {buffer->Release();throw std::runtime_error("Preview staging failed");}
    context->CopyResource(staging,buffer);buffer->Release();D3D11_MAPPED_SUBRESOURCE pixels;
    if (FAILED(context->Map(staging,0,D3D11_MAP_READ,0,&pixels))) {staging->Release();throw std::runtime_error("Preview read failed");}
    IWICImagingFactory* factory=nullptr;IWICStream* stream=nullptr;IWICBitmapEncoder* encoder=nullptr;IWICBitmapFrameEncode* frame=nullptr;
    result=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory));
    if (SUCCEEDED(result)) result=factory->CreateStream(&stream);
    if (SUCCEEDED(result)) result=stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE);
    if (SUCCEEDED(result)) result=factory->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder);
    if (SUCCEEDED(result)) result=encoder->Initialize(stream,WICBitmapEncoderNoCache);
    if (SUCCEEDED(result)) result=encoder->CreateNewFrame(&frame,nullptr);
    if (SUCCEEDED(result)) result=frame->Initialize(nullptr);
    if (SUCCEEDED(result)) result=frame->SetSize(desc.Width,desc.Height);
    WICPixelFormatGUID format=GUID_WICPixelFormat32bppRGBA;
    if (SUCCEEDED(result)) result=frame->SetPixelFormat(&format);
    std::vector<BYTE> converted;
    UINT stride=pixels.RowPitch;BYTE* data=static_cast<BYTE*>(pixels.pData);
    if (SUCCEEDED(result)) {
        stride=desc.Width*4;converted.resize(stride*desc.Height);
        for (UINT y=0;y<desc.Height;++y) for (UINT x=0;x<desc.Width;++x) {
            BYTE* source=data+y*pixels.RowPitch+x*4;BYTE* output=converted.data()+y*stride+x*4;
            bool bgra=IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA);
            // DComposition buffers are premultiplied BGRA; PNG stores straight alpha.
            const int alpha=source[3];
            auto straight=[&](int channel)->BYTE {return alpha?BYTE(std::min(255,(int(source[channel])*255+alpha/2)/alpha)):0;};
            output[0]=straight(bgra?0:2);output[1]=straight(1);output[2]=straight(bgra?2:0);
            output[3]=BYTE(alpha);
        }
        data=converted.data();
    } else if (SUCCEEDED(result) && !IsEqualGUID(format,GUID_WICPixelFormat32bppRGBA)) result=E_FAIL;
    if (SUCCEEDED(result)) result=frame->WritePixels(desc.Height,stride,stride*desc.Height,data);
    if (SUCCEEDED(result)) result=frame->Commit();
    if (SUCCEEDED(result)) result=encoder->Commit();
    if (frame) frame->Release();if (encoder) encoder->Release();if (stream) stream->Release();if (factory) factory->Release();
    context->Unmap(staging,0);staging->Release();
    if (FAILED(result)) throw std::runtime_error("Preview PNG encoding failed");
}
static void readEvents() {
    try {
        std::string line;
        while (std::getline(std::cin,line)) {
            auto event=std::make_unique<Json>(Json::parse(line));
            if (!PostMessageW(window,WM_APP,0,reinterpret_cast<LPARAM>(event.get()))) break;
            event.release();
        }
    } catch (...) {}
    PostMessageW(window,WM_CLOSE,0,0);
}
int main() {
    // Report CRT assertions to overlay.log rather than a blocking OS dialog.
    _set_error_mode(_OUT_TO_STDERR);
    int argc;LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    std::wstring iconPath;DWORD parent=0;
    for (int i=1;i<argc;++i) {
        std::wstring arg=argv[i];
        if (arg==L"--preview-lifecycle") previewLifecycle=true;
        else if (arg==L"--preview-live") previewLive=true;
        else if (arg==L"--self-test") selfTest=true;
        else if (i+1<argc && arg==L"--preview-output") preview=argv[++i];
        else if (i+1<argc && arg==L"--preview-kind") {
            std::wstring kind=argv[++i];previewKind=kind==L"context"?"context":kind==L"hold"?"hold":"menu";
        }
        else if (i+1<argc && arg==L"--preview-theme") {
            std::wstring value=argv[++i];std::string name(value.begin(),value.end());
            if (knownTheme(name)) uiTheme=name;
        }
        else if (i+1<argc && arg==L"--preview-animation-ms") previewAnimationMs=std::stof(argv[++i]);
        else if (i+1<argc && arg==L"--preview-font-size") {
            std::wstring value=argv[++i];
            if (value==L"small" || value==L"medium" || value==L"large") uiFontSize=std::string(value.begin(),value.end());
        }
        else if (i+1<argc && arg==L"--preview-panel") {
            std::wstring kind=argv[++i];panelKind=kind==L"canvas"?1:kind==L"layers"?2:kind==L"text"?3:0;
        }
        else if (i+1<argc && arg==L"--icon") iconPath=argv[++i];
        else if (i+1<argc && arg==L"--parent") parent=std::stoul(argv[++i]);
    }
    LocalFree(argv);CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    backendParent=parent;
    ImGui_ImplWin32_EnableDpiAwareness();
    WNDCLASSEXW wc{sizeof(WNDCLASSEXW)};wc.style=CS_CLASSDC;wc.lpfnWndProc=procedure;wc.hInstance=GetModuleHandleW(nullptr);
    wc.lpszClassName=L"PhotoshopMenuImGui";wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);
    HICON iconHandle=iconPath.empty()?nullptr:static_cast<HICON>(LoadImageW(nullptr,iconPath.c_str(),IMAGE_ICON,32,32,LR_LOADFROMFILE));
    wc.hIcon=wc.hIconSm=iconHandle;RegisterClassExW(&wc);
    contextMode=previewKind=="context";
    window=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOREDIRECTIONBITMAP,wc.lpszClassName,preview.empty()?L"Photoshop Menu - Actions":L"Photoshop Menu - Preview",
        WS_POPUP,100,100,contextMode?260:360,contextMode?240:300,nullptr,nullptr,wc.hInstance,nullptr);
    if (!window || !createDevice(window)) {std::cerr<<"DirectX 11 initialization failed\n";return 1;}
    IMGUI_CHECKVERSION();ImGui::CreateContext();auto& io=ImGui::GetIO();
    io.ConfigFlags|=ImGuiConfigFlags_NavEnableKeyboard|ImGuiConfigFlags_ViewportsEnable;
    io.IniFilename=nullptr;io.LogFilename=nullptr;
    if (selfTest) io.ConfigFlags|=ImGuiConfigFlags_NoMouseCursorChange;
    scale=ImGui_ImplWin32_GetDpiScaleForHwnd(window);theme();
    if (!preview.empty() || selfTest) SetWindowPos(window,nullptr,100,100,
        static_cast<int>((contextMode?260:360)*scale),static_cast<int>((contextMode?240:300)*scale),SWP_NOZORDER|SWP_NOACTIVATE);
    io.ConfigViewportsNoTaskBarIcon=true;
    std::wstring fontPath; wchar_t windowsPath[MAX_PATH];GetWindowsDirectoryW(windowsPath,MAX_PATH);fontPath=std::wstring(windowsPath)+L"/Fonts/msyh.ttc";
    int size=WideCharToMultiByte(CP_UTF8,0,fontPath.c_str(),-1,nullptr,0,nullptr,nullptr);std::string font(size,0);WideCharToMultiByte(CP_UTF8,0,fontPath.c_str(),-1,font.data(),size,nullptr,nullptr);
    requiredGlyphs.AddRanges(io.Fonts->GetGlyphRangesDefault());
    for (ImWchar c:menuStaticGlyphs) requiredGlyphs.AddChar(c);
    ImVector<ImWchar> glyphs;
    wchar_t executable[MAX_PATH]{};GetModuleFileNameW(nullptr,executable,MAX_PATH);
    auto fontFolder=std::filesystem::path(executable).parent_path()/L"fonts";
    auto utf8=[](const std::filesystem::path& path) {return path.u8string();};
    auto loadFont=[&]{
        const ULONGLONG fontStart=GetTickCount64();
        io.FontDefault=nullptr;
        io.Fonts->Clear();
        glyphs.clear();requiredGlyphs.BuildRanges(&glyphs);
        auto inter=utf8(fontFolder/L"Inter.ttf"),cjk=utf8(fontFolder/L"NotoSansCJK.otf");
        for (int index=0;index<3;++index) {
        const float em=11.f+index;
        if (std::filesystem::exists(fontFolder/L"Inter.ttf") && std::filesystem::exists(fontFolder/L"NotoSansCJK.otf")) {
            // stb_truetype sizes by ascent-descent; Blender/FreeType sizes by
            // em. Convert hhea metrics; apply monitor DPI exactly once.
            menuFonts[index]=io.Fonts->AddFontFromFileTTF(inter.c_str(),em*scale*(2478.f/2048.f));
            ImFontConfig merge;merge.MergeMode=true;
            io.Fonts->AddFontFromFileTTF(cjk.c_str(),em*scale*1.448f,&merge,glyphs.Data);
        } else {
            menuFonts[index]=io.Fonts->AddFontFromFileTTF(font.c_str(),em*scale,nullptr,glyphs.Data);
            if (!menuFonts[index]) menuFonts[index]=io.Fonts->AddFontDefault();
        }
        }
        // Build CPU glyph data explicitly. GPU creation can fail before its
        // implicit font build (e.g. a removed device); NewFrame must never
        // receive the cleared, unbuilt atlas in that case.
        if (!io.Fonts->Build() || !io.Fonts->IsBuilt())
            throw std::runtime_error("Unable to build menu font atlas");
        fontDirty=false;
        ++fontBuilds;io.FontDefault=menuFonts[fontIndex()];
        std::cerr<<"Font atlas prepared: three sizes, "<<(GetTickCount64()-fontStart)<<" ms, "
                 <<io.Fonts->TexWidth<<"x"<<io.Fonts->TexHeight<<", builds="<<fontBuilds<<"\n";
    };
    loadFont();
    ImGui_ImplWin32_Init(window);ImGui_ImplDX11_Init(device,context);
    platformShowWindow=ImGui::GetPlatformIO().Platform_ShowWindow;
    ImGui::GetPlatformIO().Platform_ShowWindow=showPopupWindow;
    if (!ImGui_ImplDX11_CreateDeviceObjects()) {
        std::cerr<<"Unable to initialize menu renderer resources\n";return 1;
    }
    if (preview.empty() && !selfTest) {
        std::cout<<Json({{"type","ready"},{"hwnd",reinterpret_cast<uintptr_t>(window)},{"pid",GetCurrentProcessId()}}).dump()<<std::endl;
        std::thread(readEvents).detach();
        if (parent) std::thread([parent]{HANDLE process=OpenProcess(SYNCHRONIZE,FALSE,parent);if (process){WaitForSingleObject(process,INFINITE);CloseHandle(process);}PostMessageW(window,WM_CLOSE,0,0);}).detach();
    } else {
        allowed=true;document="示例文档.psd";
        if (selfTest) {
            for (int kind=0;kind<4;++kind) for (int input=0;input<2;++input) {
                procedure(window,WM_APP+17,kind|(input<<2)|16,73);
                if (panelKind!=kind || inputFocused!=bool(input) || !holdMode || contextMode || menuEpoch!=73)
                    throw std::runtime_error("Atomic pie preparation lost context/input/session");
            }
            // Start with a stale fully opaque surface, as on a repeated tap.
            // Each prepare/show must stay transparent until its new animation.
            for (int cycle=0;cycle<100;++cycle) {
                setOpacity(1.f);
                procedure(window,WM_APP+17,16,cycle);
                if (compositionOpacity!=0.f) throw std::runtime_error("Pie prepare exposed previous frame");
                procedure(window,WM_SHOWWINDOW,TRUE,0);
                if (compositionOpacity!=0.f) throw std::runtime_error("Pie show exposed previous frame");
                procedure(window,WM_SHOWWINDOW,FALSE,0);
                if (compositionOpacity!=0.f || !holdFinished)
                    throw std::runtime_error("Pie hide retained visible content");
            }
            procedure(window,WM_APP+17,8,74);
            if (holdMode || !contextMode || inputFocused || panelKind || menuEpoch!=74)
                throw std::runtime_error("Atomic regular preparation retained pie state");
            procedure(window,WM_APP+17,0,0);
            if (pieAnimation(0)!=0 || pieAnimation(30)!=.5f || pieAnimation(60)!=1 || pieAnimation(120)!=1 || pieAnimation(0,true)!=1)
                throw std::runtime_error("Blender pie animation timing failed");
            const float savedScale=scale;const float padding=ImGui::GetStyle().WindowPadding.x;
            for (const char* name:{"light","light-gray","dark-gray","dark"}) {
                Json testSettings={{"enabled",true},{"shortcuts",Json::object()}};
                accept({{"type","status"},{"data",{{"photoshop",{{"ui_theme",name}}},{"settings",testSettings}}}});
                const auto& c=ImGui::GetStyle().Colors;
                bool light=uiTheme=="light" || uiTheme=="light-gray";
                if (uiTheme!=name || (c[ImGuiCol_Text].x<c[ImGuiCol_WindowBg].x)!=light ||
                    scale!=savedScale || ImGui::GetStyle().WindowPadding.x!=padding)
                    throw std::runtime_error("Theme update lost contrast or accumulated DPI scale");
            }
            Json settings={{"enabled",true},{"shortcuts",Json::object()}};
            settings["shortcuts"]={{"select","capslock+a"},{"color","capslock+c"},{"moveToTop","capslock+w"},{"moveToBottom","capslock+s"}};
            accept({{"type","status"},{"data",{{"photoshop",{{"connected",true},{"document","test.psd"}}},{"settings",settings}}}});
            accept({{"type","status"},{"data",{{"photoshop",{{"busy",true}}},{"settings",settings}}}});
            accept({{"type","operation"},{"busy",false}});
            if (!canExecute()) throw std::runtime_error("Menu readiness lost after busy status");
            accept({{"type","operation"},{"busy",true},{"action","select"}});
            auto started=taskStarted;resetMenu();
            accept({{"type","status"},{"data",{{"photoshop",{{"busy",true}}},{"settings",settings}}}});
            if (canExecute() || taskStarted!=started || taskStatus().find("选择组内图层")==std::string::npos)
                throw std::runtime_error("Running task status lost on reopen/status refresh");
            accept({{"type","notice"},{"ok",false},{"message","Operation timed out"}});
            if (taskStatus().find("执行中")==std::string::npos)
                throw std::runtime_error("Timeout must not imply COM task stopped");
            accept({{"type","operation"},{"busy",false}});resetMenu();
            if (taskStatus().find("失败")==std::string::npos || notice.empty())
                throw std::runtime_error("Failure status lost after reopening");
            accept({{"type","operation"},{"busy",true},{"action","select"}});
            accept({{"type","notice"},{"ok",true},{"message","Completed"}});
            accept({{"type","operation"},{"busy",false}});resetMenu();
            if (!canExecute() || taskStatus().find("已完成")==std::string::npos)
                throw std::runtime_error("Completion state failed");
            notice.clear();taskFailed=false;
            panelKind=1;if (!rowVisible(0) || rowVisible(2)) throw std::runtime_error("Canvas panel routing failed");
            panelKind=3;if (rowVisible(0)) throw std::runtime_error("Text panel routing failed");
            panelKind=2;if (!rowVisible(3)) throw std::runtime_error("Layer panel routing failed");
            panelKind=0;
            if (!matches(2,"CapsLock+w") || !matches(0,"组内") || !matches(1,"orange color") || matches(3,"top") || matches(0,"missing"))
                throw std::runtime_error("Search self-test failed");
        }
        if (previewLifecycle) {
            ShowWindow(window,SW_MINIMIZE);ShowWindow(window,SW_HIDE);
            for (int i=0;i<3;++i) {ShowWindow(window,SW_RESTORE);ShowWindow(window,SW_HIDE);}
        }
    if (!selfTest) {ShowWindow(window,SW_SHOWNORMAL);UpdateWindow(window);}
        resetMenu();
        if (previewKind=="hold") {
            SetWindowPos(window,nullptr,100,100,static_cast<int>(620*scale),static_cast<int>(440*scale),SWP_NOZORDER|SWP_NOACTIVATE);
            setHoldMode(true);
        }
    }
    int frames=0;
    try {
        while (running) {
            // Wait BEFORE sampling input/building the next frame. Messages wake
            // this wait, so release/cancel/prepare do not queue behind v-sync.
            if (!selfTest && IsWindowVisible(window) && frameLatency && !frameGranted) {
                DWORD result=MsgWaitForMultipleObjectsEx(1,&frameLatency,100,QS_ALLINPUT,MWMO_INPUTAVAILABLE);
                if (result==WAIT_FAILED) throw std::runtime_error("Frame wait failed");
                frameGranted=result==WAIT_OBJECT_0;
            }
            MSG msg;while (PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)) {TranslateMessage(&msg);DispatchMessageW(&msg);if (msg.message==WM_QUIT) running=false;}
            if (!running) break;
            if ((selfTest || previewLifecycle) && frames==14) {
                RECT rect;GetWindowRect(window,&rect);
                SetWindowPos(window,nullptr,0,0,rect.right-rect.left+40,rect.bottom-rect.top+40,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
                SetWindowPos(window,nullptr,0,0,rect.right-rect.left,rect.bottom-rect.top,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
                if (previewLifecycle) {ShowWindow(window,SW_MINIMIZE);ShowWindow(window,SW_HIDE);ShowWindow(window,SW_RESTORE);}
            }
            float dpi=ImGui_ImplWin32_GetDpiScaleForHwnd(window);
            requireText(document);requireText(notice);requireText(taskName);requireText(search);
            for (const auto& text:shortcuts) requireText(text);
            if (selfTest && frames>=1 && frames<=3) {
                uiFontSize=frames==1?"large":frames==2?"medium":"small";
                if (frames==2) requireText("\xE9\xBE\x98"); // Rare document-name glyph U+9F98.
            }
            if (fabsf(dpi-scale)>.01f || fontDirty) {
                ImGui_ImplDX11_InvalidateDeviceObjects();scale=dpi;theme();loadFont();
                // Inject an early GPU creation failure into the native test.
                bool uploaded=!(selfTest && frames==2) && ImGui_ImplDX11_CreateDeviceObjects();
                if (!uploaded && !recoverRenderer())
                    throw std::runtime_error("Unable to restore renderer after font update");
            }
            if (io.FontDefault!=menuFonts[fontIndex()]) {
                io.FontDefault=menuFonts[fontIndex()];
                std::cerr<<"Font selection ready: "<<uiFontSize<<", cached\n";
            }
            if (selfTest && frames>=1 && frames<=3) {
                if (fontBuilds!=(frames==1?1u:2u))
                    throw std::runtime_error("Cached size switch unexpectedly rebuilt fonts");
                if (frames>=2) for (auto* cached:menuFonts)
                    if (!cached->FindGlyphNoFallback(0x9F98))
                        throw std::runtime_error("Dynamic Chinese glyph missing from a cached size");
            }
            // Prepare pending fonts while hidden, on receipt of PS status.
            // Deferring this until ShowWindow blocked the first CapsLock frame.
            // Preserve an acquired slot if a hide arrived during the wait.
            // Dropping it without Present can strand the next reopen.
            if (!IsWindowVisible(window) && !selfTest) {WaitMessage();continue;}
            if (FAILED(device->GetDeviceRemovedReason()) || !target) {
                if (!recoverRenderer()) throw std::runtime_error("Unable to recover removed graphics device");
                continue;
            }
            if (!selfTest && frameLatency && !frameGranted) continue;
            frameGranted=false;
            ImGui_ImplDX11_NewFrame();ImGui_ImplWin32_NewFrame();
            if (!io.Fonts->IsBuilt()) throw std::runtime_error("Font atlas unavailable after renderer NewFrame");
            if (selfTest) {
                io.AddFocusEvent(true);
                if (frames==4 || frames==5) io.AddKeyEvent(ImGuiKey_DownArrow,frames==4);
                if (frames==6 || frames==7) io.AddKeyEvent(ImGuiKey_Enter,frames==6);
                if (frames>=10 && frames<=12) {
                    io.AddMouseViewportEvent(ImGui::GetMainViewport()->ID);
                    io.AddMousePosEvent(bottomRow.x,bottomRow.y);
                    if (frames==10 || frames==11) io.AddMouseButtonEvent(ImGuiMouseButton_Left,frames==10);
                }
                if (frames==22 || frames==23) {
                    auto r=labelRows[1];
                    io.AddMouseViewportEvent(ImGui::GetMainViewport()->ID);
                    io.AddMousePosEvent((r.left+r.right)*.5f,(r.top+r.bottom)*.5f);
                    io.AddMouseButtonEvent(ImGuiMouseButton_Left,frames==22);
                }
            }
            ImGui::NewFrame();drawMenu();ImGui::Render();
            ++renderedFrames;
            if (!target) throw std::runtime_error("DX11 render target lost after window resize");
            auto bg=ImGui::GetStyleColorVec4(ImGuiCol_WindowBg);
            float clear[]={holdMode?0.f:bg.x,holdMode?0.f:bg.y,holdMode?0.f:bg.z,holdMode?0.f:1.f};context->OMSetRenderTargets(1,&target,nullptr);context->ClearRenderTargetView(target,clear);
            ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
            ++frames;
            if (selfTest && frames==20) {
                if (testedActions!=std::vector<std::string>{"color","moveToBottom"}) throw std::runtime_error("ImGui keyboard/click dispatch self-test failed: "+Json(testedActions).dump());
                SetWindowPos(window,nullptr,100,100,static_cast<int>(620*scale),static_cast<int>(440*scale),SWP_NOZORDER|SWP_NOACTIVATE);
                setHoldMode(true);
            }
            if (selfTest && frames==21) {
                holdOrigin={static_cast<LONG>(pieCenter.x),static_cast<LONG>(pieCenter.y)};
                auto point=[&](float x,float y){return POINT{static_cast<LONG>(pieCenter.x+x*scale),static_cast<LONG>(pieCenter.y+y*scale)};};
                for (const auto& entry:std::array<std::pair<POINT,int>,8>{{{point(-150,0),0},{point(80,0),-1},{point(0,-120),2},{point(0,120),3},{point(0,0),-1},{point(20,10),-1},{point(70,70),-1},{{-100,-100},-1}}})
                    if (holdActionAt(entry.first)!=entry.second) throw std::runtime_error("Pie direction/dead-zone hit test failed");
                for (int i=0;i<4;++i) {
                    if (i==1) continue; // The palette commits only an explicit swatch.
                    POINT middle={(holdRows[i].left+holdRows[i].right)/2,(holdRows[i].top+holdRows[i].bottom)/2};
                    if (holdActionAt(middle)!=i) throw std::runtime_error("Pie card hit test failed");
                }
                holdOrigin=point(-150,0);holdMoved=false;
                if (holdActionAt(holdOrigin)!=-1) throw std::runtime_error("Clamped invocation must cancel");
                holdOrigin=point(0,0);
                if (holdActionAt(point(0,11))!=-1 || holdActionAt(point(0,20))!=-1)
                    throw std::runtime_error("Blender 12-unit centre threshold failed");
                panelKind=1;
                if (std::string(panelTitle())!="画布操作" || !rowVisible(0) || !rowVisible(1) || rowVisible(2) || rowVisible(3) ||
                    holdActionAt(point(0,-120))!=-1 || holdActionAt(point(0,120))!=-1)
                    throw std::runtime_error("Canvas pie leaked hidden layer-sort actions");
                panelKind=2;
                if (std::string(panelTitle())!="图层操作" || holdActionAt(point(0,-120))!=2 || holdActionAt(point(0,120))!=3)
                    throw std::runtime_error("Layer pie lost sorting actions");
                panelKind=3;
                if (rowVisible(0) || rowVisible(1) || holdActionAt(point(-150,0))!=-1)
                    throw std::runtime_error("Input context exposed pie actions");
                panelKind=0;
                for (int i=0;i<8;++i) {
                    auto r=labelRows[i];POINT middle={(r.left+r.right)/2,(r.top+r.bottom)/2};
                    if (holdActionAt(middle)!=4+i) throw std::runtime_error("Label swatch hit test failed");
                }
                for (int origin=0;origin<8;++origin) {
                    auto r=labelRows[origin];
                    holdOrigin={(r.left+r.right)/2,(r.top+r.bottom)/2};holdMoved=false;
                    if (holdActionAt(holdOrigin)!=-1)
                        throw std::runtime_error("Unmoved clamped press must cancel");
                    holdActionAt(point(0,0)); // Deliberately leave the invocation area.
                    for (int i=0;i<8;++i) {
                        auto cell=labelRows[i];
                        for (LONG y=cell.top;y<cell.bottom;++y)
                            for (LONG x=cell.left;x<cell.right;++x)
                                if (holdActionAt({x,y})!=4+i)
                                    throw std::runtime_error("Invocation dead zone masks a swatch pixel");
                    }
                    holdMoved=false;pinned=true;
                    if (holdActionAt(holdOrigin)!=4+origin)
                        throw std::runtime_error("Pinned swatch must ignore invocation dead zone");
                    pinned=false;
                }
                holdOrigin=point(0,0);holdMoved=false;
                POINT rowPoint=point(0,120);
                pinned=true;auto beforePin=testedActions.size();finishHold(rowPoint);
                if (testedActions.size()!=beforePin || holdFinished)
                    throw std::runtime_error("Pinned menu must ignore key release");
                pinned=false;
                pieAnimating=true;
                auto animLabel=labelRows[1];
                if (holdActionAt({(animLabel.left+animLabel.right)/2,(animLabel.top+animLabel.bottom)/2})!=-1 ||
                    holdActionAt(point(-150,0))!=-1)
                    throw std::runtime_error("Animation must cancel card and palette releases");
                pieAnimating=false;
                allowed=false;
                if (holdActionAt(rowPoint)!=-1) throw std::runtime_error("Disabled hold action executed");
                allowed=true;finishHold(rowPoint);finishHold(rowPoint);
                if (testedActions.back()!="moveToBottom" || testedActions.size()!=3) throw std::runtime_error("Hold release must execute exactly once");
                holdFinished=false;pieReady=true;finishHold(point(0,0));
                if (testedActions.back()!="hide") throw std::runtime_error("Empty hold release must cancel");
                holdFinished=false;pieReady=false;finishHold(rowPoint);
                if (testedActions.back()!="hide") throw std::runtime_error("Release before first render must cancel");
                for (int i=0;i<8;++i) {
                    holdFinished=false;pieReady=true;auto r=labelRows[i];
                    POINT middle={(r.left+r.right)/2,(r.top+r.bottom)/2};
                    auto before=testedActions.size();finishHold(middle);finishHold(middle);
                    if (testedActions.size()!=before+1 || testedActions.back()!=std::string("label.")+labelColors[i].id)
                        throw std::runtime_error("Label release did not dispatch exactly once");
                    holdFinished=false;pieReady=true;before=testedActions.size();commitLabel(i);finishHold(middle);
                    if (testedActions.size()!=before+1) throw std::runtime_error("Click plus release dispatched twice");
                }
                labelTestActionCount=testedActions.size();holdFinished=false;pieReady=true;
            }
            if (selfTest && frames==25) {
                if (testedActions.size()!=labelTestActionCount+1 || testedActions.back()!="label.red")
                    throw std::runtime_error("ImGui swatch click did not dispatch immediately");
                auto r=labelRows[1];finishHold({(r.left+r.right)/2,(r.top+r.bottom)/2});
                if (testedActions.size()!=labelTestActionCount+1) throw std::runtime_error("Swatch click repeated on CapsLock release");
                auto composed=GetWindowLongPtrW(window,GWL_EXSTYLE)&WS_EX_NOREDIRECTIONBITMAP;
                procedure(window,WM_SHOWWINDOW,FALSE,0);
                if (!composed || !(GetWindowLongPtrW(window,GWL_EXSTYLE)&WS_EX_NOREDIRECTIONBITMAP) || !holdMode || pieReady)
                    throw std::runtime_error("Hiding a pie must keep transparency and cancel hit testing");
                setHoldMode(false);
                if (!(GetWindowLongPtrW(window,GWL_EXSTYLE)&WS_EX_NOREDIRECTIONBITMAP) || compositionOpacity!=1.f)
                    throw std::runtime_error("Regular menu must retain compositor and restore opacity");
                ShowWindow(window,SW_HIDE);
                finishPlatformFrame();
                for (int iteration=0;iteration<100;++iteration) {
                    ImGui::NewFrame();drawMenu();ImGui::Render();finishPlatformFrame();
                    if (ImGui::GetCurrentContext()->FrameCountPlatformEnded!=ImGui::GetFrameCount())
                        throw std::runtime_error("Hidden frame skipped platform lifecycle");
                }
                setHoldMode(true);panelKind=2;allowed=true;
                auto numberFrame=[&](ImGuiKey key,bool down) {
                    io.AddKeyEvent(key,down);
                    ImGui::NewFrame();drawMenu();ImGui::Render();finishPlatformFrame();
                };
                for (auto entry:std::array<std::pair<ImGuiKey,const char*>,3>{{
                    {ImGuiKey_4,"select"},{ImGuiKey_Keypad8,"moveToTop"},{ImGuiKey_2,"moveToBottom"}}}) {
                    holdFinished=false;auto before=testedActions.size();
                    numberFrame(entry.first,true);numberFrame(entry.first,false);
                    finishHold({LONG(pieCenter.x),LONG(pieCenter.y)});
                    if (testedActions.size()!=before+1 || testedActions.back()!=entry.second)
                        throw std::runtime_error("Pie numeric accelerator must execute once");
                }
                auto before=testedActions.size();holdFinished=false;panelKind=1;
                numberFrame(ImGuiKey_8,true);numberFrame(ImGuiKey_8,false);
                panelKind=3;numberFrame(ImGuiKey_4,true);numberFrame(ImGuiKey_4,false);
                panelKind=2;allowed=false;numberFrame(ImGuiKey_2,true);numberFrame(ImGuiKey_2,false);
                if (testedActions.size()!=before)
                    throw std::runtime_error("Pie accelerator bypassed panel/input/busy protection");
                std::cout<<"Dear ImGui self-test passed: search, keyboard selection, Enter and mouse click dispatch; radial directions, centre cancellation, edge origin, single release, immediate swatch click; 100 hidden platform frames\n";break;
            }
            if (!preview.empty() && frames==20) {screenshot(preview);if (!previewLive) break;}
            swapChain->Present(1,0);
            finishPlatformFrame();
        }
    } catch (const std::exception& error) {std::cerr<<error.what()<<"\n";return 1;}
    ImGui_ImplDX11_Shutdown();ImGui_ImplWin32_Shutdown();ImGui::DestroyContext();releaseTarget();
    releaseDevice();
    if (IsWindow(window)) DestroyWindow(window);UnregisterClassW(wc.lpszClassName,wc.hInstance);
    if (iconHandle) DestroyIcon(iconHandle);CoUninitialize();return 0;
}
