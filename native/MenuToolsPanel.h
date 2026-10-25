#include "MenuTextGroups.h"

struct MenuToolsPanel {
    bool active=false,opening=false,ready=false,pending=false,focus=false;
    std::string mode,error,source,sourceDisplay,revision,layerName;
    char name[801]{},grouping[4001]{};
    char draft[80001]{},find[801]{},replacement[2001]{},separator[801]{},joiner[801]=" ";
    int textTab=0,replaceMode=0,caseMode=0,tidyMode=0,splitMode=0,splitLayout=0,draftGeneration=0,previewGeneration=0,resultCount=0;
    std::string pendingAction,planId,resultValue,resultPreview,resultKind;
    void changedText(){++draftGeneration;planId.clear();resultValue.clear();resultPreview.clear();resultKind.clear();error.clear();}
    Json textParams()const {
        Json args={{"revision",revision},{"draft",draft},{"operation","edit"}};
        if(textTab==1){args["operation"]="replace";args["find"]=find;args["replacement"]=replacement;args["regex"]=replaceMode==1;args["ignore_case"]=caseMode==1;}
        if(textTab==2){const char* operations[]={"trim","remove-empty","space","join","upper","lower"};args["operation"]=operations[tidyMode];if(tidyMode==3)args["separator"]=joiner;}
        if(textTab==3){const char* modes[]={"lines","literal","regex"};args["operation"]="split";args["mode"]=modes[splitMode];args["groups"]=grouping;args["separator"]=separator;args["layout"]=splitLayout==0?"original":"lines";}
        return args;
    }
    ID3D11ShaderResourceView* thumbnail=nullptr;
    ImVec2 thumbnailSize{};
    int previewHovered=-1,previewTarget=-1,previewRequest=0;
    double previewAt=0;
    bool previewPending=false;
    std::string previewQuery,previewMessage;
    void clearPreview(){if(thumbnail){thumbnail->Release();thumbnail=nullptr;}thumbnailSize={};previewTarget=-1;previewMessage.clear();}
    bool loadPreview(const Json& result) {
        clearPreview();
        if(!result.value("available",false)){previewMessage=result.value("reason",std::string("没有可显示的内容"));return false;}
        const int w=result.value("width",0),h=result.value("height",0);
        if(w<1 || h<1 || w>128 || h>128 || !result.contains("pixels") || !result.at("pixels").is_array() || result.at("pixels").size()!=size_t(w*h*4))return false;
        std::vector<unsigned char> pixels;pixels.reserve(w*h*4);
        for(const auto& item:result.at("pixels")){if(!item.is_number_integer() || item.get<int64_t>()<0 || item.get<int64_t>()>255)return false;pixels.push_back(item.get<unsigned char>());}
        D3D11_TEXTURE2D_DESC desc{};desc.Width=w;desc.Height=h;desc.MipLevels=desc.ArraySize=1;desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA data{pixels.data(),UINT(w*4),0};ID3D11Texture2D* texture=nullptr;
        if(!device || FAILED(device->CreateTexture2D(&desc,&data,&texture)))return false;
        const auto created=device->CreateShaderResourceView(texture,nullptr,&thumbnail);texture->Release();
        if(FAILED(created))return false;
        thumbnailSize={float(w),float(h)};return true;
    }
    bool searchDirty=false;
    double searchChanged=0;
    void changeSearch(double now){clearPreview();previewHovered=-1;searchDirty=true;searchChanged=now;results=Json();error.clear();}
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

