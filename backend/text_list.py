"""List options travel with the native text layer; PS text remains authoritative."""
import json
import re
from xml.dom import Node, minidom
from .text_plan import parameters

NAMESPACE='https://15100px.menu/ns/list/1.0/'
RDF='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
KEYS={'kind','marker','custom_marker','numbering','start'}


def options(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!=KEYS:raise ValueError('无效的列表标记')
    result=parameters({**value,'revision':'list','draft':'','operation':'list'})
    if result['kind']=='remove':raise ValueError('无效的列表标记')
    return {key:result[key] for key in KEYS}


def packet(raw):
    if not isinstance(raw,str) or len(raw)>131072 or '\0' in raw or re.search(r'<!\s*(DOCTYPE|ENTITY)\b',raw,re.I):raise ValueError('图层元数据过大或包含不支持的XML声明')
    try:doc=minidom.parseString(raw) if raw.strip() else minidom.parseString('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="'+RDF+'"/></x:xmpmeta>')
    except Exception:raise ValueError('图层元数据XML无效，未改动列表标记') from None
    stack=[(doc,0)];count=0
    while stack:
        node,depth=stack.pop();count+=1
        if count>4096 or depth>64:raise ValueError('图层元数据结构超出上限')
        stack.extend((child,depth+1) for child in node.childNodes)
    roots=doc.getElementsByTagNameNS(RDF,'RDF')
    if len(roots)!=1:raise ValueError('图层元数据缺少唯一RDF容器')
    found=[]
    for desc in roots[0].childNodes:
        if desc.nodeType!=Node.ELEMENT_NODE or (desc.namespaceURI,desc.localName)!=(RDF,'Description'):continue
        attr=desc.getAttributeNodeNS(NAMESPACE,'options')
        if attr:found.append((desc,attr))
        for child in desc.childNodes:
            if child.nodeType==Node.ELEMENT_NODE and (child.namespaceURI,child.localName)==(NAMESPACE,'options'):found.append((desc,child))
    if len(found)>1:raise ValueError('图层包含冲突的列表标记')
    return doc,roots[0],found


def read(raw):
    _,_,found=packet(raw)
    if not found:return None
    desc,node=found[0]
    if desc.getAttributeNS(RDF,'about'):raise ValueError('列表标记目标无效')
    if node.nodeType==Node.ATTRIBUTE_NODE:text=node.value
    else:
        if any(child.nodeType not in (Node.TEXT_NODE,Node.CDATA_SECTION_NODE) for child in node.childNodes):raise ValueError('列表标记结构无效')
        text=''.join(child.data for child in node.childNodes)
    try:value=json.loads(text)
    except (TypeError,ValueError):raise ValueError('列表标记JSON无效') from None
    if not isinstance(value,dict) or set(value)!={'schema','options'} or type(value['schema']) is not int or value['schema']!=1:raise ValueError('列表标记版本不受支持')
    return options(value['options'])


def write(raw,value):
    value=options(value)
    if read(raw)==value:return raw
    doc,root,found=packet(raw)
    for desc,node in found:
        if node.nodeType==Node.ATTRIBUTE_NODE:desc.removeAttributeNode(node)
        else:desc.removeChild(node)
    if value is not None:
        desc=doc.createElementNS(RDF,'rdf:Description');desc.setAttribute('xmlns:rdf',RDF);desc.setAttributeNS(RDF,'rdf:about','')
        node=doc.createElementNS(NAMESPACE,'pxmenu:options');node.setAttribute('xmlns:pxmenu',NAMESPACE)
        node.appendChild(doc.createTextNode(json.dumps({'schema':1,'options':value},ensure_ascii=False,separators=(',',':'))))
        desc.appendChild(node);root.appendChild(desc)
    result=doc.toxml()
    if len(result)>131072:raise ValueError('图层元数据超出上限')
    return result
