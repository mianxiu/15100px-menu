"""Exercise the production C++ pipe writer without installing input hooks.

Measures queue-to-pipe delivery, not physical-key-to-screen latency. The only
window APIs used are those already in the included production translation unit;
the harness creates no UI, sends no input, and changes no Photoshop state.
"""
import argparse,json,math,statistics,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#define main production_hotkey_main
#include "SOURCE"
#undef main
int main(int argc,char** argv) {
    available=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    if(!available || argc!=2)return 2;
    std::string mode=argv[1];
    emit(HoldBegin);
    if(mode=="queued") {emit(CopyStyle);emit(HoldCancel);}
    else if(mode=="tap")emit(HoldPin);
    else if(mode=="cancel")emit(HoldCancel);
    const char* marker="{\"type\":\"test.start\"}\n";DWORD written=0;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),marker,DWORD(strlen(marker)),&written,nullptr);
    std::thread writer(writeActions);
    if(mode=="hold" || mode=="late") {
        Sleep(mode=="hold"?300:80);
        if(mode=="late")emit(CopyStyle);
        emit(HoldCancel);
    }
    Sleep(20);closing.store(true);SetEvent(available);writer.join();CloseHandle(available);
    return 0;
}
'''

def compile_writer(source,folder,name):
    cpp=folder/(name+'.cpp');exe=folder/(name+'.exe')
    cpp.write_text(HARNESS.replace('SOURCE',source.resolve().as_posix()),'utf-8')
    subprocess.run(['g++','-std=c++17','-O2','-static',str(cpp),'-o',str(exe),'-luser32'],check=True,capture_output=True)
    return exe

def run(exe,mode):
    process=subprocess.Popen([str(exe),mode],stdout=subprocess.PIPE,text=True,encoding='utf-8')
    started=None;latency=None;events=[]
    try:
        for line in process.stdout:
            value=json.loads(line)
            if value['type']=='test.start':started=time.perf_counter()
            elif value['type']=='action':
                if value['action']=='hold_begin' and latency is None:latency=(time.perf_counter()-started)*1000
                events.append(value['action'])
        assert process.wait(3)==0
    finally:
        process.stdout.close()
        if process.poll() is None:process.terminate();process.wait(3)
    return events,latency

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-ref',default='v0.4.148')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/hotkey-opening.json')
    args=parser.parse_args();folder=ROOT/'.runtime/hotkey-opening';folder.mkdir(parents=True,exist_ok=True)
    old=folder/'baseline.cpp'
    old.write_bytes(subprocess.check_output(['git','show',args.compare_ref+':native/HotkeyHost.cpp'],cwd=ROOT))
    old_exe=compile_writer(old,folder,'old-writer');new_exe=compile_writer(ROOT/'native/HotkeyHost.cpp',folder,'new-writer')
    measured={}
    for name,exe in [('old',old_exe),('new',new_exe)]:
        values=[]
        for i in range(21):
            events,latency=run(exe,'hold');assert events==['hold_begin','hold_cancel'],events
            if i:values.append(latency)
        measured[name]={'samples':len(values),'median_ms':round(statistics.median(values),3),'p95_ms':round(sorted(values)[math.ceil(.95*len(values))-1],3)}
    assert measured['old']['median_ms']>=180 and measured['new']['p95_ms']<100,measured
    for mode,expected in [('queued',['copyStyle']),('tap',['hold_begin','hold_pin']),('cancel',[]),('late',['hold_begin','hold_cancel','copyStyle'])]:
        events,_=run(new_exe,mode);assert events==expected,(mode,events)
    report={'baseline_ref':args.compare_ref,'queue_to_pipe':measured,'queued_chord_tap_late_chord_cancel_order_passed':True,'no_input_hooks_installed':True,'physical_key_to_screen_measured':False}
    args.output.write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
