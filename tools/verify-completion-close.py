
"""Actual Desktop.event -> native stdin -> completion query -> Desktop.hide -> Win32 visibility.
Owned test window only; no PS commands, keyboard/mouse injection, or foreground activation.
"""
import argparse,json,queue,subprocess,sys,threading,time
from pathlib import Path
from unittest.mock import Mock
import win32api,win32con,win32gui,win32process
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r));from backend.desktop import Desktop
parser=argparse.ArgumentParser();parser.add_argument('--native',type=Path,default=r/'native/MenuHost.exe');parser.add_argument('--output',type=Path,default=r/'.runtime/completion-close');parser.add_argument('--origin',type=int,nargs=2,default=[2000,40]);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
h=win32api.GetCurrentProcess();bits=[1<<n for n in range(64) if win32process.GetProcessAffinityMask(h)[0]&(1<<n)];win32process.SetProcessAffinityMask(h,sum(bits[:2]));win32process.SetPriorityClass(h,win32process.BELOW_NORMAL_PRIORITY_CLASS)
ready=queue.Queue();foreground=win32gui.GetForegroundWindow();startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=win32con.SW_SHOWNOACTIVATE
p=subprocess.Popen([str(args.native.resolve()),'--self-test-origin',*map(str,args.origin)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(args.output/'native.log').open('w',encoding='utf-8'),text=True,encoding='utf-8',startupinfo=startup)
def reader():
 for line in p.stdout:
  v=json.loads(line)
  if v.get('type')=='ready':ready.put(v)
threading.Thread(target=reader,daemon=True).start();native=ready.get(timeout=15);hwnd=native['hwnd'];records=[]
d=Desktop('http://localhost',lambda _:None);d.process=p;d.gui=win32gui;d.hwnd=hwnd;d._native_config=Mock();d._scope=Mock(return_value=True);d._is_menu_window=Mock(return_value=False);d.preview_pending_feedback=Mock()
def wait(check):
 end=time.monotonic()+3
 while not check():
  assert p.poll() is None and time.monotonic()<end,'Native state transition did not complete'
  time.sleep(.005)
try:
 for n,(scope,held,action) in enumerate([(2,True,'shape.paint'),(2,False,'moveUp'),(2,True,'label.red'),(2,False,'layer.new'),(2,True,'selectAbove'),(2,True,'shape.pastePaint'),(0,False,'copyStyle'),(1,True,'color'),(4,False,'document.recent')]):
  d.menu_epoch=20+n;win32gui.SendMessage(hwnd,0x8011,(32 if scope==4 else scope)|(16 if held else 0),d.menu_epoch)
  d.visible=True;win32gui.SetWindowPos(hwnd,0,*args.origin,920,620,win32con.SWP_NOZORDER|win32con.SWP_NOACTIVATE|win32con.SWP_SHOWWINDOW)
  d.event({'type':'operation','busy':True,'action':action});wait(lambda:win32gui.SendMessage(hwnd,0x8013,0,0)&2)
  wait(lambda:win32gui.SendMessage(hwnd,0x8012,0,0)>0)
  assert win32gui.IsWindowVisible(hwnd)
  # Failure and unknown cannot close despite idle; a later real success replaces the failure.
  d.event({'type':'notice','scope':'operation','ok':False,'message':'fixture failure'});d.event({'type':'operation','busy':False})
  wait(lambda:not win32gui.SendMessage(hwnd,0x8013,0,0)&2);d._close_completed_menu();assert d.visible and win32gui.IsWindowVisible(hwnd)
  d.event({'type':'notice','scope':'operation','ok':True,'message':'fixture success'});started=time.monotonic()
  d._close_completed_menu();assert d.visible and win32gui.IsWindowVisible(hwnd)
  if action=='shape.paint':
   d.preview_input_guard={'release':True};time.sleep(.5);d._close_completed_menu();assert d.visible
   d.preview_input_guard=None
  while d.visible and time.monotonic()-started<2:
   d._close_completed_menu();time.sleep(.01)
  assert not d.visible and not win32gui.IsWindowVisible(hwnd)
  records.append({'scope':scope,'held':held,'action':action,'visible_content_before':True,'native_window_hidden_after':True,'close_ms':round((time.monotonic()-started)*1000,2),'guard_waited':action=='shape.paint'})
 assert win32gui.GetForegroundWindow()==foreground,'Owned fixture changed foreground'
 (args.output/'verified.json').write_text(json.dumps({'cases':records,'real_desktop_event_and_hide':True,'no_ps_commands':True,'foreground_preserved':True,'two_cpu_below_normal':True},indent=2),'utf-8')
 print(json.dumps(records),flush=True)
finally:
 win32gui.PostMessage(hwnd,win32con.WM_CLOSE,0,0);p.wait(timeout=5);p.stdin.close();p.stdout.close()
