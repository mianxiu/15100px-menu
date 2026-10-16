// Exercises the production pipe writer; never installs hooks or sends input.
#define main production_hotkey_main
#include "../native/HotkeyHost.cpp"
#undef main
int main() {
    HANDLE read=nullptr,write=nullptr;auto original=GetStdHandle(STD_OUTPUT_HANDLE);
    if(!CreatePipe(&read,&write,nullptr,65536))return 1;
    SetStdHandle(STD_OUTPUT_HANDLE,write);available=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    std::thread writer(writeActions);
    std::vector<Action> expected;
    for(Action command:{CopyStyle,PasteStyle,EditStyle,SelectAbove,SelectBelow,ExtendAbove,ExtendBelow,ConvertSmartObject}) {
        emit(HoldBegin);emit(command);emit(HoldCancel);expected.push_back(command);
    }
    emit(HoldBegin);emit(HoldPin);expected.push_back(HoldBegin);expected.push_back(HoldPin);
    emit(HoldBegin);emit(HoldReveal);emit(HoldRelease);expected.push_back(HoldBegin);expected.push_back(HoldRelease);
    emit(HoldBegin);Sleep(280);emit(CopyStyle);emit(HoldCancel);
    expected.push_back(HoldBegin);expected.push_back(HoldCancel);expected.push_back(CopyStyle);
    closing.store(true);SetEvent(available);writer.join();CloseHandle(write);
    std::string body;char buffer[4096];DWORD count=0;
    while(ReadFile(read,buffer,sizeof(buffer),&count,nullptr) && count)body.append(buffer,count);
    CloseHandle(read);CloseHandle(available);SetStdHandle(STD_OUTPUT_HANDLE,original);
    std::regex pattern("\\\"action\\\":\\\"([^\\\"]+)\\\"");
    std::vector<std::string> actions;
    for(auto i=std::sregex_iterator(body.begin(),body.end(),pattern);i!=std::sregex_iterator();++i)actions.push_back((*i)[1]);
    if(actions.size()!=expected.size()){std::cerr<<body;return 2;}
    for(size_t i=0;i<expected.size();++i)if(actions[i]!=names[expected[i]]){std::cerr<<body;return 3;}
    std::cout<<"Production pipe passed: 8 quick shortcuts emit no menu; tap/reveal/long hold preserve exact begin/release/cancel order\n";
    return 0;
}
