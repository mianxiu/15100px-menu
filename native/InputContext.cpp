// Runs only in the verified PS UI thread. No text or document data is read.
#include <windows.h>
#include <imm.h>
#include "InputContextTsf.h"

static const wchar_t* controlClass=L"PhotoshopMenu.InputContext.v1";
static const wchar_t* controlProperty=L"PhotoshopMenu.InputContext.Window.v1";
static const wchar_t* nonceProperty=L"PhotoshopMenu.InputContext.Nonce.v1";
static const wchar_t* ownerProperty=L"PhotoshopMenu.InputContext.Owner.v1";
static UINT attachMessage=0,controlMessage=0;
static HMODULE module=nullptr;
static HWND control=nullptr,root=nullptr,disabledWindow=nullptr;
static HIMC originalContext=nullptr;
static HANDLE owner=nullptr;
static DWORD ownerId=0;
static ULONG_PTR nonce=0;
static ULONGLONG deadline=0;
static bool restoreFailed=false,changing=false;
static bool restored=false;
static InputContextTsf tsf;

static HIMC associated(HWND window) {
    const auto context=ImmGetContext(window);
    if(context)ImmReleaseContext(window,context);
    return context;
}
static bool restore() {
    if(!disabledWindow)return true;
    changing=true;const bool tsfRestored=tsf.restore();changing=false;
    if(!tsfRestored){restoreFailed=true;return false;}
    if(!IsWindow(disabledWindow)){disabledWindow=nullptr;originalContext=nullptr;restored=true;return true;}
    const auto current=associated(disabledWindow);
    // Do not overwrite a context PS has already replaced itself.
    if(current && current!=originalContext){disabledWindow=nullptr;originalContext=nullptr;restored=true;return true;}
    changing=true;ImmAssociateContext(disabledWindow,originalContext);changing=false;
    if(associated(disabledWindow)!=originalContext){restoreFailed=true;return false;}
    disabledWindow=nullptr;originalContext=nullptr;restoreFailed=false;restored=true;return true;
}
static bool foreground() {
    const auto window=GetForegroundWindow();
    return window && (GetAncestor(window,GA_ROOTOWNER)==root || window==root);
}
static bool ownFocus(HWND window) {
    DWORD pid=0;
    return window && GetWindowThreadProcessId(window,&pid)==GetCurrentThreadId() && pid==GetCurrentProcessId() && GetFocus()==window;
}
static LRESULT state(HWND focus) {
    DWORD pid=0;
    if(focus && (GetWindowThreadProcessId(focus,&pid)!=GetCurrentThreadId() || pid!=GetCurrentProcessId()))return 9;
    return 1 | (disabledWindow?2:0) | (!disabledWindow && focus && (associated(focus) || InputContextTsf::available())?4:0) |
        (restoreFailed?8:0) | (restored?16:0) | (tsf.keyboard?32:0);
}
static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM wParam,LPARAM lParam) {
    if(message==controlMessage && (wParam>>8)==nonce) {
        const auto focus=reinterpret_cast<HWND>(lParam);const auto operation=wParam&255;
        if(operation==3){restore();return state(focus);}
        if(operation==1)return state(focus);
        if(operation==4){
            if(disabledWindow==focus && foreground() && ownFocus(focus))deadline=GetTickCount64()+1500;
            return state(focus);
        }
        if(operation==2) {
            GUITHREADINFO info{};info.cbSize=sizeof(info);
            if(disabledWindow || !foreground() || !ownFocus(focus) || !GetGUIThreadInfo(0,&info) || info.hwndCaret || info.hwndCapture || info.hwndMenuOwner || info.hwndMoveSize)return state(focus)|8;
            const auto context=associated(focus);
            if(!context && !InputContextTsf::available())return state(focus);
            if(context && ImmGetCompositionStringW(context,GCS_COMPSTR,nullptr,0)>0)return state(focus)|8;
            restored=false;originalContext=context;disabledWindow=focus;deadline=GetTickCount64()+1500;
            changing=true;const bool tsfDisabled=tsf.start();const auto previous=ImmAssociateContext(focus,nullptr);changing=false;
            if(!tsfDisabled || previous!=context || associated(focus) || !ownFocus(focus)){restore();return state(focus)|8;}
            return state(focus);
        }
        return state(focus)|8;
    }
    if(message==WM_TIMER) {
        const bool exited=!owner || WaitForSingleObject(owner,0)!=WAIT_TIMEOUT;
        if(disabledWindow && (exited || !foreground() || GetFocus()!=disabledWindow || GetTickCount64()>deadline))restore();
        if(exited && !disabledWindow)DestroyWindow(window);
        return 0;
    }
    if(message==WM_DESTROY) {
        KillTimer(window,1);RemovePropW(root,controlProperty);RemovePropW(window,nonceProperty);RemovePropW(window,ownerProperty);
        if(owner)CloseHandle(owner);
        owner=nullptr;control=nullptr;root=nullptr;ownerId=0;
        return 0;
    }
    return DefWindowProcW(window,message,wParam,lParam);
}
[[maybe_unused]] static bool namedProcess(HANDLE process,const wchar_t* expected) {
    wchar_t path[32768]{};DWORD length=32768;
    if(!QueryFullProcessImageNameW(process,0,path,&length))return false;
    const auto name=wcsrchr(path,L'\\');return _wcsicmp(name?name+1:path,expected)==0;
}
extern "C" __declspec(dllexport) LRESULT CALLBACK InputContextHook(int code,WPARAM wParam,LPARAM lParam) {
    if(code>=0) {
        if(!attachMessage){attachMessage=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Attach.v1");controlMessage=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Control.v1");}
        const auto& event=*reinterpret_cast<CWPSTRUCT*>(lParam);
        if(!changing && disabledWindow && event.hwnd!=control &&
            (event.message==WM_KILLFOCUS || event.message==WM_LBUTTONDOWN || event.message==WM_LBUTTONDBLCLK || event.message==WM_RBUTTONDOWN ||
             (event.message==WM_ACTIVATEAPP && !event.wParam) ||
             (event.message==WM_KEYDOWN && (event.wParam=='T' || event.wParam==VK_RETURN || event.wParam==VK_F2))))restore();
        if(event.message==attachMessage && event.wParam && event.lParam>0) {
            wchar_t name[64]{};GetClassNameW(event.hwnd,name,64);
            if(wcscmp(name,L"Photoshop")!=0 || event.hwnd!=GetAncestor(event.hwnd,GA_ROOTOWNER))return CallNextHookEx(nullptr,code,wParam,lParam);
            const auto candidate=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,DWORD(event.wParam));
            if(candidate) {
#ifdef INPUT_CONTEXT_SELF_TEST
                const bool valid=DWORD(event.wParam)==GetCurrentProcessId();
#else
                const bool valid=namedProcess(GetCurrentProcess(),L"Photoshop.exe") && namedProcess(candidate,L"PhotoshopMenu.exe");
#endif
                if(valid && (!control || ownerId==DWORD(event.wParam))) {
                    if(!control) {
                        // The callback/window must remain valid until PS exits, even after unhooking.
                        HMODULE pinned=nullptr;GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&InputContextHook),&pinned);
                        WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=module;wc.lpszClassName=controlClass;RegisterClassW(&wc);
                        root=event.hwnd;ownerId=DWORD(event.wParam);owner=candidate;nonce=ULONG_PTR(event.lParam);
                        control=CreateWindowExW(0,controlClass,L"",0,0,0,0,0,HWND_MESSAGE,nullptr,module,nullptr);
                        if(control){
                            if(!SetPropW(control,nonceProperty,reinterpret_cast<HANDLE>(nonce)) || !SetPropW(control,ownerProperty,reinterpret_cast<HANDLE>(ULONG_PTR(ownerId))) ||
                               !SetPropW(root,controlProperty,control) || !SetTimer(control,1,100,nullptr))DestroyWindow(control);
                        }
                        else {CloseHandle(owner);owner=nullptr;ownerId=0;}
                    } else CloseHandle(candidate);
                } else CloseHandle(candidate);
            }
        }
    }
    return CallNextHookEx(nullptr,code,wParam,lParam);
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH){module=instance;DisableThreadLibraryCalls(instance);}
    return TRUE;
}
