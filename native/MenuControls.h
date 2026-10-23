// Shared Caps/tool surfaces and widgets; inherit the current PS palette.
namespace MenuControls {
inline void surface(ImDrawList* draw,ImVec2 a,ImVec2 b,float scale,bool shadow=true) {
    const auto rounding=ImGui::GetStyle().FrameRounding;
    if(shadow)menuShadow::draw(draw,a,b,rounding,scale);
    draw->AddRectFilled(a,b,ImGui::GetColorU32(ImGuiCol_Button),rounding);
}
inline void outline(ImDrawList* draw,ImVec2 a,ImVec2 b,float scale) {
    draw->AddRect(a,b,ImGui::GetColorU32(ImGuiCol_Border),ImGui::GetStyle().FrameRounding,0,menuControlBorder*scale);
}
inline void segment(ImDrawList* draw,ImVec2 a,ImVec2 b,bool first,bool last,bool highlighted,float scale) {
    if(highlighted)draw->AddRectFilled(a,b,ImGui::GetColorU32(ImGuiCol_ButtonHovered),ImGui::GetStyle().FrameRounding,
        first && last?ImDrawFlags_RoundCornersAll:first?ImDrawFlags_RoundCornersLeft:last?ImDrawFlags_RoundCornersRight:ImDrawFlags_RoundCornersNone);
    if(!first)draw->AddLine(a,{a.x,b.y},ImGui::GetColorU32(ImGuiCol_Border),menuControlBorder*scale);
}
struct PanelStyle {
    explicit PanelStyle(float scale) {
        ImGui::PushFont(menuFont(MenuTextRole::Control));
        ImGui::PushStyleVar(ImGuiStyleVar_FramePadding,{menuControlTextInset*scale,std::max(0.f,(menuControlHeight*scale-ImGui::GetFontSize())*.5f)});
        ImGui::PushStyleVar(ImGuiStyleVar_FrameBorderSize,menuControlBorder*scale);
        ImGui::PushStyleVar(ImGuiStyleVar_ChildBorderSize,menuControlBorder*scale);
        ImGui::PushStyleVar(ImGuiStyleVar_ChildRounding,ImGui::GetStyle().FrameRounding);
        ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,{menuControlPadding*scale,menuControlPadding*scale});
        ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,{menuPanelGap*scale,menuPanelGap*scale});
    }
    ~PanelStyle(){ImGui::PopStyleVar(6);ImGui::PopFont();}
};
inline bool button(const char* label,float scale) {return ImGui::Button(label,{0,menuControlHeight*scale});}
inline bool input(const char* id,const char* hint,char* value,size_t capacity) {
    ImGui::SetNextItemWidth(-1);
    const bool enter=ImGui::InputTextWithHint(id,hint,value,capacity,ImGuiInputTextFlags_EnterReturnsTrue);
    requireText(value);
    return enter;
}
template<size_t N> bool segments(const char* id,const char* const (&names)[N],int& selected,float scale) {
    const auto origin=ImGui::GetCursorScreenPos();const float width=ImGui::GetContentRegionAvail().x,h=menuControlHeight*scale;
    if(width<=0){ImGui::Dummy({0,h});return false;}
    std::array<float,N> widths{};for(size_t i=0;i<N;++i)widths[i]=std::min(width,ImGui::CalcTextSize(names[i]).x+2*menuControlTextInset*scale);
    auto* draw=ImGui::GetWindowDrawList();float y=origin.y;bool changed=false;ImGui::PushID(id);
    for(size_t first=0;first<N;){
        size_t last=first;float total=widths[first];
        while(last+1<N && total+widths[last+1]<=width){++last;total+=widths[last];}
        surface(draw,{origin.x,y},{origin.x+total,y+h},scale,false);float x=origin.x;
        for(size_t i=first;i<=last;++i){
            ImGui::SetCursorScreenPos({x,y});ImGui::PushID(int(i));const bool clicked=ImGui::InvisibleButton(names[i],{widths[i],h},ImGuiButtonFlags_EnableNav);
            const auto mouse=ImGui::GetIO().MousePos;
            const bool seam=i>first && mouse.x<x+scale || i<last && mouse.x>=x+widths[i]-scale;
            const bool disabled=(ImGui::GetItemFlags()&ImGuiItemFlags_Disabled)!=0;
            segment(draw,{x,y},{x+widths[i],y+h},i==first,i==last,!disabled && ((!seam && ImGui::IsItemHovered()) || selected==int(i)),scale);
            const auto text=ImGui::CalcTextSize(names[i]);
            draw->AddText({x+(widths[i]-text.x)*.5f,y+(h-text.y)*.5f},ImGui::GetColorU32(disabled?ImGuiCol_TextDisabled:ImGuiCol_Text),names[i]);
            ImGui::RenderNavCursor(ImRect({x,y},{x+widths[i],y+h}),ImGui::GetItemID());
            if(clicked && (!seam || !ImGui::IsMouseReleased(ImGuiMouseButton_Left)) && !disabled){selected=int(i);changed=true;}
            ImGui::PopID();x+=widths[i];
        }
        outline(draw,{origin.x,y},{origin.x+total,y+h},scale);first=last+1;
        if(first<N)y+=h+menuPanelGap*scale;
    }
    ImGui::PopID();ImGui::SetCursorScreenPos(origin);ImGui::Dummy({width,y-origin.y+h});return changed;
}
}
