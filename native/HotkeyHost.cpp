// Win32 hooks: no allocation, pipe I/O or application calls in callbacks.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <array>
#include <atomic>
#include <string>
#include <regex>
#include <thread>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <utility>

enum Action { None, Toggle, Hide, Select, Color, Top, Bottom, Context, Dismiss, Ready, Error, Configured, PanelClick, HoldBegin, HoldRelease, HoldCancel, HoldPin, CapsTrace, HookHealth, CapsState, ActivationTrace, SelectAbove, SelectBelow, MoveUp, MoveDown, CopyStyle, PasteStyle, EditStyle, TriggerTrace };
static const char* names[] = {"", "toggle", "hide", "select", "color", "moveToTop", "moveToBottom", "context", "dismiss", "hooks", "configuration", "settings", "panel.click", "hold_begin", "hold_release", "hold_cancel", "hold_pin", "caps.trace", "hook.health", "caps.state", "activation.trace", "selectAbove", "selectBelow", "moveUp", "moveDown", "copyStyle", "pasteStyle", "editStyle", "trigger.trace"};
struct Binding { Action action=None; std::array<int,6> keys{}; int count=0; };
struct Config { bool enabled=false, textInput=false,colorEditor=false,diagnostic=false,remoteCompatibility=false; HWND overlay=nullptr; std::array<Binding,13> bindings{}; };
// Opt-in remote clicks qualify only on a matching release in the same verified
// PS workspace. No hover, taskbar or injected Alt+Tab activation is added.
struct RemoteClickIntent {
    uintptr_t workspace=0; ULONGLONG tick=0;
    bool event(bool down,bool enabled,uintptr_t clicked,uintptr_t foreground,ULONGLONG now) {
        if(down) {workspace=enabled?clicked:0;tick=now;return false;}
        auto previous=std::exchange(workspace,0);
        return enabled && previous && clicked==previous && foreground==previous && now-tick<=2000;
    }
};
static RemoteClickIntent remoteClick;
static int alias(int key) {
    if (key==160 || key==161) return 16;
    if (key==162 || key==163) return 17;
    if (key==164 || key==165) return 18;
    return key;
}
struct KeyMachine {
    std::array<bool,256> physical{}, held{}, consumed{};
    int pending=-1; bool used=false;
    ULONGLONG pressTime=0;
    void cancelGesture() { pending=-1; used=true; }
    void seed(int raw) { physical[raw]=held[alias(raw)]=true; }
    bool modified() const { return held[16] || held[17] || held[18] || held[91] || held[92]; }
    bool event(int raw,bool down,bool scope,const Config& cfg,bool visible,Action& action,ULONGLONG now=0,bool reserveOnly=false) {
        action=None; if (raw<0 || raw>=256) return false;
        int key=alias(raw); bool repeated=physical[raw]; physical[raw]=down;
        held[key]=false;
        // At most two physical keys share an alias; bounded, stack-only work.
        if (key==16 || key==17 || key==18) {
            int left=160+(key==17?2:key==18?4:0);
            held[key]=physical[key] || physical[left] || physical[left+1];
        } else held[key]=physical[raw];
        if (!down && consumed[key]) {
            consumed[key]=false;
            if (key==pending) {
                action=scope && !reserveOnly && !used?(now && now-pressTime<=220?HoldPin:HoldRelease):HoldCancel;
                pending=-1;
            }
            return true;
        }
        // A duplicate/orphan CapsLock up is not an outside-owned press. Never
        // leak it in reserved PS scope or let it submit a gesture. A known
        // outside down still owns its matching up (repeated=true) unchanged.
        if (!down && !repeated && scope && key==VK_CAPITAL) {
            for (const auto& b:cfg.bindings) for (int i=0;i<b.count;++i)
                if (b.keys[i]==VK_CAPITAL) return true;
        }
        // A physical press owns its whole repeat/release sequence. Never
        // reinterpret it after focus, modifiers or configuration changes.
        if (down && repeated) return consumed[key];
        if (!scope || !down) return down && consumed[key];
        // PS-owned dialogs reserve CapsLock without launching commands or
        // interfering with Tab/navigation/input in the dialog.
        if (reserveOnly) {
            if (key==VK_CAPITAL) for (const auto& b:cfg.bindings) for (int i=0;i<b.count;++i)
                if (b.keys[i]==VK_CAPITAL) {consumed[key]=true;return true;}
            return false;
        }
        const Binding* match=nullptr;
        bool tabPrefix=false;
        for (const auto& b:cfg.bindings) {
            if ((cfg.textInput || (cfg.colorEditor && visible)) && ((b.action>=Select && b.action<=Bottom) || b.action>=SelectAbove)) continue;
            if (!b.count || (!visible && b.action==Hide)) continue;
            for (int i=0;i<b.count-1;++i) if (b.keys[i]==9) tabPrefix=true;
            if (b.keys[b.count-1]!=key) continue;
            bool matches=true;
            for (int i=0;i<b.count;++i) if (!held[b.keys[i]] && !(b.keys[i]==VK_CAPITAL && visible && !cfg.textInput && !cfg.colorEditor)) matches=false;
            for (int m:{16,17,18,91,92}) {
                bool requested=false;
                for (int i=0;i<b.count;++i) if (b.keys[i]==m) requested=true;
                if (held[m]!=requested) matches=false;
            }
            if (matches && (!match || b.count>match->count)) match=&b;
        }
        if (match) {
            consumed[key]=true;
            if (match->action==Toggle) { if (!repeated) {
                if (visible) {pending=-1;action=cfg.colorEditor?Toggle:Hide;}
                else {pending=key;used=false;pressTime=now;action=HoldBegin;}
            } }
            else { if (pending!=-1) used=true; if (!repeated) action=match->action; }
            return true;
        }
        if (key==9 && !modified() && tabPrefix) { consumed[key]=true; return true; }
        // A configured CapsLock prefix is reserved in PS even if additional
        // modifiers prevent a command match. Letting that down through toggles
        // the global CapsLock state. Do not synthesize a corrective keypress.
        if (key==VK_CAPITAL) {
            for (const auto& b:cfg.bindings) for (int i=0;i<b.count;++i)
                if (b.keys[i]==VK_CAPITAL) {consumed[key]=true;return true;}
        }
        if (pending!=-1 && key!=pending && !(cfg.colorEditor && visible)) used=true;
        return consumed[key];
    }
};
struct WinRightMachine {
    bool physical=false,mapped=false;
    bool event(bool down,bool scoped,DWORD& mouse) {
        mouse=0;
        if (down) {
            if (physical) return mapped;
            physical=true;mapped=scoped;
            if (mapped) mouse=MOUSEEVENTF_RIGHTDOWN;
            return mapped;
        }
        physical=false;
        bool consumed=mapped;mapped=false;
        if (consumed) mouse=MOUSEEVENTF_RIGHTUP;
        return consumed;
    }
};
static WinRightMachine winRight;
static bool rightInjected=false;
static constexpr UINT winRightMessage=WM_APP+20;
static bool injectRight(DWORD flags) {
    INPUT input{};input.type=INPUT_MOUSE;input.mi.dwFlags=flags;
    return SendInput(1,&input,sizeof(input))==1;
}
static Config config;
static ULONGLONG diagnosticUntil=0;
static KeyMachine keys;
static HWND target=nullptr;
static bool dismissPending=false;
static std::array<bool,3> mouseConsumed{};
static std::atomic<bool> closing{false};
static DWORD hookThread;
static HANDLE available;
static ULONGLONG lastInputTick=0,lastScanUs=0;
struct ActivationGate {
    bool active=false,allowed=false,switching=false,taskbarSwitching=false,directSwitching=false;
    ULONGLONG clicked=0;
    void observe(bool scoped,ULONGLONG now) {
        if (!scoped) {active=false;allowed=false;return;}
        if (!active) {allowed=clicked && now-clicked<=2000;active=true;clicked=0;}
    }
    void observeForeground(bool scoped,bool sameOrigin,bool taskbar,ULONGLONG now,bool transition=false) {
        // GetForegroundWindow can temporarily return NULL during activation.
        // That is no foreign application and must not consume a real click.
        // Qualification still requires a scoped HWND and bounded click age.
        if (transition) return;
        if (!scoped && !switching && !taskbarSwitching && !directSwitching && clicked && !sameOrigin && !taskbar)
            clicked=0;
        observe(scoped,now);
    }
    void click(bool photoshop,ULONGLONG now) {
        if (photoshop) {clicked=active?0:now;if (active) allowed=true;}
        else {clicked=0;allowed=false;}
    }
    void switchIntent(ULONGLONG now) {clicked=now;}
    void beginSwitch(ULONGLONG now) {switching=true;switchIntent(now);}
    void beginTaskbar(ULONGLONG now) {taskbarSwitching=true;switchIntent(now);}
    void beginDirect(ULONGLONG now) {directSwitching=true;click(true,now);switchIntent(now);}
    void clickTarget(bool photoshop,bool ownedMenu,ULONGLONG now) {
        if (photoshop) beginDirect(now);
        // Clicking our own menu belongs to the existing PS session. It must
        // neither revoke that session nor grant a new one from outside PS.
        else if (!ownedMenu) click(false,now);
    }
    void finishDirect(bool scoped,ULONGLONG now) {
        directSwitching=false;
        if (scoped) {active=true;allowed=true;clicked=0;}
        else switchIntent(now);
    }
    void finishTaskbar(bool scoped,ULONGLONG now) {
        taskbarSwitching=false;
        if (scoped) {active=true;allowed=true;clicked=0;}
        else switchIntent(now);
    }
    void finishSwitch(bool scoped,ULONGLONG now) {
        switching=false;
        if (scoped) {active=true;allowed=true;clicked=0;}
        else switchIntent(now);
    }
};
static ActivationGate activation;
static HWND activationOrigin=nullptr;
static LONGLONG counterFrequency=1;
static std::atomic<ULONGLONG> droppedEvents{0},callbackPeakUs{0};
static ULONGLONG microseconds() {
    LARGE_INTEGER value{};QueryPerformanceCounter(&value);
    return static_cast<ULONGLONG>((value.QuadPart/counterFrequency)*1000000+
        (value.QuadPart%counterFrequency)*1000000/counterFrequency);
}
struct CallbackTiming {
    ULONGLONG start=microseconds();
    ~CallbackTiming() {
        auto elapsed=microseconds()-start;
        if (elapsed>callbackPeakUs.load(std::memory_order_relaxed)) callbackPeakUs.store(elapsed,std::memory_order_relaxed);
    }
};
// Single producer (hook thread), single consumer (pipe writer).
struct HookEvent {
    Action action=None; HWND hwnd=nullptr,root=nullptr; POINT cursor{};
    DWORD pid=0,flags=0,time=0;UINT message=0; int key=0,modifiers=0,matched=0;
    bool command=false,process=false,enabled=false,repeat=false,owned=false,blocked=false;
    ULONGLONG decisionUs=0,scanUs=0,renewUs=0,gapMs=0,peakUs=0,dropped=0;
    DWORD ageMs=0;
    bool attempted=false,toggleOn=false,previousToggle=false;
    bool activationAllowed=false,activationActive=false,taskbarSwitching=false,directSwitching=false;
    ULONGLONG activationIntent=0;
    wchar_t windowClass[64]{};
};
static std::array<HookEvent,1024> queue{};
static std::atomic<unsigned> head{0}, tail{0};
static void emit(Action action,HWND hwnd=nullptr,HWND root=nullptr) {
    if (action==None) return;
    unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
    if (next==tail.load(std::memory_order_acquire)) {droppedEvents.fetch_add(1,std::memory_order_relaxed);return;}
    POINT cursor{};
    if (action==HoldRelease && !GetCursorPos(&cursor)) action=HoldCancel;
    queue[head.load(std::memory_order_relaxed)]={action,hwnd,root,cursor};
    head.store(next,std::memory_order_release); SetEvent(available);
}
static bool photoshop(HWND hwnd) {
    if (!hwnd || !IsWindow(hwnd) || IsIconic(hwnd) || !IsWindowVisible(hwnd)) return false;
    wchar_t name[64]{}; GetClassNameW(hwnd,name,64);
    bool main=wcscmp(name,L"Photoshop")==0;
    if (!main && wcscmp(name,L"OWL.DocumentWindow")!=0 && wcscmp(name,L"OWL.Dock")!=0) return false;
    HWND root=main?hwnd:GetAncestor(hwnd,GA_ROOTOWNER);
    wchar_t rootName[64]{};GetClassNameW(root,rootName,64);
    if (wcscmp(rootName,L"Photoshop")!=0 || IsIconic(root) || !IsWindowVisible(root) ||
        !IsWindowEnabled(root) || !IsWindowEnabled(hwnd)) return false;
    DWORD pid=0,owner=0;GetWindowThreadProcessId(hwnd,&pid);GetWindowThreadProcessId(root,&owner);
    return pid && pid==owner;
}
static bool menuWindow(HWND hwnd);
static bool scope(HWND foreground=GetForegroundWindow()) {
    if (!config.enabled) return false;
    if (photoshop(foreground)) { target=foreground; return true; }
    // Hide and foreground restoration are separate operations. A just-hidden
    // menu may still own foreground; it remains part of this PS key scope.
    return menuWindow(foreground) && photoshop(target);
}
struct ProcessIdentity { DWORD pid=0;HANDLE handle=nullptr; };
static std::array<ProcessIdentity,32> photoshopProcesses{};
struct ProcessSnapshot {
    std::array<ProcessIdentity,32> entries{};
    ULONGLONG scanUs=0;
    ~ProcessSnapshot() {for (auto& p:entries) if (p.handle) CloseHandle(p.handle);}
};
static std::unique_ptr<ProcessSnapshot> scanPhotoshopProcesses() {
    auto result=std::make_unique<ProcessSnapshot>();
    auto started=microseconds();
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if (snapshot==INVALID_HANDLE_VALUE) return nullptr;
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
    if (Process32FirstW(snapshot,&entry)) do {
        if (_wcsicmp(entry.szExeFile,L"Photoshop.exe")!=0) continue;
        HANDLE handle=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,entry.th32ProcessID);
        if (!handle) continue;
        wchar_t path[32768]{};DWORD length=32768;
        bool valid=QueryFullProcessImageNameW(handle,0,path,&length)!=0;
        const wchar_t* name=wcsrchr(path,L'\\');name=name?name+1:path;
        valid=valid && _wcsicmp(name,L"Photoshop.exe")==0 && WaitForSingleObject(handle,0)==WAIT_TIMEOUT;
        bool stored=false;
        if (valid) for (auto& p:result->entries) if (!p.handle) {p={entry.th32ProcessID,handle};stored=true;break;}
        if (!stored) CloseHandle(handle);
    } while (Process32NextW(snapshot,&entry));
    CloseHandle(snapshot);
    result->scanUs=microseconds()-started;
    return result;
}
static void applyProcesses(ProcessSnapshot& snapshot) {
    // Only this bounded handle exchange runs on the input thread. Worker
    // snapshots own their handles until the message thread takes ownership.
    for (auto& p:photoshopProcesses) if (p.handle) CloseHandle(p.handle);
    for (size_t i=0;i<photoshopProcesses.size();++i) photoshopProcesses[i]=std::exchange(snapshot.entries[i],{});
    lastScanUs=snapshot.scanUs;
}
static void refreshPhotoshopProcesses() {
    auto snapshot=scanPhotoshopProcesses();
    if (snapshot) applyProcesses(*snapshot);
}
static bool photoshopProcessWindow(HWND hwnd) {
    DWORD pid=0;GetWindowThreadProcessId(hwnd,&pid);
    for (const auto& p:photoshopProcesses)
        if (pid && pid==p.pid && p.handle && WaitForSingleObject(p.handle,0)==WAIT_TIMEOUT) return true;
    return false;
}
static bool photoshopKeyScope(HWND foreground=GetForegroundWindow()) {
    if (!config.enabled) return false;
    return photoshopProcessWindow(foreground) ||
        (menuWindow(foreground) && photoshopProcessWindow(target));
}
static HWND remoteWorkspace(HWND child) {
    if(!child || !IsWindowVisible(child) || !IsWindowEnabled(child))return nullptr;
    HWND root=GetAncestor(child,GA_ROOT);
    if(!photoshop(root) || !photoshopProcessWindow(root))return nullptr;
    DWORD childPid=0,rootPid=0;
    GetWindowThreadProcessId(child,&childPid);GetWindowThreadProcessId(root,&rootPid);
    return childPid && childPid==rootPid?GetAncestor(root,GA_ROOTOWNER):nullptr;
}
static bool taskbarWindow(HWND hwnd) {
    if (!hwnd) return false;
    wchar_t name[64]{};GetClassNameW(GetAncestor(hwnd,GA_ROOT),name,64);
    return wcscmp(name,L"Shell_TrayWnd")==0 || wcscmp(name,L"Shell_SecondaryTrayWnd")==0 ||
           wcscmp(name,L"TaskListThumbnailWnd")==0;
}
static void observeActivation(HWND foreground,bool scoped,ULONGLONG now) {
    // If a taskbar/Alt+Tab intent activates some other application, consume
    // it there; a subsequent hover into PS must not inherit that intent.
    bool taskbar=taskbarWindow(foreground);
    ULONGLONG before=activation.clicked;
    activation.observeForeground(scoped,foreground==activationOrigin,taskbar,now,!foreground);
    static HWND previous=reinterpret_cast<HWND>(-1);
    static bool previousAllowed=false,previousActive=false;
    static ULONGLONG previousIntent=0;
    if (foreground!=previous || activation.allowed!=previousAllowed || activation.active!=previousActive || activation.clicked!=previousIntent) {
        unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
        if (next!=tail.load(std::memory_order_acquire)) {
            HookEvent event{};event.action=ActivationTrace;event.hwnd=foreground;event.root=activationOrigin;
            event.time=static_cast<DWORD>(now);event.process=scoped;event.command=taskbar;event.gapMs=before;
            GetWindowThreadProcessId(foreground,&event.pid);GetClassNameW(foreground,event.windowClass,64);
            event.activationAllowed=activation.allowed;event.activationActive=activation.active;
            event.taskbarSwitching=activation.taskbarSwitching;event.directSwitching=activation.directSwitching;
            event.activationIntent=activation.clicked;
            queue[head.load(std::memory_order_relaxed)]=event;head.store(next,std::memory_order_release);SetEvent(available);
        } else droppedEvents.fetch_add(1,std::memory_order_relaxed);
        previous=foreground;previousAllowed=activation.allowed;previousActive=activation.active;previousIntent=activation.clicked;
    }
}
static bool inside(HWND hwnd,POINT point) {
    RECT rect{}; return GetWindowRect(hwnd,&rect) && PtInRect(&rect,point);
}
static bool menuWindow(HWND hwnd) {
    if (!hwnd || !config.overlay || !IsWindow(hwnd) || !IsWindow(config.overlay)) return false;
    DWORD pid=0,owner=0;
    GetWindowThreadProcessId(hwnd,&pid);GetWindowThreadProcessId(config.overlay,&owner);
    return pid && pid==owner;
}
static bool routeKey(KeyMachine& state,int raw,bool down,bool commandScope,bool processScope,
                     const Config& cfg,bool visible,Action& action,ULONGLONG now) {
    // Reserve only CapsLock in PS-owned non-workspace windows. Other keys keep
    // their normal dialog/navigation behavior, and cannot launch scripts here.
    bool reserve=raw==VK_CAPITAL && processScope && !commandScope;
    return state.event(raw,down,commandScope || reserve,cfg,visible,action,now,reserve);
}
static LRESULT CALLBACK keyboard(int code,WPARAM message,LPARAM data) {
    CallbackTiming timing;
    if (code>=0) {
        lastInputTick=GetTickCount64();
        const auto& input=*reinterpret_cast<const KBDLLHOOKSTRUCT*>(data);
        Action action;
        HWND foreground=GetForegroundWindow();
        bool processScope=photoshopKeyScope(foreground);
        observeActivation(foreground,processScope,lastInputTick);
        // An explicit task switch is activation intent, unlike mouse hover.
        if (!(input.flags&LLKHF_INJECTED) && (message==WM_KEYDOWN || message==WM_SYSKEYDOWN) &&
            input.vkCode==VK_TAB && (keys.held[VK_MENU] || (input.flags&LLKHF_ALTDOWN))) {
            activationOrigin=foreground;activation.beginSwitch(lastInputTick);
        }
        if (!(input.flags&LLKHF_INJECTED) && alias(input.vkCode)==VK_MENU &&
            (message==WM_KEYUP || message==WM_SYSKEYUP) && activation.switching) {
            activationOrigin=foreground;activation.finishSwitch(processScope,lastInputTick);
        }
        bool commandScope=scope(foreground) && activation.allowed;
        bool repeat=input.vkCode<256 && keys.physical[input.vkCode];
        bool owned=input.vkCode<256 && keys.consumed[alias(input.vkCode)];
        if (input.vkCode==VK_LWIN && !(input.flags&LLKHF_INJECTED)) {
            DWORD mouse=0;
            if (winRight.event(message==WM_KEYDOWN || message==WM_SYSKEYDOWN,processScope,mouse)) {
                // Inject from the message loop, never recursively in a hook.
                if (mouse && !PostThreadMessageW(hookThread,winRightMessage,mouse,
                    reinterpret_cast<LPARAM>(GetForegroundWindow()))) emit(Error);
                return 1;
            }
        }
        Config localConfig=config;
        localConfig.colorEditor=config.colorEditor && menuWindow(foreground);
        bool blocked=routeKey(keys,input.vkCode,message==WM_KEYDOWN || message==WM_SYSKEYDOWN,
                     commandScope,processScope,localConfig,IsWindowVisible(config.overlay),action,GetTickCount64());
        bool traceConfigured=false;
        if(config.diagnostic && GetTickCount64()<diagnosticUntil) for(const auto& b:config.bindings)
            if(b.action==Toggle && b.count && b.keys[b.count-1]==alias(input.vkCode))traceConfigured=true;
        if (input.vkCode==VK_CAPITAL || traceConfigured) {
            unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
            if (next!=tail.load(std::memory_order_acquire)) {
                HookEvent event{};event.action=traceConfigured?TriggerTrace:CapsTrace;event.hwnd=foreground;
                event.key=alias(input.vkCode);event.matched=action;
                event.modifiers=(keys.held[16]?1:0)|(keys.held[17]?2:0)|(keys.held[18]?4:0)|(keys.held[20]?8:0);
                event.attempted=config.textInput;
                GetWindowThreadProcessId(foreground,&event.pid);
                GetClassNameW(foreground,event.windowClass,64);
                event.flags=input.flags;event.time=input.time;event.message=static_cast<UINT>(message);
                event.command=commandScope;event.process=processScope;event.enabled=config.enabled;
                event.repeat=repeat;event.owned=owned;event.blocked=blocked;
                event.activationAllowed=activation.allowed;event.activationActive=activation.active;
                event.taskbarSwitching=activation.taskbarSwitching;event.activationIntent=activation.clicked;
                event.decisionUs=microseconds()-timing.start;
                event.ageMs=GetTickCount()-input.time;
                event.dropped=droppedEvents.load(std::memory_order_relaxed);
                queue[head.load(std::memory_order_relaxed)]=event;
                head.store(next,std::memory_order_release);SetEvent(available);
            } else droppedEvents.fetch_add(1,std::memory_order_relaxed);
        }
        if (blocked) {
            emit(action); return 1;
        }
    }
    return CallNextHookEx(nullptr,code,message,data);
}
static LRESULT CALLBACK pointer(int code,WPARAM message,LPARAM data) {
    CallbackTiming timing;
    if (code>=0) {
        lastInputTick=GetTickCount64();
        HWND foreground=GetForegroundWindow();
        observeActivation(foreground,photoshopKeyScope(foreground),lastInputTick);
        int index=message==WM_LBUTTONUP || message==WM_LBUTTONDOWN?0:
                  message==WM_RBUTTONUP || message==WM_RBUTTONDOWN?1:
                  message==WM_MBUTTONUP || message==WM_MBUTTONDOWN?2:-1;
        bool up=message==WM_LBUTTONUP || message==WM_RBUTTONUP || message==WM_MBUTTONUP;
        const auto& mouse=*reinterpret_cast<const MSLLHOOKSTRUCT*>(data);
        if(index==0) {
            if(mouse.flags&LLMHF_INJECTED) {
                bool enabled=config.enabled && config.remoteCompatibility;
                HWND clicked=enabled?remoteWorkspace(WindowFromPoint(mouse.pt)):nullptr;
                HWND current=enabled && photoshop(foreground)?remoteWorkspace(foreground):nullptr;
                if(remoteClick.event(!up,enabled,reinterpret_cast<uintptr_t>(clicked),
                    reinterpret_cast<uintptr_t>(current),lastInputTick)) {
                    activationOrigin=foreground;
                    activation.clickTarget(true,false,lastInputTick);
                    activation.finishDirect(true,lastInputTick);
                }
            } else remoteClick.workspace=0;
        }
        // Complete the physical taskbar click before cancellation can consume
        // its up. Win11 can change foreground between down and up; observing
        // only the down loses intent, or never grants an already-active PS.
        if (message==WM_LBUTTONUP && activation.taskbarSwitching &&
            !(reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->flags&LLMHF_INJECTED)) {
            activation.finishTaskbar(photoshopKeyScope(foreground),lastInputTick);
            observeActivation(foreground,photoshopKeyScope(foreground),lastInputTick);
        }
        if (message==WM_LBUTTONUP && activation.directSwitching &&
            !(reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->flags&LLMHF_INJECTED)) {
            activation.finishDirect(photoshopKeyScope(foreground),lastInputTick);
        }
        if (index>=0 && up && mouseConsumed[index]) {
            mouseConsumed[index]=false;
            return 1;
        }
        if (index>=0 && !up) {
            POINT point=reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->pt;
            if (index==0 && !(reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->flags&LLMHF_INJECTED)) {
                HWND clicked=WindowFromPoint(point);
                activationOrigin=foreground;
                if (taskbarWindow(clicked)) activation.beginTaskbar(lastInputTick);
                else activation.clickTarget(photoshopProcessWindow(clicked),
                    menuWindow(clicked) && photoshopProcessWindow(target),lastInputTick);
            }
            bool visible=IsWindowVisible(config.overlay);
            if (visible && index==1 && scope()) {
                // Explicit right-click cancellation owns the click, so return
                // focus through Hide rather than outside-click Dismiss.
                keys.cancelGesture();
                emit(Hide);mouseConsumed[index]=true;return 1;
            }
            if (!visible && config.enabled) {
                HWND child=WindowFromPoint(point),root=GetAncestor(child,GA_ROOT);
                if (photoshop(root)) emit(PanelClick,child,root);
            }
            if (visible && !inside(config.overlay,point) && !menuWindow(GetAncestor(WindowFromPoint(point),GA_ROOT))) {
                bool scoped=scope();
                if (!dismissPending) { dismissPending=true; emit(Dismiss); }
                if (scoped && index!=1) { mouseConsumed[index]=true; return 1; }
            }
        }
        if (message==WM_LBUTTONDOWN || message==WM_LBUTTONUP) {
            unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
            if (next!=tail.load(std::memory_order_acquire)) {
                HookEvent event{};event.action=ActivationTrace;event.hwnd=foreground;
                event.root=WindowFromPoint(reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->pt);
                event.message=static_cast<UINT>(message);event.time=GetTickCount();
                event.flags=mouse.flags;
                event.process=photoshopProcessWindow(event.root);
                event.activationAllowed=activation.allowed;event.activationActive=activation.active;
                event.directSwitching=activation.directSwitching;event.taskbarSwitching=activation.taskbarSwitching;
                event.activationIntent=activation.clicked;
                queue[head.load(std::memory_order_relaxed)]=event;
                head.store(next,std::memory_order_release);SetEvent(available);
            } else droppedEvents.fetch_add(1,std::memory_order_relaxed);
        }
    }
    return CallNextHookEx(nullptr,code,message,data);
}
static void stop() {
    closing.store(true); PostThreadMessageW(hookThread,WM_QUIT,0,0); SetEvent(available);
}
// Restricted internal JSON schema, parsed on the pipe thread, never in a hook.
static Config parse(const std::string& line) {
    Config next;
    std::smatch match;
    auto field=[&](const char* name,const char* pattern) {
        if (!std::regex_search(line,match,std::regex(std::string("\"")+name+"\"\\s*:\\s*"+pattern)))
            throw std::runtime_error("Missing configuration field");
        return match[1].str();
    };
    next.enabled=field("enabled","(true|false)")=="true";
    if (std::regex_search(line,match,std::regex("\"text_input\"\\s*:\\s*(true|false)"))) next.textInput=match[1]=="true";
    if (std::regex_search(line,match,std::regex("\"color_editor\"\\s*:\\s*(true|false)"))) next.colorEditor=match[1]=="true";
    if (std::regex_search(line,match,std::regex("\"diagnostic_trace\"\\s*:\\s*(true|false)"))) next.diagnostic=match[1]=="true";
    if (std::regex_search(line,match,std::regex("\"remote_compatibility\"\\s*:\\s*(true|false)"))) next.remoteCompatibility=match[1]=="true";
    next.overlay=reinterpret_cast<HWND>(std::stoull(field("hwnd","([0-9]+)")));
    const Action actions[]={Toggle,Hide,Select,Color,Top,Bottom,SelectAbove,SelectBelow,MoveUp,MoveDown,CopyStyle,PasteStyle,EditStyle};
    int index=0;
    for (Action a:actions) {
        Binding& b=next.bindings[index++]; b.action=a;
        if (!std::regex_search(line,match,std::regex(std::string("\"")+names[a]+"\"\\s*:\\s*\\[([^\\]]*)\\]"))) {
            if(a>=SelectAbove)continue;
            throw std::runtime_error("Missing binding");
        }
        auto list=match[1].str();
        size_t offset=0;
        while (offset<list.size()) {
            size_t consumed=0; int key=std::stoi(list.substr(offset),&consumed);
            if (key<0 || key>=256 || b.count==6) throw std::runtime_error("Invalid binding");
            b.keys[b.count++]=key; offset+=consumed;
            while (offset<list.size() && isspace(static_cast<unsigned char>(list[offset]))) ++offset;
            if (offset==list.size()) break;
            if (list[offset++]!=',') throw std::runtime_error("Invalid binding separator");
        }
    }
    return next;
}
static void readSettings() {
    try {
        std::string line;
        while (std::getline(std::cin,line)) {
            if (line.find("\"quit\"")!=std::string::npos) break;
            auto next=std::make_unique<Config>(parse(line));
            if (!PostThreadMessageW(hookThread,WM_APP,0,reinterpret_cast<LPARAM>(next.get()))) break;
            next.release();
        }
    } catch (...) { PostThreadMessageW(hookThread,WM_APP+1,0,0); }
    PostThreadMessageW(hookThread,WM_QUIT,0,0);
}
static void writeActions() {
    HANDLE output=GetStdHandle(STD_OUTPUT_HANDLE);
    while (!closing.load() || tail.load()!=head.load()) {
        unsigned cursor=tail.load(std::memory_order_relaxed);
        while (cursor!=head.load(std::memory_order_acquire)) {
            auto event=queue[cursor];Action action=event.action; cursor=(cursor+1)%queue.size(); tail.store(cursor,std::memory_order_release);
            const char* type=action==Ready?"ready":action==Error?"error":action==Configured?"configured":"action";
            std::string line;
            if (action==ActivationTrace) {
                std::wstring wideClass(event.windowClass);std::string windowClass(wideClass.begin(),wideClass.end());
                windowClass=std::regex_replace(windowClass,std::regex("[^A-Za-z0-9_.# -]"),"_");
                line=std::string("{\"type\":\"")+(event.message?"activation.trace":"activation.foreground")+"\",\"foreground\":"+std::to_string(reinterpret_cast<uintptr_t>(event.hwnd))+
                    ",\"clicked\":"+std::to_string(reinterpret_cast<uintptr_t>(event.root))+",\"message\":"+std::to_string(event.message)+
                    ",\"pid\":"+std::to_string(event.pid)+",\"window_class\":\""+windowClass+"\",\"taskbar\":"+(event.command?"true":"false")+
                    ",\"flags\":"+std::to_string(event.flags)+
                    ",\"intent_before\":"+std::to_string(event.gapMs)+
                    ",\"tick_ms\":"+std::to_string(event.time)+",\"clicked_ps\":"+(event.process?"true":"false")+
                    ",\"allowed\":"+(event.activationAllowed?"true":"false")+",\"active\":"+(event.activationActive?"true":"false")+
                    ",\"direct_switching\":"+(event.directSwitching?"true":"false")+
                    ",\"taskbar_switching\":"+(event.taskbarSwitching?"true":"false")+
                    ",\"intent_tick\":"+std::to_string(event.activationIntent)+"}\n";
                DWORD written=0;
                if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) {stop();return;}
                continue;
            }
            if (action==CapsState) {
                line="{\"type\":\"caps.state\",\"tick_ms\":"+std::to_string(event.gapMs)+
                    ",\"toggle_on\":"+(event.toggleOn?"true":"false")+",\"previous\":"+(event.previousToggle?"true":"false")+
                    ",\"baseline\":"+(event.enabled?"true":"false")+",\"hwnd\":"+std::to_string(reinterpret_cast<uintptr_t>(event.hwnd))+
                    ",\"pid\":"+std::to_string(event.pid)+",\"process_scope\":"+(event.process?"true":"false")+
                    ",\"tracked_down\":"+(event.repeat?"true":"false")+",\"owned\":"+(event.owned?"true":"false")+
                    ",\"dropped_total\":"+std::to_string(event.dropped)+",\"source\":\"GetKeyState; hook message queue\"}\n";
                DWORD written=0;
                if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) {stop();return;}
                continue;
            }
            if (action==HookHealth) {
                line="{\"type\":\"hook.health\",\"scan_us\":"+std::to_string(event.scanUs)+
                    ",\"renew_us\":"+std::to_string(event.renewUs)+",\"timer_gap_ms\":"+std::to_string(event.gapMs)+
                    ",\"callback_peak_us\":"+std::to_string(event.peakUs)+",\"dropped_total\":"+std::to_string(event.dropped)+
                    ",\"renew_ok\":"+(event.blocked?"true":"false")+",\"renew_attempted\":"+(event.attempted?"true":"false")+
                    ",\"scan_on_worker\":true}\n";
                DWORD written=0;
                if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) {stop();return;}
                continue;
            }
            if (action==CapsTrace || action==TriggerTrace) {
                std::string windowClass;
                for (wchar_t c:event.windowClass) {
                    if (!c) break;
                    if (c==L'"' || c==L'\\') windowClass+='\\';
                    windowClass+=c>=32 && c<=126?static_cast<char>(c):'?';
                }
                line=std::string("{\"type\":\"")+(action==TriggerTrace?"trigger.trace":"caps.trace")+"\",\"key\":"+std::to_string(event.key)+",\"modifiers\":"+std::to_string(event.modifiers)+",\"matched_action\":\""+names[event.matched]+"\",\"text_input\":"+(event.attempted?"true":"false")+",\"hwnd\":"+std::to_string(reinterpret_cast<uintptr_t>(event.hwnd))+
                    ",\"pid\":"+std::to_string(event.pid)+",\"window_class\":\""+windowClass+"\",\"message\":"+std::to_string(event.message)+
                    ",\"flags\":"+std::to_string(event.flags)+",\"key_time_ms\":"+std::to_string(event.time)+
                    ",\"command_scope\":"+(event.command?"true":"false")+",\"process_scope\":"+(event.process?"true":"false")+
                    ",\"enabled\":"+(event.enabled?"true":"false")+",\"repeat\":"+(event.repeat?"true":"false")+
                    ",\"owned_before\":"+(event.owned?"true":"false")+",\"blocked\":"+(event.blocked?"true":"false")+
                    ",\"activation_allowed\":"+(event.activationAllowed?"true":"false")+
                    ",\"activation_active\":"+(event.activationActive?"true":"false")+
                    ",\"taskbar_switching\":"+(event.taskbarSwitching?"true":"false")+
                    ",\"activation_intent_tick\":"+std::to_string(event.activationIntent)+
                    ",\"decision_us\":"+std::to_string(event.decisionUs)+",\"delivery_age_ms\":"+std::to_string(event.ageMs)+
                    ",\"dropped_total\":"+std::to_string(event.dropped)+"}\n";
                DWORD written=0;
                if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) {stop();return;}
                continue;
            }
            if (action==PanelClick) line="{\"type\":\"panel.click\",\"hwnd\":"+std::to_string(reinterpret_cast<uintptr_t>(event.hwnd))+",\"root\":"+std::to_string(reinterpret_cast<uintptr_t>(event.root))+"}\n";
            else {
                line=std::string("{\"type\":\"")+type+"\",\"action\":\""+names[action]+"\"";
                if (action==HoldRelease) line+=",\"cursor\":["+std::to_string(event.cursor.x)+","+std::to_string(event.cursor.y)+"]";
                line+="}\n";
            }
            DWORD written=0;
            if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) { stop(); return; }
        }
        if (!closing.load()) WaitForSingleObject(available,250);
    }
}
static void check(bool value) { if (!value) throw std::runtime_error("Native hook self-test failed"); }
static bool renewalAllowed(ULONGLONG now,ULONGLONG last,bool capsHeld,bool winHeld,bool mouseHeld) {
    return !capsHeld && !winHeld && !mouseHeld && now-last>=250;
}
static void sampleCapsState(bool force=false) {
    static bool sampled=false,previous=false;
    // The low bit is the toggle bit. GetAsyncKeyState's low bit is NOT a
    // toggle state. Sample only from the pumping message thread, not a hook.
    bool current=(GetKeyState(VK_CAPITAL)&1)!=0;
    if (sampled && current==previous && !force) return;
    unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
    if (next!=tail.load(std::memory_order_acquire)) {
        HookEvent event{};event.action=CapsState;event.hwnd=GetForegroundWindow();
        GetWindowThreadProcessId(event.hwnd,&event.pid);
        event.toggleOn=current;event.previousToggle=previous;event.enabled=!sampled || force;
        event.process=photoshopKeyScope(event.hwnd);event.repeat=keys.physical[VK_CAPITAL];event.owned=keys.consumed[VK_CAPITAL];
        event.gapMs=GetTickCount64();event.dropped=droppedEvents.load(std::memory_order_relaxed);
        queue[head.load(std::memory_order_relaxed)]=event;
        head.store(next,std::memory_order_release);SetEvent(available);
        sampled=true;previous=current;
    } else droppedEvents.fetch_add(1,std::memory_order_relaxed);
}
static int selfTest() {
    // Complete remote click pairs only: opt-in, same valid workspace and 2s.
    RemoteClickIntent remote;
    check(!remote.event(true,false,10,10,100));
    check(!remote.event(false,false,10,10,101));
    check(!remote.event(true,true,10,0,200));
    check(remote.event(false,true,10,10,201));
    check(!remote.event(false,true,10,10,202)); // release cannot replay
    for(auto pair:std::array<std::pair<uintptr_t,uintptr_t>,4>{{{0,10},{10,0},{11,10},{10,11}}}) {
        remote.event(true,true,10,10,300);
        check(!remote.event(false,true,pair.first,pair.second,301));
    }
    remote.event(true,true,10,10,400);
    check(!remote.event(false,true,10,10,2401));
    remote.event(true,true,10,10,3000);
    check(!remote.event(false,false,10,10,3001));
    remote.event(true,true,0,10,4000); // taskbar/foreign/modal not a workspace
    check(!remote.event(false,true,10,10,4001));
    ActivationGate gate;
    gate.observe(false,100);gate.observe(true,200);check(!gate.allowed);
    gate.click(true,201);check(gate.allowed);
    gate.observe(true,1000);check(gate.allowed);
    gate.observe(false,1100);check(!gate.allowed);
    gate.observe(true,1200);check(!gate.allowed);
    gate.observe(false,1300);gate.click(true,1400);gate.observe(true,1401);check(gate.allowed);
    gate.observe(false,1500);gate.click(true,1600);gate.observe(true,2200);check(gate.allowed);
    gate.observe(false,2300);gate.click(true,2400);gate.observe(true,4500);check(!gate.allowed);
    gate.switchIntent(4600);gate.observe(false,4601);gate.observe(true,4700);check(gate.allowed);
    gate.observe(false,4800);gate.beginSwitch(4900);
    gate.observe(false,5000);check(gate.switching && !gate.allowed);
    gate.observe(true,10000);check(!gate.allowed);
    gate.finishSwitch(true,10100);check(gate.allowed && !gate.switching && !gate.clicked);
    gate.observe(false,10200);gate.observe(true,10300);check(!gate.allowed);
    gate.observe(false,10400);gate.beginSwitch(10500);gate.finishSwitch(false,10600);
    gate.observe(true,10601);check(gate.allowed);
    // Taskbar clicking an already-foreground, unqualified PS must qualify it.
    gate.observe(false,11000);gate.observe(true,11001);check(!gate.allowed);
    gate.beginTaskbar(11002);gate.observe(true,11003);check(gate.taskbarSwitching);
    gate.finishTaskbar(true,11004);check(gate.allowed && !gate.taskbarSwitching);
    // Temporary taskbar foreground does not end the click gesture.
    gate.observe(false,11100);gate.beginTaskbar(11101);gate.observe(false,11102);
    check(gate.taskbarSwitching);gate.finishTaskbar(true,11103);check(gate.allowed);
    // Delayed final PS activation remains bounded; ordinary hover cannot reuse it.
    gate.observe(false,11200);gate.beginTaskbar(11201);gate.finishTaskbar(false,11202);
    gate.observe(true,11203);check(gate.allowed);
    gate.observe(false,11204);gate.observe(true,11205);check(!gate.allowed);
    gate.beginTaskbar(11300);gate.finishTaskbar(false,11301);
    gate.observe(true,14000);check(!gate.allowed);
    gate.observe(false,14100);gate.beginTaskbar(14101);
    gate.observeForeground(false,false,false,14102);check(gate.clicked && gate.taskbarSwitching);
    gate.finishTaskbar(true,14103);check(gate.allowed);
    gate.observe(false,14200);gate.beginTaskbar(14201);gate.finishTaskbar(false,14202);
    gate.observeForeground(false,false,false,14203);check(!gate.clicked);
    gate.observe(true,14204);check(!gate.allowed); // Other app won; hover must not inherit.
    // Taskbar release -> NULL activation gap -> PS must retain the click.
    gate.observe(false,14300);gate.beginTaskbar(14301);gate.finishTaskbar(false,14302);
    gate.observeForeground(false,false,true,14303);
    gate.observeForeground(false,false,false,14304,true);check(gate.clicked==14302);
    gate.observeForeground(true,false,false,14305);check(gate.allowed);
    // A later transient NULL must not revoke an already-qualified PS either.
    gate.observeForeground(false,false,false,14306,true);check(gate.active && gate.allowed);
    gate.observeForeground(true,false,false,14307);check(gate.allowed);
    gate.observeForeground(false,false,false,14308);check(!gate.allowed);
    gate.observeForeground(true,false,false,14309);check(!gate.allowed);
    // NULL gaps cannot extend the original two-second activation intent.
    gate.observe(false,14400);gate.beginTaskbar(14401);gate.finishTaskbar(false,14402);
    gate.observeForeground(false,false,false,17000,true);
    gate.observeForeground(true,false,false,17001);check(!gate.allowed);
    // A PS click can pass through an intermediate foreground before its up.
    gate.observe(false,15000);gate.beginDirect(15001);
    gate.observeForeground(false,false,false,15002);
    check(gate.directSwitching && gate.clicked);
    gate.finishDirect(true,15003);check(gate.allowed && !gate.directSwitching);
    gate.observe(false,15004);gate.observe(true,15005);check(!gate.allowed);
    // Also restore an already-foreground PS whose earlier qualification was lost.
    gate.beginDirect(15100);gate.finishDirect(true,15101);check(gate.allowed);
    gate.observe(false,15200);gate.beginDirect(15201);gate.finishDirect(false,15202);
    gate.observeForeground(false,false,false,15203);check(!gate.clicked);
    gate.observe(true,15204);check(!gate.allowed);
    gate.clickTarget(true,false,15300);gate.finishDirect(true,15301);check(gate.allowed);
    for (int i=0;i<10000;++i) {
        gate.clickTarget(false,true,15302+i); // Own menu click then return to PS.
        gate.observe(true,15303+i);check(gate.allowed);
    }
    gate.clickTarget(false,false,26000);check(!gate.allowed);
    gate.observe(false,26001);gate.clickTarget(false,true,26002);
    gate.observe(true,26003);check(!gate.allowed); // Own menu never grants new scope.
    for (int i=0;i<10000;++i) {
        ULONGLONG last=1000+i*20;
        check(!renewalAllowed(last+20,last,false,false,false));
        check(!renewalAllowed(last+600,last,true,false,false));
        check(!renewalAllowed(last+600,last,false,true,false));
        check(!renewalAllowed(last+600,last,false,false,true));
        check(renewalAllowed(last+250,last,false,false,false));
    }
    for (const auto pair:std::array<std::pair<int,Action>,5>{{{67,CopyStyle},{86,PasteStyle},{70,EditStyle},{87,SelectAbove},{83,SelectBelow}}}) {
        Config ref;ref.bindings[0]={Toggle,{20},1};ref.bindings[1]={pair.second,{20,pair.first},2};
        for(bool pinned:{false,true}) {
            KeyMachine machine;Action result;
            if(!pinned)check(machine.event(20,true,true,ref,false,result,1000) && result==HoldBegin);
            check(machine.event(pair.first,true,true,ref,pinned,result,1100) && result==pair.second);
            check(machine.event(pair.first,true,true,ref,pinned,result,1110) && result==None);
            check(machine.event(pair.first,false,true,ref,pinned,result,1120) && result==None);
            if(!pinned)check(machine.event(20,false,true,ref,pinned,result,1200) && result==HoldCancel);
        }
        for(int guarded:{0,1,2}) {
            KeyMachine machine;Action result;ref.textInput=guarded==1;ref.colorEditor=guarded==2;
            check(!machine.event(pair.first,true,guarded!=0,ref,true,result,1000) && result==None);
        }
    }
    for(int shift:{VK_LSHIFT,VK_RSHIFT}) for(bool releaseShiftFirst:{false,true}) {
        Config cfg;cfg.enabled=true;cfg.bindings[0]={Toggle,{VK_SHIFT,90},2};KeyMachine machine;Action action;
        check(!machine.event(shift,true,true,cfg,false,action,1000));
        check(machine.event(90,true,true,cfg,false,action,1010) && action==HoldBegin);
        check(machine.event(90,true,true,cfg,false,action,1020) && action==None);
        if(releaseShiftFirst)check(!machine.event(shift,false,true,cfg,true,action,1030));
        check(machine.event(90,false,true,cfg,true,action,1100) && action==HoldPin);
        if(!releaseShiftFirst)check(!machine.event(shift,false,true,cfg,true,action,1110));
        KeyMachine outside;check(!outside.event(shift,true,false,cfg,false,action));
        check(!outside.event(90,true,false,cfg,false,action) && action==None);
    }
    Config cfg; cfg.bindings[0]={Toggle,{20},1}; cfg.bindings[1]={Select,{20,65},2};
    KeyMachine state; Action action;
    WinRightMachine remap;DWORD mouse=0;
    for (int i=0;i<10000;++i) {
        check(remap.event(true,true,mouse) && mouse==MOUSEEVENTF_RIGHTDOWN);
        check(remap.event(true,false,mouse) && mouse==0);
        check(remap.event(false,false,mouse) && mouse==MOUSEEVENTF_RIGHTUP);
    }
    check(!remap.event(true,false,mouse) && mouse==0);
    check(!remap.event(true,true,mouse) && mouse==0);
    check(!remap.event(false,true,mouse) && mouse==0);
    remap.physical=true; // Startup while already held: do not capture mid-press.
    check(!remap.event(true,true,mouse) && mouse==0);
    check(!remap.event(false,true,mouse) && mouse==0);
    KeyMachine dialog;
    check(dialog.event(20,true,true,cfg,false,action,1000,true) && action==None);
    check(dialog.event(20,true,true,cfg,false,action,1010,true) && action==None);
    check(!dialog.event(9,true,true,cfg,false,action,1020,true) && action==None);
    check(dialog.event(20,false,false,cfg,false,action,1030,true) && action==None);
    KeyMachine processCaps;
    check(routeKey(processCaps,20,false,true,true,cfg,false,action,900) && action==None);
    check(routeKey(processCaps,20,false,false,true,cfg,false,action,901) && action==None);
    check(!routeKey(processCaps,20,false,false,false,cfg,false,action,902) && action==None);
    Config noCaps;noCaps.bindings[0]={Toggle,{9},1};
    check(!routeKey(processCaps,20,false,true,true,noCaps,false,action,903));
    for (int i=0;i<10000;++i) {
        check(routeKey(processCaps,20,true,false,true,cfg,false,action,1000) && action==None);
        check(routeKey(processCaps,20,true,false,true,cfg,false,action,1010) && action==None);
        check(!routeKey(processCaps,65,true,false,true,cfg,false,action,1020) && action==None);
        check(!routeKey(processCaps,65,false,false,true,cfg,false,action,1025) && action==None);
        check(routeKey(processCaps,20,false,false,false,cfg,false,action,1030) && action==None);
    }
    check(routeKey(processCaps,20,true,true,true,cfg,false,action,1000) && action==HoldBegin);
    check(routeKey(processCaps,20,false,false,true,cfg,true,action,1050) && action==HoldCancel);
    check(!routeKey(processCaps,20,true,false,false,cfg,false,action,1100));
    check(!routeKey(processCaps,20,true,true,true,cfg,false,action,1120));
    check(!routeKey(processCaps,20,false,true,true,cfg,false,action,1130));
    check(routeKey(processCaps,20,true,true,true,cfg,false,action,1200) && action==HoldBegin);
    check(routeKey(processCaps,20,false,true,true,cfg,true,action,1250) && action==HoldPin);
    check(routeKey(processCaps,20,false,true,true,cfg,true,action,1260) && action==None);
    check(!routeKey(processCaps,20,true,false,false,cfg,false,action,1300));
    check(!routeKey(processCaps,20,false,true,true,cfg,false,action,1310) && action==None);
    KeyMachine cancelled;
    check(cancelled.event(20,true,true,cfg,false,action,1000) && action==HoldBegin);
    cancelled.cancelGesture();
    check(cancelled.event(20,false,true,cfg,false,action,1050) && action==None);
    check(cancelled.event(20,true,true,cfg,false,action,1200) && action==HoldBegin);
    check(cancelled.event(20,false,true,cfg,true,action,1250) && action==HoldPin);
    KeyMachine taps;
    check(taps.event(20,true,true,cfg,false,action,1000) && action==HoldBegin);
    check(taps.event(20,false,true,cfg,false,action,1050) && action==HoldPin);
    check(taps.event(20,true,true,cfg,false,action,1200) && action==HoldBegin);
    check(taps.event(20,true,true,cfg,true,action,1220) && action==None);
    check(taps.event(20,false,true,cfg,true,action,1250) && action==HoldPin);
    check(taps.event(20,true,true,cfg,false,action,1600) && action==HoldBegin);
    check(taps.event(20,false,true,cfg,true,action,2000) && action==HoldRelease);
    check(taps.event(20,true,true,cfg,true,action,2010) && action==Hide);
    check(taps.event(20,false,true,cfg,false,action,2050) && action==None);
    check(taps.event(20,true,true,cfg,false,action,2100) && action==HoldBegin);
    check(taps.event(20,false,false,cfg,false,action,2150) && action==HoldCancel);
    check(taps.event(20,true,true,cfg,false,action,2200) && action==HoldBegin);
    for (int i=0;i<10000;++i) {
        check(state.event(20,true,true,cfg,false,action) && action==HoldBegin);
        check(state.event(20,true,true,cfg,false,action) && action==None);
        check(state.event(20,false,true,cfg,false,action) && action==HoldRelease);
    }
    state.event(20,true,true,cfg,false,action);
    check(state.event(65,true,true,cfg,false,action) && action==Select);
    check(state.event(65,true,true,cfg,false,action) && action==None);
    check(state.event(65,false,true,cfg,false,action));
    check(state.event(20,false,true,cfg,false,action) && action==HoldCancel);
    state.event(20,true,true,cfg,false,action);
    check(state.event(20,false,false,cfg,false,action) && action==HoldCancel);
    cfg.textInput=true;
    state.event(20,true,true,cfg,false,action);
    check(!state.event(65,true,true,cfg,false,action) && action==None);
    state.event(65,false,true,cfg,false,action);
    check(state.event(20,false,true,cfg,false,action) && action==HoldCancel);
    cfg.textInput=false;
    check(!state.event(20,true,false,cfg,false,action));
    check(!state.event(20,false,false,cfg,false,action));
    state.event(162,true,true,cfg,false,action);
    check(state.event(20,true,true,cfg,false,action) && action==None);
    check(state.event(20,false,true,cfg,false,action) && action==None);
    state.event(163,true,true,cfg,false,action); state.event(162,false,true,cfg,false,action);
    check(state.modified()); state.event(163,false,true,cfg,false,action); check(!state.modified());
    for (int modifier:{160,161,162,163,164,165,91,92}) {
        KeyMachine modifiedState;
        modifiedState.event(modifier,true,true,cfg,false,action);
        check(modifiedState.event(20,true,true,cfg,false,action) && action==None);
        modifiedState.event(modifier,false,true,cfg,false,action);
        check(modifiedState.event(20,true,true,cfg,false,action) && action==None);
        check(modifiedState.event(20,false,false,cfg,false,action) && action==None);
    }
    // Presses begun outside PS stay passed through until release, even when
    // auto-repeat arrives after focus returns; no unmatched release is eaten.
    check(!state.event(20,true,false,cfg,false,action));
    check(!state.event(20,true,true,cfg,false,action) && action==None);
    check(!state.event(20,false,true,cfg,false,action));
    // Conversely a captured press remains captured through disable/rebind.
    check(state.event(20,true,true,cfg,false,action) && action==HoldBegin);
    Config empty;
    check(state.event(20,true,false,empty,false,action) && action==None);
    check(state.event(20,false,false,empty,false,action) && action==HoldCancel);
    check(!state.event(20,true,true,empty,false,action));
    check(!state.event(20,false,true,empty,false,action));
    Config paintConfig=cfg;paintConfig.colorEditor=true;
    KeyMachine paintKeys;
    check(paintKeys.event(20,true,true,paintConfig,false,action,3000) && action==HoldBegin);
    for(int local:{9,65,67,87,83,49,70}) {
        check(!paintKeys.event(local,true,true,paintConfig,true,action,3100) && action==None);
        check(!paintKeys.event(local,false,true,paintConfig,true,action,3200) && action==None);
    }
    check(paintKeys.event(20,false,true,paintConfig,true,action,3400) && action==HoldRelease);
    check(paintKeys.event(20,true,true,paintConfig,true,action,3500) && action==Toggle);
    check(paintKeys.event(20,false,true,paintConfig,true,action,3510) && action==None);
    cfg.bindings[0]={Toggle,{9},1}; cfg.bindings[1]={Top,{9,87},2};
    for (int i=0;i<10000;++i) {
        check(state.event(9,true,true,cfg,false,action) && action==HoldBegin);
        check(state.event(9,false,true,cfg,false,action) && action==HoldRelease);
    }
    state.event(9,true,true,cfg,false,action);
    check(state.event(87,true,true,cfg,false,action) && action==Top);
    state.event(87,false,true,cfg,false,action);
    check(state.event(9,false,true,cfg,false,action) && action==HoldCancel);
    std::cout<<"Native hotkey self-test passed: 10000 CapsLock and Tab pairs, repeat, scope, modifiers, combinations\n";
    return 0;
}
static bool renewHooks(HHOOK& keyHook,HHOOK& mouseHook) {
    // Install replacements first. Preserve KeyMachine and mouseConsumed so a
    // held press keeps its original suppression decision through renewal.
    HHOOK nextKey=SetWindowsHookExW(WH_KEYBOARD_LL,keyboard,GetModuleHandleW(nullptr),0);
    HHOOK nextMouse=SetWindowsHookExW(WH_MOUSE_LL,pointer,GetModuleHandleW(nullptr),0);
    if (!nextKey || !nextMouse) {
        if (nextKey) UnhookWindowsHookEx(nextKey);
        if (nextMouse) UnhookWindowsHookEx(nextMouse);
        return false;
    }
    if (keyHook) UnhookWindowsHookEx(keyHook);
    if (mouseHook) UnhookWindowsHookEx(mouseHook);
    keyHook=nextKey;mouseHook=nextMouse;return true;
}
int main(int argc,char** argv) {
    LARGE_INTEGER frequency{};QueryPerformanceFrequency(&frequency);counterFrequency=frequency.QuadPart;
    // MSLLHOOKSTRUCT uses physical per-monitor coordinates. GetWindowRect and
    // WindowFromPoint must use the same coordinate space at 125/150/200% DPI.
    auto dpi=reinterpret_cast<BOOL(WINAPI*)(HANDLE)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetProcessDpiAwarenessContext"));
    if (!dpi || !dpi(reinterpret_cast<HANDLE>(-4))) SetProcessDPIAware();
    if (argc==3 && std::string(argv[1])=="--inspect-window") {
        HWND hwnd=reinterpret_cast<HWND>(std::stoull(argv[2]));RECT rect{};
        if (!GetWindowRect(hwnd,&rect)) return 1;
        std::cout<<"["<<rect.left<<","<<rect.top<<","<<rect.right<<","<<rect.bottom<<"]\n";return 0;
    }
    if (argc==3 && std::string(argv[1])=="--inspect-workspace") {
        HWND hwnd=reinterpret_cast<HWND>(std::stoull(argv[2]));
        std::cout<<(photoshop(hwnd)?"true":"false")<<"\n";return 0;
    }
    if (argc==3 && std::string(argv[1])=="--inspect-win-scope") {
        HWND hwnd=reinterpret_cast<HWND>(std::stoull(argv[2]));
        refreshPhotoshopProcesses();
        std::cout<<(photoshopProcessWindow(hwnd)?"true":"false")<<"\n";return 0;
    }
    if (argc==2 && std::string(argv[1])=="--self-test") return selfTest();
    if (argc==3 && std::string(argv[1])=="--self-test-process-scope") {
        bool expected=std::string(argv[2])=="true";
        refreshPhotoshopProcesses();
        for (const wchar_t* name:{L"Photoshop",L"PSFloatC",L"FutureUnknownPSPopup"}) {
            WNDCLASSW wc{};wc.lpfnWndProc=DefWindowProcW;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=name;
            check(RegisterClassW(&wc)!=0);
            HWND hwnd=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,name,L"Isolated process scope test",
                WS_POPUP,-10000,-10000,10,10,nullptr,nullptr,wc.hInstance,nullptr);
            check(hwnd!=nullptr);
            check(photoshopProcessWindow(hwnd)==expected);
            ShowWindow(hwnd,SW_SHOWNOACTIVATE);
            check((remoteWorkspace(hwnd)!=nullptr)==(expected && wcscmp(name,L"Photoshop")==0));
            EnableWindow(hwnd,FALSE);check(photoshopProcessWindow(hwnd)==expected);
            check(remoteWorkspace(hwnd)==nullptr);
            auto previous=photoshopProcesses;
            for (auto& p:photoshopProcesses) p={};
            HANDLE ended=CreateEventW(nullptr,TRUE,TRUE,nullptr);
            photoshopProcesses[0]={GetCurrentProcessId(),ended};
            check(!photoshopProcessWindow(hwnd));
            CloseHandle(ended);photoshopProcesses=previous;
            DestroyWindow(hwnd);check(!photoshopProcessWindow(hwnd));
            UnregisterClassW(name,wc.hInstance);
        }
        check(!photoshopProcessWindow(nullptr));
        for (auto& p:photoshopProcesses) if (p.handle) CloseHandle(p.handle);
        std::cout<<"Process scope self-test passed: classes, disabled windows, executable identity, stale PID\n";return 0;
    }
    if (argc==2 && std::string(argv[1])=="--self-test-hooks") {
        HHOOK key=nullptr,mouse=nullptr;
        Config cfg;cfg.bindings[0]={Toggle,{20},1};Action action;
        check(keys.event(20,true,true,cfg,false,action) && action==HoldBegin);
        for (int i=0;i<30;++i) {
            if (!renewHooks(key,mouse)) return 1;
            check(keys.event(20,true,true,cfg,false,action) && action==None);
            // Simulate Windows removing hooks without ending the host process.
            UnhookWindowsHookEx(key);UnhookWindowsHookEx(mouse);
        }
        if (!renewHooks(key,mouse)) return 1;
        check(keys.event(20,false,false,cfg,false,action) && action==HoldCancel);
        UnhookWindowsHookEx(key);UnhookWindowsHookEx(mouse);
        std::cout<<"Hook renewal passed: 30 silent-removal cycles, no input injection\n";return 0;
    }
    DWORD parent=argc==3 && std::string(argv[1])=="--parent"?std::stoul(argv[2]):0;
    hookThread=GetCurrentThreadId(); MSG message; PeekMessageW(&message,nullptr,0,0,PM_NOREMOVE);
    available=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    if (!available) return 1;
    for (int vk:{160,161,162,163,164,165,91,92}) if (GetAsyncKeyState(vk)&0x8000) keys.seed(vk);
    winRight.physical=(GetAsyncKeyState(VK_LWIN)&0x8000)!=0;
    SetThreadPriority(GetCurrentThread(),THREAD_PRIORITY_ABOVE_NORMAL);
    refreshPhotoshopProcesses();
    HHOOK keyHook=SetWindowsHookExW(WH_KEYBOARD_LL,keyboard,GetModuleHandleW(nullptr),0);
    HHOOK mouseHook=SetWindowsHookExW(WH_MOUSE_LL,pointer,GetModuleHandleW(nullptr),0);
    std::thread writer(writeActions);
    if (!keyHook || !mouseHook) {
        emit(Error); closing.store(true); SetEvent(available); writer.join();
        if (keyHook) UnhookWindowsHookEx(keyHook);
        if (mouseHook) UnhookWindowsHookEx(mouseHook);
        CloseHandle(available); return 1;
    }
    std::thread(readSettings).detach();
    if (parent) std::thread([parent]{
        HANDLE process=OpenProcess(SYNCHRONIZE,FALSE,parent);
        if (process) { WaitForSingleObject(process,INFINITE); CloseHandle(process); }
        stop();
    }).detach();
    emit(Ready);
    std::thread processScanner([]{
        while (!closing.load()) {
            for (int i=0;i<20 && !closing.load();++i) Sleep(50);
            if (closing.load()) break;
            auto snapshot=scanPhotoshopProcesses();
            if (snapshot && PostThreadMessageW(hookThread,WM_APP+22,0,reinterpret_cast<LPARAM>(snapshot.get()))) snapshot.release();
        }
    });
    sampleCapsState(true);
    UINT_PTR capsTimer=SetTimer(nullptr,0,16,nullptr);
    UINT_PTR renewal=SetTimer(nullptr,0,1000,nullptr);
    if (!renewal || !capsTimer) {stop();}
    unsigned renewalFailures=0;
    ULONGLONG previousMaintenance=GetTickCount64();
    while (GetMessageW(&message,nullptr,0,0)>0) {
        if (message.message==WM_APP+22) {
            std::unique_ptr<ProcessSnapshot> snapshot(reinterpret_cast<ProcessSnapshot*>(message.lParam));
            applyProcesses(*snapshot);
        } else if (message.message==WM_TIMER && message.wParam==capsTimer) {
            HWND foreground=GetForegroundWindow();
            observeActivation(foreground,photoshopKeyScope(foreground),GetTickCount64());
            sampleCapsState();
        } else if (message.message==winRightMessage) {
            if (message.wParam==MOUSEEVENTF_RIGHTDOWN) {
                // Do not send a new click to a window that gained foreground
                // after the physical down. Ups still complete any sent down.
                if (!rightInjected && GetForegroundWindow()==reinterpret_cast<HWND>(message.lParam) && photoshopKeyScope()) {
                    rightInjected=injectRight(MOUSEEVENTF_RIGHTDOWN);
                    if (!rightInjected) emit(Error);
                }
            } else if (message.wParam==MOUSEEVENTF_RIGHTUP && rightInjected) {
                if (injectRight(MOUSEEVENTF_RIGHTUP)) rightInjected=false;
                else emit(Error);
            }
        } else if (message.message==WM_TIMER && message.wParam==renewal) {
            auto now=GetTickCount64(),started=microseconds();
            bool mouseHeld=false;for (bool held:mouseConsumed) mouseHeld=mouseHeld || held;
            bool attempted=renewalAllowed(now,lastInputTick,keys.physical[VK_CAPITAL],winRight.physical,mouseHeld);
            // Unhooking while Windows has pending hook calls can lose an
            // event. Keep the same hook throughout holds and rapid input.
            bool renewed=!attempted || renewHooks(keyHook,mouseHook);
            auto finished=microseconds();
            if (renewed) renewalFailures=0;
            else {emit(Error);if (++renewalFailures>=3) stop();}
            unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
            if (next!=tail.load(std::memory_order_acquire)) {
                HookEvent event{};event.action=HookHealth;event.scanUs=lastScanUs;event.renewUs=finished-started;event.attempted=attempted;
                event.gapMs=now-previousMaintenance;event.peakUs=callbackPeakUs.exchange(0,std::memory_order_relaxed);
                event.dropped=droppedEvents.load(std::memory_order_relaxed);event.blocked=renewed;
                queue[head.load(std::memory_order_relaxed)]=event;
                head.store(next,std::memory_order_release);SetEvent(available);
            } else droppedEvents.fetch_add(1,std::memory_order_relaxed);
            previousMaintenance=now;
            sampleCapsState(true);
        } else if (message.message==WM_APP) {
            std::unique_ptr<Config> next(reinterpret_cast<Config*>(message.lParam));
            if(!next->enabled || !next->remoteCompatibility)remoteClick.workspace=0;
            config=*next;
            diagnosticUntil=config.diagnostic?GetTickCount64()+35000:0;
            if (!IsWindowVisible(config.overlay)) dismissPending=false;
            emit(Configured);
        } else if (message.message==WM_APP+1) emit(Error);
        else { TranslateMessage(&message); DispatchMessageW(&message); }
    }
    if (renewal) KillTimer(nullptr,renewal);
    if (capsTimer) KillTimer(nullptr,capsTimer);
    closing.store(true);processScanner.join();
    while (PeekMessageW(&message,nullptr,WM_APP+22,WM_APP+22,PM_REMOVE)) {
        std::unique_ptr<ProcessSnapshot> snapshot(reinterpret_cast<ProcessSnapshot*>(message.lParam));
    }
    UnhookWindowsHookEx(keyHook); UnhookWindowsHookEx(mouseHook);
    if (rightInjected) injectRight(MOUSEEVENTF_RIGHTUP);
    for (auto& p:photoshopProcesses) if (p.handle) CloseHandle(p.handle);
    closing.store(true); SetEvent(available); writer.join();
    // Detached pipe/parent threads are terminated with this process.
    return 0;
}
