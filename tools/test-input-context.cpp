#define INPUT_CONTEXT_SELF_TEST
#include <cstdio>
#include "../native/InputContext.cpp"
#include <cstdio>
#include <stdexcept>
#include <string>

static HWND childEdit=nullptr;
static HIMC childContext=nullptr;
static PROCESS_INFORMATION fixtureChild{};
static void closeChild() {
    if(!fixtureChild.hProcess)return;
    if(WaitForSingleObject(fixtureChild.hProcess,0)==WAIT_TIMEOUT) {
        EnumWindows([](HWND window,LPARAM data)->BOOL{
            DWORD pid=0;GetWindowThreadProcessId(window,&pid);
            wchar_t name[64]{};GetClassNameW(window,name,64);
            if(pid==DWORD(data) && wcscmp(name,L"PhotoshopMenuImGui")==0)SendMessageW(window,WM_CLOSE,0,0);
            return TRUE;
        },LPARAM(fixtureChild.dwProcessId));
        if(WaitForSingleObject(fixtureChild.hProcess,5000)!=WAIT_OBJECT_0)std::fprintf(stderr,"Owned menu fixture did not exit normally\n");
    }
    CloseHandle(fixtureChild.hThread);CloseHandle(fixtureChild.hProcess);fixtureChild={};
}
static LRESULT CALLBACK menuProcedure(HWND window,UINT message,WPARAM wParam,LPARAM lParam) {
    if(message==WM_APP+53)return associated(childEdit)==childContext && ImmGetOpenStatus(childContext);
    if(message==WM_APP+54){SetFocus(childEdit);return 1;}
    if(message==WM_APP+55){
        const auto target=reinterpret_cast<HWND>(wParam);DWORD pid=0;GetWindowThreadProcessId(target,&pid);
        AllowSetForegroundWindow(pid);return SetForegroundWindow(target);
    }
    if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
    return DefWindowProcW(window,message,wParam,lParam);
}
static int childMenu() {
    WNDCLASSW wc{};wc.lpfnWndProc=menuProcedure;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"PhotoshopMenuImGui";
    if(!RegisterClassW(&wc))return 2;
    auto window=CreateWindowW(wc.lpszClassName,L"Owned input fixture",WS_OVERLAPPEDWINDOW,320,0,240,120,nullptr,nullptr,wc.hInstance,nullptr);
    childEdit=CreateWindowW(L"EDIT",L"",WS_CHILD|WS_VISIBLE,0,0,120,24,window,nullptr,wc.hInstance,nullptr);
    childContext=ImmCreateContext();if(!window || !childEdit || !childContext)return 3;
    ImmAssociateContext(childEdit,childContext);ImmSetOpenStatus(childContext,TRUE);ShowWindow(window,SW_SHOWNOACTIVATE);
    MSG message{};while(GetMessageW(&message,nullptr,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
    ImmDestroyContext(childContext);return 0;
}

static void check(bool value,const char* message){if(!value){wchar_t name[128]{};GetClassNameW(GetForegroundWindow(),name,128);std::fprintf(stderr,"root=%p foreground=%p class=%ls focus=%p owned=%p restore_failed=%d tsf=%d\n",root,GetForegroundWindow(),name,GetFocus(),disabledWindow,restoreFailed,tsf.keyboard!=nullptr);throw std::runtime_error(message);}}
static void settledForeground(HWND window) {
    const auto end=GetTickCount64()+500;
    while(GetForegroundWindow()!=window && GetTickCount64()<end) {
        MSG message{};while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessageW(&message);}Sleep(1);
    }
    check(GetForegroundWindow()==window,"fixture foreground did not settle");
}
int main(int argc,char** argv) {
    if(argc==2 && strcmp(argv[1],"--owned-menu")==0)return childMenu();
    try {
        bool low=false,queuedOnly=false;
        for(int i=1;i<argc;++i) {
            if(strcmp(argv[i],"--low")==0)low=true;
            else if(strcmp(argv[i],"--queued-only")==0)queuedOnly=true;
            else throw std::runtime_error("Unknown fixture argument");
        }
        if(low){DWORD_PTR affinity=0,system=0;check(GetProcessAffinityMask(GetCurrentProcess(),&affinity,&system)!=0,"fixture affinity");int count=0;for(auto bits=affinity;bits;bits&=bits-1)count++;check(count==2 && GetPriorityClass(GetCurrentProcess())==BELOW_NORMAL_PRIORITY_CLASS,"fixture low CPU not applied");}
        module=GetModuleHandleW(nullptr);
        WNDCLASSW wc{};wc.lpfnWndProc=DefWindowProcW;wc.hInstance=module;wc.lpszClassName=L"Photoshop";
        check(RegisterClassW(&wc)!=0,"fixture class");
        auto fixture=CreateWindowW(L"Photoshop",L"Owned input context test",WS_OVERLAPPEDWINDOW,0,0,300,180,nullptr,nullptr,module,nullptr);
        auto focus=CreateWindowW(L"STATIC",L"",WS_CHILD|WS_VISIBLE,0,0,40,40,fixture,nullptr,module,nullptr);
        auto edit=CreateWindowW(L"EDIT",L"",WS_CHILD|WS_VISIBLE,50,0,100,24,fixture,nullptr,module,nullptr);
        auto context=ImmCreateContext();check(context!=nullptr,"IME context");ImmAssociateContext(focus,context);
        ShowWindow(fixture,SW_SHOWNORMAL);SetForegroundWindow(fixture);SetFocus(focus);
        check(GetForegroundWindow()==fixture,"fixture foreground denied");
        const auto layout=GetKeyboardLayout(0);
        auto hook=SetWindowsHookExW(WH_CALLWNDPROC,InputContextHook,nullptr,GetCurrentThreadId());check(hook!=nullptr,"thread hook");
        auto queuedHook=SetWindowsHookExW(WH_GETMESSAGE,InputContextQueueHook,nullptr,GetCurrentThreadId());check(queuedHook!=nullptr,"queued input hook");
        auto attach=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Attach.v1");
        SendMessageW(fixture,attach,GetCurrentProcessId(),12345);
        check(control && GetPropW(fixture,controlProperty)==control,"in-thread handshake");
        check(GetPropW(control,ownerProperty)==reinterpret_cast<HANDLE>(ULONG_PTR(GetCurrentProcessId())),"service ownership binding");
        const auto command=[&](UINT op,HWND target=0){return SendMessageW(control,controlMessage,(12345<<8)|op,reinterpret_cast<LPARAM>(target?target:focus));};
        const auto dispatchContextEvents=[&](){MSG event{};bool seen=false;while(PeekMessageW(&event,control,contextChangedMessage,contextChangedMessage,PM_REMOVE)){DispatchMessageW(&event);seen=true;}check(seen,"TSF change event was not posted");};
        check(command(1)==5,"association read");
        SendMessageW(control,controlMessage,(54321<<8)|2,reinterpret_cast<LPARAM>(focus));check(associated(focus)==context,"foreign nonce changed context");
        check((command(2)&15)==3 && associated(focus)==nullptr,"disable association readback");
        check(GetKeyboardLayout(0)==layout,"keyboard profile changed");
        SendMessageW(focus,WM_KEYDOWN,'T',0);check(disabledWindow==focus && associated(focus)==nullptr,"idle type tool released protection before editing");
        SendMessageW(focus,WM_LBUTTONDOWN,0,0);check(associated(focus)==context && !disabledWindow,"mouse input did not restore before editing");
        check((command(2)&15)==3,"queued input disable");
        check(PostMessageW(focus,WM_LBUTTONDOWN,0,0)!=0,"queued mouse message");
        MSG queued{};while(PeekMessageW(&queued,nullptr,0,0,PM_REMOVE)){TranslateMessage(&queued);DispatchMessageW(&queued);}
        check(associated(focus)==context && !disabledWindow,"queued mouse input did not restore before editing");
        check((command(2)&15)==3,"queued keyboard disable");
        PostMessageW(focus,WM_KEYDOWN,'T',0);
        check(PeekMessageW(&queued,focus,WM_KEYDOWN,WM_KEYDOWN,PM_REMOVE) && disabledWindow==focus,"queued idle T released protection");
        DispatchMessageW(&queued);
        PostMessageW(focus,WM_KEYDOWN,VK_RETURN,0);
        check(PeekMessageW(&queued,focus,WM_KEYDOWN,WM_KEYDOWN,PM_NOREMOVE) && disabledWindow==focus,"peek without removal changed input context");
        check(PeekMessageW(&queued,focus,WM_KEYDOWN,WM_KEYDOWN,PM_REMOVE) && !disabledWindow && associated(focus)==context,"queued Enter did not restore before translation");
        TranslateMessage(&queued);DispatchMessageW(&queued);
        if(queuedOnly) {
            check(GetForegroundWindow()==fixture,"queued fixture foreground changed");
            UnhookWindowsHookEx(queuedHook);UnhookWindowsHookEx(hook);DestroyWindow(control);DestroyWindow(fixture);ImmDestroyContext(context);
            std::puts("Queued PS-thread input passed: mouse restoration, idle T retained, Enter restored before TranslateMessage, PM_NOREMOVE unchanged, original IMM and HKL preserved");return 0;
        }
        check((command(2)&15)==3,"second disable");SetFocus(edit);check(associated(focus)==context && !disabledWindow,"focus input restoration");
        SetFocus(focus);check((command(2)&15)==3,"watchdog disable");
        const auto end=GetTickCount64()+1900;
        while(GetTickCount64()<end){MSG msg{};while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}Sleep(10);}
        check(GetForegroundWindow()==fixture && GetFocus()==focus,"foreground changed during lease-expiry fixture");
        check(associated(focus)==context && !disabledWindow,"expired lease restoration");
        check((command(2)&15)==3,"explicit restore disable");check(command(3)==21 && associated(focus)==context,"explicit original-context restoration");
        check(GetKeyboardLayout(0)==layout,"restore changed keyboard profile");
        check((command(2)&15)==3,"external IMM reassociation disable");ImmAssociateContext(focus,context);
        check(command(1)&2,"read-only state unexpectedly restored ownership");
        check(command(4)==21 && associated(focus)==context,"external IMM reassociation survived lease validation");
        check((command(2)&15)==3,"profile notification disable");SendMessageW(focus,WM_INPUTLANGCHANGE,0,reinterpret_cast<LPARAM>(layout));
        check(command(1)==21 && associated(focus)==context && GetKeyboardLayout(0)==layout,"profile notification did not restore original context");
        wchar_t ownPath[32768]{};check(GetModuleFileNameW(nullptr,ownPath,32768)!=0,"fixture path");
        std::wstring folder=ownPath;folder=folder.substr(0,folder.find_last_of(L"\\"))+L"\\input-context-menu-fixture";
        check(CreateDirectoryW(folder.c_str(),nullptr) || GetLastError()==ERROR_ALREADY_EXISTS,"fixture directory");
        std::wstring childPath=folder+L"\\MenuHost.exe";check(CopyFileW(ownPath,childPath.c_str(),FALSE)!=0,"menu fixture copy");
        std::wstring childCommand=L"\""+childPath+L"\" --owned-menu";STARTUPINFOW startup{};startup.cb=sizeof(startup);auto& child=fixtureChild;
        check(CreateProcessW(childPath.c_str(),childCommand.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,folder.c_str(),&startup,&child)!=0,"menu fixture process");
        WaitForInputIdle(child.hProcess,3000);HWND menu=nullptr;
        const auto findMenu=[](HWND window,LPARAM data)->BOOL {
            auto args=reinterpret_cast<std::pair<DWORD,HWND*>*>(data);DWORD pid=0;GetWindowThreadProcessId(window,&pid);
            wchar_t name[64]{};GetClassNameW(window,name,64);
            if(pid==args->first && wcscmp(name,L"PhotoshopMenuImGui")==0){*args->second=window;return FALSE;}return TRUE;
        };
        std::pair<DWORD,HWND*> search{child.dwProcessId,&menu};const auto readyEnd=GetTickCount64()+3000;
        do {EnumWindows(findMenu,reinterpret_cast<LPARAM>(&search));if(menu)break;Sleep(10);}while(GetTickCount64()<readyEnd && WaitForSingleObject(child.hProcess,0)==WAIT_TIMEOUT);
        check(menu!=nullptr,"child menu window readiness");check(ownMenu(menu),"trusted child menu identity");
        SetForegroundWindow(fixture);SetFocus(focus);check((command(2)&15)==3,"menu origin disable");
        testTrace=true;
        for(int i=0;i<50;++i) {
            SetForegroundWindow(menu);settledForeground(menu);SendMessageW(menu,WM_APP+54,0,0);
            check((command(1)&130)==130 && associated(focus)==nullptr && SendMessageW(menu,WM_APP+53,0,0),"own menu released PS protection or changed menu IME");
            command(4);SendMessageW(control,WM_TIMER,1,0);check(disabledWindow==focus,"own menu renewal lost lease");
            SendMessageW(menu,WM_APP+55,reinterpret_cast<WPARAM>(fixture),0);settledForeground(fixture);SetFocus(focus);
            check((command(1)&15)==3 && associated(focus)==nullptr,"PS return exposed an IME gap");
        }
        testTrace=false;
        SetForegroundWindow(menu);SendMessageW(menu,WM_APP+54,0,0);deadline=GetTickCount64()-1;SendMessageW(control,WM_TIMER,1,0);
        check(!disabledWindow && associated(focus)==context,"own menu bypassed lease expiry");
        SendMessageW(menu,WM_APP+55,reinterpret_cast<WPARAM>(fixture),0);settledForeground(fixture);SetFocus(focus);check((command(2)&15)==3,"foreign application fixture disable");
        auto foreign=CreateWindowW(L"STATIC",L"Foreign window",WS_OVERLAPPEDWINDOW,580,0,120,100,nullptr,nullptr,module,nullptr);
        ShowWindow(foreign,SW_SHOW);SetForegroundWindow(foreign);SetFocus(foreign);SendMessageW(control,WM_TIMER,1,0);
        check(!disabledWindow && associated(focus)==context && !ownMenu(foreign),"foreign application retained PS protection");
        DestroyWindow(foreign);SendMessageW(menu,WM_CLOSE,0,0);check(WaitForSingleObject(child.hProcess,5000)==WAIT_OBJECT_0,"menu fixture normal exit");
        closeChild();SetForegroundWindow(fixture);SetFocus(focus);
        check(SUCCEEDED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)),"TSF fixture COM");
        ITfThreadMgr* manager=nullptr;ITfDocumentMgr* document=nullptr;ITfContext* text=nullptr;ITfCompartmentMgr* compartments=nullptr;ITfCompartment* keyboard=nullptr;TfClientId client=0;TfEditCookie cookie=0;
        check(SUCCEEDED(CoCreateInstance(CLSID_TF_ThreadMgr,nullptr,CLSCTX_INPROC_SERVER,IID_ITfThreadMgr,reinterpret_cast<void**>(&manager))),"TSF manager");
        check(SUCCEEDED(manager->Activate(&client)),"TSF client");
        const auto associate=[&](ITfDocumentMgr* value){ITfDocumentMgr* previous=nullptr;const auto result=manager->AssociateFocus(focus,value,&previous);if(previous)previous->Release();check(SUCCEEDED(result),"TSF HWND association");};
        check(SUCCEEDED(manager->CreateDocumentMgr(&document)) && SUCCEEDED(document->CreateContext(client,0,nullptr,&text,&cookie)) && SUCCEEDED(document->Push(text)) && SUCCEEDED(manager->SetFocus(document)),"TSF focused context");
        associate(document);check(SUCCEEDED(manager->SetFocus(document)),"TSF associated focus");
        check(SUCCEEDED(text->QueryInterface(IID_ITfCompartmentMgr,reinterpret_cast<void**>(&compartments))) && SUCCEEDED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&keyboard)),"TSF keyboard compartment");
        VARIANT prior{},value{};check(SUCCEEDED(keyboard->GetValue(&prior)),"TSF prior value");
        check((command(2)&35)==35 && SUCCEEDED(keyboard->GetValue(&value)) && value.vt==VT_I4 && value.lVal==1,"TSF actual disabled readback");VariantClear(&value);
        check((command(1)&64) && tsf.watching(),"TSF subscriptions not active");
        check((command(3)&15)==5,"TSF explicit restore");keyboard->Release();keyboard=nullptr;
        check(SUCCEEDED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&keyboard)) && SUCCEEDED(keyboard->GetValue(&value)) && value.vt==prior.vt && (value.vt==VT_EMPTY || value.lVal==prior.lVal),"TSF original value restoration");
        VariantClear(&value);
        check((command(2)&35)==35,"TSF reset disable");
        check(SUCCEEDED(manager->SetFocus(nullptr)) && (command(4)&35)==35,"temporary absent TSF focus discarded original protection");
        check(SUCCEEDED(manager->SetFocus(document)),"TSF focus return");value.vt=VT_I4;value.lVal=0;
        const auto resetRevision=GetPropW(control,revisionProperty);
        check(SUCCEEDED(keyboard->SetValue(client,&value)),"external TSF reset");VariantClear(&value);
        check((command(1)&35)==3 && disabledWindow,"TSF drift read changed ownership or reported disabled");
        dispatchContextEvents();
        check((command(1)&51)==17 && !disabledWindow,"external TSF reset survived notification handling");
        check(GetPropW(control,revisionProperty)!=resetRevision && !tsf.watching() && tsf.references==1,"TSF reset did not invalidate evidence or release subscriptions");
        check((command(2)&35)==35,"TSF renewed disable");
        ITfDocumentMgr* secondDocument=nullptr;ITfContext* secondText=nullptr;ITfCompartmentMgr* secondCompartments=nullptr;ITfCompartment* secondKeyboard=nullptr;
        check(SUCCEEDED(manager->CreateDocumentMgr(&secondDocument)) && SUCCEEDED(secondDocument->CreateContext(client,0,nullptr,&secondText,&cookie)) && SUCCEEDED(secondDocument->Push(secondText)) && SUCCEEDED(manager->SetFocus(secondDocument)),"second TSF context");
        associate(secondDocument);check(SUCCEEDED(manager->SetFocus(secondDocument)),"second associated focus");
        check(SUCCEEDED(secondText->QueryInterface(IID_ITfCompartmentMgr,reinterpret_cast<void**>(&secondCompartments))) && SUCCEEDED(secondCompartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&secondKeyboard)),"second keyboard compartment");
        VARIANT secondPrior{};check(SUCCEEDED(secondKeyboard->GetValue(&secondPrior)),"second TSF original");
        dispatchContextEvents();
        check((command(1)&51)==17 && !disabledWindow,"notification accepted a different TSF context");
        check(SUCCEEDED(keyboard->GetValue(&value)) && value.vt==VT_I4 && value.lVal==0,"old TSF context not restored");VariantClear(&value);
        check(SUCCEEDED(secondKeyboard->GetValue(&value)) && value.vt==secondPrior.vt && (value.vt==VT_EMPTY || value.lVal==secondPrior.lVal),"unverified new TSF context modified");VariantClear(&value);
        check((command(2)&35)==35 && (command(3)&15)==5,"fresh TSF context cannot be independently protected and restored");
        for(int i=0;i<20;i++)check((command(2)&99)==99 && (command(3)&15)==5 && tsf.references==1 && !tsf.watching(),"repeated lease leaked subscriptions or failed readback");
        VariantClear(&secondPrior);secondKeyboard->Release();secondCompartments->Release();associate(document);manager->SetFocus(document);secondDocument->Pop(TF_POPF_ALL);secondText->Release();secondDocument->Release();
        VariantClear(&prior);VariantClear(&value);keyboard->Release();compartments->Release();manager->SetFocus(nullptr);document->Pop(TF_POPF_ALL);text->Release();document->Release();manager->Deactivate();manager->Release();CoUninitialize();
        UnhookWindowsHookEx(queuedHook);UnhookWindowsHookEx(hook);DestroyWindow(control);DestroyWindow(fixture);ImmDestroyContext(context);
        std::puts("PS-thread context: nonce, real association, focus/mouse/profile restore, IMM reassociation, TSF event reset/context replacement without timer or renew, 50 cross-process menu returns with independent menu IME, 20 subscription lifecycles, lease expiry, original context and unchanged HKL passed");return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());closeChild();return 1;}
}
