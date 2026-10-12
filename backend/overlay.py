"""Compatibility entry point for exporting the C++ Dear ImGui renderer."""
import argparse
import subprocess
from pathlib import Path
from .paths import ROOT


def cli():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview-output',type=Path,required=True)
    parser.add_argument('--preview-kind',choices=('menu','context','hold'),default='menu')
    parser.add_argument('--preview-panel',choices=('generic','canvas','layers','text','home'),default='generic')
    parser.add_argument('--preview-lifecycle',action='store_true')
    parser.add_argument('--data-dir',type=Path)
    args=parser.parse_args()
    output=args.preview_output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    command=[str(ROOT/'native/MenuHost.exe'),'--icon',str(ROOT/'frontend/public/icon.ico'),
             '--preview-output',str(output),'--preview-kind',args.preview_kind,'--preview-panel',args.preview_panel]
    if args.preview_lifecycle: command.append('--preview-lifecycle')
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=0x08000000)
    if result.returncode or not output.is_file():
        raise RuntimeError(result.stderr or 'Dear ImGui preview failed')


if __name__=='__main__':
    cli()
