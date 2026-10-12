"""Import matching primitive and vector icons from the user's offline Figma export.

Unsupported vector nodes are never guessed or traced from preview images.
Geometry is compiled into MenuHost; opening the menu does not read JSON/assets.
"""
import hashlib,json,re,runpy,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'.local/design/151500PX.figma-export.zip'
if len(sys.argv)==1 and not source.is_file():source=ROOT/'151500PX.figma-export.zip'
if not source.is_file():raise SystemExit('Provide a local Figma export path; raw designs are not distributed. Expected .local/design/151500PX.figma-export.zip or an explicit argument.')
with zipfile.ZipFile(source) as archive:
    design=archive.read('design.figma-export.json')
    source_svgs={id:archive.read('svg/'+id.replace(':','%3A')+'.svg') for id in ('324:0','326:461')}
data=json.loads(design);nodes=[]
def walk(node):
    nodes.append(node)
    for child in node.get('children',[]):walk(child)
for page in data['pages']:walk(page)
chosen=['quick_icon-layer-same-level-select','quick_icon-h/s']
blocks=[];provenance=[]
def tone(color):
    assert max(color[k] for k in ('r','g','b'))-min(color[k] for k in ('r','g','b'))<.001
    return (color['r']-37/255)/(1-37/255)
for index,name in enumerate(chosen):
    node=next(n for n in nodes if n['type']=='COMPONENT' and n['name']==name)
    children=[c for c in node['children'] if c.get('visible',True)]
    assert all(c['type']=='RECTANGLE' and not c.get('children') and c['rotation']==0 and c.get('cornerRadius',0)==0 for c in children)
    left=min(c['x'] for c in children);top=min(c['y'] for c in children)
    width=max(c['x']+c['width'] for c in children)-left;height=max(c['y']+c['height'] for c in children)-top
    rows=[]
    for c in children:
        fill=next(p for p in c['fills'] if p.get('visible',True));strokes=[p for p in c['strokes'] if p.get('visible',True)]
        assert fill.get('opacity',1)==1 and c.get('opacity',1)==1
        assert not strokes or (len(strokes)==1 and strokes[0]['type']=='SOLID' and c['strokeAlign']=='INSIDE')
        stroke=c['strokeWeight'] if strokes else 0
        if fill['type']=='SOLID':a=b=tone(fill['color']);start,end=0,1
        else:
            assert fill['type']=='GRADIENT_LINEAR' and len(fill['gradientStops'])==2
            m=fill['gradientTransform'];assert abs(m[0][1])<.00001 and abs(m[1][0])<.00001
            a,b=[tone(p['color']) for p in fill['gradientStops']]
            start,end=-m[0][2]/m[0][0],(1-m[0][2])/m[0][0]
        rows.append([c['x']-left,c['y']-top,c['width'],c['height'],a,b,start,end,stroke,tone(strokes[0]['color']) if strokes else 0])
    number=lambda v:format(v,'.8f')+'f'
    blocks.append('static constexpr FigmaIconRect figmaIcon'+str(index)+'[] = {\n'+''.join('    {'+', '.join(map(number,r))+'},\n' for r in rows)+'};\n')
    provenance.append({'node_id':node['id'],'name':name,'root_size':[node['width'],node['height']], 'content_bounds':[left,top,width,height],'child_ids':[c['id'] for c in children],'rectangles':len(rows)})
