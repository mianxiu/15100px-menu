// Shared presentation-only activity geometry for ImGui and the Win32 hint.
// Absolute time keeps the arc continuous through stage/window handoffs.
namespace activity {
inline constexpr unsigned periodMs=1100;
inline constexpr int segments=12;
inline float angle(unsigned long long tick,int segment=0){
    return float(tick%periodMs)*(6.2831853f/periodMs)-1.5707963f+segment*(1.5707963f/segments);
}
inline float stroke(float radius,float unit){return std::max(unit,radius*.28f);}
inline void draw(ImDrawList* list,ImVec2 at,float radius,float unit,ImU32 track,ImU32 accent,unsigned long long tick){
    const float width=stroke(radius,unit);
    list->AddCircle(at,radius,track,40,width);
    list->PathArcTo(at,radius,angle(tick),angle(tick,segments),segments);
    list->PathStroke(accent,0,width);
}
}
