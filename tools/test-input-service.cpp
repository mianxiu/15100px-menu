// End-to-end test host for the TSF transport, without Photoshop and without
// administrator rights.
//
//  --owner : copied as PhotoshopMenu.exe, stays alive as the attach owner.
//  --host  : copied as Photoshop.exe, creates a "Photoshop"-class root window,
//            activates the TSF thread manager, instantiates InputService.dll
//            through its COM class and checks that InputContext attached.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msctf.h>
#include <cstdio>
#include <string>

static const CLSID kService = {0xa4d1c7f2, 0x5e3b, 0x4c8d, {0x9f, 0x01, 0x6b, 0x2e, 0x8d, 0x4a, 0x7c, 0x15}};
static const wchar_t* kControlProperty = L"PhotoshopMenu.InputContext.Window.v1";
static const wchar_t* kControlClass = L"PhotoshopMenu.InputContext.v1";

static LRESULT CALLBACK empty(HWND window, UINT message, WPARAM wParam, LPARAM lParam) {
    return DefWindowProcW(window, message, wParam, lParam);
}

int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "";
    if (mode == "--owner") { Sleep(8000); return 0; }
    if (mode != "--host") { printf("usage: --owner | --host\n"); return 2; }

    WNDCLASSW wc{};
    wc.lpfnWndProc = empty;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"Photoshop";
    RegisterClassW(&wc);
    HWND root = CreateWindowExW(WS_EX_TOOLWINDOW, L"Photoshop", L"transport test", WS_POPUP,
                                -3000, -3000, 200, 120, nullptr, nullptr, wc.hInstance, nullptr);
    if (!root) { printf("root window failed %lu\n", GetLastError()); return 1; }
    ShowWindow(root, SW_SHOWNA);

    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    ITfThreadMgr* manager = nullptr;
    if (FAILED(CoCreateInstance(CLSID_TF_ThreadMgr, nullptr, CLSCTX_INPROC_SERVER, IID_ITfThreadMgr,
                                reinterpret_cast<void**>(&manager))) || !manager) {
        printf("thread manager failed\n");
        return 1;
    }
    TfClientId client = 0;
    printf("thread manager activate hr=%08lx\n", static_cast<unsigned long>(manager->Activate(&client)));

    ITfTextInputProcessor* service = nullptr;
    const HRESULT created = CoCreateInstance(kService, nullptr, CLSCTX_INPROC_SERVER,
                                             IID_ITfTextInputProcessor, reinterpret_cast<void**>(&service));
    printf("service CoCreateInstance hr=%08lx\n", static_cast<unsigned long>(created));
    bool attached = false;
    if (service) {
        printf("service Activate hr=%08lx\n", static_cast<unsigned long>(service->Activate(manager, client)));
        for (int attempt = 0; attempt < 20 && !attached; ++attempt) {
            Sleep(250);
            HWND control = reinterpret_cast<HWND>(GetPropW(root, kControlProperty));
            if (!control || !IsWindow(control)) continue;
            wchar_t name[64]{};
            GetClassNameW(control, name, 64);
            attached = wcscmp(name, kControlClass) == 0;
            wprintf(L"control window=%p class=%ls attached=%d\n", static_cast<void*>(control), name, attached ? 1 : 0);
        }
        service->Deactivate();
        service->Release();
    }
    manager->Deactivate();
    manager->Release();
    CoUninitialize();
    DestroyWindow(root);
    printf("RESULT attached=%d\n", attached ? 1 : 0);
    return attached ? 0 : 1;
}
