import glob
import os
import re


# todo 2023 10 17 need add init file
# test how insert the variable to string
def baseJsxInitFiles():
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

    return file_contents


# f = baseJsxInitFiles()


def replaceJsxFilesStr(jsxString: str, replaceStr: str):
    reg = r"=.*\/\*%Bool%\*\/"
    return re.sub(reg, r"= " + replaceStr, jsxString)

    # print(f["move_to_top_or_bottom"])


def jsxFilesBooleanStr(jsxString: str, isTrue=True):
    reg = r"=.*\/\*%Bool%\*\/"
    if isTrue:
        return re.sub(reg, r"= true", jsxString)
    else:
        return re.sub(reg, r"= false", jsxString)

    # print(f["move_to_top_or_bottom"])


# print(jsxFilesBooleanStr(f["move_to_top_or_bottom"], isTrue=False))

# print(jsxFilesBooleanStr(f["move_to_top_or_bottom"], isTrue=True))
# print(f["select_all_layer_in_group"])
