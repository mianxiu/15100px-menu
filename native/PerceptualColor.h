#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <vector>
#include <string>
// Bjorn Ottosson's Oklab matrices, D65 / sRGB. Local, bounded math only.
namespace perceptual {
using Color=std::array<double,3>;
constexpr double pi=3.14159265358979323846;
inline double hue(double h){h=std::fmod(h,360.);return h<0?h+360:h;}
inline double linear(double v){return v<=.04045?v/12.92:std::pow((v+.055)/1.055,2.4);}
inline double encoded(double v){return v<=.0031308?12.92*v:1.055*std::pow(v,1/2.4)-.055;}
inline Color lab(Color rgb){
    double r=linear(rgb[0]/255),g=linear(rgb[1]/255),b=linear(rgb[2]/255);
    double l=std::cbrt(.4122214708*r+.5363325363*g+.0514459929*b);
    double m=std::cbrt(.2119034982*r+.6806995451*g+.1073969566*b);
    double s=std::cbrt(.0883024619*r+.2817188376*g+.6299787005*b);
    return {.2104542553*l+.793617785*m-.0040720468*s,1.9779984951*l-2.428592205*m+.4505937099*s,.0259040371*l+.7827717662*m-.808675766*s};
}
inline Color rgbLinear(Color lab){
    double l=lab[0]+.3963377774*lab[1]+.2158037573*lab[2];l=l*l*l;
    double m=lab[0]-.1055613458*lab[1]-.0638541728*lab[2];m=m*m*m;
    double s=lab[0]-.0894841775*lab[1]-1.291485548*lab[2];s=s*s*s;
    return {4.0767416621*l-3.3077115913*m+.2309699292*s,-1.2684380046*l+2.6097574011*m-.3413193965*s,-.0041960863*l-.7034186147*m+1.707614701*s};
}
inline Color lch(Color rgb,double fallback=0){auto p=lab(rgb);double c=std::hypot(p[1],p[2]);return {p[0],c,c<.00001?fallback:hue(std::atan2(p[2],p[1])*180/pi)};}
inline Color cartesian(double l,double c,double h){h*=pi/180;return {l,c*std::cos(h),c*std::sin(h)};}
inline bool gamut(Color c){return std::all_of(c.begin(),c.end(),[](double v){return v>=-1e-7 && v<=1.0000001;});}
inline double maxChroma(double l,double h){
    double lo=0,hi=.4;for(int n=0;n<24;++n){double mid=(lo+hi)*.5;if(gamut(rgbLinear(cartesian(l,mid,h))))lo=mid;else hi=mid;}return lo;
}
inline Color fromLab(Color p){
    p[0]=std::clamp(p[0],0.,1.);auto v=rgbLinear(p);
    if(!gamut(v)){double h=hue(std::atan2(p[2],p[1])*180/pi),c=std::min(std::hypot(p[1],p[2]),maxChroma(p[0],h));v=rgbLinear(cartesian(p[0],c,h));}
    for(auto& n:v)n=std::clamp(encoded(n)*255,0.,255.);return v;
}
inline Color fromLch(double l,double c,double h){return fromLab(cartesian(std::clamp(l,0.,1.),std::max(0.,c),h));}
inline Color mix(Color a,Color b,double t,const std::string& method){
    t=std::clamp(t,0.,1.);if(t==0)return a;if(t==1)return b;
    if(method=="perceptual"){a=lab(a);b=lab(b);for(int i=0;i<3;++i)a[i]+=(b[i]-a[i])*t;return fromLab(a);}
    if(method=="linear"){for(int i=0;i<3;++i)a[i]=encoded(linear(a[i]/255)*(1-t)+linear(b[i]/255)*t)*255;return a;}
    for(int i=0;i<3;++i)a[i]+=(b[i]-a[i])*t;return a;
}
inline std::vector<double> offsets(int rule){
    switch(rule){case 0:return {0,-30,30};case 1:return {0,180};case 2:return {0,150,210};case 3:return {0,120,240};default:return {0,180};}
}
inline Color role(Color base,int rule,int i){
    auto values=offsets(rule);double l=base[0],c=base[1],h=hue(base[2]+values.at(i));
    if(rule==4 && i){l=base[0]>.6?.35:.8;c*=1.15;}
    return fromLch(l,c,h);
}
}
