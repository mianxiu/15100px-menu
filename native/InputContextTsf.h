// Only the focused PS edit context is changed; never the global keyboard compartment.
#include <msctf.h>
#include <oleauto.h>

struct InputContextTsf {
    ITfContext* context=nullptr;
    ITfThreadMgr* thread=nullptr;
    ITfCompartmentMgr* compartments=nullptr;
    ITfCompartment* keyboard=nullptr;
    VARIANT original{};
    TfClientId client=0;
    bool activated=false,changed=false;
    static ITfContext* current(ITfThreadMgr** manager=nullptr) {
        const auto library=GetModuleHandleW(L"msctf.dll");
        HRESULT(WINAPI*get)(ITfThreadMgr**)=nullptr;
        const auto address=library?GetProcAddress(library,"TF_GetThreadMgr"):nullptr;
        static_assert(sizeof(get)==sizeof(address));memcpy(&get,&address,sizeof(get));
        ITfThreadMgr* thread=nullptr;ITfDocumentMgr* document=nullptr;ITfContext* context=nullptr;
        if(get && SUCCEEDED(get(&thread)) && thread) {
            if(SUCCEEDED(thread->GetFocus(&document)) && document){document->GetTop(&context);document->Release();}
            if(manager)*manager=thread;else thread->Release();
        }
        return context;
    }
    static bool available(){const auto context=current();if(context)context->Release();return context!=nullptr;}
    bool disabled()const {
        if(!keyboard)return true;
        VARIANT value{};const bool ok=SUCCEEDED(keyboard->GetValue(&value)) && value.vt==VT_I4 && value.lVal==1;VariantClear(&value);return ok;
    }
    bool currentDisabled()const {
        auto focused=current();
        if(!context){if(focused)focused->Release();return focused==nullptr;}
        IUnknown *expected=nullptr,*actual=nullptr;
        // Detaching IMM can temporarily remove TSF focus; keep the verified original disabled until focus returns or changes.
        const bool same=!focused || (SUCCEEDED(context->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&expected))) &&
            SUCCEEDED(focused->QueryInterface(IID_IUnknown,reinterpret_cast<void**>(&actual))) && expected==actual);
        if(expected)expected->Release();
        if(actual)actual->Release();
        if(focused)focused->Release();
        return same && disabled();
    }
    bool start() {
        context=current(&thread);
        if(!context){if(thread){thread->Release();thread=nullptr;}return true;}
        const auto queried=context->QueryInterface(IID_ITfCompartmentMgr,reinterpret_cast<void**>(&compartments));
        if(FAILED(queried) || FAILED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&keyboard)) ||
           FAILED(keyboard->GetValue(&original)) || (original.vt!=VT_EMPTY && original.vt!=VT_I4) || FAILED(thread->Activate(&client)))return false;
        activated=true;VARIANT value{};value.vt=VT_I4;value.lVal=1;changed=true;
        return SUCCEEDED(keyboard->SetValue(client,&value)) && disabled();
    }
    bool restore() {
        if(changed) {
            VARIANT value{};const auto read=keyboard->GetValue(&value);
            if(FAILED(read)){VariantClear(&value);return false;}
            const bool ours=value.vt==VT_I4 && value.lVal==1;VariantClear(&value);
            if(ours) {
                const auto result=original.vt==VT_EMPTY?compartments->ClearCompartment(client,GUID_COMPARTMENT_KEYBOARD_DISABLED):keyboard->SetValue(client,&original);
                if(FAILED(result))return false;
                ITfCompartment* check=nullptr;
                if(FAILED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_DISABLED,&check)))return false;
                const auto readback=check->GetValue(&value);check->Release();
                const bool same=SUCCEEDED(readback) && value.vt==original.vt && (value.vt==VT_EMPTY || value.lVal==original.lVal);VariantClear(&value);
                if(!same)return false;
            }
            changed=false;
        }
        if(activated){if(FAILED(thread->Deactivate()))return false;activated=false;}
        if(keyboard)keyboard->Release();
        if(compartments)compartments->Release();
        if(thread)thread->Release();
        if(context)context->Release();
        keyboard=nullptr;compartments=nullptr;thread=nullptr;context=nullptr;VariantClear(&original);client=0;return true;
    }
};
