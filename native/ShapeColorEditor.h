// Local paint draft only. The renderer never communicates with Photoshop.
struct ShapeColorEditor {
    bool available=false,dirty=false,vector=true;
    int channel=0,stop=0;
    Json original,draft,patterns;
    std::array<Json,2> modes;
    char hexInput[8]{};
    std::string hexKey;
    ULONGLONG copiedAt=0;
    bool copyFailed=false;
    RECT bounds{},copyBounds{},gradientBounds{},featherBounds{},densityBounds{};
    bool gradientDragging=false;
    float gradientDragOffset=0;
    void prepare(const Json& data) {
        available=false;dirty=false;bounds=copyBounds=gradientBounds=featherBounds=densityBounds={};gradientDragging=false;gradientDragOffset=0;channel=stop=0;modes={};hexInput[0]=0;hexKey.clear();copiedAt=0;copyFailed=false;
        if(!data.value("available",false))return;
        if(!data.at("revision").is_string() || !data.at("fill").is_object() || !data.at("stroke").is_object())return;
        original=draft=Json{{"revision",data.at("revision")},{"fill",data.at("fill")},{"stroke",data.at("stroke")}};
        patterns=data.value("patterns",Json::array());
        for(const auto& item:patterns)if(item.is_string())requireText(item.get<std::string>());
        for(int i=0;i<2;++i){const auto& p=draft.at(i?"stroke":"fill");modes[i]=Json::object();modes[i][p.at("kind").get<std::string>()]=p;}
        vector=data.value("vector",true);available=true;
        if(vector && data.contains("mask") && data["mask"].is_object())original["mask"]=draft["mask"]=data["mask"];
    }
    Json& current(){return draft.at(channel?"stroke":"fill");}
    bool ready() const {return available && holdMode && panelKind==2 && layerAware && layerKind==6 && layerCount==1
        && !layerLocked && !layerBackground && !inputFocused && canExecute() && !holdFinished;}
    void changed(){dirty=draft!=original;}
    void mode(int next) {
        const char* names[]={"solid","gradient","pattern"};
        auto& p=current();const std::string old=p.at("kind");modes[channel][old]=p;
        const bool enabled=p.value("enabled",true);const double width=p.value("width",1.);
        if(modes[channel].contains(names[next]))p=modes[channel][names[next]];
        else {
            Json color=p.contains("rgb")?p["rgb"]:p.contains("stops")?p["stops"][0]["rgb"]:Json::array({0,0,0});
            p=Json{{"kind",names[next]},{"enabled",enabled}};
            if(next==0)p["rgb"]=color;
            if(next==1)p["stops"]=Json::array({Json{{"rgb",color},{"location",0}},Json{{"rgb",Json::array({255,255,255})},{"location",4096}}});
            if(next==2)p["name"]=patterns.empty()?"":patterns[0].get<std::string>();
            if(channel)p["width"]=width;
        }
        stop=0;gradientDragging=false;changed();
    }
    bool valid() const {
        if(!available)return false;
        for(const char* name:{"fill","stroke"})if(draft.at(name).value("kind","")=="pattern" && draft.at(name).value("name","").empty())return false;
        return true;
    }
    bool hasMask() const {return vector && draft.contains("mask");}
};
static ShapeColorEditor shapeEditor;
static Json testedShapePaint;
static std::string testedCopiedHex;
static std::string shapeHex(const Json& rgb) {
    const char* digits="0123456789ABCDEF";std::string result="#";
    for(const auto& channel:rgb){const int value=std::clamp(int(std::lround(channel.get<double>())),0,255);result+=digits[value>>4];result+=digits[value&15];}
    return result;
}
static bool parseShapeHex(const std::string& text,Json& rgb) {
    const size_t start=text.size()==7 && text[0]=='#'?1:0;if(text.size()-start!=6)return false;
    int values[3]={};
    for(int i=0;i<6;++i){char c=text[start+i];int digit=c>='0' && c<='9'?c-'0':c>='a' && c<='f'?c-'a'+10:c>='A' && c<='F'?c-'A'+10:-1;
        if(digit<0)return false;values[i/2]=(values[i/2]<<4)|digit;}
    rgb=Json::array({values[0],values[1],values[2]});return true;
}
static void copyShapeHex(const Json& rgb) {
    const std::string value=shapeHex(rgb);
    if(selfTest)testedCopiedHex=value;
    else {
        ImGui::SetClipboardText(value.c_str());const char* readback=ImGui::GetClipboardText();
        if(!readback || value!=readback){shapeEditor.copyFailed=true;shapeEditor.copiedAt=0;return;}
    }
    shapeEditor.copyFailed=false;
    shapeEditor.copiedAt=GetTickCount64();
}
static void commitShapeDraft() {
    if(!shapeEditor.ready() || !shapeEditor.dirty || !shapeEditor.valid()){send("hide");return;}
    if(selfTest){testedActions.emplace_back("shape.paint");testedShapePaint=shapeEditor.draft;return;}
    if(backendParent)AllowSetForegroundWindow(backendParent);
    std::cout<<Json{{"type","action"},{"action","shape.paint"},{"session",menuEpoch},{"params",shapeEditor.draft}}.dump()<<std::endl;
}
static bool shapeSegment(const char* id,const std::vector<std::string>& names,int& selected,float width,bool lockSelection=false) {
    const ImVec2 start=ImGui::GetCursorScreenPos();const float height=menuControlHeight*scale,part=width/names.size();
    const float rounding=ImGui::GetStyle().FrameRounding;
    auto* draw=ImGui::GetWindowDrawList();bool changed=false;
    ImGui::PushID(id);
    for(int i=0;i<int(names.size());++i){
        ImGui::PushID(i);ImVec2 a={start.x+part*i,start.y},b={a.x+part,a.y+height};
        const bool disabled=lockSelection && selected!=i;
        ImGui::BeginDisabled(disabled);
        ImGui::SetCursorScreenPos(a);bool click=ImGui::InvisibleButton("segment",{part,height});
        const auto mouse=ImGui::GetIO().MousePos;
        bool divider=(i && mouse.x<a.x+scale) || (i+1<int(names.size()) && mouse.x>=b.x-scale);
        if(click && !divider && selected!=i){selected=i;changed=true;}
        auto color=ImGui::GetColorU32(selected==i?ImGuiCol_FrameBgActive:ImGui::IsItemHovered()?ImGuiCol_FrameBgHovered:ImGuiCol_FrameBg);
        ImDrawFlags corners=i==0?ImDrawFlags_RoundCornersLeft:i+1==int(names.size())?ImDrawFlags_RoundCornersRight:ImDrawFlags_RoundCornersNone;
        draw->AddRectFilled(a,b,color,rounding,corners);
        const auto size=ImGui::CalcTextSize(names[i].c_str());draw->AddText({a.x+(part-size.x)*.5f,a.y+(height-size.y)*.5f},ImGui::GetColorU32(ImGuiCol_Text),names[i].c_str());
        if(i)draw->AddLine(a,{a.x,b.y},ImGui::GetColorU32(ImGuiCol_Border),scale);
        ImGui::EndDisabled();
        ImGui::PopID();
    }
    draw->AddRect(start,{start.x+width,start.y+height},ImGui::GetColorU32(ImGuiCol_Border),rounding,0,scale);
    ImGui::PopID();ImGui::SetCursorScreenPos({start.x,start.y+height+menuPanelGap*scale});return changed;
}
static bool shapeEnabledControl(bool& enabled) {
    const auto at=ImGui::GetCursorScreenPos();const auto size=ImGui::CalcTextSize("启用");
    const float height=menuControlHeight*scale,box=menuCheckSize*scale,gap=menuControlPadding*scale;
    const bool click=ImGui::InvisibleButton("##enabled",{box+gap+size.x,height});auto* draw=ImGui::GetWindowDrawList();
    ImVec2 a={at.x,at.y+(height-box)*.5f},b={a.x+box,a.y+box};
    draw->AddRectFilled(a,b,ImGui::GetColorU32(ImGui::IsItemHovered()?ImGuiCol_FrameBgHovered:ImGuiCol_FrameBg),ImGui::GetStyle().FrameRounding);
    draw->AddRect(a,b,ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,scale);
    if(enabled)ImGui::RenderCheckMark(draw,{a.x+2*scale,a.y+2*scale},ImGui::GetColorU32(ImGuiCol_CheckMark),box-4*scale);
    draw->AddText({b.x+gap,at.y+(height-size.y)*.5f},ImGui::GetColorU32(ImGuiCol_Text),"启用");
    if(click)enabled=!enabled;return click;
}
static int gradientPosition(float x,float left,float width) {
    return width>0?std::clamp(int(std::lround((x-left)/width*4096.f)),0,4096):0;
}
static void moveGradientStop(int position) {
    auto& stops=shapeEditor.current().at("stops");const int index=shapeEditor.stop;
    const int low=index?stops[index-1].at("location").get<int>():0;
    const int high=index+1<int(stops.size())?stops[index+1].at("location").get<int>():4096;
    stops[index]["location"]=std::clamp(position,low,high);shapeEditor.changed();
}
static void drawGradientBar(float width) {
    auto& stops=shapeEditor.current().at("stops");
    shapeEditor.stop=std::clamp(shapeEditor.stop,0,int(stops.size())-1);
    const auto at=ImGui::GetCursorScreenPos();const float marker=menuGradientHandleSize*scale;
    const float left=at.x+marker*.5f,barWidth=width-marker,barHeight=menuGradientBarHeight*scale;
    const ImVec2 a={left,at.y},b={left+barWidth,at.y+barHeight};
    shapeEditor.gradientBounds={LONG(at.x),LONG(at.y),LONG(at.x+width),LONG(at.y+menuGradientEditorHeight*scale)};
    ImGui::InvisibleButton("##gradient-bar",{width,menuGradientEditorHeight*scale});
    const auto mouse=ImGui::GetIO().MousePos;const bool enabled=!(GImGui->LastItemData.ItemFlags&ImGuiItemFlags_Disabled);
    auto stopX=[&](int i){return left+stops[i].at("location").get<float>()/4096.f*barWidth;};
    if(enabled && ImGui::IsItemHovered() && ImGui::IsMouseClicked(ImGuiMouseButton_Left)){
        int nearest=shapeEditor.stop;float distance=std::abs(mouse.x-stopX(nearest));
        for(int i=0;i<int(stops.size());++i){const float d=std::abs(mouse.x-stopX(i));if(d<distance-.01f){nearest=i;distance=d;}}
        // Coincident stops remain independently selectable without reordering.
        if(distance<marker*.5f)for(int step=1;step<int(stops.size());++step){const int i=(shapeEditor.stop+step)%stops.size();
            if(std::abs(mouse.x-stopX(i))<=distance+.01f){nearest=i;break;}}
        shapeEditor.stop=nearest;
        shapeEditor.gradientDragging=mouse.y>=b.y && distance<=marker*.6f;
        shapeEditor.gradientDragOffset=mouse.x-stopX(nearest);
    }
    if(enabled && shapeEditor.gradientDragging && ImGui::IsItemActive() && ImGui::IsMouseDown(ImGuiMouseButton_Left))
        moveGradientStop(gradientPosition(mouse.x-shapeEditor.gradientDragOffset,left,barWidth));
    if(!enabled || !ImGui::IsMouseDown(ImGuiMouseButton_Left))shapeEditor.gradientDragging=false;
    auto* draw=ImGui::GetWindowDrawList();
    auto color=[&](int i){const auto& rgb=stops[i].at("rgb");return IM_COL32(int(rgb[0].get<double>()),int(rgb[1].get<double>()),int(rgb[2].get<double>()),255);};
    auto segment=[&](float x1,float x2,ImU32 c1,ImU32 c2){
        if(x2<=x1)return;
        ImDrawFlags corners=ImDrawFlags_RoundCornersNone;
        if(x1<=a.x+.01f)corners=ImDrawFlags_RoundCornersLeft;
        if(x2>=b.x-.01f)corners=corners==ImDrawFlags_RoundCornersNone?ImDrawFlags_RoundCornersRight:ImDrawFlags_RoundCornersAll;
        const int begin=draw->VtxBuffer.Size;
        draw->AddRectFilled({x1,a.y},{x2,b.y},IM_COL32_WHITE,ImGui::GetStyle().FrameRounding,corners);
        ImGui::ShadeVertsLinearColorGradientKeepAlpha(draw,begin,draw->VtxBuffer.Size,{x1,a.y},{x2,a.y},c1,c2);
    };
    segment(a.x,stopX(0),color(0),color(0));
    for(int i=0;i+1<int(stops.size());++i)segment(stopX(i),stopX(i+1),color(i),color(i+1));
    segment(stopX(int(stops.size())-1),b.x,color(int(stops.size())-1),color(int(stops.size())-1));
    draw->AddRect(a,b,ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,scale);
    auto handle=[&](int i){
        const float x=stopX(i),y=b.y+menuCompactGap*scale;
        const ImVec2 points[]={{x,y},{x+marker*.5f,y+marker*.35f},{x+marker*.5f,y+marker},{x-marker*.5f,y+marker},{x-marker*.5f,y+marker*.35f}};
        draw->AddConvexPolyFilled(points,5,color(i));
        draw->AddPolyline(points,5,ImGui::GetColorU32(i==shapeEditor.stop?ImGuiCol_CheckMark:ImGuiCol_Text),ImDrawFlags_Closed,(i==shapeEditor.stop?2.f:1.f)*scale);
    };
    for(int i=0;i<int(stops.size());++i)if(i!=shapeEditor.stop)handle(i);handle(shapeEditor.stop);
    ImGui::SetCursorScreenPos({at.x,at.y+menuGradientEditorHeight*scale+menuPanelGap*scale});
}
static void drawShapeEditor() {
    shapeEditor.bounds=shapeEditor.copyBounds=shapeEditor.gradientBounds=shapeEditor.featherBounds=shapeEditor.densityBounds={};if(!shapeEditor.ready())return;
    const auto windowPos=ImGui::GetWindowPos(),windowSize=ImGui::GetWindowSize();
    const float available=pieCenter.x-windowPos.x-65*scale-basicLabelExtent(0).x-basicTextOffset()-figmaBasicRightPadding*scale-30*scale;
    if(available<140*scale)return;
    auto* panelFont=menuFonts[0]?menuFonts[0]:ImGui::GetFont();
    const float width=std::min(menuPanelWidth*scale,available),gap=menuPanelGap*scale;
    const float row=menuControlHeight*scale+gap,textLine=panelFont->FontSize+gap;
    const auto kind=shapeEditor.current().value("kind",std::string("solid"));
    const float content=2*menuControlPadding*scale+textLine+2*row+(shapeEditor.vector?row:0)+
        (kind=="pattern"?row:textLine+width-2*menuControlPadding*scale+2*row+(kind=="gradient"?menuGradientEditorHeight*scale+gap:0))+(shapeEditor.vector?row:0)+(shapeEditor.hasMask()?2*row:0);
    const float height=std::min(content,windowSize.y-24*scale);
    ImVec2 at={std::max(windowPos.x+16*scale,pieCenter.x-65*scale-basicLabelExtent(0).x-basicTextOffset()-figmaBasicRightPadding*scale-30*scale-width),std::max(windowPos.y+12*scale,pieCenter.y-238*scale)};
    at.y=std::max(windowPos.y+12*scale,std::min(at.y,windowPos.y+windowSize.y-height-12*scale));
    shapeEditor.bounds={LONG(at.x),LONG(at.y),LONG(at.x+width),LONG(at.y+height)};
    const auto saved=ImGui::GetCursorScreenPos();ImGui::SetCursorScreenPos(at);
    ImGui::PushStyleColor(ImGuiCol_ChildBg,ImGui::GetStyle().Colors[ImGuiCol_WindowBg]);
    ImGui::PushStyleVar(ImGuiStyleVar_ChildRounding,ImGui::GetStyle().FrameRounding);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,{menuControlPadding*scale,menuControlPadding*scale});
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,{gap,gap});
    ImGui::PushStyleVar(ImGuiStyleVar_ItemInnerSpacing,{gap,gap});
    const float controlTextSize=panelFont->FontSize;
    ImGui::PushFont(panelFont);
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding,{menuControlTextInset*scale,std::max(0.f,(menuControlHeight*scale-controlTextSize)*.5f)});
    ImGui::PushStyleVar(ImGuiStyleVar_FrameBorderSize,scale);
    ImGui::BeginChild("shape-color",{width,height},ImGuiChildFlags_Borders,ImGuiWindowFlags_NoScrollbar|ImGuiWindowFlags_NoScrollWithMouse);
    ImGui::SetWindowFontScale(1.f);
    if(selfTest && std::abs(ImGui::GetFontSize()-controlTextSize)>.01f)
        throw std::runtime_error("Shape controls must share the menu panel body font");
    ImGui::BeginDisabled(pieAnimating);
    ImGui::TextUnformatted(shapeEditor.vector?"形状颜色":"填充颜色");float inner=ImGui::GetContentRegionAvail().x;
    if(!shapeEditor.vector)shapeEditor.channel=0;
    if(shapeSegment("channel",shapeEditor.vector?std::vector<std::string>{"填充","描边"}:std::vector<std::string>{"填充"},shapeEditor.channel,inner)){shapeEditor.stop=0;shapeEditor.gradientDragging=false;}
    auto& p=shapeEditor.current();std::string paintKind=p.at("kind");int mode=paintKind=="solid"?0:paintKind=="gradient"?1:2;
    if(shapeEditor.vector && ImGui::IsKeyPressed(ImGuiKey_Tab,false) && !ImGui::GetIO().KeyCtrl && !ImGui::GetIO().KeyAlt){
        mode=(mode+(ImGui::GetIO().KeyShift?2:1))%3;shapeEditor.mode(mode);
        ImGui::SetKeyOwner(ImGuiKey_Tab,ImGui::GetID("shape-kind"),ImGuiInputFlags_LockThisFrame);
    }
    if(shapeSegment("kind",{"纯色","渐变","图案"},mode,inner,!shapeEditor.vector))shapeEditor.mode(mode);
    paintKind=p.at("kind");bool enabled=p.value("enabled",true);
    if(shapeEditor.vector && shapeEnabledControl(enabled)){p["enabled"]=enabled;shapeEditor.changed();}
    if(shapeEditor.channel){ImGui::SameLine();float strokeWidth=p.value("width",1.f);ImGui::SetNextItemWidth(std::max(55*scale,inner-65*scale));
        if(ImGui::DragFloat("px",&strokeWidth,.25f,0.f,1000.f,"%.2f")){p["width"]=strokeWidth;shapeEditor.changed();}}
    if(paintKind=="pattern"){
        std::string name=p.value("name","");ImGui::SetNextItemWidth(inner);
        if(ImGui::BeginCombo("##pattern",name.empty()?"选择图案":name.c_str())){
            for(const auto& item:shapeEditor.patterns){const std::string value=item;
                if(ImGui::Selectable(value.c_str(),value==name)){p["name"]=value;p["enabled"]=true;shapeEditor.changed();}}
            ImGui::EndCombo();
        }
        if(shapeEditor.patterns.empty())ImGui::TextWrapped("没有已加载的图案预设");
    } else {
        if(paintKind=="gradient"){
            drawGradientBar(inner);
        }
        Json& c=paintKind=="solid"?p["rgb"]:p["stops"][shapeEditor.stop]["rgb"];
        float color[]={c[0].get<float>()/255,c[1].get<float>()/255,c[2].get<float>()/255,1};
        ImGui::TextUnformatted("RGB");
        const float reserve=((shapeEditor.vector?3:2)+(shapeEditor.hasMask()?2:0))*ImGui::GetFrameHeightWithSpacing()+gap;
        ImGui::SetNextItemWidth(std::min(inner,std::max(90*scale,ImGui::GetContentRegionAvail().y-reserve)));
        if(ImGui::ColorPicker4("##paint",color,ImGuiColorEditFlags_NoAlpha|ImGuiColorEditFlags_NoSidePreview|ImGuiColorEditFlags_NoSmallPreview|
            ImGuiColorEditFlags_NoOptions|ImGuiColorEditFlags_NoDragDrop|ImGuiColorEditFlags_PickerHueBar|ImGuiColorEditFlags_DisplayRGB|ImGuiColorEditFlags_Uint8)){
            c=Json::array({int(std::lround(std::clamp(color[0],0.f,1.f)*255)),int(std::lround(std::clamp(color[1],0.f,1.f)*255)),int(std::lround(std::clamp(color[2],0.f,1.f)*255))});p["enabled"]=true;shapeEditor.changed();}
        const std::string hexKey=std::to_string(shapeEditor.channel)+paintKind+std::to_string(shapeEditor.stop);
        const ImGuiID hexId=ImGui::GetID("##hex");
        if(shapeEditor.hexKey!=hexKey){if(ImGui::GetActiveID()==hexId)ImGui::ClearActiveID();shapeEditor.hexKey=hexKey;}
        if(ImGui::GetActiveID()!=hexId){const auto value=shapeHex(c);std::copy(value.begin(),value.end(),shapeEditor.hexInput);shapeEditor.hexInput[7]=0;}
        const float copyWidth=ImGui::CalcTextSize("已复制").x+2*menuControlPadding*scale;
        ImGui::SetNextItemWidth(inner-copyWidth-gap);
        if(ImGui::InputText("##hex",shapeEditor.hexInput,sizeof(shapeEditor.hexInput),ImGuiInputTextFlags_CharsUppercase|ImGuiInputTextFlags_CharsNoBlank)){
            Json parsed;if(parseShapeHex(shapeEditor.hexInput,parsed)){c=parsed;p["enabled"]=true;shapeEditor.changed();}}
        ImGui::SameLine(0,gap);Json parsed;
        ImGui::BeginDisabled(!parseShapeHex(shapeEditor.hexInput,parsed));
        const bool copied=shapeEditor.copiedAt && GetTickCount64()-shapeEditor.copiedAt<900;
        if(ImGui::Button(copied?"已复制###copy-hex":"复制###copy-hex",{copyWidth,menuControlHeight*scale}))copyShapeHex(c);
        const auto ca=ImGui::GetItemRectMin(),cb=ImGui::GetItemRectMax();
        shapeEditor.copyBounds={LONG(ca.x),LONG(ca.y),LONG(cb.x),LONG(cb.y)};
        ImGui::EndDisabled();
        int quickColor=-1;
        if(shapeSegment("quick-color",{"黑色","白色"},quickColor,inner)){
            c=quickColor?Json::array({255,255,255}):Json::array({0,0,0});p["enabled"]=true;shapeEditor.changed();}
    }
    if(shapeEditor.vector && ImGui::Button("交换填充与描边",{inner,0})){
        const double widthValue=shapeEditor.draft["stroke"].value("width",1.);
        Json fill=shapeEditor.draft["fill"],stroke=shapeEditor.draft["stroke"];stroke.erase("width");
        fill["width"]=widthValue;shapeEditor.draft["fill"]=stroke;shapeEditor.draft["stroke"]=fill;
        shapeEditor.modes={};for(int i=0;i<2;++i){const auto& v=shapeEditor.draft[i?"stroke":"fill"];shapeEditor.modes[i]=Json::object();shapeEditor.modes[i][v.at("kind").get<std::string>()]=v;}
        shapeEditor.stop=0;shapeEditor.changed();
    }
    if(shapeEditor.hasMask()) {
        const float labelWidth=std::max(ImGui::CalcTextSize("羽化").x,ImGui::CalcTextSize("密度").x);
        auto slider=[&](const char* label,const char* id,const char* key,float maximum,const char* format,ImGuiSliderFlags flags,RECT& bounds){
            const auto at=ImGui::GetCursorScreenPos();
            ImGui::AlignTextToFramePadding();ImGui::TextUnformatted(label);
            ImGui::SameLine();ImGui::SetCursorScreenPos({at.x+labelWidth+gap,at.y});
            float value=shapeEditor.draft["mask"][key].get<float>();ImGui::SetNextItemWidth(inner-labelWidth-gap);
            if(ImGui::SliderFloat(id,&value,0.f,maximum,format,flags|ImGuiSliderFlags_AlwaysClamp)){shapeEditor.draft["mask"][key]=value;shapeEditor.changed();}
            const auto a=ImGui::GetItemRectMin(),b=ImGui::GetItemRectMax();bounds={LONG(a.x),LONG(a.y),LONG(b.x),LONG(b.y)};
        };
        slider("羽化","##mask-feather","feather",1000.f,"%.1f px",ImGuiSliderFlags_Logarithmic,shapeEditor.featherBounds);
        slider("密度","##mask-density","density",100.f,"%.1f%%",ImGuiSliderFlags_None,shapeEditor.densityBounds);
    }
    ImGui::EndDisabled();ImGui::EndChild();ImGui::PopStyleVar(6);ImGui::PopFont();ImGui::PopStyleColor();ImGui::SetCursorScreenPos(saved);
}