    void reset(){clearPreview();*this=MenuToolsPanel{};}
    void open(const char* value){reset();opening=true;mode=value;sendMenuTool("menu.tools.open",Json{{"mode",value}});}
    void submit(const char* action,Json args) {
        if(!ready || pending)return;
        pending=true;pendingAction=action;if(pendingAction=="text.preview")previewGeneration=draftGeneration;
        error.clear();sendMenuTool("menu.tools.request",Json{{"request",++request},{"action",action},{"args",args}});
    }
    void regroup(){split=menuSplitPreview(source,grouping);}
    std::string status() const {
        if(pending)return mode=="search"?"正在查找图层…":"正在处理…";
        if(mode!="search" || results.is_null())return "";
        return "找到图层："+std::to_string(results.at("items").size())+" · 已扫描："+std::to_string(results.value("scanned",0))+
            (results.value("truncated",false)?" · 请缩小条件":"");
    }
    void receive(const Json& event) {
        if(event.value("epoch",LPARAM(-1))!=menuEpoch || !IsWindowVisible(window))return;
        if(event.value("type",std::string())=="menu.tools.opened") {
            if(!event.value("ok",true)){reset();active=true;error=event.value("error",std::string("面板未能打开"));requireText(error);return;}
            reset();active=ready=focus=true;mode=event.at("mode").get<std::string>();
            if(mode=="split")submit("text.read",Json::object());
            else changeSearch(ImGui::GetTime()-.18);
            return;
        }
        if(event.value("type",std::string())=="menu.tools.preview.result") {
            if(!active || !previewPending || event.value("request",-1)!=previewRequest)return;
            previewPending=false;
            if(results.is_null() || results.value("search_id",std::string())!=previewQuery || previewHovered!=previewTarget)return;
            const int selected=previewTarget;
            if(!event.value("ok",false))previewMessage=event.value("error",std::string("预览未能读取"));
            else if(!loadPreview(event.at("result")) && previewMessage.empty())previewMessage="预览像素不可用";
            previewTarget=selected;requireText(previewMessage);return;
        }
        if(!active || !pending || event.value("request",-1)!=request)return;
        pending=false;
        if(event.value("action",std::string())=="text.preview" && previewGeneration!=draftGeneration)return;
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
            std::snprintf(draft,sizeof(draft),"%s",sourceDisplay.c_str());changedText();
        } else if(action=="text.preview") {
            planId=result.at("plan_id").get<std::string>();resultValue=result.at("value").get<std::string>();
            std::replace(resultValue.begin(),resultValue.end(),'\r','\n');
            resultPreview=result.at("preview").get<std::string>();resultKind=result.at("kind").get<std::string>();resultCount=result.at("count").get<int>();requireText(resultPreview);
        } else if(action=="text.split" || action=="text.apply") {source.clear();revision.clear();changedText();}
    }
    void drawText(float scale) {
        if(MenuControls::button("重新读取（覆盖草稿）",scale)){source.clear();revision.clear();changedText();submit("text.read",Json::object());}
        if(revision.empty())return;
        {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("%s",layerName.c_str());}
        const char* tabs[]={"编辑","查找替换","整理","拆分"};
        if(MenuControls::segments("##text-tabs",tabs,textTab,scale))changedText();
        {MenuTextStyle text(MenuTextRole::Body);ImGui::TextUnformatted("编辑文字");}
        ImGui::PushID(int(menuEpoch));
        if(MenuControls::multiline("##draft",draft,sizeof(draft),110*scale))changedText();
        ImGui::PopID();
        if(textTab==1) {
            const char* modes[]={"普通查找","正则表达式"};if(MenuControls::segments("##replace-mode",modes,replaceMode,scale))changedText();
            const char* cases[]={"区分大小写","忽略大小写"};if(MenuControls::segments("##replace-case",cases,caseMode,scale))changedText();
            MenuControls::input("##find","查找内容",find,sizeof(find));if(ImGui::IsItemEdited())changedText();
            MenuControls::input("##replacement","替换为（可留空）",replacement,sizeof(replacement));if(ImGui::IsItemEdited())changedText();
            if(replaceMode==1){MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("Python 正则；替换可用 \\1 或 \\g<名称> 引用分组");}
        } else if(textTab==2) {
            const char* tidy[]={"去首尾空白","删空行","合并空格","合并行","大写","小写"};
            if(MenuControls::segments("##tidy",tidy,tidyMode,scale))changedText();
            if(tidyMode==3){MenuControls::input("##joiner","合并行的连接符（可留空）",joiner,sizeof(joiner));if(ImGui::IsItemEdited())changedText();}
        } else if(textTab==3) {
            const char* modes[]={"按行分组","分隔符","正则分隔"};if(MenuControls::segments("##split-mode",modes,splitMode,scale))changedText();
            if(splitMode==0){MenuControls::input("##groups","例如 1-3,4,5-7",grouping,sizeof(grouping));if(ImGui::IsItemEdited())changedText();}
            else {MenuControls::input("##separator",splitMode==1?"分隔符，例如逗号或空格":"正则分隔符，例如 [,，]",separator,sizeof(separator));if(ImGui::IsItemEdited())changedText();}
            const char* layouts[]={"保留位置","逐行排列"};if(MenuControls::segments("##split-layout",layouts,splitLayout,scale))changedText();
            {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("分隔符保留在前一组；最多64组。保留位置要求原有换行边界，不换行文字请选择逐行排列。");}
        }
        ImGui::BeginDisabled(pending);
        if(MenuControls::button("计算预览",scale)){planId.clear();submit("text.preview",textParams());}
        ImGui::EndDisabled();
        {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("%s",planId.empty()?"折行预览 · 尚未写入PS":resultKind=="split"?("拆分预览 · "+std::to_string(resultCount)+" 个文字层").c_str():"处理结果 · 确认后写入PS");}
        MenuControls::textPreview("##text-result",planId.empty()?draft:resultPreview.c_str(),130*scale);
        ImGui::BeginDisabled(planId.empty() || pending);
        if(MenuControls::button(resultKind=="split"?"确认拆分并替换原层":"确认写回文字",scale))submit("text.apply",Json{{"revision",revision},{"plan_id",planId}});
        if(MenuControls::button("将结果继续编辑",scale)){std::snprintf(draft,sizeof(draft),"%s",resultValue.c_str());textTab=0;changedText();}
        ImGui::EndDisabled();
    }
    void draw(float scale,ImVec2 center,bool available) {
        const auto pos=ImGui::GetWindowPos(),size=ImGui::GetWindowSize();
        MenuControls::PanelStyle controls(scale);
        const float gap=menuControlPadding*scale,margin=menuFloatingInset*scale,h=menuControlHeight*scale;
        const float width=std::max(1.f,std::min((mode=="search"?420:620)*scale,size.x-margin*2));
        const int rows=results.is_null()?0:std::min(8,int(results.at("items").size()));
        const float contentHeight=mode=="search"?(140+30*std::max(0,rows-1))*scale:size.y-margin*2;
        const float height=std::max(1.f,std::min(contentHeight,size.y-60*scale-margin*2));
        const ImVec2 at={pos.x+margin,pos.y+margin};
        menuShadow::draw(ImGui::GetWindowDrawList(),at,{at.x+width,at.y+height},ImGui::GetStyle().FrameRounding,scale);
        ImGui::SetCursorScreenPos(at);
        ImGui::PushStyleColor(ImGuiCol_ChildBg,ImGui::GetStyleColorVec4(ImGuiCol_PopupBg));
        ImGui::BeginChild("##caps-tools",{width,height},ImGuiChildFlags_Borders|ImGuiChildFlags_AlwaysUseWindowPadding);
        ImGui::PopStyleColor();
        if(opening || !ready){ImGui::TextWrapped("%s",error.empty()?"正在准备输入保护…":error.c_str());if(MenuControls::button("关闭",scale))send("hide");ImGui::EndChild();return;}
        ImGui::BeginDisabled((pending && mode!="search" && pendingAction!="text.preview") || !available);
        if(mode=="search") {
            if(focus){ImGui::SetKeyboardFocusHere();focus=false;}
            ImGui::PushID(int(menuEpoch));
            const bool enter=MenuControls::input("##layer","搜索图层…",name,sizeof(name));
            ImGui::PopID();
            if(ImGui::IsItemEdited())changeSearch(ImGui::GetTime());
            const char* kinds[]={"全部","像素","文字","组","形状","智能对象","调整","填充","其他"};
            const char* ids[]={"all","pixel","text","group","shape","smart-object","adjustment","fill","other"};
            const int icons[]={7,35,36,2,37,38,6,1,40};
            if(MenuControls::iconSegments("##types",kinds,icons,kind,scale))changeSearch(ImGui::GetTime()-.18);
            if(enter && !pending)changeSearch(ImGui::GetTime()-.18);
            if(available && searchDue(ImGui::GetTime())) {
                searchDirty=false;submit("layers.search",Json{{"name",name},{"type",ids[kind]}});
            }
            if(!results.is_null()) {
                const float rows=std::max(menuSearchRowHeight*scale,ImGui::GetContentRegionAvail().y-h-gap);
                ImGui::BeginChild("##results",{0,rows},ImGuiChildFlags_None);
                int index=0,hover=-1;ImVec2 anchor{};
                for(const auto& row:results.at("items")) {
                    ImGui::PushID(index);ImGui::BeginDisabled(pending);
                    const auto type=row.value("type",std::string("other"));int typeIndex=8;
                    for(int i=0;i<IM_ARRAYSIZE(ids);++i)if(type==ids[i])typeIndex=i;
                    bool over=false;ImVec2 point{};
                    if(MenuControls::resultRow("##result",icons[typeIndex],row.at("name").get_ref<const std::string&>().c_str(),row.at("document_name").get_ref<const std::string&>().c_str(),scale,over,point))
                        submit("layers.focus",Json{{"search_id",results.at("search_id")},{"index",index}});
                    if(over){hover=index;anchor=point;}
                    ImGui::EndDisabled();ImGui::PopID();++index;
                }
                if(hover!=previewHovered){previewHovered=hover;previewAt=ImGui::GetTime();}
                if(hover>=0 && ImGui::GetTime()-previewAt>=.25) {
                    if(!previewPending && previewTarget!=hover) {
                        clearPreview();previewTarget=hover;
                        if(!layerPreviewReady)previewMessage="当前PS不支持图层像素预览";
                        else {
                            previewPending=true;previewQuery=results.at("search_id").get<std::string>();
                            sendMenuTool("menu.tools.preview",Json{{"request",++previewRequest},{"search_id",previewQuery},{"index",hover}});
                        }
                    }
                    MenuControls::previewTile(previewTarget==hover?thumbnail:nullptr,thumbnailSize,previewMessage.empty()?"正在读取预览…":previewMessage.c_str(),anchor,{at.x,at.y,at.x+width,at.y+height},scale);
                }
                ImGui::EndChild();
            }
        } else {
            ImGui::BeginChild("##text-body",{0,std::max(h,ImGui::GetContentRegionAvail().y-h-gap)},ImGuiChildFlags_None);
            drawText(scale);ImGui::EndChild();
        }
        ImGui::EndDisabled();
        if(MenuControls::button("关闭",scale))send("hide");
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
