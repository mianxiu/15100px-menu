// Included after shared shape controls; no host calls, no runtime assets.
#include "HarmonyMarkers.h"
struct PerceptualPickerState {
    perceptual::Color base{},last{},layoutBase{};
    std::string key;int active=0,drag=-1;
    double cachedLightness=-1;
    std::array<ImU32,193> mesh{};
    RECT wheelBounds{},lightnessBounds{},squareBounds{};
    float svHue=0;
    std::array<ImVec2,perceptual::wheelCount> points{},rawPoints{};
    ImVec2 layoutCenter{},dragOffset{},dragStart{},dragLast{};
    float layoutRadius=-1,layoutScale=-1;
    bool dragHandle=false;
    size_t meshBuilds=0,layoutBuilds=0;
    static perceptual::Color color(const Json& rgb){return {rgb[0].get<double>(),rgb[1].get<double>(),rgb[2].get<double>()};}
    static ImU32 ink(perceptual::Color c){return IM_COL32(int(std::lround(c[0])),int(std::lround(c[1])),int(std::lround(c[2])),255);}
    static float markerRadius(int index){return index==0?9.f:4.5f;}
    static const HarmonyMarkerGeometry& geometry(int index){return harmonyMarkers[harmonyMarkerRoles[index]];}
    static float markerExtent(int index){return geometry(index).extent*markerRadius(index)/4.5f;}
    static bool markerHit(int index,ImVec2 at,ImVec2 mouse,float uiScale){
        const auto& g=geometry(index);const float unit=markerRadius(index)*uiScale/4.5f;
        const float x=(mouse.x-at.x)/unit+4.5f,y=(mouse.y-at.y)/unit+4.5f,padding=2.5f*uiScale/unit;
        bool inside=false;
        for(int i=0,j=g.count-1;i<g.count;j=i++){
            const auto a=g.points[j],b=g.points[i];
            if((a.y>y)!=(b.y>y) && x<(b.x-a.x)*(y-a.y)/(b.y-a.y)+a.x)inside=!inside;
            const float dx=b.x-a.x,dy=b.y-a.y,t=std::clamp(((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy),0.f,1.f);
            if(std::hypot(x-a.x-t*dx,y-a.y-t*dy)<=padding)return true;
        }
        return inside;
    }
    static void drawMarker(ImDrawList* draw,int index,ImVec2 at,float uiScale,ImU32 color,bool selected){
        const auto& g=geometry(index);const float unit=markerRadius(index)*uiScale/4.5f;
        std::array<ImVec2,32> vertices{};
        for(int i=0;i<g.count;++i)vertices[i]={at.x+(g.points[i].x-4.5f)*unit,at.y+(g.points[i].y-4.5f)*unit};
        // Outer strokes sit outside the real color. The same polygon drives hits.
        if(selected)draw->AddPolyline(vertices.data(),g.count,ImGui::GetColorU32(ImGuiCol_CheckMark),ImDrawFlags_Closed,5*uiScale);
        draw->AddPolyline(vertices.data(),g.count,IM_COL32(255,255,255,240),ImDrawFlags_Closed,3*uiScale);
        draw->AddPolyline(vertices.data(),g.count,IM_COL32(0,0,0,230),ImDrawFlags_Closed,uiScale);
        if(index==8)draw->AddConcavePolyFilled(vertices.data(),g.count,color);
        else draw->AddConvexPolyFilled(vertices.data(),g.count,color);
    }
    void reset(const Json& rgb,const std::string& identity){
        auto current=color(rgb);
        if(key!=identity || current!=last){base=perceptual::lch(current,base[2]);key=identity;last=current;active=0;drag=-1;layoutRadius=-1;}
    }
    bool apply(Json& rgb){
        auto value=perceptual::wheelColor(base,active);for(auto& c:value)c=std::round(c);
        const auto previous=color(rgb);bool equal=true;for(int i=0;i<3;++i)equal&=std::abs(value[i]-previous[i])<.001;
        if(equal){last=previous;return false;}last=value;rgb=value;return true;
    }
    void dragPoint(double angle,double /*fraction*/,int index){
        active=index;base[2]=perceptual::hue(angle-perceptual::wheelOffsets[index]);
    }
    static ImVec2 railPoint(ImVec2 center,float radius,double degrees,float rounding){
        double angle=degrees*perceptual::pi/180,x=std::cos(angle),y=std::sin(angle);
        double t=radius/std::max(std::abs(x),std::abs(y)),corner=std::max(0.f,radius-rounding);
        if(std::abs(t*x)>corner && std::abs(t*y)>corner){
            double dot=corner*(std::abs(x)+std::abs(y));
            t=dot+std::sqrt(std::max(0.,dot*dot-2*corner*corner+rounding*rounding));
        }
        return {center.x+float(t*x),center.y+float(t*y)};
    }
    // Independent rounded-square rail. Relocated handles retain true hue anchors.
    void layout(ImVec2 center,float radius,float uiScale){
        if(layoutBase==base && layoutCenter.x==center.x && layoutCenter.y==center.y && layoutRadius==radius && layoutScale==uiScale)return;
        layoutBase=base;layoutCenter=center;layoutRadius=radius;layoutScale=uiScale;++layoutBuilds;
        for(int i=0;i<perceptual::wheelCount;++i){
            const double angle=base[2]+perceptual::wheelOffsets[i];
            rawPoints[i]=railPoint(center,radius,angle,12*uiScale);points[i]=rawPoints[i];
            auto clear=[&](ImVec2 p){for(int j=0;j<i;++j){
                const float gap=(markerExtent(i)+markerExtent(j)+5.5f)*uiScale;
                if(std::hypot(p.x-points[j].x,p.y-points[j].y)<gap)return false;}return true;};
            if(clear(points[i]))continue;bool found=false;
            for(int step=1;step<=180 && !found;++step)for(int sign:{1,-1}){
                auto candidate=railPoint(center,radius,angle+step*sign,12*uiScale);
                if(clear(candidate)){points[i]=candidate;found=true;break;}
            }
        }
    }
    int hit(ImVec2 mouse,float uiScale) const {
        for(int i=0;i<perceptual::wheelCount;++i)if(markerHit(i,points[i],mouse,uiScale))return i;
        return -1;
    }
    void cache(){
        if(cachedLightness==.72)return;
        cachedLightness=.72;++meshBuilds;
        for(int a=0;a<=192;++a)mesh[a]=ink(perceptual::fromLch(.72,.18,a*360./192));
    }
};
static PerceptualPickerState perceptualPicker;
static bool drawPerceptualPicker(Json& rgb,float width) {
    using State=PerceptualPickerState;
    auto& state=perceptualPicker;const auto at=ImGui::GetCursorScreenPos();auto* draw=ImGui::GetWindowDrawList();
    const float gap=menuPanelGap*scale,side=std::max(50*scale,width),radius=side*.5f-12*scale,half=std::max(1.f,radius-15*scale);
    const ImVec2 center={at.x+side*.5f,at.y+side*.5f},lo={center.x-half,center.y-half},hi={center.x+half,center.y+half};
    const auto identity=std::to_string(menuEpoch)+":"+std::to_string(shapeEditor.channel)+":"+std::to_string(shapeEditor.stop);
    state.reset(rgb,identity);state.layout(center,radius,scale);bool changed=false;
    ImGui::InvisibleButton("##perceptual-wheel",{side,side});shapeItemTip(23);
    state.wheelBounds={LONG(at.x),LONG(at.y),LONG(at.x+side),LONG(at.y+side)};
    state.squareBounds={LONG(lo.x),LONG(lo.y),LONG(hi.x),LONG(hi.y)};state.lightnessBounds={};
    const auto mouse=ImGui::GetIO().MousePos;
    const int hovered=ImGui::IsItemHovered()?state.hit(mouse,scale):-1;
    if(hovered>=0 && !ImGui::IsItemActive()){
        const auto p=state.points[hovered];const float hit=(State::markerExtent(hovered)+2.5f)*scale;
        shapeTipRows[25+hovered]={LONG(p.x-hit),LONG(p.y-hit),LONG(p.x+hit),LONG(p.y+hit)};shapeTipCandidate=225+hovered;
    }
    auto inSquare=[&](ImVec2 p){return p.x>=lo.x && p.y>=lo.y && p.x<=hi.x && p.y<=hi.y;};
    if(ImGui::IsItemHovered() && ImGui::IsMouseClicked(0)){
        state.dragHandle=hovered>=0;
        const auto rail=State::railPoint(center,radius,std::atan2(mouse.y-center.y,mouse.x-center.x)*180/perceptual::pi,12*scale);
        state.drag=hovered>=0?hovered:inSquare(mouse)?-2:std::hypot(mouse.x-rail.x,mouse.y-rail.y)<=8*scale?0:-1;
        state.dragStart=mouse;state.dragLast={-FLT_MAX,-FLT_MAX};state.dragOffset=hovered>=0?ImVec2{mouse.x-state.rawPoints[hovered].x,mouse.y-state.rawPoints[hovered].y}:ImVec2{};
        if(hovered>=0 && state.active!=hovered){state.active=hovered;changed|=state.apply(rgb);}
        float h,s,v;ImGui::ColorConvertRGBtoHSV(rgb[0].get<float>()/255,rgb[1].get<float>()/255,rgb[2].get<float>()/255,h,s,v);
        if(s>.0001f)state.svHue=h;
        else {const auto chromatic=perceptual::fromLch(.72,.18,state.base[2]);ImGui::ColorConvertRGBtoHSV(float(chromatic[0]/255),float(chromatic[1]/255),float(chromatic[2]/255),state.svHue,s,v);}
    }
    if(ImGui::IsItemActive() && ImGui::IsMouseDown(0) && state.drag!=-1 && (mouse.x!=state.dragLast.x || mouse.y!=state.dragLast.y) &&
       (!state.dragHandle || std::hypot(mouse.x-state.dragStart.x,mouse.y-state.dragStart.y)>.5f)){
        state.dragLast=mouse;
        if(state.drag==-2){
            float r,g,b;ImGui::ColorConvertHSVtoRGB(state.svHue,std::clamp((mouse.x-lo.x)/(2*half),0.f,1.f),std::clamp(1-(mouse.y-lo.y)/(2*half),0.f,1.f),r,g,b);
            Json next=Json::array({int(std::lround(r*255)),int(std::lround(g*255)),int(std::lround(b*255))});
            if(next!=rgb){rgb=next;state.last=State::color(rgb);state.base=perceptual::lch(state.last,state.base[2]);state.active=0;changed=true;}
        }else{
            double x=mouse.x-state.dragOffset.x-center.x,y=mouse.y-state.dragOffset.y-center.y;
            state.dragPoint(perceptual::hue(std::atan2(y,x)*180/perceptual::pi),1,state.drag);changed|=state.apply(rgb);
        }
    }
    if(!ImGui::IsMouseDown(0))state.drag=-1;
    state.cache();state.layout(center,radius,scale);
    const auto uv=ImGui::GetFontTexUvWhitePixel();
    for(int a=0;a<192;++a){
        double angle=a*360./192,next=(a+1)*360./192;
        const ImVec2 p[]={State::railPoint(center,radius+3*scale,angle,15*scale),State::railPoint(center,radius+3*scale,next,15*scale),
            State::railPoint(center,radius-3*scale,next,9*scale),State::railPoint(center,radius-3*scale,angle,9*scale)};
        const ImU32 c=state.mesh[a],n=state.mesh[a+1];
        draw->PrimReserve(6,4);auto index=draw->_VtxCurrentIdx;
        for(int i:{0,1,2,0,2,3})draw->PrimWriteIdx(index+i);
        for(int i=0;i<4;++i)draw->PrimWriteVtx(p[i],uv,i==0||i==3?c:n);
    }
    float hue,saturation,value;ImGui::ColorConvertRGBtoHSV(rgb[0].get<float>()/255,rgb[1].get<float>()/255,rgb[2].get<float>()/255,hue,saturation,value);
    if(state.drag==-2)hue=state.svHue;
    else if(saturation<.0001f){const auto chromatic=perceptual::fromLch(.72,.18,state.base[2]);float ignoredS,ignoredV;
        ImGui::ColorConvertRGBtoHSV(float(chromatic[0]/255),float(chromatic[1]/255),float(chromatic[2]/255),hue,ignoredS,ignoredV);}
    float r,g,b;ImGui::ColorConvertHSVtoRGB(hue,1,1,r,g,b);const ImU32 hueColor=ImGui::ColorConvertFloat4ToU32({r,g,b,1});
    draw->AddRectFilledMultiColor(lo,hi,IM_COL32_WHITE,hueColor,hueColor,IM_COL32_WHITE);
    draw->AddRectFilledMultiColor(lo,hi,IM_COL32(0,0,0,0),IM_COL32(0,0,0,0),IM_COL32_BLACK,IM_COL32_BLACK);
    draw->AddRect(lo,hi,ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,scale);
    const ImVec2 selected={lo.x+saturation*2*half,hi.y-value*2*half};
    draw->AddCircle(selected,4*scale,IM_COL32_BLACK,24,2*scale);draw->AddCircle(selected,5*scale,IM_COL32_WHITE,24,scale);
    for(int i=1;i<perceptual::wheelCount;++i){auto p=state.points[i],anchor=state.rawPoints[i];
        if(std::hypot(p.x-anchor.x,p.y-anchor.y)>scale){draw->AddLine(anchor,p,ImGui::GetColorU32(ImGuiCol_Border),scale);draw->AddCircleFilled(anchor,scale,ImGui::GetColorU32(ImGuiCol_TextDisabled));}}
    for(int i=1;i<perceptual::wheelCount;++i)State::drawMarker(draw,i,state.points[i],scale,State::ink(perceptual::wheelColor(state.base,i)),i==state.active);
    State::drawMarker(draw,0,state.points[0],scale,State::ink(perceptual::wheelColor(state.base,0)),state.active==0);
    ImGui::SetCursorScreenPos({at.x,at.y+side+gap});
    return changed;
}
