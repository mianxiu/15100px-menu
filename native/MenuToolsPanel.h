#include "MenuTextGroups.h"

struct MenuToolsPanel {
    bool active=false,opening=false,ready=false,pending=false,focus=false;
    std::string mode,error,source,sourceDisplay,revision,layerName;
    char name[801]{},grouping[4001]{};
    char draft[80001]{},find[801]{},replacement[2001]{},separator[801]{},joiner[801]=" ";
    char listCustom[9]{},listStart[9]="1";
    inline static constexpr const char* listKinds[]={"bullet","numbered","remove"},*listMarkers[]={"auto","disc","circle","square","dash","check","custom"},*listStyles[]={"decimal","right-paren","parens","lower-alpha","upper-alpha","lower-roman","upper-roman","hierarchical","mixed"};
    Json draftList=nullptr;bool draftListChanged=false;
    void restoreList(const Json& value) {
        if(!value.is_object())return;
        const auto kind=value.value("kind",std::string()),marker=value.value("marker",std::string()),numbering=value.value("numbering",std::string());
        const auto k=std::find(std::begin(listKinds),std::end(listKinds),kind),m=std::find(std::begin(listMarkers),std::end(listMarkers),marker),n=std::find(std::begin(listStyles),std::end(listStyles),numbering);
        if(k==std::end(listKinds) || k-std::begin(listKinds)>1 || m==std::end(listMarkers) || n==std::end(listStyles) || !value.contains("start") || !value.at("start").is_number_integer())return;
        const auto start=value.at("start").get<int64_t>();const auto custom=value.value("custom_marker",std::string());
        if(start<1 || start>9999 || custom.size()>=sizeof(listCustom))return;
        listMode=int(k-std::begin(listKinds));listMarker=int(m-std::begin(listMarkers));listNumbering=int(n-std::begin(listStyles));
        std::snprintf(listStart,sizeof(listStart),"%d",int(start));std::snprintf(listCustom,sizeof(listCustom),"%s",custom.c_str());textTab=4;
    }
    int listMarker=0,listNumbering=0,indentCommand=0,selectionStart=0,selectionEnd=0,cursorPos=0,draftBufferId=0;
    bool restoreDraftFocus=false;
    int textTab=0,replaceMode=0,caseMode=0,tidyMode=0,listMode=0,splitMode=0,splitLayout=0,draftGeneration=0,previewGeneration=0,resultCount=0;
    std::string pendingAction,planId,resultValue,resultPreview,resultKind;
    std::vector<MenuControls::TextRange> textMatches;std::string matchSource;
    bool textDirty=false;double textChanged=0;
    void changedText(){++draftGeneration;planId.clear();resultValue.clear();resultPreview.clear();resultKind.clear();textMatches.clear();matchSource.clear();error.clear();textDirty=true;textChanged=ImGui::GetTime();}
    void setDraft(const std::string& value){std::snprintf(draft,sizeof(draft),"%s",value.c_str());++draftBufferId;indentCommand=selectionStart=selectionEnd=cursorPos=0;restoreDraftFocus=false;changedText();}
    static int draftCallback(ImGuiInputTextCallbackData* data) {
        auto& panel=*static_cast<MenuToolsPanel*>(data->UserData);
        if(data->EventFlag==ImGuiInputTextFlags_CallbackCharFilter) {
            const auto& io=ImGui::GetIO();
            if(panel.textTab==4 && data->EventChar=='\t' && ImGui::IsKeyDown(ImGuiKey_Tab) && !io.KeyCtrl && !io.KeyAlt && !io.KeySuper){panel.indentCommand=1;return 1;}
            return 0;
        }
        if(panel.restoreDraftFocus){data->SelectionStart=panel.selectionStart;data->SelectionEnd=panel.selectionEnd;data->CursorPos=panel.cursorPos;panel.restoreDraftFocus=false;}
        const auto& io=ImGui::GetIO();
        if(panel.textTab==4)ImGui::SetKeyOwner(ImGuiKey_Tab,data->ID);
        if(panel.textTab==4 && io.KeyShift && !io.KeyCtrl && !io.KeyAlt && !io.KeySuper && ImGui::IsKeyPressed(ImGuiKey_Tab))panel.indentCommand=-1;
        if(panel.indentCommand) {
            const auto result=menuIndentLines(data->Buf,data->SelectionStart,data->SelectionEnd,data->CursorPos,panel.indentCommand);panel.indentCommand=0;
            if(!result.error.empty()){panel.error=result.error;requireText(panel.error);}
            else if(result.text!=data->Buf){data->DeleteChars(0,data->BufTextLen);data->InsertChars(0,result.text.c_str());data->SelectionStart=result.start;data->SelectionEnd=result.end;data->CursorPos=result.cursor;}
        }
        panel.selectionStart=data->SelectionStart;panel.selectionEnd=data->SelectionEnd;panel.cursorPos=data->CursorPos;
        return 0;
    }
    bool textDue(double now)const{return textDirty && active && ready && !pending && !revision.empty() && (textTab!=1 || find[0]) && (textTab!=3 || splitMode==0 || separator[0]) && now-textChanged>=.18;}
    bool canWriteText()const{return !pending && !revision.empty() && draft[0];}
    std::string textStatus()const {
        if(!error.empty())return textTab==3?error+"；仍可写回当前文字":error;
        if(pending && pendingAction=="text.preview")return "正在自动预览 · 可继续编辑，尚未写入PS";
        if(pending && (pendingAction=="text.write" || pendingAction=="text.apply"))return pendingAction=="text.apply" && resultKind=="split"?"正在拆成多个图层…":"正在写回文字…";
        if(planId.empty()) {
            if(textTab==1 && !find[0])return "请输入查找内容后自动预览";
            if(textTab==3 && splitMode!=0 && !separator[0])return "请输入分隔符或正则；仍可写回当前文字";
            return "等待自动预览 · 尚未写入PS";
        }
        return resultKind=="split"?"拆分预览 · "+std::to_string(resultCount)+" 个文字层":"处理结果 · 确认后写入PS";
    }
    Json textParams()const {
        Json args={{"revision",revision},{"draft",draft},{"operation","edit"}};
        if(textTab==1){args["operation"]="replace";args["find"]=find;args["replacement"]=replacement;args["regex"]=replaceMode==1;args["ignore_case"]=caseMode==1;}
        if(textTab==2){const char* operations[]={"trim","remove-empty","space","join","upper","lower"};args["operation"]=operations[tidyMode];if(tidyMode==3)args["separator"]=joiner;}
        if(textTab==3){const char* modes[]={"lines","literal","regex"};args["operation"]="split";args["mode"]=modes[splitMode];args["groups"]=grouping[0]?std::string(grouping):menuDefaultGroups(draft);args["separator"]=separator;args["layout"]=splitLayout==0?"original":"lines";}
        if(textTab==4){args["operation"]="list";args["kind"]=listKinds[listMode];args["marker"]=listMarkers[listMarker];args["custom_marker"]=listMarker==6?listCustom:"";args["numbering"]=listStyles[listNumbering];args["start"]=listMode==1?listStart:"1";}
        else if(textTab!=3 && draftListChanged)args["list_options"]=draftList;
        return args;
    }
    ID3D11ShaderResourceView* thumbnail=nullptr;
    ImVec2 thumbnailSize{};
    int previewHovered=-1,previewTarget=-1,previewRequest=0;
    double previewAt=0;
    bool previewPending=false,previewVisible=false;
    std::string previewQuery,previewMessage;
    void clearPreview(){if(thumbnail){thumbnail->Release();thumbnail=nullptr;}thumbnailSize={};previewTarget=-1;previewVisible=false;previewMessage.clear();}
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
    bool searchDue(double now)const{return searchDirty && !pending && !previewPending && ready && now-searchChanged>=.18;}
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
        pending=true;pendingAction=action;if(pendingAction=="text.preview"){previewGeneration=draftGeneration;planId.clear();textMatches.clear();}
        error.clear();sendMenuTool("menu.tools.request",Json{{"request",++request},{"action",action},{"args",args}});
    }
    void regroup(){split=menuSplitPreview(source,grouping[0]?std::string(grouping):menuDefaultGroups(source));}
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
            if(results.is_null() || results.value("search_id",std::string())!=previewQuery)return;
            const int selected=previewTarget;
            if(!event.value("ok",false))previewMessage=event.value("error",std::string("预览未能读取"));
            else if(!loadPreview(event.at("result")) && previewMessage.empty())previewMessage="预览像素不可用";
            previewTarget=selected;previewVisible=true;requireText(previewMessage);return;
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
            grouping[0]=0;splitLayout=source.find_first_of("\r\n")==std::string::npos?1:0;regroup();requireText(source);requireText(layerName);
            setDraft(sourceDisplay);
            draftList=nullptr;draftListChanged=false;
            if(result.contains("list_options"))restoreList(result.at("list_options"));
            if(result.contains("list_warning")){error=result.at("list_warning").get<std::string>();requireText(error);}
        } else if(action=="text.preview") {
            textMatches.clear();matchSource.clear();
            for(size_t i=0;draft[i];++i){if(draft[i]=='\r'){matchSource+='\n';if(draft[i+1]=='\n')++i;}else matchSource+=draft[i];}
            std::vector<MenuControls::TextRange> validated;
            const auto matches=result.value("matches",Json::array());int last=0;const int length=int(matchSource.size());
            if(!matches.is_array()){error="匹配范围无效，请重新预览";return;}
            for(const auto& span:matches) {
                if(!span.is_array() || span.size()!=2 || !span[0].is_number_integer() || !span[1].is_number_integer()){error="匹配范围无效，请重新预览";return;}
                const auto start=span[0].get<int64_t>(),end=span[1].get<int64_t>();
                if(start<last || end<=start || end>length || (static_cast<unsigned char>(matchSource[start])&0xc0)==0x80 || (static_cast<unsigned char>(matchSource[end])&0xc0)==0x80){textMatches.clear();error="匹配范围无效，请重新预览";return;}
                validated.emplace_back(int(start),int(end));last=int(end);
            }
            textMatches=std::move(validated);
            planId=result.at("plan_id").get<std::string>();resultValue=result.at("value").get<std::string>();
            std::replace(resultValue.begin(),resultValue.end(),'\r','\n');
            resultPreview=result.at("preview").get<std::string>();resultKind=result.at("kind").get<std::string>();resultCount=result.at("count").get<int>();requireText(resultPreview);
        } else if(action=="text.split" || action=="text.apply" || action=="text.write") {source.clear();revision.clear();changedText();}
    }
    void drawText(float scale,bool available) {
        ImGui::BeginDisabled(pending);
        if(MenuControls::button("重新读取（覆盖草稿）",scale)){source.clear();revision.clear();changedText();submit("text.read",Json::object());}
        ImGui::EndDisabled();
        if(revision.empty())return;
        {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("%s",layerName.c_str());}
        const char* tabs[]={"编辑","查找替换","整理","拆分","列表"};
        if(MenuControls::segments("##text-tabs",tabs,textTab,scale))changedText();
        {MenuTextStyle text(MenuTextRole::Body);ImGui::TextUnformatted("编辑文字");}
        ImGui::PushID(int(menuEpoch));
        ImGui::PushID(draftBufferId);
        if(restoreDraftFocus)ImGui::SetKeyboardFocusHere();
        if(MenuControls::multiline("##draft",draft,sizeof(draft),110*scale,draftCallback,this))changedText();
        ImGui::PopID();ImGui::PopID();
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
            if(splitMode==0){MenuControls::input("##groups","留空自动按行分组；自定义如 1-2,3",grouping,sizeof(grouping));if(ImGui::IsItemEdited())changedText();}
            else {MenuControls::input("##separator",splitMode==1?"分隔符，例如逗号或空格":"正则分隔符，例如 [,，]",separator,sizeof(separator));if(ImGui::IsItemEdited())changedText();}
            const char* layouts[]={"保留位置","逐行排列"};if(MenuControls::segments("##split-layout",layouts,splitLayout,scale))changedText();
            {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("留空自动按行分组，最多64组，自动折行不计。写回当前文字保留原图层，拆成多个图层才替换原层；保留位置要求原有换行边界。");}
        } else if(textTab==4) {
            const char* lists[]={"项目列表","编号列表","移除列表"};if(MenuControls::segments("##list-mode",lists,listMode,scale))changedText();
            if(listMode==0) {
                const char* markers[]={"随层级 • ◦ ▪","•","◦","▪","–","✓","自定义"};if(MenuControls::segments("##list-markers",markers,listMarker,scale))changedText();
                if(listMarker==6){MenuControls::input("##list-custom","项目符号（一个字符）",listCustom,sizeof(listCustom));if(ImGui::IsItemEdited())changedText();}
            } else if(listMode==1) {
                const char* styles[]={"1.","1)","(1)","a)","A)","i)","I)","1.1","1.a.i"};if(MenuControls::segments("##list-numbering",styles,listNumbering,scale))changedText();
                MenuControls::input("##list-start","起始编号 1—9999",listStart,sizeof(listStart));if(ImGui::IsItemEdited())changedText();
            }
            int indent=-1;const char* actions[]={"减少缩进","增加缩进"};
            if(MenuControls::segments("##list-indent",actions,indent,scale)){indentCommand=indent==0?-1:1;restoreDraftFocus=true;}
            {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("缩进作用于选中行或当前行，最多6级；Tab增加、Shift+Tab减少。预览自动更新编号，空行保留；每级写入4个空格，写回PS后不自动续号。");}
        }
        if(available && textDue(ImGui::GetTime())){textDirty=false;submit("text.preview",textParams());}
        if(textTab==1 && !planId.empty()) {
            {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("匹配 %d 处 · 强调色为匹配内容",resultCount);}
            MenuControls::textPreview("##text-matches",matchSource.c_str(),80*scale,textMatches);
        }
        {MenuTextStyle text(MenuTextRole::Secondary);ImGui::TextWrapped("%s",textStatus().c_str());}
        MenuControls::textPreview("##text-result",planId.empty()?draft:resultPreview.c_str(),130*scale,{},textTab==4 && !planId.empty() && listMode!=2);
        const bool processed=textTab!=3 && !planId.empty() && resultKind=="replace";
        ImGui::BeginDisabled(!canWriteText());
        if(MenuControls::button(processed?"写回预览结果":"写回当前文字",scale)) {
            if(processed)submit("text.apply",Json{{"revision",revision},{"plan_id",planId}});
            else {Json args={{"revision",revision},{"draft",draft}};if(draftListChanged)args["list_options"]=draftList;submit("text.write",args);}
        }
        ImGui::EndDisabled();
        if(textTab==3) {
            ImGui::BeginDisabled(planId.empty() || resultKind!="split" || pending);
            if(MenuControls::button("拆成多个图层",scale))submit("text.apply",Json{{"revision",revision},{"plan_id",planId}});
            ImGui::EndDisabled();
        }
        ImGui::BeginDisabled(planId.empty() || pending);
        if(MenuControls::button("将结果继续编辑",scale)){
            if(textTab==4){const auto params=textParams();draftList=nullptr;if(listMode!=2){draftList=Json::object();for(const char* key:{"kind","marker","custom_marker","numbering","start"})draftList[key]=params.at(key);}draftListChanged=true;}
            setDraft(resultValue);textTab=0;
        }
        ImGui::EndDisabled();
    }
    void draw(float scale,ImVec2 center,bool available) {
        const auto pos=ImGui::GetWindowPos(),size=ImGui::GetWindowSize();
        MenuControls::PanelStyle controls(scale);
        const float gap=menuControlPadding*scale,margin=menuFloatingInset*scale,h=menuControlHeight*scale;
        const float width=std::max(1.f,std::min((mode=="search"?420:620)*scale,size.x-margin*2));
        const char* kinds[]={"全部","像素","文字","组","形状","智能对象","调整","填充","其他"};
        const float filters=MenuControls::segmentsHeight(kinds,width-2*ImGui::GetStyle().WindowPadding.x,scale);
        const int rows=results.is_null()?0:std::min(8,int(results.at("items").size()));
        const float contentHeight=mode=="search"?(140+30*std::max(0,rows-1))*scale+filters-figmaDisplayWidgetHeight*scale:size.y-margin*2;
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
            const bool enter=MenuControls::input("##layer","搜索图层…",name,sizeof(name),MenuControls::Emphasis::Neutral);
            ImGui::PopID();
            if(ImGui::IsItemEdited())changeSearch(ImGui::GetTime());
                const char* ids[]={"all","pixel","text","group","shape","smart-object","adjustment","fill","other"};
            const int icons[]={7,35,36,2,37,38,6,1,40};
            if(MenuControls::segments("##types",kinds,kind,scale))changeSearch(ImGui::GetTime()-.18);
            if(enter && !pending)changeSearch(ImGui::GetTime()-.18);
            if(available && searchDue(ImGui::GetTime())) {
                searchDirty=false;submit("layers.search",Json{{"name",name},{"type",ids[kind]}});
            }
            if(!results.is_null()) {
                const float rows=std::max(menuSearchRowHeight*scale,ImGui::GetContentRegionAvail().y-h-gap);
                ImGui::BeginChild("##results",{0,rows},ImGuiChildFlags_None);
                int index=0,hover=-1;bool previewInView=false;ImVec2 anchor{},selectedAnchor{};
                for(const auto& row:results.at("items")) {
                    ImGui::PushID(index);ImGui::BeginDisabled(pending || previewPending);
                    const auto type=row.value("type",std::string("other"));int typeIndex=8;
                    for(int i=0;i<IM_ARRAYSIZE(ids);++i)if(type==ids[i])typeIndex=i;
                    const bool canPreview=type!="adjustment" && (layerPreviewReady && type!="group");
                    bool over=false,previewClick=false;ImVec2 point{};
                    if(MenuControls::resultRow("##result",icons[typeIndex],row.at("name").get_ref<const std::string&>().c_str(),row.at("document_name").get_ref<const std::string&>().c_str(),scale,over,point,&previewClick,canPreview))
                        submit("layers.focus",Json{{"search_id",results.at("search_id")},{"index",index}});
                    if(previewClick && !previewPending) {
                        if(previewTarget==index && previewVisible)previewVisible=false;
                        else {
                            clearPreview();previewTarget=index;previewVisible=true;
                            if(!layerPreviewReady)previewMessage="请更新执行插件以读取缩略图";
                            else {
                                previewPending=true;previewQuery=results.at("search_id").get<std::string>();
                                sendMenuTool("menu.tools.preview",Json{{"request",++previewRequest},{"search_id",previewQuery},{"index",index}});
                            }
                        }
                    }
                    if(over){hover=index;anchor=point;}
                    if(canPreview && previewTarget==index){selectedAnchor=point;previewInView=ImGui::IsRectVisible(point,{point.x+menuSearchRowHeight*scale,point.y+menuSearchRowHeight*scale});}
                    ImGui::EndDisabled();ImGui::PopID();++index;
                }
                if(hover!=previewHovered){previewHovered=hover;previewAt=ImGui::GetTime();}
                if(previewVisible && previewTarget>=0 && previewInView)
                    MenuControls::previewTile(thumbnail,thumbnailSize,previewMessage.empty()?"正在生成预览…":previewMessage.c_str(),selectedAnchor,{at.x,at.y,at.x+width,at.y+height},scale);
                else if(hover>=0 && ImGui::GetTime()-previewAt>=.25)MenuControls::tip("点击预览图层",scale);
                ImGui::EndChild();
            }
        } else {
            ImGui::BeginChild("##text-body",{0,std::max(h,ImGui::GetContentRegionAvail().y-h-gap)},ImGuiChildFlags_None);
            drawText(scale,available);ImGui::EndChild();
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
