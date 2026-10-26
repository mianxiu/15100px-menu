#define INPUT_CONTEXT_SELF_TEST
#include "../native/InputContext.cpp"
#include <cstdio>
#include <stdexcept>

static void check(bool value,const char* message){if(!value){std::fprintf(stderr,"foreground=%p focus=%p owned=%p restore_failed=%d tsf=%d\n",GetForegroundWindow(),GetFocus(),disabledWindow,restoreFailed,tsf.keyboard!=nullptr);throw std::runtime_error(message);}}
int main() {
    try {
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
        auto attach=RegisterWindowMessageW(L"PhotoshopMenu.InputContext.Attach.v1");
        SendMessageW(fixture,attach,GetCurrentProcessId(),12345);
        check(control && GetPropW(fixture,controlProperty)==control,"in-thread handshake");
        check(GetPropW(control,ownerProperty)==reinterpret_cast<HANDLE>(ULONG_PTR(GetCurrentProcessId())),"service ownership binding");
        const auto command=[&](UINT op,HWND target=0){return SendMessageW(control,controlMessage,(12345<<8)|op,reinterpret_cast<LPARAM>(target?target:focus));};
        check(command(1)==5,"association read");
        SendMessageW(control,controlMessage,(54321<<8)|2,reinterpret_cast<LPARAM>(focus));check(associated(focus)==context,"foreign nonce changed context");
        check((command(2)&15)==3 && associated(focus)==nullptr,"disable association readback");
        check(GetKeyboardLayout(0)==layout,"keyboard profile changed");
        SendMessageW(focus,WM_LBUTTONDOWN,0,0);check(associated(focus)==context && !disabledWindow,"mouse input did not restore before editing");
        check((command(2)&15)==3,"second disable");SetFocus(edit);check(associated(focus)==context && !disabledWindow,"focus input restoration");
        SetFocus(focus);check((command(2)&15)==3,"watchdog disable");
        const auto end=GetTickCount64()+1900;
        while(GetTickCount64()<end){MSG msg{};while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}Sleep(10);}
        check(associated(focus)==context && !disabledWindow,"expired lease restoration");
        check((command(2)&15)==3,"explicit restore disable");check(command(3)==21 && associated(focus)==context,"explicit original-context restoration");
        check(GetKeyboardLayout(0)==layout,"restore changed keyboard profile");
        check((command(2)&15)==3,"external IMM reassociation disable");ImmAssociateContext(focus,context);
        check(command(1)&2,"read-only state unexpectedly restored ownership");
        check(command(4)==21 && associated(focus)==context,"external IMM reassociation survived lease validation");
        check((command(2)&15)==3,"profile notification disable");SendMessageW(focus,WM_INPUTLANGCHANGE,0,reinterpret_cast<LPARAM>(layout));
        check(command(1)==21 && associated(focus)==context && GetKeyboardLayout(0)==layout,"profile notification did not restore original context");
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
        check((command(3)&15)==5,"TSF explicit restore");keyboard->Release();keyboard=nullptr;
        check(SUCCEEDED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&keyboard)) && SUCCEEDED(keyboard->GetValue(&value)) && value.vt==prior.vt && (value.vt==VT_EMPTY || value.lVal==prior.lVal),"TSF original value restoration");
        VariantClear(&value);
        check((command(2)&35)==35,"TSF reset disable");
        check(SUCCEEDED(manager->SetFocus(nullptr)) && (command(4)&35)==35,"temporary absent TSF focus discarded original protection");
        check(SUCCEEDED(manager->SetFocus(document)),"TSF focus return");value.vt=VT_I4;value.lVal=0;
        check(SUCCEEDED(keyboard->SetValue(client,&value)),"external TSF reset");VariantClear(&value);
        check((command(1)&35)==3 && disabledWindow,"TSF drift read changed ownership or reported disabled");
        check((command(4)&51)==17 && !disabledWindow,"external TSF reset survived lease validation");
        check((command(2)&35)==35,"TSF renewed disable");
        ITfDocumentMgr* secondDocument=nullptr;ITfContext* secondText=nullptr;ITfCompartmentMgr* secondCompartments=nullptr;ITfCompartment* secondKeyboard=nullptr;
        check(SUCCEEDED(manager->CreateDocumentMgr(&secondDocument)) && SUCCEEDED(secondDocument->CreateContext(client,0,nullptr,&secondText,&cookie)) && SUCCEEDED(secondDocument->Push(secondText)) && SUCCEEDED(manager->SetFocus(secondDocument)),"second TSF context");
        associate(secondDocument);check(SUCCEEDED(manager->SetFocus(secondDocument)),"second associated focus");
        check(SUCCEEDED(secondText->QueryInterface(IID_ITfCompartmentMgr,reinterpret_cast<void**>(&secondCompartments))) && SUCCEEDED(secondCompartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&secondKeyboard)),"second keyboard compartment");
        VARIANT secondPrior{};check(SUCCEEDED(secondKeyboard->GetValue(&secondPrior)),"second TSF original");
        check((command(4)&51)==17 && !disabledWindow,"renewal accepted a different TSF context");
        check(SUCCEEDED(keyboard->GetValue(&value)) && value.vt==VT_I4 && value.lVal==0,"old TSF context not restored");VariantClear(&value);
        check(SUCCEEDED(secondKeyboard->GetValue(&value)) && value.vt==secondPrior.vt && (value.vt==VT_EMPTY || value.lVal==secondPrior.lVal),"unverified new TSF context modified");VariantClear(&value);
        check((command(2)&35)==35 && (command(3)&15)==5,"fresh TSF context cannot be independently protected and restored");
        VariantClear(&secondPrior);secondKeyboard->Release();secondCompartments->Release();associate(document);manager->SetFocus(document);secondDocument->Pop(TF_POPF_ALL);secondText->Release();secondDocument->Release();
        VariantClear(&prior);VariantClear(&value);keyboard->Release();compartments->Release();manager->SetFocus(nullptr);document->Pop(TF_POPF_ALL);text->Release();document->Release();manager->Deactivate();manager->Release();CoUninitialize();
        UnhookWindowsHookEx(hook);DestroyWindow(control);DestroyWindow(fixture);ImmDestroyContext(context);
        std::puts("PS-thread context: nonce, real association, focus/mouse/profile restore, IMM reassociation, TSF reset/context replacement, lease expiry, original context and unchanged HKL passed");return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 1;}
}
