// Runs only in the verified PS UI thread. No text or document data is read.
#include <windows.h>
#include <imm.h>
#include <tlhelp32.h>
#include "InputContextTsf.h"

static const wchar_t* controlClass=L"PhotoshopMenu.InputContext.v1";
static const wchar_t* controlProperty=L"PhotoshopMenu.InputContext.Window.v1";
static const wchar_t* nonceProperty=L"PhotoshopMenu.InputContext.Nonce.v1";
static const wchar_t* ownerProperty=L"PhotoshopMenu.InputContext.Owner.v1";
static const wchar_t* revisionProperty=L"PhotoshopMenu.InputContext.Revision.v1";
static constexpr UINT contextChangedMessage=WM_APP+51;
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
static ULONG_PTR revision=1;
static InputContextTsf tsf;
static bool menuHandoff=false;
#ifdef INPUT_CONTEXT_SELF_TEST
static bool testTrace=false;
#endif
static HANDLE menuProcess=nullptr;
static DWORD menuPid=0;

static bool ownMenu(HWND window) {
    if(!window || !owner || WaitForSingleObject(owner,0)!=WAIT_TIMEOUT)return false;
    window=GetAncestor(window,GA_ROOT);
    wchar_t name[64]{};GetClassNameW(window,name,64);
    if(wcscmp(name,L"PhotoshopMenuImGui")!=0)return false;
    DWORD pid=0;GetWindowThreadProcessId(window,&pid);
    if(menuProcess && menuPid==pid && WaitForSingleObject(menuProcess,0)==WAIT_TIMEOUT)return true;
    if(menuProcess){CloseHandle(menuProcess);menuProcess=nullptr;menuPid=0;}
    const auto snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snapshot==INVALID_HANDLE_VALUE)return false;
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);bool valid=false;
    for(BOOL found=Process32FirstW(snapshot,&entry);found;found=Process32NextW(snapshot,&entry))
        if(entry.th32ProcessID==pid){valid=entry.th32ParentProcessID==ownerId && _wcsicmp(entry.szExeFile,L"MenuHost.exe")==0;break;}
    CloseHandle(snapshot);if(!valid)return false;
    const auto process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,pid);
    FILETIME created{},exited{},kernel{},user{},ownerCreated{};
    if(!process)return false;
    valid=GetProcessTimes(process,&created,&exited,&kernel,&user) && GetProcessTimes(owner,&ownerCreated,&exited,&kernel,&user) &&
        CompareFileTime(&created,&ownerCreated)>=0 && WaitForSingleObject(process,0)==WAIT_TIMEOUT;
    if(!valid){CloseHandle(process);return false;}
    menuProcess=process;menuPid=pid;return true;
}
static bool ownMenuThread(DWORD thread) {
    bool found=false;
    if(thread)EnumThreadWindows(thread,[](HWND window,LPARAM data)->BOOL{
        if(!ownMenu(window))return TRUE;
        *reinterpret_cast<bool*>(data)=true;return FALSE;
    },reinterpret_cast<LPARAM>(&found));
    return found;
}
static bool menuReturning() {
    const auto window=GetForegroundWindow(),focus=GetFocus();
    return menuHandoff && (!window || window==root) && (!focus || focus==root || focus==disabledWindow);
}
static bool menuActive() {
    const auto window=GetForegroundWindow();
    return ownMenu(window) || (window==root && ownMenu(GetFocus()));
}

