// Fixed alpha contours avoid a per-frame blur pass or new GPU resources.
namespace menuShadow {
inline bool enabled=true;
inline void draw(ImDrawList* list,ImVec2 a,ImVec2 b,float rounding,float scale) {
    if(!enabled || b.x<=a.x || b.y<=a.y)return;
    static constexpr int alpha[]={24,18,14,10,7,4,2,1};
    for(int i=7;i>=0;--i) {
        const float spread=(i+1)*scale,offset=2*scale;
        list->AddRect({a.x-spread,a.y-spread+offset},{b.x+spread,b.y+spread+offset},
            IM_COL32(0,0,0,alpha[i]),rounding+spread,0,scale);
    }
}
}