assert len(provenance)==2 and all(p['content_bounds'][2:]==[9,9] for p in provenance)
# Compile the original outlined geometry. No tracing, runtime SVG parsing or
# guessed substitutions: these components represent the existing parent sort.
vector_blocks=[]
for index,node_id,top in [(2,'324:0',8),(3,'326:461',7)]:
    node=next(n for n in nodes if n['id']==node_id)
    rows=[]
    for child in node['children']:
        if not child.get('visible',True):continue
        transform=child['relativeTransform']
        def point(x,y):
            return [transform[0][0]*x+transform[0][1]*y+transform[0][2]-4.5,
                    transform[1][0]*x+transform[1][1]*y+transform[1][2]-top]
        geometries=child.get('fillGeometry',[]) if child.get('fills') else child.get('strokeGeometry',[])
        assert geometries,child['id']
        for geometry in geometries:
            assert geometry['windingRule']=='NONZERO'
            tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',geometry['data'])
            i=0;command=None;current=[0,0]
            while i<len(tokens):
                if tokens[i].isalpha():command=tokens[i];i+=1
                assert command in ('M','L','C','H','V','Z'),command
                if command=='Z':rows.append(['Z',0,0,0,0,0,0]);command=None;continue
                count={'M':2,'L':2,'C':6,'H':1,'V':1}[command]
                values=list(map(float,tokens[i:i+count]));assert len(values)==count;i+=count
                if command=='H':values=[values[0],current[1]]
                if command=='V':values=[current[0],values[0]]
                current=values[-2:]
                mapped=[v for j in range(0,len(values),2) for v in point(*values[j:j+2])]
                rows.append([command if command in ('M','C') else 'L',*mapped,*([0]*(6-len(mapped)))])
                if command=='M':command='L'
    vector_blocks.append('static constexpr FigmaPathCommand figmaIcon'+str(index)+'[] = {\n'+''.join("    {'"+r[0]+"', "+', '.join(format(v,'.8f')+'f' for v in r[1:])+"},\n" for r in rows)+'};\n')
    assets=ROOT/'native/figma-assets';assets.mkdir(exist_ok=True)
    (assets/(node_id.replace(':','_')+'.svg')).write_bytes(source_svgs[node_id])
    provenance.append({'node_id':node_id,'name':node['name'],'root_size':[18,24],
        'content_bounds':[5,top,8,9],'normalized_square':[4.5,top,9,9],
        'child_ids':[c['id'] for c in node['children']],'commands':len(rows),
        'svg_sha256':hashlib.sha256(source_svgs[node_id]).hexdigest(),
        'geometry':'Original fillGeometry/strokeGeometry with relativeTransform; cubic curves preserved'})
panel=next(n for n in nodes if n['id']=='326:514')
wrapper=next(n for n in nodes if n['id']=='223:20')
assert panel['cornerRadius']==4 and panel['height']==24 and panel['strokeWeight']==1
assert wrapper['paddingTop']==wrapper['itemSpacing']==6
metrics={'corner_radius':panel['cornerRadius'],'widget_height':panel['height'],
    'icon_width':provenance[0]['root_size'][0],'icon_size':provenance[0]['content_bounds'][2],
    'padding':wrapper['paddingTop'],'gap':wrapper['itemSpacing'],'border':panel['strokeWeight']}
