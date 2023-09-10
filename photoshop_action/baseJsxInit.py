import glob
import os

# 文件夹路径
folder_path = "G:\Github/15100px-menu\extendScriptTest/finish jsx/"

# 获取文件夹内所有的txt文件路径
txt_files = glob.glob(folder_path + "/*.jsx")

# 创建一个空字典
file_contents = {}

# 遍历txt文件
for file_path in txt_files:
    # 获取文件名（不包含扩展名）
    file_name, file_extend = os.path.splitext(os.path.basename(file_path))
    print(file_name)
    # 打开文件并读取内容
    with open(file_path, "r", encoding="UTF-8") as file:
        content = file.read()

    # 将文件名作为字典的键，文件内容作为字典的值
    file_contents[file_name] = content

# 使用文件名作为变量名访问文件内容
for file_name, content in file_contents.items():
    globals()[file_name] = content
