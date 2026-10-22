// Prewarmed smooth shadow atlas; no per-frame blur or contour outlines.
namespace menuShadow {
inline bool enabled=true;
inline ID3D11ShaderResourceView* texture=nullptr;
inline constexpr int tile=192;
inline constexpr float extent=20.f;
inline double distance(double x,double y,double radius) {
    const double qx=std::abs(x)-1,qy=std::abs(y)-1;
    return std::hypot(std::max(qx,0.),std::max(qy,0.))+std::min(std::max(qx,qy),0.)-radius;
}
inline unsigned alpha(double x,double y,double radius) {
    const double mask=std::clamp(distance(x,y,radius)*2+.5,0.,1.);
    const double broad=.12*.5*std::erfc(distance(x,y-3,radius)/(std::sqrt(2.)*5.5));
    const double contact=.06*.5*std::erfc(distance(x,y-1,radius)/std::sqrt(2.));
    return unsigned(std::lround(255*(1-(1-broad)*(1-contact))*mask));
}
inline void release(){if(texture){texture->Release();texture=nullptr;}}
inline bool create(ID3D11Device* device) {
    release();std::vector<unsigned> pixels(tile*tile*2);
    // shortcut: current shared 4-unit corners and 19-unit ring; regenerate if those radii change.
    for(int profile=0;profile<2;++profile){
        const double radius=profile?19:figmaCornerRadius,side=2*(extent+radius+1);
        for(int y=0;y<tile;++y)for(int x=0;x<tile;++x)
            pixels[(profile*tile+y)*tile+x]=alpha((x+.5)*side/tile-side*.5,(y+.5)*side/tile-side*.5,radius)<<24;
    }
    D3D11_TEXTURE2D_DESC desc{};desc.Width=tile;desc.Height=tile*2;desc.MipLevels=desc.ArraySize=1;
    desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA data{pixels.data(),tile*4,0};ID3D11Texture2D* image=nullptr;
    HRESULT result=device->CreateTexture2D(&desc,&data,&image);
    if(SUCCEEDED(result)){result=device->CreateShaderResourceView(image,nullptr,&texture);image->Release();}
    return SUCCEEDED(result);
}
inline void draw(ImDrawList* list,ImVec2 a,ImVec2 b,float rounding,float scale) {
    if(!enabled || !texture || b.x<=a.x || b.y<=a.y)return;
    const bool ring=rounding>12*scale;const float radius=ring?19.f:figmaCornerRadius,side=2*(extent+radius+1);
    const float corner=std::min(rounding,std::min(b.x-a.x,b.y-a.y)*.5f),pad=extent*scale;
    const float xs[]={a.x-pad,a.x+corner,b.x-corner,b.x+pad},ys[]={a.y-pad,a.y+corner,b.y-corner,b.y+pad};
    const float uv[]={0,(extent+radius)/side,(extent+radius+2)/side,1};
    for(int y=0;y<3;++y)for(int x=0;x<3;++x){
        if(x==1 && y==1 || xs[x+1]<=xs[x] || ys[y+1]<=ys[y])continue;
        list->AddImage((ImTextureID)(intptr_t)texture,{xs[x],ys[y]},{xs[x+1],ys[y+1]},
            {uv[x],(uv[y]+int(ring))*.5f},{uv[x+1],(uv[y+1]+int(ring))*.5f});
    }
}
}
