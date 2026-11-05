// TSF text service that hosts the verified in-process IME context helper.
//
// The service is registered in HKLM (see tools/manage-input-service.py); msctf
// loads it into every TSF process, but it only acts inside Photoshop.exe. In
// Photoshop it loads InputContext.dll from its own directory and calls
// InputContextAttach, replacing the previous cross-process hook injection.
//
// Safety: no input is intercepted, no text or document data is read, every
// failure only retries later, and non-Photoshop processes return immediately.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msctf.h>
#include <string>

static const CLSID kClsid = {0xa4d1c7f2, 0x5e3b, 0x4c8d, {0x9f, 0x01, 0x6b, 0x2e, 0x8d, 0x4a, 0x7c, 0x15}};
static const wchar_t* kOwnerKey = L"Software\\PhotoshopMenu\\InputService";
static const wchar_t* kWindowClass = L"PhotoshopMenu.InputService.v1";

static HMODULE g_module = nullptr;
static HWND g_window = nullptr;
static HMODULE g_context = nullptr;
typedef BOOL(WINAPI* AttachFn)(HWND, DWORD, ULONG_PTR);
typedef BOOL(WINAPI* DetachFn)();
typedef DWORD(WINAPI* OwnerFn)();
static AttachFn g_attach = nullptr;
static DetachFn g_detach = nullptr;
static OwnerFn g_owner = nullptr;

static bool namedProcess(HANDLE process, const wchar_t* expected) {
    wchar_t path[32768]{};
    DWORD length = 32768;
    if (!QueryFullProcessImageNameW(process, 0, path, &length)) return false;
    const auto slash = wcsrchr(path, L'\\');
    return _wcsicmp(slash ? slash + 1 : path, expected) == 0;
}

static DWORD ownerPid() {
    DWORD value = 0, size = sizeof(value), type = 0;
    HKEY key = nullptr;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, kOwnerKey, 0, KEY_QUERY_VALUE, &key) != ERROR_SUCCESS) return 0;
    const auto read = RegQueryValueExW(key, L"OwnerPid", nullptr, &type, reinterpret_cast<BYTE*>(&value), &size);
    RegCloseKey(key);
    return read == ERROR_SUCCESS && type == REG_DWORD ? value : 0;
}

static HWND photoshopRoot() {
    struct Search { DWORD pid; HWND found; } search{GetCurrentProcessId(), nullptr};
    EnumWindows([](HWND window, LPARAM data) -> BOOL {
        auto& search = *reinterpret_cast<Search*>(data);
        DWORD pid = 0;
        GetWindowThreadProcessId(window, &pid);
        if (pid != search.pid || !IsWindowVisible(window)) return TRUE;
        wchar_t name[64]{};
        GetClassNameW(window, name, 64);
        if (wcscmp(name, L"Photoshop") != 0) return TRUE;
        search.found = window;
        return FALSE;
    }, reinterpret_cast<LPARAM>(&search));
    return search.found;
}

static bool loadContext() {
    if (g_attach && g_detach && g_owner) return true;
    if (g_context) return false;
    wchar_t path[MAX_PATH]{};
    if (!GetModuleFileNameW(g_module, path, MAX_PATH)) return false;
    std::wstring directory(path);
    const auto slash = directory.find_last_of(L"\\/");
    if (slash == std::wstring::npos) return false;
    directory = directory.substr(0, slash + 1) + L"InputContext.dll";
    g_context = LoadLibraryW(directory.c_str());
    if (!g_context) return false;
    g_attach = reinterpret_cast<AttachFn>(GetProcAddress(g_context, "InputContextAttach"));
    g_detach = reinterpret_cast<DetachFn>(GetProcAddress(g_context, "InputContextDetach"));
    g_owner = reinterpret_cast<OwnerFn>(GetProcAddress(g_context, "InputContextOwner"));
    return g_attach && g_detach && g_owner;
}

static void reconcile() {
    const auto root = photoshopRoot();
    if (!root) return;
    const auto owner = ownerPid();
    if (!owner) return;
    if (!loadContext()) return;
    if (g_owner() == owner) return;
    // Another transport already owns the context; never create a second policy.
    if (GetPropW(root, L"PhotoshopMenu.InputContext.Window.v1")) return;
    if (g_owner()) g_detach();
    g_attach(root, owner, static_cast<ULONG_PTR>(GetTickCount64()) ^ reinterpret_cast<ULONG_PTR>(root));
}

static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wParam, LPARAM lParam) {
    if (message == WM_TIMER && wParam == 1) {
        reconcile();
        return 0;
    }
    if (message == WM_DESTROY) return 0;
    return DefWindowProcW(window, message, wParam, lParam);
}

class Service : public ITfTextInputProcessor {
    LONG references = 1;

public:
    virtual ~Service() = default;
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (id == IID_IUnknown || id == IID_ITfTextInputProcessor) {
            *out = static_cast<ITfTextInputProcessor*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override {
        const auto left = InterlockedDecrement(&references);
        if (!left) delete this;
        return left;
    }
    HRESULT STDMETHODCALLTYPE Activate(ITfThreadMgr*, TfClientId) override {
        // Loaded into every TSF process: only Photoshop is touched.
        if (!namedProcess(GetCurrentProcess(), L"Photoshop.exe")) return S_OK;
        if (!g_window) {
            WNDCLASSW wc{};
            wc.lpfnWndProc = procedure;
            wc.hInstance = g_module;
            wc.lpszClassName = kWindowClass;
            RegisterClassW(&wc);
            g_window = CreateWindowExW(0, kWindowClass, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr,
                                       g_module, nullptr);
            if (g_window) SetTimer(g_window, 1, 1500, nullptr);
        }
        reconcile();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Deactivate() override {
        if (g_window) {
            KillTimer(g_window, 1);
            DestroyWindow(g_window);
            g_window = nullptr;
        }
        if (g_context && g_detach) g_detach();
        return S_OK;
    }
};

class Factory : public IClassFactory {
    LONG references = 1;

public:
    virtual ~Factory() = default;
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (id == IID_IUnknown || id == IID_IClassFactory) {
            *out = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override {
        const auto left = InterlockedDecrement(&references);
        if (!left) delete this;
        return left;
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID id, void** out) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* service = new Service();
        if (!service) return E_OUTOFMEMORY;
        const HRESULT result = service->QueryInterface(id, out);
        service->Release();
        return result;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL) override { return S_OK; }
};

extern "C" __declspec(dllexport) HRESULT STDMETHODCALLTYPE DllGetClassObject(REFCLSID id, REFIID interfaceId, void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (!IsEqualCLSID(id, kClsid)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new Factory();
    if (!factory) return E_OUTOFMEMORY;
    const HRESULT result = factory->QueryInterface(interfaceId, out);
    factory->Release();
    return result;
}

extern "C" __declspec(dllexport) HRESULT STDMETHODCALLTYPE DllCanUnloadNow() { return S_FALSE; }

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = instance;
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
