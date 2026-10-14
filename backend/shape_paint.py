"""Strict, bounded paint values shared by native metadata and API requests."""
import math

def number(value,low,high):
    return type(value) in (int,float) and math.isfinite(value) and low<=value<=high

def paint(value,stroke=False):
    if not isinstance(value,dict) or type(value.get('enabled')) is not bool:raise ValueError('无效填充／描边')
    kind=value.get('kind');keys={'kind','enabled'}|({'width'} if stroke else set())
    def rgb(c):
        if not isinstance(c,list) or len(c)!=3 or any(not number(v,0,255) for v in c):raise ValueError('无效RGB颜色')
        return list(c)
    if kind=='solid':
        keys.add('rgb');result={'kind':kind,'enabled':value['enabled'],'rgb':rgb(value.get('rgb'))}
    elif kind=='gradient':
        keys.add('stops');stops=value.get('stops')
        if not isinstance(stops,list) or not 2<=len(stops)<=32:raise ValueError('渐变需要2至32个颜色节点')
        result={'kind':kind,'enabled':value['enabled'],'stops':[]};previous=-1
        for item in stops:
            if not isinstance(item,dict) or set(item)!={'rgb','location'} or type(item['location']) is not int or not previous<=item['location']<=4096:raise ValueError('无效渐变位置')
            result['stops'].append({'rgb':rgb(item['rgb']),'location':item['location']});previous=item['location']
    elif kind=='pattern':
        keys.add('name');name=value.get('name')
        if not isinstance(name,str) or not name or len(name)>128:raise ValueError('无效图案预设名称')
        result={'kind':kind,'enabled':value['enabled'],'name':name}
    else:raise ValueError('未知填充／描边类型')
    if set(value)!=keys:raise ValueError('填充／描边包含未知参数')
    if stroke:
        if not number(value.get('width'),0,1000):raise ValueError('无效描边宽度')
        result['width']=value['width']
    return result

def parameters(value):
    if not isinstance(value,dict) or set(value)!={'revision','fill','stroke'}:raise ValueError('形状颜色参数不完整')
    revision=value['revision']
    if not isinstance(revision,str) or not 1<=len(revision)<=128:raise ValueError('形状状态已失效，请重新打开菜单')
    return {'revision':revision,'fill':paint(value['fill']),'stroke':paint(value['stroke'],True)}

def metadata(value):
    if not isinstance(value,dict) or value.get('available') is not True:return {'available':False}
    try:
        result=parameters({k:value.get(k) for k in ('revision','fill','stroke')})
        vector=value.get('vector',True)
        if type(vector) is not bool:raise ValueError()
        patterns=value.get('patterns',[])
        if not isinstance(patterns,list) or len(patterns)>128 or any(not isinstance(x,str) or not x or len(x)>128 for x in patterns):raise ValueError()
        return {'available':True,'vector':vector,**result,'patterns':list(patterns)}
    except ValueError:return {'available':False}
