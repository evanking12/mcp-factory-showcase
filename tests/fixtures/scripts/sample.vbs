' sample.vbs — Demo VBScript file for MCP Factory script_analyzer tests.
'
' Exercises: Sub and Function declarations so the VBScript extraction
' path in script_analyzer.py is exercised.

Option Explicit

' ---------------------------------------------------------------------------
' CompressFile  –  Compress a file using Shell.Application.
'
' Parameters:
'   sourcePath  String  Path to the input file.
'   destPath    String  Path for the ZIP output.
' ---------------------------------------------------------------------------
Sub CompressFile(sourcePath, destPath)
    Dim fso, shell
    Set fso   = CreateObject("Scripting.FileSystemObject")
    Set shell = CreateObject("Shell.Application")

    If Not fso.FileExists(sourcePath) Then
        WScript.Echo "ERROR: source file not found: " & sourcePath
        Exit Sub
    End If

    ' Create empty ZIP wrapper
    Dim newZip
    newZip = "PK" & Chr(5) & Chr(6) & String(18, Chr(0))
    Dim ts
    Set ts = fso.CreateTextFile(destPath, True)
    ts.Write newZip
    ts.Close

    ' Copy file into ZIP
    Dim zipFolder
    Set zipFolder = shell.NameSpace(destPath)
    zipFolder.CopyHere sourcePath
    WScript.Sleep 500
End Sub

' ---------------------------------------------------------------------------
' ListExports  –  Return a comma-separated string of exported symbol names.
'
' Parameters:
'   dllPath       String  Path to the DLL file.
'   filterPrefix  String  Optional prefix filter (empty = all symbols).
'
' Returns:
'   String  Comma-separated symbol names.
' ---------------------------------------------------------------------------
Function ListExports(dllPath, filterPrefix)
    Dim wsh, exec, line, symbols
    Set wsh  = CreateObject("WScript.Shell")
    Set exec = wsh.Exec("dumpbin /exports """ & dllPath & """")

    symbols = ""
    Do While Not exec.StdOut.AtEndOfStream
        line = exec.StdOut.ReadLine()
        Dim matches
        If line Like "*  [0-9]*  [0-9A-F]*  [0-9A-F]*  *" Then
            Dim parts
            parts = Split(Trim(line))
            Dim sym
            sym = parts(UBound(parts))
            If filterPrefix = "" Or Left(sym, Len(filterPrefix)) = filterPrefix Then
                If symbols <> "" Then symbols = symbols & ","
                symbols = symbols & sym
            End If
        End If
    Loop
    ListExports = symbols
End Function

' ---------------------------------------------------------------------------
' ScoreConfidence  –  Return a confidence label string.
'
' Parameters:
'   symbolName  String   Export symbol name.
'   hasDoc      Boolean  True if a header/doc was found.
'   isSigned    Boolean  True if the binary is digitally signed.
'
' Returns:
'   String  One of: "guaranteed", "high", "medium", "low"
' ---------------------------------------------------------------------------
Function ScoreConfidence(symbolName, hasDoc, isSigned)
    If hasDoc And isSigned Then
        ScoreConfidence = "guaranteed"
    ElseIf hasDoc Or isSigned Then
        ScoreConfidence = "high"
    ElseIf Left(symbolName, 1) <> "_" Then
        ScoreConfidence = "medium"
    Else
        ScoreConfidence = "low"
    End If
End Function

' ---------------------------------------------------------------------------
' WriteMcpJson  –  Write a minimal MCP JSON stub to a file.
'
' Parameters:
'   outputPath  String   Destination .json path.
'   sourceFile  String   The analysed file path.
'   itemCount   Integer  Number of invocables discovered.
' ---------------------------------------------------------------------------
Sub WriteMcpJson(outputPath, sourceFile, itemCount)
    Dim fso, ts
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set ts  = fso.CreateTextFile(outputPath, True, True)
    ts.WriteLine "{"
    ts.WriteLine "  ""source_file"": """ & sourceFile & ""","
    ts.WriteLine "  ""invocable_count"": " & itemCount & ","
    ts.WriteLine "  ""invocables"": []"
    ts.WriteLine "}"
    ts.Close
End Sub