static void contextChanged() {
    // Defer mutation until the TSF notification callback has returned.
    if(!changing && control && disabledWindow)PostMessageW(control,contextChangedMessage,0,0);
}

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
    disabledWindow=nullptr;originalContext=nullptr;restoreFailed=false;restored=true;menuHandoff=false;return true;
}
static bool foreground() {
    const auto window=GetForegroundWindow();
    return window?(GetAncestor(window,GA_ROOTOWNER)==root || window==root || ownMenu(window)):menuReturning();
}
static bool ownFocus(HWND window) {
    DWORD pid=0;
    return window && GetWindowThreadProcessId(window,&pid)==GetCurrentThreadId() && pid==GetCurrentProcessId() && GetFocus()==window;
}
static void verifyContext() {
    if(disabledWindow && (associated(disabledWindow) || !tsf.currentDisabled())) {
#ifdef INPUT_CONTEXT_SELF_TEST
        if(testTrace)std::fprintf(stderr,"restore: changed context associated=%p tsf_current=%d\n",associated(disabledWindow),tsf.currentDisabled());
#endif
        revision=revision==0x7fffffff?1:revision+1;
        SetPropW(control,revisionProperty,reinterpret_cast<HANDLE>(revision));
        GUITHREADINFO info{};info.cbSize=sizeof(info);
        const auto focus=GetFocus();const auto activeContext=focus?associated(focus):nullptr;
        const bool handoff=menuHandoff && !associated(disabledWindow) && foreground() &&
            (focus==disabledWindow || focus==root) && GetGUIThreadInfo(0,&info) &&
            !info.hwndCaret && !info.hwndCapture && !info.hwndMenuOwner && !info.hwndMoveSize &&
            (!activeContext || ImmGetCompositionStringW(activeContext,GCS_COMPSTR,nullptr,0)<=0);
        if(handoff) {
            changing=true;const bool rebound=tsf.restore() && tsf.start() && tsf.currentDisabled();changing=false;
            if(rebound)return;
        }
        restore();
    }
}
static LRESULT state(HWND focus) {
    DWORD pid=0;
    if(focus && (GetWindowThreadProcessId(focus,&pid)!=GetCurrentThreadId() || pid!=GetCurrentProcessId()))return 9;
    return 1 | (disabledWindow?2:0) | (!disabledWindow && focus && (associated(focus) || InputContextTsf::available())?4:0) |
        (restoreFailed?8:0) | (restored?16:0) | (tsf.keyboard && tsf.currentDisabled()?32:0) | (tsf.watching()?64:0) |
        (disabledWindow && (menuActive() || menuReturning())?128:0);
}
static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM wParam,LPARAM lParam) {
    if(message==controlMessage && (wParam>>8)==nonce) {
        const auto focus=reinterpret_cast<HWND>(lParam);const auto operation=wParam&255;
        if(operation==3){restore();return state(focus);}
        if(operation==1)return state(focus);
        if(operation==4){
            verifyContext();
            if(disabledWindow==focus && foreground() && (ownFocus(focus) || menuActive()))deadline=GetTickCount64()+1500;
            return state(focus);
        }
        if(operation==2) {
            GUITHREADINFO info{};info.cbSize=sizeof(info);
            if(disabledWindow || !GetForegroundWindow() || menuActive() || !foreground() || !ownFocus(focus) || !GetGUIThreadInfo(0,&info) || info.hwndCaret || info.hwndCapture || info.hwndMenuOwner || info.hwndMoveSize)return state(focus)|8;
            const auto context=associated(focus);
            if(!context && !InputContextTsf::available())return state(focus)|8;
            if(context && ImmGetCompositionStringW(context,GCS_COMPSTR,nullptr,0)>0)return state(focus)|8;
            restored=false;originalContext=context;disabledWindow=focus;deadline=GetTickCount64()+1500;
            changing=true;const bool tsfDisabled=tsf.start();const auto previous=ImmAssociateContext(focus,nullptr);changing=false;
            if(!tsfDisabled || previous!=context || associated(focus) || !tsf.currentDisabled() || !ownFocus(focus)){restore();return state(focus)|8;}
            const auto status=state(focus);
            return status&2?status:status|8;
        }
        return state(focus)|8;
    }
    if(message==contextChangedMessage){verifyContext();return 0;}
    if(message==WM_TIMER) {
        const bool exited=!owner || WaitForSingleObject(owner,0)!=WAIT_TIMEOUT;
        if(disabledWindow && (exited || !foreground() || (GetFocus()!=disabledWindow && !menuActive() && !menuReturning()) || GetTickCount64()>deadline)){
#ifdef INPUT_CONTEXT_SELF_TEST
            if(testTrace)std::fprintf(stderr,"restore: timer exited=%d foreground=%p focus=%p disabled=%p expired=%d\n",exited,GetForegroundWindow(),GetFocus(),disabledWindow,GetTickCount64()>deadline);
#endif
            restore();
        }
        verifyContext();
        if(exited && !disabledWindow)DestroyWindow(window);
        return 0;
    }
    if(message==WM_DESTROY) {
        KillTimer(window,1);RemovePropW(root,controlProperty);RemovePropW(window,nonceProperty);RemovePropW(window,ownerProperty);RemovePropW(window,revisionProperty);
        if(owner)CloseHandle(owner);
        if(menuProcess){CloseHandle(menuProcess);menuProcess=nullptr;menuPid=0;}
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
static void observeMessage(const CWPSTRUCT& event) {
        if(disabledWindow && event.message==WM_ACTIVATEAPP)menuHandoff=ownMenuThread(DWORD(event.lParam)) || ownMenu(GetForegroundWindow());
        if(disabledWindow && event.message==WM_KILLFOCUS && ownMenu(reinterpret_cast<HWND>(event.wParam)))menuHandoff=true;
        if(disabledWindow && menuHandoff && event.message==WM_KEYDOWN && !ownMenu(event.hwnd) &&
           (event.wParam!='T' || !(GetKeyState(VK_CONTROL)&0x8000)) && event.wParam!=VK_RETURN && event.wParam!=VK_F2){verifyContext();menuHandoff=false;}
        if(!changing && disabledWindow && event.hwnd!=control && !ownMenu(event.hwnd) &&
            ((event.message==WM_KILLFOCUS && !ownMenu(reinterpret_cast<HWND>(event.wParam)) && !ownMenu(GetForegroundWindow()) && !menuReturning()) || event.message==WM_INPUTLANGCHANGE || event.message==WM_LBUTTONDOWN || event.message==WM_LBUTTONDBLCLK || event.message==WM_RBUTTONDOWN ||
             (event.message==WM_ACTIVATEAPP && !event.wParam && !ownMenu(GetForegroundWindow()) && !ownMenuThread(DWORD(event.lParam))) ||
             (event.message==WM_KEYDOWN && ((event.wParam=='T' && (GetKeyState(VK_CONTROL)&0x8000)) || event.wParam==VK_RETURN || event.wParam==VK_F2)))){
#ifdef INPUT_CONTEXT_SELF_TEST
            if(testTrace)std::fprintf(stderr,"restore: message=%x hwnd=%p disabled=%p w=%p foreground=%p\n",event.message,event.hwnd,disabledWindow,reinterpret_cast<void*>(event.wParam),GetForegroundWindow());
#endif
            restore();
        }
}
// Attach this in-process context helper to a Photoshop root window. Called by
// the injected queue/call hooks (legacy transport) and directly by the TSF
// service (InputService.dll), which is registered in HKLM instead of injected.
static bool attach(HWND rootWindow,DWORD ownerProcess,ULONG_PTR nonceValue) {
    if(!rootWindow || !ownerProcess)return false;
    wchar_t name[64]{};GetClassNameW(rootWindow,name,64);
    if(wcscmp(name,L"Photoshop")!=0 || rootWindow!=GetAncestor(rootWindow,GA_ROOTOWNER))return false;
    if(control)return ownerId==ownerProcess;
    const auto candidate=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,ownerProcess);
    if(!candidate)return false;
#ifdef INPUT_CONTEXT_SELF_TEST
    const bool valid=ownerProcess==GetCurrentProcessId();
#else
    const bool valid=namedProcess(GetCurrentProcess(),L"Photoshop.exe") && (namedProcess(candidate,L"151500px-menu.exe") || namedProcess(candidate,L"PhotoshopMenu.exe"));
#endif
    if(!valid){CloseHandle(candidate);return false;}
    // The control window must remain valid until PS exits, even after unhooking.
    HMODULE pinned=nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
                       reinterpret_cast<LPCWSTR>(&attach),&pinned);
    WNDCLASSW wc{};wc.lpfnWndProc=procedure;wc.hInstance=module;wc.lpszClassName=controlClass;RegisterClassW(&wc);
    root=rootWindow;ownerId=ownerProcess;owner=candidate;nonce=nonceValue;revision=1;tsf.notify=contextChanged;
    control=CreateWindowExW(0,controlClass,L"",0,0,0,0,0,HWND_MESSAGE,nullptr,module,nullptr);
    if(!control){CloseHandle(owner);owner=nullptr;ownerId=0;return false;}
    if(!SetPropW(control,nonceProperty,reinterpret_cast<HANDLE>(nonce)) ||
       !SetPropW(control,ownerProperty,reinterpret_cast<HANDLE>(ULONG_PTR(ownerId))) ||
       !SetPropW(control,revisionProperty,reinterpret_cast<HANDLE>(revision)) ||
       !SetPropW(root,controlProperty,control) || !SetTimer(control,1,100,nullptr)) {
        DestroyWindow(control);control=nullptr;return false;
    }
    return true;
}
static bool detach() {
    if(!control)return true;
    restore();
    DestroyWindow(control);
    control=nullptr;
    return true;
}
extern "C" __declspec(dllexport) BOOL WINAPI InputContextAttach(HWND rootWindow,DWORD ownerProcess,ULONG_PTR nonceValue) {
    return attach(rootWindow,ownerProcess,nonceValue)?TRUE:FALSE;
}
extern "C" __declspec(dllexport) BOOL WINAPI InputContextDetach() {
    return detach()?TRUE:FALSE;
}
extern "C" __declspec(dllexport) DWORD WINAPI InputContextOwner() {
    return ownerId;
}
extern "C" __declspec(dllexport) LRESULT CALLBACK InputContextQueueHook(int code,WPARAM wParam,LPARAM lParam) {
    if(code>=0 && wParam==PM_REMOVE) {
        const auto& message=*reinterpret_cast<MSG*>(lParam);
        const CWPSTRUCT event{message.lParam,message.wParam,message.message,message.hwnd};
        observeMessage(event);
    }
    return CallNextHookEx(nullptr,code,wParam,lParam);
}
extern "C" __declspec(dllexport) LRESULT CALLBACK InputContextHook(int code,WPARAM wParam,LPARAM lParam) {
    if(code>=0) {
        if(!attachMessage){attachMessage=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Attach.v1");controlMessage=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Control.v1");}
        const auto& event=*reinterpret_cast<CWPSTRUCT*>(lParam);
        observeMessage(event);
        if(event.message==attachMessage && event.wParam && event.lParam>0)
            attach(event.hwnd,DWORD(event.wParam),ULONG_PTR(event.lParam));
    }
    return CallNextHookEx(nullptr,code,wParam,lParam);
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH){module=instance;DisableThreadLibraryCalls(instance);}
    return TRUE;
}
