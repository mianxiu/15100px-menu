"""Build a versioned JSX upgrade ZIP without changing the installed package."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.plugins import FILES, PLUGIN_ID, version


def main():
    parser = argparse.ArgumentParser(description="打包 Photoshop Menu JSX 升级包")
    parser.add_argument("--version", required=True)
    parser.add_argument("--scripts", type=Path, default=ROOT / "jsx")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    version(args.version)
    files = {name: (args.scripts/name).read_bytes() for name in FILES}
    if files[FILES[2]].decode("utf-8").count("/*%Bool%*/") != 1:
        raise ValueError("移动脚本必须包含唯一的 /*%Bool%*/ 参数标记")
    data = {"id":PLUGIN_ID, "version":args.version, "api_version":1, "name":"Photoshop Menu 图层操作",
            "sha256":{name:hashlib.sha256(content).hexdigest() for name,content in files.items()}}
    output = args.output or ROOT / ".runtime" / f"{PLUGIN_ID}-{args.version}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json",json.dumps(data,ensure_ascii=False,indent=2))
        for name, content in files.items():
            archive.writestr(name,content)
    print(str(output.resolve()))
    print("SHA256:",hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
