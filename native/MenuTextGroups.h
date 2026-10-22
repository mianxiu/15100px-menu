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
    const auto text=menuWide(source);const int lines=1+int(std::count(text.begin(),text.end(),L'\r')),size=(lines+63)/64;
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
