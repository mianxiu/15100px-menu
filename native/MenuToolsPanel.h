#include "MenuTextGroups.h"

struct MenuToolsPanel {
    bool active=false,opening=false,ready=false,pending=false,focus=false;
    std::string mode,error,source,sourceDisplay,revision,layerName;
    char name[801]{},grouping[4001]{};
    bool searchDirty=false;
    double searchChanged=0;
    void changeSearch(double now){searchDirty=true;searchChanged=now;results=Json();error.clear();}
    bool searchDue(double now)const{return searchDirty && !pending && ready && now-searchChanged>=.18;}
    int kind=0,request=0;
    Json results;
    MenuSplitPreview split;
    bool dragging=false;
    POINT dragPointer{};
    static POINT dragPosition(RECT own,RECT limit,POINT delta) {
        return {std::clamp(own.left+delta.x,limit.left,std::max(limit.left,limit.right-(own.right-own.left))),
                std::clamp(own.top+delta.y,limit.top,std::max(limit.top,limit.bottom-(own.bottom-own.top)))};
    }

    void reset(){*this=MenuToolsPanel{};}
    void open(const char* value){reset();opening=true;mode=value;sendMenuTool("menu.tools.open",Json{{"mode",value}});}
    void submit(const char* action,Json args) {
        if(!ready || pending)return;
        pending=true;error.clear();sendMenuTool("menu.tools.request",Json{{"request",++request},{"action",action},{"args",args}});
    }
    void regroup(){split=menuSplitPreview(source,grouping);}
    void receive(const Json& event) {
        if(event.value("epoch",LPARAM(-1))!=menuEpoch || !IsWindowVisible(window))return;
        if(event.value("type",std::string())=="menu.tools.opened") {
            if(!event.value("ok",true)){reset();active=true;error=event.value("error",std::string("面板未能打开"));requireText(error);return;}
            reset();active=ready=focus=true;mode=event.at("mode").get<std::string>();
            if(mode=="split")submit("text.read",Json::object());
            else changeSearch(ImGui::GetTime()-.18);
            return;
        }
        if(!active || !pending || event.value("request",-1)!=request)return;
        pending=false;
        if(event.value("action",std::string())=="layers.search" && searchDirty)return;
        if(!event.value("ok",false)){error=event.value("error",std::string("操作失败"));requireText(error);return;}
        const auto action=event.value("action",std::string());const auto& result=event.at("result");
        if(action=="layers.search") {
            results=result;
            for(const auto& row:results.at("items")){requireText(row.at("name"));requireText(row.at("document_name"));}
        } else if(action=="text.read") {
            source=result.at("text").get<std::string>();sourceDisplay=source;std::replace(sourceDisplay.begin(),sourceDisplay.end(),'\r','\n');
            revision=result.at("revision").get<std::string>();layerName=result.at("name").get<std::string>();
            const auto groups=menuDefaultGroups(source);std::snprintf(grouping,sizeof(grouping),"%s",groups.c_str());regroup();requireText(source);requireText(layerName);
        } else if(action=="text.split") {source.clear();revision.clear();}
    }
    void draw(float scale,ImVec2 center,bool available) {
        const auto pos=ImGui::GetWindowPos(),size=ImGui::GetWindowSize();
        const float gap=menuControlPadding*scale,padding=menuControlPadding*scale,h=menuControlHeight*scale;
        const float width=std::max(1.f,std::min(420*scale,size.x-gap*2));
        const int rows=results.is_null()?0:std::min(6,int(results.at("items").size()));
        const float contentHeight=mode=="search"?(218+46*rows)*scale:510*scale;
        const float height=std::max(1.f,std::min(contentHeight,size.y-70*scale));
        const ImVec2 at={pos.x+gap,pos.y+gap};
        ImGui::SetCursorScreenPos(at);
        ImGui::PushStyleVar(ImGuiStyleVar_ChildRounding,ImGui::GetStyle().FrameRounding);
        ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,{padding,padding});
        ImGui::PushStyleColor(ImGuiCol_ChildBg,ImGui::GetStyleColorVec4(ImGuiCol_PopupBg));
        ImGui::BeginChild("##caps-tools",{width,height},ImGuiChildFlags_Borders|ImGuiChildFlags_AlwaysUseWindowPadding);
        ImGui::PopStyleColor();ImGui::PopStyleVar(2);
        if(opening || !ready){ImGui::TextWrapped("%s",error.empty()?"正在准备输入保护…":error.c_str());if(ImGui::Button("关闭",{0,h}))send("hide");ImGui::EndChild();return;}
        ImGui::BeginDisabled((pending && mode!="search") || !available);
        if(mode=="search") {
            ImGui::SetNextItemWidth(-1);
            if(focus){ImGui::SetKeyboardFocusHere();focus=false;}
            const bool enter=ImGui::InputTextWithHint("##layer","搜索图层…",name,sizeof(name),ImGuiInputTextFlags_EnterReturnsTrue);
            if(ImGui::IsItemEdited())changeSearch(ImGui::GetTime());
            const char* kinds[]={"全部","像素","文字","组","形状","智能对象","调整","填充","其他"};
            const char* ids[]={"all","pixel","text","group","shape","smart-object","adjustment","fill","other"};
            for(int i=0;i<IM_ARRAYSIZE(kinds);++i) {
                const float buttonWidth=ImGui::CalcTextSize(kinds[i]).x+ImGui::GetStyle().FramePadding.x*2;
                if(i && ImGui::GetItemRectMax().x+ImGui::GetStyle().ItemSpacing.x+buttonWidth<ImGui::GetWindowPos().x+ImGui::GetWindowContentRegionMax().x)ImGui::SameLine();
                ImGui::PushID(i);
                if(ImGui::Selectable(kinds[i],kind==i,ImGuiSelectableFlags_None,{buttonWidth,h})) {
                    kind=i;changeSearch(ImGui::GetTime()-.18);
                }
                ImGui::PopID();
            }
            if(enter && !pending)changeSearch(ImGui::GetTime()-.18);
            if(available && searchDue(ImGui::GetTime())) {
                searchDirty=false;submit("layers.search",Json{{"name",name},{"type",ids[kind]}});
            }
            if(!results.is_null()) {
                ImGui::Text("找到图层：%d · 已扫描：%d",int(results.at("items").size()),results.value("scanned",0));
                if(results.value("truncated",false))ImGui::TextWrapped("达到搜索上限，请缩小条件");
                const float rows=std::max(60*scale,ImGui::GetContentRegionAvail().y-h-gap);
                ImGui::BeginChild("##results",{0,rows},ImGuiChildFlags_None);
                int index=0;
                for(const auto& row:results.at("items")) {
                    ImGui::PushID(index);
                    ImGui::BeginDisabled(pending);
                    if(ImGui::Button("定位",{0,h}))submit("layers.focus",Json{{"search_id",results.at("search_id")},{"index",index}});
                    ImGui::EndDisabled();ImGui::SameLine();ImGui::BeginGroup();
                    ImGui::TextUnformatted(row.at("name").get_ref<const std::string&>().c_str());
                    const auto type=row.value("type",std::string("other"));int typeIndex=8;
                    for(int i=0;i<IM_ARRAYSIZE(ids);++i)if(type==ids[i])typeIndex=i;
                    ImGui::Text("%s · %s",row.at("document_name").get_ref<const std::string&>().c_str(),kinds[typeIndex]);
                    ImGui::EndGroup();ImGui::Separator();ImGui::PopID();++index;
                }
                ImGui::EndChild();
            }
        } else {
            if(ImGui::Button("重新读取选中文字",{0,h})){source.clear();revision.clear();submit("text.read",Json::object());}
            if(!revision.empty()) {
                ImGui::TextUnformatted(layerName.c_str());ImGui::TextUnformatted("原文字");
                ImGui::BeginChild("##source",{0,88*scale},ImGuiChildFlags_Borders);ImGui::TextUnformatted(sourceDisplay.c_str());ImGui::EndChild();
                ImGui::TextUnformatted("按行分组");ImGui::SetNextItemWidth(-1);
                if(ImGui::InputText("##groups",grouping,sizeof(grouping)))regroup();
                ImGui::TextWrapped("例如1-3,4,5-7；按顺序覆盖所有行，最多64组");
                ImGui::Text("独立文字层数量：%d",split.count);
                ImGui::BeginChild("##split",{0,130*scale},ImGuiChildFlags_Borders);ImGui::TextUnformatted(split.text.c_str());ImGui::EndChild();
                if(!split.error.empty())ImGui::TextWrapped("%s",split.error.c_str());
                ImGui::BeginDisabled(!split.error.empty() || split.count<2);
                if(ImGui::Button("确认拆分并替换原层",{0,h}))submit("text.split",Json{{"revision",revision},{"breaks",split.breaks}});
                ImGui::EndDisabled();
            }
        }
        ImGui::EndDisabled();
        if(pending)ImGui::TextUnformatted("正在处理…");
        if(ImGui::Button("关闭",{0,h}))send("hide");
        if(ImGui::IsMouseClicked(ImGuiMouseButton_Left) && ImGui::IsWindowHovered() && !ImGui::IsAnyItemHovered() && !ImGui::IsAnyItemActive()) {
            dragging=true;GetCursorPos(&dragPointer);
        }
        if(!available || pending || !ImGui::IsMouseDown(ImGuiMouseButton_Left))dragging=false;
        if(dragging && !pending) {
            POINT pointer{};GetCursorPos(&pointer);
            RECT own{},owner{},limit{};GetWindowRect(window,&own);
            HWND target=GetWindow(window,GW_OWNER);
            MONITORINFO monitor{sizeof(MONITORINFO)};
            if(target && GetWindowRect(target,&owner) && GetMonitorInfoW(MonitorFromWindow(target,MONITOR_DEFAULTTONEAREST),&monitor) && IntersectRect(&limit,&owner,&monitor.rcWork)) {
                const auto at=dragPosition(own,limit,{pointer.x-dragPointer.x,pointer.y-dragPointer.y});
                SetWindowPos(window,nullptr,at.x,at.y,0,0,SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE);
            }
            dragPointer=pointer;
        }
        ImGui::EndChild();
    }
};
static MenuToolsPanel menuTools;