header='''// Generated by tools/import-figma-menu.py from the user's 151500PX export.
// Source geometry/inside strokes retained; monochrome tones follow PS colors.
struct FigmaIconRect {float x,y,w,h,a,b,start,end,stroke,strokeTone;};
'''+''.join('static constexpr float figma'+''.join(p.title() for p in k.split('_'))+' = '+str(v)+'.0f;\n' for k,v in metrics.items())+'''// User requested larger icons and comfortable icon buttons.
static constexpr float figmaDisplayIconSize = 16.0f;
static constexpr float figmaDisplayIconWidth = 24.0f;
static constexpr float figmaDisplayWidgetHeight = 30.0f;
// Optical balance for text actions; icon-only segments retain their larger size.
static constexpr float figmaBasicIconSize = 12.0f;
static constexpr float figmaBasicTextScale = .95f;
static constexpr float figmaBasicLeftPadding = 9.0f;
static constexpr float figmaBasicIconGap = 6.0f;
static constexpr float figmaBasicRightPadding = 9.0f;
'''+''.join(blocks)+'''struct FigmaPathCommand {char op;float x,y,x2,y2,x3,y3;};
'''+''.join(vector_blocks)+'''
static void drawFigmaSortIcon(ImDrawList* draw,int icon,ImVec2 at,float size,ImU32 ink) {
    const auto* commands=icon==2?figmaIcon2:figmaIcon3;
    const int count=icon==2?sizeof(figmaIcon2)/sizeof(*figmaIcon2):sizeof(figmaIcon3)/sizeof(*figmaIcon3);
    const float unit=size/9;
    auto point=[&](float x,float y){return ImVec2{at.x+x*unit,at.y+y*unit};};
    for(int i=0;i<count;++i) {
        const auto& c=commands[i];
        if(c.op=='M') {draw->PathClear();draw->PathLineTo(point(c.x,c.y));}
        else if(c.op=='L')draw->PathLineToMergeDuplicate(point(c.x,c.y));
        else if(c.op=='C')draw->PathBezierCubicCurveTo(point(c.x,c.y),point(c.x2,c.y2),point(c.x3,c.y3));
        else { // Explicit closing edge may duplicate the first vertex.
            if(draw->_Path.Size>1 && draw->_Path.back().x==draw->_Path[0].x && draw->_Path.back().y==draw->_Path[0].y)draw->_Path.pop_back();
            // Figma outlines can wind either way; ImGui concave fill requires
            // clockwise contours. Reordering sampled vertices preserves shape.
            float area=0;
            for(int j=0;j<draw->_Path.Size;++j) {
                const auto& a=draw->_Path[j];const auto& b=draw->_Path[(j+1)%draw->_Path.Size];
                area+=a.x*b.y-b.x*a.y;
            }
            if(area<0)std::reverse(draw->_Path.begin(),draw->_Path.end());
            draw->PathFillConcave(ink);
        }
    }
}
static void drawFigmaMenuIcon(ImDrawList* draw,int icon,ImVec2 at,float size,ImU32 ink,ImU32 surface) {
    const auto fg=ImGui::ColorConvertU32ToFloat4(ink),bg=ImGui::ColorConvertU32ToFloat4(surface);
    auto color=[&](float t){t=std::clamp(t,0.f,1.f);return ImGui::ColorConvertFloat4ToU32({fg.x+(bg.x-fg.x)*t,fg.y+(bg.y-fg.y)*t,fg.z+(bg.z-fg.z)*t,fg.w});};
    const float unit=size/9;
    const FigmaIconRect* rects=icon==0?figmaIcon0:figmaIcon1;
    const int count=icon==0?sizeof(figmaIcon0)/sizeof(*figmaIcon0):sizeof(figmaIcon1)/sizeof(*figmaIcon1);
    for(int i=0;i<count;++i) {
        const auto& r=rects[i];const ImVec2 a={at.x+r.x*unit,at.y+r.y*unit},b={a.x+r.w*unit,a.y+r.h*unit};
        if(r.a==r.b)draw->AddRectFilled(a,b,color(r.a));
        else {
            const float start=a.x+r.start*r.w*unit,end=a.x+r.end*r.w*unit;
            draw->AddRectFilled(a,{start,b.y},color(r.a));
            draw->AddRectFilledMultiColor({start,a.y},{end,b.y},color(r.a),color(r.b),color(r.b),color(r.a));
            draw->AddRectFilled({end,a.y},b,color(r.b));
        }
        if(r.stroke) {
            const float inset=r.stroke*unit*.5f;
            draw->AddRect({a.x+inset,a.y+inset},{b.x-inset,b.y-inset},color(r.strokeTone),0,0,r.stroke*unit);
        }
    }
}
'''
(ROOT/'native/FigmaMenuIcons.h').write_text(header,'utf-8')
(ROOT/'native/figma-menu-provenance.json').write_text(json.dumps({'source':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'design_sha256':hashlib.sha256(design).hexdigest(),'geometry_coverage':data['geometryCoverage'],'icons':provenance,'unmatched_operations':['layer.new','layer.solid','layer.group','adjustment.curves','adjustment.colorBalance','adjustment.blackAndWhite'],'unmatched_reason':'No component with corresponding operation semantics; existing native glyphs retained. Full export contains vector paths.','ui_reference':{'node_ids':['326:514','223:20'],'metrics':metrics,'display_icon_size':16,'display_icon_button':[24,30],'item_spacing':0,'icon_root':[18,24]},'adaptation':'Source rounding, metrics, exact primitive and outlined vector geometry compiled into native menu. Source 9-unit glyphs display at 16 units per user feedback. Existing PS palette, blue hover, font settings, near-centre radial anchors, preset dimensions, swatch size and hit bounds retained.'},ensure_ascii=False,indent=2),'utf-8')
print('Imported 4 original Figma icons (2 primitive, 2 outlined vector); no runtime file reads')
runpy.run_path(str(ROOT/'tools/build-menu-style-icons.py'))
