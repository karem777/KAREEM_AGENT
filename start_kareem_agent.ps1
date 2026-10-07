$ErrorActionPreference = "Stop"

$Project = "C:\Users\Acer\KAREEM_AGENT"

Set-Location $Project

$Python = ".\.venv\Scripts\python.exe"
$App = ".\chat_app.py"
$Url = "http://127.0.0.1:5001/"

# لو الواجهة شغالة بالفعل، افتحها فقط
try {
    $r = Invoke-WebRequest `
        -Uri $Url `
        -UseBasicParsing `
        -TimeoutSec 2

    if ($r.StatusCode -eq 200) {
        Start-Process $Url
        exit
    }
}
catch {}

# شغّل الـ Agent UI في الخلفية
Start-Process `
    -FilePath $Python `
    -ArgumentList $App `
    -WorkingDirectory $Project `
    -WindowStyle Hidden

# استنى لحد Flask يشتغل
for ($i = 0; $i -lt 40; $i++) {

    Start-Sleep -Milliseconds 500

    try {

        $r = Invoke-WebRequest `
            -Uri $Url `
            -UseBasicParsing `
            -TimeoutSec 2

        if ($r.StatusCode -eq 200) {

            Start-Process $Url

            exit
        }
    }
    catch {}
}

Start-Process $Url
