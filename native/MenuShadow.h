// Win11-style contact + broad lower shadow; fixed contours, no blur pass.
// Per-surface approximation: these controls share one transparent HWND.
namespace menuShadow {
inline bool enabled=true;
inline void draw(ImDrawList* list,ImVec2 a,ImVec2 b,float rounding,float scale) {
    if(!enabled || b.x<=a.x || b.y<=a.y)return;
    static constexpr int broad[]={16,12,9,6,4,2,1,1};
    for(int i=7;i>=0;--i) {
        const float spread=(i+1)*2*scale,offset=4*scale;
        list->AddRect({a.x-spread,a.y-spread+offset},{b.x+spread,b.y+spread+offset},
            IM_COL32(0,0,0,broad[i]),rounding+spread,0,2*scale);
    }
    for(int i=2;i>=1;--i) {
        const float spread=i*scale,offset=scale;
        list->AddRect({a.x-spread,a.y-spread+offset},{b.x+spread,b.y+spread+offset},
            IM_COL32(0,0,0,i==1?20:10),rounding+spread,0,scale);
    }
}
}
