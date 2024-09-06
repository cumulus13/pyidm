; Define the global hotkey
^!d::
{
    ; Retrieve the clipboard content
    ClipSaved := ClipboardAll()
    ClipboardContent := A_Clipboard
    Clipboard := ClipSaved
    ClipSaved := ""
    ; URL := ClipboardContent
    ; APP := "c:\Program Files (x86)\Internet Download Manager\IDMan.exe"

    ; Check if the clipboard content starts with 'http://', 'https://', 'ftp://', or 'ftps://'
    if (InStr(ClipboardContent, "http://") == 1 || InStr(ClipboardContent, "https://") == 1 || InStr(ClipboardContent, "ftp://") == 1 || InStr(ClipboardContent, "ftps://") == 1) {
    	URL := ClipboardContent
        ;will run
        ; MsgBox "`"%APP%`" `"/d `"%URL%`" /p `"c:\DOWNLOAD`" /n"
        ; Run the command with the URL
        Run "idm `"" URL "`" -p `"c:\DOWNLOAD`" "
    } else {
        MsgBox Format("The clipboard does not contain a valid URL. '{1}'", %ClipboardContent%)
    }
    return
}

#!n::WinMinimize "A"
#!x::WinClose "A"
^!x::ExitApp
^!+Right::
{
	Run, "mpc next", , hide
}
^!+Left::
{
	Run "mpc prev"
}
^!+Home::
{
	Run "mpc play"
}
^!+End::
{
	Run "mpc stop"
}


