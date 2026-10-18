// Included after shared shape controls; no host calls, no runtime assets.
struct PerceptualPickerState {
    perceptual::Color base{},last{};
    std::string key;int rule=-1,active=0,drag=-1;
    double cachedLightness=-1;
    std::array<ImU32,49*9> mesh{};
    RECT wheelBounds{},lightnessBounds{};std::array<ImVec2,3> points{};
    size_t meshBuilds=0;
    static perceptual::Color color(const Json& rgb){return {rgb[0].get<double>(),rgb[1].get<double>(),rgb[2].get<double>()};}
    static ImU32 ink(perceptual::Color c){return IM_COL32(int(std::lround(c[0])),int(std::lround(c[1])),int(std::lround(c[2])),255);}
    void reset(const Json& rgb,const std::string& identity,int nextRule){
        auto current=color(rgb);
        if(key!=identity || current!=last || rule!=nextRule){base=perceptual::lch(current,base[2]);key=identity;last=current;rule=nextRule;active=0;drag=-1;}
    }
    bool apply(Json& rgb){auto value=perceptual::role(base,rule,active);for(auto& c:value)c=std::round(c);last=value;if(color(rgb)==value)return false;rgb=value;return true;}
    void dragPoint(double angle,double fraction,int index){
        active=index;const auto offsets=perceptual::offsets(rule);
        base[2]=perceptual::hue(angle-offsets[index]);
        const double light=rule==4 && index?(base[0]>.6?.35:.8):base[0];
        base[1]=perceptual::maxChroma(light,angle)*std::clamp(fraction,0.,1.)/(rule==4 && index?1.15:1.);
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
    const float gap=menuPanelGap*scale,bar=menuControlHeight*scale,side=std::max(50*scale,width-bar-gap),radius=side*.5f-7*scale;
    const ImVec2 center={at.x+side*.5f,at.y+side*.5f};
    const auto identity=std::to_string(menuEpoch)+":"+std::to_string(shapeEditor.channel)+":"+std::to_string(shapeEditor.stop);
    state.reset(rgb,identity,shapeEditor.harmonyRule);bool changed=false;
    auto offsets=perceptual::offsets(state.rule);
    auto point=[&](int i){auto value=perceptual::lch(perceptual::role(state.base,state.rule,i),state.base[2]+offsets[i]);
        const double max=perceptual::maxChroma(value[0],value[2]);const float r=radius*std::clamp(max>1e-6?value[1]/max:0.,0.,1.);
        return ImVec2{center.x+r*float(std::cos(value[2]*perceptual::pi/180)),center.y+r*float(std::sin(value[2]*perceptual::pi/180))};};
    ImGui::InvisibleButton("##perceptual-wheel",{side,side});shapeItemTip(23);
    state.wheelBounds={LONG(at.x),LONG(at.y),LONG(at.x+side),LONG(at.y+side)};
    if(ImGui::IsItemHovered() && ImGui::IsMouseClicked(0)){
        auto mouse=ImGui::GetIO().MousePos;float dx=mouse.x-center.x,dy=mouse.y-center.y;
        state.drag=std::hypot(dx,dy)<=radius+6*scale?0:-1;float nearest=12*scale;
        for(int i=0;i<int(offsets.size());++i){auto p=point(i);float d=std::hypot(mouse.x-p.x,mouse.y-p.y);if(d<nearest){state.drag=i;nearest=d;}}
    }
    if(ImGui::IsItemActive() && ImGui::IsMouseDown(0) && state.drag>=0){
        auto m=ImGui::GetIO().MousePos;double x=m.x-center.x,y=m.y-center.y;
        state.dragPoint(perceptual::hue(std::atan2(y,x)*180/perceptual::pi),std::hypot(x,y)/radius,state.drag);changed|=state.apply(rgb);
    }
    if(!ImGui::IsMouseDown(0))state.drag=-1;
    state.cache();
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
    for(int i=0;i<int(offsets.size());++i){state.points[i]=point(i);if(i)draw->AddLine(point(0),state.points[i],ImGui::GetColorU32(ImGuiCol_Border),scale);}
    for(int i=0;i<int(offsets.size());++i){auto p=point(i);draw->AddCircleFilled(p,5*scale,State::ink(perceptual::role(state.base,state.rule,i)));}
    // Separate outlines retain visibility on both light and dark colors.
    for(int i=0;i<int(offsets.size());++i){auto p=point(i);draw->AddCircle(p,5*scale,IM_COL32(0,0,0,220),20,2*scale);draw->AddCircle(p,6*scale,IM_COL32(255,255,255,240),20,(i==state.active?2.f:1.f)*scale);}
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
    const float swatchWidth=width/offsets.size(),height=menuControlHeight*scale;const auto swatchAt=ImGui::GetCursorScreenPos();
    for(int i=0;i<int(offsets.size());++i){ImGui::PushID(i);ImGui::SetCursorScreenPos({at.x+i*swatchWidth,swatchAt.y});
        if(ImGui::InvisibleButton("##harmony-color",{swatchWidth,height})){state.active=i;changed|=state.apply(rgb);}shapeItemTip(23);
        draw->AddRectFilled({at.x+i*swatchWidth,swatchAt.y},{at.x+(i+1)*swatchWidth,swatchAt.y+height},State::ink(perceptual::role(state.base,state.rule,i)),ImGui::GetStyle().FrameRounding,
            i==0?ImDrawFlags_RoundCornersLeft:i+1==int(offsets.size())?ImDrawFlags_RoundCornersRight:ImDrawFlags_RoundCornersNone);
        if(i==state.active)draw->AddRect({at.x+i*swatchWidth+scale,swatchAt.y+scale},{at.x+(i+1)*swatchWidth-scale,swatchAt.y+height-scale},IM_COL32_WHITE,0,0,2*scale);
        if(i)draw->AddLine({at.x+i*swatchWidth,swatchAt.y},{at.x+i*swatchWidth,swatchAt.y+height},ImGui::GetColorU32(ImGuiCol_Border),scale);ImGui::PopID();}
    draw->AddRect(swatchAt,{at.x+width,swatchAt.y+height},ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,scale);
    ImGui::SetCursorScreenPos({at.x,swatchAt.y+height+gap});return changed;
}
