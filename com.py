import win32com.client

# 连接到 Photoshop 的 COM 接口

app = win32com.client.Dispatch("Photoshop.Application")

# 获取当前文档

# 执行 JavaScript 代码
result = app.DoJavaScript("alert('123')")

# 输出执行结果
print(result)
