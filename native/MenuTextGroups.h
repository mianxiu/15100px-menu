// Same UTF-16 line boundaries as frontend/src/text-tools.mjs.
static std::wstring menuWide(const std::string& value) {
    if(value.empty())return {};
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),nullptr,0);
    if(!size)throw std::runtime_error("文字编码无效");
    std::wstring result(size,0);MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),int(value.size()),result.data(),size);return result;
}
static std::string menuUtf8(const std::wstring& value) {
    if(value.empty())return {};
    const int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),int(value.size()),nullptr,0,nullptr,nullptr);
    if(!size)throw std::runtime_error("文字编码无效");
    std::string result(size,0);WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),int(value.size()),result.data(),size,nullptr,nullptr);return result;
}
static std::string menuDefaultGroups(const std::string& source) {
    const auto text=menuWide(source);int lines=1;
    for(size_t i=0;i<text.size();++i)if(text[i]==L'\r'){++lines;if(i+1<text.size() && text[i+1]==L'\n')++i;}else if(text[i]==L'\n')++lines;
    const int size=(lines+63)/64;
    std::string result;
    for(int from=1;from<=lines;from+=size){int to=std::min(lines,from+size-1);if(!result.empty())result+=',';result+=std::to_string(from);if(to!=from)result+='-'+std::to_string(to);}
    return result;
}
struct MenuSplitPreview {Json breaks=Json::array();std::string text,error;int count=0;};
static MenuSplitPreview menuSplitPreview(const std::string& source,const std::string& expression) {
    MenuSplitPreview result;
    const auto fail=[&](){result.breaks=Json::array();result.count=0;result.text.clear();result.error="分组须按顺序覆盖所有行，例如1-3,4,5-7，最多64组";return result;};
    try {
        const auto text=menuWide(source);auto groups=menuWide(expression);
        if(text.size()>20000 || groups.size()>1000 || text.find(L'\0')!=std::wstring::npos)return fail();
        std::replace(groups.begin(),groups.end(),L'，',L',');
        std::vector<int> ends;for(int i=0;i<int(text.size());++i)if(text[i]==L'\r')ends.push_back(i+1);ends.push_back(int(text.size()));
        static const std::wregex token(LR"(^\s*([1-9][0-9]*)(?:\s*-\s*([1-9][0-9]*))?\s*$)");
        std::wistringstream input(groups);std::wstring part;int next=1,tokens=0;
        if(groups.empty() || groups.back()==L',')return fail();
        while(std::getline(input,part,L',')) {
            std::wsmatch match;if(++tokens>64 || !std::regex_match(part,match,token))return fail();
            unsigned long from=std::stoul(match[1]),to=match[2].matched?std::stoul(match[2]):from;
            if(from!=unsigned(next) || to<from || to>ends.size())return fail();
            int end=ends[to-1];if(end>0 && (result.breaks.empty() || result.breaks.back()!=end))result.breaks.push_back(end);next=int(to)+1;
        }
        if(next!=int(ends.size())+1)return fail();
        int from=0;
        for(const auto& boundary:result.breaks){int end=boundary.get<int>(),to=end && text[end-1]==L'\r'?end-1:end;auto value=text.substr(from,to-from);from=end;
            auto space=[](wchar_t c){return iswspace(c) || c==0xa0 || c==0xfeff || (c>=0x2000 && c<=0x200a) || c==0x2028 || c==0x2029 || c==0x202f || c==0x205f || c==0x3000;};
            if(std::all_of(value.begin(),value.end(),space))continue;
            std::replace(value.begin(),value.end(),L'\r',L'\n');
            if(!result.text.empty())result.text+="\n\n";
            result.text+=std::to_string(++result.count)+":\n"+menuUtf8(value);
        }
        if(result.count<2)result.error="拆分需要至少两组非空文字";
        return result;
    } catch(const std::exception&) {return fail();}
}

struct MenuIndentResult {std::string text,error;int start,end,cursor;};
static MenuIndentResult menuIndentLines(const std::string& text,int start,int end,int cursor,int direction) {
    MenuIndentResult result{text,"",start,end,cursor};
    if(direction!=1 && direction!=-1){result.error="无效的缩进操作";return result;}
    auto position=[&](int p){p=std::clamp(p,0,int(text.size()));while(p>0 && p<int(text.size()) && (static_cast<unsigned char>(text[p])&0xc0)==0x80)--p;return p;};
    start=position(start);end=position(end);cursor=position(cursor);
    const int left=std::min(start,end),right=std::max(start,end),limit=right>left?right-1:right;
    const auto newline=left?text.rfind('\n',left-1):std::string::npos;
    int from=newline==std::string::npos?0:int(newline)+1;
    struct Edit {int from,length;std::string value;};std::vector<Edit> edits;
    for(;from<=limit && from<=int(text.size());) {
        int stop=from,columns=0;
        while(stop<int(text.size()) && (text[stop]==' ' || text[stop]=='\t')){columns=text[stop]=='\t'?(columns/4+1)*4:columns+1;++stop;}
        const int level=(columns+3)/4;
        if(direction>0 && level>=5){result.error="列表最多6级，请减少缩进";return result;}
        const auto value=std::string(std::max(0,level+direction),'\t');
        if(text.substr(from,stop-from)!=value)edits.push_back({from,stop-from,value});
        const auto next=text.find('\n',stop);if(next==std::string::npos)break;from=int(next)+1;
    }
    auto mapped=[&](int p){int shift=0;for(const auto& edit:edits){if(p>=edit.from+edit.length)shift+=int(edit.value.size())-edit.length;else if(p>=edit.from)return edit.from+shift+int(edit.value.size());}return p+shift;};
    result.start=mapped(start);result.end=mapped(end);result.cursor=mapped(cursor);
    for(auto edit=edits.rbegin();edit!=edits.rend();++edit)result.text.replace(edit->from,edit->length,edit->value);
    if(result.text.size()>=80001){result.text=text;result.start=start;result.end=end;result.cursor=cursor;result.error="缩进后的文字超出编辑上限";}
    return result;
}
