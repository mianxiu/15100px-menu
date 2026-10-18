// Included after shared shape controls; no host calls, no runtime assets.
struct PerceptualPickerState {
    perceptual::Color base{},last{},layoutBase{};
    std::string key;int active=0,drag=-1;
    double cachedLightness=-1;
    std::array<ImU32,49*9> mesh{};
    RECT wheelBounds{},lightnessBounds{};
    std::array<ImVec2,perceptual::wheelCount> points{},rawPoints{};
    ImVec2 layoutCenter{},dragOffset{},dragStart{},dragLast{};
    float layoutRadius=-1,layoutScale=-1;
    bool dragHandle=false;
    size_t meshBuilds=0,layoutBuilds=0;
    static perceptual::Color color(const Json& rgb){return {rgb[0].get<double>(),rgb[1].get<double>(),rgb[2].get<double>()};}
    static ImU32 ink(perceptual::Color c){return IM_COL32(int(std::lround(c[0])),int(std::lround(c[1])),int(std::lround(c[2])),255);}
    static float markerRadius(int index){return index==0?9.f:4.5f;}
    void reset(const Json& rgb,const std::string& identity){
        auto current=color(rgb);
        if(key!=identity || current!=last){base=perceptual::lch(current,base[2]);key=identity;last=current;active=0;drag=-1;layoutRadius=-1;}
    }
    bool apply(Json& rgb){
        auto value=perceptual::wheelColor(base,active);for(auto& c:value)c=std::round(c);
        const auto previous=color(rgb);bool equal=true;for(int i=0;i<3;++i)equal&=std::abs(value[i]-previous[i])<.001;
        if(equal){last=previous;return false;}last=value;rgb=value;return true;
    }
    void dragPoint(double angle,double fraction,int index){
        active=index;base[2]=perceptual::hue(angle-perceptual::wheelOffsets[index]);
        const double light=index==8?(base[0]>.6?.35:.8):base[0];
        base[1]=perceptual::maxChroma(light,angle)*std::clamp(fraction,0.,1.)/(index==8?1.15:1.);
    }
    // Only visual handles move to avoid overlap; colors keep their true anchors.
    // Pickup offsets below preserve the original color until the pointer moves.
    void layout(ImVec2 center,float radius,float uiScale){
        if(layoutBase==base && layoutCenter.x==center.x && layoutCenter.y==center.y && layoutRadius==radius && layoutScale==uiScale)return;
        layoutBase=base;layoutCenter=center;layoutRadius=radius;layoutScale=uiScale;++layoutBuilds;
        auto square=[](float n){return n*n;};
        for(int i=0;i<perceptual::wheelCount;++i){
            const double angle=(base[2]+perceptual::wheelOffsets[i])*perceptual::pi/180;
            auto value=perceptual::lch(perceptual::wheelColor(base,i),perceptual::hue(base[2]+perceptual::wheelOffsets[i]));
            double max=perceptual::maxChroma(value[0],value[2]);const float r=radius*std::clamp(max>1e-6?value[1]/max:0.,0.,1.);
            rawPoints[i]={center.x+r*float(std::cos(angle)),center.y+r*float(std::sin(angle))};points[i]=rawPoints[i];if(!i)continue;
            auto clear=[&](ImVec2 p){
                if(square(p.x-center.x)+square(p.y-center.y)>square(radius)+.1f)return false;
                for(int j=0;j<i;++j){const float gap=(markerRadius(i)+markerRadius(j)+4)*uiScale;
                    if(square(p.x-points[j].x)+square(p.y-points[j].y)<square(gap))return false;}
                return true;
            };
            if(clear(points[i]))continue;bool found=false;
            for(int step=1;step<=28 && !found;++step)for(int direction=0;direction<24;++direction){
                double a=angle+direction*2*perceptual::pi/24;float distance=step*3*uiScale;
                ImVec2 candidate={rawPoints[i].x+distance*float(std::cos(a)),rawPoints[i].y+distance*float(std::sin(a))};
                if(clear(candidate)){points[i]=candidate;found=true;break;}
            }
        }
    }
    int hit(ImVec2 mouse,float uiScale) const {
        for(int i=0;i<perceptual::wheelCount;++i)if(std::hypot(mouse.x-points[i].x,mouse.y-points[i].y)<=(markerRadius(i)+2)*uiScale)return i;
        return -1;
    }
    void cache(){
        if(std::abs(cachedLightness-base[0])<.0001)return;
        cachedLightness=base[0];++meshBuilds;
        for(int a=0;a<=48;++a){double h=a*360./48,c=perceptual::maxChroma(base[0],h);
            for(int ring=0;ring<=8;++ring)mesh[a*9+ring]=ink(perceptual::fromLch(base[0],c*ring/8,h));}
    }
};
static PerceptualPickerState perceptualPicker;
static bool drawPerceptualPicker(Json& rgb,float width) {
    using State=PerceptualPickerState;
    auto& state=perceptualPicker;const auto at=ImGui::GetCursorScreenPos();auto* draw=ImGui::GetWindowDrawList();
    const float gap=menuPanelGap*scale,bar=menuControlHeight*scale,side=std::max(50*scale,width-bar-gap),radius=side*.5f-12*scale;
    const ImVec2 center={at.x+side*.5f,at.y+side*.5f};
    const auto identity=std::to_string(menuEpoch)+":"+std::to_string(shapeEditor.channel)+":"+std::to_string(shapeEditor.stop);
    state.reset(rgb,identity);state.layout(center,radius,scale);bool changed=false;
    ImGui::InvisibleButton("##perceptual-wheel",{side,side});shapeItemTip(23);
    state.wheelBounds={LONG(at.x),LONG(at.y),LONG(at.x+side),LONG(at.y+side)};
    const auto mouse=ImGui::GetIO().MousePos;
    const int hovered=ImGui::IsItemHovered()?state.hit(mouse,scale):-1;
    if(hovered>=0 && !ImGui::IsItemActive()){
        const auto p=state.points[hovered];const float hit=(State::markerRadius(hovered)+2)*scale;
        shapeTipRows[25+hovered]={LONG(p.x-hit),LONG(p.y-hit),LONG(p.x+hit),LONG(p.y+hit)};shapeTipCandidate=225+hovered;
    }
    if(ImGui::IsItemHovered() && ImGui::IsMouseClicked(0)){
        state.dragHandle=hovered>=0;state.drag=hovered>=0?hovered:std::hypot(mouse.x-center.x,mouse.y-center.y)<=radius?0:-1;
        state.dragStart=mouse;state.dragLast={-FLT_MAX,-FLT_MAX};state.dragOffset=hovered>=0?ImVec2{mouse.x-state.rawPoints[hovered].x,mouse.y-state.rawPoints[hovered].y}:ImVec2{};
        if(hovered>=0 && state.active!=hovered){state.active=hovered;changed|=state.apply(rgb);}
    }
    if(ImGui::IsItemActive() && ImGui::IsMouseDown(0) && state.drag>=0 && (mouse.x!=state.dragLast.x || mouse.y!=state.dragLast.y) &&
       (!state.dragHandle || std::hypot(mouse.x-state.dragStart.x,mouse.y-state.dragStart.y)>.5f)){
        state.dragLast=mouse;double x=mouse.x-state.dragOffset.x-center.x,y=mouse.y-state.dragOffset.y-center.y;
        state.dragPoint(perceptual::hue(std::atan2(y,x)*180/perceptual::pi),std::hypot(x,y)/radius,state.drag);changed|=state.apply(rgb);
    }
    if(!ImGui::IsMouseDown(0))state.drag=-1;
    state.cache();state.layout(center,radius,scale);
    auto vertex=[&](int a,int ring){double h=a*2*perceptual::pi/48,r=radius*ring/8;return ImVec2{center.x+float(r*std::cos(h)),center.y+float(r*std::sin(h))};};
    const auto uv=ImGui::GetFontTexUvWhitePixel();
    for(int a=0;a<48;++a)for(int ring=0;ring<8;++ring){
        const ImVec2 p[]={vertex(a,ring),vertex(a+1,ring),vertex(a+1,ring+1),vertex(a,ring+1)};
        const ImU32 colors[]={state.mesh[a*9+ring],state.mesh[(a+1)*9+ring],state.mesh[(a+1)*9+ring+1],state.mesh[a*9+ring+1]};
        draw->PrimReserve(6,4);auto index=draw->_VtxCurrentIdx;
        draw->PrimWriteIdx(index);draw->PrimWriteIdx(index+1);draw->PrimWriteIdx(index+2);draw->PrimWriteIdx(index);draw->PrimWriteIdx(index+2);draw->PrimWriteIdx(index+3);
        for(int n=0;n<4;++n)draw->PrimWriteVtx(p[n],uv,colors[n]);
    }
    draw->AddCircle(center,radius,ImGui::GetColorU32(ImGuiCol_Border),64,scale);
    for(int i=1;i<perceptual::wheelCount;++i){auto p=state.points[i],anchor=state.rawPoints[i];
        if(i==state.active || i==hovered)draw->AddLine(state.points[0],p,ImGui::GetColorU32(ImGuiCol_Border),scale);
        if(std::hypot(p.x-anchor.x,p.y-anchor.y)>scale){draw->AddLine(anchor,p,ImGui::GetColorU32(ImGuiCol_Border),scale);draw->AddCircleFilled(anchor,scale,ImGui::GetColorU32(ImGuiCol_TextDisabled));}}
    auto marker=[&](int i){const auto p=state.points[i];const float r=State::markerRadius(i)*scale;
        draw->AddCircleFilled(p,r,State::ink(perceptual::wheelColor(state.base,i)));
        draw->AddCircle(p,r,IM_COL32(0,0,0,220),24,2*scale);draw->AddCircle(p,r+scale,IM_COL32(255,255,255,240),24,scale);
        if(i==state.active)draw->AddCircle(p,r+2*scale,ImGui::GetColorU32(ImGuiCol_CheckMark),24,scale);};
    for(int i=1;i<perceptual::wheelCount;++i)marker(i);marker(0);
    const ImVec2 lightAt={at.x+side+gap,at.y};ImGui::SetCursorScreenPos(lightAt);
    ImGui::InvisibleButton("##perceptual-lightness",{bar,side});shapeItemTip(24);
    state.lightnessBounds={LONG(lightAt.x),LONG(lightAt.y),LONG(lightAt.x+bar),LONG(lightAt.y+side)};
    if(ImGui::IsItemActive() && ImGui::IsMouseDown(0)){
        state.base[0]=std::clamp(1.-(ImGui::GetIO().MousePos.y-at.y)/side,0.,1.);state.active=0;changed|=state.apply(rgb);
    }
    for(int n=0;n<32;++n){double l1=1.-n/32.,l2=1.-(n+1)/32.;
        auto c1=State::ink(perceptual::fromLch(l1,state.base[1],state.base[2])),c2=State::ink(perceptual::fromLch(l2,state.base[1],state.base[2]));
        draw->AddRectFilledMultiColor({lightAt.x,at.y+side*n/32},{lightAt.x+bar,at.y+side*(n+1)/32},c1,c1,c2,c2);}
    draw->AddRect(lightAt,{lightAt.x+bar,at.y+side},ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,scale);
    const float y=at.y+float(1-state.base[0])*side;draw->AddLine({lightAt.x,y},{lightAt.x+bar,y},IM_COL32_WHITE,2*scale);
    ImGui::SetCursorScreenPos({at.x,at.y+side+gap});
    return changed;
}
