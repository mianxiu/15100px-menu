// Win32 hooks: no allocation, pipe I/O or application calls in callbacks.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <atomic>
#include <string>
#include <regex>
#include <thread>
#include <iostream>
#include <memory>
#include <stdexcept>

enum Action { None, Toggle, Hide, Select, Color, Top, Bottom, Context, Dismiss, Ready, Error, Configured, PanelClick, HoldBegin, HoldRelease, HoldCancel, HoldPin };
static const char* names[] = {"", "toggle", "hide", "select", "color", "moveToTop", "moveToBottom", "context", "dismiss", "hooks", "configuration", "settings", "panel.click", "hold_begin", "hold_release", "hold_cancel", "hold_pin"};
struct Binding { Action action=None; std::array<int,6> keys{}; int count=0; };
struct Config { bool enabled=false, textInput=false; HWND overlay=nullptr; std::array<Binding,6> bindings{}; };
static int alias(int key) {
    if (key==160 || key==161) return 16;
    if (key==162 || key==163) return 17;
    if (key==164 || key==165) return 18;
    return key;
}
struct KeyMachine {
    std::array<bool,256> physical{}, held{}, consumed{};
    int pending=-1; bool used=false;
    ULONGLONG pressTime=0,lastTap=0;
    bool pinPress=false;
    void seed(int raw) { physical[raw]=held[alias(raw)]=true; }
    bool modified() const { return held[16] || held[17] || held[18] || held[91] || held[92]; }
    bool event(int raw,bool down,bool scope,const Config& cfg,bool visible,Action& action,ULONGLONG now=0) {
        action=None; if (raw<0 || raw>=256) return false;
        if (!scope || (down && raw!=VK_CAPITAL)) lastTap=0;
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
                action=scope && !used?(pinPress?None:HoldRelease):HoldCancel;
                lastTap=key==VK_CAPITAL && scope && !used && !pinPress && now && now-pressTime<=220?now:0;
                pending=-1;pinPress=false;
            }
            return true;
        }
        // A physical press owns its whole repeat/release sequence. Never
        // reinterpret it after focus, modifiers or configuration changes.
        if (down && repeated) return consumed[key];
        if (!scope || !down) return down && consumed[key];
        const Binding* match=nullptr;
        bool tabPrefix=false;
        for (const auto& b:cfg.bindings) {
            if (cfg.textInput && b.action>=Select && b.action<=Bottom) continue;
            if (!b.count || (!visible && b.action==Hide)) continue;
            for (int i=0;i<b.count-1;++i) if (b.keys[i]==9) tabPrefix=true;
            if (b.keys[b.count-1]!=key) continue;
            bool matches=true;
            for (int i=0;i<b.count;++i) if (!held[b.keys[i]]) matches=false;
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
                pinPress=key==VK_CAPITAL && now && lastTap && now-lastTap<=300;
                pending=key;used=false;pressTime=now;lastTap=0;action=pinPress?HoldPin:HoldBegin;
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
        if (pending!=-1 && key!=pending) used=true;
        return consumed[key];
    }
};
static Config config;
static KeyMachine keys;
static HWND target=nullptr;
static bool dismissPending=false;
static std::array<bool,3> mouseConsumed{};
static std::atomic<bool> closing{false};
static DWORD hookThread;
static HANDLE available;
// Single producer (hook thread), single consumer (pipe writer).
struct HookEvent { Action action=None; HWND hwnd=nullptr,root=nullptr; };
static std::array<HookEvent,1024> queue{};
static std::atomic<unsigned> head{0}, tail{0};
static void emit(Action action,HWND hwnd=nullptr,HWND root=nullptr) {
    if (action==None) return;
    unsigned next=(head.load(std::memory_order_relaxed)+1)%queue.size();
    if (next==tail.load(std::memory_order_acquire)) return;
    queue[head.load(std::memory_order_relaxed)]={action,hwnd,root};
    head.store(next,std::memory_order_release); SetEvent(available);
}
static bool photoshop(HWND hwnd) {
    if (!hwnd || !IsWindow(hwnd) || IsIconic(hwnd) || !IsWindowVisible(hwnd)) return false;
    wchar_t name[64]{}; GetClassNameW(hwnd,name,64);
    return wcscmp(name,L"Photoshop")==0;
}
static bool menuWindow(HWND hwnd);
static bool scope() {
    if (!config.enabled) return false;
    HWND foreground=GetForegroundWindow();
    if (photoshop(foreground)) { target=foreground; return true; }
    // Hide and foreground restoration are separate operations. A just-hidden
    // menu may still own foreground; it remains part of this PS key scope.
    return menuWindow(foreground) && photoshop(target);
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
static LRESULT CALLBACK keyboard(int code,WPARAM message,LPARAM data) {
    if (code>=0) {
        const auto& input=*reinterpret_cast<const KBDLLHOOKSTRUCT*>(data);
        Action action;
        if (keys.event(input.vkCode,message==WM_KEYDOWN || message==WM_SYSKEYDOWN,
                       scope(),config,IsWindowVisible(config.overlay),action,GetTickCount64())) {
            emit(action); return 1;
        }
    }
    return CallNextHookEx(nullptr,code,message,data);
}
static LRESULT CALLBACK pointer(int code,WPARAM message,LPARAM data) {
    if (code>=0) {
        int index=message==WM_LBUTTONUP || message==WM_LBUTTONDOWN?0:
                  message==WM_RBUTTONUP || message==WM_RBUTTONDOWN?1:
                  message==WM_MBUTTONUP || message==WM_MBUTTONDOWN?2:-1;
        bool up=message==WM_LBUTTONUP || message==WM_RBUTTONUP || message==WM_MBUTTONUP;
        if (index>=0 && up && mouseConsumed[index]) {
            mouseConsumed[index]=false;
            return 1;
        }
        if (index>=0 && !up) {
            keys.lastTap=0;
            POINT point=reinterpret_cast<const MSLLHOOKSTRUCT*>(data)->pt;
            bool visible=IsWindowVisible(config.overlay);
            if (visible && index==1 && scope()) {
                emit(Dismiss);mouseConsumed[index]=true;return 1;
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
    next.overlay=reinterpret_cast<HWND>(std::stoull(field("hwnd","([0-9]+)")));
    for (int a=Toggle;a<=Bottom;++a) {
        auto list=field(names[a],"\\[([^\\]]+)\\]");
        Binding& b=next.bindings[a-1]; b.action=static_cast<Action>(a);
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
            if (action==PanelClick) line="{\"type\":\"panel.click\",\"hwnd\":"+std::to_string(reinterpret_cast<uintptr_t>(event.hwnd))+",\"root\":"+std::to_string(reinterpret_cast<uintptr_t>(event.root))+"}\n";
            else line=std::string("{\"type\":\"")+type+"\",\"action\":\""+names[action]+"\"}\n";
            DWORD written=0;
            if (!WriteFile(output,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written!=line.size()) { stop(); return; }
        }
        if (!closing.load()) WaitForSingleObject(available,250);
    }
}
static void check(bool value) { if (!value) throw std::runtime_error("Native hook self-test failed"); }
static int selfTest() {
    Config cfg; cfg.bindings[0]={Toggle,{20},1}; cfg.bindings[1]={Select,{20,65},2};
    KeyMachine state; Action action;
    KeyMachine taps;
    check(taps.event(20,true,true,cfg,false,action,1000) && action==HoldBegin);
    check(taps.event(20,false,true,cfg,false,action,1050) && action==HoldRelease);
    check(taps.event(20,true,true,cfg,false,action,1200) && action==HoldPin);
    check(taps.event(20,true,true,cfg,true,action,1220) && action==None);
    check(taps.event(20,false,true,cfg,true,action,1250) && action==None);
    check(taps.event(20,true,true,cfg,true,action,1600) && action==HoldBegin);
    check(taps.event(20,false,true,cfg,true,action,2000) && action==HoldRelease);
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
int main(int argc,char** argv) {
    // MSLLHOOKSTRUCT uses physical per-monitor coordinates. GetWindowRect and
    // WindowFromPoint must use the same coordinate space at 125/150/200% DPI.
    auto dpi=reinterpret_cast<BOOL(WINAPI*)(HANDLE)>(GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetProcessDpiAwarenessContext"));
    if (!dpi || !dpi(reinterpret_cast<HANDLE>(-4))) SetProcessDPIAware();
    if (argc==3 && std::string(argv[1])=="--inspect-window") {
        HWND hwnd=reinterpret_cast<HWND>(std::stoull(argv[2]));RECT rect{};
        if (!GetWindowRect(hwnd,&rect)) return 1;
        std::cout<<"["<<rect.left<<","<<rect.top<<","<<rect.right<<","<<rect.bottom<<"]\n";return 0;
    }
    if (argc==2 && std::string(argv[1])=="--self-test") return selfTest();
    DWORD parent=argc==3 && std::string(argv[1])=="--parent"?std::stoul(argv[2]):0;
    hookThread=GetCurrentThreadId(); MSG message; PeekMessageW(&message,nullptr,0,0,PM_NOREMOVE);
    available=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    if (!available) return 1;
    for (int vk:{160,161,162,163,164,165,91,92}) if (GetAsyncKeyState(vk)&0x8000) keys.seed(vk);
    SetThreadPriority(GetCurrentThread(),THREAD_PRIORITY_ABOVE_NORMAL);
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
    while (GetMessageW(&message,nullptr,0,0)>0) {
        if (message.message==WM_APP) {
            std::unique_ptr<Config> next(reinterpret_cast<Config*>(message.lParam)); config=*next;
            if (!IsWindowVisible(config.overlay)) dismissPending=false;
            emit(Configured);
        } else if (message.message==WM_APP+1) emit(Error);
        else { TranslateMessage(&message); DispatchMessageW(&message); }
    }
    UnhookWindowsHookEx(keyHook); UnhookWindowsHookEx(mouseHook);
    closing.store(true); SetEvent(available); writer.join();
    // Detached pipe/parent threads are terminated with this process.
    return 0;
}
