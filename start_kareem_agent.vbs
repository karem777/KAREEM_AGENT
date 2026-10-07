Set shell = CreateObject("WScript.Shell")

project = "C:\Users\Acer\KAREEM_AGENT"
pythonw = project & "\.venv\Scripts\pythonw.exe"
app = project & "\chat_app.py"

shell.Run """" & pythonw & """ """ & app & """", 0, False

WScript.Sleep 2500

shell.Run "http://127.0.0.1:5001/", 1, False
