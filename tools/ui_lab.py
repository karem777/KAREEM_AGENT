from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "tools" / "ui_lab_native.ps1"

NATIVE_PS = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "KAREEM UI LAB"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(950, 720)
$form.MinimumSize = New-Object System.Drawing.Size(820, 620)

$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Dock = "Fill"

$basic = New-Object System.Windows.Forms.TabPage
$basic.Text = "Basic"

$advanced = New-Object System.Windows.Forms.TabPage
$advanced.Text = "Advanced"

[void]$tabs.TabPages.Add($basic)
[void]$tabs.TabPages.Add($advanced)

$labelText = New-Object System.Windows.Forms.Label
$labelText.Text = "Universal Text"
$labelText.AutoSize = $true
$labelText.Location = New-Object System.Drawing.Point(30, 35)
$basic.Controls.Add($labelText)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Name = "UniversalText"
$textBox.Width = 520
$textBox.Location = New-Object System.Drawing.Point(170, 30)
$basic.Controls.Add($textBox)

$check = New-Object System.Windows.Forms.CheckBox
$check.Name = "ReadyCheck"
$check.Text = "Ready Check"
$check.AutoSize = $true
$check.Location = New-Object System.Drawing.Point(170, 78)
$basic.Controls.Add($check)

$labelCombo = New-Object System.Windows.Forms.Label
$labelCombo.Text = "Profile"
$labelCombo.AutoSize = $true
$labelCombo.Location = New-Object System.Drawing.Point(30, 125)
$basic.Controls.Add($labelCombo)

$combo = New-Object System.Windows.Forms.ComboBox
$combo.Name = "ProfileCombo"
$combo.DropDownStyle = "DropDownList"
$combo.Width = 250
[void]$combo.Items.Add("Basic")
[void]$combo.Items.Add("Expert")
[void]$combo.Items.Add("Automation")
$combo.SelectedIndex = 0
$combo.Location = New-Object System.Drawing.Point(170, 120)
$basic.Controls.Add($combo)

$radioA = New-Object System.Windows.Forms.RadioButton
$radioA.Name = "OptionA"
$radioA.Text = "Option A"
$radioA.AutoSize = $true
$radioA.Location = New-Object System.Drawing.Point(170, 170)
$basic.Controls.Add($radioA)

$radioB = New-Object System.Windows.Forms.RadioButton
$radioB.Name = "OptionB"
$radioB.Text = "Option B"
$radioB.AutoSize = $true
$radioB.Location = New-Object System.Drawing.Point(270, 170)
$basic.Controls.Add($radioB)

$labelList = New-Object System.Windows.Forms.Label
$labelList.Text = "Items"
$labelList.AutoSize = $true
$labelList.Location = New-Object System.Drawing.Point(30, 220)
$basic.Controls.Add($labelList)

$list = New-Object System.Windows.Forms.ListBox
$list.Name = "ItemsList"
$list.Width = 250
$list.Height = 115
[void]$list.Items.Add("Alpha")
[void]$list.Items.Add("Beta")
[void]$list.Items.Add("Gamma")
[void]$list.Items.Add("Delta")
$list.Location = New-Object System.Drawing.Point(170, 215)
$basic.Controls.Add($list)

$run = New-Object System.Windows.Forms.Button
$run.Name = "RunUniversalTest"
$run.Text = "Run Universal Test"
$run.Width = 190
$run.Height = 38
$run.Location = New-Object System.Drawing.Point(170, 355)
$basic.Controls.Add($run)

$status = New-Object System.Windows.Forms.Label
$status.Name = "Status"
$status.AutoSize = $true
$status.Text = "READY"
$status.Location = New-Object System.Drawing.Point(170, 410)
$basic.Controls.Add($status)

$labelSlider = New-Object System.Windows.Forms.Label
$labelSlider.Text = "Range Value"
$labelSlider.AutoSize = $true
$labelSlider.Location = New-Object System.Drawing.Point(30, 40)
$advanced.Controls.Add($labelSlider)

$slider = New-Object System.Windows.Forms.TrackBar
$slider.Name = "RangeSlider"
$slider.Minimum = 0
$slider.Maximum = 100
$slider.Value = 25
$slider.TickFrequency = 10
$slider.Width = 520
$slider.Location = New-Object System.Drawing.Point(170, 25)
$advanced.Controls.Add($slider)

$dialogButton = New-Object System.Windows.Forms.Button
$dialogButton.Name = "OpenNativeDialog"
$dialogButton.Text = "Open Native Dialog"
$dialogButton.Width = 190
$dialogButton.Height = 36
$dialogButton.Location = New-Object System.Drawing.Point(170, 100)
$advanced.Controls.Add($dialogButton)

$dialogButton.Add_Click({
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = "KAREEM LAB DIALOG"
    $dlg.StartPosition = "CenterParent"
    $dlg.Size = New-Object System.Drawing.Size(420, 220)

    $dlgLabel = New-Object System.Windows.Forms.Label
    $dlgLabel.Text = "Universal modal dialog"
    $dlgLabel.AutoSize = $true
    $dlgLabel.Location = New-Object System.Drawing.Point(25, 25)
    $dlg.Controls.Add($dlgLabel)

    $dlgEdit = New-Object System.Windows.Forms.TextBox
    $dlgEdit.Name = "DialogText"
    $dlgEdit.Width = 330
    $dlgEdit.Location = New-Object System.Drawing.Point(25, 65)
    $dlg.Controls.Add($dlgEdit)

    $dlgClose = New-Object System.Windows.Forms.Button
    $dlgClose.Text = "Close Dialog"
    $dlgClose.Width = 120
    $dlgClose.Location = New-Object System.Drawing.Point(25, 110)
    $dlgClose.Add_Click({ $dlg.Close() })
    $dlg.Controls.Add($dlgClose)

    [void]$dlg.ShowDialog($form)
    $dlg.Dispose()
})

$run.Add_Click({
    $textOk = -not [string]::IsNullOrWhiteSpace($textBox.Text)
    $checkOk = $check.Checked
    $comboOk = ($combo.SelectedItem -eq "Expert")
    $listOk = ($list.SelectedItem -eq "Gamma")
    $radioOk = $radioB.Checked
    $rangeOk = ($slider.Value -ge 69 -and $slider.Value -le 81)

    if ($textOk -and $checkOk -and $comboOk -and $listOk -and $radioOk -and $rangeOk) {
        $status.Text = "PASS - universal controls verified"
        $form.Text = "KAREEM UI LAB - PASS"
    }
    else {
        $status.Text = "FAIL - inspect state and retry"
        $form.Text = "KAREEM UI LAB - FAIL"
    }
})

$form.Controls.Add($tabs)
[System.Windows.Forms.Application]::Run($form)
'''

def main():
    PS1.write_text(NATIVE_PS, encoding="utf-8")

    subprocess.Popen([
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(PS1)
    ]).wait()


if __name__ == "__main__":
    main()
